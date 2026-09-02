# BRIEFING — 2026-09-02T08:03:00Z

## Mission
Implement DSP Acoustic Hardening & Echo Suppression (M1) and SAPI5 TTS COM Thread Safety (M2) for JARVIS Sprint 2 (v4.7.0).

## 🔒 My Identity
- Archetype: worker
- Roles: implementer, qa, specialist
- Working directory: d:\Software GitCode\JARVIS\.agents\worker_m1_m2
- Original parent: 9506425c-ec6d-40db-a68f-f37c461f99fc
- Milestone: Sprint 2 (M1 & M2)

## 🔒 Key Constraints
- Exclusively owned files:
  - `jarvis/audio/wake_word.py`
  - `jarvis/audio/dsp.py`
  - `jarvis/core/app.py`
  - `jarvis/tts/manager.py`
  - `jarvis/tts/fallback.py`
- DO NOT CHEAT. All implementations must be genuine. Real state and behavior only.
- Minimal change principle.
- Full verification: `pytest tests/unit/test_wake_word.py tests/unit/test_wake_word_p0.py tests/unit/test_tts_engines.py tests/unit/test_dsp.py tests/unit/test_acoustic_hardening.py tests/unit/test_tts_com_safety.py -v` must pass with 0 failures.

## Current Parent
- Conversation ID: 9506425c-ec6d-40db-a68f-f37c461f99fc
- Updated: 2026-09-02T08:03:00Z

## Task Summary
- **What to build**:
  - DSP Acoustic Hardening & Echo Suppression (R1 / P1-8):
    - `jarvis/audio/wake_word.py`: VAD pre-filter in `feed_audio_block()` dropping silent/low-energy frames, SFM [0.03, 0.65], ZCR >= 0.10, and `suppress_until()` method to purge buffer.
    - `jarvis/tts/manager.py`: Track `_last_playback_finish_time`, `_is_playing`, and implement `is_in_echo_window(cooldown_s=2.5)`.
    - `jarvis/core/app.py`: Drop incoming mic frames and suppress wake word buffer if `tts_manager.is_in_echo_window()`.
  - SAPI5 TTS COM Thread Safety (R2 / P1-9):
    - `jarvis/tts/manager.py`: `pythoncom.CoInitialize()` at worker thread start, `pythoncom.CoUninitialize()` in finally block.
    - `jarvis/tts/fallback.py`: Proper COM uninitialization in `finally:`.
- **Success criteria**: 102/102 unit tests pass with 0 failures.

## Change Tracker
- **Files modified**:
  - `jarvis/audio/wake_word.py`: Added VAD pre-filter gate, `suppress_until()`, timestamp checking, and stream buffer clearing.
  - `jarvis/tts/manager.py`: Added COM lifecycle in `_process_queue()`, playback tracking, `is_in_echo_window()`.
  - `jarvis/tts/fallback.py`: Added `pythoncom.CoUninitialize()` in `finally:` block.
  - `jarvis/core/app.py`: Added echo suppression mic frame drop and wake word suppression in `_on_audio_blocks_dispatch()`.
  - `tests/unit/test_acoustic_hardening.py`: Added 11 comprehensive tests for VAD, echo suppression, and spectral bounds.
  - `tests/unit/test_tts_com_safety.py`: Added 5 comprehensive tests for COM initialization, daemon queuing, and fallback error handling.
- **Build status**: 102 passed, 0 failures.
- **Pending issues**: None.

## Quality Status
- **Build/test result**: 102 passed in 20.60s.
- **Lint status**: 0 errors.
- **Tests added/modified**: `tests/unit/test_acoustic_hardening.py` (11 tests), `tests/unit/test_tts_com_safety.py` (5 tests).

## Loaded Skills
- None

## Key Decisions Made
- Gated silent frames with RMS < 0.003 before feeding ring buffer in standalone Tier 2 acoustic detector and before STFT analysis.
- Guaranteed COM lifecycle integrity per STA thread in TTS worker thread and SAPI5 fallback.
- Added 2.5s post-playback acoustic echo window in TTSManager and hooked into audio dispatcher in App.

## Artifact Index
- `.agents/worker_m1_m2/DISPATCH.md` — Assignment instructions
- `.agents/worker_m1_m2/progress.md` — Progress tracker
- `.agents/worker_m1_m2/handoff.md` — Final handoff report
