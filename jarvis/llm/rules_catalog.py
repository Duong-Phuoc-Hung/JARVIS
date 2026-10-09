"""
jarvis/llm/rules_catalog.py
===========================
Deterministic Vietnamese keyword and phrase mapping catalog for JARVIS Intent Routing.
Contains curated mappings covering smart home, media playback, hardware queries,
workspace configuration, system control, notes, and productivity routines.
"""
from __future__ import annotations

from jarvis.llm.models import IntentResult


def get_default_rules() -> dict[str, IntentResult]:
    """
    Returns a newly constructed dictionary of default keyword and phrase rules.
    """
    return {
            # 1. Smart Home (Category 1)
            "bật đèn phòng khách": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "light", "service": "turn_on", "entity_id": "light.living_room"},
                source="rule_fallback",
                response_text="Đang bật đèn phòng khách cho Ngài.",
            ),
            "tắt đèn phòng khách": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "light", "service": "turn_off", "entity_id": "light.living_room"},
                source="rule_fallback",
                response_text="Đang tắt đèn phòng khách cho Ngài.",
            ),
            "bật đèn phòng ngủ": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "light", "service": "turn_on", "entity_id": "light.bedroom"},
                source="rule_fallback",
                response_text="Đang bật đèn phòng ngủ cho Ngài.",
            ),
            "tắt đèn phòng ngủ": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "light", "service": "turn_off", "entity_id": "light.bedroom"},
                source="rule_fallback",
                response_text="Đang tắt đèn phòng ngủ cho Ngài.",
            ),
            "bật đèn bàn": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "light", "service": "turn_on", "entity_id": "light.desk_lamp"},
                source="rule_fallback",
                response_text="Đang bật đèn bàn làm việc cho Ngài.",
            ),
            "tắt đèn bàn": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "light", "service": "turn_off", "entity_id": "light.desk_lamp"},
                source="rule_fallback",
                response_text="Đang tắt đèn bàn làm việc cho Ngài.",
            ),
            "bật đèn làm việc": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "light", "service": "turn_on", "entity_id": "light.desk_lamp"},
                source="rule_fallback",
                response_text="Đang bật đèn bàn làm việc cho Ngài.",
            ),
            "tắt đèn làm việc": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "light", "service": "turn_off", "entity_id": "light.desk_lamp"},
                source="rule_fallback",
                response_text="Đang tắt đèn bàn làm việc cho Ngài.",
            ),
            "bật đèn": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "light", "service": "turn_on", "entity_id": "light.living_room"},
                source="rule_fallback",
                response_text="Đang bật đèn cho Ngài.",
            ),
            "tắt đèn": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "light", "service": "turn_off", "entity_id": "light.living_room"},
                source="rule_fallback",
                response_text="Đang tắt đèn cho Ngài.",
            ),
            "mở đèn": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "light", "service": "turn_on", "entity_id": "light.living_room"},
                source="rule_fallback",
                response_text="Đang bật đèn cho Ngài.",
            ),
            "tắt điện": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "light", "service": "turn_off", "entity_id": "light.living_room"},
                source="rule_fallback",
                response_text="Đang tắt đèn cho Ngài.",
            ),
            "bật điện": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "light", "service": "turn_on", "entity_id": "light.living_room"},
                source="rule_fallback",
                response_text="Đang bật đèn cho Ngài.",
            ),
            "bật quạt phòng khách": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "fan", "service": "turn_on", "entity_id": "fan.living_room"},
                source="rule_fallback",
                response_text="Đang bật quạt cho Ngài.",
            ),
            "tắt quạt phòng khách": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "fan", "service": "turn_off", "entity_id": "fan.living_room"},
                source="rule_fallback",
                response_text="Đang tắt quạt cho Ngài.",
            ),
            "bật quạt": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "fan", "service": "turn_on", "entity_id": "fan.living_room"},
                source="rule_fallback",
                response_text="Đang bật quạt cho Ngài.",
            ),
            "tắt quạt": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "fan", "service": "turn_off", "entity_id": "fan.living_room"},
                source="rule_fallback",
                response_text="Đang tắt quạt cho Ngài.",
            ),
            "bật điều hòa": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "climate", "service": "turn_on", "entity_id": "climate.ac_unit"},
                source="rule_fallback",
                response_text="Đang bật điều hòa cho Ngài.",
            ),
            "tắt điều hòa": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "climate", "service": "turn_off", "entity_id": "climate.ac_unit"},
                source="rule_fallback",
                response_text="Đang tắt điều hòa cho Ngài.",
            ),
            "bật máy lạnh": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "climate", "service": "turn_on", "entity_id": "climate.ac_unit"},
                source="rule_fallback",
                response_text="Đang bật điều hòa cho Ngài.",
            ),
            "tắt máy lạnh": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "climate", "service": "turn_off", "entity_id": "climate.ac_unit"},
                source="rule_fallback",
                response_text="Đang tắt điều hòa cho Ngài.",
            ),
            "bật thiết bị": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "switch", "service": "turn_on", "entity_id": "switch.main"},
                source="rule_fallback",
                response_text="Đang bật thiết bị cho Ngài.",
            ),
            "tắt thiết bị": IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": "switch", "service": "turn_off", "entity_id": "switch.main"},
                source="rule_fallback",
                response_text="Đang tắt thiết bị cho Ngài.",
            ),

            # 2. Hardware / Telemetry / System Status (Category 2)
            "kiểm tra nhiệt độ cpu": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "cpu"},
                source="rule_fallback",
                response_text="Nhiệt độ CPU hiện tại là 45 độ C, hiệu năng ổn định, thưa Ngài.",
            ),
            "nhiệt độ cpu": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "cpu"},
                source="rule_fallback",
                response_text="Nhiệt độ CPU hiện tại là 45 độ C, hiệu năng ổn định, thưa Ngài.",
            ),
            "kiểm tra nhiệt độ": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "cpu"},
                source="rule_fallback",
                response_text="Nhiệt độ CPU hiện tại là 45 độ C, hiệu năng ổn định, thưa Ngài.",
            ),
            "kiểm tra cpu": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "cpu"},
                source="rule_fallback",
                response_text="Nhiệt độ CPU hiện tại là 45 độ C, hiệu năng ổn định, thưa Ngài.",
            ),
            "cpu": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "cpu"},
                source="rule_fallback",
                response_text="Nhiệt độ CPU hiện tại là 45 độ C, hiệu năng ổn định, thưa Ngài.",
            ),
            "kiểm tra ram": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "ram"},
                source="rule_fallback",
                response_text="Bộ nhớ RAM đang sử dụng ở mức bình thường, tài nguyên dồi dào, thưa Ngài.",
            ),
            "dung lượng ram": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "ram"},
                source="rule_fallback",
                response_text="Bộ nhớ RAM đang sử dụng ở mức bình thường, tài nguyên dồi dào, thưa Ngài.",
            ),
            "bộ nhớ ram": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "ram"},
                source="rule_fallback",
                response_text="Bộ nhớ RAM đang sử dụng ở mức bình thường, tài nguyên dồi dào, thưa Ngài.",
            ),
            "ram": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "ram"},
                source="rule_fallback",
                response_text="Bộ nhớ RAM đang sử dụng ở mức bình thường, tài nguyên dồi dào, thưa Ngài.",
            ),
            "kiểm tra gpu": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "gpu"},
                source="rule_fallback",
                response_text="Card đồ họa hoạt động bình thường, nhiệt độ trong ngưỡng an toàn, thưa Ngài.",
            ),
            "nhiệt độ gpu": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "gpu"},
                source="rule_fallback",
                response_text="Card đồ họa hoạt động bình thường, nhiệt độ trong ngưỡng an toàn, thưa Ngài.",
            ),
            "card đồ họa": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "gpu"},
                source="rule_fallback",
                response_text="Card đồ họa hoạt động bình thường, nhiệt độ trong ngưỡng an toàn, thưa Ngài.",
            ),
            "card màn hình": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "gpu"},
                source="rule_fallback",
                response_text="Card đồ họa hoạt động bình thường, nhiệt độ trong ngưỡng an toàn, thưa Ngài.",
            ),
            "gpu": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "gpu"},
                source="rule_fallback",
                response_text="Card đồ họa hoạt động bình thường, nhiệt độ trong ngưỡng an toàn, thưa Ngài.",
            ),

            # Battery Telemetry
            "kiểm tra pin": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "battery"},
                source="rule_fallback",
                response_text="Đang kiểm tra tình trạng pin hệ thống cho Ngài.",
            ),
            "kiem tra pin": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "battery"},
                source="rule_fallback",
                response_text="Đang kiểm tra tình trạng pin hệ thống cho Ngài.",
            ),
            "pin còn bao nhiêu": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "battery"},
                source="rule_fallback",
                response_text="Đang kiểm tra dung lượng pin cho Ngài.",
            ),
            "tình trạng pin": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "battery"},
                source="rule_fallback",
                response_text="Đang kiểm tra tình trạng pin hệ thống cho Ngài.",
            ),
            "xem pin": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "battery"},
                source="rule_fallback",
                response_text="Đang kiểm tra tình trạng pin cho Ngài.",
            ),
            "check battery": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "battery"},
                source="rule_fallback",
                response_text="Checking system battery status, Sir.",
            ),
            "battery status": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "battery"},
                source="rule_fallback",
                response_text="Checking system battery status, Sir.",
            ),
            "dung lượng ổ đĩa": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "disk"},
                source="rule_fallback",
                response_text="Ổ đĩa đang hoạt động trong trạng thái tốt, thưa Ngài.",
            ),
            "ổ cứng": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "disk"},
                source="rule_fallback",
                response_text="Ổ đĩa đang hoạt động trong trạng thái tốt, thưa Ngài.",
            ),
            "cpu mấy phần trăm": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "cpu"},
                source="rule_fallback",
                response_text="Nhiệt độ CPU hiện tại là 45 độ C, hiệu năng ổn định, thưa Ngài.",
            ),
            "mức sử dụng cpu": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "cpu"},
                source="rule_fallback",
                response_text="Nhiệt độ CPU hiện tại là 45 độ C, hiệu năng ổn định, thưa Ngài.",
            ),
            "tốc độ cpu": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "cpu"},
                source="rule_fallback",
                response_text="Nhiệt độ CPU hiện tại là 45 độ C, hiệu năng ổn định, thưa Ngài.",
            ),
            "xung nhịp cpu": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "cpu"},
                source="rule_fallback",
                response_text="Nhiệt độ CPU hiện tại là 45 độ C, hiệu năng ổn định, thưa Ngài.",
            ),
            "ram còn bao nhiêu": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "ram"},
                source="rule_fallback",
                response_text="Bộ nhớ RAM đang sử dụng ở mức bình thường, tài nguyên dồi dào, thưa Ngài.",
            ),
            "ram còn lại bao nhiêu": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "ram"},
                source="rule_fallback",
                response_text="Bộ nhớ RAM đang sử dụng ở mức bình thường, tài nguyên dồi dào, thưa Ngài.",
            ),
            "bộ nhớ còn bao nhiêu": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "ram"},
                source="rule_fallback",
                response_text="Bộ nhớ RAM đang sử dụng ở mức bình thường, tài nguyên dồi dào, thưa Ngài.",
            ),
            "nhiệt độ máy": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "cpu"},
                source="rule_fallback",
                response_text="Nhiệt độ CPU hiện tại là 45 độ C, hiệu năng ổn định, thưa Ngài.",
            ),
            "nhiệt độ laptop": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "cpu"},
                source="rule_fallback",
                response_text="Nhiệt độ CPU hiện tại là 45 độ C, hiệu năng ổn định, thưa Ngài.",
            ),
            "nhiệt độ pc": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "cpu"},
                source="rule_fallback",
                response_text="Nhiệt độ CPU hiện tại là 45 độ C, hiệu năng ổn định, thưa Ngài.",
            ),
            "dung lượng pin": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "battery"},
                source="rule_fallback",
                response_text="Pin hệ thống đang ở mức an toàn, thưa Ngài.",
            ),
            "mức pin": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "battery"},
                source="rule_fallback",
                response_text="Pin hệ thống đang ở mức an toàn, thưa Ngài.",
            ),
            "pin mấy phần trăm": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "battery"},
                source="rule_fallback",
                response_text="Pin hệ thống đang ở mức an toàn, thưa Ngài.",
            ),
            "pin": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "battery"},
                source="rule_fallback",
                response_text="Pin hệ thống đang ở mức an toàn, thưa Ngài.",
            ),
            "battery": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "battery"},
                source="rule_fallback",
                response_text="Pin hệ thống đang ở mức an toàn, thưa Ngài.",
            ),
            "tình trạng hệ thống": IntentResult(
                action_name="hardware_status_query",
                parameters={},
                source="rule_fallback",
                response_text="Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu, CPU và RAM ở mức an toàn, thưa Ngài.",
            ),
            "tình trạng máy": IntentResult(
                action_name="hardware_status_query",
                parameters={},
                source="rule_fallback",
                response_text="Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu, CPU và RAM ở mức an toàn, thưa Ngài.",
            ),
            "trạng thái máy tính": IntentResult(
                action_name="hardware_status_query",
                parameters={},
                source="rule_fallback",
                response_text="Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu, CPU và RAM ở mức an toàn, thưa Ngài.",
            ),
            "sức khỏe máy tính": IntentResult(
                action_name="hardware_status_query",
                parameters={},
                source="rule_fallback",
                response_text="Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu, CPU và RAM ở mức an toàn, thưa Ngài.",
            ),
            "kiểm tra hệ thống": IntentResult(
                action_name="hardware_status_query",
                parameters={},
                source="rule_fallback",
                response_text="Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu, CPU và RAM ở mức an toàn, thưa Ngài.",
            ),

            # 3. Spotify / Music (Category 3)
            "mở spotify": IntentResult(
                action_name="spotify",
                parameters={},
                source="rule_fallback",
                response_text="Đang mở Spotify và phát nhạc cho Ngài.",
            ),
            "bật spotify": IntentResult(
                action_name="spotify",
                parameters={},
                source="rule_fallback",
                response_text="Đang mở Spotify và phát nhạc cho Ngài.",
            ),
            # H-07 fix: a bare, unqualified single-word "spotify" key was
            # removed here. _match_rule_key()'s word_count==1 path is a
            # whole-word (not full-utterance) boundary match, so it fired on
            # ANY sentence containing the standalone word "spotify" --
            # including questions ("spotify có tốt không") and negations
            # ("tôi không muốn mở spotify") -- incorrectly launching Spotify.
            # Every genuine positive alias ("mở spotify", "bật spotify",
            # "mo spotify", "open spotify", bare "spotify" alone) is still
            # covered by dedicated verb-qualified dict entries and the
            # anchored (^...$) regexes elsewhere in this file, so removing
            # this overly broad key closes the false-positive gap with no
            # loss of legitimate positive coverage.
            "bật nhạc": IntentResult(
                action_name="spotify",
                parameters={},
                source="rule_fallback",
                response_text="Đang mở Spotify và phát nhạc cho Ngài.",
            ),
            "phát nhạc": IntentResult(
                action_name="spotify",
                parameters={},
                source="rule_fallback",
                response_text="Đang mở Spotify và phát nhạc cho Ngài.",
            ),
            "mở nhạc": IntentResult(
                action_name="spotify",
                parameters={},
                source="rule_fallback",
                response_text="Đang mở Spotify và phát nhạc cho Ngài.",
            ),
            "nghe nhạc": IntentResult(
                action_name="spotify",
                parameters={},
                source="rule_fallback",
                response_text="Đang mở Spotify và phát nhạc cho Ngài.",
            ),
            "nhạc": IntentResult(
                action_name="spotify",
                parameters={},
                source="rule_fallback",
                response_text="Đang mở Spotify và phát nhạc cho Ngài.",
            ),
            "dừng nhạc": IntentResult(
                action_name="spotify",
                parameters={"command": "pause"},
                source="rule_fallback",
                response_text="Đã tạm dừng phát nhạc, thưa Ngài.",
            ),
            "tạm dừng nhạc": IntentResult(
                action_name="spotify",
                parameters={"command": "pause"},
                source="rule_fallback",
                response_text="Đã tạm dừng phát nhạc, thưa Ngài.",
            ),
            "tắt nhạc": IntentResult(
                action_name="spotify",
                parameters={"command": "pause"},
                source="rule_fallback",
                response_text="Đã tạm dừng phát nhạc, thưa Ngài.",
            ),
            "dừng phát nhạc": IntentResult(
                action_name="spotify",
                parameters={"command": "pause"},
                source="rule_fallback",
                response_text="Đã tạm dừng phát nhạc, thưa Ngài.",
            ),
            "bài tiếp theo": IntentResult(
                action_name="spotify",
                parameters={"command": "next"},
                source="rule_fallback",
                response_text="Đang chuyển bài tiếp theo, thưa Ngài.",
            ),
            "chuyển bài": IntentResult(
                action_name="spotify",
                parameters={"command": "next"},
                source="rule_fallback",
                response_text="Đang chuyển bài tiếp theo, thưa Ngài.",
            ),

            # 4. Weather (Category 4)
            "dự báo thời tiết hà nội": IntentResult(
                action_name="shell_exec",
                parameters={"command": "curl -s wttr.in/Hanoi?format=3", "topic": "weather", "location": "Hà Nội"},
                source="rule_fallback",
                response_text="Đang kiểm tra thông tin thời tiết tại Hà Nội cho Ngài.",
            ),
            "thời tiết hà nội": IntentResult(
                action_name="shell_exec",
                parameters={"command": "curl -s wttr.in/Hanoi?format=3", "topic": "weather", "location": "Hà Nội"},
                source="rule_fallback",
                response_text="Đang kiểm tra thông tin thời tiết tại Hà Nội cho Ngài.",
            ),
            "dự báo thời tiết sài gòn": IntentResult(
                action_name="shell_exec",
                parameters={"command": "curl -s wttr.in/Saigon?format=3", "topic": "weather", "location": "Sài Gòn"},
                source="rule_fallback",
                response_text="Đang kiểm tra thông tin thời tiết tại Sài Gòn cho Ngài.",
            ),
            "thời tiết sài gòn": IntentResult(
                action_name="shell_exec",
                parameters={"command": "curl -s wttr.in/Saigon?format=3", "topic": "weather", "location": "Sài Gòn"},
                source="rule_fallback",
                response_text="Đang kiểm tra thông tin thời tiết tại Sài Gòn cho Ngài.",
            ),
            "thời tiết tp hcm": IntentResult(
                action_name="shell_exec",
                parameters={"command": "curl -s wttr.in/Saigon?format=3", "topic": "weather", "location": "Sài Gòn"},
                source="rule_fallback",
                response_text="Đang kiểm tra thông tin thời tiết tại Sài Gòn cho Ngài.",
            ),
            "dự báo thời tiết": IntentResult(
                action_name="shell_exec",
                parameters={"command": "curl -s wttr.in?format=3", "topic": "weather", "location": "current"},
                source="rule_fallback",
                response_text="Đang kiểm tra thông tin thời tiết cho Ngài.",
            ),
            "thời tiết hôm nay": IntentResult(
                action_name="shell_exec",
                parameters={"command": "curl -s wttr.in?format=3", "topic": "weather", "location": "current"},
                source="rule_fallback",
                response_text="Đang kiểm tra thông tin thời tiết hôm nay cho Ngài.",
            ),
            "xem thời tiết": IntentResult(
                action_name="shell_exec",
                parameters={"command": "curl -s wttr.in?format=3", "topic": "weather", "location": "current"},
                source="rule_fallback",
                response_text="Đang kiểm tra thông tin thời tiết hôm nay cho Ngài.",
            ),
            "nhiệt độ thời tiết": IntentResult(
                action_name="shell_exec",
                parameters={"command": "curl -s wttr.in?format=3", "topic": "weather", "location": "current"},
                source="rule_fallback",
                response_text="Đang kiểm tra thông tin thời tiết hôm nay cho Ngài.",
            ),
            "trời có mưa không": IntentResult(
                action_name="shell_exec",
                parameters={"command": "curl -s wttr.in?format=3", "topic": "weather", "location": "current"},
                source="rule_fallback",
                response_text="Đang kiểm tra thông tin thời tiết hôm nay cho Ngài.",
            ),
            "thời tiết": IntentResult(
                action_name="shell_exec",
                parameters={"command": "curl -s wttr.in?format=3", "topic": "weather", "location": "current"},
                source="rule_fallback",
                response_text="Đang kiểm tra thông tin thời tiết hôm nay cho Ngài.",
            ),

            # 4b. Crypto / Finance (web search shortcuts — no API key needed)
            "tỷ giá usd": IntentResult(action_name="crypto_rates", parameters={"currency": "USD"}, source="rule_fallback", response_text="Đang kiểm tra tỷ giá Đô la Mỹ USD cho Ngài."),
            "ty gia usd": IntentResult(action_name="crypto_rates", parameters={"currency": "USD"}, source="rule_fallback", response_text="Đang kiểm tra tỷ giá Đô la Mỹ USD cho Ngài."),
            "giá usd": IntentResult(action_name="crypto_rates", parameters={"currency": "USD"}, source="rule_fallback", response_text="Đang kiểm tra giá USD cho Ngài."),
            "gia usd": IntentResult(action_name="crypto_rates", parameters={"currency": "USD"}, source="rule_fallback", response_text="Đang kiểm tra giá USD cho Ngài."),
            "1 usd": IntentResult(action_name="crypto_rates", parameters={"currency": "USD"}, source="rule_fallback", response_text="Đang kiểm tra tỷ giá USD cho Ngài."),
            "1 đô": IntentResult(action_name="crypto_rates", parameters={"currency": "USD"}, source="rule_fallback", response_text="Đang kiểm tra giá 1 Đô la Mỹ cho Ngài."),
            "tỷ giá eur": IntentResult(action_name="crypto_rates", parameters={"currency": "EUR"}, source="rule_fallback", response_text="Đang kiểm tra tỷ giá Euro EUR cho Ngài."),
            "ty gia eur": IntentResult(action_name="crypto_rates", parameters={"currency": "EUR"}, source="rule_fallback", response_text="Đang kiểm tra tỷ giá Euro EUR cho Ngài."),
            "giá eur": IntentResult(action_name="crypto_rates", parameters={"currency": "EUR"}, source="rule_fallback", response_text="Đang kiểm tra giá Euro cho Ngài."),
            "gia eur": IntentResult(action_name="crypto_rates", parameters={"currency": "EUR"}, source="rule_fallback", response_text="Đang kiểm tra giá Euro cho Ngài."),
            "xem gia bitcoin": IntentResult(action_name="web_open", parameters={"target": "https://www.google.com/search?q=giá+bitcoin+hôm+nay", "site": "google"}, source="rule_fallback", response_text="Đang tra giá Bitcoin cho Ngài."),
            "gia bitcoin": IntentResult(action_name="web_open", parameters={"target": "https://www.google.com/search?q=giá+bitcoin+hôm+nay", "site": "google"}, source="rule_fallback", response_text="Đang tra giá Bitcoin cho Ngài."),
            "btc hom nay": IntentResult(action_name="web_open", parameters={"target": "https://www.google.com/search?q=BTC+giá+hôm+nay", "site": "google"}, source="rule_fallback", response_text="Đang tra giá BTC cho Ngài."),
            "gia eth": IntentResult(action_name="web_open", parameters={"target": "https://www.google.com/search?q=giá+ethereum+hôm+nay", "site": "google"}, source="rule_fallback", response_text="Đang tra giá ETH cho Ngài."),
            "gia ethereum": IntentResult(action_name="web_open", parameters={"target": "https://www.google.com/search?q=giá+ethereum+hôm+nay", "site": "google"}, source="rule_fallback", response_text="Đang tra giá Ethereum cho Ngài."),
            "thi truong hom nay": IntentResult(action_name="web_open", parameters={"target": "https://coinmarketcap.com", "site": "coinmarketcap"}, source="rule_fallback", response_text="Đang mở CoinMarketCap cho Ngài."),
            "cho tao xem binance": IntentResult(action_name="web_open", parameters={"target": "binance", "site": "binance"}, source="rule_fallback", response_text="Đang mở Binance cho Ngài."),
            "xem binance": IntentResult(action_name="web_open", parameters={"target": "binance", "site": "binance"}, source="rule_fallback", response_text="Đang mở Binance cho Ngài."),

            # 4c. Date/Time
            "may gio roi": IntentResult(action_name="shell_exec", parameters={"command": "powershell -c \"Get-Date -Format 'HH:mm:ss'\"", "topic": "time"}, source="rule_fallback", response_text="Đang kiểm tra giờ hiện tại cho Ngài."),
            "hom nay thu may": IntentResult(action_name="shell_exec", parameters={"command": "powershell -c \"(Get-Date).ToString('dddd, dd/MM/yyyy')\"", "topic": "date"}, source="rule_fallback", response_text="Đang kiểm tra ngày hôm nay cho Ngài."),
            "hom nay ngay may": IntentResult(action_name="shell_exec", parameters={"command": "powershell -c \"(Get-Date).ToString('dd/MM/yyyy')\"", "topic": "date"}, source="rule_fallback", response_text="Đang kiểm tra ngày hôm nay cho Ngài."),
            "xem gio": IntentResult(action_name="shell_exec", parameters={"command": "powershell -c \"Get-Date -Format 'HH:mm'\"", "topic": "time"}, source="rule_fallback", response_text="Đang kiểm tra giờ hiện tại cho Ngài."),

            # 4d. Display / Brightness
            "do sang man hinh": IntentResult(action_name="system_brightness", parameters={"query": True}, source="rule_fallback", response_text="Đang kiểm tra độ sáng màn hình cho Ngài."),
            "độ sáng màn hình": IntentResult(action_name="system_brightness", parameters={"query": True}, source="rule_fallback", response_text="Đang kiểm tra độ sáng màn hình cho Ngài."),
            "do sang": IntentResult(action_name="system_brightness", parameters={"query": True}, source="rule_fallback", response_text="Đang kiểm tra độ sáng màn hình cho Ngài."),

            # 4e. Sleep/Hibernate
            "ngu dong": IntentResult(action_name="system_power", parameters={"action": "hibernate"}, source="rule_fallback", response_text="Đang chuyển máy sang chế độ ngủ đông, thưa Ngài."),
            "ngu": IntentResult(action_name="system_power", parameters={"action": "sleep"}, source="rule_fallback", response_text="Đang chuyển máy sang chế độ ngủ, thưa Ngài."),

            # 4f. Spotify navigation
            "bai truoc": IntentResult(action_name="spotify", parameters={"action": "previous"}, source="rule_fallback", response_text="Đang phát bài trước cho Ngài."),
            "quay lai bai truoc": IntentResult(action_name="spotify", parameters={"action": "previous"}, source="rule_fallback", response_text="Đang phát bài trước cho Ngài."),
            "chat voi claude": IntentResult(action_name="web_open", parameters={"target": "claude", "site": "claude"}, source="rule_fallback", response_text="Đang mở Claude AI cho Ngài."),

            # 4g. File operations
            "tao file moi": IntentResult(action_name="file_search", parameters={"action": "create", "clarify": True}, source="rule_fallback", response_text="Ngài muốn tạo file tên gì và ở đâu?"),
            "tạo file mới": IntentResult(action_name="file_search", parameters={"action": "create", "clarify": True}, source="rule_fallback", response_text="Ngài muốn tạo file tên gì và ở đâu?"),
            "xoa file tam": IntentResult(action_name="shell_exec", parameters={"command": "powershell -c \"Remove-Item $env:TEMP\\* -Recurse -Force -ErrorAction SilentlyContinue; Write-Output 'Đã xóa file tạm'\"", "topic": "cleanup"}, source="rule_fallback", response_text="Đang xóa file tạm để giải phóng bộ nhớ cho Ngài."),
            "xóa file tạm": IntentResult(action_name="shell_exec", parameters={"command": "powershell -c \"Remove-Item $env:TEMP\\* -Recurse -Force -ErrorAction SilentlyContinue; Write-Output 'Đã xóa file tạm'\"", "topic": "cleanup"}, source="rule_fallback", response_text="Đang xóa file tạm để giải phóng bộ nhớ cho Ngài."),
            "don dep may tinh": IntentResult(action_name="shell_exec", parameters={"command": "powershell -c \"Remove-Item $env:TEMP\\* -Recurse -Force -ErrorAction SilentlyContinue; Write-Output 'Đã dọn dẹp'\"", "topic": "cleanup"}, source="rule_fallback", response_text="Đang dọn dẹp file tạm trên máy cho Ngài."),

            # 4h. Window management
            "phong to cua so": IntentResult(action_name="window_active", parameters={"action": "maximize"}, source="rule_fallback", response_text="Đang phóng to cửa sổ cho Ngài."),
            "phóng to cửa sổ": IntentResult(action_name="window_active", parameters={"action": "maximize"}, source="rule_fallback", response_text="Đang phóng to cửa sổ cho Ngài."),
            "phóng to": IntentResult(action_name="window_active", parameters={"action": "maximize"}, source="rule_fallback", response_text="Đang phóng to cửa sổ cho Ngài."),
            "phong to": IntentResult(action_name="window_active", parameters={"action": "maximize"}, source="rule_fallback", response_text="Đang phóng to cửa sổ cho Ngài."),
            "chia màn hình sang trái": IntentResult(action_name="window_active", parameters={"action": "snap_left"}, source="rule_fallback", response_text="Đang xếp cửa sổ sang bên trái màn hình cho Ngài."),
            "chia màn hình sang phải": IntentResult(action_name="window_active", parameters={"action": "snap_right"}, source="rule_fallback", response_text="Đang xếp cửa sổ sang bên phải màn hình cho Ngài."),
            "chia đôi màn hình": IntentResult(action_name="window_active", parameters={"action": "snap_left"}, source="rule_fallback", response_text="Đang chia đôi màn hình cho Ngài."),
            "xếp sang trái": IntentResult(action_name="window_active", parameters={"action": "snap_left"}, source="rule_fallback", response_text="Đang xếp cửa sổ sang bên trái cho Ngài."),
            "xếp sang phải": IntentResult(action_name="window_active", parameters={"action": "snap_right"}, source="rule_fallback", response_text="Đang xếp cửa sổ sang bên phải cho Ngài."),
            "thu nhỏ cửa sổ": IntentResult(action_name="window_active", parameters={"action": "minimize"}, source="rule_fallback", response_text="Đang thu nhỏ cửa sổ cho Ngài."),
            "thu nhỏ": IntentResult(action_name="window_active", parameters={"action": "minimize"}, source="rule_fallback", response_text="Đang thu nhỏ cửa sổ cho Ngài."),
            "thu nho": IntentResult(action_name="window_active", parameters={"action": "minimize"}, source="rule_fallback", response_text="Đang thu nhỏ cửa sổ cho Ngài."),
            "đóng cửa sổ": IntentResult(action_name="window_active", parameters={"action": "close"}, source="rule_fallback", response_text="Đang đóng cửa sổ hiện tại cho Ngài."),
            "dong cua so": IntentResult(action_name="window_active", parameters={"action": "close"}, source="rule_fallback", response_text="Đang đóng cửa sổ hiện tại cho Ngài."),
            "tắt cửa sổ": IntentResult(action_name="window_active", parameters={"action": "close"}, source="rule_fallback", response_text="Đang đóng cửa sổ hiện tại cho Ngài."),
            "chuyển ứng dụng": IntentResult(action_name="window_active", parameters={"action": "switch"}, source="rule_fallback", response_text="Đang chuyển sang ứng dụng tiếp theo cho Ngài."),
            "chuyển cửa sổ": IntentResult(action_name="window_active", parameters={"action": "switch"}, source="rule_fallback", response_text="Đang chuyển sang cửa sổ tiếp theo cho Ngài."),
            "chuyen cua so": IntentResult(action_name="window_active", parameters={"action": "switch"}, source="rule_fallback", response_text="Đang chuyển sang cửa sổ tiếp theo cho Ngài."),
            "đóng tab": IntentResult(action_name="close_tab", parameters={}, source="rule_fallback", response_text="Đang đóng tab hiện tại cho Ngài."),
            "dong tab": IntentResult(action_name="close_tab", parameters={}, source="rule_fallback", response_text="Đang đóng tab hiện tại cho Ngài."),
            "tắt tab": IntentResult(action_name="close_tab", parameters={}, source="rule_fallback", response_text="Đang đóng tab hiện tại cho Ngài."),
            "close tab": IntentResult(action_name="close_tab", parameters={}, source="rule_fallback", response_text="Closing current tab, Sir."),
            "cuộn xuống": IntentResult(action_name="page_scroll", parameters={"direction": "down"}, source="rule_fallback", response_text="Đang cuộn trang xuống cho Ngài."),
            "cuon xuong": IntentResult(action_name="page_scroll", parameters={"direction": "down"}, source="rule_fallback", response_text="Đang cuộn trang xuống cho Ngài."),
            "kéo xuống": IntentResult(action_name="page_scroll", parameters={"direction": "down"}, source="rule_fallback", response_text="Đang kéo trang xuống cho Ngài."),
            "scroll down": IntentResult(action_name="page_scroll", parameters={"direction": "down"}, source="rule_fallback", response_text="Scrolling down, Sir."),
            "cuộn lên": IntentResult(action_name="page_scroll", parameters={"direction": "up"}, source="rule_fallback", response_text="Đang cuộn trang lên cho Ngài."),
            "cuon len": IntentResult(action_name="page_scroll", parameters={"direction": "up"}, source="rule_fallback", response_text="Đang cuộn trang lên cho Ngài."),
            "kéo lên": IntentResult(action_name="page_scroll", parameters={"direction": "up"}, source="rule_fallback", response_text="Đang kéo trang lên cho Ngài."),
            "scroll up": IntentResult(action_name="page_scroll", parameters={"direction": "up"}, source="rule_fallback", response_text="Scrolling up, Sir."),
            "tải lại trang": IntentResult(action_name="page_refresh", parameters={}, source="rule_fallback", response_text="Đang tải lại trang cho Ngài."),
            "tai lai trang": IntentResult(action_name="page_refresh", parameters={}, source="rule_fallback", response_text="Đang tải lại trang cho Ngài."),
            "load lại": IntentResult(action_name="page_refresh", parameters={}, source="rule_fallback", response_text="Đang tải lại trang cho Ngài."),
            "reload": IntentResult(action_name="page_refresh", parameters={}, source="rule_fallback", response_text="Reloading page, Sir."),
            "refresh": IntentResult(action_name="page_refresh", parameters={}, source="rule_fallback", response_text="Refreshing page, Sir."),

            # 4i. Clipboard cut
            "cat": IntentResult(action_name="skill_clipboard", parameters={"action": "cut"}, source="rule_fallback", response_text="Đã cắt nội dung vào clipboard."),
            "cắt": IntentResult(action_name="skill_clipboard", parameters={"action": "cut"}, source="rule_fallback", response_text="Đã cắt nội dung vào clipboard."),
            "xoa clipboard": IntentResult(action_name="skill_clipboard", parameters={"action": "clear"}, source="rule_fallback", response_text="Đã xóa clipboard."),
            "xóa clipboard": IntentResult(action_name="skill_clipboard", parameters={"action": "clear"}, source="rule_fallback", response_text="Đã xóa clipboard."),

            # 4j. Network speed
            "toc do mang": IntentResult(action_name="shell_exec", parameters={"command": "powershell -c \"Test-Connection 8.8.8.8 -Count 3 | Select-Object ResponseTime | Measure-Object -Property ResponseTime -Average | ForEach-Object { Write-Output \\\"Ping trung bình: $([math]::Round($_.Average,1))ms\\\" }\"", "topic": "network"}, source="rule_fallback", response_text="Đang kiểm tra tốc độ mạng cho Ngài."),
            "tốc độ mạng": IntentResult(action_name="shell_exec", parameters={"command": "powershell -c \"Test-Connection 8.8.8.8 -Count 3 | Select-Object ResponseTime | Measure-Object -Property ResponseTime -Average | ForEach-Object { Write-Output \\\"Ping: $([math]::Round($_.Average,1))ms\\\" }\"", "topic": "network"}, source="rule_fallback", response_text="Đang kiểm tra tốc độ mạng cho Ngài."),
            "kiem tra mang": IntentResult(action_name="shell_exec", parameters={"command": "powershell -c \"Test-Connection 8.8.8.8 -Count 1 | ForEach-Object { Write-Output \\\"Kết nối OK, ping: $($_.ResponseTime)ms\\\" }\"", "topic": "network"}, source="rule_fallback", response_text="Đang kiểm tra kết nối mạng cho Ngài."),

            # 4k. Notes & Memo
            "xem ghi chú": IntentResult(action_name="note_list", parameters={}, source="rule_fallback", response_text="Đang mở danh sách ghi chú cho Ngài."),
            "xem ghi chu": IntentResult(action_name="note_list", parameters={}, source="rule_fallback", response_text="Đang mở danh sách ghi chú cho Ngài."),
            "đọc ghi chú": IntentResult(action_name="note_list", parameters={}, source="rule_fallback", response_text="Đang đọc các ghi chú gần nhất cho Ngài."),
            "doc ghi chu": IntentResult(action_name="note_list", parameters={}, source="rule_fallback", response_text="Đang đọc các ghi chú gần nhất cho Ngài."),
            "danh sách ghi chú": IntentResult(action_name="note_list", parameters={}, source="rule_fallback", response_text="Đang mở danh sách ghi chú cho Ngài."),
            "các ghi chú": IntentResult(action_name="note_list", parameters={}, source="rule_fallback", response_text="Đang đọc các ghi chú cho Ngài."),

            # 4l. Screen Dialogs & Error Popups
            "xử lý lỗi màn hình": IntentResult(action_name="dialog_resolve", parameters={"auto_dismiss": True}, source="rule_fallback", response_text="Đang kiểm tra và xử lý các hộp thoại lỗi trên màn hình cho Ngài."),
            "đóng thông báo lỗi": IntentResult(action_name="dialog_resolve", parameters={"auto_dismiss": True}, source="rule_fallback", response_text="Đang đóng các hộp thoại lỗi cho Ngài."),
            "tắt popup lỗi": IntentResult(action_name="dialog_resolve", parameters={"auto_dismiss": True}, source="rule_fallback", response_text="Đang đóng các popup lỗi cho Ngài."),
            "đóng popup": IntentResult(action_name="dialog_resolve", parameters={"auto_dismiss": True}, source="rule_fallback", response_text="Đang đóng các popup cho Ngài."),
            "fix dialog": IntentResult(action_name="dialog_resolve", parameters={"auto_dismiss": True}, source="rule_fallback", response_text="Checking and resolving active dialogs, Sir."),

            # 4m. Web Dashboard & Productivity Workflows
            "mở dashboard": IntentResult(action_name="web_open", parameters={"target": "http://127.0.0.1:8080", "site": "dashboard"}, source="rule_fallback", response_text="Đang mở giao diện bảng điều khiển trực quan cho Ngài."),
            "mo dashboard": IntentResult(action_name="web_open", parameters={"target": "http://127.0.0.1:8080", "site": "dashboard"}, source="rule_fallback", response_text="Đang mở giao diện bảng điều khiển trực quan cho Ngài."),
            "xem dashboard": IntentResult(action_name="web_open", parameters={"target": "http://127.0.0.1:8080", "site": "dashboard"}, source="rule_fallback", response_text="Đang mở giao diện bảng điều khiển trực quan cho Ngài."),
            "giao diện web": IntentResult(action_name="web_open", parameters={"target": "http://127.0.0.1:8080", "site": "dashboard"}, source="rule_fallback", response_text="Đang mở giao diện bảng điều khiển trực quan cho Ngài."),
            "dashboard": IntentResult(action_name="web_open", parameters={"target": "http://127.0.0.1:8080", "site": "dashboard"}, source="rule_fallback", response_text="Đang mở giao diện bảng điều khiển trực quan cho Ngài."),
            "chế độ làm việc": IntentResult(action_name="workflow_preset", parameters={"preset": "work"}, source="rule_fallback", response_text="Đang kích hoạt chế độ làm việc tập trung cho Ngài."),
            "bắt đầu làm việc": IntentResult(action_name="workflow_preset", parameters={"preset": "work"}, source="rule_fallback", response_text="Đang kích hoạt chế độ làm việc tập trung cho Ngài."),
            "chế độ nghỉ ngơi": IntentResult(action_name="workflow_preset", parameters={"preset": "relax"}, source="rule_fallback", response_text="Đang kích hoạt chế độ nghỉ ngơi thư giãn cho Ngài."),
            "nghỉ ngơi": IntentResult(action_name="workflow_preset", parameters={"preset": "relax"}, source="rule_fallback", response_text="Đang kích hoạt chế độ nghỉ ngơi thư giãn cho Ngài."),
            "thư giãn": IntentResult(action_name="workflow_preset", parameters={"preset": "relax"}, source="rule_fallback", response_text="Đang kích hoạt chế độ nghỉ ngơi thư giãn cho Ngài."),
            "dọn dẹp nhanh": IntentResult(action_name="workflow_preset", parameters={"preset": "clean"}, source="rule_fallback", response_text="Đang tiến hành dọn dẹp và tối ưu hóa hệ thống nhanh cho Ngài."),
            "tối ưu hóa máy tính": IntentResult(action_name="workflow_preset", parameters={"preset": "clean"}, source="rule_fallback", response_text="Đang tiến hành dọn dẹp và tối ưu hóa hệ thống nhanh cho Ngài."),

            # 5. Reminder (Category 5)
            "tạo nhắc nhở": IntentResult(
                action_name="reminder",
                parameters={"message": "nhắc nhở chung"},
                source="rule_fallback",
                response_text="Đã ghi nhận lời nhắc của Ngài.",
            ),
            "đặt báo thức": IntentResult(
                action_name="reminder",
                parameters={"message": "báo thức"},
                source="rule_fallback",
                response_text="Đã ghi nhận lời nhắc của Ngài.",
            ),
            "hẹn giờ": IntentResult(
                action_name="reminder",
                parameters={"message": "hẹn giờ"},
                source="rule_fallback",
                response_text="Đã ghi nhận lời nhắc của Ngài.",
            ),
            "đặt lịch": IntentResult(
                action_name="reminder",
                parameters={"message": "đặt lịch"},
                source="rule_fallback",
                response_text="Đã ghi nhận lời nhắc của Ngài.",
            ),
            "nhắc nhở": IntentResult(
                action_name="reminder",
                parameters={"message": "nhắc nhở chung"},
                source="rule_fallback",
                response_text="Đã ghi nhận lời nhắc của Ngài.",
            ),
            "nhắc tôi": IntentResult(
                action_name="reminder",
                parameters={"message": "nhắc nhở chung"},
                source="rule_fallback",
                response_text="Đã ghi nhận lời nhắc của Ngài.",
            ),
            "reminder": IntentResult(
                action_name="reminder",
                parameters={"message": "nhắc nhở chung"},
                source="rule_fallback",
                response_text="Đã ghi nhận lời nhắc của Ngài.",
            ),
            "báo thức": IntentResult(
                action_name="reminder",
                parameters={"message": "báo thức"},
                source="rule_fallback",
                response_text="Đã ghi nhận lời nhắc của Ngài.",
            ),

            # 6. System Power (Category 6)
            "tắt máy tính": IntentResult(
                action_name="system_power",
                parameters={"action": "shutdown"},
                source="rule_fallback",
                response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận để thực thi nhằm đảm bảo an toàn dữ liệu, thưa Ngài.",
                requires_confirmation=True,
                confirmation_prompt="Ngài có chắc chắn muốn tắt máy không?",
                danger_level="CRITICAL",
            ),
            "tắt nguồn": IntentResult(
                action_name="system_power",
                parameters={"action": "shutdown"},
                source="rule_fallback",
                response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận để thực thi nhằm đảm bảo an toàn dữ liệu, thưa Ngài.",
                requires_confirmation=True,
                confirmation_prompt="Ngài có chắc chắn muốn tắt máy không?",
                danger_level="CRITICAL",
            ),
            "tắt máy": IntentResult(
                action_name="system_power",
                parameters={"action": "shutdown"},
                source="rule_fallback",
                response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận để thực thi nhằm đảm bảo an toàn dữ liệu, thưa Ngài.",
                requires_confirmation=True,
                confirmation_prompt="Ngài có chắc chắn muốn tắt máy không?",
                danger_level="CRITICAL",
            ),
            "shutdown": IntentResult(
                action_name="system_power",
                parameters={"action": "shutdown"},
                source="rule_fallback",
                response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận để thực thi nhằm đảm bảo an toàn dữ liệu, thưa Ngài.",
                requires_confirmation=True,
                confirmation_prompt="Ngài có chắc chắn muốn tắt máy không?",
                danger_level="CRITICAL",
            ),
            "khởi động lại máy": IntentResult(
                action_name="system_power",
                parameters={"action": "restart"},
                source="rule_fallback",
                response_text="Lệnh khởi động lại hệ thống đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.",
                requires_confirmation=True,
                confirmation_prompt="Ngài có chắc chắn muốn khởi động lại máy không?",
                danger_level="CRITICAL",
            ),
            "khởi động lại": IntentResult(
                action_name="system_power",
                parameters={"action": "restart"},
                source="rule_fallback",
                response_text="Lệnh khởi động lại hệ thống đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.",
                requires_confirmation=True,
                confirmation_prompt="Ngài có chắc chắn muốn khởi động lại máy không?",
                danger_level="CRITICAL",
            ),
            "restart": IntentResult(
                action_name="system_power",
                parameters={"action": "restart"},
                source="rule_fallback",
                response_text="Lệnh khởi động lại hệ thống đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.",
                requires_confirmation=True,
                confirmation_prompt="Ngài có chắc chắn muốn khởi động lại máy không?",
                danger_level="CRITICAL",
            ),
            "reboot": IntentResult(
                action_name="system_power",
                parameters={"action": "restart"},
                source="rule_fallback",
                response_text="Lệnh khởi động lại hệ thống đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.",
                requires_confirmation=True,
                confirmation_prompt="Ngài có chắc chắn muốn khởi động lại máy không?",
                danger_level="CRITICAL",
            ),
            "chế độ ngủ": IntentResult(
                action_name="system_power",
                parameters={"action": "sleep"},
                source="rule_fallback",
                response_text="Đang đưa hệ thống vào chế độ ngủ tiết kiệm điện năng, thưa Ngài.",
                requires_confirmation=True,
                confirmation_prompt="Ngài có muốn đưa hệ thống vào chế độ ngủ không?",
                danger_level="MEDIUM",
            ),
            "sleep": IntentResult(
                action_name="system_power",
                parameters={"action": "sleep"},
                source="rule_fallback",
                response_text="Đang đưa hệ thống vào chế độ ngủ tiết kiệm điện năng, thưa Ngài.",
                requires_confirmation=True,
                confirmation_prompt="Ngài có muốn đưa hệ thống vào chế độ ngủ không?",
                danger_level="MEDIUM",
            ),
            "khóa màn hình": IntentResult(
                action_name="system_power",
                parameters={"action": "lock"},
                source="rule_fallback",
                response_text="Đã khóa màn hình máy tính, thưa Ngài.",
                requires_confirmation=False,
                danger_level="LOW",
            ),
            "khóa máy": IntentResult(
                action_name="system_power",
                parameters={"action": "lock"},
                source="rule_fallback",
                response_text="Đã khóa màn hình máy tính, thưa Ngài.",
                requires_confirmation=False,
                danger_level="LOW",
            ),
            "lock screen": IntentResult(
                action_name="system_power",
                parameters={"action": "lock"},
                source="rule_fallback",
                response_text="Đã khóa màn hình máy tính, thưa Ngài.",
                requires_confirmation=False,
                danger_level="LOW",
            ),

            # 7. Stop / Dừng (Category 7) — maps to lock screen as "stop session"
            "dừng lại": IntentResult(
                action_name="system_power",
                parameters={"action": "lock"},
                source="rule_fallback",
                response_text="Đã dừng phiên làm việc và khóa màn hình, thưa Ngài.",
                requires_confirmation=False,
                danger_level="LOW",
            ),
            "dừng": IntentResult(
                action_name="system_power",
                parameters={"action": "lock"},
                source="rule_fallback",
                response_text="Đã dừng phiên làm việc và khóa màn hình, thưa Ngài.",
                requires_confirmation=False,
                danger_level="LOW",
            ),
            "dung lai": IntentResult(  # no-diacritic fallback for STT garbling
                action_name="system_power",
                parameters={"action": "lock"},
                source="rule_fallback",
                response_text="Đã dừng phiên làm việc và khóa màn hình, thưa Ngài.",
                requires_confirmation=False,
                danger_level="LOW",
            ),

            # Abort shutdown / cancel power actions
            "hủy tắt máy": IntentResult(
                action_name="system_power",
                parameters={"action": "abort"},
                source="rule_fallback",
                response_text="Đang hủy lệnh tắt máy tính cho Ngài.",
                requires_confirmation=False,
                danger_level="LOW",
            ),
            "huy tat may": IntentResult(
                action_name="system_power",
                parameters={"action": "abort"},
                source="rule_fallback",
                response_text="Đang hủy lệnh tắt máy tính cho Ngài.",
                requires_confirmation=False,
                danger_level="LOW",
            ),
            "hủy shutdown": IntentResult(
                action_name="system_power",
                parameters={"action": "abort"},
                source="rule_fallback",
                response_text="Đang hủy lệnh tắt máy tính cho Ngài.",
                requires_confirmation=False,
                danger_level="LOW",
            ),
            "hủy khởi động lại": IntentResult(
                action_name="system_power",
                parameters={"action": "abort"},
                source="rule_fallback",
                response_text="Đang hủy lệnh khởi động lại máy tính cho Ngài.",
                requires_confirmation=False,
                danger_level="LOW",
            ),
            "cancel shutdown": IntentResult(
                action_name="system_power",
                parameters={"action": "abort"},
                source="rule_fallback",
                response_text="Canceling scheduled shutdown, Sir.",
                requires_confirmation=False,
                danger_level="LOW",
            ),
            "abort shutdown": IntentResult(
                action_name="system_power",
                parameters={"action": "abort"},
                source="rule_fallback",
                response_text="Canceling scheduled shutdown, Sir.",
                requires_confirmation=False,
                danger_level="LOW",
            ),

            # 8. Settings Open (Category 8)
            "mở cài đặt": IntentResult(
                action_name="app_open",
                parameters={"app_name": "Settings", "app": "ms-settings:"},
                source="rule_fallback",
                response_text="Đang mở cài đặt hệ thống cho Ngài.",
            ),
            "cài đặt": IntentResult(
                action_name="app_open",
                parameters={"app_name": "Settings", "app": "ms-settings:"},
                source="rule_fallback",
                response_text="Đang mở cài đặt hệ thống cho Ngài.",
            ),
            "mở settings": IntentResult(
                action_name="app_open",
                parameters={"app_name": "Settings", "app": "ms-settings:"},
                source="rule_fallback",
                response_text="Đang mở cài đặt hệ thống cho Ngài.",
            ),
            "open settings": IntentResult(
                action_name="app_open",
                parameters={"app_name": "Settings", "app": "ms-settings:"},
                source="rule_fallback",
                response_text="Đang mở cài đặt hệ thống cho Ngài.",
            ),
            "cai dat": IntentResult(  # no-diacritic fallback
                action_name="app_open",
                parameters={"app_name": "Settings", "app": "ms-settings:"},
                source="rule_fallback",
                response_text="Đang mở cài đặt hệ thống cho Ngài.",
            ),

            # 9. Screen Off (Category 9)
            "tắt màn hình": IntentResult(
                action_name="system_brightness",
                parameters={"level": 0},
                source="rule_fallback",
                response_text="Đang tắt màn hình cho Ngài.",
            ),
            "tắt monitor": IntentResult(
                action_name="system_brightness",
                parameters={"level": 0},
                source="rule_fallback",
                response_text="Đang tắt màn hình cho Ngài.",
            ),
            "tắt màn": IntentResult(
                action_name="system_brightness",
                parameters={"level": 0},
                source="rule_fallback",
                response_text="Đang tắt màn hình cho Ngài.",
            ),
            "turn off screen": IntentResult(
                action_name="system_brightness",
                parameters={"level": 0},
                source="rule_fallback",
                response_text="Đang tắt màn hình cho Ngài.",
            ),
            "tat man hinh": IntentResult(  # no-diacritic fallback
                action_name="system_brightness",
                parameters={"level": 0},
                source="rule_fallback",
                response_text="Đang tắt màn hình cho Ngài.",
            ),

            # Workflows
            "quét mạng nội bộ": IntentResult(
                action_name="security_nmap_scan",
                parameters={"target": "192.168.1.0/24"},
                source="rule_fallback",
                response_text="Đang thực hiện quét an ninh mạng nội bộ cho Ngài.",
            ),
            "chuẩn bị môi trường làm việc": IntentResult(
                action_name="workspace_prepare",
                parameters={"recipe": "ai_development"},
                source="rule_fallback",
                response_text="Đang chuẩn bị môi trường làm việc cho Ngài.",
            ),
            "tự phục hồi hệ thống": IntentResult(
                action_name="healing_watchdog_heal",
                parameters={},
                source="rule_fallback",
                response_text="Đang tiến hành tối ưu hóa bộ nhớ và kiểm tra tiến trình hệ thống cho Ngài.",
            ),
            "dọn dẹp ram": IntentResult(
                action_name="healing_watchdog_heal",
                parameters={},
                source="rule_fallback",
                response_text="Đang tiến hành tối ưu hóa bộ nhớ và giải phóng RAM cho Ngài.",
            ),
            "dọn dẹp ram hệ thống": IntentResult(
                action_name="healing_watchdog_heal",
                parameters={},
                source="rule_fallback",
                response_text="Đang tiến hành tối ưu hóa bộ nhớ và kiểm tra tiến trình hệ thống cho Ngài.",
            ),
            "giải phóng ram": IntentResult(
                action_name="healing_watchdog_heal",
                parameters={},
                source="rule_fallback",
                response_text="Đang giải phóng bộ nhớ RAM cho Ngài.",
            ),
            "giai phong ram": IntentResult(
                action_name="healing_watchdog_heal",
                parameters={},
                source="rule_fallback",
                response_text="Đang giải phóng bộ nhớ RAM cho Ngài.",
            ),
            "giải phóng bộ nhớ": IntentResult(
                action_name="healing_watchdog_heal",
                parameters={},
                source="rule_fallback",
                response_text="Đang tiến hành tối ưu hóa bộ nhớ cho Ngài.",
            ),

            # App launchers (static, non-diacritic & standard, supplement regex for edge cases)
            "mo chrome": IntentResult(action_name="app_open", parameters={"app_name": "chrome", "name": "chrome"}, source="rule_fallback", response_text="Đang mở Google Chrome cho Ngài."),
            "mo ung dung chrome": IntentResult(action_name="app_open", parameters={"app_name": "chrome", "name": "chrome"}, source="rule_fallback", response_text="Đang mở Google Chrome cho Ngài."),
            "mo notepad": IntentResult(action_name="app_open", parameters={"app_name": "notepad", "name": "notepad"}, source="rule_fallback", response_text="Đang mở Notepad cho Ngài."),
            "open chrome": IntentResult(action_name="app_open", parameters={"app_name": "chrome", "name": "chrome"}, source="rule_fallback", response_text="Đang mở Google Chrome cho Ngài."),
            "launch notepad": IntentResult(action_name="app_open", parameters={"app_name": "notepad", "name": "notepad"}, source="rule_fallback", response_text="Đang mở Notepad cho Ngài."),
            "mo word": IntentResult(action_name="app_open", parameters={"app_name": "word", "name": "word"}, source="rule_fallback", response_text="Đang mở Microsoft Word cho Ngài."),
            "mo excel": IntentResult(action_name="app_open", parameters={"app_name": "excel", "name": "excel"}, source="rule_fallback", response_text="Đang mở Microsoft Excel cho Ngài."),
            "mo paint": IntentResult(action_name="app_open", parameters={"app_name": "paint", "name": "paint"}, source="rule_fallback", response_text="Đang mở Paint cho Ngài."),
            "open file explorer": IntentResult(action_name="app_open", parameters={"app_name": "explorer"}, source="rule_fallback", response_text="Đang mở File Explorer cho Ngài."),
            "mo calculator": IntentResult(action_name="app_open", parameters={"app_name": "calculator", "name": "calc"}, source="rule_fallback", response_text="Đang mở Máy tính cho Ngài."),
            "mo powerpoint": IntentResult(action_name="app_open", parameters={"app_name": "powerpoint", "name": "powerpoint"}, source="rule_fallback", response_text="Đang mở PowerPoint cho Ngài."),
            "mo cai dat": IntentResult(action_name="app_open", parameters={"app_name": "Settings", "app": "ms-settings:"}, source="rule_fallback", response_text="Đang mở cài đặt hệ thống cho Ngài."),
            "cai dat he thong": IntentResult(action_name="app_open", parameters={"app_name": "Settings", "app": "ms-settings:"}, source="rule_fallback", response_text="Đang mở cài đặt hệ thống cho Ngài."),
            "cài đặt hệ thống": IntentResult(action_name="app_open", parameters={"app_name": "Settings", "app": "ms-settings:"}, source="rule_fallback", response_text="Đang mở cài đặt hệ thống cho Ngài."),
            # H-07 fix: a bare, unqualified single-word "settings" key was
            # removed here for the same reason as the bare "spotify" key
            # above -- word_count==1 matching fires on ANY sentence
            # containing the standalone word "settings" (e.g. "settings
            # nghĩa là gì" incorrectly launched Settings). Every genuine
            # positive alias ("mở settings", "open settings", "mo settings",
            # bare "cài đặt") remains covered by dedicated dict entries and
            # the anchored regex + _make_app_intent()'s canonical-settings
            # branch above.
            "cai dat windows": IntentResult(action_name="app_open", parameters={"app_name": "Settings", "app": "ms-settings:"}, source="rule_fallback", response_text="Đang mở cài đặt hệ thống cho Ngài."),
            "cài đặt windows": IntentResult(action_name="app_open", parameters={"app_name": "Settings", "app": "ms-settings:"}, source="rule_fallback", response_text="Đang mở cài đặt hệ thống cho Ngài."),
            "mo settings": IntentResult(action_name="app_open", parameters={"app_name": "Settings", "app": "ms-settings:"}, source="rule_fallback", response_text="Đang mở cài đặt hệ thống cho Ngài."),
            "bật claude": IntentResult(action_name="web_open", parameters={"target": "claude", "site": "claude"}, source="rule_fallback", response_text="Đang mở Claude AI cho Ngài."),
            "mở claude": IntentResult(action_name="web_open", parameters={"target": "claude", "site": "claude"}, source="rule_fallback", response_text="Đang mở Claude AI cho Ngài."),
            "bật chatgpt": IntentResult(action_name="web_open", parameters={"target": "chatgpt", "site": "chatgpt"}, source="rule_fallback", response_text="Đang mở ChatGPT cho Ngài."),
            "mở chatgpt": IntentResult(action_name="web_open", parameters={"target": "chatgpt", "site": "chatgpt"}, source="rule_fallback", response_text="Đang mở ChatGPT cho Ngài."),
            "bật youtube": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
            "mở youtube": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
            "mở xem youtube": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
            "xem youtube": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
            "mo youtube": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
            "mo xem youtube": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
            "open youtube": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
            "vao youtube": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
            "vào xem youtube": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
            "cho tao vao youtube": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
            "cho toi vao youtube": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
            "cho t vao youtube": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
            "vao youtube di": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
            "bật google": IntentResult(action_name="web_open", parameters={"target": "google", "site": "google"}, source="rule_fallback", response_text="Đang mở Google cho Ngài."),
            "mở google": IntentResult(action_name="web_open", parameters={"target": "google", "site": "google"}, source="rule_fallback", response_text="Đang mở Google cho Ngài."),
            "bật gmail": IntentResult(action_name="web_open", parameters={"target": "gmail", "site": "gmail"}, source="rule_fallback", response_text="Đang mở Gmail cho Ngài."),
            "mở gmail": IntentResult(action_name="web_open", parameters={"target": "gmail", "site": "gmail"}, source="rule_fallback", response_text="Đang mở Gmail cho Ngài."),
            "bật github": IntentResult(action_name="web_open", parameters={"target": "github", "site": "github"}, source="rule_fallback", response_text="Đang mở GitHub cho Ngài."),
            "mở github": IntentResult(action_name="web_open", parameters={"target": "github", "site": "github"}, source="rule_fallback", response_text="Đang mở GitHub cho Ngài."),
            "bật facebook": IntentResult(action_name="web_open", parameters={"target": "facebook", "site": "facebook"}, source="rule_fallback", response_text="Đang mở Facebook cho Ngài."),
            "mở facebook": IntentResult(action_name="web_open", parameters={"target": "facebook", "site": "facebook"}, source="rule_fallback", response_text="Đang mở Facebook cho Ngài."),
            "mo facebook": IntentResult(action_name="web_open", parameters={"target": "facebook", "site": "facebook"}, source="rule_fallback", response_text="Đang mở Facebook cho Ngài."),
            "open facebook": IntentResult(action_name="web_open", parameters={"target": "facebook", "site": "facebook"}, source="rule_fallback", response_text="Đang mở Facebook cho Ngài."),
            "vao facebook": IntentResult(action_name="web_open", parameters={"target": "facebook", "site": "facebook"}, source="rule_fallback", response_text="Đang mở Facebook cho Ngài."),
            "cho tao vao facebook": IntentResult(action_name="web_open", parameters={"target": "facebook", "site": "facebook"}, source="rule_fallback", response_text="Đang mở Facebook cho Ngài."),
            "cho toi vao facebook": IntentResult(action_name="web_open", parameters={"target": "facebook", "site": "facebook"}, source="rule_fallback", response_text="Đang mở Facebook cho Ngài."),
            "cho tao mo facebook": IntentResult(action_name="web_open", parameters={"target": "facebook", "site": "facebook"}, source="rule_fallback", response_text="Đang mở Facebook cho Ngài."),
            "cho tao mo youtube": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
            "cho toi mo youtube": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
            "cho tao mo google": IntentResult(action_name="web_open", parameters={"target": "google", "site": "google"}, source="rule_fallback", response_text="Đang mở Google cho Ngài."),
            "cho toi mo google": IntentResult(action_name="web_open", parameters={"target": "google", "site": "google"}, source="rule_fallback", response_text="Đang mở Google cho Ngài."),
            "open website": IntentResult(action_name="web_open", parameters={"target": "https://www.google.com", "site": "google"}, source="rule_fallback", response_text="Đang mở trình duyệt cho Ngài."),
            "mo trang web": IntentResult(action_name="web_open", parameters={"target": "https://www.google.com", "site": "google"}, source="rule_fallback", response_text="Đang mở trình duyệt cho Ngài."),
            "bật discord": IntentResult(action_name="app_open", parameters={"app_name": "discord"}, source="rule_fallback", response_text="Đang mở Discord cho Ngài."),
            "mở discord": IntentResult(action_name="app_open", parameters={"app_name": "discord"}, source="rule_fallback", response_text="Đang mở Discord cho Ngài."),
            "bật telegram": IntentResult(action_name="app_open", parameters={"app_name": "telegram"}, source="rule_fallback", response_text="Đang mở Telegram cho Ngài."),
            "mở telegram": IntentResult(action_name="app_open", parameters={"app_name": "telegram"}, source="rule_fallback", response_text="Đang mở Telegram cho Ngài."),
            "bật zalo": IntentResult(action_name="app_open", parameters={"app_name": "zalo"}, source="rule_fallback", response_text="Đang mở Zalo cho Ngài."),
            "mở zalo": IntentResult(action_name="app_open", parameters={"app_name": "zalo"}, source="rule_fallback", response_text="Đang mở Zalo cho Ngài."),
            "bật vscode": IntentResult(action_name="app_open", parameters={"app_name": "vscode"}, source="rule_fallback", response_text="Đang mở VS Code cho Ngài."),
            "mở vscode": IntentResult(action_name="app_open", parameters={"app_name": "vscode"}, source="rule_fallback", response_text="Đang mở VS Code cho Ngài."),
            "bật chrome": IntentResult(action_name="app_open", parameters={"app_name": "chrome"}, source="rule_fallback", response_text="Đang mở Google Chrome cho Ngài."),
            # Browser tab control
            "mo tab moi": IntentResult(action_name="new_tab", parameters={}, source="rule_fallback", response_text="Dang mo tab moi, thua Ngai."),
            "tab moi": IntentResult(action_name="new_tab", parameters={}, source="rule_fallback", response_text="Dang mo tab moi, thua Ngai."),
            "open new tab": IntentResult(action_name="new_tab", parameters={}, source="rule_fallback", response_text="Opening new tab."),
            "new tab": IntentResult(action_name="new_tab", parameters={}, source="rule_fallback", response_text="Opening new tab."),
            "mo them tab": IntentResult(action_name="new_tab", parameters={}, source="rule_fallback", response_text="Dang mo tab moi, thua Ngai."),
            "mở chrome": IntentResult(action_name="app_open", parameters={"app_name": "chrome"}, source="rule_fallback", response_text="Đang mở Google Chrome cho Ngài."),
            "bật edge": IntentResult(action_name="app_open", parameters={"app_name": "edge"}, source="rule_fallback", response_text="Đang mở Microsoft Edge cho Ngài."),
            "mở edge": IntentResult(action_name="app_open", parameters={"app_name": "edge"}, source="rule_fallback", response_text="Đang mở Microsoft Edge cho Ngài."),
            "bật word": IntentResult(action_name="app_open", parameters={"app_name": "word"}, source="rule_fallback", response_text="Đang mở Microsoft Word cho Ngài."),
            "mở word": IntentResult(action_name="app_open", parameters={"app_name": "word"}, source="rule_fallback", response_text="Đang mở Microsoft Word cho Ngài."),
            "bật excel": IntentResult(action_name="app_open", parameters={"app_name": "excel"}, source="rule_fallback", response_text="Đang mở Microsoft Excel cho Ngài."),
            "mở excel": IntentResult(action_name="app_open", parameters={"app_name": "excel"}, source="rule_fallback", response_text="Đang mở Microsoft Excel cho Ngài."),
            "bật notepad": IntentResult(action_name="app_open", parameters={"app_name": "notepad"}, source="rule_fallback", response_text="Đang mở Notepad cho Ngài."),
            "mở notepad": IntentResult(action_name="app_open", parameters={"app_name": "notepad"}, source="rule_fallback", response_text="Đang mở Notepad cho Ngài."),
            "bật terminal": IntentResult(action_name="app_open", parameters={"app_name": "terminal"}, source="rule_fallback", response_text="Đang mở Terminal cho Ngài."),
            "mở terminal": IntentResult(action_name="app_open", parameters={"app_name": "terminal"}, source="rule_fallback", response_text="Đang mở Terminal cho Ngài."),
            "bật powershell": IntentResult(action_name="app_open", parameters={"app_name": "powershell"}, source="rule_fallback", response_text="Đang mở PowerShell cho Ngài."),
            "mở powershell": IntentResult(action_name="app_open", parameters={"app_name": "powershell"}, source="rule_fallback", response_text="Đang mở PowerShell cho Ngài."),
            "bật cursor": IntentResult(action_name="app_open", parameters={"app_name": "cursor"}, source="rule_fallback", response_text="Đang mở Cursor AI cho Ngài."),
            "mở cursor": IntentResult(action_name="app_open", parameters={"app_name": "cursor"}, source="rule_fallback", response_text="Đang mở Cursor AI cho Ngài."),
            "mở file explorer": IntentResult(action_name="app_open", parameters={"app_name": "explorer"}, source="rule_fallback", response_text="Đang mở File Explorer cho Ngài."),
            "bật file explorer": IntentResult(action_name="app_open", parameters={"app_name": "explorer"}, source="rule_fallback", response_text="Đang mở File Explorer cho Ngài."),
            "bật task manager": IntentResult(action_name="app_open", parameters={"app_name": "taskmgr"}, source="rule_fallback", response_text="Đang mở Task Manager cho Ngài."),
            "mở task manager": IntentResult(action_name="app_open", parameters={"app_name": "taskmgr"}, source="rule_fallback", response_text="Đang mở Task Manager cho Ngài."),
            "quản lý tác vụ": IntentResult(action_name="app_open", parameters={"app_name": "taskmgr"}, source="rule_fallback", response_text="Đang mở Quản lý tác vụ cho Ngài."),

            # Volume & screen controls
            "tăng âm lượng": IntentResult(action_name="system_volume", parameters={"delta": 10}, source="rule_fallback", response_text="Đang tăng âm lượng cho Ngài."),
            "giảm âm lượng": IntentResult(action_name="system_volume", parameters={"delta": -10}, source="rule_fallback", response_text="Đang giảm âm lượng cho Ngài."),
            "tang am luong": IntentResult(action_name="system_volume", parameters={"delta": 10}, source="rule_fallback", response_text="Đang tăng âm lượng cho Ngài."),
            "giam am luong": IntentResult(action_name="system_volume", parameters={"delta": -10}, source="rule_fallback", response_text="Đang giảm âm lượng cho Ngài."),
            # H-08 final contract correction: a bare "adjust the volume"
            # request with no direction/level is genuinely ambiguous, but
            # remains categorized under the established system_volume P0
            # routing contract (tests/unit/test_router_p0.py,
            # tests/eval/routing_eval_n150.py) rather than unknown_intent --
            # it must NOT silently execute a fake volume change
            # ({"delta": 0} previously implied a real action happened when
            # none did), but it also must not be reclassified out of
            # system_volume. The explicit {"clarify": True} parameter tells
            # _handle_system_volume() to ask a clarification question with
            # ZERO hardware side effects, before ever touching
            # computer_controller -- see its clarify branch.
            "dieu chinh am luong": IntentResult(
                action_name="system_volume",
                parameters={"clarify": True},
                source="rule_fallback",
                response_text=(
                    "Ngài muốn tăng âm lượng, giảm âm lượng, tắt tiếng, bật tiếng, "
                    "hay đặt một mức âm lượng cụ thể? Xin nói rõ hơn, thưa Ngài."
                ),
            ),
            "volume up": IntentResult(action_name="system_volume", parameters={"delta": 10}, source="rule_fallback", response_text="Đang tăng âm lượng cho Ngài."),
            "volume down": IntentResult(action_name="system_volume", parameters={"delta": -10}, source="rule_fallback", response_text="Đang giảm âm lượng cho Ngài."),
            "giảm âm": IntentResult(action_name="system_volume", parameters={"delta": -10}, source="rule_fallback", response_text="Đang giảm âm lượng cho Ngài."),
            "tắt tiếng": IntentResult(action_name="system_volume", parameters={"mute": True}, source="rule_fallback", response_text="Đã tắt tiếng máy tính, thưa Ngài."),
            "tat tieng": IntentResult(action_name="system_volume", parameters={"mute": True}, source="rule_fallback", response_text="Đã tắt tiếng máy tính, thưa Ngài."),
            "mute": IntentResult(action_name="system_volume", parameters={"mute": True}, source="rule_fallback", response_text="Đã tắt tiếng máy tính, thưa Ngài."),
            "bật tiếng": IntentResult(action_name="system_volume", parameters={"mute": False}, source="rule_fallback", response_text="Đã bật tiếng máy tính, thưa Ngài."),
            "bật tắt mic": IntentResult(action_name="toggle_mute", parameters={}, source="rule_fallback", response_text="Đã chuyển đổi trạng thái micro, thưa Ngài."),
            "bat tat mic": IntentResult(action_name="toggle_mute", parameters={}, source="rule_fallback", response_text="Đã chuyển đổi trạng thái micro, thưa Ngài."),
            "tắt mic": IntentResult(action_name="toggle_mute", parameters={"muted": True}, source="rule_fallback", response_text="Đã tắt micro, thưa Ngài."),
            "tat mic": IntentResult(action_name="toggle_mute", parameters={"muted": True}, source="rule_fallback", response_text="Đã tắt micro, thưa Ngài."),
            "bật mic": IntentResult(action_name="toggle_mute", parameters={"muted": False}, source="rule_fallback", response_text="Đã bật micro, thưa Ngài."),
            "bat mic": IntentResult(action_name="toggle_mute", parameters={"muted": False}, source="rule_fallback", response_text="Đã bật micro, thưa Ngài."),
            "mute mic": IntentResult(action_name="toggle_mute", parameters={"muted": True}, source="rule_fallback", response_text="Đã tắt micro, thưa Ngài."),
            "unmute mic": IntentResult(action_name="toggle_mute", parameters={"muted": False}, source="rule_fallback", response_text="Đã bật micro, thưa Ngài."),
            "toggle mic": IntentResult(action_name="toggle_mute", parameters={}, source="rule_fallback", response_text="Đã chuyển đổi trạng thái micro, thưa Ngài."),
            "tăng độ sáng": IntentResult(action_name="system_brightness", parameters={"delta": 10}, source="rule_fallback", response_text="Đang tăng độ sáng màn hình cho Ngài."),
            "giảm độ sáng": IntentResult(action_name="system_brightness", parameters={"delta": -10}, source="rule_fallback", response_text="Đang giảm độ sáng màn hình cho Ngài."),
            "tang do sang": IntentResult(action_name="system_brightness", parameters={"delta": 10}, source="rule_fallback", response_text="Đang tăng độ sáng màn hình cho Ngài."),
            "giam do sang": IntentResult(action_name="system_brightness", parameters={"delta": -10}, source="rule_fallback", response_text="Đang giảm độ sáng màn hình cho Ngài."),
            "brightness up": IntentResult(action_name="system_brightness", parameters={"delta": 10}, source="rule_fallback", response_text="Đang tăng độ sáng màn hình cho Ngài."),
            "brightness down": IntentResult(action_name="system_brightness", parameters={"delta": -10}, source="rule_fallback", response_text="Đang giảm độ sáng màn hình cho Ngài."),
            "tat monitor": IntentResult(action_name="system_brightness", parameters={"level": 0}, source="rule_fallback", response_text="Đang tắt màn hình cho Ngài."),
            "turn off monitor": IntentResult(action_name="system_brightness", parameters={"level": 0}, source="rule_fallback", response_text="Đang tắt màn hình cho Ngài."),
            "tat man": IntentResult(action_name="system_brightness", parameters={"level": 0}, source="rule_fallback", response_text="Đang tắt màn hình cho Ngài."),
            "screen off": IntentResult(action_name="system_brightness", parameters={"level": 0}, source="rule_fallback", response_text="Đang tắt màn hình cho Ngài."),

            # Power & Shutdown (non-diacritic & English)
            "tat may tinh": IntentResult(action_name="system_power", parameters={"action": "shutdown"}, source="rule_fallback", response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.", requires_confirmation=True, confirmation_prompt="Ngài có chắc chắn muốn tắt máy không?", danger_level="CRITICAL"),
            "shutdown may": IntentResult(action_name="system_power", parameters={"action": "shutdown"}, source="rule_fallback", response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.", requires_confirmation=True, confirmation_prompt="Ngài có chắc chắn muốn tắt máy không?", danger_level="CRITICAL"),
            "tat may": IntentResult(action_name="system_power", parameters={"action": "shutdown"}, source="rule_fallback", response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.", requires_confirmation=True, confirmation_prompt="Ngài có chắc chắn muốn tắt máy không?", danger_level="CRITICAL"),
            "tat nguon": IntentResult(action_name="system_power", parameters={"action": "shutdown"}, source="rule_fallback", response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.", requires_confirmation=True, confirmation_prompt="Ngài có chắc chắn muốn tắt máy không?", danger_level="CRITICAL"),
            "shut down": IntentResult(action_name="system_power", parameters={"action": "shutdown"}, source="rule_fallback", response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.", requires_confirmation=True, confirmation_prompt="Ngài có chắc chắn muốn tắt máy không?", danger_level="CRITICAL"),
            "turn off computer": IntentResult(action_name="system_power", parameters={"action": "shutdown"}, source="rule_fallback", response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.", requires_confirmation=True, confirmation_prompt="Ngài có chắc chắn muốn tắt máy không?", danger_level="CRITICAL"),
            "tat may di": IntentResult(action_name="system_power", parameters={"action": "shutdown"}, source="rule_fallback", response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.", requires_confirmation=True, confirmation_prompt="Ngài có chắc chắn muốn tắt máy không?", danger_level="CRITICAL"),
            "tắt": IntentResult(action_name="system_power", parameters={"action": "shutdown"}, source="rule_fallback", response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.", requires_confirmation=True, confirmation_prompt="Ngài có chắc chắn muốn tắt máy không?", danger_level="CRITICAL"),
            "power off": IntentResult(action_name="system_power", parameters={"action": "shutdown"}, source="rule_fallback", response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.", requires_confirmation=True, confirmation_prompt="Ngài có chắc chắn muốn tắt máy không?", danger_level="CRITICAL"),
            "stop": IntentResult(action_name="system_power", parameters={"action": "lock"}, source="rule_fallback", response_text="Đã dừng phiên làm việc và khóa màn hình, thưa Ngài."),
            "thoi": IntentResult(action_name="system_power", parameters={"action": "lock"}, source="rule_fallback", response_text="Đã dừng phiên làm việc và khóa màn hình, thưa Ngài."),
            "huy": IntentResult(action_name="system_power", parameters={"action": "lock"}, source="rule_fallback", response_text="Đã hủy tác vụ hiện tại, thưa Ngài."),
            "cancel": IntentResult(action_name="system_power", parameters={"action": "lock"}, source="rule_fallback", response_text="Đã hủy tác vụ hiện tại, thưa Ngài."),

            # Restart (non-diacritic & English)
            "khoi dong lai may": IntentResult(action_name="system_power", parameters={"action": "restart"}, source="rule_fallback", response_text="Lệnh khởi động lại hệ thống đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.", requires_confirmation=True, confirmation_prompt="Ngài có chắc chắn muốn khởi động lại máy không?", danger_level="CRITICAL"),
            "khoi dong lai": IntentResult(action_name="system_power", parameters={"action": "restart"}, source="rule_fallback", response_text="Lệnh khởi động lại hệ thống đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.", requires_confirmation=True, confirmation_prompt="Ngài có chắc chắn muốn khởi động lại máy không?", danger_level="CRITICAL"),
            "restart may tinh": IntentResult(action_name="system_power", parameters={"action": "restart"}, source="rule_fallback", response_text="Lệnh khởi động lại hệ thống đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.", requires_confirmation=True, confirmation_prompt="Ngài có chắc chắn muốn khởi động lại máy không?", danger_level="CRITICAL"),
            "restart windows": IntentResult(action_name="system_power", parameters={"action": "restart"}, source="rule_fallback", response_text="Lệnh khởi động lại hệ thống đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.", requires_confirmation=True, confirmation_prompt="Ngài có chắc chắn muốn khởi động lại máy không?", danger_level="CRITICAL"),
            "restart may": IntentResult(action_name="system_power", parameters={"action": "restart"}, source="rule_fallback", response_text="Lệnh khởi động lại hệ thống đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.", requires_confirmation=True, confirmation_prompt="Ngài có chắc chắn muốn khởi động lại máy không?", danger_level="CRITICAL"),

            # Weather (non-diacritic & English)
            "thoi tiet hom nay": IntentResult(action_name="shell_exec", parameters={"command": "curl -s wttr.in?format=3", "topic": "weather", "location": "current"}, source="rule_fallback", response_text="Đang kiểm tra thời tiết hôm nay cho Ngài."),
            "thoi tiet ngay mai": IntentResult(action_name="shell_exec", parameters={"command": "curl -s wttr.in?format=3", "topic": "weather", "location": "tomorrow"}, source="rule_fallback", response_text="Đang kiểm tra dự báo thời tiết ngày mai cho Ngài."),
            "du bao thoi tiet": IntentResult(action_name="shell_exec", parameters={"command": "curl -s wttr.in?format=3", "topic": "weather", "location": "current"}, source="rule_fallback", response_text="Đang xem dự báo thời tiết cho Ngài."),
            "troi hom nay": IntentResult(action_name="shell_exec", parameters={"command": "curl -s wttr.in?format=3", "topic": "weather", "location": "current"}, source="rule_fallback", response_text="Đang kiểm tra tình hình thời tiết hôm nay cho Ngài."),
            "weather today": IntentResult(action_name="shell_exec", parameters={"command": "curl -s wttr.in?format=3", "topic": "weather", "location": "current"}, source="rule_fallback", response_text="Đang kiểm tra thời tiết hôm nay cho Ngài."),
            "thoi tiet ha noi": IntentResult(action_name="shell_exec", parameters={"command": "curl -s wttr.in/Hanoi?format=3", "topic": "weather", "location": "Hà Nội"}, source="rule_fallback", response_text="Đang kiểm tra thời tiết tại Hà Nội cho Ngài."),
            "bao nhieu do": IntentResult(action_name="shell_exec", parameters={"command": "curl -s wttr.in?format=3", "topic": "weather", "location": "current"}, source="rule_fallback", response_text="Đang kiểm tra nhiệt độ hiện tại cho Ngài."),
            "weather forecast": IntentResult(action_name="shell_exec", parameters={"command": "curl -s wttr.in?format=3", "topic": "weather", "location": "current"}, source="rule_fallback", response_text="Đang kiểm tra dự báo thời tiết cho Ngài."),

            # Music (non-diacritic & English)
            "mo nhac": IntentResult(action_name="spotify", parameters={"command": "play", "query": ""}, source="rule_fallback", response_text="Đang mở Spotify và phát nhạc cho Ngài."),
            "phat nhac": IntentResult(action_name="spotify", parameters={"command": "play", "query": ""}, source="rule_fallback", response_text="Đang phát nhạc cho Ngài."),
            "play music": IntentResult(action_name="spotify", parameters={"command": "play", "query": ""}, source="rule_fallback", response_text="Đang phát nhạc trên Spotify cho Ngài."),
            "mo spotify": IntentResult(action_name="spotify", parameters={"query": "", "name": "spotify"}, source="rule_fallback", response_text="Đang mở Spotify cho Ngài."),
            "launch spotify": IntentResult(action_name="spotify", parameters={"query": "", "name": "spotify"}, source="rule_fallback", response_text="Đang mở Spotify cho Ngài."),
            "open spotify": IntentResult(action_name="spotify", parameters={"query": "", "name": "spotify"}, source="rule_fallback", response_text="Đang mở Spotify cho Ngài."),
            "play song": IntentResult(action_name="spotify", parameters={"command": "play", "query": ""}, source="rule_fallback", response_text="Đang phát bài hát cho Ngài."),
            "bat nhac len": IntentResult(action_name="spotify", parameters={"command": "play", "query": ""}, source="rule_fallback", response_text="Đang bật nhạc cho Ngài."),

            # System status & Hardware
            "tinh trang he thong": IntentResult(action_name="hardware_status_query", parameters={}, source="rule_fallback", response_text="Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu, CPU và RAM ở mức an toàn, thưa Ngài."),
            "kiem tra he thong": IntentResult(action_name="hardware_status_query", parameters={}, source="rule_fallback", response_text="Đang kiểm tra tình trạng hệ thống cho Ngài."),
            "trang thai may": IntentResult(action_name="hardware_status_query", parameters={}, source="rule_fallback", response_text="Trạng thái hệ thống đang ổn định, thưa Ngài."),
            "system status": IntentResult(action_name="hardware_status_query", parameters={}, source="rule_fallback", response_text="Tình trạng hệ thống đang ổn định, thưa Ngài."),
            "hardware status": IntentResult(action_name="hardware_status_query", parameters={}, source="rule_fallback", response_text="Tình trạng phần cứng hoạt động tốt, thưa Ngài."),
            "xem ram": IntentResult(action_name="hardware_telemetry_check", parameters={"component": "ram"}, source="rule_fallback", response_text="Bộ nhớ RAM đang sử dụng ở mức bình thường, thưa Ngài."),

            # News headlines & Morning briefing
            "tin tuc hom nay": IntentResult(action_name="news_headlines", parameters={"topic": "general"}, source="rule_fallback", response_text="Đang cập nhật tin tức hôm nay cho Ngài."),
            "tin moi nhat": IntentResult(action_name="news_headlines", parameters={"topic": "breaking"}, source="rule_fallback", response_text="Đang tổng hợp các tin mới nhất cho Ngài."),
            "doc tin tuc": IntentResult(action_name="news_headlines", parameters={"topic": "general"}, source="rule_fallback", response_text="Đang mở tin tức cho Ngài."),
            "news today": IntentResult(action_name="news_headlines", parameters={"topic": "general"}, source="rule_fallback", response_text="Đang tổng hợp tin tức hôm nay cho Ngài."),
            "tin tuc": IntentResult(action_name="news_headlines", parameters={"topic": "general"}, source="rule_fallback", response_text="Đang lấy tin tức mới nhất cho Ngài."),
            "latest news": IntentResult(action_name="news_headlines", parameters={"topic": "breaking"}, source="rule_fallback", response_text="Đang cập nhật tin tức mới nhất cho Ngài."),
            "doc bao": IntentResult(action_name="news_headlines", parameters={"topic": "general"}, source="rule_fallback", response_text="Đang mở các đầu báo điện tử cho Ngài."),
            "bao cao buoi sang": IntentResult(action_name="morning_briefing", parameters={}, source="rule_fallback", response_text="Đang tổng hợp báo cáo buổi sáng cho Ngài."),
            "morning briefing": IntentResult(action_name="morning_briefing", parameters={}, source="rule_fallback", response_text="Đang chuẩn bị thông tin buổi sáng cho Ngài."),
            "thong tin buoi sang": IntentResult(action_name="morning_briefing", parameters={}, source="rule_fallback", response_text="Đang chuẩn bị thông tin buổi sáng cho Ngài."),

            # Memory facts & Daily summary
            "nho cho toi": IntentResult(action_name="memory_save_fact", parameters={}, source="rule_fallback", response_text="Đã ghi nhớ thông tin này cho Ngài."),
            "save this": IntentResult(action_name="memory_save_fact", parameters={}, source="rule_fallback", response_text="Đã lưu thông tin vào bộ nhớ dài hạn, thưa Ngài."),
            "tom tat hom nay": IntentResult(action_name="memory_summarize_daily", parameters={}, source="rule_fallback", response_text="Đang tóm tắt hoạt động trong ngày hôm nay cho Ngài."),
            "summarize today": IntentResult(action_name="memory_summarize_daily", parameters={}, source="rule_fallback", response_text="Đang tổng kết các công việc hôm nay cho Ngài."),

            # Memory and facts
            "nhớ rằng": IntentResult(action_name="memory_save_fact", parameters={}, source="rule_fallback", response_text="Đã ghi nhớ thông tin này, thưa Ngài."),
            "tôi tên là": IntentResult(action_name="memory_save_fact", parameters={}, source="rule_fallback", response_text="Đã ghi nhớ tên của Ngài."),

            # Screen capture
            "chụp màn hình": IntentResult(action_name="screen_capture", parameters={}, source="rule_fallback", response_text="Đã chụp ảnh màn hình và lưu vào Desktop cho Ngài."),
            "screenshot": IntentResult(action_name="screen_capture", parameters={}, source="rule_fallback", response_text="Đã chụp ảnh màn hình và lưu vào Desktop cho Ngài."),
            "chup man hinh": IntentResult(action_name="screen_capture", parameters={}, source="rule_fallback", response_text="Đã chụp ảnh màn hình và lưu ra Desktop cho Ngài."),
            "chup anh man hinh": IntentResult(action_name="screen_capture", parameters={}, source="rule_fallback", response_text="Đã chụp ảnh màn hình và lưu ra Desktop cho Ngài."),
            "take screenshot": IntentResult(action_name="screen_capture", parameters={}, source="rule_fallback", response_text="Đã chụp ảnh màn hình và lưu ra Desktop cho Ngài."),
            "chụp ảnh màn hình": IntentResult(action_name="screen_capture", parameters={}, source="rule_fallback", response_text="Đã chụp ảnh màn hình và lưu ra Desktop cho Ngài."),
            "printscreen": IntentResult(action_name="screen_capture", parameters={}, source="rule_fallback", response_text="Đã chụp ảnh màn hình và lưu ra Desktop cho Ngài."),
            "chup anh": IntentResult(action_name="screen_capture", parameters={}, source="rule_fallback", response_text="Đã chụp ảnh màn hình cho Ngài."),

            # Clipboard
            "sao chép": IntentResult(action_name="skill_clipboard", parameters={"action": "copy"}, source="rule_fallback", response_text="Đã sao chép nội dung vào clipboard, thưa Ngài."),
            "dán": IntentResult(action_name="skill_clipboard", parameters={"action": "paste"}, source="rule_fallback", response_text="Đã dán nội dung từ clipboard, thưa Ngài."),

            # Search Web & File search (non-diacritic & English)
            "tim kiem google": IntentResult(action_name="web_open", parameters={"query": "google", "target": "https://www.google.com"}, source="rule_fallback", response_text="Đang tìm kiếm trên Google cho Ngài."),
            "search chrome": IntentResult(action_name="web_open", parameters={"query": "chrome", "target": "https://www.google.com"}, source="rule_fallback", response_text="Đang mở Google Chrome cho Ngài."),
            "tim kiem youtube": IntentResult(action_name="web_open", parameters={"query": "youtube", "target": "https://www.youtube.com"}, source="rule_fallback", response_text="Đang tìm kiếm trên YouTube cho Ngài."),
            "google thoi tiet": IntentResult(action_name="web_open", parameters={"query": "thời tiết", "target": "https://www.google.com/search?q=thời+tiết"}, source="rule_fallback", response_text="Đang tìm kiếm thời tiết trên Google cho Ngài."),
            "search for news": IntentResult(action_name="web_open", parameters={"query": "news", "target": "https://www.google.com/search?q=news"}, source="rule_fallback", response_text="Đang tìm kiếm tin tức trên Google cho Ngài."),
            "tim kiem tren google": IntentResult(action_name="web_open", parameters={"query": "", "target": "https://www.google.com"}, source="rule_fallback", response_text="Đang tìm kiếm trên Google cho Ngài."),
            "tim file word": IntentResult(action_name="file_search", parameters={"action": "search", "query": "word"}, source="rule_fallback", response_text="Đang tìm kiếm file Word cho Ngài."),
            "find file": IntentResult(action_name="file_search", parameters={"action": "search", "query": ""}, source="rule_fallback", response_text="Đang tìm kiếm file cho Ngài."),
            "tim file pdf": IntentResult(action_name="file_search", parameters={"action": "search", "query": "pdf"}, source="rule_fallback", response_text="Đang tìm kiếm file PDF cho Ngài."),

            # Folders (non-diacritic & English)
            "mo thu muc downloads": IntentResult(action_name="folder_open", parameters={"folder": "downloads"}, source="rule_fallback", response_text="Đang mở thư mục Downloads cho Ngài."),
            "open folder downloads": IntentResult(action_name="folder_open", parameters={"folder": "downloads"}, source="rule_fallback", response_text="Đang mở thư mục Downloads cho Ngài."),
            "mo thu muc desktop": IntentResult(action_name="folder_open", parameters={"folder": "desktop"}, source="rule_fallback", response_text="Đang mở thư mục Desktop cho Ngài."),
            "open documents": IntentResult(action_name="folder_open", parameters={"folder": "documents"}, source="rule_fallback", response_text="Đang mở thư mục Documents cho Ngài."),
            "mo thu muc": IntentResult(action_name="folder_open", parameters={"folder": "documents"}, source="rule_fallback", response_text="Đang mở thư mục cho Ngài."),
            "mo folder": IntentResult(action_name="folder_open", parameters={"folder": "documents"}, source="rule_fallback", response_text="Đang mở thư mục cho Ngài."),

            # Project & Workspace Management (Static Rules)
            "mo du an jarvis": IntentResult(action_name="workspace_prepare", parameters={"action": "open", "project": "jarvis", "recipe": "jarvis"}, source="rule_fallback", response_text="Đang mở dự án jarvis cho Ngài."),
            "open project jarvis": IntentResult(action_name="workspace_prepare", parameters={"action": "open", "project": "jarvis", "recipe": "jarvis"}, source="rule_fallback", response_text="Đang mở dự án jarvis cho Ngài."),
            "switch sang project core": IntentResult(action_name="workspace_prepare", parameters={"action": "open", "project": "core", "recipe": "core"}, source="rule_fallback", response_text="Đang chuyển sang dự án core cho Ngài."),
            "chuyen sang workspace dev": IntentResult(action_name="workspace_prepare", parameters={"action": "open", "project": "dev", "recipe": "dev"}, source="rule_fallback", response_text="Đang chuyển sang workspace dev cho Ngài."),
            "tao project moi": IntentResult(action_name="project_create", parameters={"action": "create", "name": "", "project_name": ""}, source="rule_fallback", response_text="Đang khởi tạo dự án mới cho Ngài."),
            "create project backend": IntentResult(action_name="project_create", parameters={"action": "create", "name": "backend", "project_name": "backend"}, source="rule_fallback", response_text="Đang khởi tạo dự án backend cho Ngài."),
            "mở dự án": IntentResult(action_name="workspace_prepare", parameters={"action": "open", "project": "", "recipe": "ai_development"}, source="rule_fallback", response_text="Đang chuẩn bị môi trường làm việc cho Ngài."),
            "chuyển workspace": IntentResult(action_name="workspace_prepare", parameters={"action": "open", "project": "", "recipe": "ai_development"}, source="rule_fallback", response_text="Đang chuẩn bị môi trường làm việc cho Ngài."),
            "chuyển dự án": IntentResult(action_name="workspace_prepare", parameters={"action": "open", "project": "", "recipe": "ai_development"}, source="rule_fallback", response_text="Đang chuẩn bị môi trường làm việc cho Ngài."),
            "tạo workspace mới": IntentResult(action_name="project_create", parameters={"action": "create", "name": "", "project_name": ""}, source="rule_fallback", response_text="Đang khởi tạo dự án mới cho Ngài."),
            "tạo dự án mới": IntentResult(action_name="project_create", parameters={"action": "create", "name": "", "project_name": ""}, source="rule_fallback", response_text="Đang khởi tạo dự án mới cho Ngài."),
            "tạo project": IntentResult(action_name="project_create", parameters={"action": "create", "name": "", "project_name": ""}, source="rule_fallback", response_text="Đang khởi tạo dự án mới cho Ngài."),
            "tạo dự án": IntentResult(action_name="project_create", parameters={"action": "create", "name": "", "project_name": ""}, source="rule_fallback", response_text="Đang khởi tạo dự án mới cho Ngài."),
            "tạo workspace": IntentResult(action_name="project_create", parameters={"action": "create", "name": "", "project_name": ""}, source="rule_fallback", response_text="Đang khởi tạo dự án mới cho Ngài."),
            "liệt kê dự án": IntentResult(action_name="project_list", parameters={"action": "list"}, source="rule_fallback", response_text="Đang liệt kê danh sách các dự án cho Ngài."),
            "liệt kê project": IntentResult(action_name="project_list", parameters={"action": "list"}, source="rule_fallback", response_text="Đang liệt kê danh sách các dự án cho Ngài."),
            "liet ke project": IntentResult(action_name="project_list", parameters={"action": "list"}, source="rule_fallback", response_text="Đang liệt kê danh sách các dự án cho Ngài."),
            "liệt kê workspace": IntentResult(action_name="project_list", parameters={"action": "list"}, source="rule_fallback", response_text="Đang liệt kê danh sách các dự án cho Ngài."),
            "show projects": IntentResult(action_name="project_list", parameters={"action": "list"}, source="rule_fallback", response_text="Đang liệt kê danh sách các dự án cho Ngài."),
            "các project đang có": IntentResult(action_name="project_list", parameters={"action": "list"}, source="rule_fallback", response_text="Đang liệt kê danh sách các dự án cho Ngài."),
            "các dự án đang có": IntentResult(action_name="project_list", parameters={"action": "list"}, source="rule_fallback", response_text="Đang liệt kê danh sách các dự án cho Ngài."),
            "danh sách dự án": IntentResult(action_name="project_list", parameters={"action": "list"}, source="rule_fallback", response_text="Đang liệt kê danh sách các dự án cho Ngài."),
            "danh sách project": IntentResult(action_name="project_list", parameters={"action": "list"}, source="rule_fallback", response_text="Đang liệt kê danh sách các dự án cho Ngài."),
            "danh sách workspace": IntentResult(action_name="project_list", parameters={"action": "list"}, source="rule_fallback", response_text="Đang liệt kê danh sách các dự án cho Ngài."),
            "list projects": IntentResult(action_name="project_list", parameters={"action": "list"}, source="rule_fallback", response_text="Đang liệt kê danh sách các dự án cho Ngài."),
            "git status dự án": IntentResult(action_name="skill_git_assistant", parameters={"action": "status", "project": "", "repo_path": ""}, source="rule_fallback", response_text="Đang kiểm tra trạng thái Git cho Ngài."),
            "commit dự án": IntentResult(action_name="skill_git_assistant", parameters={"action": "commit", "project": "", "repo_path": ""}, source="rule_fallback", response_text="Đang commit các thay đổi dự án cho Ngài."),
            "push project": IntentResult(action_name="skill_git_assistant", parameters={"action": "push", "project": "", "repo_path": ""}, source="rule_fallback", response_text="Đang đẩy các thay đổi lên Git repository cho Ngài."),
            "git commit dự án": IntentResult(action_name="skill_git_assistant", parameters={"action": "commit", "project": "", "repo_path": ""}, source="rule_fallback", response_text="Đang commit các thay đổi dự án cho Ngài."),
            "git push project": IntentResult(action_name="skill_git_assistant", parameters={"action": "push", "project": "", "repo_path": ""}, source="rule_fallback", response_text="Đang đẩy các thay đổi lên Git repository cho Ngài."),
            "git status": IntentResult(action_name="skill_git_assistant", parameters={"action": "status", "project": "", "repo_path": ""}, source="rule_fallback", response_text="Đang kiểm tra trạng thái Git cho Ngài."),
            "git commit": IntentResult(action_name="skill_git_assistant", parameters={"action": "commit", "project": "", "repo_path": ""}, source="rule_fallback", response_text="Đang commit các thay đổi dự án cho Ngài."),
            "git push": IntentResult(action_name="skill_git_assistant", parameters={"action": "push", "project": "", "repo_path": ""}, source="rule_fallback", response_text="Đang đẩy các thay đổi lên Git repository cho Ngài."),

            # Phonetic drift aliases for Whisper mishearings (v4.8.1 STT robustness)
            # system_power
            "tắc máy": IntentResult(
                action_name="system_power",
                parameters={"action": "shutdown", "command": "shutdown"},
                source="rule_fallback",
                response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.",
                requires_confirmation=True,
                confirmation_prompt="Ngài có chắc chắn muốn tắt máy không?",
                danger_level="CRITICAL",
            ),
            "tập máy tính": IntentResult(
                action_name="system_power",
                parameters={"action": "shutdown", "command": "shutdown"},
                source="rule_fallback",
                response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.",
                requires_confirmation=True,
                confirmation_prompt="Ngài có chắc chắn muốn tắt máy không?",
                danger_level="CRITICAL",
            ),
            "sắt đau má": IntentResult(
                action_name="system_power",
                parameters={"action": "shutdown", "command": "shutdown"},
                source="rule_fallback",
                response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.",
                requires_confirmation=True,
                confirmation_prompt="Ngài có chắc chắn muốn tắt máy không?",
                danger_level="CRITICAL",
            ),

            # app_open
            "cái đặt": IntentResult(
                action_name="app_open",
                parameters={"app_name": "settings", "app": "ms-settings:", "name": "settings"},
                source="rule_fallback",
                response_text="Đang mở cài đặt hệ thống cho Ngài.",
            ),
            "má kẻ đặt": IntentResult(
                action_name="app_open",
                parameters={"app_name": "settings", "app": "ms-settings:", "name": "settings"},
                source="rule_fallback",
                response_text="Đang mở cài đặt hệ thống cho Ngài.",
            ),
            "open sentence": IntentResult(
                action_name="app_open",
                parameters={"app_name": "settings", "app": "ms-settings:", "name": "settings"},
                source="rule_fallback",
                response_text="Đang mở cài đặt hệ thống cho Ngài.",
            ),
            "open sente": IntentResult(
                action_name="app_open",
                parameters={"app_name": "settings", "app": "ms-settings:", "name": "settings"},
                source="rule_fallback",
                response_text="Đang mở cài đặt hệ thống cho Ngài.",
            ),

            # reminder
            "đặt time": IntentResult(
                action_name="reminder",
                parameters={"message": "hẹn giờ"},
                source="rule_fallback",
                response_text="Đã ghi nhận lời nhắc của Ngài.",
            ),
            "đặc nhắc": IntentResult(
                action_name="reminder",
                parameters={"message": "nhắc nhở"},
                source="rule_fallback",
                response_text="Đã ghi nhận lời nhắc của Ngài.",
            ),

            # system_volume
            "tắc tính": IntentResult(
                action_name="system_volume",
                parameters={"action": "mute", "mute": True},
                source="rule_fallback",
                response_text="Đã tắt tiếng máy tính, thưa Ngài.",
            ),
            "tắt tính": IntentResult(
                action_name="system_volume",
                parameters={"action": "mute", "mute": True},
                source="rule_fallback",
                response_text="Đã tắt tiếng máy tính, thưa Ngài.",
            ),

            # memory_save_fact
            "ghi chú": IntentResult(
                action_name="memory_save_fact",
                parameters={},
                source="rule_fallback",
                response_text="Đã ghi nhận ghi chú cho Ngài.",
            ),
            "ghi chu": IntentResult(
                action_name="memory_save_fact",
                parameters={},
                source="rule_fallback",
                response_text="Đã ghi nhận ghi chú cho Ngài.",
            ),
            "tạo ghi chú mới": IntentResult(
                action_name="memory_save_fact",
                parameters={},
                source="rule_fallback",
                response_text="Đã ghi nhận ghi chú mới cho Ngài.",
            ),
            "tao ghi chu moi": IntentResult(
                action_name="memory_save_fact",
                parameters={},
                source="rule_fallback",
                response_text="Đã ghi nhận ghi chú mới cho Ngài.",
            ),
    }
