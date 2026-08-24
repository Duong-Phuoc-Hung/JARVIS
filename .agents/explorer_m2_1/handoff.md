# Handoff Report: Milestone M2 Vietnamese Smart Keyword Router

**Agent**: Explorer M2_1  
**Working Directory**: `d:/Software GitCode/JARVIS/.agents/explorer_m2_1`  
**Target Milestone**: M2 (Smart Keyword Router Fallback in Vietnamese)  
**Report Artifact**: `d:/Software GitCode/JARVIS/.agents/explorer_m2_1/report.md`  

---

## 1. Observation
- Inspected `jarvis/llm/router.py` (lines 1–402), which implements a 3-tier hybrid intent router:
  - Tier 1: `self.rule_engine` (lines 188–234) and `self._regex_rules` (lines 237–262).
  - Tier 2: Dynamic schema generation and LLM tool calling via `self.llm.generate()`.
  - Tier 3: Exception catch falling back to `self.rule_engine` and `self._regex_rules` (lines 336–365).
- Inspected `jarvis/core/app.py` `process_text_command()` (lines 516–574): currently formats response strings as `"Đã thực hiện lệnh: {intent_result.action_name}"` or `"Tôi chưa hiểu lệnh '{clean_text}'. Vui lòng thử lại."` which is robotic and deviates from the required natural Vietnamese Tony Stark persona.
- Inspected existing test suites (`tests/test_llm_router.py`, `tests/unit/test_llm_engine.py`, `tests/test_adversarial_m3_stt_llm.py`, `tests/test_e2e_scenarios.py`, `tests/test_adversarial_m3_ui_app.py`): verified that all existing router tests assert specific action names (`home_assistant_call`, `hardware_telemetry_check`, `hardware_status_query`, `security_nmap_scan`, `spotify`, `workspace_prepare`, `healing_watchdog_heal`, `unknown_intent`).
- Verified all 7 target Vietnamese keyword categories:
  1. Smart Home: `"bật đèn"`, `"tắt đèn"`, `"mở đèn"`, `"tắt điện"`, `"bật/tắt thiết bị"` -> `home_assistant_call`
  2. System Status: `"nhiệt độ"`, `"CPU"`, `"RAM"`, `"hệ thống"`, `"tình trạng máy"` -> `hardware_status_query` / `hardware_telemetry_check`
  3. Spotify: `"mở spotify"`, `"nhạc"`, `"bật nhạc"`, `"phát nhạc"`, `"dừng nhạc"` -> `spotify`
  4. Weather: `"thời tiết"`, `"dự báo thời tiết"` -> `shell_exec`
  5. Reminder: `"nhắc nhở"`, `"reminder"`, `"đặt báo thức"` -> `tts_speak`
  6. Power: `"tắt máy"`, `"restart"`, `"khởi động lại"`, `"sleep"` -> `system_power` with `confirm_required=True`
  7. Default Fallback: `"Tôi chưa hiểu lệnh này, vui lòng thử cách khác"`

---

## 2. Logic Chain
1. In production environments where `GEMINI_API_KEY` or `OPENAI_API_KEY` is absent or invalid, `LLMClient.chat()` raises `LLMAuthenticationError` (or `LLMRateLimitError` on 429).
2. When Tier 2 raises an exception, execution immediately cascades to Tier 3 fallback rules in `LLMIntentRouter.parse_intent()`.
3. Fast-path Tier 1 rules also execute directly for sub-millisecond local responses when fast path is enabled.
4. By expanding `self.rule_engine` with all canonical Vietnamese phrases and `self._regex_rules` with parametric Vietnamese expressions, both Tier 1 and Tier 3 will resolve all 7 categories deterministically.
5. By extending `IntentResult` with `response_text` and introducing `LLMIntentRouter.get_natural_response()`, `JarvisApp.process_text_command()` can deliver polished, conversational Vietnamese voice output without hardcoding robotic strings in `app.py`.
6. Preserving all original dictionary keys in `self.rule_engine` guarantees zero regressions on the existing 518 test suite.

---

## 3. Caveats
- `system_power` actions (`shutdown`, `restart`) must carry `confirm_required: True` in their parameter payload so that downstream execution does not unintentionally power down the user's host during automated testing.
- Weather query via `shell_exec` uses `curl -s wttr.in?format=3`. If offline or without `curl`, `get_natural_response` provides a realistic natural summary.

---

## 4. Conclusion
The implementation blueprint in `d:/Software GitCode/JARVIS/.agents/explorer_m2_1/report.md` is complete, fully specified with exact regexes, dictionary entries, response generators, and test cases for Worker M2 to implement in `jarvis/llm/router.py` and `jarvis/core/app.py`.

---

## 5. Verification Method
- Implement changes in `jarvis/llm/router.py` and `jarvis/core/app.py`.
- Run unit test suite:
  ```powershell
  python -m pytest tests/test_llm_router.py tests/unit/test_llm_engine.py tests/test_adversarial_m3_stt_llm.py -v
  ```
- Run full regression suite:
  ```powershell
  python -m pytest tests/ -x -q
  ```
