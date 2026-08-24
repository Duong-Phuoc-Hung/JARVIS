# Milestone M1 Review & Adversarial Challenge Report

**Reviewer**: Reviewer 2 (Milestone M1)  
**Working Directory**: `d:/Software GitCode/JARVIS/.agents/reviewer_m1_2`  
**Date**: 2026-08-22  
**Final Verdict**: **`APPROVE`**  
**Overall Risk Assessment**: **`LOW`**

---

## 1. Observation

Direct observations from examining the codebase and test runs:

1. **`jarvis/gesture/patterns.py` (lines 41-51)**:
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
   )
   ```
   `CLAP_PAUSE_CLAP` pattern is bound to `actions=["show_overlay"]`. In `config/default_config.yaml` (lines 56-65), `clap_pause_clap` defines `actions: ["show_overlay"]`.

2. **`jarvis/core/app.py` (lines 230-233, 306-311, 472-480)**:
   - Action `"show_overlay"` is registered in `_register_core_actions` with handler `_handle_show_overlay`.
   - `_handle_show_overlay` calls `self.overlay.show_listening()` and returns `{"status": "overlay_shown"}`.
   - `_on_gesture_event` dynamically dispatches configured actions from `self.config.get("gesture.patterns.clap_pause_clap.actions", ["show_overlay"])`.

3. **`jarvis/core/app.py` `record_audio()` (lines 313-343) and `_ai_voice_loop()` (lines 403-455)**:
   - `record_audio(duration_s, sample_rate)` encapsulates microphone recording. When `self.headless` is True, it immediately returns `np.zeros(int(sr * min(dur, 0.1)), dtype=np.float32)` without hardware blocking.
   - `_ai_voice_loop` calls `audio_flat = self.record_audio()` and `transcript = self.stt_engine.transcribe(audio_flat)` within a try/except block.
   - If audio capture or transcription fails or produces silence, it shows `"(không nghe thấy)"` on the overlay and speaks `"Tôi không nghe thấy gì cả. Vui lòng thử lại."` without raising uncaught exceptions.

4. **`jarvis/core/app.py` `_handle_system_status()` (lines 243-298)**:
   - `self.hardware_reporter` is initialized in `initialize()`.
   - In `_handle_system_status()`, fast CPU/RAM metrics are queried via `self.hardware_reporter.monitor.get_metrics()` or direct probe fallback (`_probe_ram()` / `_probe_cpu()`).
   - Summary string is generated via `self.hardware_reporter.format_voice_summary(metrics=metrics, lang=lang)`, spoken via `self.tts_manager.speak(msg, wait=False)`, and returned as structured dictionary `{"status": "healthy", "message": msg, "metrics": metrics_dict}`.

5. **`jarvis/core/app.py` Zero Duplicate TTS Calls (lines 437-450 vs lines 553-556)**:
   - `_ai_voice_loop` passes transcript to `self.process_text_command(transcript, requester="voice")`.
   - `process_text_command` performs single vocalization at line 555: `self.tts_manager.speak(response_text, wait=False)`.
   - `_ai_voice_loop` updates the overlay HUD (`self.overlay.show_response(...)`) without calling `self.tts_manager.speak(...)` again in the success path.

6. **`jarvis/stt/engine.py` Resolution & Fallback (lines 657-679, 715-737)**:
   - `_resolve_engine()` maps `"web_speech"`, `"windows"`, `"web"`, `"windows_sapi"`, `"windows_speech"`, and `"sapi5"` to `WindowsSpeechSTT` on Windows (using PowerShell `System.Speech.Recognition.SpeechRecognitionEngine`) and `MockSTTEngine` on other platforms.
   - In `STTEngine.transcribe()`, primary engine is attempted first; on any failure, fallback engine is automatically executed.
   - Audio conversion in `audio_to_float32` (lines 92, 139) normalizes int16 PCM by `32768.0` before channel downmixing, avoiding integer overflow or 1.0 clipping.

7. **`jarvis/tts/fallback.py` & `jarvis/tts/manager.py`**:
   - `SAPI5FallbackTTS` defensively initializes COM with `pythoncom.CoInitialize()` in secondary threads, and encodes PowerShell commands using UTF-16LE Base64 (`-EncodedCommand`) with UTF-8 byte reconstruction for shell-safe, diacritic-preserving speech.
   - `TTSManager.speak_welcome()` implements a non-repeating randomized greeting pool from `config.get("welcome.phrases")` or `WELCOME_PHRASES`.

8. **Test Execution Command & Output**:
   Ran: `python -m pytest tests/test_gesture_detector.py tests/test_tts_engine.py tests/unit/test_app_integration.py tests/test_adversarial_m3_ui_app.py -v`
   Result: **30 passed in 14.75s** (100% pass rate).

---

## 2. Logic Chain

1. **Routing & Overlay**:
   `CLAP_PAUSE_CLAP` pattern definition, YAML configuration, and `app._on_gesture_event` are fully aligned to `"show_overlay"`. When the syncopated pattern is recognized by DSP Schmitt trigger, `_handle_show_overlay` is invoked, successfully displaying the listening HUD.
2. **Audio Decoupling**:
   By encapsulating recording in `record_audio()` with headless and exception fallbacks, `_ai_voice_loop` does not freeze the event loop or crash headless CI runs when physical audio capture devices are absent.
3. **Hardware Telemetry**:
   `_handle_system_status` queries live CPU and RAM usage via `HardwareReporter`, generating human-readable English/Vietnamese voice output and returning metric payloads to callers and event buses.
4. **Duplicate Speech Elimination**:
   Consolidating speech output within `process_text_command()` ensures all interaction pathways (voice loop, text input, web UI) produce exactly one vocalization per command.
5. **STT Reliability & Robustness**:
   Support for `"web_speech"` provides built-in speech recognition on Windows without external API keys. Fast RMS gating (`calculate_rms(arr) < 0.001`) prevents wasteful network requests on silence.
6. **Integrity & Quality**:
   Source code contains genuine logic with proper error handling and fallback paths. No hardcoded mock assertions or test-bypass shims exist in production code.

---

## 3. Caveats

1. **Windows Speech Engine Recognition Quality**:
   `WindowsSpeechSTT` utilizes the OS desktop dictation grammar (`System.Speech.Recognition`). In noisy environments or for non-English/non-Vietnamese localized Windows speech packs, accuracy varies. The system cleanly falls back to `MockSTTEngine` or OpenAI Whisper if configured.
2. **Hardware Thermal Sensors**:
   On machines without ACPI ThermalZone CIM exposure or admin WMI permissions, CPU temperature metrics are omitted gracefully while CPU/RAM load percentages remain functional.

---

## 4. Conclusion

The implementation by Worker M1 satisfies all Milestone M1 functional requirements, interface contracts, and stability criteria:
- `clap_pause_clap` properly opens the overlay.
- `_ai_voice_loop` records non-blockingly via decoupled `record_audio()`.
- `_handle_system_status` reports dynamic CPU/RAM telemetry.
- Zero duplicate TTS calls exist in the voice interaction loop.
- STT `"web_speech"` resolves properly with defensive fallbacks.
- Cooldown suppression is visible at INFO log level.
- All 30 targeted unit and adversarial tests pass cleanly.

**Final Recommendation**: **`APPROVE`** — Ready to proceed to Milestone M2 (Smart Keyword Router in Vietnamese).

---

## 5. Verification Method

To independently verify these results:

```powershell
python -m pytest tests/test_gesture_detector.py tests/test_tts_engine.py tests/unit/test_app_integration.py tests/test_adversarial_m3_ui_app.py -v
```

### Invalidation Conditions:
- Any test failures in the 30 targeted test cases.
- Any regression causing `clap_pause_clap` to route to `toggle_mute`.
- Duplicate audio playback in `_ai_voice_loop`.
