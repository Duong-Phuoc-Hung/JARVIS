## 2026-08-22T05:05:37Z

You are Worker M3-2 (Remediation & Polish for Milestone 3).
Your working directory is: d:/Software GitCode/JARVIS/.agents/worker_m3_2/
Project Root: d:/Software GitCode/JARVIS/
Project Scope: d:/Software GitCode/JARVIS/PROJECT.md
Original Requirements: d:/Software GitCode/JARVIS/.agents/ORIGINAL_REQUEST.md
Python virtualenv: d:/Software GitCode/JARVIS/.venv (e.g. d:\Software GitCode\JARVIS\.venv\Scripts\pytest)

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Your Task:
Reviewer 2 identified 3 specific edge-case fixes needed for Milestone 3:
1. `jarvis/stt/__init__.py`:
   - Add `WindowsSpeechSTT` to the top-level import statement (`from jarvis.stt.engine import (...)`) so it matches `__all__`.
2. `jarvis/llm/router.py`:
   - In `generate_tool_schema_from_dispatcher()`, ensure nested collection type annotations (e.g., `List[Dict[...]]`) map to `"type": "array"` rather than `"object"`. Use `typing.get_origin(ann)` or check `list`/`List` container origin before checking inner type substrings.
3. `jarvis/ui/dashboard.py`:
   - Set `request_queue_size = 128` on `ThreadingHTTPServer` (or subclass) so high-concurrency connection floods (>60 threads) do not saturate the TCP listen backlog.
4. Also check `tests/unit/test_ui_dashboard.py` if any fixture needs direct return instead of `yield` for custom runner compatibility.
5. Run the full test suite using `.venv/Scripts/pytest` to verify all tests pass:
   `& "d:/Software GitCode/JARVIS/.venv/Scripts/pytest" tests/ tests/unit/ -v`
6. Write your handoff report to `d:/Software GitCode/JARVIS/.agents/worker_m3_2/handoff.md` and send a message to parent when done.
