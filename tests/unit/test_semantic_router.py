"""
tests/unit/test_semantic_router.py
==================================
Comprehensive Unit & Integration Test Suite for Local Semantic Router & Typed Slot-Filling.
Verifies:
  1. Volume & Audio Slot Extraction (set absolute, relative +/- delta, mute/unmute).
  2. Display & Screen Brightness Slot Extraction (set absolute, relative +/- delta, query).
  3. Smart Home / Home Assistant Slot Extraction (domain, service, canonical entity_id, area mapping, AC temperature).
  4. Media & Music Controls (play, pause, next, song search on Spotify & YouTube).
  5. Windows & Tab Controls (minimize all, close tab, new tab, page refresh, scroll up/down).
  6. Countdown Timers & Reminders (duration in seconds/minutes/hours, contextual label/message).
  7. Web Search Slot Extraction (query cleaning, Google search).
  8. Conversational Prefix Stripping ("jarvis ơi", "này jarvis", "làm ơn").
  9. Full LLMIntentRouter Integration (<1ms fast path routing without LLM invocation).
"""
import pytest
from jarvis.llm.semantic_router import (
    LocalSemanticRouter,
    normalize_vietnamese_text,
    parse_vietnamese_number,
    parse_duration_seconds,
)
from jarvis.llm.router import LLMIntentRouter
from jarvis.llm.client import LLMClient


@pytest.fixture
def semantic_router() -> LocalSemanticRouter:
    return LocalSemanticRouter()


@pytest.fixture
def intent_router() -> LLMIntentRouter:
    # LLMClient is None to guarantee zero network/LLM calls are made
    return LLMIntentRouter(llm_client=None)


# ==============================================================================
# 1. Number & Duration Parser Tests
# ==============================================================================

def test_parse_vietnamese_number():
    assert parse_vietnamese_number("80") == 80
    assert parse_vietnamese_number("50%") == 50
    assert parse_vietnamese_number("hai mươi") == 20
    assert parse_vietnamese_number("năm mươi") == 50
    assert parse_vietnamese_number("mười lăm") == 15
    assert parse_vietnamese_number("một trăm") == 100
    assert parse_vietnamese_number("một nửa") == 50
    assert parse_vietnamese_number("tối đa") == 100
    assert parse_vietnamese_number("tối thiểu") == 0


def test_parse_duration_seconds():
    # Minutes
    sec, lbl = parse_duration_seconds("15 phút luộc gà")
    assert sec == 900
    assert lbl == "luộc gà"

    # Half hour
    sec2, lbl2 = parse_duration_seconds("nửa tiếng nữa đi ngủ")
    assert sec2 == 1800

    # Hours
    sec3, lbl3 = parse_duration_seconds("2 giờ xem phim")
    assert sec3 == 7200
    assert lbl3 == "xem phim"

    # Seconds
    sec4, lbl4 = parse_duration_seconds("30 giây")
    assert sec4 == 30


# ==============================================================================
# 2. Volume & Audio Slot Matching
# ==============================================================================

def test_volume_slot_matching(semantic_router: LocalSemanticRouter):
    # Absolute set
    res = semantic_router.match("cho âm lượng 80%")
    assert res is not None
    assert res.action_name == "system_volume"
    assert res.parameters == {"level": 80}

    res2 = semantic_router.match("đặt âm lượng năm mươi phần trăm")
    assert res2 is not None
    assert res2.action_name == "system_volume"
    assert res2.parameters == {"level": 50}

    # Relative increase
    res3 = semantic_router.match("vặn to lên một chút")
    assert res3 is not None
    assert res3.action_name == "system_volume"
    assert res3.parameters == {"delta": 5}

    res4 = semantic_router.match("tăng âm lượng thêm 20%")
    assert res4 is not None
    assert res4.action_name == "system_volume"
    assert res4.parameters == {"delta": 20}

    # Relative decrease
    res5 = semantic_router.match("cho nhỏ tiếng đi 15")
    assert res5 is not None
    assert res5.action_name == "system_volume"
    assert res5.parameters == {"delta": -15}

    # Mute / Unmute
    res6 = semantic_router.match("tắt tiếng đi")
    assert res6 is not None
    assert res6.action_name == "system_volume"
    assert res6.parameters == {"mute": True}

    res7 = semantic_router.match("bật loa lại")
    assert res7 is not None
    assert res7.action_name == "system_volume"
    assert res7.parameters == {"mute": False}


# ==============================================================================
# 3. Display Brightness Slot Matching
# ==============================================================================

def test_brightness_slot_matching(semantic_router: LocalSemanticRouter):
    # Absolute set
    res = semantic_router.match("chỉnh độ sáng 70%")
    assert res is not None
    assert res.action_name == "system_brightness"
    assert res.parameters == {"level": 70}

    # Relative delta
    res2 = semantic_router.match("tăng độ sáng màn hình lên 20%")
    assert res2 is not None
    assert res2.action_name == "system_brightness"
    assert res2.parameters == {"delta": 20}

    res3 = semantic_router.match("cho màn hình tối bớt đi 10")
    assert res3 is not None
    assert res3.action_name == "system_brightness"
    assert res3.parameters == {"delta": -10}

    # Query
    res4 = semantic_router.match("độ sáng màn hình hiện tại bao nhiêu")
    assert res4 is not None
    assert res4.action_name == "system_brightness"
    assert res4.parameters == {"query": True}


# ==============================================================================
# 4. Smart Home / Home Assistant Slot Matching
# ==============================================================================

def test_smart_home_slot_matching(semantic_router: LocalSemanticRouter):
    # Lights
    res = semantic_router.match("bật đèn phòng khách")
    assert res is not None
    assert res.action_name == "home_assistant_call"
    assert res.parameters == {"domain": "light", "service": "turn_on", "entity_id": "light.living_room"}

    res2 = semantic_router.match("tắt bóng đèn phòng ngủ")
    assert res2 is not None
    assert res2.action_name == "home_assistant_call"
    assert res2.parameters == {"domain": "light", "service": "turn_off", "entity_id": "light.bedroom"}

    res3 = semantic_router.match("bật đèn bàn làm việc")
    assert res3 is not None
    assert res3.action_name == "home_assistant_call"
    assert res3.parameters == {"domain": "light", "service": "turn_on", "entity_id": "light.desk"}

    # Fans
    res4 = semantic_router.match("tắt quạt phòng khách")
    assert res4 is not None
    assert res4.action_name == "home_assistant_call"
    assert res4.parameters == {"domain": "fan", "service": "turn_off", "entity_id": "fan.living_room"}

    res5 = semantic_router.match("bật quạt trần")
    assert res5 is not None
    assert res5.action_name == "home_assistant_call"
    assert res5.parameters == {"domain": "fan", "service": "turn_on", "entity_id": "fan.ceiling"}

    # Climate / AC temperature
    res6 = semantic_router.match("chỉnh điều hòa lên 25 độ")
    assert res6 is not None
    assert res6.action_name == "home_assistant_call"
    assert res6.parameters == {
        "domain": "climate",
        "service": "set_temperature",
        "entity_id": "climate.ac_unit",
        "temperature": 25.0,
    }

    # Switch / Water heater
    res7 = semantic_router.match("bật bình nóng lạnh")
    assert res7 is not None
    assert res7.action_name == "home_assistant_call"
    assert res7.parameters == {"domain": "switch", "service": "turn_on", "entity_id": "switch.water_heater"}


# ==============================================================================
# 5. Media & Music Slot Matching
# ==============================================================================

def test_media_slot_matching(semantic_router: LocalSemanticRouter):
    # Controls
    res = semantic_router.match("tạm dừng nhạc")
    assert res is not None
    assert res.action_name == "spotify"
    assert res.parameters == {"command": "pause"}

    res2 = semantic_router.match("chuyển bài tiếp theo")
    assert res2 is not None
    assert res2.action_name == "spotify"
    assert res2.parameters == {"command": "next"}

    # Song search
    res3 = semantic_router.match("phát bài Cắt Đôi Nỗi Sầu trên spotify")
    assert res3 is not None
    assert res3.action_name == "spotify"
    assert res3.parameters == {"query": "Cắt Đôi Nỗi Sầu"}

    # YouTube video search
    res4 = semantic_router.match("mở youtube tìm kiếm nhạc thiền")
    assert res4 is not None
    assert res4.action_name == "web_open"
    assert res4.parameters["site"] == "youtube"
    assert "nhạc thiền" in res4.parameters["query"]


# ==============================================================================
# 6. Window & Tab Management Slot Matching
# ==============================================================================

def test_window_tab_slot_matching(semantic_router: LocalSemanticRouter):
    assert semantic_router.match("thu nhỏ tất cả cửa sổ").action_name == "window_minimize_all"
    assert semantic_router.match("mở tab mới").action_name == "new_tab"
    assert semantic_router.match("đóng tab hiện tại").action_name == "close_tab"
    assert semantic_router.match("tải lại trang").action_name == "page_refresh"
    assert semantic_router.match("cuộn trang xuống").action_name == "page_scroll"
    assert semantic_router.match("cuộn trang xuống").parameters == {"direction": "down"}
    assert semantic_router.match("cuộn lên trên").parameters == {"direction": "up"}


# ==============================================================================
# 7. Timers, Reminders, and Web Search
# ==============================================================================

def test_timers_reminders_and_search(semantic_router: LocalSemanticRouter):
    # Timer
    res = semantic_router.match("hẹn giờ 10 phút nấu mì")
    assert res is not None
    assert res.action_name == "timer_set"
    assert res.parameters == {"duration": 600, "label": "nấu mì"}

    # Reminder
    res2 = semantic_router.match("nhắc tôi sau 20 phút nữa uống thuốc")
    assert res2 is not None
    assert res2.action_name == "reminder_set"
    assert res2.parameters == {"duration": 1200, "message": "uống thuốc"}

    # Search
    res3 = semantic_router.match("tìm kiếm giá vàng hôm nay trên google")
    assert res3 is not None
    assert res3.action_name == "web_open"
    assert "giá vàng hôm nay" in res3.parameters["query"]
    assert "google.com/search" in res3.parameters["target"]


# ==============================================================================
# 8. LLMIntentRouter Integration Verification
# ==============================================================================

def test_intent_router_semantic_slot_integration(intent_router: LLMIntentRouter):
    # Conversational phrasing that previously missed static regex
    res = intent_router.parse_intent("jarvis ơi cho âm lượng 80%")
    assert res.action_name == "system_volume"
    assert res.parameters == {"level": 80}
    assert res.source == "rule_fallback"

    # Smart home device in area not covered by legacy regex
    res2 = intent_router.parse_intent("này jarvis tắt điện phòng tắm giúp mình")
    assert res2.action_name == "home_assistant_call"
    assert res2.parameters["domain"] == "light"
    assert res2.parameters["service"] == "turn_off"
    assert res2.parameters["entity_id"] == "light.bathroom"
    assert res2.source == "rule_fallback"

    # Natural AC temperature phrasing without rigid 'đặt/chỉnh' verb
    res3 = intent_router.parse_intent("cho máy lạnh phòng khách 26 độ")
    assert res3.action_name == "home_assistant_call"
    assert res3.parameters["domain"] == "climate"
    assert res3.parameters["service"] == "set_temperature"
    assert res3.parameters["temperature"] == 26.0
    assert res3.source == "rule_fallback"

    # Page refresh action (which legacy router completely lacked)
    res4 = intent_router.parse_intent("tải lại trang web này")
    assert res4.action_name == "page_refresh"
    assert res4.source == "rule_fallback"
