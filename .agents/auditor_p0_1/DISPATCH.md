# Dispatch: Forensic Auditor P0 (Integrity Verification of P0 Subsystems)

## Task Description
- Working Directory: `d:\Software GitCode\JARVIS\.agents\auditor_p0_1\`
- Read `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md` verbatim.
- Read `d:\Software GitCode\JARVIS\PROJECT.md`.
- Conduct exhaustive forensic integrity verification of all P0 implementations:
  1. `jarvis/audio/wake_word.py`: Check for genuine DSP/Vosk/Whisper streaming algorithms, absence of hardcoded trigger strings or dummy bypasses.
  2. `jarvis/workers/proactive.py`: Check that `ProactiveEngine` genuinely coordinates reminders, evaluates real/mock hardware metrics, and registers actions.
  3. `jarvis/llm/router.py`: Check that regexes and Tier-2 LLM fallback perform authentic parsing and API client interaction.
  4. Verify zero prohibited patterns (no hardcoded test outputs, no facade stubs, no fake benchmark outputs).
  5. Run test verification:
     - `pytest tests/unit/test_wake_word_p0.py tests/unit/test_proactive_engine_p0.py tests/unit/test_router_p0.py -v`
     - `pytest tests/e2e/test_v460_e2e.py -v`
- Deliver verdict: `CLEAN` or `INTEGRITY VIOLATION` with evidence in `handoff.md`.
