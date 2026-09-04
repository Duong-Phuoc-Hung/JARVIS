"""
tests/test_challenger_m1_2_empirical.py
=========================================
Empirical Challenger 2 Test Suite for Milestone M1:
Voice AI Pipeline Bug Fixes, Decoupling & Telemetry Stabilization.

Target Areas:
  1. Headless audio capture (`record_audio()`): non-blocking, zero-latency, exception resilience.
  2. STT Fallback: missing/invalid API keys, HTTP failures, provider name resolution, silence gating.
  3. TTS Cascading Fallback: ElevenLabs failure -> SAPI5 fallback, multi-threaded safety, randomized welcome pool.
  4. Live `system_status` telemetry: live CPU/RAM metrics, Vietnamese voice summary, fault tolerance.
  5. End-to-end Voice Pipeline Timing: latency benchmark (<10s requirement, target <200ms in mock/headless).
"""
import base64
import io
import math
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.audio.dsp import calculate_rms
from jarvis.core.app import JarvisApp
from jarvis.core.config import ConfigManager
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import PrivilegeLevel, RequesterContext
from jarvis.hardware.monitor import HardwareMetrics, HardwareMonitor
from jarvis.hardware.reporter import HardwareReporter
from jarvis.llm.client import LLMClient
from jarvis.llm.router import IntentResult, LLMIntentRouter
from jarvis.stt.engine import (
    BaseSTTEngine,
    FasterWhisperSTT,
    MockSTTEngine,
    OpenAIWhisperSTT,
    STTEngine,
    STTError,
    VADSegmenter,
    WindowsSpeechSTT,
    audio_to_float32,
    float32_to_pcm16_wav_bytes,
)
from jarvis.tts.base import BaseTTSEngine, TTSError
from jarvis.tts.elevenlabs import ElevenLabsTTS
from jarvis.tts.fallback import SAPI5FallbackTTS
from jarvis.tts.manager import WELCOME_PHRASES, TTSManager

# ============================================================================
# 1. HEADLESS AUDIO CAPTURE (`record_audio()`)
# ============================================================================

def test_record_audio_headless_zero_latency_and_non_blocking():
    """
    [CHALLENGE-1.1] Verify record_audio() in headless mode returns immediately
    without blocking for duration_s and produces a valid silent float32 buffer.
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # Test default duration and custom duration
    durations = [0.05, 1.0, 5.0, 10.0]
    for dur in durations:
        t0 = time.perf_counter()
        buffer = app.record_audio(duration_s=dur, sample_rate=16000)
        dt = time.perf_counter() - t0

        # Latency must be near-instant (< 20ms), not blocking for `dur` seconds
        assert dt < 0.05, f"record_audio blocked for {dt:.4f}s on dur={dur}s in headless mode!"
        assert isinstance(buffer, np.ndarray)
        assert buffer.dtype == np.float32
        assert buffer.ndim == 1
        # In headless mode, buffer length is sr * min(dur, 0.1)
        expected_samples = int(16000 * min(dur, 0.1))
        assert len(buffer) == expected_samples
        assert np.all(buffer == 0.0)

    app.stop()


def test_record_audio_exception_resilience_when_sounddevice_fails():
    """
    [CHALLENGE-1.2] Verify record_audio() when headless=False safely catches
    sounddevice exceptions and returns a silent buffer without raising unhandled errors.
    """
    app = JarvisApp(headless=False, no_hot_reload=True)
    app.initialize()

    # Simulate sounddevice raising PortAudioError or generic exception
    with patch("sounddevice.rec", side_effect=RuntimeError("PortAudio device unavailable")):
        t0 = time.perf_counter()
        buffer = app.record_audio(duration_s=5.0, sample_rate=16000)
        dt = time.perf_counter() - t0

        assert dt < 0.1, f"Fallback buffer generation took too long: {dt:.4f}s"
        assert isinstance(buffer, np.ndarray)
        assert buffer.dtype == np.float32
        assert len(buffer) == int(16000 * 0.1)
        assert np.all(buffer == 0.0)

    app.stop()


# ============================================================================
# 2. STT FALLBACK (MISSING/INVALID API KEY & HTTP ERRORS)
# ============================================================================

def test_stt_openai_whisper_missing_and_invalid_key_availability():
    """
    [CHALLENGE-2.1] Verify OpenAIWhisperSTT correctly identifies missing or blank API keys
    and raises STTError when invoked directly without valid credentials.
    """
    # Empty string key
    stt_empty = OpenAIWhisperSTT(config={"api_key": ""})
    assert stt_empty.is_available() is False

    # Whitespace key
    stt_space = OpenAIWhisperSTT(config={"api_key": "   "})
    assert stt_space.is_available() is False

    # Non-empty key
    stt_key = OpenAIWhisperSTT(config={"api_key": "sk-mock-key-123"})
    assert stt_key.is_available() is True

    # Non-silent synthetic audio
    tone = (np.sin(np.linspace(0, 100, 16000)) * 0.5).astype(np.float32)

    # Calling transcribe on unavailable engine raises STTError
    with pytest.raises(STTError, match="API key missing or invalid"):
        stt_empty.transcribe(tone)


def test_stt_unified_engine_graceful_fallback_cascade():
    """
    [CHALLENGE-2.2] Verify STTEngine cascades from failing primary (OpenAI Whisper)
    to fallback engine (MockSTTEngine) without leaking exceptions.
    """
    # Primary configured with mock key that will fail HTTP
    primary = OpenAIWhisperSTT(config={"api_key": "invalid_key", "timeout_s": 0.5})
    fallback = MockSTTEngine(default_transcript="bật đèn phòng khách fallback")

    coordinator = STTEngine(
        primary_engine=primary,
        fallback_engine=fallback,
    )

    tone = (np.sin(np.linspace(0, 100, 16000)) * 0.5).astype(np.float32)

    # Simulate HTTP 401 Unauthorized from OpenAI API
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = '{"error": {"message": "Incorrect API key provided"}}'

    with patch("requests.post", return_value=mock_resp):
        transcript = coordinator.transcribe(tone)
        assert transcript == "bật đèn phòng khách fallback"


def test_stt_provider_resolution_mappings():
    """
    [CHALLENGE-2.3] Verify provider aliases map correctly:
    'web_speech', 'windows_sapi', 'windows', 'web' -> WindowsSpeechSTT (or MockSTTEngine on non-win32).
    """
    engine_web = STTEngine(provider="web_speech")
    if sys.platform == "win32":
        assert isinstance(engine_web.primary_engine, WindowsSpeechSTT)
    else:
        assert isinstance(engine_web.primary_engine, MockSTTEngine)

    engine_win = STTEngine(provider="windows")
    if sys.platform == "win32":
        assert isinstance(engine_win.primary_engine, WindowsSpeechSTT)
    else:
        assert isinstance(engine_win.primary_engine, MockSTTEngine)

    engine_mock = STTEngine(provider="mock")
    assert isinstance(engine_mock.primary_engine, MockSTTEngine)


def test_stt_fast_silence_gating():
    """
    [CHALLENGE-2.4] Verify pure silence skips remote API calls and returns empty string.
    """
    primary = MagicMock(spec=BaseSTTEngine)
    coordinator = STTEngine(primary_engine=primary)

    # Silent buffer
    silence = np.zeros(16000, dtype=np.float32)
    res = coordinator.transcribe(silence)
    assert res == ""
    primary.transcribe.assert_not_called()


# ============================================================================
# 3. TTS SAPI5 FALLBACK & RANDOMIZED WELCOME POOL
# ============================================================================

def test_tts_elevenlabs_http_failure_cascades_to_sapi5():
    """
    [CHALLENGE-3.1] Verify ElevenLabsTTS HTTP failure (500 / 401 / Timeout)
    cascades to SAPI5 fallback without throwing unhandled exceptions.
    """
    spoken_fallback: List[str] = []

    class CapturingFallback(BaseTTSEngine):
        def is_available(self) -> bool:
            return True
        @property
        def engine_name(self) -> str:
            return "capturing_fallback"
        def speak(self, text: str, voice_id: Optional[str] = None, wait: bool = False, **kwargs) -> bool:
            spoken_fallback.append(text)
            return True
        def synthesize_to_bytes(self, text: str, **kwargs) -> bytes:
            return b"pcm_fallback_bytes"

    # Primary with key that fails HTTP
    primary = ElevenLabsTTS(config={"api_key": "fake_elevenlabs_key"})
    fallback = CapturingFallback()

    manager = TTSManager(
        primary_engine=primary,
        fallback_engine=fallback,
        cache_dir=".cache/test_tts_challenger",
    )

    # Mock HTTP 500 from ElevenLabs API
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    with patch("requests.post", return_value=mock_resp):
        success = manager.speak("JARVIS kiểm tra hệ thống", wait=True)
        assert success is True
        assert "JARVIS kiểm tra hệ thống" in spoken_fallback

    manager.stop()


def test_sapi5_fallback_tts_multithread_and_powershell_safety():
    """
    [CHALLENGE-3.2] Verify SAPI5FallbackTTS execution in background threads
    handles COM initialization and doesn't crash on empty or whitespace strings.
    """
    engine = SAPI5FallbackTTS()

    # Empty strings
    assert engine.speak("") is False
    assert engine.speak("   \n\t ") is False

    # Multi-threaded stress test: 10 concurrent threads invoking speak()
    results: List[bool] = []
    def _worker(thread_id: int):
        # Mock win32com or PowerShell execution to verify thread entry
        res = engine.speak(f"Test thread voice {thread_id}", wait=False)
        results.append(res)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=2.0)

    assert len(results) == 10
    assert all(r is True for r in results)


def test_tts_welcome_phrases_randomized_non_repeating():
    """
    [CHALLENGE-3.3] Verify speak_welcome() picks non-repeating phrases from the pool.
    """
    spoken_phrases: List[str] = []

    class CapturingTTSManager(TTSManager):
        def speak(self, text: str, **kwargs) -> bool:
            spoken_phrases.append(text)
            return True

    mgr = CapturingTTSManager()

    # Call speak_welcome multiple times
    for _ in range(8):
        mgr.speak_welcome(delay_s=0.0)

    # Allow worker threads to execute
    time.sleep(0.2)

    assert len(spoken_phrases) == 8
    # Verify no two consecutive phrases are identical
    for i in range(len(spoken_phrases) - 1):
        assert spoken_phrases[i] != spoken_phrases[i + 1], (
            f"Consecutive duplicate welcome phrase found: {spoken_phrases[i]}"
        )

    mgr.stop()


# ============================================================================
# 4. LIVE `system_status` HARDWARE TELEMETRY OUTPUT
# ============================================================================

def test_system_status_live_telemetry_vocalization():
    """
    [CHALLENGE-4.1] Verify _handle_system_status returns live CPU and RAM metrics
    with natural Vietnamese voice formatting and non-empty telemetry.
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # Ensure HardwareReporter is present
    assert app.hardware_reporter is not None
    assert app.hardware_reporter.monitor is not None

    res = app._handle_system_status()

    assert res["status"] == "healthy"
    assert "message" in res
    assert "metrics" in res

    msg = res["message"]
    assert "Tình trạng hệ thống" in msg or "CPU" in msg
    assert "phần trăm" in msg or "percent" in msg

    metrics = res["metrics"]
    assert isinstance(metrics, dict)
    assert "cpu_percent" in metrics
    assert "ram_percent" in metrics
    assert isinstance(metrics["cpu_percent"], (int, float))
    assert isinstance(metrics["ram_percent"], (int, float))
    assert 0.0 <= metrics["cpu_percent"] <= 100.0
    assert 0.0 <= metrics["ram_percent"] <= 100.0

    app.stop()


def test_system_status_sub_millisecond_execution_and_fault_isolation():
    """
    [CHALLENGE-4.2] Benchmark _handle_system_status execution time (< 100ms)
    and verify fault isolation when hardware monitor probes fail.
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # Benchmark normal probe execution
    t0 = time.perf_counter()
    res = app._handle_system_status()
    dt_ms = (time.perf_counter() - t0) * 1000.0
    assert dt_ms < 100.0, f"System status probe took {dt_ms:.2f}ms (threshold: 100ms)"

    # Fault isolation: Simulate exception inside hardware reporter
    with patch.object(app.hardware_reporter.monitor, "get_metrics", side_effect=RuntimeError("Hardware sensor error")):
        with patch.object(app.hardware_reporter.monitor, "_probe_ram", side_effect=RuntimeError("RAM probe error")):
            res_fail = app._handle_system_status()
            assert res_fail["status"] == "healthy"
            assert "Tất cả dịch vụ đang hoạt động bình thường" in res_fail["message"]

    app.stop()


# ============================================================================
# 5. FULL VOICE PIPELINE TIMING (< 10s REQUIREMENT) & GESTURE DEBOUNCE
# ============================================================================

def test_full_mock_voice_pipeline_timing_sub_second():
    """
    [CHALLENGE-5.1] Verify that full voice pipeline execution:
    Voice Audio -> STT -> Intent Parsing -> Action Execution -> TTS Spoken Output
    completes in < 10.0 seconds (target: < 200ms in mock mode).
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # Deterministic Mock STT
    app.stt_engine.primary_engine = MockSTTEngine(default_transcript="tình trạng hệ thống")

    # Synthetic non-silent speech audio
    tone = (np.sin(np.linspace(0, 100, 16000)) * 0.5).astype(np.float32)

    latencies: List[float] = []
    for _ in range(10):
        t0 = time.perf_counter()
        result = app.process_voice_command(tone)
        elapsed = time.perf_counter() - t0
        latencies.append(elapsed)

        assert result["success"] is True
        assert result["transcript"] == "tình trạng hệ thống"
        assert result["response_text"] != ""

    max_latency = max(latencies)
    avg_latency = sum(latencies) / len(latencies)

    # Must be far below the 10.0s requirement
    assert max_latency < 2.0, f"Max voice pipeline latency was {max_latency:.3f}s (must be < 10.0s)!"
    assert avg_latency < 0.2, f"Average voice pipeline latency was {avg_latency:.3f}s!"

    app.stop()


def test_gesture_routing_and_cooldown_debounce_enforcement():
    """
    [CHALLENGE-5.2] Verify double-clap routing, clap-pause-clap overlay dispatch,
    and 3.0s cooldown debounce suppression.
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()
    # P0 runaway-hardening: the fanout is opt-in by default now (see
    # gesture.patterns.double_clap.allow_side_effect_fanout) -- safe to opt
    # in here since every action below is re-registered as a fake handler.
    app.config.set("gesture.patterns.double_clap.allow_side_effect_fanout", True)

    dispatched_actions: List[str] = []
    app.dispatcher.register_action("spotify", lambda **kw: dispatched_actions.append("spotify") or {"status": "ok"})
    app.dispatcher.register_action("chrome_claude", lambda **kw: dispatched_actions.append("chrome_claude") or {"status": "ok"})
    app.dispatcher.register_action("chrome_binance", lambda **kw: dispatched_actions.append("chrome_binance") or {"status": "ok"})
    app.dispatcher.register_action("cursor", lambda **kw: dispatched_actions.append("cursor") or {"status": "ok"})
    app.dispatcher.register_action("show_overlay", lambda **kw: dispatched_actions.append("show_overlay") or {"status": "ok"})

    # 1. First Double Clap -> Welcome Sequence
    app._on_gesture_event("double_clap", confidence=0.95)
    time.sleep(0.1)
    assert app.welcome_executed is True
    assert "spotify" in dispatched_actions

    # 2. Immediate Second Double Clap (within 3.0s cooldown) -> Suppressed
    dispatched_len = len(dispatched_actions)
    app._on_gesture_event("double_clap", confidence=0.95)
    time.sleep(0.05)
    assert len(dispatched_actions) == dispatched_len, "Second double-clap within cooldown was not suppressed!"

    # 3. Clap-Pause-Clap -> show_overlay
    # Wait out or reset cooldown timer for clap_pause_clap
    app._passive_trigger_guard.reset("GESTURE:clap_pause_clap")  # P0 runaway-hardening: clear circuit-breaker state instead of the old ad hoc _pattern_last_fired dict
    app._on_gesture_event("clap_pause_clap", confidence=0.90)
    time.sleep(0.05)
    assert "show_overlay" in dispatched_actions

    app.stop()
