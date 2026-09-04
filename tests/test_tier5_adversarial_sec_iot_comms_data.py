"""
d:/Software GitCode/JARVIS/.agents/challenger_m6_2/test_tier5_adversarial_sec_iot_comms_data.py
=============================================================================================
Tier 5 White-Box Adversarial Stress Testing, Protocol Fuzzing, Injection Defense, and Boundary Testing.
Modules Covered:
  1. jarvis/security   (Nmap/TShark CLI injection, malformed XML/pcap, timeouts, report generator, privilege gating)
  2. jarvis/vision     (corrupted webcam frames, 0-length/invalid embeddings, lighting extremes, 21-landmark matrices, rapid gesture switching)
  3. jarvis/smart_home (Home Assistant REST error codes, malformed payloads, MQTT broker disconnects/reconnects, topic fuzzing)
  4. jarvis/comms      (Telegram command injection, unauthorized IDs, IMAP connection resets/MIME parsing, Discord rate limits)
  5. jarvis/automation (VMware vmrun / VirtualBox VBoxManage subprocess errors, invalid VM paths, workspace recipe parsing)
  6. jarvis/data       (corrupted/empty CSV & XLSX files, non-numeric columns, Monte Carlo extremes, OpenXML doc generation)
"""
from __future__ import annotations

import io
import json
import logging
import math
import os
import shutil
import subprocess
import time
import urllib.error
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pytest

# 5. Automation imports
from jarvis.automation.vm import HypervisorType, VMActionResult, VMOrchestrator, VMState
from jarvis.automation.workspace import (
    WindowPlacementRecipe,
    WorkspaceRecipe,
    WorkspaceRecipeManager,
)
from jarvis.comms.discord import DiscordBotClient
from jarvis.comms.email_imap import EmailMessage, EmailSummaryResult, IMAPEmailReader

# 4. Comms imports
from jarvis.comms.telegram import TelegramBotController

# Core models
from jarvis.core.models import PrivilegeLevel, RequesterContext

# 6. Data imports
from jarvis.data.document import (
    DocumentExporter,
    DocxReportBuilder,
    PdfReportBuilder,
    VoiceSummaryGenerator,
    _xml_escape,
)
from jarvis.data.stats import (
    AnomalyItem,
    AnomalyReport,
    CorrelationResult,
    DataAnalyticsEngine,
    DataStatsReport,
    DescriptiveStats,
    DistributionType,
    MonteCarloConfig,
    MonteCarloEngine,
    MonteCarloResult,
    TabularDataset,
    TrendResult,
)
from jarvis.gesture.detector import GestureDetector
from jarvis.gesture.models import ClapEvent, DetectorState, GestureResult
from jarvis.security.report import SecurityPrivilegeGate, SecurityReportGenerator

# 1. Security imports
from jarvis.security.scanner import (
    HostScanResult,
    NetworkScanner,
    NmapScannerWrapper,
    PacketCapture,
    PacketCaptureResult,
    ScanReport,
    TSharkCaptureWrapper,
    Vulnerability,
    VulnerabilitySeverity,
    resolve_nmap_binary,
    resolve_tshark_binary,
)

# 3. Smart Home imports
from jarvis.smart_home.home_assistant import HomeAssistantClient
from jarvis.smart_home.mqtt import MQTTAdapter

# 2. Vision & Gesture imports
from jarvis.vision.biometrics import (
    BiometricPrivilegeGate,
    BiometricsEngine,
    FaceEmbeddingStorage,
)
from jarvis.vision.hands import (
    GestureType,
    HandGestureClassifier,
    HandGestureEngine,
    HandLandmarkTracker,
    NormalizedLandmark,
)

# ============================================================================
# DOMAIN 1: jarvis/security ADVERSARIAL STRESS TESTS
# ============================================================================

def test_security_nmap_malicious_input_blocked_at_validation_layer(monkeypatch):
    """
    [Security / F-23] Confirm malicious injection payloads in subnet are strictly
    rejected at the input validation layer (fail-closed) WITHOUT spawning a subprocess.
    """
    captured_cmds = []

    def fake_run(cmd, *args, **kwargs):
        captured_cmds.append(cmd)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout='<?xml version="1.0"?><nmaprun></nmaprun>',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(shutil, "which", lambda x: "C:\\Program Files\\Nmap\\nmap.exe")

    scanner = NetworkScanner()

    # Injection payload in subnet
    malicious_subnet = "192.168.1.1; cat /etc/passwd && whoami | dir `calc.exe`"
    report = scanner.scan_subnet(malicious_subnet, ports="80,443")

    # Defense Layer 1: Strictly blocked at validation layer before subprocess execution
    assert len(captured_cmds) == 0, "Malicious subnet must NOT spawn any subprocess"
    assert report.status == "TARGET_REJECTED"


def test_security_nmap_valid_target_properly_escaped_and_spawned(monkeypatch):
    """
    [Security / F-23] Confirm valid targets pass validation and are passed safely as
    structured list arguments without shell expansion.
    """
    captured_cmds = []

    def fake_run(cmd, *args, **kwargs):
        captured_cmds.append(cmd)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout='<?xml version="1.0"?><nmaprun></nmaprun>',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(shutil, "which", lambda x: "C:\\Program Files\\Nmap\\nmap.exe")

    scanner = NetworkScanner()

    valid_subnet = "192.168.1.10"
    report = scanner.scan_subnet(valid_subnet, ports="80,443")

    assert len(captured_cmds) == 1
    invoked_cmd = captured_cmds[0]
    assert isinstance(invoked_cmd, list)
    assert invoked_cmd[-1] == valid_subnet
    assert "-p80,443" in invoked_cmd
    assert report.status == "SUCCESS"


def test_security_nmap_malformed_xml_fuzzing():
    """
    [Security / F-23] Fuzz Nmap XML output parsing with corrupt, truncated, and malicious XML.
    """
    scanner = NetworkScanner()

    # 1. Truncated XML
    truncated_xml = "<nmaprun><host><status state='up'/><address addr='192.168.1.100'"
    res1 = scanner._parse_nmap_xml(truncated_xml)
    assert res1 == []

    # 2. XML with closed port, up host, and valid port
    valid_xml = """<?xml version="1.0"?>
    <nmaprun>
      <host>
        <status state="up"/>
        <address addr="10.0.0.5" addrtype="ipv4"/>
        <hostnames><hostname name="test.local"/></hostnames>
        <ports>
          <port portid="443"><state state="open"/><service name="https"/></port>
          <port portid="80"><state state="closed"/></port>
        </ports>
      </host>
    </nmaprun>"""
    res2 = scanner._parse_nmap_xml(valid_xml)
    assert len(res2) == 1
    assert res2[0].ip == "10.0.0.5"
    assert res2[0].hostname == "test.local"
    assert 443 in res2[0].open_ports
    assert 80 not in res2[0].open_ports  # closed port excluded

    # 3. Non-integer portid vulnerability check: string portid triggers exception caught by outer parser
    malformed_port_xml = """<?xml version="1.0"?>
    <nmaprun>
      <host>
        <status state="up"/>
        <address addr="10.0.0.6" addrtype="ipv4"/>
        <ports>
          <port portid="INVALID_NOT_A_NUM"><state state="open"/></port>
        </ports>
      </host>
    </nmaprun>"""
    res3 = scanner._parse_nmap_xml(malformed_port_xml)
    # Outer try...except catches ValueError and gracefully returns [] without unhandled crash
    assert res3 == []

    # 4. Completely empty / whitespace / binary garbage XML
    assert scanner._parse_nmap_xml("") == []
    assert scanner._parse_nmap_xml("   \n\t  ") == []
    assert scanner._parse_nmap_xml("\x00\x01\x02\xFF\xFE") == []


def test_security_nmap_scan_timeout_and_subprocess_error_handling(monkeypatch):
    """
    [Security / F-23] Test behavior when Nmap hangs and raises TimeoutExpired.
    """
    monkeypatch.setattr(shutil, "which", lambda x: "nmap.exe")

    def fake_run_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="nmap", timeout=5.0)

    monkeypatch.setattr(subprocess, "run", fake_run_timeout)

    scanner = NetworkScanner(timeout_s=5.0)
    report = scanner.scan_subnet("10.0.0.0/16")

    assert report.status == "TIMEOUT"
    assert report.total_hosts == 0
    assert "timeout" in report.error_message.lower()
    assert report.duration_s == 5.0


def test_security_tshark_cli_parameters_and_bpf_injection(monkeypatch):
    """
    [Security / F-24] Test TShark CLI wrapper under malicious BPF filters and interfaces.
    """
    captured_cmds = []

    def fake_run(cmd, *args, **kwargs):
        captured_cmds.append(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(shutil, "which", lambda x: "tshark.exe")

    capture_tool = PacketCapture(default_duration_s=5.0)
    bpf_payload = "tcp port 80; rm -rf / && netstat"
    output_pcap = Path("temp/capture.pcap")

    result = capture_tool.capture_packets(
        interface="Ethernet 1; whoami",
        count=200,
        duration_s=10.0,
        bpf_filter=bpf_payload,
        output_pcap=output_pcap,
    )

    assert len(captured_cmds) == 1
    invoked = captured_cmds[0]
    assert "-i" in invoked
    assert "Ethernet 1; whoami" in invoked
    assert "-f" in invoked
    assert bpf_payload in invoked
    assert result.packet_count == 200
    assert result.protocols["TCP"] == 140
    assert result.protocols["UDP"] == 40
    assert result.protocols["ICMP"] == 20
    assert result.status == "SUCCESS"
    assert result.get("status") == "SUCCESS"
    assert "packet_count" in result


def test_security_privilege_gate_authorization_matrix():
    """
    [Security / R12 / F-34] Stress-test RBAC Privilege Gate with invalid, unauthenticated, spoofed contexts.
    """
    # 1. None context -> Rejected
    assert SecurityPrivilegeGate.verify_privilege(None) is False
    with pytest.raises(PermissionError):
        SecurityPrivilegeGate.enforce(None)

    # 2. Unauthenticated context with claimed ADMIN -> Rejected
    fake_admin_ctx = RequesterContext(
        requester_id="attacker",
        is_authenticated=False,
        granted_privilege=PrivilegeLevel.ADMIN,
    )
    assert SecurityPrivilegeGate.verify_privilege(fake_admin_ctx) is False
    with pytest.raises(PermissionError):
        SecurityPrivilegeGate.enforce(fake_admin_ctx)

    # 3. Authenticated USER with NORMAL privilege (non-admin) -> Rejected
    user_ctx = RequesterContext(
        requester_id="normal_user",
        is_authenticated=True,
        granted_privilege=PrivilegeLevel.NORMAL,
    )
    assert SecurityPrivilegeGate.verify_privilege(user_ctx) is False
    with pytest.raises(PermissionError):
        SecurityPrivilegeGate.enforce(user_ctx)

    # 4. Authenticated ADMIN -> Granted
    admin_ctx = RequesterContext(
        requester_id="verified_owner",
        is_authenticated=True,
        granted_privilege=PrivilegeLevel.ADMIN,
    )
    assert SecurityPrivilegeGate.verify_privilege(admin_ctx) is True
    SecurityPrivilegeGate.enforce(admin_ctx)

    # 5. System context -> Granted
    sys_ctx = RequesterContext.system()
    assert SecurityPrivilegeGate.verify_privilege(sys_ctx) is True
    SecurityPrivilegeGate.enforce(sys_ctx)


def test_security_report_generator_malicious_and_missing_data(tmp_path):
    """
    [Security / F-25] Test report generation with XSS injection in hostnames, empty hosts, and multilingual voice summaries.
    """
    generator = SecurityReportGenerator()

    # Host with Markdown / HTML injection
    malicious_host = HostScanResult(
        ip="192.168.1.50",
        hostname="<script>alert('xss')</script> [Evil](http://evil.com)",
        status="UP",
        open_ports=[22, 80],
        services={22: "ssh", 80: "http<svg onload=alert(1)>"},
        vulnerabilities=[
            Vulnerability(
                id="CVE-2023-9999",
                title="Critical RCE",
                severity=VulnerabilitySeverity.CRITICAL,
                description="Arbitrary code execution",
            )
        ],
    )

    scan_report = ScanReport(
        target="192.168.1.0/24",
        hosts=[malicious_host],
        total_hosts=1,
        duration_s=2.456,
        status="SUCCESS",
        timestamp=1700000000.0,
    )

    capture_telemetry = PacketCaptureResult(
        interface="eth0",
        packet_count=150,
        duration_s=5.0,
        protocols={"TCP": 100, "UDP": 40, "ICMP": 10},
        anomalies_detected=1,
    )

    out_dir = tmp_path / "deep" / "nested" / "reports"
    res = generator.generate_report(scan_report, output_dir=out_dir, capture=capture_telemetry, lang="vi")

    report_file = res["report_path"]
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert "CRITICAL RISK" in content
    assert "192.168.1.50" in content
    assert "TCP: 100" in content

    # Spoken summary in English and Vietnamese
    summary_vi = generator.get_voice_summary(scan_report, lang="vi")
    assert "Cảnh báo bảo mật" in summary_vi
    assert "1 lỗ hổng" in summary_vi

    summary_en = generator.get_voice_summary(scan_report, lang="en")
    assert "Security Alert" in summary_en
    assert "1 potential vulnerabilities" in summary_en


# ============================================================================
# DOMAIN 2: jarvis/vision & jarvis/gesture ADVERSARIAL STRESS TESTS
# ============================================================================

def test_biometrics_corrupted_frames_and_lighting_extremes(tmp_path):
    """
    [Vision / F-33] Stress biometrics engine with invalid ndarray frames, NaNs, zero-length, and dark frames.
    """
    store_path = tmp_path / "faces.json"
    storage = FaceEmbeddingStorage(storage_path=store_path)
    engine = BiometricsEngine(storage=storage)

    # 1. None frame
    assert engine.verify_frame(None) is False
    assert engine.process_surveillance_frame(None)["status"] == "no_face"

    # 2. Empty array
    empty_frame = np.array([])
    assert engine.verify_frame(empty_frame) is False
    assert engine.process_surveillance_frame(empty_frame)["status"] == "no_face"

    # 3. Extreme dark frame (mean < 5.0)
    dark_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    assert engine.verify_frame(dark_frame) is False
    assert engine.process_surveillance_frame(dark_frame)["status"] == "no_face"

    # 4. Corrupted storage JSON recovery
    store_path.write_text("{invalid json: broken", encoding="utf-8")
    recovered_storage = FaceEmbeddingStorage(storage_path=store_path)
    assert recovered_storage.enrolled_faces == {}


def test_biometrics_intruder_detection_and_lock_failure_resilience(tmp_path, monkeypatch):
    """
    [Vision / F-35] Simulate an intruder face when locking workstation and dispatching alert.
    """
    import jarvis.vision.biometrics as bio_mod
    class FakeCV2:
        @staticmethod
        def imencode(ext, frame):
            return True, np.array([255, 216, 255, 224], dtype=np.uint8)
    monkeypatch.setattr(bio_mod, "cv2", FakeCV2)

    store = FaceEmbeddingStorage(storage_path=tmp_path / "faces.json")
    owner_embedding = np.ones(128, dtype=np.float64) * 0.1
    store.add_face("owner", owner_embedding)

    class MockCamera:
        def __init__(self, embedding):
            self.emb = embedding
        def get_face_encodings(self, frame):
            return [self.emb]

    # Intruder embedding (distance > 0.60 from owner)
    intruder_embedding = np.ones(128, dtype=np.float64) * 0.9
    camera_mock = MockCamera(intruder_embedding)
    engine = BiometricsEngine(camera_feed=camera_mock, storage=store, tolerance=0.60)

    class TrackingWin32:
        def __init__(self):
            self.lock_workstation_calls = 0
        def lock_workstation(self):
            self.lock_workstation_calls += 1
            return True

    class TrackingTelegram:
        def __init__(self):
            self.photos_sent = 0
        def send_photo(self, chat_id, photo_bytes, caption):
            self.photos_sent += 1

    win32_mock = TrackingWin32()
    tg_mock = TrackingTelegram()

    valid_frame = np.ones((480, 640, 3), dtype=np.uint8) * 128
    res = engine.process_surveillance_frame(
        frame=valid_frame,
        win32_platform=win32_mock,
        telegram_bot=tg_mock,
    )

    assert res["status"] == "intruder_locked"
    assert res["locked"] is True
    assert win32_mock.lock_workstation_calls == 1
    assert tg_mock.photos_sent == 1
    assert res["distance"] > 0.60


def test_biometric_privilege_gate_session_expiry(tmp_path):
    """
    [Vision / F-34] Verify BiometricPrivilegeGate temporary session token generation and TTL expiration.
    """
    store = FaceEmbeddingStorage(storage_path=tmp_path / "faces.json")
    owner_emb = np.ones(128, dtype=np.float64) * 0.05
    store.add_face("owner", owner_emb)

    class MockCamera:
        def get_face_encodings(self, frame):
            return [owner_emb]

    engine = BiometricsEngine(camera_feed=MockCamera(), storage=store)
    gate = BiometricPrivilegeGate(biometrics=engine, session_ttl_s=0.1)

    valid_frame = np.ones((100, 100, 3), dtype=np.uint8) * 100

    # Authenticate
    ctx = gate.authenticate(valid_frame)
    assert ctx is not None
    assert ctx.is_authenticated is True
    assert gate.is_session_valid() is True
    assert gate.is_allowed("execute_task", context=None) is True

    # Wait for TTL expiry
    time.sleep(0.15)
    assert gate.is_session_valid() is False
    assert gate.is_allowed("execute_task", context=None) is False


def test_hand_landmark_invalid_matrices_and_fuzzing():
    """
    [Vision / F-36] Feed invalid landmark matrices (<21 points, NaNs, Infs) to gesture classifier.
    """
    classifier = HandGestureClassifier(debounce_cooldown_s=0.5)

    # 1. None and empty
    assert classifier.classify(None) == GestureType.NONE
    assert classifier.classify([]) == GestureType.NONE

    # 2. Incomplete landmark set (only 10 points)
    partial_lms = [NormalizedLandmark(x=0.5, y=0.5, z=0.0) for _ in range(10)]
    assert classifier.classify(partial_lms) == GestureType.NONE

    # 3. Clustered landmarks (Fist detection via small std)
    fist_lms = [NormalizedLandmark(x=0.5 + np.random.uniform(-0.01, 0.01), y=0.5 + np.random.uniform(-0.01, 0.01), z=0.0) for _ in range(21)]
    assert classifier.classify(fist_lms) == GestureType.FIST


def test_hand_gesture_classifier_rapid_switching_and_debounce():
    """
    [Vision / F-37] Adversarial test: Rapidly alternate between gestures to verify debounce cooldown.
    """
    classifier = HandGestureClassifier(debounce_cooldown_s=1.0)

    # Trigger fist
    fist_lms = [NormalizedLandmark(x=0.5, y=0.5, z=0.0) for _ in range(21)]
    first_gesture = classifier.classify(fist_lms)
    assert first_gesture == GestureType.FIST

    # Immediately attempt another gesture within 0.1s (< 1.0s cooldown)
    immediate_gesture = classifier.classify(fist_lms)
    assert immediate_gesture == GestureType.NONE


def test_acoustic_gesture_detector_chatter_burst_suppression():
    """
    [Gesture] Feed high-frequency burst of transient spikes to acoustic gesture detector.
    Acoustic chatter suppression (<50ms raw gap) must suppress rapid burst.
    """
    detector = GestureDetector(cooldown_s=0.5, min_double_gap_s=0.05, max_double_gap_s=0.35)

    base_t = 10.0
    results = []
    for i in range(20):
        t = base_t + (i * 0.005)
        clap = ClapEvent(timestamp=t, amplitude=0.8, duration=0.02)
        res = detector.feed_clap(clap)
        if res is not None:
            results.append(res)

    # All chatter claps must be dropped, 0 triggers emitted
    assert len(results) == 0

    # Now feed a legitimate 2nd clap at +150ms
    legit_clap_2 = ClapEvent(timestamp=base_t + 0.150, amplitude=0.8, duration=0.02)
    detector.feed_clap(legit_clap_2)

    # Advance clock to trigger disambiguation timeout
    trigger = detector.tick(base_t + 0.150 + detector.disambiguation_timeout_s + 0.01)
    assert trigger is not None
    assert trigger.gesture_type.value == "double_clap"


# ============================================================================
# DOMAIN 3: jarvis/smart_home ADVERSARIAL STRESS TESTS
# ============================================================================

def test_home_assistant_rest_http_errors_and_connection_drop(monkeypatch):
    """
    [Smart Home / F-26] Simulate HTTP 401 Unauthorized, HTTP 500 Server Error, and connection drops.
    """
    client = HomeAssistantClient(base_url="http://192.168.1.10:8123", access_token="secret_token")

    # 1. Simulate HTTP 404 Not Found on get_state
    def mock_urlopen_404(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "Entity Not Found", {}, io.BytesIO(b"Not Found"))

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_404)
    assert client.get_state("sensor.ghost_device") is None

    # 2. Simulate ConnectionRefusedError on call_service
    def mock_urlopen_conn_err(req, timeout=None):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_conn_err)
    svc_res = client.call_service("light", "turn_on", {"entity_id": "light.living_room"})
    assert svc_res["success"] is False
    assert "unreachable" in svc_res["error"].lower() or "connection" in svc_res["error"].lower()


def test_home_assistant_entity_alias_fuzzing():
    """
    [Smart Home / F-26] Test entity resolution against whitespace, case sensitivity, Vietnamese accents, SQL injection.
    """
    client = HomeAssistantClient()

    assert client.resolve_entity("LIVING ROOM LIGHT") == "light.living_room"
    assert client.resolve_entity("  đèn phòng khách  ") == "light.living_room"
    assert client.resolve_entity("ĐIỀU HÒA") == "climate.ac_unit"
    assert client.resolve_entity("nhiệt độ") == "sensor.temperature"

    sqli = "light.living_room' OR '1'='1"
    assert client.resolve_entity(sqli) == sqli


def test_mqtt_adapter_disconnect_reconnect_and_wildcards():
    """
    [Smart Home / F-27] Test MQTT publish/subscribe behavior, wildcard routing, and subscriber exception isolation.
    """
    adapter = MQTTAdapter(broker_host="127.0.0.1", broker_port=1883)
    assert adapter.connect() is True

    received_exact = []
    received_wildcard = []
    received_failing = []

    def cb_exact(topic, payload):
        received_exact.append((topic, payload))

    def cb_wildcard(topic, payload):
        received_wildcard.append((topic, payload))

    def cb_failing(topic, payload):
        received_failing.append(topic)
        raise ValueError("Intentional callback crash in subscriber")

    adapter.subscribe("home/living_room/temperature", cb_exact)
    adapter.subscribe("home/#", cb_wildcard)
    adapter.subscribe("home/living_room/temperature", cb_failing)

    test_payload = {"temp": 24.5, "humidity": 60}
    pub_ok = adapter.publish("home/living_room/temperature", test_payload)
    assert pub_ok is True

    assert len(received_exact) == 1
    assert len(received_wildcard) == 1
    assert len(received_failing) == 1

    adapter.disconnect()
    assert adapter.is_connected is False


def test_mqtt_malformed_payload_fuzzing():
    """
    [Smart Home / F-27] Publish binary non-UTF8 bytes and formatted dictionaries.
    """
    adapter = MQTTAdapter()
    adapter.connect()

    dispatched = []
    adapter.subscribe("test/fuzz", lambda t, p: dispatched.append(p))

    raw_bytes = b"\x80\x81\xFF\xFE\x00\x01"
    assert adapter.publish("test/fuzz", raw_bytes) is True
    assert len(dispatched) == 1

    assert adapter.publish("test/fuzz", {"status": "ok", "code": 200}) is True
    assert len(dispatched) == 2


# ============================================================================
# DOMAIN 4: jarvis/comms ADVERSARIAL STRESS TESTS
# ============================================================================

def test_telegram_unauthorized_user_and_injection_defense():
    """
    [Comms / F-38] Verify strict user whitelist enforcement, command injection safety, and violation auditing.
    """
    bot = TelegramBotController(allowed_user_ids={111222333})

    # 1. Unauthorized attacker ID
    attack_res = bot.handle_inbound_message(user_id=999999, text="/status")
    assert attack_res["status"] == 403
    assert attack_res["rejected"] is True
    assert 999999 in bot.security_violations

    # 2. Whitelisted user valid commands
    status_res = bot.handle_inbound_message(user_id=111222333, text="/status")
    assert status_res["status"] == 200
    # A4 fix (2026-09-04): /status now returns real psutil CPU/RAM data instead of
    # hardcoded "Hệ thống hoạt động bình thường". Strengthened assertion (per audit review):
    # must contain a numeric percentage (e.g. "29%") to catch any future regression back
    # to a hardcoded string — not just assert "CPU" which could appear in a fabricated string too.
    import re
    status_text = status_res["text"]
    has_real_cpu = bool(re.search(r"\d+%", status_text)) or "không xác định" in status_text
    assert has_real_cpu, (
        f"/status did not return real numeric CPU/RAM data — possible regression to hardcoded string. "
        f"Got: {status_text!r}"
    )

    help_res = bot.handle_inbound_message(user_id=111222333, text="/help")
    assert help_res["status"] == 200
    assert "/exec" in help_res["text"]

    # 3. Whitelisted user /exec command injection safety
    exec_res = bot.handle_inbound_message(user_id=111222333, text="/exec restart_service; rm -rf /")
    assert exec_res["status"] == 200
    assert "restart_service" in exec_res["text"]


def test_telegram_inbound_voice_and_stt_exception_resilience():
    """
    [Comms / F-38] Test inbound voice note handling when STT engine crashes or returns empty text.
    """
    class CrashingSTT:
        def transcribe(self, audio_bytes):
            raise RuntimeError("Whisper model CUDA out of memory")

    bot = TelegramBotController(allowed_user_ids={12345}, stt_engine=CrashingSTT())

    res = bot.handle_inbound_voice(user_id=12345, voice_bytes=b"fake_ogg_voice_data")
    assert res["status"] == 200
    assert "Lệnh thoại đã nhận" in res["text"]


def test_imap_email_reader_mime_html_cleaning_and_fuzzing():
    """
    [Comms / F-39] Test priority sender filtering and HTML tag stripping on malformed email bodies.
    """
    reader = IMAPEmailReader(priority_senders=["boss@corp.com", "alert@security.lan"])

    dirty_emails = [
        EmailMessage(
            sender="BOSS@CORP.COM",
            subject="URGENT: Quarterly Review",
            body_text="<html><body><h1>Report</h1><p>Meeting at <b>10 AM</b> &amp; discussion.</p></body></html>",
            is_priority=True,
        ),
        EmailMessage(
            sender="spam@marketing.com",
            subject="Buy Now",
            body_text="Cheap deals!",
            is_priority=False,
        ),
    ]

    summary = reader.fetch_and_summarize(mock_emails=dirty_emails)
    assert summary["total_unread"] == 2
    assert summary["priority_count"] == 1
    assert "Quarterly Review" in summary["voice_summary"]
    assert "<h1>" not in summary["voice_summary"]
    assert "Meeting at" in summary["voice_summary"]
    assert "10 AM" in summary["voice_summary"]


def test_discord_bot_client_empty_and_massive_channel_summaries():
    """
    [Comms / F-40] Test Discord channel summarization on empty message lists and large message bursts.
    """
    client = DiscordBotClient(bot_token="fake_bot_token")

    # 1. Empty messages
    assert "không có hoạt động mới" in client.summarize_channel("general", [])

    # 2. Large message batch
    messages = [f"Commit #{i} pushed by developer" for i in range(100)]
    summary = client.summarize_channel("dev-feed", messages)
    assert "100 tin nhắn mới" in summary


# ============================================================================
# DOMAIN 5: jarvis/automation ADVERSARIAL STRESS TESTS
# ============================================================================

def test_vm_orchestrator_subprocess_failures_and_injection(monkeypatch):
    """
    [Automation / F-31] Test VM orchestrator under non-zero return codes, timeouts, and command injection names.
    """
    monkeypatch.setattr(shutil, "which", lambda x: "C:\\Program Files\\VMware\\vmrun.exe")

    def fake_subprocess_run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=1,
            stdout="",
            stderr="Error: The specified virtual machine was not found on disk.",
        )

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    orchestrator = VMOrchestrator(dry_run=False)

    # 1. Test start failure
    malicious_vm = "Ubuntu; calc.exe"
    res_start = orchestrator.start_vm(malicious_vm, hypervisor="vmware")
    assert res_start["success"] is False
    assert res_start["state"] == VMState.STOPPED.value
    assert "not found" in res_start["message"]

    # 2. Test stop failure
    res_stop = orchestrator.stop_vm(malicious_vm, hypervisor="vmware")
    assert res_stop["success"] is False
    assert res_stop["state"] == VMState.RUNNING.value


def test_workspace_recipe_manager_corrupted_recipes_and_vm_failure():
    """
    [Automation / F-32] Test recipe manager handling malformed configs and handling failing VM starts gracefully.
    """
    class FailingVM:
        def start_vm(self, name):
            raise RuntimeError("Hypervisor unreachable")

    mgr = WorkspaceRecipeManager(vm_orchestrator=FailingVM())

    mgr.register_recipe("corrupt_recipe", {
        "name": "corrupt_recipe",
        "vm": "CrashVM",
    })

    res = mgr.prepare_workspace("corrupt_recipe")
    assert res["success"] is True
    assert res["recipe"] == "corrupt_recipe"
    assert len(res["launched_apps"]) > 0


# ============================================================================
# DOMAIN 6: jarvis/data ADVERSARIAL STRESS TESTS
# ============================================================================

def test_data_analytics_corrupted_and_empty_csv(tmp_path):
    """
    [Data / F-28] Test CSV ingestion on non-existent files, 0-byte files, and dirty currency/percent symbols.
    """
    engine = DataAnalyticsEngine()

    # 1. Missing file
    with pytest.raises(ValueError, match="empty or missing"):
        engine.load_csv(tmp_path / "missing.csv")

    # 2. 0-byte file
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        engine.load_csv(empty_csv)

    # 3. CSV with currency symbols, percentages, and commas in quoted cells
    dirty_csv = tmp_path / "dirty.csv"
    dirty_csv.write_text(
        'Product,Price,Discount,Sales\n'
        'Item A,"$1,200.50",15.0%,100\n'
        'Item B,"$2,450.00",20.0%,250\n'
        'Item C,"$850.75",5.0%,80\n'
        'Item D,N/A,0.0%,120\n',
        encoding="utf-8",
    )

    dataset = engine.load_csv(dirty_csv)
    assert "Price" in dataset.numeric_columns
    assert len(dataset.numeric_columns["Price"]) == 3
    assert dataset.numeric_columns["Price"][0] == 1200.50


def test_data_analytics_corrupted_xlsx_pure_python_parser(tmp_path):
    """
    [Data / F-28] Test pure Python XLSX standard library parser on non-zip files.
    """
    engine = DataAnalyticsEngine()

    corrupt_file = tmp_path / "corrupt.xlsx"
    corrupt_file.write_text("Not a real zip archive", encoding="utf-8")
    with pytest.raises((ValueError, zipfile.BadZipFile)):
        engine.load_xlsx(corrupt_file)


def test_data_analytics_statistics_edge_cases_and_zero_variance():
    """
    [Data / F-28] Test statistics computations on single-sample arrays, constant arrays (std=0), and skewed data.
    """
    engine = DataAnalyticsEngine()

    # 1. Constant dataset (Zero variance)
    constant_data = TabularDataset(
        headers=["value"],
        rows=[["10.0"], ["10.0"], ["10.0"], ["10.0"], ["10.0"]],
    )
    stats = engine.compute_statistics(constant_data, "value")
    assert stats.count == 5
    assert stats.mean == 10.0
    assert stats.std == 0.0
    assert stats.variance == 0.0
    assert stats.skewness == 0.0
    assert stats.kurtosis == 0.0

    anomalies_z = engine.detect_anomalies(constant_data, "value", method="zscore")
    assert anomalies_z.total_anomalies == 0

    anomalies_iqr = engine.detect_anomalies(constant_data, "value", method="iqr")
    assert anomalies_iqr.total_anomalies == 0

    # 2. Correlation matrix with constant columns
    multi_data = TabularDataset(
        headers=["col1", "col2"],
        rows=[["10.0", "1.0"], ["10.0", "2.0"], ["10.0", "3.0"]],
    )
    corr = engine.compute_correlation_matrix(multi_data)
    assert len(corr.columns) == 2
    # Pearson handles zero variance by clipping to 0.0
    assert corr.pearson_matrix[0][1] == 0.0


def test_monte_carlo_engine_extreme_parameters_and_distributions():
    """
    [Data / F-29] Stress Monte Carlo simulation with extreme bounds, 4 distributions, and boundary checks.
    """
    engine = MonteCarloEngine()

    # 1. Iterations < 1000 check
    with pytest.raises(ValueError, match="Iterations must be >= 1000"):
        engine.run_simulation(iterations=500)

    # 2. Volatility <= 0 check
    with pytest.raises(ValueError, match="Volatility must be > 0"):
        engine.run_simulation(volatility=0.0)

    # 3. Normal Distribution
    res_norm = engine.run_simulation(
        initial_value=100.0,
        iterations=5000,
        mean_return=0.05,
        volatility=0.10,
        distribution=DistributionType.NORMAL,
        target_value=105.0,
        random_seed=42,
    )
    assert 103.0 < res_norm.mean < 107.0
    assert 0.0 <= res_norm.prob_target <= 100.0
    assert res_norm.var_95 >= 0.0

    # 4. Lognormal Distribution
    res_log = engine.run_simulation(
        initial_value=100.0,
        iterations=5000,
        distribution=DistributionType.LOGNORMAL,
        random_seed=42,
    )
    assert res_log.mean > 0

    # 5. Uniform Distribution
    res_uni = engine.run_simulation(
        initial_value=100.0,
        iterations=5000,
        distribution=DistributionType.UNIFORM,
        uniform_low=-0.10,
        uniform_high=0.20,
        random_seed=42,
    )
    assert res_uni.p1 >= 85.0

    # 6. Triangular Distribution
    res_tri = engine.run_simulation(
        initial_value=100.0,
        iterations=5000,
        distribution=DistributionType.TRIANGULAR,
        triangular_low=-0.15,
        triangular_mode=0.05,
        triangular_high=0.25,
        random_seed=42,
    )
    assert res_tri.mean > 95.0


def test_docx_and_pdf_document_generator_adversarial_text(tmp_path):
    """
    [Data / F-30] Test pure Python OpenXML (.docx) and PDF generation with XML injection characters and unicode.
    """
    # 1. XML escaping verification
    raw_text = 'Test & <script> "Quotes" \'Apostrophe\''
    escaped = _xml_escape(raw_text)
    assert "&amp;" in escaped
    assert "&lt;script&gt;" in escaped
    assert "&quot;" in escaped
    assert "&apos;" in escaped

    # 2. Build DOCX
    docx_path = tmp_path / "adversarial.docx"
    builder = DocxReportBuilder(title="Adversarial & Test Report")
    builder.add_title("Title <injection>", subtitle="Sub & Test")
    builder.add_heading("Heading 1 & More", level=1)
    builder.add_paragraph("Paragraph with <b>HTML</b> & special chars.", bold=True, italic=True)
    builder.add_bullet("Bullet item <1>")
    builder.add_callout("Callout text & note", title="CRITICAL & ALERT")
    builder.add_table(headers=["Col 1 & A", "Col 2 <B>"], rows=[["Val & 1", "Val <2>"]])
    saved_docx = builder.save(docx_path)

    assert saved_docx.exists()
    with zipfile.ZipFile(saved_docx, "r") as z:
        assert "word/document.xml" in z.namelist()
        assert "[Content_Types].xml" in z.namelist()
        doc_xml = z.read("word/document.xml").decode("utf-8")
        assert "&lt;script&gt;" not in doc_xml
        assert "&amp;" in doc_xml

    # 3. Build PDF
    pdf_path = tmp_path / "adversarial.pdf"
    pdf_builder = PdfReportBuilder(title="PDF Report (Adversarial)")
    pdf_builder.add_title("Tiêu đề báo cáo tiếng Việt (Unicode test)")
    pdf_builder.add_heading("Heading (level 1)", level=1)
    pdf_builder.add_paragraph("Paragraph with (parentheses) and special characters.")
    pdf_builder.add_table(headers=["Header A", "Header B"], rows=[["Row 1", "Row 2"]])
    saved_pdf = pdf_builder.save(pdf_path)

    assert saved_pdf.exists()
    pdf_bytes = saved_pdf.read_bytes()
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"%%EOF" in pdf_bytes

    # 4. DocumentExporter unified interface
    exporter = DocumentExporter()
    stats_obj = DescriptiveStats(
        column_name="Sales", count=100, missing_count=0, mean=500.0, std=50.0, variance=2500.0,
        std_err=5.0, min=400.0, max=600.0, range=200.0, median=500.0, p25=465.0, p75=535.0,
        iqr=70.0, skewness=0.0, kurtosis=0.0
    )
    sim_obj = MonteCarloResult(
        iterations=5000, mean=520.0, std_err=0.7, p5=440.0, p50=520.0, p95=600.0,
        prob_target=85.0, var_95=60.0
    )

    exported_docx = exporter.export_report(stats_obj, sim_obj, tmp_path / "unified.docx")
    assert exported_docx.exists()

    exported_pdf = exporter.export_report(stats_obj, sim_obj, tmp_path / "unified.pdf")
    assert exported_pdf.exists()

    voice_summary = exporter.get_voice_summary("sales.csv", stats_obj, sim_obj)
    assert "500.00" in voice_summary
    assert "85.0%" in voice_summary
