# Handoff Report: DSP Acoustic Hardening & SAPI5 COM Thread Safety (Milestones M1 & M2)

**Date**: 2026-09-02  
**Author**: Worker M1 & M2 (`worker_m1_m2`)  
**Target Milestone**: JARVIS v4.7.0 Sprint 2 (R1 & R2)  
**Report Location**: `d:\Software GitCode\JARVIS\.agents\worker_m1_m2\handoff.md`

---

## 1. Observation

Direct code examination and verification of source files and test suites confirmed the following:

1. **Wake Word Detection & VAD Ingestion (`jarvis/audio/wake_word.py:470-520, 750-820`)**:
   - `WakeWordDetector.feed_audio_block()` previously ingested all frames directly into `_ring_buffer` regardless of whether the frame was silence, background noise, or speech.
   - Now, `WakeWordDetector` features `vad_filter_enabled` (default `True`), `vad_threshold` (default `0.003`), and `_suppress_until`. Silent frames (`block_rms < vad_threshold` and `ring_rms < vad_threshold`) are dropped prior to ring buffer rolling and FFT execution.
   - `WakeWordDetector.suppress_until(timestamp)` immediately zeroes `_ring_buffer` and resets detector streams.
   - SFM thresholds ($0.03 \le \text{SFM} \le 0.65$) and ZCR threshold ($\text{ZCR}_{S2} \ge 0.10$) in `AcousticSpectralDetector` accurately reject pure sinusoidal tones, white noise, and non-fricative syllables.

2. **Acoustic Echo Suppression (`jarvis/tts/manager.py:65-170`, `jarvis/core/app.py:330-350`)**:
   - `TTSManager` now tracks `_last_playback_finish_time` and `_is_playing`.
   - `TTSManager.is_in_echo_window(current_time, cooldown_s=2.5)` returns `True` during active playback and for 2.5s post-playback.
   - `_on_audio_blocks_dispatch()` in `jarvis/core/app.py` actively checks `is_in_echo_window()` and discards incoming microphone frames while calling `wake_word_detector.suppress_until()` to prevent reverberation and echo loops.

3. **SAPI5 TTS COM Thread Safety (`jarvis/tts/manager.py:73-110`, `jarvis/tts/fallback.py:52-85`)**:
   - `TTSManager._process_queue()` initializes COM via `pythoncom.CoInitialize()` upon worker thread start and cleans up via `pythoncom.CoUninitialize()` in the `finally:` block.
   - `SAPI5FallbackTTS.speak()` wraps COM dispatch in `try: pythoncom.CoInitialize() ... finally: pythoncom.CoUninitialize()`, guaranteeing no COM apartment leaks or RPC mode errors.

---

## 2. Logic Chain

```
[Requirement R1] Microphone captures room audio continuously, including speaker output during TTS.
       ↓
[Acoustic Echo Loop] Without frame-level suppression, speaker speech enters wake word buffer.
       ↓
[Implementation] In TTSManager, record _last_playback_finish_time upon speak completion and expose is_in_echo_window(cooldown_s=2.5).
                 In core/app.py _on_audio_blocks_dispatch, drop incoming mic frames during echo window and flush wake word buffer.
                 In wake_word.py, add VAD pre-filter gate to drop silent blocks (RMS < 0.003).
       ↓
[Requirement R2] win32com Dispatch on Windows requires single-threaded apartment (STA) initialization per thread.
       ↓
[COM Crash Prevention] SAPI5 worker thread and direct fallback calls now manage CoInitialize/CoUninitialize lifecycles with guaranteed finally teardown.
```

---

## 3. Caveats

- `is_in_echo_window` uses `time.monotonic()`. When testing in simulated time environments, the `current_time` parameter should be supplied explicitly.
- Porcupine and Vosk Tier 1 engines require continuous PCM streaming when active; VAD pre-filtering gates Tier 2 / Whisper fallback while allowing Tier 1 state machine operations.

---

## 4. Conclusion

All requirements for Milestones M1 (R1: DSP Acoustic Hardening & Echo Suppression) and M2 (R2: SAPI5 TTS COM Thread Safety) are fully implemented, verified, and integrated cleanly. All 102 target unit tests pass with 0 failures, and the full repository test suite (1,200+ unit tests) passes with no regressions.

---

## 5. Verification Method

### Test Suite Execution
```powershell
pytest tests/unit/test_wake_word.py tests/unit/test_wake_word_p0.py tests/unit/test_tts_engines.py tests/unit/test_dsp.py tests/unit/test_acoustic_hardening.py tests/unit/test_tts_com_safety.py -v
```

### Verification Result
- `tests/unit/test_wake_word.py`: 53 passed
- `tests/unit/test_wake_word_p0.py`: 20 passed
- `tests/unit/test_tts_engines.py`: 4 passed
- `tests/unit/test_dsp.py`: 9 passed
- `tests/unit/test_acoustic_hardening.py`: 11 passed
- `tests/unit/test_tts_com_safety.py`: 5 passed
- **Total**: **102 passed**, 0 failures in 20.60s.
