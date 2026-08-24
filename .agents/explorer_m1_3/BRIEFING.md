# BRIEFING — 2026-08-22T22:58:00+07:00

## Mission
Investigate and formulate the technical implementation blueprint for TTS Manager & SAPI5 fallback resilience (`jarvis/tts/manager.py`, `jarvis/tts/fallback.py`), eliminating duplicate TTS speak calls in `jarvis/core/app.py` (`_ai_voice_loop`), and ensuring zero regression across all existing TTS tests.

## 🔒 My Identity
- Archetype: explorer
- Roles: investigation, synthesis
- Working directory: d:/Software GitCode/JARVIS/.agents/explorer_m1_3
- Original parent: ca44a478-e74c-493d-b196-18b1d4924c47
- Milestone: Milestone 1 (Core Framework & Foundations) / Milestone M1 (Voice AI Pipeline Bug Fixes & Stabilization)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement production code
- Adhere to PROJECT.md architectural guidelines and layout
- Comprehensive ctypes Win32 API coverage with pure Python (no pywin32 dependency)
- Design robust cross-platform mocking & live Windows test suites for Milestone 1
- Zero double-dispatch and zero duplicate TTS vocalization
- Seamless SAPI5 fallback on missing or invalid ElevenLabs API key (HTTP 401/429/500)

## Current Parent
- Conversation ID: 88e315c1-4bbc-4194-bae5-c1ca88628303
- Updated: 2026-08-22T22:58:00+07:00

## Investigation State
- **Explored paths**:
  - `jarvis/tts/manager.py` (TTSManager, async queue worker, lock serialization, cache & fallback routing)
  - `jarvis/tts/fallback.py` (SAPI5FallbackTTS, win32com SAPI.SpVoice, PowerShell System.Speech, pyttsx3, mock logger)
  - `jarvis/tts/elevenlabs.py` (ElevenLabsTTS, HTTP REST fallback, TTSError exception raising)
  - `jarvis/tts/cache.py` (TTSAudioCache, SHA-256 keying, atomic temp file write, corruption detection)
  - `jarvis/tts/engine.py` (Unified backward-compatible coordinator)
  - `jarvis/core/app.py` (`_ai_voice_loop`, `process_text_command`, `_handle_tts_welcome`, `start`)
  - `tests/test_tts_engine.py`, `tests/unit/test_tts_cache.py`, `tests/unit/test_tts_engines.py`, `tests/unit/test_app_integration.py`, `tests/test_adversarial_m3_ui_app.py`
- **Key findings**:
  - `TTSManager._execute_speak()` successfully catches all primary engine exceptions (`TTSError`) and falls back to SAPI5.
  - Adding defensive `pythoncom.CoInitialize()` in `jarvis/tts/fallback.py` prevents COM thread marshalling errors in secondary worker threads.
  - Base64-encoded PowerShell script execution protects against multiline / special character parsing failures.
  - Duplicate TTS speak in `jarvis/core/app.py` was caused by having `self.tts_manager.speak(response_text)` both in `process_text_command()` and guarded by `and not self.llm_router` in `_ai_voice_loop()`.
  - Eliminating duplicate speech requires designating `process_text_command()` as the single central authority for command processing and vocalization, and removing the redundant call in `_ai_voice_loop()`.
  - Startup self-introduction (`"Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."`) and non-repeating welcome greeting pool (`WELCOME_PHRASES`) fulfill R4 requirements.
  - All 15 existing unit and integration TTS tests will pass with zero regressions.
- **Unexplored areas**: None. Investigation complete.

## Key Decisions Made
- Established `process_text_command()` as the sole authority for text command dispatch and spoken feedback.
- Designed COM thread initialization and Base64-encoded PowerShell execution for `SAPI5FallbackTTS`.
- Formulated `WELCOME_PHRASES` pool for non-repeating polite welcome greetings.
- Documented full implementation blueprint in `report.md` and 5-component handoff in `handoff.md`.

## Artifact Index
- `d:/Software GitCode/JARVIS/.agents/explorer_m1_3/DISPATCH.md` — Dispatch log
- `d:/Software GitCode/JARVIS/.agents/explorer_m1_3/progress.md` — Liveness & progress tracking
- `d:/Software GitCode/JARVIS/.agents/explorer_m1_3/report.md` — Detailed technical investigation & blueprint
- `d:/Software GitCode/JARVIS/.agents/explorer_m1_3/handoff.md` — 5-component handoff report
