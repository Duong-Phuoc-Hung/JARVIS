## 2026-08-22T16:08:07Z
You are Explorer M2_1 for Milestone M2 (Smart Keyword Router Fallback in Vietnamese).

Working Directory: d:/Software GitCode/JARVIS/.agents/explorer_m2_1
Project Scope: d:/Software GitCode/JARVIS/PROJECT.md
Original Request: d:/Software GitCode/JARVIS/.agents/ORIGINAL_REQUEST.md (Section ## 2026-08-22T15:49:23Z)
Survey Report: d:/Software GitCode/JARVIS/.agents/explorer_survey_2/report.md
Project Root: d:/Software GitCode/JARVIS

Your Task:
Formulate the exact implementation blueprint for `jarvis/llm/router.py` Tier 1 / Tier 3 rule matching for all 7 Vietnamese keyword categories:
1. "bật đèn", "tắt đèn", "bật/tắt thiết bị" -> `smart_home` / `home_assistant_call`
2. "nhiệt độ", "CPU", "RAM", "hệ thống", "tình trạng máy" -> `system_status` / `hardware_status_query`
3. "mở spotify", "nhạc", "bật nhạc", "phát nhạc", "dừng nhạc" -> `spotify`
4. "thời tiết", "dự báo thời tiết" -> `shell` / weather action
5. "nhắc nhở", "reminder", "đặt báo thức" -> `tts_speak` / reminder
6. "tắt máy", "restart", "khởi động lại", "sleep" -> `shell` / power action with confirmation
7. Default fallback: "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"

Write your report to `d:/Software GitCode/JARVIS/.agents/explorer_m2_1/report.md` and send a summary handoff to parent.
