# DISPATCH — Reviewer M1-1

You are a Reviewer agent conducting independent review of Milestone 1 (Safe Preprocessing Diacritic Normalization) for JARVIS Voice Pipeline Upgrade (v4.8.1).
Your working directory is: `d:\Software GitCode\JARVIS\.agents\reviewer_m1_1\`

## Mandatory Reading
1. `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md` (section `2026-09-03T15:09:08Z`)
2. `d:\Software GitCode\JARVIS\.agents\orchestrator_4\PROJECT.md`
3. `d:\Software GitCode\JARVIS\.agents\worker_m1\handoff.md`

## Review Focus
1. Inspect code changes made in `jarvis/llm/router.py` and `tests/eval/stt_intent_eval.py`.
2. Verify correctness and completeness of `strip_vietnamese_diacritics`:
   - All Vietnamese vowel forms (a, ă, â, e, ê, i, o, ô, ơ, u, ư, y with 5 tone marks) in NFC and NFD.
   - `đ` -> `d`, `Đ` -> `D`.
   - ASCII, numbers, whitespace, punctuation preserved.
3. Verify two-class token matching in `_match_rule_key`:
   - Single-word rules (`len(words) == 1`): diacritics preserved, whole-token boundary enforced `(?:\b|^)key(?:\b|$)`.
   - Multi-word rules (`len(words) >= 2`): diacritic folding enabled with word boundary verification.
   - Homophone collision prevention: test `"nhạc"` vs `"nhắc"`, `"dừng"` vs `"dụng"`, `"dán"` vs `"dẫn"`.
4. Verify sync of `predict_intent` in `tests/eval/stt_intent_eval.py`:
   - Calls `_ROUTER.parse_intent(t, force_llm=False)`.
   - Maps `unknown_intent` -> `"NO_INTENT"`.
5. Run test verification and output your report to `d:\Software GitCode\JARVIS\.agents\reviewer_m1_1\handoff.md` with a clear verdict: `APPROVE` or `REQUEST_CHANGES`.

## 2026-09-03T15:39:50Z
You are Reviewer M1-1 reviewing Milestone 1 for JARVIS Voice Pipeline Upgrade (v4.8.1).
Your working directory is: `d:\Software GitCode\JARVIS\.agents\reviewer_m1_1\`.
Read `d:\Software GitCode\JARVIS\.agents\reviewer_m1_1\DISPATCH.md`.
Read `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md` (section `2026-09-03T15:09:08Z`).
Read `d:\Software GitCode\JARVIS\.agents\orchestrator_4\PROJECT.md`.
Read `d:\Software GitCode\JARVIS\.agents\worker_m1\handoff.md`.
Review code changes in `jarvis/llm/router.py` and `tests/eval/stt_intent_eval.py`. Run tests.
Deliver your report with verdict (APPROVE or REQUEST_CHANGES) to `d:\Software GitCode\JARVIS\.agents\reviewer_m1_1\handoff.md` and send message when done.

