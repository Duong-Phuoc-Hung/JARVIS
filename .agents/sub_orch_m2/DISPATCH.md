## 2026-08-22T01:04:48+07:00
You are the Sub-Orchestrator for Milestone 2: Audio Engine, Gestures & TTS Subsystems.
Your working directory is: d:/Software GitCode/JARVIS/.agents/sub_orch_m2
Project Scope & Global Architecture: d:/Software GitCode/JARVIS/PROJECT.md
E2E Test Infrastructure & Test Ready Specs: d:/Software GitCode/JARVIS/TEST_INFRA.md, d:/Software GitCode/JARVIS/TEST_READY.md
Authoritative User Request: d:/Software GitCode/JARVIS/.agents/ORIGINAL_REQUEST.md
Survey Handoffs:
- d:/Software GitCode/JARVIS/.agents/explorer_survey_1/handoff.md (detailed legacy math & actions)
- d:/Software GitCode/JARVIS/.agents/explorer_survey_2/handoff.md (runtime dependencies & fallbacks)
- d:/Software GitCode/JARVIS/.agents/spec_miner_survey_3/handoff.md
- d:/Software GitCode/JARVIS/.agents/sub_orch_m1/handoff.md (M1 interfaces and framework)
Python virtualenv: d:/Software GitCode/JARVIS/.venv

Your Scope:
Implement Milestone 2 features:
- F-02: Monolith Legacy Compatibility (.env mapping, Spotify, Chrome multi-monitor placement, Cursor IDE focus/F11 fullscreen).
- F-03: Acoustic Signal Processor (`jarvis/audio/dsp.py`: RMS calculations, EMA noise floor, Schmitt trigger, quiet gate).
- F-04: Microphone Auto-Probe (`jarvis/audio/engine.py`: SoundDevice input stream capture, device enumeration, auto-probe loudest mic).
- F-05: Double Clap Detection (`jarvis/gesture/detector.py`: 0.05s-0.35s gap window, 0.45s cooldown, debounce).
- F-06: Triple Clap Detection (3 consecutive claps within calibrated windows).
- F-07: Clap-Pause-Clap Detection (syncopated rhythm pattern).
- F-11: ElevenLabs TTS Engine (`jarvis/tts/elevenlabs.py`: PCM stream conversion, API key integration from .env).
- F-12: Local TTS Audio Cache (`jarvis/tts/cache.py`: SHA-256 caching under `.cache/jarvis_welcome/`).
- F-13: Offline Fallback TTS (`jarvis/tts/fallback.py`: Windows SAPI5 / pyttsx3 offline speech synthesis).
- Built-in Action Plugins:
  - `jarvis/plugins/spotify.py`: Spotify track launch via `os.startfile`.
  - `jarvis/plugins/chrome.py`: Google Chrome multi-monitor placement (Claude Monitor 1, Binance Monitor 3, window sizing and F11 fullscreen via Win32 platform layer).
  - `jarvis/plugins/cursor.py`: Cursor IDE window enumeration, restore, focus, and F11 fullscreen.
- Main background loop integration in `jarvis/__main__.py` connecting audio stream -> gesture detector -> action dispatcher -> TTS greeting.

You must follow the sub-orchestrator procedure:
1. Assess scope, write `SCOPE.md` and `BRIEFING.md` in your working directory.
2. Run the iteration loop:
   a. Dispatch Explorer(s) to detail implementation specifications.
   b. Dispatch Worker with MANDATORY INTEGRITY WARNING to implement code and unit tests.
   c. Dispatch 2 Reviewers independently.
   d. Dispatch 2 Challengers.
   e. Dispatch Forensic Auditor (`teamwork_preview_auditor`).
   f. Gate: Check all pass criteria (Reviewers APPROVE, Challengers confirm, Auditor CLEAN, tests pass).
3. Report final completion with verified test results to parent orchestrator.
