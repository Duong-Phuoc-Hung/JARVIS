# DISPATCH — Explorer Survey Router

You are an Explorer agent investigating JARVIS codebase for Voice Pipeline Upgrade (v4.8.1).
Your working directory is: `d:\Software GitCode\JARVIS\.agents\explorer_survey_router\`

## Task Assignment
Investigate `jarvis/llm/router.py`, `jarvis/__init__.py`, `tests/unit/test_router*.py`, and `tests/eval/routing_eval_*.py`.
Read `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md` (section `2026-09-03T15:09:08Z`).

Specific focus:
1. Examine `_match_rule_key` in `jarvis/llm/router.py`: how rules are currently matched, regex vs substring vs exact token, whether any diacritic stripping currently exists.
2. Design specification for `strip_vietnamese_diacritics(text: str) -> str`:
   - Must cover all Vietnamese vowels with diacritics (acute, grave, hook, tilde, dot below: á, à, ả, ã, ạ, ă, ắ, ằ, ẳ, ẵ, ặ, â, ấn, ầ, ẩ, ẫ, ậ, é, è, ẻ, ẽ, ẹ, ê, ế, ề, ể, ễ, ệ, í, ì, ỉ, ĩ, ị, ó, ò, ỏ, õ, ọ, ô, ố, ồ, ổ, ỗ, ộ, ơ, ớ, ờ, ở, ỡ, ợ, ú, ù, ủ, ũ, ụ, ư, ứ, ừ, ử, ữ, ự, ý, ỳ, ỷ, ỹ, ỵ) and `đ/Đ` -> `d/D`.
   - Must support both precomposed NFC and decomposed NFD unicode forms.
3. Safe diacritic folding integration into `_match_rule_key`:
   - Requirement: multi-word phrases (`len(words) >= 2`) can be matched with diacritic folding.
   - Requirement: single words (`len(words) == 1`) MUST be exact whole-word token match with diacritics preserved, NEVER substring or stripped diacritic, to avoid homophone collisions (`nhạc` vs `nhắc`, `dừng` vs `dụng`, `dán` vs `dẫn`).
   - Check existing test cases: `"Điều chỉnh âm lượng"` -> `system_volume`, `"Tìm kiếm Google."` -> `web_open`, `"Trời hôm nay thế nào?"` -> `shell_exec`.
4. Check rule dictionary in `jarvis/llm/router.py` for R3 phonetic drift aliases:
   - `system_power`: `"tắc máy"`, `"tập máy tính"`, `"sắt đau má"`
   - `app_open`: `"cái đặt"`, `"má kẻ đặt"`, `"open sentence"`, `"open sente"`
   - `reminder`: `"đặt time"`, `"đặc nhắc"`
   - `system_volume`: `"tắc tính"`, `"tắt tính"`
   - `memory_save_fact`: `"ghi chú"`, `"ghi chu"`, `"tạo ghi chú mới"`, `"tao ghi chu moi"`
   - Check where these rules should be placed, rule ordering, priority, and check whether any existing tests might collide.
5. Write your complete findings to `d:\Software GitCode\JARVIS\.agents\explorer_survey_router\handoff.md` and send a message when done.

## 2026-09-03T15:12:07Z
You are an Explorer agent investigating JARVIS codebase for Voice Pipeline Upgrade (v4.8.1).
Your working directory is `d:\Software GitCode\JARVIS\.agents\explorer_survey_router\`.
Read your assignment details in `d:\Software GitCode\JARVIS\.agents\explorer_survey_router\DISPATCH.md` and read `d:\Software GitCode\JARVIS\.agents\ORIGINAL_REQUEST.md` (section `2026-09-03T15:09:08Z`).
Investigate `jarvis/llm/router.py`, `_match_rule_key`, `strip_vietnamese_diacritics` requirements, homophone collisions prevention, and rule dictionary additions for R3.
Output your comprehensive report to `d:\Software GitCode\JARVIS\.agents\explorer_survey_router\handoff.md` and send a message to parent when finished.

