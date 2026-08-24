## 2026-08-22T16:46:19Z
You are Explorer 2 for Milestone M4 (Automated User Simulation Test Suite & Full Regression).
Your working directory is `d:/Software GitCode/JARVIS/.agents/explorer_m4_2`. Create your directory and write your findings to `d:/Software GitCode/JARVIS/.agents/explorer_m4_2/analysis.md` and `d:/Software GitCode/JARVIS/.agents/explorer_m4_2/handoff.md`.

Read:
- `d:/Software GitCode/JARVIS/.agents/ORIGINAL_REQUEST.md`
- `d:/Software GitCode/JARVIS/PROJECT.md`
- `d:/Software GitCode/JARVIS/jarvis/ui/overlay.py`
- `d:/Software GitCode/JARVIS/jarvis/stt/engine.py`
- `d:/Software GitCode/JARVIS/jarvis/llm/router.py`
- `d:/Software GitCode/JARVIS/jarvis/tts/manager.py`
- `d:/Software GitCode/JARVIS/jarvis/tts/fallback.py`

Mission:
Investigate how to write pytest simulation tests for:
1. Overlay state transitions: `IDLE` -> `LISTENING` -> `THINKING` -> `RESPONSE` -> `HIDDEN` (with breathing animation, typing dots, tooltip hint "💡 Double clap để hỏi tiếp").
2. Overlay thread safety and stability over 10+ consecutive `show_listening()` / `show_thinking()` / `show_response()` / `hide()` cycles without hanging or crashing.
3. STT fallback: when Whisper API key is missing / invalid, falls back gracefully (mock / web_speech) without crash.
4. LLM Smart Keyword Router in Vietnamese: test 7 categories ("bật/tắt đèn" -> smart home, "nhiệt độ/CPU/RAM" -> system status, "mở Spotify/nhạc" -> spotify, "thời tiết" -> weather, "nhắc nhở" -> reminder, "tắt máy/restart" -> power with safety flag, and default fallback).
5. TTS fallback: when ElevenLabs key is invalid, cascades to SAPI5 fallback without crashing.
6. Full end-to-end pipeline in mock mode completes in < 10.0 seconds.

Provide exact test designs and assertions for `tests/test_user_simulation.py`.
Report your findings in handoff.md.
