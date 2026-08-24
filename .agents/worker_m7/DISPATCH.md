## 2026-08-24T01:21:34Z
You are Worker M7 (Master Integration & QA Engineer) for the JARVIS Personal AI Expansion project.
Your working directory is `d:/Software GitCode/JARVIS/.agents/worker_m7/`.
The workspace is `d:/Software GitCode/JARVIS`.
You MUST read `d:/Software GitCode/JARVIS/.agents/ORIGINAL_REQUEST.md`, `d:/Software GitCode/JARVIS/PROJECT.md`, and `d:/Software GitCode/JARVIS/TEST_READY.md`.
Read all worker handoffs:
- `d:/Software GitCode/JARVIS/.agents/worker_m1/handoff.md` (Wake Word)
- `d:/Software GitCode/JARVIS/.agents/worker_m2/handoff.md` (Memory & Context)
- `d:/Software GitCode/JARVIS/.agents/worker_m3/handoff.md` (Vision & Web Intelligence)
- `d:/Software GitCode/JARVIS/.agents/worker_m4/handoff.md` (Control & Shell)
- `d:/Software GitCode/JARVIS/.agents/worker_m5/handoff.md` (Proactive Engine)
- `d:/Software GitCode/JARVIS/.agents/worker_m6/handoff.md` (Always-On Overlay)

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your Mission — Milestone 7: Master Integration, CLI Diagnostics & Regression Verification (R9):
1. Wire all subsystems into `jarvis/core/app.py` (`JarvisApp`):
   - Instantiate `WakeWordDetector` in `AudioEngine` or `JarvisApp.initialize()`, subscribe it to incoming audio frames, wire its callback to trigger overlay listening mode ("Vâng thưa Ngài") in parallel with double clap.
   - Instantiate `MemoryManager` (`logs/memory.db`) and inject it into `LLMIntentRouter` and `ActionDispatcher`.
   - Instantiate `ScreenVisionManager` (`jarvis/vision/screen.py`).
   - Instantiate `WebIntelligenceHub` (`jarvis/web/hub.py`).
   - Instantiate `ComputerController`, `ShellAssistant`, `SafetyGate` (`jarvis/automation/`).
   - Instantiate `ProactiveEngine` (`jarvis/proactive/engine.py`) and wire to `JarvisApp` lifecycle (`start()` and `stop()`).
   - Instantiate `AlwaysOnOverlay` (`jarvis/ui/overlay.py`), bind status updates, quick action buttons, and memory preview.
   - Update `process_text_command()` in `jarvis/core/app.py` to record turn in `SessionContextManager` and `SQLiteMemoryStore.log_episode()`, feed overlay cards, and update inactivity timestamp.
2. Update `jarvis/core/config.py`:
   - Add configuration fields and defaults for wake word, memory, vision, web intelligence, automation safety gate, and proactive intelligence toggles.
3. Update `jarvis/cli.py` (`run_health_check()`):
   - Add diagnostic health checks for:
     - Wake Word Engine (acoustic & local detector availability)
     - Persistent Memory SQLite Database (`logs/memory.db`)
     - Vision Subsystem & Screen Capture (mss/PIL)
     - Web Intelligence Hub & Network Providers
     - Computer Control & Win32 Automation APIs
     - Proactive Intelligence Engine
     - Always-On Overlay UI Subsystem
   - Ensure `python -m jarvis health-check` returns all green diagnostics and exits with code 0.
4. Implement `tests/unit/test_integration_e2e.py` with comprehensive integration tests verifying `JarvisApp` boots cleanly, all subsystems are wired, health-check passes, and commands route seamlessly.
5. Run the FULL test suite: `pytest tests/ -v`.
   - Verify that all 537+ baseline tests pass without regression.
   - Verify that all new unit tests and E2E tests pass (total tests >= 557).
   - Run `python -m jarvis health-check` and verify all green.
6. Write a comprehensive completion report to `d:/Software GitCode/JARVIS/.agents/worker_m7/handoff.md`.

Exclusive Write Boundaries:
- `jarvis/core/app.py`
- `jarvis/core/config.py`
- `jarvis/cli.py`
- `tests/unit/test_integration_e2e.py`
