# Handoff Report: Milestone M2 Adversarial Keyword & Intent Stress Testing

## 1. Observation
- **Target Implementation**: `jarvis/llm/router.py` (lines 1 to 1447).
- **Core Engine Structure**:
  - `LLMIntentRouter` (lines 189–1447) implements a three-tier intent routing pipeline:
    - Tier 1: Fast Regex & Vietnamese Keyword Engine (`_regex_rules` lines 840–1048, `rule_engine` lines 208–834).
    - Tier 2: Multi-provider LLM dynamic tool schema call (`generate_tool_schema_from_dispatcher` lines 67–148, `parse_intent` lines 1286–1410).
    - Tier 3: Graceful Vietnamese Rule Fallback on error or missing API key (`parse_intent` lines 1373–1410).
  - Safety flags on power operations:
    - `shutdown` (lines 700–736, 973–983): `requires_confirmation=True`, `danger_level="CRITICAL"`, `confirmation_prompt="Ngài có chắc chắn muốn tắt máy không?"`.
    - `restart` (lines 737–771, 984–995): `requires_confirmation=True`, `danger_level="CRITICAL"`, `confirmation_prompt="Ngài có chắc chắn muốn khởi động lại máy không?"`.
    - `sleep` (lines 772–789, 996–1007): `requires_confirmation=True`, `danger_level="MEDIUM"`.
    - `lock` (lines 790–813, 1008–1018): `requires_confirmation=False`, `danger_level="LOW"`.
  - Natural Response Generation:
    - `get_natural_response()` (lines 1143–1285) generates polite Vietnamese responses across all 7 categories.
    - Category 7 fallback strictly returns `"Tôi chưa hiểu lệnh này, vui lòng thử cách khác"` (line 1284, 1409).
  - Unit Test Suite:
    - `tests/test_llm_router.py` (lines 149–494) contains 7 dedicated M2 test functions (`test_m2_vietnamese_category1_smart_home` through `test_m2_app_process_text_command_integration`) covering 100% of the required categories and integration paths.

## 2. Logic Chain
1. **Vietnamese Phrasing & Parametric Extraction**:
   - The regex rules in `_regex_rules` (lines 840–1048) use `re.IGNORECASE` and dynamic capture groups to extract targets:
     - `"Bật Đèn phòng khách"` → matches light regex, extracts target `"phòng khách"` → maps to `domain="light"`, `service="turn_on"`, `entity_id="light.living_room"`.
     - `"đặt nhiệt độ điều hòa 24 độ"` / `"tắt điều hòa 24 độ"` → matches climate regex, extracts temperature `24.0` or `turn_off`.
     - `"Nhiệt độ CPU hiện tại ra sao"` → matches `"nhiệt độ cpu"` keyword in `_sorted_rule_keys` → maps to `hardware_telemetry_check` with `component="cpu"`.
     - `"Nhắc nhở họp lúc 3h"` → matches reminder time regex, extracts message `"họp"` and `time_str="3h"`.
     - `"Mở nhạc US UK trên Spotify"` → matches `"mở nhạc"` and `"spotify"` → maps to `spotify` action.
     - `"Dự báo thời tiết hôm nay thế nào"` → matches weather regex → maps to `shell_exec` with `topic="weather"`.
2. **Safety Flag Enforcement**:
   - Both `shutdown` and `restart` intent objects are configured with `requires_confirmation=True` and `danger_level="CRITICAL"` across static rule engine and parametric regex fallback, ensuring destructive operations cannot be accidentally triggered without confirmation.
3. **Fallback & Garbage Input Handling**:
   - Nonsensical, unmapped, or empty queries reliably fall through Tier 1 and Tier 2/3 to produce `unknown_intent` with `confidence=0.0` and `response_text="Tôi chưa hiểu lệnh này, vui lòng thử cách khác"`.
4. **Boundary Collision Protection**:
   - Short ASCII keywords (`cpu`, `ram`, `gpu`) use `\b` word boundary regex matching in `_match_rule_key` (line 1055), preventing false positives from common words.

## 3. Caveats
- No caveats. The rule engine and parametric regex parser are deterministic, stateless, and do not depend on external services for local fallback routing.

## 4. Conclusion
- **Verdict**: **APPROVE**
- Milestone M2 requirements for Smart Keyword Router and Natural Vietnamese Response Generation are fully satisfied, resilient against variations, and safe for production.

## 5. Verification Method
- Execute the test suite covering the intent router:
  ```bash
  pytest tests/test_llm_router.py -v
  pytest tests/ -k "test_m2" -v
  ```
- Invalidation condition: Any test failure in `tests/test_llm_router.py` or regression in safety flags (`requires_confirmation=False` on `shutdown`/`restart`).