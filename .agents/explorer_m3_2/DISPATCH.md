## 2026-08-22T16:25:19Z

Task: Technical Investigation & Implementation Blueprint for Milestone M3 Startup Intro & Interaction Logging.
Read:
- d:/Software GitCode/JARVIS/.agents/ORIGINAL_REQUEST.md (specifically R4, R6, and acceptance criteria)
- d:/Software GitCode/JARVIS/PROJECT.md (Milestone M3 & Code Layout)
- Code files: `jarvis/core/app.py`, `jarvis/tts/manager.py`, `config/default_config.yaml`

Analyze and specify exact implementation details for:
1. Vocal startup introduction in `app.py`:
   - In `JarvisApp.start()`, speak the exact phrase: `"Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS."` via `self.tts_manager.speak(..., wait=False)`.
   - Ensure it does not block application startup or crash if TTS is uninitialized/silent in tests.
2. Randomized greeting pool in `jarvis/tts/manager.py`:
   - Non-repeating random selection from configured greeting phrases in `config/default_config.yaml`.
3. Structured `[INTERACTION]` logging in `app.py` & `logs/jarvis.log`:
   - Ensure `logs/` directory exists.
   - Log format for every user interaction (voice command, text command, gesture trigger):
     `[INTERACTION] <timestamp> | TRIGGER: <trigger_type> | INPUT: <transcript/input> | ACTION: <action_name> | RESPONSE: <response_text> | STATUS: <success/failed>`
   - Write to both logger and dedicated `logs/jarvis.log` file safely.

Write your comprehensive blueprint to `d:/Software GitCode/JARVIS/.agents/explorer_m3_2/handoff.md`.
Send a completion message back to caller.
