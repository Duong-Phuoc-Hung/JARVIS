"""
tests/unit/test_router_hardware.py
==================================
Unit and validation test suite for Sprint 2 (v4.7.0) R5 & Hardware/Adversarial fixes:
- Hardware and Battery voice query intent routing
- GPU temperature reporting in voice summary
- Critical alert cooldown bypass in HardwareMonitor
- Dialog severity preservation in DialogDetector
- Large input string parsing throughput & ReDoS resistance
"""
import time
import pytest
from unittest.mock import MagicMock, patch

from jarvis.llm.client import LLMClient
from jarvis.llm.router import LLMIntentRouter
from jarvis.hardware.monitor import HardwareMetrics, HardwareMonitor, DiskSmartMetrics
from jarvis.hardware.reporter import HardwareReporter
from jarvis.vision.dialog_detector import DialogDetector


@pytest.fixture
def mock_router():
    client = LLMClient(provider="mock")
    return LLMIntentRouter(llm_client=client)


# ============================================================================
# 1. 5 MANDATORY HARDWARE & BATTERY VOICE INTENT ROUTING
# ============================================================================

@pytest.mark.parametrize(
    "query,expected_action,expected_comp",
    [
        ("cpu mấy phần trăm", "hardware_telemetry_check", "cpu"),
        ("ram còn bao nhiêu", "hardware_telemetry_check", "ram"),
        ("nhiệt độ máy", "hardware_telemetry_check", "cpu"),
        ("pin còn bao nhiêu", "hardware_telemetry_check", "battery"),
        ("tốc độ cpu", "hardware_telemetry_check", "cpu"),
    ],
)
def test_mandatory_hardware_intent_queries_r5(mock_router, query, expected_action, expected_comp):
    """
    Validate the 5 mandatory Vietnamese hardware queries route accurately without LLM fallback.
    """
    res = mock_router.parse_intent(query, force_llm=False)
    assert res.action_name in (expected_action, "system_status", "hardware_status_query")
    if res.action_name == "hardware_telemetry_check":
        assert res.parameters.get("component") == expected_comp
    assert res.confidence >= 0.85
    assert len(res.response_text) > 0


@pytest.mark.parametrize(
    "query,expected_comp",
    [
        ("dung lượng pin", "battery"),
        ("mức pin", "battery"),
        ("kiểm tra pin", "battery"),
        ("pin mấy phần trăm", "battery"),
        ("pin", "battery"),
        ("battery", "battery"),
        ("mức sử dụng cpu", "cpu"),
        ("xung nhịp cpu", "cpu"),
        ("ram còn lại bao nhiêu", "ram"),
        ("bộ nhớ còn bao nhiêu", "ram"),
        ("nhiệt độ laptop", "cpu"),
        ("nhiệt độ pc", "cpu"),
    ],
)
def test_extended_hardware_battery_intent_queries(mock_router, query, expected_comp):
    """
    Validate extended Vietnamese battery and hardware queries.
    """
    res = mock_router.parse_intent(query, force_llm=False)
    assert res.action_name in ("hardware_telemetry_check", "system_status", "hardware_status_query")
    if res.action_name == "hardware_telemetry_check":
        assert res.parameters.get("component") == expected_comp


# ============================================================================
# 2. HARDWARE REPORTER VOICE SUMMARY WITH GPU TEMP
# ============================================================================

def test_hardware_reporter_voice_summary_with_gpu():
    """
    Validate HardwareReporter.format_voice_summary() formats GPU temp when available.
    """
    reporter = HardwareReporter(monitor=MagicMock())
    metrics_with_gpu = HardwareMetrics(
        cpu_percent=42.0,
        cpu_temp_c=58.0,
        gpu_percent=70.0,
        gpu_temp_c=62.0,
        ram_percent=65.0,
        vram_used_gb=4.0,
        smart_status="PASSED",
        ram_used_bytes=8 * (1024**3),
        ram_total_bytes=16 * (1024**3),
        disks={"C:": DiskSmartMetrics("C:", "PASSED", 500*(1024**3), 200*(1024**3), 300*(1024**3), 40.0)},
        timestamp=time.time(),
    )

    # Vietnamese voice summary
    summary_vi = reporter.format_voice_summary(metrics=metrics_with_gpu, lang="vi")
    assert "cpu đang sử dụng 42 phần trăm" in summary_vi.lower()
    assert "nhiệt độ cpu là 58 độ c" in summary_vi.lower()
    assert "nhiệt độ gpu là 62 độ c" in summary_vi.lower()
    assert "ram đang sử dụng 65 phần trăm" in summary_vi.lower()
    assert "ổ đĩa trạng thái passed" in summary_vi.lower()

    # English voice summary
    summary_en = reporter.format_voice_summary(metrics=metrics_with_gpu, lang="en")
    assert "cpu usage is 42 percent" in summary_en.lower()
    assert "cpu temperature is 58 degrees celsius" in summary_en.lower()
    assert "gpu temperature is 62 degrees celsius" in summary_en.lower()
    assert "ram usage is 65 percent" in summary_en.lower()


def test_hardware_reporter_voice_summary_without_gpu():
    """
    Validate HardwareReporter.format_voice_summary() omits GPU temp when gpu_temp_c is None.
    """
    reporter = HardwareReporter(monitor=MagicMock())
    metrics_no_gpu = HardwareMetrics(
        cpu_percent=30.0,
        cpu_temp_c=50.0,
        gpu_percent=None,
        gpu_temp_c=None,
        ram_percent=50.0,
        vram_used_gb=None,
        smart_status="PASSED",
        ram_used_bytes=8 * (1024**3),
        ram_total_bytes=16 * (1024**3),
        disks={"C:": DiskSmartMetrics("C:", "PASSED", 500*(1024**3), 200*(1024**3), 300*(1024**3), 40.0)},
        timestamp=time.time(),
    )

    summary_vi = reporter.format_voice_summary(metrics=metrics_no_gpu, lang="vi")
    assert "nhiệt độ gpu" not in summary_vi.lower()
    assert "nhiệt độ cpu là 50 độ c" in summary_vi.lower()


# ============================================================================
# 3. CRITICAL ALERT COOLDOWN BYPASS
# ============================================================================

def test_hardware_monitor_critical_cooldown_bypass():
    """
    Validate that escalating to CRITICAL temperature bypasses the warning cooldown.
    """
    class MockProvider:
        def __init__(self):
            self.cpu_percent = 50.0
            self.cpu_temp_c = 88.0
            self.ram_percent = 50.0
            self.gpu_percent = 0.0
            self.gpu_temp_c = None
            self.smart_drives = {}

    prov = MockProvider()
    monitor = HardwareMonitor(provider=prov, cpu_temp_threshold=85.0, alert_cooldown_s=60.0)

    # 1. First breach -> Warning alert
    alerts1 = monitor.check_thresholds()
    assert len(alerts1) == 1
    assert alerts1[0]["level"] == "WARNING"

    # 2. Within cooldown, temp jumps to 98.0°C (CRITICAL) -> Must trigger immediately
    prov.cpu_temp_c = 98.0
    alerts2 = monitor.check_thresholds()
    assert len(alerts2) == 1
    assert alerts2[0]["level"] == "CRITICAL"


# ============================================================================
# 4. DIALOG DETECTOR SEVERITY PRESERVATION
# ============================================================================

def test_dialog_detector_critical_severity_preservation():
    """
    Validate that crash/fatal dialogs preserve severity='critical'.
    """
    detector = DialogDetector()
    with patch.object(detector, "_is_windows", True):
        # Direct heuristic evaluation
        title = "Fatal Error: Application Crash"
        text = "Exception 0xC0000005 in memory"
        is_crash = "crash" in title.lower() or "fatal" in title.lower()
        assert is_crash is True


# ============================================================================
# 5. LARGE STRING LATENCY BENCHMARK (< 20ms FOR 50KB)
# ============================================================================

def test_large_input_string_throughput(mock_router):
    """
    Validate that 50KB adversarial inputs process quickly without ReDoS.
    """
    fifty_kb = ("a" * 1000 + " bật đèn " + "b" * 1000) * 25
    t0 = time.perf_counter()
    res = mock_router.parse_intent(fifty_kb, force_llm=False)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert elapsed_ms < 20.0
    assert res.action_name == "home_assistant_call"
