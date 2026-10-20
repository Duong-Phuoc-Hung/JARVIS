"""
tests/unit/test_realtime_voice_bridge.py
========================================
Comprehensive unit test suite for Milestone 4:
  1. Voice Pipeline Full-Duplex Barge-In Bridge in `jarvis/core/app.py`:
     - Full-duplex microphone chunk forwarding during active TTS playback.
     - Acoustic barge-in interruption triggering `tts_manager.stop()` on 3 consecutive loud frames.
     - State transition to `LISTENING` and immediate buffer accumulation.
     - Edge case handling: silence/low RMS counter reset, non-speaking state isolation.
  2. Sub-2ms On-Device Hybrid Semantic Router in `jarvis/llm/semantic_router.py`:
     - Typed slot extraction and TF-IDF similarity across 7 high-frequency desktop domains:
       volume, brightness, media, app launch, timers, notes, weather.
     - Sub-2ms on-device latency SLA verification (< 2.0ms per query).
     - Fast-path execution in `app.process_text_command()` bypassing Cloud LLM roundtrip.
"""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.core.app import JarvisApp
from jarvis.core.config import ConfigManager
from jarvis.llm.models import IntentResult
from jarvis.llm.semantic_router import (
    HybridSemanticRouter,
    LocalSemanticRouter,
    normalize_vietnamese_text,
    parse_duration_seconds,
)
from jarvis.voice.realtime import (
    RealtimeSessionConfig,
    RealtimeVoiceSession,
    RealtimeVoiceState,
)


def _generate_speech_chunk(freq: float = 300.0, duration_s: float = 0.04, amplitude: float = 0.35, sample_rate: int = 16000) -> np.ndarray:
    """Generates synthetic speech-like tone chunk within passband (80-7500 Hz)."""
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    # Fundamental + harmonics to simulate vocal speech formant
    signal = amplitude * (
        0.6 * np.sin(2 * np.pi * freq * t)
        + 0.3 * np.sin(2 * np.pi * (2 * freq) * t)
        + 0.1 * np.sin(2 * np.pi * (3 * freq) * t)
    )
    return signal.astype(np.float32)


def _generate_silence_chunk(duration_s: float = 0.04, sample_rate: int = 16000) -> np.ndarray:
    """Generates silent audio chunk."""
    return np.zeros(int(sample_rate * duration_s), dtype=np.float32)


# ==============================================================================
# 1. Full-Duplex Real-Time Voice Bridge & Acoustic Barge-In Interruption Tests
# ==============================================================================

def test_full_duplex_audio_chunk_forwarding_during_tts():
    """Verify incoming audio chunks are forwarded to RealtimeVoiceSession during active TTS playback."""
    cfg = ConfigManager()
    app = JarvisApp(config=cfg, headless=True)

    mock_session = MagicMock()
    mock_tts = MagicMock()
    mock_tts.is_playing = True

    app.realtime_voice_session = mock_session
    app.tts_manager = mock_tts

    chunk = _generate_speech_chunk(amplitude=0.01)  # Low amplitude, no barge-in
    app.on_audio_chunk(chunk)

    # Audio chunk must be forwarded despite active TTS (full-duplex)
    mock_session.on_audio_chunk.assert_called_once_with(chunk)
    # Low amplitude must not trigger TTS stop
    mock_tts.stop.assert_not_called()


def test_barge_in_interruption_triggers_tts_stop_and_listening_state():
    """Verify 3 consecutive speech chunks with RMS > 0.025 trigger tts_manager.stop() and state transition."""
    cfg = ConfigManager()
    app = JarvisApp(config=cfg, headless=True)

    mock_tts = MagicMock()
    mock_tts.is_playing = True
    app.tts_manager = mock_tts

    # Real RealtimeVoiceSession with mock STT factory
    mock_stt_session = MagicMock()
    factory = MagicMock(return_value=mock_stt_session)
    session = RealtimeVoiceSession(
        stt_session_factory=factory,
        tts_manager=mock_tts,
        config=RealtimeSessionConfig(enable_barge_in=True),
    )
    session.start()
    session.set_speaking(True)
    assert session.state == RealtimeVoiceState.SPEAKING

    app.realtime_voice_session = session

    loud_chunk = _generate_speech_chunk(freq=300.0, amplitude=0.40)

    # Frame 1: consecutive = 1
    app.on_audio_chunk(loud_chunk)
    assert app._barge_in_consecutive == 1
    mock_tts.stop.assert_not_called()

    # Frame 2: consecutive = 2
    app.on_audio_chunk(loud_chunk)
    assert app._barge_in_consecutive == 2
    mock_tts.stop.assert_not_called()

    # Frame 3: consecutive = 3 -> triggers barge-in!
    app.on_audio_chunk(loud_chunk)
    assert app._barge_in_consecutive == 0
    mock_tts.stop.assert_called_once()
    assert session.state == RealtimeVoiceState.LISTENING


def test_barge_in_counter_resets_on_silence():
    """Verify silence / low RMS chunk breaks consecutive voiced sequence and resets counter."""
    cfg = ConfigManager()
    app = JarvisApp(config=cfg, headless=True)

    mock_tts = MagicMock()
    mock_tts.is_playing = True
    app.tts_manager = mock_tts
    app.realtime_voice_session = MagicMock()

    loud_chunk = _generate_speech_chunk(amplitude=0.40)
    silent_chunk = _generate_silence_chunk()

    # Two loud frames
    app.on_audio_chunk(loud_chunk)
    assert app._barge_in_consecutive == 1
    app.on_audio_chunk(loud_chunk)
    assert app._barge_in_consecutive == 2

    # Silent frame breaks consecutive streak
    app.on_audio_chunk(silent_chunk)
    assert app._barge_in_consecutive == 0
    mock_tts.stop.assert_not_called()

    # One loud frame after silence
    app.on_audio_chunk(loud_chunk)
    assert app._barge_in_consecutive == 1
    mock_tts.stop.assert_not_called()


def test_barge_in_ignored_when_tts_not_playing():
    """Verify loud audio chunks do not trigger tts_manager.stop() when TTS is inactive."""
    cfg = ConfigManager()
    app = JarvisApp(config=cfg, headless=True)

    mock_tts = MagicMock()
    mock_tts.is_playing = False
    app.tts_manager = mock_tts
    app.realtime_voice_session = MagicMock()

    loud_chunk = _generate_speech_chunk(amplitude=0.40)
    for _ in range(5):
        app.on_audio_chunk(loud_chunk)

    assert app._barge_in_consecutive == 0
    mock_tts.stop.assert_not_called()


# ==============================================================================
# 2. Fast On-Device Hybrid Semantic Router Intent Resolution & Slot Filling Tests
# ==============================================================================

@pytest.fixture(scope="module")
def hybrid_router() -> HybridSemanticRouter:
    """Fixture providing initialized HybridSemanticRouter."""
    return HybridSemanticRouter()


def test_hybrid_router_volume_resolution(hybrid_router: HybridSemanticRouter):
    """Test typed slot extraction for volume adjustments."""
    # Delta increase
    res_up = hybrid_router.route("tăng âm lượng lên 20%")
    assert res_up is not None
    assert res_up.action_name == "system_volume"
    assert res_up.parameters.get("delta") == 20
    assert res_up.source == "hybrid_fast_path"

    # Delta decrease
    res_down = hybrid_router.route("giảm âm lượng 15%")
    assert res_down is not None
    assert res_down.action_name == "system_volume"
    assert res_down.parameters.get("delta") == -15

    # Specific level
    res_lvl = hybrid_router.route("đặt âm lượng 60%")
    assert res_lvl is not None
    assert res_lvl.action_name == "system_volume"
    assert res_lvl.parameters.get("level") == 60

    # Mute / unmute
    res_mute = hybrid_router.route("tắt tiếng loa")
    assert res_mute is not None
    assert res_mute.action_name == "system_volume"
    assert res_mute.parameters.get("mute") is True

    res_unmute = hybrid_router.route("bật tiếng")
    assert res_unmute is not None
    assert res_unmute.action_name == "system_volume"
    assert res_unmute.parameters.get("mute") is False


def test_hybrid_router_brightness_resolution(hybrid_router: HybridSemanticRouter):
    """Test typed slot extraction for screen brightness."""
    res_up = hybrid_router.route("tăng độ sáng màn hình")
    assert res_up is not None
    assert res_up.action_name == "system_brightness"
    assert res_up.parameters.get("delta") == 10

    res_lvl = hybrid_router.route("đặt độ sáng 75%")
    assert res_lvl is not None
    assert res_lvl.action_name == "system_brightness"
    assert res_lvl.parameters.get("level") == 75


def test_hybrid_router_media_resolution(hybrid_router: HybridSemanticRouter):
    """Test typed slot extraction for media and music playback."""
    res_music = hybrid_router.route("mở nhạc spotify")
    assert res_music is not None
    assert res_music.action_name == "spotify"

    res_pause = hybrid_router.route("tạm dừng nhạc")
    assert res_pause is not None
    assert res_pause.action_name == "spotify"
    assert res_pause.parameters.get("command") == "pause"

    res_resume = hybrid_router.route("tiếp tục phát nhạc")
    assert res_resume is not None
    assert res_resume.action_name == "spotify"
    assert res_resume.parameters.get("command") == "play"


def test_hybrid_router_app_launch_resolution(hybrid_router: HybridSemanticRouter):
    """Test typed slot extraction for desktop application launching."""
    res_notepad = hybrid_router.route("mở notepad")
    assert res_notepad is not None
    assert res_notepad.action_name == "app_open"
    assert res_notepad.parameters.get("app_name") == "notepad"
    assert res_notepad.parameters.get("installed_only") is True

    res_chrome = hybrid_router.route("bật trình duyệt chrome")
    assert res_chrome is not None
    assert res_chrome.action_name == "app_open"
    assert res_chrome.parameters.get("app_name") == "chrome"

    res_calc = hybrid_router.route("khởi động calculator")
    assert res_calc is not None
    assert res_calc.action_name == "app_open"
    assert res_calc.parameters.get("app_name") == "calculator"

    res_vscode = hybrid_router.route("chạy visual studio code")
    assert res_vscode is not None
    assert res_vscode.action_name == "app_open"
    assert res_vscode.parameters.get("app_name") == "code"


def test_hybrid_router_timers_resolution(hybrid_router: HybridSemanticRouter):
    """Test typed slot extraction for timers and alarms."""
    res_timer = hybrid_router.route("hẹn giờ 10 phút")
    assert res_timer is not None
    assert res_timer.action_name == "timer_set"
    assert res_timer.parameters.get("duration") == 600

    res_sec = hybrid_router.route("bấm giờ 30 giây")
    assert res_sec is not None
    assert res_sec.action_name == "timer_set"
    assert res_sec.parameters.get("duration") == 30

    res_remind = hybrid_router.route("nhắc tôi sau 15 phút gọi điện")
    assert res_remind is not None
    assert res_remind.action_name == "reminder_set"
    assert res_remind.parameters.get("duration") == 900


def test_hybrid_router_notes_resolution(hybrid_router: HybridSemanticRouter):
    """Test typed slot extraction for personal notes."""
    res_note = hybrid_router.route("ghi chú mua sữa hôm nay")
    assert res_note is not None
    assert res_note.action_name == "note_add"
    assert "mua sữa" in res_note.parameters.get("content", "")

    res_memo = hybrid_router.route("lưu ghi chú chuẩn bị tài liệu họp")
    assert res_memo is not None
    assert res_memo.action_name == "note_add"
    assert "chuẩn bị tài liệu" in res_memo.parameters.get("content", "")


def test_hybrid_router_weather_resolution(hybrid_router: HybridSemanticRouter):
    """Test typed slot extraction for weather queries."""
    res_hn = hybrid_router.route("thời tiết hà nội")
    assert res_hn is not None
    assert res_hn.action_name == "shell_exec"
    assert res_hn.parameters.get("location") == "Hà Nội"

    res_sg = hybrid_router.route("dự báo thời tiết sài gòn")
    assert res_sg is not None
    assert res_sg.action_name == "shell_exec"
    assert res_sg.parameters.get("location") == "Sài Gòn"

    res_curr = hybrid_router.route("thời tiết hôm nay thế nào")
    assert res_curr is not None
    assert res_curr.action_name == "shell_exec"
    assert res_curr.parameters.get("location") == "current"


def test_hybrid_router_sub_2ms_latency_sla(hybrid_router: HybridSemanticRouter):
    """Verify sub-2ms intent resolution latency SLA across diverse commands."""
    test_queries = [
        "tăng âm lượng lên 20%",
        "giảm độ sáng màn hình",
        "mở notepad",
        "hẹn giờ 5 phút",
        "ghi chú mua bánh mì",
        "thời tiết hà nội",
        "tạm dừng nhạc",
    ]

    for q in test_queries:
        avg_ms = hybrid_router.benchmark_latency(q, iterations=50)
        assert avg_ms < 2.0, f"Query '{q}' exceeded 2ms SLA: {avg_ms:.4f}ms"


def test_app_process_text_command_uses_hybrid_router_fast_path():
    """Verify process_text_command executes via hybrid router, bypassing cloud LLM."""
    cfg = ConfigManager()
    app = JarvisApp(config=cfg, headless=True)
    app.dispatcher = MagicMock()
    app.llm_client = MagicMock()

    # Hybrid router is initialized
    app.hybrid_router = HybridSemanticRouter()

    action_res = MagicMock()
    action_res.success = True
    action_res.data = {"message": "Đã tăng âm lượng."}
    app.dispatcher.dispatch_action.return_value = action_res

    res = app.process_text_command("tăng âm lượng lên 20%")

    # Dispatched locally
    app.dispatcher.dispatch_action.assert_called_once()
    assert app.dispatcher.dispatch_action.call_args[1]["action_name"] == "system_volume"
    # LLM client chat must NOT be called (bypassed Cloud LLM roundtrip)
    app.llm_client.chat.assert_not_called()
    assert res.get("status") == "success" or res.get("response_text")
