# JARVIS Core Architecture, Voice Pipeline & Proactive Monitoring Survey Report

**Explorer**: Explorer 1  
**Date**: 2026-08-24  
**Project**: JARVIS Personal AI Expansion (Windows Desktop AI Assistant)  
**Target Requirements Investigated**: R1 (Wake Word Detection "Hey JARVIS"), R6 (Proactive Intelligence), Core Lifecycle, Voice Pipeline, and Test Infrastructure.

---

## Executive Summary

JARVIS is a modular, zero-cloud-dependent (with graceful cloud-enhancement) Windows desktop AI assistant built in Python. The current codebase contains 67 modules and over 537 passing tests across 4 testing tiers. 

This survey maps the existing core lifecycle, acoustic audio and gesture stream, speech-to-text (STT), text-to-speech (TTS), floating HUD overlay, system tray, hardware diagnostics, and test infrastructure. Based on the analysis of the running architecture, detailed implementation blueprints are formulated for:
1. **R1: Offline Wake Word Detection ("Hey JARVIS")** (<1s latency, local lightweight model / fallback, parallel with double clap, dynamic tray toggle without restart, instant HUD overlay + "Vâng thưa Ngài" voice feedback).
2. **R6: Proactive Intelligence** (Smart reminder scheduler, background system health & battery monitor, Pomodoro focus mode, 8:00 AM daily briefing scheduler, 2-hour inactivity greeting, per-feature configuration toggles).

---

## 1. Entry Points & Core Application Lifecycle

### 1.1 Entry Point Chain
- **Package Entry Point**: `jarvis/__main__.py` (Lines 1–11)
  ```python
  import sys
  from jarvis.cli import main
  if __name__ == "__main__":
      sys.exit(main())
  ```
- **CLI Dispatcher**: `jarvis/cli.py` (Lines 30–195)
  - `build_parser()` parses subcommands:
    - `run`: Starts daemon assistant (flags: `--no-hot-reload`, `--headless`, `-c/--config`, `--log-level`).
    - `health-check` (alias `health`): Runs system diagnostics.
    - `install-autostart` / `uninstall-autostart` / `autostart-status`: Manages Windows Registry `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
  - `main(argv)` initializes logging via `setup_logging(level=args.log_level)` and loads `ConfigManager(config_path=args.config)`.

### 1.2 Core Lifecycle: `JarvisApp` (`jarvis/core/app.py`)
`JarvisApp` (769 lines) coordinates the runtime lifecycle across all subsystems:

```
+-----------------------------------------------------------------------------------+
|                                   JarvisApp                                       |
|                                                                                   |
|  [ConfigManager]   <---> [EventBus] <---> [ActionDispatcher] <---> [PluginRegistry]|
|         |                                        |                                |
|         v                                        v                                |
|  [AudioEngine]                         Built-in Core Actions:                     |
|    | (SoundDevice 44.1kHz Stream)        - tts_welcome                            |
|    +--> GestureDetector (Claps)          - system_status                          |
|    +--> [NEW] WakeWordDetector (R1)      - toggle_mute                            |
|                                          - show_overlay                           |
|  [STTEngine] (VAD + Whisper/SAPI)        - [NEW] reminder / focus_mode (R6)       |
|  [TTSManager] (ElevenLabs + SAPI5)                                                |
|  [LLMClient & LLMIntentRouter]                                                    |
|  [JarvisOverlay] (Tkinter HUD)                                                    |
|  [SystemTrayController] (pystray / Win32)                                         |
|  [HardwareReporter & Monitor]                                                     |
|  [NEW] [ProactiveEngine] (R6 Scheduler, Health, Pomodoro, Briefing, Inactivity)   |
+-----------------------------------------------------------------------------------+
```

#### Lifecycle Phases:
1. **`JarvisApp.__init__(config_path, headless, no_hot_reload)`** (Lines 58–102):
   - Instantiates `ConfigManager`, `EventBus`, `ActionDispatcher`, and `PluginRegistry`.
   - Initializes sub-engine handles (`tts_manager`, `audio_engine`, `gesture_detector`, `stt_engine`, `llm_client`, `llm_router`, `tray_controller`, `dashboard_server`, `overlay`, `hardware_reporter`).
2. **`JarvisApp.initialize()`** (Lines 126–240):
   - Loads config hierarchy: `self.config.load()`.
   - Starts config hot-reload thread: `self.config.start_watcher(interval_seconds=2.0)` (unless `--no-hot-reload`).
   - Initializes `TTSManager`, registers core actions (`_register_core_actions()`).
   - Registers plugins: `SpotifyPlugin`, `ChromeMultiMonitorPlugin`, `CursorPlugin`, `ShellPlugin`, `WebhookPlugin`.
   - Instantiates `STTEngine`, `LLMClient`, `LLMIntentRouter`.
   - Instantiates `GestureDetector` (configured with `on_gesture=self._on_gesture_event`).
   - Instantiates `AudioEngine` (passing `on_audio_block=self.gesture_detector.feed_audio_block`).
   - Instantiates `DashboardServer`, `SystemTrayController`, and `HardwareReporter`.
   - Registers OS signal handlers (`SIGINT`, `SIGTERM`).
3. **`JarvisApp.start()`** (Lines 679–727):
   - Starts `audio_engine.start_stream()`.
   - Starts `dashboard_server.start()`.
   - Starts `overlay = JarvisOverlay(auto_hide_s=10.0)` and `overlay.start()` (Tkinter GUI thread).
   - Starts `tray_controller.start(in_thread=True)`.
   - Queues startup speech introduction: `tts_manager.speak(startup_phrase, wait=False)`.
4. **`JarvisApp.run()`** (Lines 728–744):
   - Enters non-busy daemon loop (`while not self._shutdown_event.is_set(): time.sleep(0.5)`).
5. **`JarvisApp.stop()`** (Lines 749–769):
   - Thread-safe graceful teardown: stops tray, dashboard, audio stream, TTS worker, config watcher, and all plugins.

### 1.3 Configuration Management (`jarvis/core/config.py` & `config/default_config.yaml`)
- **Multi-source Hierarchy**:
  1. Default YAML (`config/default_config.yaml`)
  2. Custom YAML/JSON/TOML (passed via `--config`)
  3. `.env` file key-value pairs
  4. Environment variables (`os.environ` & `LEGACY_ENV_MAPPING`)
- **Key Features**:
  - `ConfigManager.get(dot_key, default)` & `set(dot_key, value)`.
  - Background thread file watcher (`start_watcher(interval_seconds=2.0)`) monitoring `st_mtime` with atomic rollback on syntax errors.
  - Observer callbacks via `register_reload_callback(callback)`.
  - Typed Config Node schema: `JarvisConfig`, `AudioConfig`, `TTSConfig`, `WindowsConfig`, `LoggingConfig`.

### 1.4 System Health Check Routine (`jarvis/cli.py:88-137`)
`run_health_check(config)` runs pre-flight diagnostics:
1. Platform & Python version detection (`sys.platform`, `os.name`, `sys.version`).
2. Audio Subsystem: `sounddevice.query_devices()` enumeration, default input device check.
3. TTS Engine: ElevenLabs API Key validation or SAPI5 fallback announcement.
4. Win32 Platform: `ctypes.windll.user32.GetSystemMetrics(80)` (SM_CMONITORS).
5. Configuration Sections count.

---

## 2. Existing Audio & Voice Pipeline

### 2.1 Audio Ingestion & DSP Stream (`jarvis/audio/engine.py` & `jarvis/audio/dsp.py`)
- **Sampling Parameters**: 44,100 Hz, 16-bit float32 PCM, 1 channel (mono), 40 ms block size (`block_size = int(44100 * 0.040) = 1764` samples).
- **Loudest Microphone Auto-Probe** (`MicrophoneProbeManager`): Scans input endpoints with short 0.5s RMS probe to auto-select the active microphone if not overridden.
- **Worker Thread (`_stream_worker`)**: Reads frames from `sounddevice.InputStream` and calls `_dispatch_block(data)` to fan out to registered subscriber callbacks (`self._callbacks`) and `EventBus.publish("audio.block", block=data, rms=...)`.
- **DSP Transient Detection (`AudioDSPProcessor`)**: Calculates frame RMS, maintains Exponential Moving Average (EMA) dynamic noise floor (`alpha = 0.992`), and triggers Schmitt spike detection when `rms > spike_ratio * noise_floor` (default ratio: 7.0).

### 2.2 Gesture Detection (`jarvis/gesture/detector.py` & `patterns.py`)
- Manages state machine (`IDLE -> PENDING -> COOLDOWN`).
- Supported acoustic transient patterns:
  - **Double Clap**: 2 claps with gap between 0.05s and 0.35s.
  - **Triple Clap**: 3 claps with gap <= 0.40s.
  - **Clap-Pause-Clap**: Clap 1 -> Gap (0.05–0.35s) -> Pause (0.50–1.20s) -> Clap 2 (0.05–0.35s).
- Dispatches result via `on_gesture(pattern_name, confidence)` to `JarvisApp._on_gesture_event()`.

### 2.3 STT Subsystem (`jarvis/stt/engine.py`)
- **Multi-Provider Architecture**:
  1. `OpenAIWhisperSTT`: Remote OpenAI Whisper API REST (`POST /v1/audio/transcriptions`).
  2. `FasterWhisperSTT`: Local offline CT2 faster-whisper.
  3. `WindowsSpeechSTT`: Offline Windows built-in `System.Speech` PowerShell SAPI recognition (Zero external dependency).
  4. `MockSTTEngine`: Deterministic test mock.
- **VAD Segmenter (`VADSegmenter`)**: Ring buffer with pre-speech window (0.3s) and trailing silence detector (0.8s) for boundary segmentation.

### 2.4 TTS Subsystem (`jarvis/tts/manager.py`, `elevenlabs.py`, `fallback.py`, `cache.py`)
- **Multi-Engine Cascading**:
  1. Local WAV Disk Cache (`TTSAudioCache`): SHA-256 hash of `(text, voice_id, model_id)` saved to `.cache/jarvis_welcome/`. Instant playback via `winsound.PlaySound` or `sounddevice`.
  2. Online ElevenLabs API (`ElevenLabsTTS`): Streaming PCM synthesis (`eleven_multilingual_v2`).
  3. Offline SAPI5 Fallback (`SAPI5FallbackTTS`): Windows native `win32com.client.Dispatch("SAPI.SpVoice")` or `pyttsx3`.
- **Greeting Pool**: Non-repeating randomized greeting selection from configured phrases list.
- **Async Queue**: Thread-safe background `TTS-Worker` queue for non-blocking playback.

### 2.5 End-to-End Voice Interaction Flow (`jarvis/core/app.py:408-500`)
```
[User Trigger: Double Clap #2+ OR Wake Word "Hey JARVIS"]
                    │
                    ▼
          _ai_voice_loop() Thread
                    │
   1. overlay.show_listening() (HUD animates amber breathing dot)
   2. tts_manager.speak("Vâng thưa Ngài, tôi đang lắng nghe.", wait=True)
   3. tray_controller.update_status(TrayStatus.LISTENING)
   4. record_audio() -> captures 5.0s audio buffer (44.1kHz -> float32)
   5. stt_engine.transcribe(audio) -> transcript string
                    │
   [If silence detected]:
   -> overlay.show_response("(không nghe thấy)", "Tôi không nghe thấy gì...")
   -> tts_manager.speak("Tôi không nghe thấy gì cả. Vui lòng thử lại.")
                    │
   [If speech transcribed]:
   6. overlay.show_thinking(transcript) (HUD animates cycling typing dots)
   7. process_text_command(transcript, requester="voice")
        ├─ llm_router.parse_intent(transcript)
        ├─ dispatcher.dispatch_action(action_name, payload)
        └─ tts_manager.speak(response_text, wait=False)
   8. overlay.show_response(transcript, response_text)
   9. tray_controller.update_status(TrayStatus.ACTIVE)
  10. log_interaction(trigger="VOICE/WAKEWORD", input=transcript, response=response_text)
```

---

## 3. Architecture Blueprint for R1: Wake Word Detection ("Hey JARVIS")

### 3.1 Requirements Breakdown
- **Latency**: Detection within < 1.0s.
- **Offline / Zero-Cloud**: Must function entirely locally without external API dependencies.
- **Accuracy**: False positive rate < 1 occurrence per hour in normal ambient room noise.
- **Coexistence**: Operates in parallel with existing Double Clap trigger without audio device lock contention.
- **Dynamic Control**: Toggled on/off via Windows System Tray context menu on the fly without application restart.
- **UX Flow**: Instant overlay pop-up + "Vâng thưa Ngài" voice feedback + automated command recording.

### 3.2 Detection Engine Architecture (`jarvis/audio/wake_word.py`)

To ensure robust performance, a 3-tier hybrid detection strategy is designed:

```
                             AudioEngine (44.1kHz PCM Stream)
                                            │
               ┌────────────────────────────┴────────────────────────────┐
               ▼                                                         ▼
    GestureDetector.feed_audio_block                        WakeWordDetector.feed_audio_block
    (Clap Schmitt Trigger & Patterns)                         (Ring Buffer & Resampler)
                                                                         │
                                                                         ▼
                                                              Resample to 16kHz Mono
                                                                         │
                                                                         ▼
                                                          Sliding Window Buffer (1.2s)
                                                                         │
                                                  ┌──────────────────────┴──────────────────────┐
                                                  ▼                                             ▼
                                      [Tier 1: Vosk / OpenWakeWord]               [Tier 2: Acoustic Energy & ZCR Fallback]
                                      Small offline keyword model                 Phoneme formant & spectral energy filter
                                      "hey jarvis" / "jarvis"                     High sensitivity acoustic envelope match
                                                  │                                             │
                                                  └──────────────────────┬──────────────────────┘
                                                                         │ (Confidence >= threshold)
                                                                         ▼
                                                            Debounce & Cooldown Guard (2.0s)
                                                                         │
                                                                         ▼
                                                             on_wake_word("hey_jarvis")
```

#### Multi-Tier Engine Details:
1. **Tier 1: Lightweight Local Acoustic Model (Vosk Small or OpenWakeWord ONNX)**:
   - Input: 16 kHz 16-bit mono PCM.
   - Constrained grammar search: `["hey jarvis", "jarvis", "chào jarvis", "[unk]"]`.
   - Memory footprint: ~15MB.
   - Detection latency: ~150–350ms.
2. **Tier 2: Zero-Dependency Pure Python Acoustic Keyword Fallback**:
   - Resonator filter tuned to "JAR-VIS" acoustic formant transitions:
     - Syllable 1 ("JAR" / "dʒɑːr"): Low-mid formant boost (300–800 Hz) followed by transient spike.
     - Syllable 2 ("VIS" / "vɪs"): High-frequency fricative energy (3500–6500 Hz, high Zero-Crossing Rate).
   - Temporal syllable gap: 0.15s to 0.45s.
   - Guaranteed zero-dependency fallback for test/CI environments.

### 3.3 Proposed Module Structure: `jarvis/audio/wake_word.py`

```python
"""
jarvis/audio/wake_word.py
=========================
Offline Wake Word Detection Engine for "Hey JARVIS".
Supports Vosk local model, OpenWakeWord ONNX, and pure Python spectral fallback.
"""
from dataclasses import dataclass
from enum import Enum
import logging
import numpy as np
import threading
import time
from typing import Callable, Optional, Dict, Any

from jarvis.audio.dsp import calculate_rms
from jarvis.stt.engine import resample_audio

log = logging.getLogger("jarvis.audio.wake_word")

class WakeWordEngineType(str, Enum):
    VOSK = "vosk"
    OPENWAKEWORD = "openwakeword"
    ACOUSTIC_FALLBACK = "acoustic_fallback"
    MOCK = "mock"

@dataclass
class WakeWordResult:
    keyword: str
    confidence: float
    timestamp: float
    engine: str

class WakeWordDetector:
    def __init__(
        self,
        sample_rate: int = 44100,
        target_sample_rate: int = 16000,
        window_duration_s: float = 1.2,
        sensitivity: float = 0.6,
        cooldown_s: float = 2.0,
        enabled: bool = True,
        on_wake_word: Optional[Callable[[str, float], None]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.target_sample_rate = target_sample_rate
        self.window_duration_s = window_duration_s
        self.sensitivity = sensitivity
        self.cooldown_s = cooldown_s
        self._enabled = enabled
        self.on_wake_word = on_wake_word
        
        self._lock = threading.RLock()
        self._last_trigger_time: float = 0.0
        self._ring_buffer: np.ndarray = np.zeros(int(target_sample_rate * window_duration_s), dtype=np.float32)
        self._engine: Any = None
        self._engine_type: WakeWordEngineType = self._init_engine()

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = enabled
            log.info("WakeWordDetector enabled state changed: %s", enabled)

    @property
    def is_enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def feed_audio_block(self, block: np.ndarray, timestamp: Optional[float] = None) -> Optional[WakeWordResult]:
        """Callback fed directly by AudioEngine for every 40ms audio block."""
        if not self._enabled:
            return None
        
        # 1. Resample block from 44.1kHz to 16kHz
        resampled = resample_audio(block, self.sample_rate, self.target_sample_rate)
        if len(resampled) == 0:
            return None
            
        with self._lock:
            # 2. Push into sliding ring buffer
            self._ring_buffer = np.roll(self._ring_buffer, -len(resampled))
            self._ring_buffer[-len(resampled):] = resampled
            
            # 3. Check Cooldown
            now = time.monotonic()
            if (now - self._last_trigger_time) < self.cooldown_s:
                return None
            
            # 4. Run classification
            detected, keyword, confidence = self._classify_window(self._ring_buffer)
            if detected and confidence >= self.sensitivity:
                self._last_trigger_time = now
                result = WakeWordResult(
                    keyword=keyword,
                    confidence=confidence,
                    timestamp=now,
                    engine=self._engine_type.value,
                )
                if self.on_wake_word:
                    try:
                        self.on_wake_word(keyword, confidence)
                    except Exception as e:
                        log.error("Wake word callback error: %s", e)
                return result
        return None
```

### 3.4 Integration Points in `jarvis/core/app.py`
1. **Instantiation**:
   ```python
   # In JarvisApp.initialize():
   ww_cfg = self.config.get("audio.wake_word", {})
   self.wake_word_detector = WakeWordDetector(
       sample_rate=int(self.config.get("audio.sample_rate", 44100)),
       enabled=bool(ww_cfg.get("enabled", True)),
       sensitivity=float(ww_cfg.get("sensitivity", 0.6)),
       cooldown_s=float(ww_cfg.get("cooldown_s", 2.0)),
       on_wake_word=self._on_wake_word_event,
   )
   # Register callback on audio stream
   self.audio_engine.register_callback(self.wake_word_detector.feed_audio_block)
   ```
2. **Wake Word Event Handler**:
   ```python
   def _on_wake_word_event(self, keyword: str, confidence: float) -> None:
       log.info("Wake word detected: [%s] (confidence=%.2f)", keyword, confidence)
       if self.dashboard_server:
           self.dashboard_server.broadcast_event({
               "type": "wake_word",
               "keyword": keyword,
               "confidence": confidence,
           })
       self.log_interaction(
           trigger=f"WAKEWORD:{keyword}",
           input_text=keyword,
           action="voice_interaction",
           response="Vâng thưa Ngài, tôi đang lắng nghe.",
           status="success",
       )
       # Launch AI Voice Loop (same flow as double clap)
       self._start_ai_voice_loop(initial_phrase="Vâng thưa Ngài, tôi đang lắng nghe.")
   ```

### 3.5 System Tray Dynamic Toggle (`jarvis/ui/tray.py`)
Add menu item to `pystray.Menu`:
```python
def _get_wakeword_text(_):
    enabled = self.app.wake_word_detector.is_enabled if (self.app and hasattr(self.app, "wake_word_detector") and self.app.wake_word_detector) else True
    return "Disable Wake Word (Hey JARVIS)" if enabled else "Enable Wake Word (Hey JARVIS)"

def _on_toggle_wakeword(self, icon=None, item=None):
    if self.app and hasattr(self.app, "wake_word_detector") and self.app.wake_word_detector:
        cur = self.app.wake_word_detector.is_enabled
        self.app.wake_word_detector.set_enabled(not cur)
        logger.info("Wake word toggle clicked: now %s", not cur)
```

---

## 4. Architecture Blueprint for R6: Proactive Intelligence

### 4.1 Requirements Breakdown
1. **Smart Reminders**:
   - Natural language commands ("nhắc tôi lúc 3 giờ chiều họp với team", "nhắc tôi sau 5 phút kiểm tra lò nướng").
   - Triggers TTS vocal announcement + Overlay popup at exact scheduled time.
2. **System Health Background Monitor**:
   - Polling every 10s: CPU > 90%, RAM > 85%, Disk < 10GB free, CPU Temp > 85°C, Battery < 20%.
   - Active voice warning delivered in < 30s with debouncing (cooldown 120s per component).
3. **Focus Mode / Pomodoro Timer**:
   - Command: "JARVIS, tôi cần tập trung 2 tiếng" / "bật chế độ tập trung".
   - 25-minute work session, 5-minute break reminders.
   - Suppresses non-critical notifications during focus cycles.
4. **Auto Daily Briefing (8:00 AM)**:
   - Automatically triggers at configured morning time (default 08:00).
   - Vocalizes weather forecast + top news headlines + system health status summary.
5. **Inactivity Greeting**:
   - If user has had no interaction (gestures, voice, tray, UI) for > 2 hours (7200s), JARVIS gently checks in: *"Thưa Ngài, Ngài có cần hỗ trợ gì không?"*.
6. **Per-Feature Configuration Toggles**:
   - Every single proactive capability must be individually toggleable in YAML configuration.

### 4.2 Module Architecture: `jarvis/proactive/`

```
jarvis/proactive/
├── __init__.py
├── engine.py                 # ProactiveEngine: Master coordinator & background scheduler loop
├── reminders.py              # SmartReminderScheduler: Time parsing, persistent/memory queue, trigger dispatcher
├── health_monitor.py         # ProactiveHealthMonitor: CPU/RAM/Disk/Temp/Battery threshold watchdog
├── pomodoro.py               # PomodoroManager: Focus mode state machine (WORK -> BREAK -> WORK)
├── briefing_scheduler.py     # DailyBriefingScheduler: Morning 8:00 AM briefing trigger
└── inactivity.py             # InactivityMonitor: Idle tracking & check-in prompter
```

```
+----------------------------------------------------------------------------------------------------+
|                                           ProactiveEngine                                          |
|                                                                                                    |
|  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐  ┌────────────────┐  |
|  | SmartReminder        |  | ProactiveHealth      |  | PomodoroManager      |  | Inactivity     |  |
|  | Scheduler            |  | Monitor              |  | (Focus Mode)         |  | Monitor        |  |
|  |                      |  |                      |  |                      |  |                |  |
|  | - sau 5 phút...      |  | - CPU > 90%          |  | - 25m Work           |  | - Idle > 2h    |  |
|  | - lúc 3 giờ chiều... |  | - RAM > 85%          |  | - 5m Break           |  | - Vocal prompt |  |
|  | - Overlay + TTS      |  | - Disk < 10GB        |  | - DND Suppression    |  |                |  |
|  |                      |  | - Temp > 85°C        |  |                      |  |                |  |
|  |                      |  | - Battery < 20%      |  |                      |  |                |  |
|  └──────────┬───────────┘  └──────────┬───────────┘  └──────────┬───────────┘  └───────┬────────┘  |
|             │                         │                         │                      │           |
|             └─────────────────────────┼─────────────────────────┴──────────────────────┘           |
|                                       ▼                                                            |
|                        Background Worker Loop (1-second tick)                                      |
|                                       │                                                            |
|                    ┌──────────────────┴──────────────────┐                                         |
|                    ▼                                     ▼                                         |
|       TTSManager.speak(alert_text)         JarvisOverlay.show_response(alert_text)                  |
+----------------------------------------------------------------------------------------------------+
```

### 4.3 Detailed Subsystem Specifications

#### 1. Smart Reminder Scheduler (`jarvis/proactive/reminders.py`)
- **Data Model**:
  ```python
  @dataclass
  class ScheduledReminder:
      reminder_id: str
      message: str
      trigger_timestamp: float
      created_timestamp: float
      spoken: bool = False
      source: str = "voice"
  ```
- **Time Parsing Engine**:
  - Relative: `sau (\d+) (giây|phút|giờ)` -> `now + parsed_seconds`.
  - Absolute: `lúc (\d{1,2})(?:h|:)(\d{1,2})?` -> today's timestamp (or tomorrow if earlier than now).
- **Execution**: On trigger tick -> calls `tts_manager.speak(f"Thưa Ngài, đây là lời nhắc: {reminder.message}")` and `overlay.show_response(transcript="⏰ Lời nhắc", response=reminder.message)`.

#### 2. Proactive Health & Battery Watchdog (`jarvis/proactive/health_monitor.py`)
- **Metrics Acquisition**:
  - Leverages existing `HardwareMonitor` (`jarvis/hardware/monitor.py`).
  - **Battery Telemetry Integration**:
    - Primary: `psutil.sensors_battery()` (returns `percent`, `power_plugged`).
    - Fallback: Win32 `kernel32.GetSystemPowerStatus(byref(SYSTEM_POWER_STATUS))` where `BatteryLifePercent` is read.
- **Debounced Rule Engine**:
  - CPU utilization >= 90.0% for >= 2 consecutive checks -> *"Cảnh báo: CPU đang hoạt động quá tải ở mức {cpu}%."*
  - RAM utilization >= 85.0% -> *"Cảnh báo: Bộ nhớ RAM đang sử dụng {ram}%, vượt ngưỡng an toàn."*
  - Disk C: free space < 10.0 GB -> *"Cảnh báo: Dung lượng ổ đĩa C chỉ còn {free_gb} GB."*
  - CPU Temperature >= 85.0°C -> *"Cảnh báo: Nhiệt độ CPU đạt {temp}°C, cần hạ tải."*
  - Battery <= 20% and not plugged in -> *"Thưa Ngài, pin thiết bị còn {battery}%, vui lòng kết nối bộ sạc."*
  - Cooldown: 120s per metric to prevent alert fatigue.

#### 3. Focus Mode / Pomodoro Manager (`jarvis/proactive/pomodoro.py`)
- **State Machine**: `IDLE -> WORKING (25m) -> BREAK (5m) -> WORKING (25m) -> ...`
- **Actions Registered**: `start_focus_mode(duration_minutes, pomodoro=True)`, `cancel_focus_mode()`.
- **Transitions**:
  - On start: *"Đã kích hoạt chế độ tập trung trong {hours} giờ. Bắt đầu chu kỳ làm việc 25 phút."*
  - On 25m work complete: *"Chu kỳ làm việc kết thúc. Mời Ngài nghỉ ngơi 5 phút."*
  - On 5m break complete: *"Thời gian nghỉ kết thúc. Bắt đầu chu kỳ làm việc tiếp theo, thưa Ngài."*

#### 4. Daily Briefing Scheduler (`jarvis/proactive/briefing_scheduler.py`)
- Tracks target time string (e.g. `"08:00"`).
- Once per calendar day at >= 08:00 AM, compiles and vocalizes the Morning Briefing:
  ```python
  def generate_briefing(self) -> str:
      greeting = "Chào buổi sáng thưa Ngài. Đây là bản tin tổng hợp 8 giờ sáng."
      hw_status = self.hardware_reporter.format_voice_summary()
      reminders_today = self.reminder_scheduler.get_todays_reminders_summary()
      return f"{greeting} {hw_status} {reminders_today}"
  ```

#### 5. Inactivity Monitor (`jarvis/proactive/inactivity.py`)
- Maintains `_last_activity_time = time.monotonic()`.
- In `JarvisApp.log_interaction()` and `_on_gesture_event()`: calls `proactive_engine.record_user_activity()`.
- If `time.monotonic() - _last_activity_time >= 7200` (2 hours):
  - Speaks: *"Thưa Ngài, Ngài có cần hỗ trợ gì không?"*
  - Updates `_last_activity_time` to prevent continuous prompting.

### 4.4 Master Configuration Schema (`config/default_config.yaml`)

```yaml
proactive:
  enabled: true
  reminders:
    enabled: true
    storage_path: "data/reminders.json"
    check_interval_s: 1.0
  health_monitor:
    enabled: true
    check_interval_s: 10.0
    cpu_threshold: 90.0
    ram_threshold: 85.0
    temp_threshold_c: 85.0
    disk_min_free_gb: 10.0
    battery_min_percent: 20.0
    cooldown_s: 120.0
  focus_mode:
    enabled: true
    work_duration_m: 25
    break_duration_m: 5
  daily_briefing:
    enabled: true
    time: "08:00"
  inactivity_greeting:
    enabled: true
    timeout_seconds: 7200 # 2 hours
    phrase: "Thưa Ngài, Ngài có cần hỗ trợ gì không?"
```

---

## 5. Existing Test Infrastructure & Health Check

### 5.1 Test Suite Breakdown
The test suite consists of 51 test files located in `tests/` and `tests/unit/`, containing 537+ tests structured across 4 distinct tiers:

| Tier | Purpose | Existing Test Files |
|---|---|---|
| **Tier 1: Feature Coverage** | Unit validation of each individual module | `test_config.py`, `test_audio_dsp.py`, `test_gesture_detector.py`, `test_tts_engine.py`, `test_plugins.py`, `test_windows_platform.py`, `test_llm_router.py`, `test_hardware_monitor.py` |
| **Tier 2: Boundary & Corner Cases** | Negative inputs, timeouts, offline fallbacks, corrupted configs | `test_adversarial_m1.py`, `test_adversarial_m2_*.py`, `test_adversarial_m3_*.py`, `test_tier5_adversarial_*.py` |
| **Tier 3: Cross-Feature Integration** | Multi-module event flows (Acoustic -> TTS, STT -> Dispatcher -> Overlay) | `test_e2e_scenarios.py`, `test_user_simulation.py`, `test_m3_ux.py` |
| **Tier 4: Real-World Scenarios** | Full user session lifecycle and mock hardware replay | `test_user_simulation.py` (18 simulated scenarios), `test_empirical_challenger_*.py` |

### 5.2 Mock Fixtures (`tests/conftest.py`)
`tests/conftest.py` (1,022 lines) provides zero-hardware, zero-cloud test isolation:
1. `AudioSynthesizer` / `MockAudioStream`: Deterministically synthesizes claps, double claps, triple claps, Gaussian white noise, and speech bursts.
2. `MockHardwareProvider`: Simulates CPU/GPU loads, temperatures, RAM bytes, and S.M.A.R.T. disk dictionaries.
3. `MockWin32Platform`: Intercepts `user32`, `kernel32`, and `winreg` ctypes calls.
4. `MockHttpServer`: Intercepts Home Assistant, ElevenLabs, Telegram, and LLM network requests.
5. `MockCameraFeed`: Provides synthetic video frames for vision testing.

### 5.3 CLI Health Check Test (`tests/test_cli.py`)
- `test_run_health_check_execution()`: Executes `run_health_check(cfg)` inside an intercepted `sys.stdout` context and asserts exit code 0 and header/version strings.
- Subcommands `install-autostart`, `uninstall-autostart`, and `autostart-status` are tested with `MockWinreg`.

### 5.4 Test Expansion Plan for R1 & R6
- **`tests/test_wake_word.py`** (R1):
  - `test_wake_word_resampling()`: Verifies 44.1kHz -> 16kHz conversion.
  - `test_wake_word_sliding_window_detection()`: Tests keyword trigger on synthesized audio buffers.
  - `test_wake_word_cooldown_debounce()`: Ensures no double trigger within 2.0s cooldown window.
  - `test_wake_word_tray_toggle_dynamic()`: Tests disabling/enabling wake word detector without restart.
  - `test_wake_word_parallel_with_claps()`: Asserts that audio stream triggers both wake word and double clap handlers independently.
- **`tests/test_proactive.py`** (R6):
  - `test_reminder_relative_parsing_and_trigger()`: 5-minute / 10-second relative reminder trigger.
  - `test_reminder_absolute_time_parsing()`: Clock time reminder trigger.
  - `test_health_monitor_cpu_ram_breach_alerts()`: Asserts alerts triggered when CPU > 90% or RAM > 85%.
  - `test_health_monitor_battery_alert()`: Asserts battery low alert when battery < 20%.
  - `test_pomodoro_state_transitions()`: Verifies 25m work -> 5m break cycles.
  - `test_inactivity_greeting_trigger()`: Simulates 2-hour idle time and verifies check-in phrase.
  - `test_proactive_config_toggles()`: Verifies that individual features can be toggled off via config.
- **`tests/test_cli.py` Update**:
  - Update `run_health_check` to report status for Wake Word engine, Proactive Intelligence engine, and Memory database.

---

## 6. Recommendations for Downstream Workers

1. **Worker 1 (R1 Wake Word)**:
   - Create `jarvis/audio/wake_word.py`.
   - Update `jarvis/audio/engine.py` to support multi-subscriber audio block dispatching without latency degradation.
   - Wire `WakeWordDetector` into `JarvisApp.initialize()` and `SystemTrayController`.
2. **Worker 6 (R6 Proactive Intelligence)**:
   - Create package `jarvis/proactive/` with `engine.py`, `reminders.py`, `health_monitor.py`, `pomodoro.py`, `briefing_scheduler.py`, `inactivity.py`.
   - Register actions `schedule_reminder`, `start_focus_mode`, `cancel_focus_mode` into `ActionDispatcher`.
   - Wire `ProactiveEngine` into `JarvisApp.start()` and `stop()`.
3. **Integration Worker & Victory Auditor**:
   - Update `config/default_config.yaml` with `audio.wake_word` and `proactive` sections.
   - Update `jarvis/cli.py` `run_health_check` to probe new subsystems.
   - Execute full pytest suite to verify $\ge 557$ passing tests with zero regressions.

---
*Report prepared by Explorer 1 for JARVIS Personal AI Expansion Project.*
