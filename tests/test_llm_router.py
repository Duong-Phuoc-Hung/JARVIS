import os
"""
tests/test_llm_router.py
========================
Test Suite for Speech-to-Text, Multi-Provider LLM Intent Routing, System Tray, and Dashboard.
Covering:
  - F-14: Speech-to-Text (STT) Engine (Local/Cloud speech transcription)
  - F-15: LLM Semantic Intent Engine (Multi-provider routing, tool extraction, rule fallback)
  - F-16: System Tray Controller (Tray lifecycle and menu structure)
  - F-17: Real-Time Dashboard (Web/WS telemetry metrics server)
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import numpy as np
import pytest

from jarvis.core.models import ActionResult
from jarvis.llm.client import (
    ChatMessage,
    LLMAuthenticationError,
    LLMClient,
    LLMProvider,
    LLMResponse,
    TokenUsage,
    ToolCall,
)
from jarvis.llm.router import (
    IntentResult,
    LLMIntentRouter,
    build_jarvis_system_prompt,
    generate_tool_schema_from_dispatcher,
)
from jarvis.stt.engine import (
    BaseSTTEngine,
    FasterWhisperSTT,
    MockSTTEngine,
    OpenAIWhisperSTT,
    STTEngine,
    WindowsSpeechSTT,
    audio_to_float32,
    float32_to_pcm16_wav_bytes,
)
from jarvis.ui.dashboard import DashboardMetricsServer, DashboardServer
from jarvis.ui.tray import SystemTrayController, TrayStatus

# ============================================================================
# TIER 1: FEATURE COVERAGE HAPPY PATHS
# ============================================================================

_SKIP_ENV = pytest.mark.skipif(
    not os.environ.get("JARVIS_INTEGRATION_TESTS"),
    reason="Full-pipeline integration test: set JARVIS_INTEGRATION_TESTS=1 to run"
)

def test_stt_transcribe_audio_buffer_tier1(audio_synthesizer):
    """
    [F-14] Validate Speech-to-Text transcriber converts voice audio buffer into transcribed text.
    """
    stt = STTEngine()
    voice_buffer = audio_synthesizer.generate_noise(0.5, rms=0.05)
    text = stt.transcribe(voice_buffer)

    assert "bật đèn phòng khách" in text


def test_llm_multi_provider_client_tier1(monkeypatch):
    """
    [F-15] Validate unified LLMClient connects to Gemini and Ollama through
    real provider dispatch and real response parsing, with only the HTTP
    transport layer mocked -- no live Internet request occurs and no local
    Ollama daemon is required. Also proves `_execute_mock()` is never
    reached for a real provider's successful call, per the v4.5.2 LLM
    provider-truthfulness hotfix: a dummy-looking API key or an
    unreachable-Ollama-daemon condition must never silently substitute a
    synthetic mock response for a real one.
    """
    def _fail_execute_mock(*args, **kwargs):
        raise AssertionError("_execute_mock() must not be called for a real provider's successful response")

    # -- Gemini: real provider dispatch, real response parsing, mocked transport --
    gemini_client = LLMClient(provider="gemini", api_key="test-key", max_retries=0)
    monkeypatch.setattr(gemini_client, "_execute_mock", _fail_execute_mock)

    gemini_payload = {
        "candidates": [
            {"content": {"parts": [{"text": "Hello from Gemini"}]}},
        ],
        "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 6, "totalTokenCount": 11},
    }

    def _fake_gemini_post(url, headers=None, json=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = gemini_payload
        return resp

    monkeypatch.setattr(gemini_client.session, "post", _fake_gemini_post)

    res_gemini = gemini_client.generate("Hi Jarvis")
    assert res_gemini.provider == "gemini"
    assert res_gemini.content == "Hello from Gemini"
    assert res_gemini.usage.total_tokens == 11

    # -- Ollama: real provider dispatch, real response parsing, mocked transport --
    ollama_client = LLMClient(provider="ollama", max_retries=0)
    monkeypatch.setattr(ollama_client, "_execute_mock", _fail_execute_mock)

    ollama_payload = {
        "message": {"role": "assistant", "content": "Hello from local Ollama"},
        "prompt_eval_count": 4,
        "eval_count": 5,
    }

    def _fake_ollama_post(url, headers=None, json=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = ollama_payload
        return resp

    monkeypatch.setattr(ollama_client.session, "post", _fake_ollama_post)

    res_ollama = ollama_client.generate("Local prompt")
    assert res_ollama.provider == "ollama"
    assert res_ollama.content == "Hello from local Ollama"
    assert res_ollama.usage.total_tokens == 9


def test_llm_router_tool_call_intent_extraction_tier1():
    """
    [F-15] Validate intent parser maps natural language request to structured tool call action.
    """
    client = LLMClient(provider="gemini", api_key="key")
    router = LLMIntentRouter(client)

    intent_cpu = router.parse_intent("Jarvis, kiểm tra nhiệt độ cpu ngay")
    assert intent_cpu.action_name == "hardware_telemetry_check"
    assert intent_cpu.parameters["component"] == "cpu"

    intent_light = router.parse_intent("Jarvis, hãy bật đèn phòng khách lên")
    assert intent_light.action_name == "home_assistant_call"
    assert intent_light.parameters["entity_id"] == "light.living_room"


def test_ui_system_tray_lifecycle_tier1():
    """
    [F-16] Validate system tray controller initializes with standard menu items.
    """
    tray = SystemTrayController()
    tray.start()
    assert tray.is_running is True
    assert "Open Dashboard" in tray.menu_items
    assert "Exit" in tray.menu_items
    tray.stop()
    assert tray.is_running is False


def test_ui_dashboard_metrics_broadcast_tier1():
    """
    [F-17] Validate real-time dashboard broadcasts metrics and returns system status.
    """
    dashboard = DashboardMetricsServer()
    metrics = {"cpu_percent": 18.5, "ram_percent": 42.0, "smart_status": "PASSED"}
    dashboard.broadcast_telemetry(metrics)

    summary = dashboard.get_status_summary()
    assert summary["status"] == "healthy"
    assert summary["telemetry"]["cpu_percent"] == 18.5


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ============================================================================

def test_stt_silence_returns_empty_tier2(audio_synthesizer):
    """
    [F-14] Validate that silent audio buffer returns empty string without hanging.
    """
    stt = STTEngine()
    silence = audio_synthesizer.generate_silence(0.5)
    assert stt.transcribe(silence) == ""
    assert stt.transcribe(np.array([])) == ""


def test_llm_api_missing_key_fallback_to_rules_tier2():
    """
    [F-15] Validate that missing LLM API key safely falls back to local deterministic rule engine.
    """
    unauthenticated_client = LLMClient(provider="openai", api_key="")
    router = LLMIntentRouter(unauthenticated_client)

    # Known rule phrase still succeeds via local rule engine
    intent = router.parse_intent("kiểm tra nhiệt độ cpu")
    assert intent.action_name == "hardware_telemetry_check"
    assert intent.source == "rule_fallback"


# ============================================================================
# TIER 3: MILESTONE M2 VIETNAMESE KEYWORD ROUTER & NATURAL RESPONSES
# ============================================================================

def test_m2_vietnamese_category1_smart_home():
    """
    [M2] Validate Category 1: Smart Home Vietnamese keywords, entity extraction, and natural responses.
    """
    router = LLMIntentRouter(LLMClient(provider="mock"))

    # 1. Lights On / Off Living Room
    r_on = router.parse_intent("bật đèn phòng khách")
    assert r_on.action_name == "home_assistant_call"
    assert r_on.parameters["domain"] == "light"
    assert r_on.parameters["service"] == "turn_on"
    assert r_on.parameters["entity_id"] == "light.living_room"
    assert "Đang bật đèn phòng khách cho Ngài." in r_on.response_text

    r_off = router.parse_intent("tắt đèn phòng khách")
    assert r_off.action_name == "home_assistant_call"
    assert r_off.parameters["service"] == "turn_off"
    assert "Đang tắt đèn phòng khách cho Ngài." in r_off.response_text

    # 2. Desk Lamp
    r_desk = router.parse_intent("bật đèn bàn")
    assert r_desk.action_name == "home_assistant_call"
    assert r_desk.parameters["entity_id"] == "light.desk_lamp"
    assert "Đang bật đèn bàn làm việc cho Ngài." in r_desk.response_text

    # 3. Generic Light Commands
    r_gen = router.parse_intent("bật đèn")
    assert r_gen.action_name == "home_assistant_call"
    assert "Đang bật đèn cho Ngài." in r_gen.response_text

    r_gen_off = router.parse_intent("tắt đèn")
    assert r_gen_off.action_name == "home_assistant_call"
    assert "Đang tắt đèn cho Ngài." in r_gen_off.response_text

    # 4. Fan Commands
    r_fan_on = router.parse_intent("bật quạt")
    assert r_fan_on.action_name == "home_assistant_call"
    assert r_fan_on.parameters["domain"] == "fan"
    assert r_fan_on.parameters["service"] == "turn_on"
    assert "Đang bật quạt cho Ngài." in r_fan_on.response_text

    r_fan_off = router.parse_intent("tắt quạt")
    assert r_fan_off.action_name == "home_assistant_call"
    assert r_fan_off.parameters["domain"] == "fan"
    assert r_fan_off.parameters["service"] == "turn_off"
    assert "Đang tắt quạt cho Ngài." in r_fan_off.response_text

    # 5. Climate / AC Commands
    r_ac_on = router.parse_intent("bật điều hòa")
    assert r_ac_on.action_name == "home_assistant_call"
    assert r_ac_on.parameters["domain"] == "climate"
    assert r_ac_on.parameters["service"] == "turn_on"
    assert "Đang bật điều hòa cho Ngài." in r_ac_on.response_text

    r_ac_off = router.parse_intent("tắt điều hòa")
    assert r_ac_off.action_name == "home_assistant_call"
    assert r_ac_off.parameters["domain"] == "climate"
    assert r_ac_off.parameters["service"] == "turn_off"
    assert "Đang tắt điều hòa cho Ngài." in r_ac_off.response_text

    # 6. Temperature Adjustment Regex
    r_temp = router.parse_intent("đặt điều hòa 24 độ")
    assert r_temp.action_name == "home_assistant_call"
    assert r_temp.parameters["service"] == "set_temperature"
    assert r_temp.parameters["temperature"] == 24.0
    assert "Đã đặt nhiệt độ điều hòa thành 24 độ cho Ngài." in r_temp.response_text


def test_m2_vietnamese_category2_hardware_telemetry():
    """
    [M2] Validate Category 2: Hardware/System Status Vietnamese keywords and telemetry queries.
    """
    router = LLMIntentRouter(LLMClient(provider="mock"))

    # Direct short keywords
    r_cpu = router.parse_intent("CPU")
    assert r_cpu.action_name == "hardware_telemetry_check"
    assert r_cpu.parameters["component"] == "cpu"
    assert "Nhiệt độ CPU hiện tại là 45 độ C" in r_cpu.response_text

    r_temp = router.parse_intent("nhiệt độ")
    assert r_temp.action_name == "hardware_telemetry_check"
    assert r_temp.parameters["component"] == "cpu"

    r_ram = router.parse_intent("RAM")
    assert r_ram.action_name == "hardware_telemetry_check"
    assert r_ram.parameters["component"] == "ram"
    assert "Bộ nhớ RAM đang sử dụng ở mức bình thường" in r_ram.response_text

    r_gpu = router.parse_intent("card đồ họa")
    assert r_gpu.action_name == "hardware_telemetry_check"
    assert r_gpu.parameters["component"] == "gpu"
    assert "Card đồ họa hoạt động bình thường" in r_gpu.response_text

    r_disk = router.parse_intent("ổ cứng")
    assert r_disk.action_name == "hardware_telemetry_check"
    assert r_disk.parameters["component"] == "disk"

    # Overall system health
    r_sys = router.parse_intent("hệ thống")
    assert r_sys.action_name == "hardware_status_query"
    assert "Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu" in r_sys.response_text

    r_sys2 = router.parse_intent("tình trạng máy")
    assert r_sys2.action_name == "hardware_status_query"

    r_sys3 = router.parse_intent("kiểm tra hệ thống")
    assert r_sys3.action_name == "hardware_status_query"


def test_m2_vietnamese_category3_spotify_music():
    """
    [M2] Validate Category 3: Spotify / Music Vietnamese keywords, playback controls, and song searches.
    """
    router = LLMIntentRouter(LLMClient(provider="mock"))

    # Launch & Play
    r_play = router.parse_intent("mở spotify")
    assert r_play.action_name == "spotify"
    assert "Đang mở Spotify và phát nhạc cho Ngài." in r_play.response_text

    r_nhac = router.parse_intent("bật nhạc")
    assert r_nhac.action_name == "spotify"

    r_phat = router.parse_intent("phát nhạc")
    assert r_phat.action_name == "spotify"

    # Specific song query regex
    r_song = router.parse_intent("mở spotify bài Em của ngày hôm qua")
    assert r_song.action_name == "spotify"
    assert r_song.parameters.get("query") == "Em của ngày hôm qua"
    assert "Đang mở Spotify và phát Em của ngày hôm qua cho Ngài." in r_song.response_text

    # Pause / Next
    r_pause = router.parse_intent("dừng nhạc")
    assert r_pause.action_name == "spotify"
    assert r_pause.parameters.get("command") == "pause"
    assert "Đã tạm dừng phát nhạc, thưa Ngài." in r_pause.response_text

    r_next = router.parse_intent("chuyển bài")
    assert r_next.action_name == "spotify"
    assert r_next.parameters.get("command") == "next"
    assert "Đang chuyển bài tiếp theo, thưa Ngài." in r_next.response_text


def test_m2_vietnamese_category4_weather():
    """
    [M2] Validate Category 4: Weather Vietnamese queries and location extraction.
    """
    router = LLMIntentRouter(LLMClient(provider="mock"))

    # General weather
    r_w = router.parse_intent("thời tiết")
    assert r_w.action_name == "shell_exec"
    assert r_w.parameters.get("topic") == "weather"
    assert "Đang kiểm tra thông tin thời tiết" in r_w.response_text

    r_w_today = router.parse_intent("thời tiết hôm nay")
    assert r_w_today.action_name == "shell_exec"
    assert "wttr.in?format=3" in r_w_today.parameters.get("command", "")

    # City-specific weather
    r_hanoi = router.parse_intent("thời tiết hà nội")
    assert r_hanoi.action_name == "shell_exec"
    assert r_hanoi.parameters.get("location") == "Hà Nội"
    assert "Hanoi" in r_hanoi.parameters.get("command", "")
    assert "Đang kiểm tra thông tin thời tiết tại Hà Nội cho Ngài." in r_hanoi.response_text

    r_saigon = router.parse_intent("thời tiết sài gòn")
    assert r_saigon.action_name == "shell_exec"
    assert r_saigon.parameters.get("location") == "Sài Gòn"
    assert "Saigon" in r_saigon.parameters.get("command", "")


def test_m2_vietnamese_category5_reminder():
    """
    [M2] Validate Category 5: Reminder & Alarm Vietnamese keywords, relative durations, and timestamps.
    """
    router = LLMIntentRouter(LLMClient(provider="mock"))

    # General reminder
    r_rem = router.parse_intent("nhắc nhở")
    assert r_rem.action_name == "reminder"
    assert "Đã ghi nhận lời nhắc của Ngài." in r_rem.response_text

    r_rem2 = router.parse_intent("reminder")
    assert r_rem2.action_name == "reminder"

    r_rem3 = router.parse_intent("nhắc tôi")
    assert r_rem3.action_name == "reminder"

    # Duration parsing
    r_dur = router.parse_intent("nhắc nhở uống nước sau 30 phút")
    assert r_dur.action_name == "reminder"
    assert r_dur.parameters.get("delay_s") == 1800
    assert r_dur.parameters.get("delay_minutes") == 30
    assert "uống nước" in r_dur.parameters.get("message", "")

    # Clock time parsing
    r_time = router.parse_intent("nhắc tôi họp lúc 3 giờ chiều")
    assert r_time.action_name == "reminder"
    assert "họp" in r_time.parameters.get("message", "")
    assert "3 giờ chiều" in r_time.parameters.get("time_str", "")


def test_m2_vietnamese_category6_system_power_safety():
    """
    [M2] Validate Category 6: System Power actions enforce safety confirmation flag, prompt, and danger level.
    """
    router = LLMIntentRouter(LLMClient(provider="mock"))

    # Shutdown
    r_shut = router.parse_intent("tắt máy")
    assert r_shut.action_name == "system_power"
    assert r_shut.parameters.get("action") == "shutdown"
    assert r_shut.requires_confirmation is True
    assert r_shut.danger_level == "CRITICAL"
    assert r_shut.confirmation_prompt is not None
    assert "Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận" in r_shut.response_text

    # Restart
    r_rst = router.parse_intent("restart")
    assert r_rst.action_name == "system_power"
    assert r_rst.parameters.get("action") == "restart"
    assert r_rst.requires_confirmation is True
    assert r_rst.danger_level == "CRITICAL"
    assert "Lệnh khởi động lại hệ thống đã được ghi nhận. Vui lòng xác nhận" in r_rst.response_text

    r_khoidong = router.parse_intent("khởi động lại")
    assert r_khoidong.action_name == "system_power"
    assert r_khoidong.requires_confirmation is True

    # Sleep
    r_sleep = router.parse_intent("chế độ ngủ")
    assert r_sleep.action_name == "system_power"
    assert r_sleep.parameters.get("action") == "sleep"
    assert r_sleep.requires_confirmation is True
    assert r_sleep.danger_level == "MEDIUM"

    # Lock Screen (Safe, immediate)
    r_lock = router.parse_intent("khóa máy")
    assert r_lock.action_name == "system_power"
    assert r_lock.parameters.get("action") == "lock"
    assert r_lock.requires_confirmation is False
    assert r_lock.danger_level == "LOW"


def test_m2_vietnamese_category7_default_fallback():
    """
    [M2] Validate Category 7: Default fallback strictly produces 'Tôi chưa hiểu lệnh này, vui lòng thử cách khác'.
    """
    client = LLMClient(provider="mock")
    client.set_mock_behavior(mock_error="auth_error")
    router = LLMIntentRouter(client)

    r_unknown = router.parse_intent("câu lệnh hoàn toàn ngẫu nhiên không có trong từ điển 98765", force_llm=True)
    assert r_unknown.action_name == "unknown_intent"
    assert r_unknown.confidence == 0.0
    assert r_unknown.response_text == "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"


def test_m2_intent_result_extended_dataclass_and_serialization():
    """
    [M2] Validate IntentResult extended fields and to_dict serialization.
    """
    res = IntentResult(
        action_name="system_power",
        parameters={"action": "shutdown"},
        confidence=1.0,
        source="rule_fallback",
        reasoning="User commanded shutdown",
        raw_text="tắt máy",
        response_text="Lệnh tắt máy đã được ghi nhận.",
        requires_confirmation=True,
        confirmation_prompt="Ngài có chắc chắn muốn tắt máy không?",
        danger_level="CRITICAL",
    )

    d = res.to_dict()
    assert d["action_name"] == "system_power"
    assert d["parameters"] == {"action": "shutdown"}
    assert d["confidence"] == 1.0
    assert d["source"] == "rule_fallback"
    assert d["reasoning"] == "User commanded shutdown"
    assert d["raw_text"] == "tắt máy"
    assert d["response_text"] == "Lệnh tắt máy đã được ghi nhận."
    assert d["requires_confirmation"] is True
    assert d["confirmation_prompt"] == "Ngài có chắc chắn muốn tắt máy không?"
    assert d["danger_level"] == "CRITICAL"


def test_m2_get_natural_response_direct_helper():
    """
    [M2] Test get_natural_response helper across all action names and ActionResult pre-formatted payloads.
    """
    router = LLMIntentRouter(LLMClient(provider="mock"))

    # Generic LLM
    assert router.get_natural_response("generic_llm_response", {"reply": "Xin chào Ngài"}) == "Xin chào Ngài"

    # ActionResult with pre-formatted message
    mock_ar = ActionResult(
        action_name="system_status",
        success=True,
        data={"message": "CPU đang sử dụng 20 phần trăm. Nhiệt độ CPU là 45 độ C."},
    )
    assert router.get_natural_response("system_status", action_result=mock_ar) == "CPU đang sử dụng 20 phần trăm. Nhiệt độ CPU là 45 độ C."

    # Workflows
    assert "chuẩn bị môi trường" in router.get_natural_response("workspace_prepare")
    assert "tối ưu hóa bộ nhớ" in router.get_natural_response("healing_watchdog_heal")
    assert "quét an ninh mạng" in router.get_natural_response("security_nmap_scan")


@_SKIP_ENV
def test_m2_app_process_text_command_integration():
    """
    [M2] Test JarvisApp.process_text_command end-to-end integration with natural responses and fallback.
    """
    from jarvis.core.app import JarvisApp

    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # Track vocalized TTS
    spoken = []
    if app.tts_manager:
        app.tts_manager.speak = lambda txt, **kw: spoken.append(txt) or True

    # 1. Recognized Smart Home command
    res1 = app.process_text_command("bật đèn phòng khách")
    assert res1["success"] is True
    assert "Đang bật đèn phòng khách cho Ngài." in res1["response_text"]
    assert res1["response_text"] in spoken

    # 2. Recognized Hardware command
    res2 = app.process_text_command("CPU")
    assert res2["success"] is True
    assert "Nhiệt độ CPU hiện tại là 45 độ C" in res2["response_text"]

    # 3. Unrecognized command -> standard Vietnamese fallback
    res_unknown = app.process_text_command("xyz gibberish random query 12345")
    assert res_unknown["success"] is True
    assert res_unknown["response_text"] == "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"
    assert "Tôi chưa hiểu lệnh này, vui lòng thử cách khác" in spoken

