## 2026-09-02T07:44:40Z

You are Worker M1 & M2 for JARVIS Sprint 2 (v4.7.0).
Your working directory is: `d:\Software GitCode\JARVIS\.agents\worker_m1_m2`
Mandatory source of truth: `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md`
Project scope: `d:\Software GitCode\JARVIS\PROJECT.md`
Audio Survey Report: `d:\Software GitCode\JARVIS\.agents\explorer_survey_audio_tts\handoff.md`

Exclusively owned files:
- `jarvis/audio/wake_word.py`
- `jarvis/audio/dsp.py`
- `jarvis/core/app.py`
- `jarvis/tts/manager.py`
- `jarvis/tts/fallback.py`

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A forensic auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Tasks:
1. R1 (DSP Acoustic Hardening & Echo Suppression):
   - In `jarvis/audio/wake_word.py`: Add VAD pre-filter gate in `feed_audio_block()` to drop silent/low-energy frames before feeding ring buffer. Ensure SFM [0.03, 0.65] and ZCR >= 0.10 thresholds operate correctly. Add `suppress_until()` method to clear buffer.
   - In `jarvis/tts/manager.py`: Track `_last_playback_finish_time` and implement `is_in_echo_window(cooldown_s=2.5)`.
   - In `jarvis/core/app.py` (`_on_audio_blocks_dispatch`): Drop incoming microphone frames if `tts_manager.is_in_echo_window()`.
2. R2 (SAPI5 TTS COM Thread Safety):
   - In `jarvis/tts/manager.py` (`_process_queue`): Add `pythoncom.CoInitialize()` at the worker thread loop start, and `pythoncom.CoUninitialize()` in `finally:`.
   - In `jarvis/tts/fallback.py`: Ensure proper COM uninitialization in `finally:`.
3. Build and test verification:
   - Run: `pytest tests/unit/test_wake_word.py tests/unit/test_wake_word_p0.py tests/unit/test_tts_engines.py tests/unit/test_dsp.py tests/unit/test_acoustic_hardening.py tests/unit/test_tts_com_safety.py -v`
   - Ensure all pass with 0 failures.

Write handoff report to `d:\Software GitCode\JARVIS\.agents\worker_m1_m2\handoff.md`.
Maintain `progress.md` in your working directory.
When complete, notify parent orchestrator via send_message.
