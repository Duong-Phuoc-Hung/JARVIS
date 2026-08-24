## 2026-08-22T16:08:07Z
You are Explorer M2_3 for Milestone M2 (Smart Keyword Router Fallback in Vietnamese).

Working Directory: d:/Software GitCode/JARVIS/.agents/explorer_m2_3
Project Scope: d:/Software GitCode/JARVIS/PROJECT.md
Original Request: d:/Software GitCode/JARVIS/.agents/ORIGINAL_REQUEST.md (Section ## 2026-08-22T15:49:23Z)
Survey Report: d:/Software GitCode/JARVIS/.agents/explorer_survey_2/report.md
Project Root: d:/Software GitCode/JARVIS

Your Task:
Formulate the parameter extraction and safety confirmation blueprint for M2 in `jarvis/llm/router.py`:
1. Entity extraction: extracting device names ("đèn phòng khách", "quạt"), music queries, reminder times/messages.
2. Safety confirmation for power/restart actions ("tắt máy", "restart"): requiring explicit confirmation (`requires_confirmation=True`) or safe dry-run mode before executing system power commands.
3. Review existing router tests in `tests/test_llm_router.py` and `tests/test_adversarial_m3_stt_llm.py` to ensure zero regression.

Write your report to `d:/Software GitCode/JARVIS/.agents/explorer_m2_3/report.md` and send a summary handoff to parent.
