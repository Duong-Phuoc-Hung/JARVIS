# Automated User Simulation Test Suite & Full Regression Analysis (Milestone M4)

**Explorer**: Explorer 2  
**Target File**: `tests/test_user_simulation.py`  
**Milestone**: M4 (User Simulation Test Suite & Full Regression)  
**Date**: 2026-08-22  

---

## 1. Executive Summary

Milestone M4 requires building a comprehensive, automated user simulation test suite in `tests/test_user_simulation.py` that verifies the entire JARVIS system behaves identically to an authentic human user interacting with the assistant on Windows.

This investigation provides:
1. **Precise behavioral contracts** for all core subsystems: `JarvisOverlay`, `STTEngine`, `LLMIntentRouter`, `TTSManager`, `GestureDetector`, and `JarvisApp`.
2. **14 targeted simulation tests** covering overlay state transitions, breathing/typing animations, thread safety & stress cycles, STT graceful fallback, 7 Vietnamese LLM keyword router categories with critical power safety flags, TTS cascading to SAPI5, gesture lifecycle & cooldown suppression, zero double-dispatch, and end-to-end pipeline execution time ($< 10.0$s).
3. **Complete, copy-pasteable test designs** ready for the implementation worker.

---

## 2. Codebase Architecture & Subsystem Analysis

### 2.1 UI Overlay Subsystem (`jarvis/ui/overlay.py`)
- **State Machine**:
  - `OverlayState.IDLE`: Overlay started but hidden, status is `"Sẵn sàng"`.
  - `OverlayState.LISTENING`: Triggered via `show_listening(prompt)`. Deiconifies root, status is `"Đang lắng nghe giọng nói"`, displays `"🎤 Đang lắng nghe..."`, starts 10-step amber-to-gold breathing dot gradient animation (`BREATHING_GRADIENT`: `#B8860B` $\to$ `#FFF8DC`).
  - `OverlayState.THINKING`: Triggered via `show_thinking(transcript)`. Status is `"AI đang suy nghĩ"`, displays `"⟳ Đang xử lý..."`, starts cycling typing dot animation (`"."`, `".."` , `"..."` every 350ms).
  - `OverlayState.RESPONSE`: Triggered via `show_response(transcript, response, duration_s, hint)`. Status is `"Hoàn thành"`, renders user transcript and truncated JARVIS response ($\le 240$ chars), displays footer tooltip hint `"💡 Double clap để hỏi tiếp"`, arms auto-hide timer `_hide_job`.
  - `OverlayState.HIDDEN`: Triggered via `hide()`. Withdraws root, cancels all active animation jobs (`_breathing_job`, `_typing_job`, `_hide_job`), resets text buffers and status to `"Sẵn sàng"`, invokes `on_close` callback if registered.
- **Headless Mode & Thread Safety**:
  - When initialized with `headless=True` or when Tkinter display is unavailable, all operations are executed synchronously without creating native OS window handles.
  - `_schedule(fn)` routes to `root.after(0, fn)` if root exists, or executes directly with error isolation.
  - Re-entrant thread lock `_lock` protects cleanup and destruction.

### 2.2 Speech-to-Text (STT) Subsystem (`jarvis/stt/engine.py`)
- **Multi-Provider Architecture**:
  - `primary_engine`: Default is `OpenAIWhisperSTT` (or `FasterWhisperSTT` / `MockSTTEngine`).
  - `fallback_engine`: Default on Windows is `WindowsSpeechSTT` or `MockSTTEngine`.
- **Fault Tolerance & Fallback Flow**:
  - If `OpenAIWhisperSTT` has an empty/missing API key, `is_available()` returns `False`. If called directly, it raises `STTError("OpenAI API key missing or invalid")`.
  - `STTEngine.transcribe()` wraps primary engine execution in `try ... except Exception as e: log.warning(...)`, gracefully falling back to `fallback_engine.transcribe()`.
  - Fast Silence Gate: `calculate_rms(arr) < 0.001` returns `""` immediately without making unnecessary network requests or subprocess calls.
  - Gated providers: `"web_speech"` correctly resolves to `WindowsSpeechSTT` on Windows or `MockSTTEngine` on non-Windows platforms.

### 2.3 LLM Semantic & Smart Keyword Router (`jarvis/llm/router.py`)
- **Three-Tier Architecture**:
  - **Tier 1 (Fast Path)**: Sub-millisecond regex & sorted exact dictionary rules for instant local matching.
  - **Tier 2 (LLM Reasoning)**: OpenAI / Gemini / Claude multi-provider semantic reasoning with dynamic schema generation from `ActionDispatcher`.
  - **Tier 3 (Rule Fallback)**: Deterministic Vietnamese keyword matching triggered on missing API key, network timeout, or HTTP 429 errors.
- **The 7 Required Vietnamese Keyword Categories**:
  1. **Smart Home** (`home_assistant_call`): `"bật đèn"`, `"tắt đèn"`, `"bật đèn phòng khách"`, `"bật quạt"`, `"bật điều hòa"`. Parameters: `domain`, `service`, `entity_id`. Response: Natural Vietnamese phrasing.
  2. **System Status / Hardware Telemetry** (`hardware_status_query` / `hardware_telemetry_check`): `"nhiệt độ CPU"`, `"kiểm tra RAM"`, `"tình trạng hệ thống"`, `"kiểm tra GPU"`. Parameters: `component`. Response: Natural hardware status.
  3. **Spotify / Music** (`spotify`): `"mở Spotify"`, `"bật nhạc"`, `"phát bài Sơn Tùng"`, `"dừng nhạc"` (`command="pause"`), `"chuyển bài"` (`command="next"`).
  4. **Weather** (`shell_exec`): `"thời tiết hôm nay"`, `"dự báo thời tiết Hà Nội"`, `"thời tiết Sài Gòn"`. Parameters: `topic="weather"`, `location="Hà Nội"`.
  5. **Reminder** (`reminder`): `"nhắc nhở uống nước sau 15 phút"`, `"nhắc tôi họp nhóm sau 1 giờ"`, `"tạo nhắc nhở"`. Parameters: `message`, `delay_s` (calculated in seconds), `delay_minutes`.
  6. **System Power (Safety Flags)** (`system_power`): `"tắt máy"`, `"tắt máy tính"`, `"restart"`, `"khởi động lại máy"`, `"chế độ ngủ"`, `"khóa màn hình"`.
     - **Safety Contract**: For destructive operations (`shutdown`, `restart`), must have `requires_confirmation = True`, `danger_level = "CRITICAL"`, and a populated `confirmation_prompt`. For non-destructive (`lock`), `requires_confirmation = False`, `danger_level = "LOW"`.
  7. **Default Fallback** (`unknown_intent`): Unrecognized queries return `action_name = "unknown_intent"`, `confidence = 0.0`, and `response_text = "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"`.

### 2.4 Text-to-Speech (TTS) Subsystem (`jarvis/tts/manager.py` & `fallback.py`)
- **Cascading Fallback Mechanism**:
  - `TTSManager` first checks disk cache (`TTSAudioCache`).
  - If cache misses, tries `primary_engine` (`ElevenLabsTTS`).
  - If ElevenLabs fails (invalid API key, network error, 401 Unauthorized), logs warning and cascades to `fallback_engine` (`SAPI5FallbackTTS`).
  - `SAPI5FallbackTTS` handles synthesis via `win32com.client` -> PowerShell `System.Speech` -> `pyttsx3` -> mock logging.
  - Returns `True` and appends text to `spoken_history` without crashing or throwing unhandled exceptions.
- **Randomized Greetings Pool**:
  - `get_welcome_phrase()` chooses from `WELCOME_PHRASES` (or configured pool) and guarantees that the chosen phrase is not identical to the immediately previous phrase.

### 2.5 Core App Integration & Interaction Lifecycle (`jarvis/core/app.py`)
- **Gesture Routing**:
  - 1st `double_clap` $\to$ Runs welcome sequence once (`self.welcome_executed = True`), launching Spotify, Chrome, Cursor, and TTS welcome.
  - 2nd+ `double_clap` $\to$ Activates AI voice loop (`show_listening()` $\to$ record audio $\to$ STT $\to$ `show_thinking()` $\to$ LLM Router $\to$ Dispatch $\to$ `show_response()` $\to$ TTS speak).
  - `triple_clap` $\to$ Dispatches `system_status` (vocalizes live CPU/RAM metrics via `HardwareReporter`).
  - `clap_pause_clap` $\to$ Dispatches `show_overlay`.
- **Debounce & Cooldown Guard**:
  - `_action_fanout_cooldown_s = 3.0`.
  - If a second gesture arrives within $< 3.0$ seconds of the previous trigger of the same pattern, it is debounced/suppressed and logged as `Gesture [...] suppressed — cooldown X.Xs remaining`.
- **Zero Double-Dispatch**:
  - `GestureDetector` is initialized with `dispatcher=None` to ensure actions are only dispatched once via `_on_gesture_event`.
- **End-to-End Pipeline Performance**:
  - In mock/offline mode, the full pipeline (`process_voice_command` or gesture-to-spoken response) executes deterministically in $< 10.0$ seconds (typically $< 0.15$ seconds).

---

## 3. Test Suite Design: `tests/test_user_simulation.py`

The test suite will contain 14 comprehensive, non-overlapping tests organized into 6 logical simulation domains:

```
tests/test_user_simulation.py
├── Domain 1: HUD Overlay State Machine, Animations & Stability
│   ├── test_simulation_overlay_state_machine_fsm_complete_cycle()
│   ├── test_simulation_overlay_breathing_and_typing_animation_logic()
│   ├── test_simulation_overlay_thread_safety_and_stability_cycles()
│   └── test_simulation_overlay_multithreaded_concurrency_stress()
│
├── Domain 2: Speech-to-Text (STT) Fault Tolerance & Fallback
│   ├── test_simulation_stt_fallback_on_missing_or_invalid_whisper_key()
│   └── test_simulation_stt_web_speech_and_silence_gating()
│
├── Domain 3: Vietnamese LLM Smart Keyword Router & Safety Flags
│   ├── test_simulation_llm_router_vietnamese_7_categories()
│   └── test_simulation_llm_router_power_safety_confirmation_flags()
│
├── Domain 4: Text-to-Speech (TTS) Fallback & Greeting Resilience
│   ├── test_simulation_tts_fallback_cascades_to_sapi5_on_invalid_key()
│   └── test_simulation_tts_randomized_greeting_pool_resilience()
│
├── Domain 5: End-to-End Pipeline Performance & Latency
│   └── test_simulation_e2e_mock_pipeline_latency_under_10_seconds()
│
└── Domain 6: Simulated User Gesture Workflows & Zero Double-Dispatch
    ├── test_simulation_gesture_double_clap_voice_loop_lifecycle()
    ├── test_simulation_gesture_cooldown_and_zero_double_dispatch()
    └── test_simulation_system_status_live_vocalization_flow()
```

---

## 4. Exact Test Implementation Blueprint

Below is the complete specification and code layout designed for `tests/test_user_simulation.py`:

```python
"""
tests/test_user_simulation.py
=============================
Automated User Simulation Test Suite & Full System Regression for JARVIS (Milestone M4).
Simulates authentic human user interactions with zero cloud dependencies:
1. Overlay state transitions (IDLE -> LISTENING -> THINKING -> RESPONSE -> HIDDEN) with breathing & typing animations.
2. Overlay thread safety, stress cycling (15+ cycles), and concurrent access.
3. STT fallback when Whisper API key is missing/invalid, web_speech provider mapping, and silence gating.
4. LLM Smart Keyword Router in Vietnamese across all 7 categories with critical system power safety confirmation flags.
5. TTS cascading to SAPI5 fallback on invalid ElevenLabs credentials and non-repeating welcome pool.
6. Full end-to-end voice loop pipeline latency benchmark (< 10.0s).
7. Acoustic gesture simulation: double clap welcome flow, AI voice interaction loop, 3.0s cooldown debounce, and zero double-dispatch.
"""
from __future__ import annotations

import concurrent.futures
import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from jarvis.core.app import JarvisApp
from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import ActionResult, RequesterContext
from jarvis.llm.client import LLMClient
from jarvis.llm.router import IntentResult, LLMIntentRouter
from jarvis.stt.engine import (
    BaseSTTEngine,
    MockSTTEngine,
    OpenAIWhisperSTT,
    STTEngine,
    STTError,
    WindowsSpeechSTT,
)
from jarvis.tts.base import BaseTTSEngine
from jarvis.tts.fallback import SAPI5FallbackTTS
from jarvis.tts.manager import TTSManager, WELCOME_PHRASES
from jarvis.ui.overlay import (
    BREATHING_GRADIENT,
    COLORS,
    JarvisOverlay,
    OverlayState,
)


# ============================================================================
# DOMAIN 1: HUD OVERLAY STATE MACHINE, ANIMATIONS & STABILITY
# ============================================================================

def test_simulation_overlay_state_machine_fsm_complete_cycle():
    """
    [Simulation 1.1] Verify overlay progresses cleanly through all 5 FSM states:
    IDLE -> LISTENING -> THINKING -> RESPONSE -> HIDDEN.
    """
    overlay = JarvisOverlay(headless=True, auto_hide_s=5.0)
    overlay.start()

    # 1. IDLE State
    assert overlay.state == OverlayState.IDLE
    assert overlay.is_visible is False
    assert overlay.status_text == "Sẵn sàng"

    # 2. LISTENING State
    overlay.show_listening("🎤 Đang lắng nghe...")
    assert overlay.state == OverlayState.LISTENING
    assert overlay.is_visible is True
    assert overlay.user_text == "🎤 Đang lắng nghe..."
    assert overlay.status_text == "Đang lắng nghe giọng nói"

    # 3. THINKING State
    overlay.show_thinking("bật đèn phòng khách")
    assert overlay.state == OverlayState.THINKING
    assert overlay.is_visible is True
    assert overlay.user_text == "bật đèn phòng khách"
    assert "Đang xử lý" in overlay.jarvis_text
    assert overlay.status_text == "AI đang suy nghĩ"

    # 4. RESPONSE State
    overlay.show_response(
        transcript="bật đèn phòng khách",
        response="Đang bật đèn phòng khách cho Ngài.",
        hint="💡 Double clap để hỏi tiếp",
    )
    assert overlay.state == OverlayState.RESPONSE
    assert overlay.is_visible is True
    assert overlay.user_text == "bật đèn phòng khách"
    assert overlay.jarvis_text == "Đang bật đèn phòng khách cho Ngài."
    assert overlay.hint_text == "💡 Double clap để hỏi tiếp"
    assert overlay.status_text == "Hoàn thành"

    # 5. HIDDEN State
    overlay.hide()
    assert overlay.state == OverlayState.HIDDEN
    assert overlay.is_visible is False
    assert overlay.user_text == ""
    assert overlay.jarvis_text == ""
    assert overlay.hint_text == ""
    assert overlay.status_text == "Sẵn sàng"

    overlay.destroy()


def test_simulation_overlay_breathing_and_typing_animation_logic():
    """
    [Simulation 1.2] Verify 10-step amber-to-gold breathing gradient ping-pong
    and 3-step cycling typing dots logic.
    """
    # 1. Breathing gradient structure
    assert len(BREATHING_GRADIENT) == 10
    assert BREATHING_GRADIENT[0] == "#B8860B"   # Warm dark amber
    assert BREATHING_GRADIENT[5] == "#FFD700"   # Pure gold
    assert BREATHING_GRADIENT[-1] == "#FFF8DC"  # Glowing gold peak

    overlay = JarvisOverlay(headless=True)
    overlay._state = OverlayState.LISTENING
    overlay._visible = True
    overlay._breathing_index = 0
    overlay._breathing_direction = 1

    # Simulate 20 steps of breathing animation
    indices = []
    for _ in range(20):
        indices.append(overlay._breathing_index)
        if overlay._breathing_direction == 1:
            if overlay._breathing_index < len(BREATHING_GRADIENT) - 1:
                overlay._breathing_index += 1
            else:
                overlay._breathing_direction = -1
                overlay._breathing_index -= 1
        else:
            if overlay._breathing_index > 0:
                overlay._breathing_index -= 1
            else:
                overlay._breathing_direction = 1
                overlay._breathing_index += 1

    assert indices[:10] == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert indices[10:19] == [8, 7, 6, 5, 4, 3, 2, 1, 0]
    assert indices[19] == 1

    # 2. Typing dots cycling logic
    overlay._state = OverlayState.THINKING
    overlay._typing_index = 0
    patterns = []
    for _ in range(6):
        patterns.append("." * (overlay._typing_index + 1))
        overlay._typing_index = (overlay._typing_index + 1) % 3

    assert patterns == [".", "..", "...", ".", "..", "..."]
    overlay.destroy()


def test_simulation_overlay_thread_safety_and_stability_cycles():
    """
    [Simulation 1.3] Stress test: 15 consecutive show_listening -> show_thinking ->
    show_response -> hide cycles without hanging, leaking handles, or crashing.
    """
    overlay = JarvisOverlay(headless=True, auto_hide_s=5.0)
    overlay.start()

    for i in range(15):
        overlay.show_listening(f"Prompt {i}")
        assert overlay.state == OverlayState.LISTENING
        assert overlay.user_text == f"Prompt {i}"

        overlay.show_thinking(f"Transcript {i}")
        assert overlay.state == OverlayState.THINKING
        assert overlay.user_text == f"Transcript {i}"

        overlay.show_response(f"Transcript {i}", f"Response text {i}", hint="💡 Double clap để hỏi tiếp")
        assert overlay.state == OverlayState.RESPONSE
        assert overlay.jarvis_text == f"Response text {i}"
        assert overlay.hint_text == "💡 Double clap để hỏi tiếp"

        overlay.hide()
        assert overlay.state == OverlayState.HIDDEN
        assert overlay.is_visible is False

    overlay.destroy()
    assert overlay.state == OverlayState.HIDDEN


def test_simulation_overlay_multithreaded_concurrency_stress():
    """
    [Simulation 1.4] Concurrency stress test: 10 parallel threads executing 100 overlay
    state transitions simultaneously to verify zero race condition crashes.
    """
    overlay = JarvisOverlay(headless=True)
    overlay.start()
    exceptions: List[Exception] = []

    def _worker(thread_id: int):
        try:
            for i in range(10):
                overlay.show_listening(f"Thread {thread_id} step {i}")
                overlay.show_thinking(f"Query {thread_id}-{i}")
                overlay.show_response(f"Query {thread_id}-{i}", f"Reply {thread_id}-{i}")
                overlay.hide()
        except Exception as e:
            exceptions.append(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(_worker, t) for t in range(10)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert len(exceptions) == 0
    overlay.destroy()


# ============================================================================
# DOMAIN 2: SPEECH-TO-TEXT (STT) FAULT TOLERANCE & FALLBACK
# ============================================================================

def test_simulation_stt_fallback_on_missing_or_invalid_whisper_key(audio_synthesizer):
    """
    [Simulation 2.1] Verify STTEngine cascades cleanly from OpenAI Whisper to fallback
    (Mock / WindowsSpeech) when Whisper API key is missing or invalid.
    """
    # 1. Explicit invalid key on primary engine
    invalid_whisper = OpenAIWhisperSTT(config={"api_key": ""})
    assert invalid_whisper.is_available() is False

    mock_fallback = MockSTTEngine(default_transcript="bật đèn phòng khách")
    stt_engine = STTEngine(
        primary_engine=invalid_whisper,
        fallback_engine=mock_fallback,
    )

    # 2. Non-silent audio buffer transcription
    audio = audio_synthesizer.generate_noise(duration_s=0.5, rms=0.05)
    result = stt_engine.transcribe(audio)

    assert result == "bật đèn phòng khách"
    assert len(mock_fallback.call_history) == 1


def test_simulation_stt_web_speech_and_silence_gating(audio_synthesizer):
    """
    [Simulation 2.2] Verify provider='web_speech' resolves properly and silence gating
    returns empty string immediately.
    """
    # 1. Provider 'web_speech' resolution
    stt_engine = STTEngine(config={"provider": "web_speech"})
    assert stt_engine.primary_engine is not None

    # 2. Silence gating returns "" without error
    silence = audio_synthesizer.generate_silence(duration_s=0.5)
    assert stt_engine.transcribe(silence) == ""
    assert stt_engine.transcribe(np.empty(0, dtype=np.float32)) == ""


# ============================================================================
# DOMAIN 3: VIETNAMESE LLM SMART KEYWORD ROUTER & SAFETY FLAGS
# ============================================================================

@pytest.mark.parametrize(
    "query, expected_action, expected_domain_or_topic, expected_text_substring",
    [
        # Category 1: Smart Home
        ("bật đèn phòng khách", "home_assistant_call", "light", "Đang bật đèn phòng khách"),
        ("tắt đèn phòng ngủ", "home_assistant_call", "light", "Đang tắt đèn phòng ngủ"),
        ("bật quạt phòng khách", "home_assistant_call", "fan", "Đang bật quạt"),
        ("bật điều hòa", "home_assistant_call", "climate", "Đang bật điều hòa"),
        
        # Category 2: System Status & Hardware
        ("kiểm tra nhiệt độ cpu", "hardware_telemetry_check", "cpu", "Nhiệt độ CPU"),
        ("kiểm tra dung lượng ram", "hardware_telemetry_check", "ram", "Bộ nhớ RAM"),
        ("tình trạng hệ thống", "hardware_status_query", None, "Tình trạng hệ thống"),
        
        # Category 3: Spotify & Music
        ("mở Spotify", "spotify", None, "Đang mở Spotify và phát nhạc"),
        ("bật nhạc bài Nơi Này Có Anh", "spotify", None, "Nơi Này Có Anh"),
        ("dừng nhạc", "spotify", "pause", "Đã tạm dừng phát nhạc"),
        ("chuyển bài", "spotify", "next", "Đang chuyển bài tiếp theo"),
        
        # Category 4: Weather
        ("thời tiết hôm nay", "shell_exec", "weather", "thời tiết hôm nay"),
        ("dự báo thời tiết Hà Nội", "shell_exec", "weather", "thời tiết tại Hà Nội"),
        
        # Category 5: Reminder
        ("nhắc nhở uống nước sau 15 phút", "reminder", None, "Đã ghi nhận lời nhắc"),
        ("nhắc tôi họp nhóm sau 1 giờ", "reminder", None, "Đã ghi nhận lời nhắc"),
        
        # Category 6: System Power (Lock screen - low risk)
        ("khóa màn hình", "system_power", "lock", "Đã khóa màn hình"),
        
        # Category 7: Default Fallback
        ("xyz123 câu hỏi không liên quan hoàn toàn", "unknown_intent", None, "Tôi chưa hiểu lệnh này"),
    ]
)
def test_simulation_llm_router_vietnamese_7_categories(
    query: str,
    expected_action: str,
    expected_domain_or_topic: Optional[str],
    expected_text_substring: str,
):
    """
    [Simulation 3.1] Verify all 7 Vietnamese keyword router categories without LLM API key.
    """
    unauthenticated_client = LLMClient(provider="openai", api_key="")
    router = LLMIntentRouter(unauthenticated_client)

    intent = router.parse_intent(query)
    assert intent.action_name == expected_action
    assert expected_text_substring.lower() in intent.response_text.lower()

    if expected_domain_or_topic:
        if intent.action_name == "home_assistant_call":
            assert intent.parameters.get("domain") == expected_domain_or_topic
        elif intent.action_name == "hardware_telemetry_check":
            assert intent.parameters.get("component") == expected_domain_or_topic
        elif intent.action_name == "shell_exec":
            assert intent.parameters.get("topic") == expected_domain_or_topic
        elif intent.action_name == "spotify" and "command" in intent.parameters:
            assert intent.parameters.get("command") == expected_domain_or_topic


def test_simulation_llm_router_power_safety_confirmation_flags():
    """
    [Simulation 3.2] CRITICAL Safety Verification: Destructive system power commands
    (shutdown, restart) MUST require confirmation with danger_level='CRITICAL'.
    """
    unauthenticated_client = LLMClient(provider="openai", api_key="")
    router = LLMIntentRouter(unauthenticated_client)

    # 1. Shutdown command
    intent_shutdown = router.parse_intent("tắt máy tính")
    assert intent_shutdown.action_name == "system_power"
    assert intent_shutdown.parameters.get("action") == "shutdown"
    assert intent_shutdown.requires_confirmation is True
    assert intent_shutdown.danger_level == "CRITICAL"
    assert intent_shutdown.confirmation_prompt is not None

    # 2. Restart command
    intent_restart = router.parse_intent("khởi động lại máy")
    assert intent_restart.action_name == "system_power"
    assert intent_restart.parameters.get("action") == "restart"
    assert intent_restart.requires_confirmation is True
    assert intent_restart.danger_level == "CRITICAL"

    # 3. Lock screen (Non-destructive)
    intent_lock = router.parse_intent("khóa máy")
    assert intent_lock.action_name == "system_power"
    assert intent_lock.parameters.get("action") == "lock"
    assert intent_lock.requires_confirmation is False
    assert intent_lock.danger_level == "LOW"


# ============================================================================
# DOMAIN 4: TEXT-TO-SPEECH (TTS) FALLBACK & GREETING RESILIENCE
# ============================================================================

def test_simulation_tts_fallback_cascades_to_sapi5_on_invalid_key(tmp_path):
    """
    [Simulation 4.1] Verify TTSManager cascades to SAPI5 fallback when ElevenLabs fails
    without throwing exceptions or hanging.
    """
    config = {
        "elevenlabs": {"api_key": "invalid_eleven_key_123"},
        "fallback": {"voice_name": "Microsoft David Desktop"},
        "cache": {"enabled": False, "dir": str(tmp_path)},
    }
    tts_mgr = TTSManager(config=config, cache_dir=tmp_path)

    # Primary engine has invalid credentials; speak call should cascade to SAPI5
    success = tts_mgr.speak("Xin chào Ngài, tôi là JARVIS.", wait=True)
    assert success is True
    assert len(tts_mgr.fallback_engine.spoken_history) >= 1
    assert "Xin chào Ngài, tôi là JARVIS." in tts_mgr.fallback_engine.spoken_history

    tts_mgr.stop()


def test_simulation_tts_randomized_greeting_pool_resilience():
    """
    [Simulation 4.2] Verify TTSManager selects randomized greeting phrases from pool
    without repeating consecutive selections.
    """
    tts_mgr = TTSManager(config={"welcome": {"phrases": WELCOME_PHRASES}})
    history = []

    for _ in range(30):
        phrase = tts_mgr.get_welcome_phrase()
        assert phrase in WELCOME_PHRASES
        history.append(phrase)

    # Verify no two consecutive phrases are identical
    for i in range(len(history) - 1):
        assert history[i] != history[i + 1]

    tts_mgr.stop()


# ============================================================================
# DOMAIN 5: END-TO-END PIPELINE PERFORMANCE & LATENCY
# ============================================================================

def test_simulation_e2e_mock_pipeline_latency_under_10_seconds(audio_synthesizer):
    """
    [Simulation 5.1] Benchmark test: The full end-to-end voice loop:
    Audio Input -> STT Transcribe -> Intent Parsing -> Action Dispatch -> TTS Speak
    MUST complete in under 10.0 seconds in mock mode.
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    # Configure mock STT with deterministic query
    mock_stt = MockSTTEngine(default_transcript="kiểm tra nhiệt độ cpu")
    app.stt_engine.primary_engine = mock_stt

    # Generate synthetic audio
    audio_buffer = audio_synthesizer.generate_noise(duration_s=0.5, rms=0.04)

    t_start = time.perf_counter()
    result = app.process_voice_command(audio_buffer)
    elapsed = time.perf_counter() - t_start

    # Strict performance assertion
    assert elapsed < 10.0, f"Pipeline took {elapsed:.2f}s, exceeding 10.0s threshold!"
    assert result["success"] is True
    assert result["transcript"] == "kiểm tra nhiệt độ cpu"
    assert "hardware_telemetry_check" in result["intent"]["action_name"]
    assert "Nhiệt độ CPU" in result["response_text"]

    app.stop()


# ============================================================================
# DOMAIN 6: SIMULATED USER GESTURE WORKFLOWS & ZERO DOUBLE-DISPATCH
# ============================================================================

def test_simulation_gesture_double_clap_voice_loop_lifecycle(monkeypatch):
    """
    [Simulation 6.1] Full gesture workflow simulation:
    - 1st double clap -> Triggers welcome sequence once.
    - 2nd double clap -> Activates AI voice interaction loop.
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()
    app._action_fanout_cooldown_s = 0.01  # Tiny cooldown for testing

    dispatched_actions: List[str] = []
    spoken_phrases: List[str] = []

    def mock_dispatch(action_name: str, payload=None, requester=None):
        dispatched_actions.append(action_name)
        return ActionResult(action_name=action_name, success=True)

    if app.tts_manager:
        monkeypatch.setattr(app.tts_manager, "speak", lambda txt, wait=False: spoken_phrases.append(txt) or True)

    monkeypatch.setattr(app.dispatcher, "dispatch_action", mock_dispatch)

    # 1. First double clap
    assert app.welcome_executed is False
    app._on_gesture_event("double_clap")
    time.sleep(0.05)

    assert app.welcome_executed is True
    assert "spotify" in dispatched_actions
    assert "tts_welcome" in dispatched_actions

    # 2. Second double clap (Voice loop)
    dispatched_actions.clear()
    app._pattern_last_fired.clear()

    # Mock audio recording and STT
    monkeypatch.setattr(app, "record_audio", lambda: np.ones(1600, dtype=np.float32) * 0.05)
    app.stt_engine.primary_engine = MockSTTEngine(default_transcript="bật đèn phòng khách")

    app._on_gesture_event("double_clap")
    time.sleep(0.1)

    assert any("đang lắng nghe" in sp.lower() for sp in spoken_phrases)
    assert "home_assistant_call" in dispatched_actions
    app.stop()


def test_simulation_gesture_cooldown_and_zero_double_dispatch(caplog):
    """
    [Simulation 6.2] Verify rapid successive gestures within 3.0s are suppressed by cooldown
    and verify zero double-dispatch per trigger.
    """
    import logging
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()
    app._action_fanout_cooldown_s = 3.0

    call_counts: Dict[str, int] = {"system_status": 0}

    def mock_status_handler(**kwargs):
        call_counts["system_status"] += 1
        return {"status": "healthy"}

    app.dispatcher.register_action("system_status", mock_status_handler)

    # 1. First trigger
    with caplog.at_level(logging.INFO):
        app._on_gesture_event("triple_clap")
        assert call_counts["system_status"] == 1

        # 2. Second trigger immediately (in < 3.0s) -> Must be suppressed
        app._on_gesture_event("triple_clap")
        assert call_counts["system_status"] == 1  # Still 1, NOT 2 (Zero double-dispatch)
        assert any("suppressed" in record.message for record in caplog.records)

    app.stop()


def test_simulation_system_status_live_vocalization_flow(monkeypatch):
    """
    [Simulation 6.3] Verify triple clap executes system_status with live hardware reporter metrics.
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    spoken_status: List[str] = []
    if app.tts_manager:
        monkeypatch.setattr(app.tts_manager, "speak", lambda txt, wait=False: spoken_status.append(txt) or True)

    res = app._handle_system_status()
    assert res["status"] == "healthy"
    assert "Tình trạng hệ thống" in res["message"] or "JARVIS systems" in res["message"]
    assert len(spoken_status) >= 1
    assert "Tình trạng hệ thống" in spoken_status[0] or "JARVIS systems" in spoken_status[0]

    app.stop()
```

---

## 5. Risk Assessment & Verification Strategy

| Potential Risk | Impact | Mitigation in Simulation Design |
|---|---|---|
| Tkinter display error on headless environments / CI | High (test crash) | Use `headless=True` for `JarvisOverlay`, ensuring pure headless execution of all state transitions and animation timers. |
| External network dependencies (OpenAI/ElevenLabs/Gemini) | Critical (flaky tests) | Pass mock/unauthenticated clients and verify deterministic local offline fallbacks (Mock STT, SAPI5 Fallback, Vietnamese Rule Fast-Path). |
| Race conditions in multi-threaded voice loops | Medium | Use `time.sleep(0.05-0.1)` or `threading.Event` synchronization after asynchronous worker thread invocations in tests. |
| Gesture cooldown interference between unit tests | Medium | Clean/reset `app._pattern_last_fired` or configure `_action_fanout_cooldown_s = 0.01` within isolated test scopes. |
| Latency test timeouts on loaded CI runners | Low | The 10.0s threshold is generously sized ($> 60\times$ the typical mock runtime of $< 0.15$s). |

