# DISPATCH — Worker M1 Fix (Iteration 2)

You are a Worker agent implementing the fix for Milestone 1 (Safe Preprocessing Diacritic Normalization) for JARVIS Voice Pipeline Upgrade (v4.8.1).
Your working directory is: `d:\Software GitCode\JARVIS\.agents\worker_m1_fix\`

## Mandatory Reading
1. `d:\Software GitCode\JARVIS\.agents\reviewer_m1_1\handoff.md` (Read Section: Findings -> Finding 1 & Finding 2)
2. `d:\Software GitCode\JARVIS\.agents\auditor_m1\handoff.md` (Read Section 3: Caveats -> Finding on line 2406)
3. `d:\Software GitCode\JARVIS\.agents\worker_m1\handoff.md`

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Write Ownership
You exclusively own:
- `jarvis/llm/router.py`

## Remediation Task
1. In `jarvis/llm/router.py`:
   - At line 2406 in `parse_intent`:
     Change:
     ```python
     clean_lower_stripped = strip_vietnamese_diacritics(clean_lower)
     ```
     To:
     ```python
     clean_lower_stripped = (
         strip_vietnamese_diacritics(clean_lower)
         if len(clean_lower) <= 2048
         else None
     )
     ```
   - In `_match_rule_key` (around lines 1910-1925):
     Ensure that if `clean_lower_stripped is None`:
     ```python
     if clean_lower_stripped is None:
         if len(clean_lower) > 2048:
             return False
         clean_lower_stripped = strip_vietnamese_diacritics(clean_lower)
     ```
     Also ensure line 2572 (in Tier-3 fallback if applicable) also does not re-strip if `len > 2048`.
2. Verification:
   - Run: `pytest tests/test_adversarial_m2_llm_router.py -k test_adversarial_massive_strings_and_redos_resistance -v`
     Ensure `duration_50k_ms < 20.0` PASSES cleanly (should be < 2ms).
   - Run: `pytest tests/unit/test_router_p0.py tests/test_adversarial_m1_intent_router.py -q`
     Ensure all pass with 0 failures.
   - Run acceptance queries:
     `parse_intent("Điều chỉnh âm lượng")` -> `system_volume`
     `parse_intent("Tìm kiếm Google.")` -> `web_open`
     `parse_intent("Trời hôm nay thế nào?")` -> `shell_exec`
3. Document genuine test results and timings in `d:\Software GitCode\JARVIS\.agents\worker_m1_fix\handoff.md`.

## 2026-09-03T15:55:46Z
You are a Worker agent implementing the fix for Milestone 1 (Safe Preprocessing Diacritic Normalization) for JARVIS Voice Pipeline Upgrade (v4.8.1).
Your working directory is: `d:\Software GitCode\JARVIS\.agents\worker_m1_fix\`.
Read `d:\Software GitCode\JARVIS\.agents\worker_m1_fix\DISPATCH.md`.
Read `d:\Software GitCode\JARVIS\.agents\reviewer_m1_1\handoff.md` (specifically Findings 1 & 2).
Read `d:\Software GitCode\JARVIS\.agents\auditor_m1\handoff.md` (Caveats on line 2406).

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Remediate the ReDoS latency issue on 50KB strings in `jarvis/llm/router.py`, verify `test_adversarial_massive_strings_and_redos_resistance` passes in < 20ms, verify router unit tests pass, and report genuine verified timings to `d:\Software GitCode\JARVIS\.agents\worker_m1_fix\handoff.md`.
