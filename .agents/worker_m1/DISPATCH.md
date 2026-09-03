# DISPATCH — Worker Milestone 1: Safe Preprocessing Diacritic Normalization

You are a Worker agent implementing Milestone 1 for JARVIS Voice Pipeline Upgrade (v4.8.1).
Your working directory is: `d:\Software GitCode\JARVIS\.agents\worker_m1\`

## Mandatory Reading
Read these files before starting:
1. `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md` (section `2026-09-03T15:09:08Z`)
2. `d:\Software GitCode\JARVIS\.agents\orchestrator_4\PROJECT.md`
3. `d:\Software GitCode\JARVIS\.agents\explorer_survey_router\handoff.md`
4. `d:\Software GitCode\JARVIS\.agents\explorer_survey_eval\handoff.md`

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Write Ownership
You exclusively own and may edit:
- `jarvis/llm/router.py`
- `tests/eval/stt_intent_eval.py`

## Implementation Tasks
1. In `jarvis/llm/router.py`:
   - Implement `strip_vietnamese_diacritics(text: str) -> str`:
     - Must handle all 134 Vietnamese vowel-tone combinations across both NFC and NFD Unicode representations.
     - Must convert `đ` -> `d` and `Đ` -> `D`.
     - Preserves all ASCII characters, whitespace, numbers, and punctuation.
   - Precompute in `IntentRouter.__init__`:
     - `self._stripped_rule_keys: dict[str, str] = {k: strip_vietnamese_diacritics(k) for k in self.rule_engine}`
     - `self._rule_word_counts: dict[str, int] = {k: len(k.strip().split()) for k in self.rule_engine}`
     - `self._rule_key_regexes: dict[str, re.Pattern] = {}`
   - Implement `_match_rule_key(self, key: str, clean_lower: str, clean_lower_stripped: str | None = None) -> bool`:
     - `len(words) == 1`: Strictly preserve diacritics, enforce whole-word token regex boundary `(?:\b|^)key(?:\b|$)`. NEVER strip diacritics or perform substring match. Zero homophone collisions (`nhạc` vs `nhắc`, `dừng` vs `dụng`, `dán` vs `dẫn`).
     - `len(words) >= 2`: Check exact match first, then fall back to stripped key in stripped text with word boundary verification.
   - In `parse_intent`:
     - Compute `clean_lower_stripped = strip_vietnamese_diacritics(clean_lower)` once per query.
     - Pass `clean_lower_stripped` to `_match_rule_key`.
     - Ensure fallback guard if `self.llm is None` returns `unknown_intent` without unhandled exception.
2. In `tests/eval/stt_intent_eval.py`:
   - Update `predict_intent(transcript: str) -> str`:
     - Route transcript through `_ROUTER.parse_intent(t, force_llm=False)`.
     - Map `res.action_name in ("unknown_intent", "generic_llm_response")` or empty back to `"NO_INTENT"` so `classify_outcome()` treats unmatched utterances as `ROUTER_ABSTAIN`.
     - Keep English/ASCII keyword fallback dictionary.
3. Verification:
   - Run unit tests to verify:
     - `parse_intent("Điều chỉnh âm lượng")` -> `system_volume`
     - `parse_intent("Tìm kiếm Google.")` -> `web_open`
     - `parse_intent("Trời hôm nay thế nào?")` -> `shell_exec`
     - `"mở ứng dụng chrome"` -> `app_open` (not `system_power` via `dừng`)
     - `"nhắc nhở lúc 8 giờ"` -> `reminder` (not `spotify` via `nhạc`)
     - `"hướng dẫn sử dụng"` does not route to `clipboard_paste` (via `dán`)
   - Run relevant pytest tests: `pytest tests/unit/test_router_p0.py tests/test_adversarial_m1_intent_router.py -q`
   - Document all verification commands and outputs in `d:\Software GitCode\JARVIS\.agents\worker_m1\handoff.md`.

## 2026-09-03T15:19:05Z
You are a Worker agent implementing Milestone 1 for JARVIS Voice Pipeline Upgrade (v4.8.1).
Your working directory is: `d:\Software GitCode\JARVIS\.agents\worker_m1\`.
Read your assignment in `d:\Software GitCode\JARVIS\.agents\worker_m1\DISPATCH.md`.
Read `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md` (section `2026-09-03T15:09:08Z`).
Read `d:\Software GitCode\JARVIS\.agents\orchestrator_4\PROJECT.md`.
Read `d:\Software GitCode\JARVIS\.agents\explorer_survey_router\handoff.md`.
Read `d:\Software GitCode\JARVIS\.agents\explorer_survey_eval\handoff.md`.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Implement:
1. `strip_vietnamese_diacritics` and safe two-class `_match_rule_key` in `jarvis/llm/router.py`.
2. Sync `predict_intent` in `tests/eval/stt_intent_eval.py` to route through production router with `unknown_intent` -> `"NO_INTENT"`.
3. Verify with unit tests, homophone collision checks, and relevant pytest tests.
Write your complete report to `d:\Software GitCode\JARVIS\.agents\worker_m1\handoff.md` and send a message when complete.
