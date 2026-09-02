# TEST_READY: JARVIS Sprint 2 (v4.7.0) Acceptance Test Suite

**Status**: READY  
**Release Target**: v4.7.0 (Sprint 2: Accuracy, Acoustic & UX Hardening)  
**Date**: 2026-09-02  
**Working Directory**: `d:\Software GitCode\JARVIS`  

---

## 1. Executive Summary
The acceptance test suite for JARVIS Sprint 2 (v4.7.0) has been fully designed, authored, and verified. The suite covers all five functional requirements (R1–R5) specified in `ORIGINAL_REQUEST.md` and `PROJECT.md`, encompassing 37 unit tests across 5 new test modules in `tests/unit/`.

---

## 2. Requirement to Test Matrix

| Req | Functional Area | Target Module | Test File | Test Cases | Status |
|:---:|---|---|---|---|:---:|
| **R1** | **DSP Acoustic Hardening & Echo Suppression** | `jarvis/audio/wake_word.py`<br>`jarvis/audio/vad.py`<br>`jarvis/core/app.py` | `tests/unit/test_acoustic_hardening.py` | • `test_vad_filter_silent_frame_discard`<br>• `test_vad_speech_frame_passthrough`<br>• `test_vad_listen_for_speech_segmentation`<br>• `test_post_tts_microphone_suppression_active_and_cooldown`<br>• `test_suppress_until_and_ring_buffer_clearing`<br>• `test_spectral_flatness_pure_tone_rejection`<br>• `test_spectral_flatness_white_noise_rejection`<br>• `test_zcr_fricative_threshold_requirement`<br>• `test_clap_impulse_rejection_simultaneous_peaks`<br>• `test_valid_synthetic_wake_word_pass_through` | ✅ READY (9 tests) |
| **R2** | **SAPI5 TTS Thread Safety (COM Apartment)** | `jarvis/tts/manager.py`<br>`jarvis/tts/fallback.py` | `tests/unit/test_tts_com_safety.py` | • `test_tts_worker_com_initialization_lifecycle`<br>• `test_ten_consecutive_tts_calls_daemon_thread`<br>• `test_sapi5_fallback_com_safety_and_finally_cleanup`<br>• `test_sapi5_dispatch_exception_recovery`<br>• `test_sapi5_synthesize_to_bytes_offline_contract` | ✅ READY (5 tests) |
| **R3** | **Faster-Whisper STT Eager Preload & VAD** | `jarvis/stt/engine.py` | `tests/unit/test_stt_preload.py` | • `test_faster_whisper_eager_background_preload`<br>• `test_faster_whisper_transcribe_vad_filter_and_parameters`<br>• `test_warm_model_transcription_latency_budget`<br>• `test_transcribe_concurrent_during_preload_thread_safety`<br>• `test_silence_and_empty_audio_short_circuit` | ✅ READY (5 tests) |
| **R4** | **HUD Non-Blocking & System Tray Status** | `jarvis/ui/tray.py`<br>`jarvis/ui/overlay.py` | `tests/unit/test_tray_menu.py` | • `test_tray_menu_item_count_and_status_item_presence`<br>• `test_tray_status_summary_display_content`<br>• `test_tray_on_view_logs_safe_path_resolution`<br>• `test_tray_toggle_controls_and_state_transitions`<br>• `test_create_status_icon_all_states` | ✅ READY (5 tests) |
| **R5** | **Hardware Voice Reporting & Intent Router** | `jarvis/hardware/reporter.py`<br>`jarvis/llm/router.py` | `tests/unit/test_router_hardware.py` | • `test_hardware_queries_routing_accented` (5 queries)<br>• `test_hardware_queries_routing_unaccented` (5 queries)<br>• `test_format_voice_summary_vietnamese_metrics`<br>• `test_format_component_summary_all_targets`<br>• `test_hardware_reporter_markdown_report_generation` | ✅ READY (13 tests) |

---

## 3. Authoritative Acceptance Criteria Verification

### 3.1 Acoustic Hardening (R1 / P1-8)
- [x] VAD filter frame discard: frames with RMS < 0.01 or non-speech are discarded.
- [x] 2.5s post-TTS microphone suppression: incoming blocks dropped during active playback and within 2.5s window.
- [x] Ring buffer zeroing / clearing on suppression.
- [x] SFM lower bound (0.03) rejects pure tones; SFM upper bound (0.65) rejects white noise.
- [x] ZCR lower bound ($\ge 0.10$) enforces fricative burst in Syllable 2 ("VIS").
- [x] Simultaneous broadband claps ($|t_{\text{diff}}| < 0.05\text{s}$) rejected.

### 3.2 SAPI5 COM Concurrency Safety (R2 / P1-9)
- [x] `pythoncom.CoInitialize()` invoked on daemon worker thread startup.
- [x] `pythoncom.CoUninitialize()` invoked in `finally` block upon thread teardown.
- [x] 10 consecutive TTS calls in daemon thread execute with 0 COM errors.
- [x] COM dispatch failure triggers automatic recovery via PowerShell/pyttsx3/mock.

### 3.3 Faster-Whisper Eager Preloading & Trimming (R3 / P1-10)
- [x] `FasterWhisperSTT.__init__()` initiates model loading without blocking caller thread.
- [x] `transcribe()` passes `vad_filter=True` and `vad_parameters={"min_silence_duration_ms": 500}`.
- [x] Warm model transcription finishes within $\le 1.5\text{s}$ for 3-second audio.
- [x] Thread-safe synchronization when `transcribe()` is called during background preload.

### 3.4 HUD Overlay & System Tray Telemetry (R4 / P1-6 & P1-7)
- [x] System tray menu contains $\ge 4$ items including Status, Wake Word, Mic, Exit.
- [x] Status menu item reflects version (v4.7.0), TTS state, STT state, and RAM usage.
- [x] `_on_view_logs` safely imports and uses `pathlib.Path` without `NameError`.

### 3.5 Hardware Voice Reporting & Router Intent (R5 / P1-11)
- [x] 5 hardware queries (`"cpu mấy phần trăm"`, `"ram còn bao nhiêu"`, `"nhiệt độ máy"`, `"pin còn bao nhiêu"`, `"tốc độ cpu"`) and unaccented variants route to `system_status` / `hardware_telemetry_check` with $\text{MISROUTED} = 0$.
- [x] `format_voice_summary()` outputs natural Vietnamese string with CPU% and RAM%.

---

## 4. How to Run the Acceptance Test Suite

```powershell
# 1. Run all Sprint 2 acceptance unit tests:
pytest tests/unit/test_acoustic_hardening.py tests/unit/test_tts_com_safety.py tests/unit/test_stt_preload.py tests/unit/test_tray_menu.py tests/unit/test_router_hardware.py -v

# 2. Run intent routing evaluation benchmark (150 utterances):
python tests/eval/routing_eval_n150.py

# 3. Run entire unit & adversarial regression suite:
pytest tests/unit/ tests/test_adversarial_*.py -q
```
