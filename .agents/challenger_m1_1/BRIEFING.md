# BRIEFING — 2026-09-03T15:40:00Z

## Mission
Adversarial empirical challenge of Milestone 1 (Safe Preprocessing Diacritic Normalization v4.8.1) in `jarvis/llm/router.py` and `tests/eval/stt_intent_eval.py`: homophone protection, diacritic permutations, boundary matching, NFC/NFD robustness, ReDoS/DoS resistance.

## 🔒 My Identity
- Archetype: EMPIRICAL CHALLENGER
- Roles: critic, specialist
- Working directory: d:/Software GitCode/JARVIS/.agents/challenger_m1_1
- Original parent: 88e315c1-4bbc-4194-bae5-c1ca88628303
- Milestone: M1 (Voice AI Pipeline Bug Fixes & Stabilization)
- Instance: 1 of 1
- Current parent: 8def6a90-7f5e-498d-8141-0070b9751330
- Current Milestone: M1 (Safe Preprocessing Diacritic Normalization - Voice Pipeline Upgrade v4.8.1)

## 🔒 Key Constraints
- Review-only & verification: do NOT modify implementation code directly
- Must empirically verify all claims via code execution and stress testing
- Provide concrete evidence chain and reproduction scripts
- Layout Compliance: .agents/ holds only metadata; tests placed in tests/

## Current Parent
- Conversation ID: 8def6a90-7f5e-498d-8141-0070b9751330
- Updated: 2026-09-03T15:40:00Z

## Review Scope
- **Files to review**:
  - `jarvis/llm/router.py` (`strip_vietnamese_diacritics`, `_match_rule_key`, `parse_intent`)
  - `tests/eval/stt_intent_eval.py` (`predict_intent`)
- **Interface contracts**: `PROJECT.md`, `ORIGINAL_REQUEST.md` (R1)
- **Review criteria**:
  - Diacritic normalization coverage (all vowels, NFC, NFD, `đ/Đ`)
  - Single-word homophone collision elimination (`nhạc` vs `nhắc`, `dừng` vs `dụng`, `dán` vs `dẫn`, `báo` vs `bảo`, `tắt` vs `tắc`)
  - Multi-word diacritic folding and token boundary regex isolation
  - `predict_intent` contract synchronization with production router
  - ReDoS / massive input SLA (< 20ms)

## Attack Surface
- **Hypotheses tested**:
  - Hypothesis 1: `strip_vietnamese_diacritics` handles all 134+ Vietnamese vowels across NFC and NFD, casing, punctuation, and non-Vietnamese unicode without corruption.
  - Hypothesis 2: Single-word tokens with diacritics are strictly preserved and never collide with unaccented substrings or alternate tones.
  - Hypothesis 3: Multi-word phrases correctly fold diacritics regardless of NFC/NFD, casing, and surrounding punctuation, without false-positive subword matching.
  - Hypothesis 4: Homophone test utterances (`nhạc`/`nhắc`, `dừng`/`dụng`, `dán`/`dẫn`, `báo`/`bảo`, `tắt`/`tắc`) do not misroute or cross-trigger.
  - Hypothesis 5: `predict_intent` in `stt_intent_eval.py` accurately mirrors `_ROUTER.parse_intent` and correctly yields `NO_INTENT` for unknown utterances.
  - Hypothesis 6: Sub-millisecond performance and ReDoS resilience under extreme load / adversarial payloads.
- **Vulnerabilities found**: [TBD after empirical execution]
- **Untested angles**: [TBD]

## Loaded Skills
- None required.

## Key Decisions Made
- Designing comprehensive adversarial test suite `tests/test_adversarial_m1_diacritic_homophones.py` to empirically stress-test all dimensions.

## Artifact Index
- `.agents/challenger_m1_1/DISPATCH.md` — Incoming instructions
- `.agents/challenger_m1_1/BRIEFING.md` — Active working memory
- `.agents/challenger_m1_1/progress.md` — Liveness heartbeat
- `.agents/challenger_m1_1/handoff.md` — Final empirical report & verdict
