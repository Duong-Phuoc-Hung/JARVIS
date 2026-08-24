## 2026-08-24T01:16:04Z

You are Worker M6 for the JARVIS Personal AI Expansion project.
Your working directory is `d:/Software GitCode/JARVIS/.agents/worker_m6/`.
The workspace is `d:/Software GitCode/JARVIS`.
You MUST read `d:/Software GitCode/JARVIS/.agents/ORIGINAL_REQUEST.md` and `d:/Software GitCode/JARVIS/PROJECT.md`.
Also read Explorer 3 survey report at `d:/Software GitCode/JARVIS/.agents/explorer_survey_3/survey_report.md`.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your Mission — Milestone 6: Always-On Intelligent Overlay HUD (R8):
1. Upgrade `jarvis/ui/overlay.py`:
   - `AlwaysOnOverlay` (or upgraded `JarvisOverlay` with backwards-compatible aliases):
     - **Sidebar Mode**: Dockable to right side of screen (380px width, expandable/collapsible to 40px ribbon, draggable, `attributes('-topmost', True)`, alpha transparency).
     - **5-Turn Conversation History**: Scrollable/stacked card display showing user queries and JARVIS responses for the last 5 turns.
     - **Quick Action Buttons**: Interactive HUD buttons for "Briefing Sáng", "System Status", "Focus Mode", "Tối giản / Thu gọn".
     - **Memory Facts Preview**: Widget displaying top 3 persistent facts JARVIS remembers about the user.
     - **5s Realtime Status Bar**: Live CPU %, RAM %, and Battery % (via `GetSystemPowerStatus` or `psutil`/`HardwareMonitor`) updated on 5s tick.
     - **Audio Waveform Spectrum Analyzer**: 11-bar Canvas dynamic waveform visualizer animating when JARVIS is listening or speaking.
     - **Floating Arc Reactor Icon**: Minimize mode to a compact floating Arc Reactor icon at screen corner.
     - **Thread Safety & Headless Tolerance**: All UI mutations scheduled via Tkinter event queue (`root.after`), headless CI environments gracefully handle missing DISPLAY/X11/Win32 GUI.
2. Write unit tests in `tests/unit/test_always_on_overlay.py`:
   - Test overlay state transitions (IDLE, LISTENING, THINKING, RESPONSE, HIDDEN).
   - Test sidebar mode docking, expand (380px) and collapse (40px).
   - Test conversation history queue (up to 5 turns tracking and formatting).
   - Test quick action button callbacks.
   - Test memory facts preview updates.
   - Test status bar telemetry updates (CPU, RAM, Battery).
   - Test waveform audio level updates.
   - Test headless mode and thread safety.
3. Run `pytest tests/unit/test_always_on_overlay.py -v` and verify 100% pass rate.
4. Write your completion report to `d:/Software GitCode/JARVIS/.agents/worker_m6/handoff.md`.

Exclusive Write Boundaries:
- `jarvis/ui/overlay.py`
- `tests/unit/test_always_on_overlay.py`
