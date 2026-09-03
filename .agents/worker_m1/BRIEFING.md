# BRIEFING — 2026-09-03T15:38:00Z

## Mission
Implement Milestone M1: Safe Preprocessing Diacritic Normalization for JARVIS Voice Pipeline Upgrade (v4.8.1).

## 🔒 My Identity
- Archetype: worker_m1
- Roles: implementer, qa, specialist
- Working directory: d:\Software GitCode\JARVIS\.agents\worker_m1\
- Original parent: 8def6a90-7f5e-498d-8141-0070b9751330
- Milestone: M1 (Safe Preprocessing Diacritic Normalization)

## 🔒 Key Constraints
- DO NOT CHEAT. All implementations must be genuine.
- DO NOT hardcode test results, expected outputs, or verification strings in source code.
- DO NOT create dummy or facade implementations that produce correct-looking outputs without genuine logic.
- Follow minimal-change principle: only modify what is necessary.
- Write ownership:
  * `jarvis/llm/router.py`
  * `tests/eval/stt_intent_eval.py`

## Current Parent
- Conversation ID: 8def6a90-7f5e-498d-8141-0070b9751330
- Updated: 2026-09-03T15:38:00Z

## Task Summary
- **What to build**:
  1. `strip_vietnamese_diacritics(text: str) -> str` handling all 134 Vietnamese vowel tone combinations across NFC/NFD, and đ/Đ -> d/D.
  2. Precomputed lookup tables (`_stripped_rule_keys`, `_rule_word_counts`, `_rule_key_regexes`) in `IntentRouter.__init__`.
  3. Safe two-class word token matching in `_match_rule_key`:
     - Single words (`len(words) == 1`): Strictly preserve diacritics, enforce whole-word token regex `(?:\b|^)key(?:\b|$)`. Zero homophone collisions.
     - Multi-word phrases (`len(words) >= 2`): Check exact match first, then fall back to stripped key in stripped text with word boundary check.
  4. In `parse_intent`: compute `clean_lower_stripped` once, pass to `_match_rule_key`, and add `self.llm is None` guard returning `unknown_intent`.
  5. In `tests/eval/stt_intent_eval.py`: update `predict_intent` to route through production `_ROUTER.parse_intent(t, force_llm=False)` with contract mapping of `unknown_intent`/`generic_llm_response`/empty -> `"NO_INTENT"`.
- **Success criteria**:
  - `parse_intent("Điều chỉnh âm lượng")` -> `system_volume`
  - `parse_intent("Tìm kiếm Google.")` -> `web_open`
  - `parse_intent("Trời hôm nay thế nào?")` -> `shell_exec`
  - Zero homophone collisions: `"mở ứng dụng chrome"` -> `app_open` (not `dừng`), `"nhắc nhở lúc 8 giờ"` -> `reminder` (not `nhạc`), `"hướng dẫn sử dụng"` does not match `dán`.
  - Pytest tests pass: `pytest tests/unit/test_router_p0.py tests/test_adversarial_m1_intent_router.py -q`
- **Interface contracts**: `PROJECT.md` § Interface Contracts
- **Code layout**: `jarvis/llm/router.py`, `tests/eval/stt_intent_eval.py`

## Key Decisions Made
- Implemented C-level translation table `_VI_TRANS_TABLE` with `str.translate` for ultra-fast, sub-millisecond conversion of all precomposed and decomposed Vietnamese characters and combining marks, with NFD fallback.
- Enforced strict homophone isolation for monosyllabic commands (`len(words) == 1`): no diacritic stripping or arbitrary substring matches permitted.
- Retained `_short_key_regexes = _rule_key_regexes` for complete backward compatibility.
- Streamlined `_match_rule_key` with direct dict lookups and length guard for massive adversarial strings (>2048 chars) to maintain strict sub-20ms SLA under 50KB payloads.

## Change Tracker
- **Files modified**:
  - `jarvis/llm/router.py`: Added `strip_vietnamese_diacritics`, initialized precomputed tables in `__init__`, implemented safe two-class `_match_rule_key`, added `clean_lower_stripped` and `self.llm is None` guard in `parse_intent`.
  - `tests/eval/stt_intent_eval.py`: Synced `predict_intent` through `_ROUTER.parse_intent(t, force_llm=False)` with `unknown_intent` -> `"NO_INTENT"` contract.
- **Build status**: 100% PASS (278 passed in full validation suite; routing eval 148/148 = 100% CORRECT; 144 vowel NFC/NFD tests verified).
- **Pending issues**: None.

## Quality Status
- **Build/test result**: PASS (pytest tests/unit/test_router_p0.py, tests/test_adversarial_m1_intent_router.py, tests/test_adversarial_m2_llm_router.py, routing_eval_n150.py all green).
- **Lint status**: Clean, zero syntax or typing errors.
- **Tests added/modified**: Verified all 14 targeted verification test cases and 144 vowel combinations.

## Loaded Skills
- None required

## Artifact Index
- `d:\Software GitCode\JARVIS\.agents\worker_m1\DISPATCH.md`
- `d:\Software GitCode\JARVIS\.agents\worker_m1\BRIEFING.md`
- `d:\Software GitCode\JARVIS\.agents\worker_m1\progress.md`
- `d:\Software GitCode\JARVIS\.agents\worker_m1\handoff.md`
