# Progress — worker_m1_m2

Last visited: 2026-09-02T08:03:00Z

## Status
Tasks M1 and M2 are COMPLETE. All 102 target unit tests pass with 0 failures.

## Accomplishments
1. **R1 (DSP Acoustic Hardening & Echo Suppression)**:
   - Added VAD pre-filter gate in `WakeWordDetector.feed_audio_block()` to drop silent/low-energy frames (RMS < 0.003) before feeding ring buffer and before STFT spectral analysis.
   - Added `suppress_until()` method to `WakeWordDetector` to immediately flush ring buffer and Porcupine/Whisper state buffers.
   - Added `_last_playback_finish_time` and `_is_playing` tracking to `TTSManager`.
   - Implemented `TTSManager.is_in_echo_window(current_time, cooldown_s=2.5)`.
   - Updated `_on_audio_blocks_dispatch()` in `jarvis/core/app.py` to drop microphone frames during active TTS or within 2.5s post-TTS cooldown window.
   - Created `tests/unit/test_acoustic_hardening.py` with 11 tests covering VAD filtering, silence rejection, echo windowing, and SFM/ZCR bounds.
2. **R2 (SAPI5 TTS COM Thread Safety)**:
   - Added `pythoncom.CoInitialize()` at worker thread start and `pythoncom.CoUninitialize()` in `finally:` block in `TTSManager._process_queue()`.
   - Added `pythoncom.CoUninitialize()` in `finally:` block in `SAPI5FallbackTTS.speak()`.
   - Created `tests/unit/test_tts_com_safety.py` with 5 tests covering COM lifecycle, 10 consecutive queue items, and error handling.
3. **Verification**:
   - `pytest tests/unit/test_wake_word.py tests/unit/test_wake_word_p0.py tests/unit/test_tts_engines.py tests/unit/test_dsp.py tests/unit/test_acoustic_hardening.py tests/unit/test_tts_com_safety.py -v` -> 102 passed, 0 failures.
