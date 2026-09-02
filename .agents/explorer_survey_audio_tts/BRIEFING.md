# BRIEFING — 2026-09-02T07:35:00Z

## Mission
Investigate Audio, Wake Word, TTS, and STT components for JARVIS Sprint 2 (v4.7.0) and produce a comprehensive 5-component handoff report.

## 🔒 My Identity
- Archetype: explorer
- Roles: Audio & TTS Explorer
- Working directory: d:\Software GitCode\JARVIS\.agents\explorer_survey_audio_tts
- Original parent: 9506425c-ec6d-40db-a68f-f37c461f99fc
- Milestone: Sprint 2 Survey & Architecture

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Focus on wake_word.py, app.py, tts/manager.py, stt/engine.py, unit tests
- Handoff report in handoff.md with 5 components

## Current Parent
- Conversation ID: 9506425c-ec6d-40db-a68f-f37c461f99fc
- Updated: 2026-09-02T07:35:00Z

## Investigation State
- **Explored paths**:
  - `jarvis/audio/wake_word.py` (Multi-tier Vosk/Whisper/Acoustic, VAD, SFM/ZCR thresholds)
  - `jarvis/core/app.py` (Audio loop, voice interaction, echo suppression gaps)
  - `jarvis/audio/dsp.py` (RMS calculation, noise floor tracking, Schmitt trigger)
  - `jarvis/tts/manager.py` & `jarvis/tts/fallback.py` (TTS worker thread, SAPI5 COM safety)
  - `jarvis/stt/engine.py` (FasterWhisper lazy load, preloading, vad_filter)
  - `tests/unit/test_wake_word.py`, `test_wake_word_p0.py`, `test_dsp.py`, `test_tts_engines.py`, `test_stt_engine.py`
- **Key findings**:
  - Echo suppression currently only uses a sleep in voice loop while mic frames are still actively captured into ring buffer. Needs 2.5s frame discard window.
  - VAD filter before wake word detection can discard silence frames with RMS < 0.003, saving CPU.
  - TTS worker thread needs `pythoncom.CoInitialize()` and `CoUninitialize()` in finally block.
  - Faster-Whisper requires eager background preload thread and `vad_filter=True` + `vad_parameters={"min_silence_duration_ms": 500}`.
- **Unexplored areas**: None (Investigation complete).

## Key Decisions Made
- Formulated concrete implementation strategies and pseudo-code for R1, R2, and R3.
- Defined verification suite with 3 new unit test modules (`test_acoustic_hardening.py`, `test_tts_com_safety.py`, `test_stt_preload.py`).

## Artifact Index
- `handoff.md` — Comprehensive investigation report
- `progress.md` — Liveness heartbeat and task progress
- `DISPATCH.md` — Inbound instructions log
