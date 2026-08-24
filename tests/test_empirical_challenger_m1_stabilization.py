"""
tests/test_empirical_challenger_m1_stabilization.py
====================================================
Empirical Adversarial Challenge & Stress Test Suite for Milestone M1:
- Double-clap welcome vs voice-loop progression verification
- Cooldown debounce suppression (< 3.0s) & INFO logging verification
- Zero double-dispatch guarantees under synthetic acoustic transient injection
- Clap-pause-clap routing & show_overlay action verification
- STT engine fallback, web_speech provider mapping, and 2D PCM conversion
- HardwareReporter live status vocalization in _handle_system_status
- TTS SAPI5 fallback cascading and non-repeating welcome phrases pool
- Concurrency and rapid multi-thread stress testing
"""
from __future__ import annotations

import io
import logging
import math
import sys
import threading
import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.core.app import JarvisApp
from jarvis.core.config import ConfigManager
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import RequesterContext
from jarvis.gesture.detector import GestureDetector
from jarvis.gesture.models import GestureType
from jarvis.gesture.patterns import get_default_patterns
from jarvis.hardware.monitor import HardwareMetrics
from jarvis.hardware.reporter import HardwareReporter
from jarvis.stt.engine import (
    MockSTTEngine,
    OpenAIWhisperSTT,
    STTEngine,
    WindowsSpeechSTT,
    audio_to_float32,
    float32_to_pcm16_wav_bytes,
)
from jarvis.tts.fallback import SAPI5FallbackTTS
from jarvis.tts.manager import TTSManager, WELCOME_PHRASES


# ============================================================================
# 1. DOUBLE-CLAP WELCOME VS VOICE-LOOP PROGRESSION
# ============================================================================

def test_double_clap_welcome_first_time_then_voice_loop_progression():
    """
    [CHALLENGE-M1-01] Verify double-clap progression:
    - 1st double clap triggers the welcome sequence (Spotify, Chrome, TTS welcome, etc.).
    - 2nd double clap (after 3.0s cooldown) does NOT run welcome sequence again;
      instead, it enters the AI voice interaction loop (_ai_voice_loop).
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    executed_actions: List[str] = []
    app.event_bus.subscribe("action.post_dispatch", lambda **ev: executed_actions.append(ev.get("action_name", "")))

    # Set mock STT transcript
    app.stt_engine.primary_engine = MockSTTEngine(default_transcript="kiểm tra hệ thống")

    # --- FIRST TRIGGER (t=0.0s) ---
    assert app.welcome_executed is False
    app._on_gesture_event("double_clap", confidence=1.0)

    # Allow welcome background thread to dispatch actions
    time.sleep(0.3)

    assert app.welcome_executed is True
    assert "spotify" in executed_actions
    assert "chrome_claude" in executed_actions
    assert "tts_welcome" in executed_actions

    count_welcome_actions = len([a for a in executed_actions if a in ("spotify", "chrome_claude", "tts_welcome")])
    assert count_welcome_actions >= 3

    # Fast-forward monotonic clock past 3.0s cooldown
    with patch("time.monotonic", side_effect=[100.0, 100.0, 100.0, 100.0]):
        app._pattern_last_fired["double_clap"] = 0.0  # Reset to 0.0, now is 100.0 (elapsed = 100s > 3s)

        # Track spoken utterances
        spoken_phrases: List[str] = []
        if app.tts_manager:
            app.tts_manager.speak = lambda txt, **kw: spoken_phrases.append(txt) or True

        # Provide simulated audio for record_audio
        sr = 16000
        t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
        simulated_voice_audio = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        app.record_audio = lambda *a, **kw: simulated_voice_audio

        # --- SECOND TRIGGER (t=100.0s) ---
        app._on_gesture_event("double_clap", confidence=1.0)
        time.sleep(0.4)

        # Verify welcome actions were NOT re-executed
        count_welcome_after = len([a for a in executed_actions if a in ("spotify", "chrome_claude", "tts_welcome")])
        assert count_welcome_after == count_welcome_actions, "Welcome actions must not repeat on 2nd double clap"

        # Verify AI voice loop was executed:
        # TTS should have spoken listening prompt and/or response
        assert len(spoken_phrases) >= 1
        assert any("lắng nghe" in p.lower() or "hệ thống" in p.lower() or "thực hiện" in p.lower() for p in spoken_phrases)

    app.stop()


# ============================================================================
# 2. COOLDOWN DEBOUNCE SUPPRESSION UNDER RAPID CONSECUTIVE TRIGGERS (< 3.0s)
# ============================================================================

def test_cooldown_debounce_suppression_and_info_logging(caplog):
    """
    [CHALLENGE-M1-02] Verify rapid consecutive triggers within 3.0s are suppressed
    and log at INFO level with remaining cooldown time.
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    executed_count = 0
    app.dispatcher.register_action("custom_act", lambda **kw: {"status": "ok"})
    app.config.set("gesture.patterns.custom_pat.actions", ["custom_act"])
    app.event_bus.subscribe("action.post_dispatch", lambda **ev: None)

    with caplog.at_level(logging.INFO, logger="jarvis.core.app"):
        # Trigger 1 at t=10.0s -> Accepted
        with patch("time.monotonic", return_value=10.0):
            app._on_gesture_event("custom_pat", confidence=0.95)

        # Trigger 2 at t=10.5s (elapsed 0.5s < 3.0s) -> Suppressed
        with patch("time.monotonic", return_value=10.5):
            app._on_gesture_event("custom_pat", confidence=0.95)

        # Trigger 3 at t=12.0s (elapsed 2.0s < 3.0s) -> Suppressed
        with patch("time.monotonic", return_value=12.0):
            app._on_gesture_event("custom_pat", confidence=0.95)

        # Trigger 4 at t=12.9s (elapsed 2.9s < 3.0s) -> Suppressed
        with patch("time.monotonic", return_value=12.9):
            app._on_gesture_event("custom_pat", confidence=0.95)

        # Trigger 5 at t=13.1s (elapsed 3.1s >= 3.0s) -> Accepted
        with patch("time.monotonic", return_value=13.1):
            app._on_gesture_event("custom_pat", confidence=0.95)

    # Check suppression logs
    suppressed_logs = [r for r in caplog.records if "suppressed" in r.message.lower() and r.levelname == "INFO"]
    assert len(suppressed_logs) == 3, f"Expected 3 suppressed logs at INFO level, got {len(suppressed_logs)}"
    assert "cooldown 2.5s remaining" in suppressed_logs[0].message
    assert "cooldown 1.0s remaining" in suppressed_logs[1].message
    assert "cooldown 0.1s remaining" in suppressed_logs[2].message

    app.stop()


# ============================================================================
# 3. ZERO DOUBLE-DISPATCH GUARANTEES
# ============================================================================

def test_zero_double_dispatch_gesture_pipeline(mock_audio_stream):
    """
    [CHALLENGE-M1-03] Verify that when an acoustic gesture is recognized via AudioEngine/GestureDetector,
    actions are dispatched EXACTLY 1 time (zero double-dispatch).
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # Ensure gesture detector does not hold duplicate dispatcher
    assert app.gesture_detector.dispatcher is None, "GestureDetector.dispatcher must be None to prevent double-dispatch"

    dispatch_log: List[str] = []
    app.dispatcher.register_action("spotify", lambda **kw: dispatch_log.append("spotify") or {"status": "ok"})
    app.dispatcher.register_action("chrome_claude", lambda **kw: dispatch_log.append("chrome_claude") or {"status": "ok"})
    app.dispatcher.register_action("chrome_binance", lambda **kw: dispatch_log.append("chrome_binance") or {"status": "ok"})
    app.dispatcher.register_action("tts_welcome", lambda **kw: dispatch_log.append("tts_welcome") or {"status": "ok"})
    app.dispatcher.register_action("cursor", lambda **kw: dispatch_log.append("cursor") or {"status": "ok"})

    # Synthetic double-clap audio buffer
    pcm = mock_audio_stream.generate_double_clap(gap_s=0.15, leading_silence_s=0.1, trailing_silence_s=0.7)

    # Feed into AudioEngine
    if app.audio_engine:
        app.audio_engine.feed_audio(pcm)

    time.sleep(0.8)

    # Verify each welcome action was dispatched EXACTLY ONCE
    assert dispatch_log.count("spotify") == 1
    assert dispatch_log.count("chrome_claude") == 1
    assert dispatch_log.count("chrome_binance") == 1
    assert dispatch_log.count("tts_welcome") == 1
    assert dispatch_log.count("cursor") == 1

    app.stop()


# ============================================================================
# 4. CLAP-PAUSE-CLAP DISPATCHING SHOW_OVERLAY
# ============================================================================

def test_clap_pause_clap_dispatches_show_overlay(mock_audio_stream):
    """
    [CHALLENGE-M1-04] Verify clap_pause_clap pattern routes to show_overlay action
    in default patterns, default config, and app event handler.
    """
    # 1. Check default patterns dictionary
    patterns = get_default_patterns()
    assert GestureType.CLAP_PAUSE_CLAP in patterns
    assert patterns[GestureType.CLAP_PAUSE_CLAP].actions == ["show_overlay"]

    # 2. Check JarvisApp initialization & dispatch
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    executed_actions: List[str] = []
    app.dispatcher.register_action("show_overlay", lambda **kw: executed_actions.append("show_overlay") or {"status": "ok"})

    # Trigger clap_pause_clap gesture
    app._on_gesture_event("clap_pause_clap", confidence=0.99)

    assert "show_overlay" in executed_actions
    assert executed_actions.count("show_overlay") == 1

    # 3. Verify _handle_show_overlay with overlay mock
    mock_overlay = MagicMock()
    app.overlay = mock_overlay
    res = app._handle_show_overlay()
    assert res["status"] == "overlay_shown"
    mock_overlay.show_listening.assert_called_once()

    app.stop()


# ============================================================================
# 5. STT ENGINE FALLBACK & AUDIO CONVERSION
# ============================================================================

def test_stt_provider_resolution_and_2d_audio_normalization():
    """
    [CHALLENGE-M1-05] Verify STTEngine provider mapping ('web_speech', 'windows', 'web')
    and test audio_to_float32 on 2D multi-channel int16 numpy buffers.
    """
    # 1. Provider resolution
    stt_web = STTEngine(config={"provider": "web_speech"})
    if sys.platform == "win32":
        assert isinstance(stt_web.primary_engine, WindowsSpeechSTT)
    else:
        assert isinstance(stt_web.primary_engine, MockSTTEngine)

    stt_windows = STTEngine(config={"provider": "windows"})
    if sys.platform == "win32":
        assert isinstance(stt_windows.primary_engine, WindowsSpeechSTT)

    # 2. 2D multi-channel int16 normalization
    # Stereo int16 array: shape (1600, 2)
    stereo_int16 = np.full((1600, 2), 16384, dtype=np.int16)
    float_out = audio_to_float32(stereo_int16)

    assert float_out.ndim == 1
    assert len(float_out) == 1600
    assert float_out.dtype == np.float32
    # 16384 / 32768 = 0.5 (approx)
    assert np.isclose(float_out[0], 0.5, atol=1e-3)
    assert np.all(float_out <= 1.0) and np.all(float_out >= -1.0)

    # 3. MockSTTEngine dynamic set_transcript and kwargs
    mock_stt = MockSTTEngine()
    mock_stt.set_transcript("lệnh mới đã cập nhật")

    # Non-silent test buffer
    sine_buf = (0.5 * np.sin(np.linspace(0, 10, 1600))).astype(np.float32)
    assert mock_stt.transcribe(sine_buf) == "lệnh mới đã cập nhật"
    assert mock_stt.transcribe(sine_buf, transcript="override text") == "override text"
    assert mock_stt.transcribe(sine_buf, canned_key="nhiệt độ") == "kiểm tra nhiệt độ cpu"

    # 4. Silence gating
    silence = np.zeros(1600, dtype=np.float32)
    assert mock_stt.transcribe(silence) == ""


# ============================================================================
# 6. LIVE HARDWARE TELEMETRY IN SYSTEM STATUS ACTION
# ============================================================================

def test_system_status_live_hardware_metrics():
    """
    [CHALLENGE-M1-06] Verify _handle_system_status probes live HardwareReporter
    and vocalizes metrics in Vietnamese and English.
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # Track spoken text
    spoken: List[str] = []
    if app.tts_manager:
        app.tts_manager.speak = lambda txt, **kw: spoken.append(txt) or True

    # Vietnamese query
    app.config.set("system.locale", "vi_VN")
    res_vi = app._handle_system_status()
    assert res_vi["status"] == "healthy"
    assert "Tình trạng hệ thống" in res_vi["message"] or "CPU" in res_vi["message"] or "RAM" in res_vi["message"]
    assert "metrics" in res_vi
    assert len(spoken) >= 1

    # English query
    spoken.clear()
    app.config.set("system.locale", "en_US")
    res_en = app._handle_system_status()
    assert res_en["status"] == "healthy"
    assert "CPU" in res_en["message"] or "RAM" in res_en["message"] or "operating normally" in res_en["message"]
    assert len(spoken) >= 1

    app.stop()


# ============================================================================
# 7. TTS SAPI5 FALLBACK & WELCOME GREETINGS POOL
# ============================================================================

def test_tts_welcome_phrases_pool_non_repeating():
    """
    [CHALLENGE-M1-07] Verify speak_welcome selects non-repeating phrases from config pool.
    """
    cfg = {
        "welcome": {
            "phrases": [
                "Phrase Alpha",
                "Phrase Beta",
                "Phrase Gamma",
            ]
        }
    }
    tts = TTSManager(config=cfg)

    spoken_welcome: List[str] = []
    tts.speak = lambda txt, **kw: spoken_welcome.append(txt) or True

    for _ in range(10):
        tts.speak_welcome(delay_s=0.0)
        time.sleep(0.02)

    assert len(spoken_welcome) == 10
    # Verify no two consecutive phrases are identical
    for i in range(len(spoken_welcome) - 1):
        assert spoken_welcome[i] != spoken_welcome[i + 1], f"Consecutive repeat: {spoken_welcome[i]}"

    tts.stop()


# ============================================================================
# 8. CONCURRENCY & STRESS HARNESS
# ============================================================================

def test_jarvis_app_concurrent_gesture_and_commands_stress():
    """
    [CHALLENGE-M1-08] High-concurrency stress test:
    20 threads hammering _on_gesture_event, process_text_command, and _handle_system_status.
    Verifies thread safety, absence of deadlocks, and zero uncaught exceptions.
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    errors: List[Exception] = []
    num_threads = 20
    ops_per_thread = 20

    def _worker(thread_idx: int):
        try:
            for i in range(ops_per_thread):
                op = (thread_idx + i) % 3
                if op == 0:
                    app._on_gesture_event("triple_clap", confidence=0.9)
                elif op == 1:
                    app.process_text_command("kiểm tra trạng thái hệ thống", requester=f"worker_{thread_idx}")
                else:
                    app._handle_system_status()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(t,)) for t in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)
        assert not t.is_alive(), f"Thread {t.name} hung or deadlocked"

    assert len(errors) == 0, f"Encountered concurrency errors: {errors}"
    app.stop()
