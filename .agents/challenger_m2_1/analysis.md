# Milestone M2 Adversarial Keyword & Intent Stress Test Analysis

## 1. Executive Summary
- **Target Component**: `jarvis/llm/router.py` (`LLMIntentRouter`, `IntentResult`, `get_natural_response`, `_regex_rules`, `rule_engine`)
- **Objective**: Conduct rigorous adversarial stress testing across 7 core Vietnamese intent categories, uppercase/lowercase variations, punctuation, unaccented inputs, safety flags, and fallback behaviors.
- **Verdict**: **APPROVE** (All M2 intent routing specifications, safety confirmation protocols, parametric extraction, and Vietnamese conversational responses meet or exceed requirements).

---

## 2. Comprehensive Test Matrix & Empirical Trace

### Category 1: Smart Home Automation (`home_assistant_call`)
| # | Input Query | Expected Action | Resolved Action | Entity / Parameters | Response Text | Status |
|---|-------------|-----------------|-----------------|---------------------|---------------|--------|
| 1.1 | `"Bật Đèn phòng khách"` | `home_assistant_call` | `home_assistant_call` | `domain=light, service=turn_on, entity_id=light.living_room` | `"Đang bật đèn phòng khách cho Ngài."` | **PASS** |
| 1.2 | `"bật đèn bàn"` | `home_assistant_call` | `home_assistant_call` | `domain=light, service=turn_on, entity_id=light.desk_lamp` | `"Đang bật đèn bàn làm việc cho Ngài."` | **PASS** |
| 1.3 | `"tắt đèn phòng ngủ"` | `home_assistant_call` | `home_assistant_call` | `domain=light, service=turn_off, entity_id=light.bedroom` | `"Đang tắt đèn phòng ngủ cho Ngài."` | **PASS** |
| 1.4 | `"bật quạt phòng khách"` | `home_assistant_call` | `home_assistant_call` | `domain=fan, service=turn_on, entity_id=fan.living_room` | `"Đang bật quạt cho Ngài."` | **PASS** |
| 1.5 | `"tắt điều hòa 24 độ"` | `home_assistant_call` | `home_assistant_call` | `domain=climate, service=turn_off, entity_id=climate.ac_unit` | `"Đang tắt điều hòa cho Ngài."` | **PASS** |
| 1.6 | `"đặt nhiệt độ điều hòa 24 độ"` | `home_assistant_call` | `home_assistant_call` | `domain=climate, service=set_temperature, entity_id=climate.ac_unit, temperature=24.0` | `"Đã đặt nhiệt độ điều hòa thành 24 độ cho Ngài."` | **PASS** |
| 1.7 | `"turn on light living room"` | `home_assistant_call` | `home_assistant_call` | `domain=light, service=turn_on, entity_id=light.living_room` | `"Đang bật đèn cho Ngài."` | **PASS** |

### Category 2: Hardware Telemetry & Diagnostics (`hardware_telemetry_check`, `hardware_status_query`)
| # | Input Query | Expected Action | Resolved Action | Component / Parameters | Response Text | Status |
|---|-------------|-----------------|-----------------|------------------------|---------------|--------|
| 2.1 | `"Nhiệt độ CPU hiện tại ra sao"` | `hardware_telemetry_check` | `hardware_telemetry_check` | `component=cpu` | `"Nhiệt độ CPU hiện tại là 45 độ C, hiệu năng ổn định, thưa Ngài."` | **PASS** |
| 2.2 | `"CPU"` / `"cpu"` | `hardware_telemetry_check` | `hardware_telemetry_check` | `component=cpu` | `"Nhiệt độ CPU hiện tại là 45 độ C, hiệu năng ổn định, thưa Ngài."` | **PASS** |
| 2.3 | `"RAM"` / `"dung lượng ram"` | `hardware_telemetry_check` | `hardware_telemetry_check` | `component=ram` | `"Bộ nhớ RAM đang sử dụng ở mức bình thường, tài nguyên dồi dào, thưa Ngài."` | **PASS** |
| 2.4 | `"kiểm tra GPU"` / `"card đồ họa"` | `hardware_telemetry_check` | `hardware_telemetry_check` | `component=gpu` | `"Card đồ họa hoạt động bình thường, nhiệt độ trong ngưỡng an toàn, thưa Ngài."` | **PASS** |
| 2.5 | `"dung lượng ổ cứng"` | `hardware_telemetry_check` | `hardware_telemetry_check` | `component=disk` | `"Ổ đĩa đang hoạt động trong trạng thái tốt, thưa Ngài."` | **PASS** |
| 2.6 | `"tình trạng hệ thống"` | `hardware_status_query` | `hardware_status_query` | `{}` | `"Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu, CPU và RAM ở mức an toàn, thưa Ngài."` | **PASS** |
| 2.7 | `"sức khỏe máy tính"` | `hardware_status_query` | `hardware_status_query` | `{}` | `"Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu, CPU và RAM ở mức an toàn, thưa Ngài."` | **PASS** |

### Category 3: Spotify & Music Playback (`spotify`)
| # | Input Query | Expected Action | Resolved Action | Extracted Query / Command | Response Text | Status |
|---|-------------|-----------------|-----------------|---------------------------|---------------|--------|
| 3.1 | `"Mở nhạc US UK trên Spotify"` | `spotify` | `spotify` | `{}` | `"Đang mở Spotify và phát nhạc cho Ngài."` | **PASS** |
| 3.2 | `"mở spotify bài Em của ngày hôm qua"` | `spotify` | `spotify` | `query="Em của ngày hôm qua"` | `"Đang mở Spotify và phát Em của ngày hôm qua cho Ngài."` | **PASS** |
| 3.3 | `"dừng nhạc"` / `"tạm dừng nhạc"` | `spotify` | `spotify` | `command="pause"` | `"Đã tạm dừng phát nhạc, thưa Ngài."` | **PASS** |
| 3.4 | `"chuyển bài"` / `"bài tiếp theo"` | `spotify` | `spotify` | `command="next"` | `"Đang chuyển bài tiếp theo, thưa Ngài."` | **PASS** |
| 3.5 | `"bật nhạc"` / `"phát nhạc"` | `spotify` | `spotify` | `{}` | `"Đang mở Spotify và phát nhạc cho Ngài."` | **PASS** |

### Category 4: Weather Forecasting (`shell_exec`)
| # | Input Query | Expected Action | Resolved Action | Target Location / Command | Response Text | Status |
|---|-------------|-----------------|-----------------|---------------------------|---------------|--------|
| 4.1 | `"Dự báo thời tiết hôm nay thế nào"` | `shell_exec` | `shell_exec` | `location="current", topic="weather"` | `"Đang kiểm tra thông tin thời tiết hôm nay cho Ngài."` | **PASS** |
| 4.2 | `"thời tiết hà nội"` | `shell_exec` | `shell_exec` | `location="Hà Nội", command="curl -s wttr.in/Hanoi?format=3"` | `"Đang kiểm tra thông tin thời tiết tại Hà Nội cho Ngài."` | **PASS** |
| 4.3 | `"dự báo thời tiết sài gòn"` | `shell_exec` | `shell_exec` | `location="Sài Gòn", command="curl -s wttr.in/Saigon?format=3"` | `"Đang kiểm tra thông tin thời tiết tại Sài Gòn cho Ngài."` | **PASS** |
| 4.4 | `"thời tiết"` | `shell_exec` | `shell_exec` | `location="current", topic="weather"` | `"Đang kiểm tra thông tin thời tiết hôm nay cho Ngài."` | **PASS** |

### Category 5: Reminders & Alarms (`reminder`)
| # | Input Query | Expected Action | Resolved Action | Extracted Time / Duration / Message | Response Text | Status |
|---|-------------|-----------------|-----------------|--------------------------------------|---------------|--------|
| 5.1 | `"Nhắc nhở họp lúc 3h"` | `reminder` | `reminder` | `message="họp", time_str="3h"` | `"Đã ghi nhận lời nhắc 'họp' vào lúc 3h của Ngài."` | **PASS** |
| 5.2 | `"nhắc nhở uống nước sau 30 phút"` | `reminder` | `reminder` | `message="uống nước", delay_s=1800, delay_minutes=30` | `"Đã ghi nhận lời nhắc 'uống nước' của Ngài."` | **PASS** |
| 5.3 | `"nhắc tôi đi ngủ sau 1 giờ"` | `reminder` | `reminder` | `message="đi ngủ", delay_s=3600, delay_minutes=60` | `"Đã ghi nhận lời nhắc 'đi ngủ' của Ngài."` | **PASS** |
| 5.4 | `"nhắc nhở"` / `"reminder"` | `reminder` | `reminder` | `message="nhắc nhở chung"` | `"Đã ghi nhận lời nhắc của Ngài."` | **PASS** |

### Category 6: System Power & Safety Confirmation (`system_power`)
| # | Input Query | Expected Action | Confirmation Required? | Danger Level | Confirmation Prompt | Response Text | Status |
|---|-------------|-----------------|------------------------|--------------|---------------------|---------------|--------|
| 6.1 | `"Tắt máy tính ngay"` | `system_power` | `True` | `CRITICAL` | `"Ngài có chắc chắn muốn tắt máy không?"` | `"Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận để thực thi nhằm đảm bảo an toàn dữ liệu, thưa Ngài."` | **PASS** |
| 6.2 | `"tắt máy"` / `"shutdown"` | `system_power` | `True` | `CRITICAL` | `"Ngài có chắc chắn muốn tắt máy không?"` | `"Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận để thực thi nhằm đảm bảo an toàn dữ liệu, thưa Ngài."` | **PASS** |
| 6.3 | `"khởi động lại"` / `"restart"` | `system_power` | `True` | `CRITICAL` | `"Ngài có chắc chắn muốn khởi động lại máy không?"` | `"Lệnh khởi động lại hệ thống đã được ghi nhận. Vui lòng xác nhận, thưa Ngài."` | **PASS** |
| 6.4 | `"chế độ ngủ"` / `"sleep"` | `system_power` | `True` | `MEDIUM` | `"Ngài có muốn đưa hệ thống vào chế độ ngủ không?"` | `"Đang đưa hệ thống vào chế độ ngủ tiết kiệm điện năng, thưa Ngài."` | **PASS** |
| 6.5 | `"khóa màn hình"` / `"khóa máy"` | `system_power` | `False` | `LOW` | `None` | `"Đã khóa màn hình máy tính, thưa Ngài."` | **PASS** |

### Category 7: Default Fallback & Adversarial Garbage Inputs
| # | Input Query | Expected Action | Resolved Action | Confidence | Response Text | Status |
|---|-------------|-----------------|-----------------|------------|---------------|--------|
| 7.1 | `"aslkdfjlasdjflkwje 192830"` | `unknown_intent` | `unknown_intent` | `0.0` | `"Tôi chưa hiểu lệnh này, vui lòng thử cách khác"` | **PASS** |
| 7.2 | `"mua cho tôi một con mèo"` | `unknown_intent` | `unknown_intent` | `0.0` | `"Tôi chưa hiểu lệnh này, vui lòng thử cách khác"` | **PASS** |
| 7.3 | `"bat den"` (unaccented fallback) | `unknown_intent` (offline) / LLM (online) | `unknown_intent` | `0.0` | `"Tôi chưa hiểu lệnh này, vui lòng thử cách khác"` | **PASS** |
| 7.4 | `""` (empty string) | `unknown_intent` | `unknown_intent` | `0.0` | `"Tôi chưa hiểu lệnh này, vui lòng thử cách khác"` | **PASS** |

---

## 3. Security, Safety, and Boundary Analysis

1. **Word Boundary Protection on Short Keywords**:
   - `_match_rule_key` employs regex word boundary anchors `(?:\b|^)...(?:\b|$)` for ASCII keys `<= 4` chars (e.g. `cpu`, `ram`, `gpu`, `ac`).
   - Words like "scraping", "frame", "ramp", "actor" will NOT accidentally trigger hardware or climate actions.
2. **Safety Confirmation Enforcement**:
   - Both `shutdown` and `restart` operations set `requires_confirmation = True` and `danger_level = "CRITICAL"`.
   - `sleep` sets `requires_confirmation = True` and `danger_level = "MEDIUM"`.
   - `lock` executes immediately without confirmation (`requires_confirmation = False`, `danger_level = "LOW"`).
3. **Vietnamese Conversational Tone**:
   - All response strings generated by `get_natural_response` use the polite JARVIS persona ("thưa Ngài", "cho Ngài", concise and clear).
