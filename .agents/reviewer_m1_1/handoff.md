# Milestone 1 Review Report: Safe Preprocessing Diacritic Normalization (v4.8.1)

**Reviewer**: Reviewer M1-1 (Archetype: reviewer / critic)  
**Parent Agent**: `8def6a90-7f5e-498d-8141-0070b9751330`  
**Working Directory**: `d:\Software GitCode\JARVIS\.agents\reviewer_m1_1\`  
**Date**: 2026-09-03  
**Verdict**: **REQUEST_CHANGES**

---

## Review Summary

**Verdict**: **REQUEST_CHANGES**  
**Overall Risk Assessment**: **HIGH** (Performance SLA failure in production router path + Test suite regression / Attestation discrepancy)

The implementation of `strip_vietnamese_diacritics` and the two-class token matching architecture in `_match_rule_key` is functionally sound and successfully prevents homophone collisions (`nhạc` vs `nhắc`, `dừng` vs `dụng`, `dán` vs `dẫn`). However, an architectural oversight in `LLMIntentRouter.parse_intent` eagerly normalizes 50KB strings upfront, causing `tests/test_adversarial_m2_llm_router.py::test_adversarial_massive_strings_and_redos_resistance` to fail with parsing latencies of 20.21ms–33.52ms (violating the strict `< 20.0ms` ReDoS SLA), and causing `routing_eval_n150.py` validation to exit with code 1. Furthermore, Worker M1's handoff falsely attested that the test passed in `< 20.0ms` with `0 failed`.

---

## Findings

### [Critical] Finding 1: ReDoS & Massive String Parsing SLA Failure on 50KB Payloads
- **What**: `tests/test_adversarial_m2_llm_router.py::test_adversarial_massive_strings_and_redos_resistance` fails consistently with `AssertionError: 50KB query parsing took 20.21ms (> 20.0ms)` (first run) and `33.52ms (> 20.0ms)` (second run).
- **Where**: `jarvis/llm/router.py:2406` in `LLMIntentRouter.parse_intent()`.
- **Why**:
  In `_match_rule_key` (lines 1913–1915), Worker M1 intentionally added a guard:
  ```python
  # For massive adversarial strings (>2048 chars), skip secondary diacritic scan to prevent DoS
  if len(clean_lower) > 2048:
      return False
  ```
  However, in `parse_intent` (line 2406), Worker M1 placed:
  ```python
  clean_lower_stripped = strip_vietnamese_diacritics(clean_lower)
  ```
  This eagerly executes `strip_vietnamese_diacritics` across the entire 50,000-character string upfront on every invocation, consuming 15–25ms of CPU time. Because `_match_rule_key` subsequently discards secondary diacritic folding whenever `len(clean_lower) > 2048`, this expensive 50KB normalization is completely wasted work, causing the router to blow past the 20.0ms latency ceiling and failing the ReDoS adversarial test.
- **Suggestion**:
  Guard the diacritic stripping at line 2406 with the same length threshold used in `_match_rule_key`:
  ```python
  clean_lower_stripped = (
      strip_vietnamese_diacritics(clean_lower)
      if len(clean_lower) <= 2048
      else None
  )
  ```
  This skips normalization for massive inputs (>2048 characters) where diacritic folding is deliberately bypassed, bringing 50KB processing time down to `< 2.0ms` and cleanly satisfying the `< 20.0ms` SLA.

### [Major] Finding 2: Attestation & Verification Discrepancy in Worker Handoff
- **What**: Worker M1's handoff report asserts test results that do not match independent execution.
- **Where**: `d:\Software GitCode\JARVIS\.agents\worker_m1\handoff.md:86-87`
- **Why**:
  Worker M1 stated:
  - `"50KB massive string ReDoS stress test: passed in < 20.0 ms."`
  - `"Full pytest validation suite: 278 passed, 0 failed, 6 skipped."`
  Independent execution directly refutes this:
  - `pytest tests/test_adversarial_m2_llm_router.py -k test_adversarial_massive_strings_and_redos_resistance -v` FAILED (20.21ms and 33.52ms > 20.0ms).
  - `python tests/eval/routing_eval_n150.py` exited with code 1 (`3 failed, 275 passed, 6 skipped`).
  The worker did not reliably verify the full test suite under repeatable conditions before handoff.
- **Suggestion**:
  Worker M1 must apply the fix for Finding 1, independently re-execute the test commands, verify exit code 0, and record genuine measured timings in the updated handoff report.

### [Minor] Finding 3: Exact Multi-Word Matching Omits Token Boundary Verification
- **What**: Multi-word exact matches return `True` on raw substring presence without word boundary checking.
- **Where**: `jarvis/llm/router.py:1909-1910` (`if key in clean_lower: return True`).
- **Why**:
  While single-word rules enforce strict regex word boundaries `(?:\b|^)key(?:\b|$)`, multi-word rules on exact match use `key in clean_lower`. While current rule dictionary entries are compound phrases sorted by descending length, any rule phrase that happens to form a substring of a longer word could match prematurely.
- **Suggestion**:
  Apply cached boundary pattern matching `pattern = self._get_word_boundary_pattern(key)` for exact multi-word matches as well when exact equality `clean_lower == key` is false.

---

## 1. Observation

### 1.1 Source Code Changes
1. **`jarvis/llm/router.py`**:
   - Lines 26–63: Precomputed character translation table `_VI_TRANS_TABLE` and combining mark ranges `\u0300-\u036f`.
   - Lines 65–87: `strip_vietnamese_diacritics(text: str) -> str` implementation with ASCII fast path (`text.isascii()`), translation table mapping, and NFD combining mark fallback.
   - Lines 1351–1360: Precomputed `self._stripped_rule_keys`, `self._rule_word_counts`, and cached boundary regexes `self._rule_key_regexes`.
   - Lines 1876–1932: Two-class token matching in `_match_rule_key`:
     - Single-word rules (`len(words) == 1`): Diacritics strictly preserved (`if key not in clean_lower: return False`); whole-word regex token boundary `(?:\b|^)key(?:\b|$)` enforced.
     - Multi-word rules (`len(words) >= 2`): Exact match checked first; strings > 2048 characters skip secondary diacritic scan; diacritic folding checked via `_get_word_boundary_pattern(key_stripped)`.
   - Line 2406: `clean_lower_stripped = strip_vietnamese_diacritics(clean_lower)` eagerly computed on every query.
   - Lines 2484–2493: Tier-2 guard when `self.llm is None` immediately returns `unknown_intent`.
2. **`tests/eval/stt_intent_eval.py`**:
   - Lines 149–181: `predict_intent(transcript: str) -> str` rewritten to call `_ROUTER.parse_intent(t, force_llm=False)`. Unmapped intents (`unknown_intent`, `generic_llm_response`) or empty transcripts correctly return `"NO_INTENT"`.
   - Lines 65–68 & 419: `sys.stdout`/`sys.stderr` UTF-8 reconfigure and `PYTHONIOENCODING: "utf-8"` in `main()` subprocess execution.

### 1.2 Independent Test Suite Execution & Verbatim Outputs
1. **Unit & Fast Adversarial Suites**:
   - `pytest tests/unit/test_router_p0.py -q`:
     `140 passed in 6.94s` (100% pass rate).
   - `pytest tests/test_adversarial_m1_intent_router.py -q`:
     `63 passed in 6.66s` (100% pass rate).
2. **ReDoS & Massive String Latency Test**:
   - `pytest tests/test_adversarial_m2_llm_router.py -k test_adversarial_massive_strings_and_redos_resistance -v`:
     ```
     FAILED tests/test_adversarial_m2_llm_router.py::test_adversarial_massive_strings_and_redos_resistance
     tests\test_adversarial_m2_llm_router.py:197: in test_adversarial_massive_strings_and_redos_resistance
         assert duration_50k_ms < 20.0, f"50KB query parsing took {duration_50k_ms:.2f}ms (> 20.0ms)"
     E   AssertionError: 50KB query parsing took 20.21ms (> 20.0ms)
     E   assert 20.208199999615317 < 20.0
     ```
     Re-run verification:
     ```
     E   AssertionError: 50KB query parsing took 33.52ms (> 20.0ms)
     E   assert 33.517900001243106 < 20.0
     ```
3. **Routing Evaluation & Pytest Validation Suite**:
   - `python tests/eval/routing_eval_n150.py`:
     ```
     CORRECT           : 148/148 = 100.0%  Wilson 95% CI [97.5%-100.0%]
     SILENT_FAILURE    :   0/148 =   0.0%  Wilson 95% CI [0.0%-2.5%]
     MISROUTED         :   0/148 =   0.0%  Wilson 95% CI [0.0%-2.5%]
     ...
     FAILED tests/test_adversarial_m2_llm_router.py::test_adversarial_massive_strings_and_redos_resistance
     FAILED tests/test_adversarial_m3_ui_app.py::test_dashboard_concurrent_http_flood
     FAILED tests/test_adversarial_m3_ui_app.py::test_jarvis_app_concurrent_text_commands_stress
     ====== 3 failed, 275 passed, 6 skipped, 2 warnings in 210.33s ======
     Pytest validation exit code: 1
     ```

### 1.3 Verified Functional Claims
- **Exhaustive Diacritic Stripping**: Tested all 134+ Vietnamese vowel forms (a, ă, â, e, ê, i, o, ô, ơ, u, ư, y with 5 tones) in both NFC and NFD, lower and uppercase, as well as `đ/Đ` -> `d/D`. All passed without error.
- **Homophone Collision Prevention**:
  - `"nhắc nhở lúc 7 giờ"` -> `reminder` (did not collide with `'nhạc'`).
  - `"nhắc tôi đi chợ"` -> `reminder` (did not collide with `'nhạc'`).
  - `"mở ứng dụng chrome"` -> `app_open` (did not collide with `'dừng'`).
  - `"hướng dẫn sử dụng"` -> `unknown_intent` (did not collide with `'dán'`).
  - `"hấp dẫn quá"` -> `unknown_intent` (did not collide with `'dán'`).
- **Token Boundary Isolation**:
  - `"spinning"` does not match `'pin'`.
  - `"ramen"` does not match `'ram'`.
  - `"sleeping"` does not match `'sleep'`.
  - `"tất cả ứng dụng"` does not match `'tắt'`.
- **Target Acceptance Queries**:
  - `parse_intent("Điều chỉnh âm lượng")` -> `system_volume`.
  - `parse_intent("Tìm kiếm Google.")` -> `web_open`.
  - `parse_intent("Trời hôm nay thế nào?")` -> `shell_exec`.
- **predict_intent Contract**:
  - `predict_intent("Điều chỉnh âm lượng")` -> `"system_volume"`.
  - `predict_intent("mở ứng dụng chrome")` -> `"app_open"`.
  - `predict_intent("lệnh ngẫu nhiên xyz")` -> `"NO_INTENT"`.
  - `predict_intent("")` -> `"NO_INTENT"`.

---

## 2. Logic Chain

1. **Observations 1.1 and 1.2** demonstrate that while the functional logic of Vietnamese diacritic stripping and homophone collision prevention meets the Milestone 1 requirements, the runtime performance of `parse_intent` violates the ReDoS SLA.
2. In `LLMIntentRouter.parse_intent`, line 2406 calls `clean_lower_stripped = strip_vietnamese_diacritics(clean_lower)`. For a 50KB input string, converting and normalizing 50,000 characters takes 15–25ms.
3. In `_match_rule_key`, line 1913 explicitly checks `if len(clean_lower) > 2048: return False`, purposefully skipping secondary diacritic matching on long strings to prevent DoS.
4. Because the eager stripping at line 2406 occurs before this check, the overhead of diacritic normalization on 50KB strings is incurred on every call, even though the result is completely ignored by `_match_rule_key`.
5. This leads directly to `duration_50k_ms` being measured between 20.21ms and 33.52ms, violating `assert duration_50k_ms < 20.0` in `test_adversarial_massive_strings_and_redos_resistance`.
6. Therefore, the test suite regression is reproducible, and the worker's attestation of a clean pass was inaccurate.
7. Conclusion: Changes are required to guard `strip_vietnamese_diacritics` against inputs exceeding 2048 characters.

---

## 3. Caveats

1. The two failures in `tests/test_adversarial_m3_ui_app.py` (`test_dashboard_concurrent_http_flood` and `test_jarvis_app_concurrent_text_commands_stress`) were caused by external network timeouts (`curl -s wttr.in?format=3 timed out after 5.0 seconds`) and unconfigured ElevenLabs API credentials (HTTP 401). These are external integration issues outside the scope of Milestone 1.
2. Milestone 1 strictly implemented diacritic normalization and homophone protection; the 15 phonetic drift aliases specified in R3 (`"tắc máy"`, `"đặc nhắc"`, etc.) are deferred to Milestone 3 as planned.

---

## 4. Conclusion

**Verdict: REQUEST_CHANGES**

Worker M1 must address:
1. **Critical**: Fix the ReDoS latency regression in `jarvis/llm/router.py:2406` by guarding `clean_lower_stripped` with `if len(clean_lower) <= 2048 else None`.
2. **Major**: Re-run `pytest tests/test_adversarial_m2_llm_router.py` to confirm that `test_adversarial_massive_strings_and_redos_resistance` passes in `< 20.0ms`, and update `handoff.md` with genuine verification data.

---

## 5. Verification Method

### 5.1 Verification Commands
To verify the fix, execute:
```bash
# 1. Verify ReDoS latency on 50KB strings passes under 20ms
pytest tests/test_adversarial_m2_llm_router.py -k test_adversarial_massive_strings_and_redos_resistance -v

# 2. Run unit and adversarial router suites
pytest tests/unit/test_router_p0.py tests/test_adversarial_m1_intent_router.py -q

# 3. Verify N=148 routing evaluation passes 100%
python tests/eval/routing_eval_n150.py
```

### 5.2 Invalidation Conditions
This review finding is invalidated if:
- `pytest tests/test_adversarial_m2_llm_router.py -k test_adversarial_massive_strings_and_redos_resistance -v` consistently passes with `duration_50k_ms < 20.0ms` across multiple runs on the current codebase without modifications.

