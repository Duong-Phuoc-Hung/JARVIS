## 2026-09-02T07:31:42Z

User Request:
You are the UI, Hardware & Eval Explorer for JARVIS Sprint 2 (v4.7.0).
Your working directory is: `d:\Software GitCode\JARVIS\.agents\explorer_survey_ui_hardware_eval`
Please read `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md` (mandatory source of truth).

Your objective is to investigate UI overlay, system tray, hardware reporter, LLM router, and test suite:
1. Examine `jarvis/ui/overlay.py`, `jarvis/ui/tray.py`, `jarvis/core/app.py`:
   - How does `AlwaysOnOverlay` operate? Is it thread-isolated? Are Tkinter GUI calls marshaled via `after()` or thread queues?
   - How is the system tray implemented? How to add the "Status" menu item (version, TTS status, STT model status, RAM usage) alongside existing Wake Word, Mic, Exit controls?
2. Examine `jarvis/hardware/reporter.py` and `jarvis/llm/router.py`:
   - How does `HardwareReporter.format_voice_summary()` work? Does it return Vietnamese CPU%, RAM%, GPU temp?
   - How does `Tier1RuleRouter` match rules? What regex/keyword patterns are needed for:
     "cpu mấy phần trăm", "ram còn bao nhiêu", "nhiệt độ máy", "pin còn bao nhiêu", "tốc độ cpu" -> `system_status`?
3. Examine test harnesses:
   - `tests/eval/routing_eval_n150.py`, `tests/unit/`, `tests/test_adversarial_*.py`
   - How are tests currently structured and run?
4. Provide precise implementation strategy and architectural recommendations.

Write your comprehensive report to:
`d:\Software GitCode\JARVIS\.agents\explorer_survey_ui_hardware_eval\handoff.md`
Maintain `progress.md` in your working directory.
When done, send a message back to the parent orchestrator with a summary and path to your handoff report.
