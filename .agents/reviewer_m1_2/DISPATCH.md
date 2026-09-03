# DISPATCH — Reviewer M1-2

You are a Reviewer agent conducting independent review of Milestone 1 (Safe Preprocessing Diacritic Normalization) for JARVIS Voice Pipeline Upgrade (v4.8.1).
Your working directory is: `d:\Software GitCode\JARVIS\.agents\reviewer_m1_2\`

## Mandatory Reading
1. `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md` (section `2026-09-03T15:09:08Z`)
2. `d:\Software GitCode\JARVIS\.agents\orchestrator_4\PROJECT.md`
3. `d:\Software GitCode\JARVIS\.agents\worker_m1\handoff.md`

## Review Focus
1. Inspect code changes made in `jarvis/llm/router.py` and `tests/eval/stt_intent_eval.py`.
2. Adversarially challenge edge cases:
   - Upper/lower case mixes (`Điều Chỉnh ÂM LƯỢNG`, `ĐẶT NHẮC`).
   - Mixed punctuation and special characters (`Điều chỉnh âm lượng!`, `Tìm kiếm Google???`).
   - ReDoS and massive input latency SLAs ($< 20.0$ ms on 50KB strings).
   - Robustness when `self.llm is None` or `dispatcher` has no actions.
3. Verify test assertions:
   - `parse_intent("Điều chỉnh âm lượng")` -> `system_volume`
   - `parse_intent("Tìm kiếm Google.")` -> `web_open`
   - `parse_intent("Trời hôm nay thế nào?")` -> `shell_exec`
   - `"mở ứng dụng chrome"` -> `app_open`
   - `"nhắc nhở lúc 8 giờ"` -> `reminder`
   - `"hướng dẫn sử dụng"` does not route to `clipboard_paste`
4. Run tests (`pytest tests/unit/test_router_p0.py tests/test_adversarial_m1_intent_router.py -q`).
5. Output your report to `d:\Software GitCode\JARVIS\.agents\reviewer_m1_2\handoff.md` with a clear verdict: `APPROVE` or `REQUEST_CHANGES`.

## 2026-09-03T15:40:00Z
You are Reviewer M1-2 reviewing Milestone 1 for JARVIS Voice Pipeline Upgrade (v4.8.1).
Your working directory is: `d:\Software GitCode\JARVIS\.agents\reviewer_m1_2\`.
Read `d:\Software GitCode\JARVIS\.agents\reviewer_m1_2\DISPATCH.md`.
Read `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md` (section `2026-09-03T15:09:08Z`).
Read `d:\Software GitCode\JARVIS\.agents\orchestrator_4\PROJECT.md`.
Read `d:\Software GitCode\JARVIS\.agents\worker_m1\handoff.md`.
Review code changes, challenge edge cases, punctuation, ReDoS SLAs, and run tests.
Deliver your report with verdict (APPROVE or REQUEST_CHANGES) to `d:\Software GitCode\JARVIS\.agents\reviewer_m1_2\handoff.md` and send message when done.
