# Progress - Worker M1 (Safe Preprocessing Diacritic Normalization)

Last visited: 2026-09-03T15:38:00Z
Current Status: Milestone M1 implementation complete. All tests passing. Handoff report ready.

## Completed Steps
- [x] Initialized DISPATCH.md, BRIEFING.md, progress.md.
- [x] Read and analyzed `ORIGINAL_REQUEST.md`, `PROJECT.md`, `explorer_survey_router/handoff.md`, `explorer_survey_eval/handoff.md`.
- [x] Inspected existing `jarvis/llm/router.py` around `_match_rule_key`, `IntentRouter.__init__`, and `parse_intent`.
- [x] Inspected existing `tests/eval/stt_intent_eval.py` around `predict_intent`.
- [x] Implemented `strip_vietnamese_diacritics` and safe two-class `_match_rule_key` in `jarvis/llm/router.py`.
- [x] Precomputed stripped keys, word counts, and regex pattern cache in `IntentRouter.__init__`.
- [x] Added `clean_lower_stripped` one-time computation and `self.llm is None` guard in `parse_intent`.
- [x] Synced `predict_intent` in `tests/eval/stt_intent_eval.py`.
- [x] Verified unit test assertions (accents, zero homophone collisions, prompt test cases).
- [x] Verified all 144 Vietnamese vowel forms across NFC and NFD + `đ/Đ` -> `d/D`.
- [x] Ran pytest test suite: `pytest tests/unit/test_router_p0.py tests/test_adversarial_m1_intent_router.py -q` (0 failures).
- [x] Ran full routing eval suite: `python tests/eval/routing_eval_n150.py` (148/148 = 100% CORRECT, 278 passed in full pytest suite).
- [x] Generated comprehensive handoff report in `d:\Software GitCode\JARVIS\.agents\worker_m1\handoff.md`.
