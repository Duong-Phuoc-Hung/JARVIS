# DISPATCH — Challenger M1-1

## 2026-09-03T15:39:51Z

You are Challenger M1-1 verifying Milestone 1 for JARVIS Voice Pipeline Upgrade (v4.8.1).
Your working directory is: `d:\Software GitCode\JARVIS\.agents\challenger_m1_1\`.

## Mandatory Reading
1. `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md` (section `2026-09-03T15:09:08Z`)
2. `d:\Software GitCode\JARVIS\.agents\orchestrator_4\PROJECT.md`
3. `d:\Software GitCode\JARVIS\.agents\worker_m1\handoff.md`

## Challenge Objectives
1. Write and run stress/adversarial scripts to challenge `strip_vietnamese_diacritics` and `_match_rule_key` in `jarvis/llm/router.py`.
2. Specifically challenge homophone collision prevention:
   - Generate test utterances containing `nhạc` vs `nhắc`, `dừng` vs `dụng`, `dán` vs `dẫn`, `báo` vs `bảo`, `tắt` vs `tắc`.
   - Verify that single words with diacritics never collide with unaccented or alternate tone words.
3. Test combinations:
   - Polysyllabic phrase variations with mixed accents, decomposed NFD characters, uppercase/lowercase, trailing and leading punctuation.
4. Output your empirical test findings to `d:\Software GitCode\JARVIS\.agents\challenger_m1_1\handoff.md` with a clear verdict: `APPROVE` or `REQUEST_CHANGES`.
