# Progress — worker_m1_fix

Last visited: 2026-09-03T16:03:00Z

## Completed Work
1. Re-read dispatch, reviewer findings (Finding 1 & 2), and auditor caveats.
2. Verified root cause of ReDoS latency on 50KB strings: eager invocation of `strip_vietnamese_diacritics` on full `clean_lower` string in `parse_intent` without length guard.
3. Implemented length guard at line 2408 in `parse_intent`:
   `clean_lower_stripped = strip_vietnamese_diacritics(clean_lower) if len(clean_lower) <= 2048 else None`
4. Implemented secondary guard in `_match_rule_key` under `if clean_lower_stripped is None:`:
   `if len(clean_lower) > 2048: return False`
5. Verified `pytest tests/test_adversarial_m2_llm_router.py -k test_adversarial_massive_strings_and_redos_resistance -v` passes with exit code 0.
6. Verified `pytest tests/unit/test_router_p0.py tests/test_adversarial_m1_intent_router.py -q` passes (203 passed, 0 failed).
7. Verified `python tests/eval/routing_eval_n150.py`:
   - Text routing eval: 148/148 = 100.0% CORRECT, 0 SILENT_FAILURE, 0 MISROUTED.
   - Pytest validation suite: 278 passed, 6 skipped, 0 failed.
8. Writing final handoff report `handoff.md`.
