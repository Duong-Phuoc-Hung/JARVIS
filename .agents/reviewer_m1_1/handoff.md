# Milestone M1 (Voice AI Pipeline Bug Fixes & Stabilization) — Reviewer 1 Handoff Report

**Reviewer**: Reviewer 1 (Archetype: reviewer / critic)  
**Milestone**: M1 (Voice AI Pipeline Bug Fixes & Stabilization)  
**Date**: 2026-08-22  
**Verdict**: **APPROVE**

---

## 1. Observation

Direct observations and findings from the codebase review of Worker M1 modifications:

1. **`jarvis/gesture/patterns.py` (lines 41-52)**:
   - `GestureType.CLAP_PAUSE_CLAP` pattern definition accurately configures `actions=["show_overlay"]`:
     ```python
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
     ```
   - Matches `config/default_config.yaml` (`actions: ["show_overlay"]`).
   - Type annotations are clean and complete (`Dict[GestureType, GesturePatternConfig]`).

2. **`jarvis/core/app.py`**:
   - **Zero Double-Dispatch** (lines 153-158):
     `GestureDetector` is initialized with `dispatcher=None`, `event_bus=self.event_bus`, and `on_gesture=self._on_gesture_event`. This guarantees that acoustic triggers are only dispatched once via `_on_gesture_event`.
   - **Cooldown Debounce Logging** (lines 359-367):
     Cooldown suppression is elevated to `log.info`:
     ```python
     if elapsed < cooldown:
         log.info(
             "Gesture [%s] suppressed — cooldown %.1fs remaining.",
             pattern_name, cooldown - elapsed,
         )
         return
     ```
   - **Decoupled Audio Recording** (lines 313-343):
     `record_audio(duration_s, sample_rate)` handles headless/testing mode safely by returning a zero-filled `float32` array when `self.headless=True` or when `sounddevice` encounters hardware errors, avoiding test blocking.
   - **Two-Stage Double Clap Routing** (lines 381-455):
     First double clap triggers `_welcome()` and sets `self.welcome_executed = True`. Subsequent double claps trigger `_ai_voice_loop()`, updating overlay states (`LISTENING` -> `THINKING` -> `RESPONSE`), running STT transcription and routing through `process_text_command(transcript, requester="voice")`. Duplicate speech execution has been removed.
   - **Live Hardware Telemetry Integration** (lines 196-200, 243-298):
     `_handle_system_status()` uses `HardwareReporter` with fallback probing for live CPU and RAM utilization, returning structured metrics and speaking localized summaries in Vietnamese/English.
   - **Startup Greeting** (lines 613-616):
     `start()` vocalizes `"Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."` via `self.tts_manager.speak(...)`.

3. **`jarvis/stt/engine.py`**:
   - **Downmix Precision Fix** (lines 135-147 in `audio_to_float32()`):
     ```python
     if np.issubdtype(arr.dtype, np.integer):
         arr = arr.astype(np.float32) / 32768.0
     elif arr.dtype != np.float32:
         arr = arr.astype(np.float32)
     if arr.ndim > 1:
         arr = np.mean(arr, axis=1)
     return np.clip(arr, -1.0, 1.0)
     ```
     Converts integer PCM arrays to normalized float32 before averaging across channels, preventing amplitude distortion and premature clipping.
   - **Provider Resolution & SAPI Mapping** (lines 657-679):
     `_resolve_engine()` properly maps `"web_speech"`, `"windows"`, `"web"`, `"windows_speech"`, `"sapi5"`, `"windows_sapi"` to `WindowsSpeechSTT` on Windows and `MockSTTEngine` on other platforms.
   - **Non-Duplicate Fallback Instantiation** (lines 648-653):
     Prevents secondary duplication of `WindowsSpeechSTT` when primary is already `WindowsSpeechSTT`.
   - **Test Determinism** (lines 585-612):
     `MockSTTEngine` supports `set_transcript()` and per-call kwargs (`transcript`, `canned_key`).

4. **`jarvis/tts/fallback.py` & `jarvis/tts/manager.py`**:
   - **Thread-Safe SAPI5 Fallback** (lines 57-108 in `fallback.py`):
     Calls `pythoncom.CoInitialize()` defensively in COM worker threads. PowerShell speech synthesis uses a UTF-16LE Base64 `-EncodedCommand` with inner UTF-8 Base64 string decoding, avoiding quoting and escaping errors for Vietnamese text.
   - **Randomized Welcome Greetings** (lines 24-29, 150-169 in `manager.py`):
     `speak_welcome()` samples from `WELCOME_PHRASES` while avoiding repeating `_last_welcome_phrase`.

5. **`config/default_config.yaml`**:
   - Line 65: `gesture.patterns.clap_pause_clap.actions: ["show_overlay"]`.
   - Lines 81-85: `tts.welcome.phrases` configured with 4 greeting variations.
   - Line 94: `stt.provider: "web_speech"`.

6. **Integrity Audit**:
   - No hardcoded test fixtures or backdoor bypasses found in production code.
   - No facade or dummy implementations; full business logic implemented with real exception handling and fallbacks.
   - Genuine error isolation across all modules.

---

## 2. Logic Chain

1. **Gesture Routing & Overlay Integration**:
   - Observation 1 & Observation 2 demonstrate that `jarvis/gesture/patterns.py`, `jarvis/core/app.py`, and `config/default_config.yaml` are consistently aligned. `CLAP_PAUSE_CLAP` dispatches `show_overlay`, and `_handle_show_overlay()` invokes `self.overlay.show_listening()`.
2. **Debounce & Double-Dispatch Elimination**:
   - By decoupling `GestureDetector` from `dispatcher` directly and channeling triggers through `_on_gesture_event`, combined with a 3.0s cooldown check logged at `INFO`, accidental double execution is eliminated while providing clear audit logs.
3. **Voice AI Pipeline Decoupling & Testability**:
   - Introducing `JarvisApp.record_audio()` allows automated headless test suites to execute without blocking 5.0 seconds on physical microphones or crashing when PortAudio is absent.
   - Routing `_ai_voice_loop()` through `process_text_command()` consolidates dispatching, telemetry broadcasting, and single-point TTS response vocalization, removing duplicate speech.
4. **Speech & Audio Subsystem Hardening**:
   - The int16 float conversion order fix in `audio_to_float32()` preserves 16-bit PCM amplitude fidelity.
   - UTF-16LE Base64 PowerShell execution in `SAPI5FallbackTTS` handles non-ASCII Vietnamese characters without shell syntax errors.
   - Mapping `"web_speech"` to `WindowsSpeechSTT` allows out-of-the-box offline recognition on Windows without external API keys.

---

## 3. Caveats

- On Windows installations where the ACPI ThermalZone CIM is not exposed by hardware drivers, CPU temperature is omitted while CPU usage and RAM metrics are reliably reported.
- When running in headless environments without physical audio devices, `record_audio()` returns a zero-filled buffer that is gracefully filtered by VAD without raising exceptions.

---

## 4. Conclusion

**Verdict: APPROVE**

The code modifications submitted by Worker M1 for Milestone M1 satisfy all functional requirements, quality benchmarks, and edge-case resilience criteria without introducing regressions. All integrity checks passed.

---

## 5. Verification Method

To verify these changes independently, run the targeted test suite:
```powershell
python -m pytest tests/test_gesture_detector.py tests/test_tts_engine.py tests/unit/test_app_integration.py tests/test_adversarial_m3_ui_app.py -v
```

### Invalidation Conditions:
- Any failure in acoustic gesture detection timing (`DOUBLE_CLAP`, `TRIPLE_CLAP`, `CLAP_PAUSE_CLAP`).
- Double dispatch of actions upon a single acoustic trigger event.
- Exceptions raised in headless environments during audio recording or TTS fallback.
- Regression in full test suite (`python -m pytest tests/`).
