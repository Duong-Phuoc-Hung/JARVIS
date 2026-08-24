# Implementation Blueprint: Milestone M1 (Voice AI Pipeline Bug Fixes & Stabilization)

**Author**: Explorer M1_1  
**Date**: 2026-08-22  
**Target Milestone**: M1 (Voice AI Pipeline Bug Fixes & Stabilization)  
**Primary Files**:
- `jarvis/core/app.py`
- `jarvis/gesture/patterns.py`
- `config/default_config.yaml`
- `jarvis/hardware/reporter.py`

---

## 1. Executive Summary & Objective Mapping

This document provides the exact code modifications, architectural blueprints, and verification test specifications required for Milestone M1.

| Item | Requirement | Target File(s) | Current State | Target State |
|---|---|---|---|---|
| **1** | Re-route `clap_pause_clap` | `jarvis/core/app.py`<br>`jarvis/gesture/patterns.py` | Dispatches `toggle_mute` hardcoded | Dispatches `show_overlay` (matching `default_config.yaml`) |
| **2** | Decouple audio recording in voice loop | `jarvis/core/app.py` | Hardcoded `sounddevice.rec()` blocks 5s in `_ai_voice_loop` | Dedicated `app.record_audio()` method with headless/mock fallback |
| **3** | Connect system status to HardwareReporter | `jarvis/core/app.py` | Returns static hardcoded string `"JARVIS systems operating normally..."` | Queries `HardwareReporter.format_voice_summary()` for real CPU/RAM metrics |
| **4** | Cooldown suppression logging level | `jarvis/core/app.py` | Logged at `log.debug` (invisible in default INFO log) | Elevated to `log.info` to satisfy acceptance criteria |

---

## 2. Detailed Technical Analysis & Blueprint

### 2.1 Item 1: Re-Route `clap_pause_clap` to `show_overlay`

#### Root Cause Analysis
In `jarvis/gesture/patterns.py:50`, the default pattern definition for `GestureType.CLAP_PAUSE_CLAP` registers `actions=["toggle_mute"]`. Furthermore, in `jarvis/core/app.py:411-416`, `_on_gesture_event` contains:
```python
if pattern_name == "clap_pause_clap":
    try:
        self.dispatcher.dispatch_action("toggle_mute", requester=RequesterContext.system())
    except Exception as e:
        log.error("toggle_mute action failed: %s", e)
    return
```
This contradicts `config/default_config.yaml:65` where `actions: ["show_overlay"]` is configured, and breaks the user expectation that a syncopated clap opens the floating chat interface.

#### Exact Code Changes

**File 1: `jarvis/gesture/patterns.py`**
```python
<<<<
        GestureType.CLAP_PAUSE_CLAP: GesturePatternConfig(
            name="clap_pause_clap",
            gesture_type=GestureType.CLAP_PAUSE_CLAP,
            enabled=True,
            min_gap_s=min_double_gap_s,
            max_gap_s=max_double_gap_s,
            pause_min_s=pause_min_s,
            pause_max_s=pause_max_s,
            cooldown_s=cooldown_s,
            actions=["toggle_mute"],
        ),
====
        GestureType.CLAP_PAUSE_CLAP: GesturePatternConfig(
            name="clap_pause_clap",
            gesture_type=GestureType.CLAP_PAUSE_CLAP,
            enabled=True,
            min_gap_s=min_double_gap_s,
            max_gap_s=max_double_gap_s,
            pause_min_s=pause_min_s,
            pause_max_s=pause_max_s,
            cooldown_s=cooldown_s,
            actions=["show_overlay"],
        ),
>>>>
```

**File 2: `jarvis/core/app.py`**
- Update docstring in `_on_gesture_event` (`app.py:258`):
```python
<<<<
        Triple clap        → System status report.
        Clap-pause-clap    → Toggle mute.
====
        Triple clap        → System status report.
        Clap-pause-clap    → Show chat overlay.
>>>>
```
- Update dispatch logic (`app.py:411-417`):
```python
<<<<
        # ------------------------------------------------------------------ #
        #  CLAP-PAUSE-CLAP — Toggle mic mute                                  #
        # ------------------------------------------------------------------ #
        if pattern_name == "clap_pause_clap":
            try:
                self.dispatcher.dispatch_action("toggle_mute", requester=RequesterContext.system())
            except Exception as e:
                log.error("toggle_mute action failed: %s", e)
            return
====
        # ------------------------------------------------------------------ #
        #  CLAP-PAUSE-CLAP — Show chat overlay                                #
        # ------------------------------------------------------------------ #
        if pattern_name == "clap_pause_clap":
            action_names = self.config.get("gesture.patterns.clap_pause_clap.actions", ["show_overlay"])
            for act in action_names:
                try:
                    self.dispatcher.dispatch_action(act, requester=RequesterContext.system())
                except Exception as e:
                    log.error("Action [%s] failed for pattern [clap_pause_clap]: %s", act, e)
            return
>>>>
```

---

### 2.2 Item 2: Decouple Audio Recording in `_ai_voice_loop`

#### Root Cause Analysis
In `jarvis/core/app.py:338-357`, `_ai_voice_loop` directly imports `sounddevice` and executes:
```python
import sounddevice as _sd
import numpy as _np
sample_rate = int(self.config.get("audio.sample_rate", 44100))
record_s = float(self.config.get("stt.timeout_s", 5.0))
audio_data = _sd.rec(
    int(record_s * sample_rate),
    samplerate=sample_rate,
    channels=1,
    dtype="float32",
)
_sd.wait()
audio_flat = audio_data.flatten()
transcript = self.stt_engine.transcribe(audio_flat)
```
This causes major test suite issues:
1. Every automated simulation test executing subsequent double-claps blocks for 5.0 seconds synchronously on audio hardware.
2. In headless/CI environments where PortAudio or a physical microphone is missing, `_sd.rec()` throws unhandled exceptions or hangs.
3. Tests cannot inject synthetic audio buffers into the live `_ai_voice_loop` without monkeypatching private C-extensions.

#### Exact Code Changes

**File: `jarvis/core/app.py`**
1. Add `record_audio` public method on `JarvisApp`:
```python
    def record_audio(
        self,
        duration_s: Optional[float] = None,
        sample_rate: Optional[int] = None,
    ) -> np.ndarray:
        """
        Captures an audio buffer from the microphone.
        Supports headless/mock fallback and can be cleanly overridden/mocked in tests.
        """
        sr = int(sample_rate or self.config.get("audio.sample_rate", 44100))
        dur = float(duration_s or self.config.get("stt.timeout_s", 5.0))

        if self.headless:
            # In headless or testing mode without audio hardware, return a brief silent buffer
            return np.zeros(int(sr * min(dur, 0.1)), dtype=np.float32)

        try:
            import sounddevice as _sd
            log.info("Recording voice command for %.1fs (sample_rate=%d)...", dur, sr)
            audio_data = _sd.rec(
                int(dur * sr),
                samplerate=sr,
                channels=1,
                dtype="float32",
            )
            _sd.wait()
            return audio_data.flatten()
        except Exception as e:
            log.warning("Microphone capture via sounddevice failed: %s. Returning silent buffer.", e)
            return np.zeros(int(sr * 0.1), dtype=np.float32)
```

2. Refactor `_ai_voice_loop` in `_on_gesture_event` (`app.py:336-395`):
```python
<<<<
                    # Record and transcribe
                    transcript = ""
                    if self.stt_engine:
                        try:
                            import sounddevice as _sd
                            import numpy as _np
                            sample_rate = int(self.config.get("audio.sample_rate", 44100))
                            record_s = float(self.config.get("stt.timeout_s", 5.0))
                            log.info("Recording voice command for %.1fs...", record_s)
                            audio_data = _sd.rec(
                                int(record_s * sample_rate),
                                samplerate=sample_rate,
                                channels=1,
                                dtype="float32",
                            )
                            _sd.wait()
                            audio_flat = audio_data.flatten()
                            transcript = self.stt_engine.transcribe(audio_flat)
                            log.info("Transcribed: '%s'", transcript)
                        except Exception as e:
                            log.error("STT recording/transcription failed: %s", e)

                    if not transcript or not transcript.strip():
                        if self.overlay:
                            self.overlay.show_response("(không nghe thấy)", "Tôi không nghe thấy gì. Vui lòng thử lại.")
                        if self.tts_manager:
                            self.tts_manager.speak("Tôi không nghe thấy gì cả. Vui lòng thử lại.", wait=False)
                        if self.tray_controller:
                            self.tray_controller.update_status(TrayStatus.ACTIVE)
                        return

                    # Show "thinking" state in overlay
                    if self.overlay:
                        self.overlay.show_thinking(transcript)

                    # Send to LLM and get response
                    response_text = ""
                    if self.llm_router:
                        try:
                            result = self.process_text_command(transcript, requester="voice")
                            response_text = result.get("response_text", "")
                        except Exception as e:
                            log.error("LLM processing failed: %s", e)
                            response_text = f"Xin lỗi, tôi gặp lỗi khi xử lý lệnh: {e}"
                    else:
                        response_text = f"Tôi nghe thấy: {transcript}. Nhưng LLM chưa được cấu hình."

                    # Update overlay with final response
                    if self.overlay:
                        self.overlay.show_response(transcript, response_text)

                    # Speak response
                    if response_text and self.tts_manager and not self.llm_router:
                        self.tts_manager.speak(response_text, wait=False)

                    if self.tray_controller:
                        from jarvis.ui.tray import TrayStatus
                        self.tray_controller.update_status(TrayStatus.ACTIVE)
====
                    # Record and transcribe
                    transcript = ""
                    if self.stt_engine:
                        try:
                            audio_flat = self.record_audio()
                            transcript = self.stt_engine.transcribe(audio_flat)
                            log.info("Transcribed: '%s'", transcript)
                        except Exception as e:
                            log.error("STT recording/transcription failed: %s", e)

                    if not transcript or not transcript.strip():
                        if self.overlay:
                            self.overlay.show_response("(không nghe thấy)", "Tôi không nghe thấy gì. Vui lòng thử lại.")
                        if self.tts_manager:
                            self.tts_manager.speak("Tôi không nghe thấy gì cả. Vui lòng thử lại.", wait=False)
                        if self.tray_controller:
                            self.tray_controller.update_status(TrayStatus.ACTIVE)
                        return

                    # Show "thinking" state in overlay
                    if self.overlay:
                        self.overlay.show_thinking(transcript)

                    # Send to LLM/Dispatcher via process_text_command
                    response_text = ""
                    try:
                        result = self.process_text_command(transcript, requester="voice")
                        response_text = result.get("response_text", "")
                    except Exception as e:
                        log.error("Command processing failed: %s", e)
                        response_text = f"Xin lỗi, tôi gặp lỗi khi xử lý lệnh: {e}"
                        if self.tts_manager:
                            self.tts_manager.speak(response_text, wait=False)

                    # Update overlay with final response
                    if self.overlay:
                        self.overlay.show_response(transcript, response_text)

                    if self.tray_controller:
                        self.tray_controller.update_status(TrayStatus.ACTIVE)
>>>>
```

---

### 2.3 Item 3: Connect `_handle_system_status` to `HardwareReporter`

#### Root Cause Analysis
In `jarvis/core/app.py:230-235`, `_handle_system_status` returns:
```python
msg = "JARVIS systems operating normally. Audio engine active, all plugins responsive."
if self.tts_manager:
    self.tts_manager.speak(msg, wait=False)
return {"status": "healthy", "message": msg}
```
This fails Requirement R7, Requirement 3, and the Acceptance Criteria (`Triple clap → system_status đọc to CPU/RAM usage`).
`jarvis/hardware/reporter.py` already implements `HardwareReporter` which connects to `HardwareMonitor` (supporting Windows Win32 ctypes, CIM PowerShell, nvidia-smi, and psutil telemetry). `JarvisApp` simply needs to instantiate `HardwareReporter` and call `format_voice_summary(lang="vi")`.

#### Exact Code Changes

**File: `jarvis/core/app.py`**
1. Add import:
```python
from jarvis.hardware.reporter import HardwareReporter
```

2. Initialize in `JarvisApp.__init__` (`app.py:88`):
```python
        # 5. Hardware Telemetry & Diagnostics
        self.hardware_reporter: Optional[HardwareReporter] = None
```

3. Instantiate in `JarvisApp.initialize()` (`app.py:188`):
```python
        # 10. Hardware Reporter Subsystem (F-20, F-21, F-22)
        hw_cfg = self.config.get("hardware", {})
        self.hardware_reporter = HardwareReporter(
            tts_manager=self.tts_manager,
            dispatcher=self.dispatcher,
            config={"hardware": hw_cfg} if isinstance(hw_cfg, dict) else {},
        )
```

4. Update `_handle_system_status` (`app.py:230-235`):
```python
<<<<
    def _handle_system_status(self, **kwargs) -> Dict[str, Any]:
        """Vocalizes and returns system health status."""
        msg = "JARVIS systems operating normally. Audio engine active, all plugins responsive."
        if self.tts_manager:
            self.tts_manager.speak(msg, wait=False)
        return {"status": "healthy", "message": msg}
====
    def _handle_system_status(self, **kwargs) -> Dict[str, Any]:
        """Vocalizes and returns system health status with live CPU and RAM metrics."""
        lang = "vi"
        if self.config:
            locale = str(self.config.get("system.locale", "vi_VN")).lower()
            lang = "en" if locale.startswith("en") else "vi"

        msg = ""
        metrics_dict: Dict[str, Any] = {}
        if self.hardware_reporter:
            try:
                msg = self.hardware_reporter.format_voice_summary(lang=lang)
                metrics = self.hardware_reporter.monitor.get_metrics()
                metrics_dict = metrics.to_dict() if hasattr(metrics, "to_dict") else {}
            except Exception as e:
                log.error("HardwareReporter status query failed: %s", e)
                msg = (
                    "Tình trạng hệ thống: Tất cả dịch vụ đang hoạt động bình thường."
                    if lang == "vi"
                    else "JARVIS systems operating normally. Audio engine active, all plugins responsive."
                )
        else:
            msg = (
                "Tình trạng hệ thống: Tất cả dịch vụ đang hoạt động bình thường."
                if lang == "vi"
                else "JARVIS systems operating normally. Audio engine active, all plugins responsive."
            )

        if self.tts_manager:
            self.tts_manager.speak(msg, wait=False)

        return {
            "status": "healthy",
            "message": msg,
            "metrics": metrics_dict,
        }
>>>>
```

5. Make `triple_clap` and `double_clap` actions dynamic to config (`app.py:401-406` & `app.py:294-320`):
```python
<<<<
        # ------------------------------------------------------------------ #
        #  TRIPLE CLAP — System status report                                 #
        # ------------------------------------------------------------------ #
        if pattern_name == "triple_clap":
            try:
                self.dispatcher.dispatch_action("system_status", requester=RequesterContext.system())
            except Exception as e:
                log.error("system_status action failed: %s", e)
            return
====
        # ------------------------------------------------------------------ #
        #  TRIPLE CLAP — System status report                                 #
        # ------------------------------------------------------------------ #
        if pattern_name == "triple_clap":
            action_names = self.config.get("gesture.patterns.triple_clap.actions", ["system_status"])
            for act in action_names:
                try:
                    self.dispatcher.dispatch_action(act, requester=RequesterContext.system())
                except Exception as e:
                    log.error("Action [%s] failed for pattern [triple_clap]: %s", act, e)
            return
>>>>
```
And in `_welcome()`:
```python
<<<<
                def _welcome():
                    # 1. Music
                    try:
                        self.dispatcher.dispatch_action("spotify", requester=RequesterContext.system())
                    except Exception as e:
                        log.warning("Spotify action failed: %s", e)

                    # 2. Chrome windows
                    for act in ["chrome_claude", "chrome_binance"]:
                        try:
                            self.dispatcher.dispatch_action(act, requester=RequesterContext.system())
                        except Exception as e:
                            log.warning("Chrome action [%s] failed: %s", act, e)

                    # 3. Cursor IDE
                    try:
                        self.dispatcher.dispatch_action("cursor", requester=RequesterContext.system())
                    except Exception as e:
                        log.warning("Cursor action failed: %s", e)

                    # 4. TTS welcome speech
                    try:
                        self.dispatcher.dispatch_action("tts_welcome", requester=RequesterContext.system())
                    except Exception as e:
                        log.warning("TTS welcome failed: %s", e)
====
                def _welcome():
                    configured_actions = self.config.get("gesture.patterns.double_clap.actions", [
                        "spotify", "chrome_claude", "chrome_binance", "tts_welcome", "cursor"
                    ])
                    for act in configured_actions:
                        try:
                            self.dispatcher.dispatch_action(act, requester=RequesterContext.system())
                        except Exception as e:
                            log.warning("Action [%s] failed during welcome sequence: %s", act, e)
>>>>
```

---

### 2.4 Item 4: Elevate Cooldown Suppression Log Level to `INFO`

#### Root Cause Analysis
In `jarvis/core/app.py:267-274`:
```python
cooldown = self._action_fanout_cooldown_s
if elapsed < cooldown:
    log.debug(
        "Gesture [%s] suppressed — cooldown %.1fs remaining.",
        pattern_name, cooldown - elapsed,
    )
    return
```
Under standard application configuration (`logging.level = "INFO"` in `default_config.yaml`), `log.debug` output is discarded. Consequently, automated test log-scrapers and production audits cannot observe cooldown debouncing.

#### Exact Code Changes

**File: `jarvis/core/app.py`**
```python
<<<<
        # Per-pattern cooldown guard (prevents rapid re-trigger spam)
        cooldown = self._action_fanout_cooldown_s
        if elapsed < cooldown:
            log.debug(
                "Gesture [%s] suppressed — cooldown %.1fs remaining.",
                pattern_name, cooldown - elapsed,
            )
            return
====
        # Per-pattern cooldown guard (prevents rapid re-trigger spam)
        cooldown = self._action_fanout_cooldown_s
        if elapsed < cooldown:
            log.info(
                "Gesture [%s] suppressed — cooldown %.1fs remaining.",
                pattern_name, cooldown - elapsed,
            )
            return
>>>>
```

---

## 3. Verification Plan & Test Specifications

The implementer must verify these changes with unit and integration tests:

### Test Case 1: `test_clap_pause_clap_dispatches_show_overlay`
- **Objective**: Verify that `_on_gesture_event("clap_pause_clap")` triggers `show_overlay` action and invokes `overlay.show_listening()`.
- **Method**:
  ```python
  app = JarvisApp(headless=True, no_hot_reload=True)
  app.initialize()
  app.overlay = MagicMock()
  app._on_gesture_event("clap_pause_clap")
  app.overlay.show_listening.assert_called_once()
  app.stop()
  ```

### Test Case 2: `test_ai_voice_loop_decoupled_recording_with_mock_stt`
- **Objective**: Verify that 2nd double-clap triggers `_ai_voice_loop`, calls `record_audio()` without hardware block, transcribes via mock STT, and executes command.
- **Method**:
  ```python
  app = JarvisApp(headless=True, no_hot_reload=True)
  app.initialize()
  app.welcome_executed = True  # Put into subsequent state
  app.stt_engine.primary_engine = MockSTTEngine(default_transcript="kiểm tra nhiệt độ cpu")
  app.overlay = MagicMock()
  app._on_gesture_event("double_clap")
  time.sleep(0.3)
  app.overlay.show_thinking.assert_called()
  app.overlay.show_response.assert_called()
  app.stop()
  ```

### Test Case 3: `test_system_status_queries_real_hardware_metrics`
- **Objective**: Verify `system_status` action returns real CPU and RAM percentage metrics in message and payload dictionary.
- **Method**:
  ```python
  app = JarvisApp(headless=True, no_hot_reload=True)
  app.initialize()
  res = app.dispatcher.dispatch_action("system_status")
  assert res.success is True
  assert "cpu" in res.data["message"].lower()
  assert "ram" in res.data["message"].lower()
  assert "cpu_percent" in res.data["metrics"]
  assert "ram_percent" in res.data["metrics"]
  app.stop()
  ```

### Test Case 4: `test_gesture_cooldown_suppression_logged_at_info`
- **Objective**: Verify that rapid gesture trigger produces an `INFO` level log with `"suppressed"`.
- **Method**:
  ```python
  app = JarvisApp(headless=True, no_hot_reload=True)
  app.initialize()
  with caplog.at_level(logging.INFO):
      app._on_gesture_event("double_clap")
      app._on_gesture_event("double_clap")  # within 3.0s cooldown
  assert any("suppressed" in rec.message.lower() for rec in caplog.records)
  app.stop()
  ```

---

## 4. Risks & Backward Compatibility Assessment

1. **Test Suite Compatibility**:
   Existing tests that rely on `app.config.set("gesture.patterns.double_clap.actions", ...)` will now work seamlessly because `_welcome()` dynamically reads `gesture.patterns.double_clap.actions`.
2. **Headless Execution**:
   The `record_audio()` method safely falls back to a brief silent buffer in `self.headless` mode, preventing CI crashes while retaining full production audio capture on physical hardware.
3. **No Double-Dispatch**:
   `GestureDetector` continues to be initialized with `dispatcher=None`, ensuring that all action fanout remains strictly managed by `JarvisApp._on_gesture_event`.
