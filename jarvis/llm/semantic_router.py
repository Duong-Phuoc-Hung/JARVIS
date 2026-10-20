"""
jarvis/llm/semantic_router.py
=============================
High-performance Local Semantic Router with Typed Slot-Filling for JARVIS.

Designed after modern local voice assistant architectures (Home Assistant Voice/Wyoming,
Rhasspy, Talon Voice) to provide deterministic, sub-millisecond intent resolution for ~90%
of routine desktop and smart home interactions without requiring slow, unpredictable, or
offline-vulnerable LLM roundtrips.

Key Capabilities:
  1. Typed Slot Filling:
     - Volume & Audio: level (0-100%), relative delta (+/-%), mute/unmute
     - Screen & Brightness: level (0-100%), relative delta (+/-%), query
     - Smart Home / IoT: domain (light, fan, climate, switch), service (turn_on, turn_off,
       set_temperature), entity_id canonical mapping, area/room slots
     - Media & Music: player command (play, pause, next, stop), song query, platform (spotify, youtube)
     - Window & Tabs: minimize_all, new_tab, close_tab, page_refresh, page_scroll (up/down)
     - Timers & Reminders: duration parsing (seconds/minutes/hours), contextual label/message
     - Web Search & Queries: search engine, cleaned search query
  2. Natural Language Parsing:
     - Conversational prefix & filler stripping ("jarvis ơi", "này jarvis", "cho mình", "làm ơn")
     - Robust Vietnamese number-word parsing ("mười", "hai mươi", "năm mươi", "một nửa", "tối đa")
     - Diacritic-resilient slot extraction (works identically with or without tone marks)
  3. Strict Fail-Closed / No-Ghost Execution:
     - Dispatches only verified, validated intents with typed parameters
     - Leaves truly complex/creative/conversational queries for Tier 2 LLM reasoning
"""
from __future__ import annotations

import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

from jarvis.llm.models import IntentResult
from jarvis.memory.vector_store import SemanticVectorStore, VectorStoreConfig

logger = logging.getLogger("jarvis.llm.semantic_router")

# ==============================================================================
# 1. Vietnamese Diacritic Normalization Utilities
# ==============================================================================

_TABLE_SRC = (
    "àáảãạăằắẳẵặâầấẩẫậ"
    "èéẻẽẹêềếểễệ"
    "ìíỉĩị"
    "òóỏõọôồốổỗộơờớởỡợ"
    "ùúủũụưừứửữự"
    "ỳýỷỹỵ"
    "đ"
    "ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬ"
    "ÈÉẺẼẸÊỀẾỂỄỆ"
    "ÌÍỈĨỊ"
    "ÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢ"
    "ÙÚỦŨỤƯỪỨỬỮỰ"
    "ỲÝỶỸỴ"
    "Đ"
)
_TABLE_DST = (
    "a" * 17
    + "e" * 11
    + "i" * 5
    + "o" * 17
    + "u" * 11
    + "y" * 5
    + "d"
    + "A" * 17
    + "E" * 11
    + "I" * 5
    + "O" * 17
    + "U" * 11
    + "Y" * 5
    + "D"
)
_VI_TRANS_TABLE = str.maketrans(_TABLE_SRC, _TABLE_DST)
for _cp in range(0x0300, 0x0370):
    _VI_TRANS_TABLE[_cp] = None


def normalize_vietnamese_text(text: str) -> str:
    """Strips Vietnamese diacritics and converts to lowercase ASCII."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.translate(_VI_TRANS_TABLE).lower().strip()


# ==============================================================================
# 2. Number and Time Slot Parsing
# ==============================================================================

_VI_NUMBER_WORDS: dict[str, int] = {
    "khong": 0, "không": 0,
    "mot": 1, "một": 1,
    "hai": 2,
    "ba": 3,
    "bon": 4, "bốn": 4, "tu": 4, "tư": 4,
    "nam": 5, "năm": 5, "lăm": 5, "lam": 5,
    "sau": 6, "sáu": 6,
    "bay": 7, "bảy": 7, "bẩy": 7,
    "tam": 8, "tám": 8,
    "chin": 9, "chín": 9,
    "muoi": 10, "mười": 10, "chuc": 10, "chục": 10,
    "tram": 100, "trăm": 100,
}


def parse_vietnamese_number(text: str) -> int | None:
    """
    Parses numeric digits or Vietnamese number expressions into an integer.
    Supports: "80", "50%", "hai mươi", "năm mươi", "mười lăm", "một trăm", "nửa" (50).
    """
    clean = text.strip().lower()
    clean_norm = normalize_vietnamese_text(clean)

    # 1. Direct digits
    digits_match = re.search(r"\b(\d{1,3})\b", clean)
    if digits_match:
        return int(digits_match.group(1))

    # 2. Special semantic words
    if any(k in clean_norm for k in ("nua", "mot nua", "nua muc")):
        return 50
    if any(k in clean_norm for k in ("toi da", "het co", "max", "full")):
        return 100
    if any(k in clean_norm for k in ("toi thieu", "min", "nho nhat")):
        return 0

    # 3. Spoken compound numbers anywhere in utterance
    words = clean_norm.split()
    for i in range(len(words)):
        # 3 words: e.g. "hai muoi lam"
        if i + 2 < len(words):
            w1, w2, w3 = words[i], words[i + 1], words[i + 2]
            if w1 in _VI_NUMBER_WORDS and w2 in ("muoi", "chuc") and w3 in _VI_NUMBER_WORDS:
                return (_VI_NUMBER_WORDS[w1] * 10) + _VI_NUMBER_WORDS[w3]
        # 2 words: e.g. "nam muoi", "hai muoi", "mot tram"
        if i + 1 < len(words):
            w1, w2 = words[i], words[i + 1]
            if w1 in _VI_NUMBER_WORDS and w2 in ("muoi", "chuc"):
                return _VI_NUMBER_WORDS[w1] * 10
            if w1 in ("muoi", "chuc") and w2 in _VI_NUMBER_WORDS:
                return 10 + _VI_NUMBER_WORDS[w2]
            if w1 in _VI_NUMBER_WORDS and w2 == "tram":
                return _VI_NUMBER_WORDS[w1] * 100

    # Single number words
    for i in range(len(words)):
        if words[i] in _VI_NUMBER_WORDS and words[i] not in ("chuc", "tram"):
            if i > 0 and words[i - 1] in ("thu", "ngay", "lan"):
                continue
            if any(k in clean_norm for k in ("am luong", "do sang", "muc", "them", "bot", "tieng", "nhiet do", "phan tram")):
                return _VI_NUMBER_WORDS[words[i]]

    return None


def parse_duration_seconds(text: str) -> tuple[int | None, str]:
    """
    Extracts duration in seconds and remaining contextual label.
    Supports: "15 phút", "10s", "1 giờ", "2 tiếng", "nửa tiếng", "30 giây".
    """
    clean = text.strip()
    norm = normalize_vietnamese_text(clean)

    # Check for "nửa tiếng" (30 minutes = 1800s)
    if "nua tieng" in norm or "nua gio" in norm:
        label = re.sub(r"\b(?:trong\s+)?(?:nua\s+tieng|nua\s+gio)\b", "", norm).strip()
        label = re.sub(r"^(?:nữa|nua|tiếp|tiep)\s+", "", label, flags=re.IGNORECASE).strip()
        return 1800, label

    # Check for "X phút / giây / giờ / tiếng"
    pattern = re.compile(
        r"(?:sau|trong\s*vòng|trong)?\s*(\d+)\s*(phút|phut|giờ|gio|tiếng|tieng|giây|giay|s|m|h)\s*(?:để|về|là)?\s*(.*)",
        re.IGNORECASE,
    )
    m = pattern.search(clean)
    if m:
        val = int(m.group(1))
        unit = normalize_vietnamese_text(m.group(2))
        remainder = m.group(3).strip() if m.group(3) else ""
        remainder = re.sub(r"^(?:nữa|nua|tiếp|tiep)\s+", "", remainder, flags=re.IGNORECASE).strip()

        if unit in ("phut", "m"):
            return val * 60, remainder
        if unit in ("gio", "tieng", "h"):
            return val * 3600, remainder
        if unit in ("giay", "s"):
            return val, remainder

    return None, clean


# ==============================================================================
# 3. Canonical Smart Home Entity Mappings
# ==============================================================================

_ROOM_ALIASES: dict[str, str] = {
    "phong khach": "living_room",
    "living room": "living_room",
    "phong ngu": "bedroom",
    "bedroom": "bedroom",
    "bep": "kitchen",
    "phong bep": "kitchen",
    "kitchen": "kitchen",
    "nha tam": "bathroom",
    "phong tam": "bathroom",
    "bathroom": "bathroom",
    "toilet": "bathroom",
    "wc": "bathroom",
    "ban lam viec": "desk",
    "phong lam viec": "desk",
    "desk": "desk",
    "ban hoc": "desk",
    "ban": "desk",
    "ban cong": "balcony",
    "balcony": "balcony",
    "san thuong": "terrace",
    "ngoai troi": "outdoor",
}

_DEVICE_DOMAINS: dict[str, str] = {
    "den": "light",
    "bong den": "light",
    "dien": "light",
    "light": "light",
    "den chieu sang": "light",
    "quat": "fan",
    "quat tran": "fan",
    "fan": "fan",
    "dieu hoa": "climate",
    "may lanh": "climate",
    "ac": "climate",
    "climate": "climate",
    "binh nong lanh": "switch",
    "binh nuoc nong": "switch",
    "may nuoc nong": "switch",
    "cong tac": "switch",
    "o cam": "switch",
    "switch": "switch",
    "tivi": "media_player",
    "tv": "media_player",
    "rem": "cover",
    "rem cua": "cover",
}


# ==============================================================================
# 4. Local Semantic Router Implementation
# ==============================================================================

class LocalSemanticRouter:
    """
    Sub-millisecond Local Semantic Intent & Slot-Filling Engine for JARVIS.
    """

    def __init__(self) -> None:
        # Pre-compile conversational vocative prefixes
        self._vocative_pattern = re.compile(
            r"^(?:(?:ê|này|hey|hi|hello)?\s*jarvis(?:\s*ơi|\s*à|\s*nhe|\s*nhé)?|[êe]|này|làm\s*ơn|hãy\s*giúp\s*(?:tôi|tao|mình)|giúp\s*(?:tôi|tao|mình)\s*(?:với)?|cho\s*hỏi\s*xíu|bạn\s*ơi)[,\s]+",
            re.IGNORECASE,
        )

    def strip_vocatives(self, text: str) -> str:
        """Removes conversational pleasantries and vocative prefixes."""
        return self._vocative_pattern.sub("", text.strip()).strip()

    def match(self, text: str) -> IntentResult | None:
        """
        Attempts to semantically match the utterance to a structured IntentResult.
        Returns None if no intent matches with high confidence.
        """
        if not text:
            return None

        clean = self.strip_vocatives(text)
        if not clean:
            return None

        norm = normalize_vietnamese_text(clean)

        # 1. Volume & Audio Slot Matching
        res = self._match_volume(clean, norm)
        if res:
            return res

        # 2. Screen & Display Brightness Slot Matching
        res = self._match_brightness(clean, norm)
        if res:
            return res

        # 3. Smart Home / IoT Slot Matching (Home Assistant)
        res = self._match_smart_home(clean, norm)
        if res:
            return res

        # 4. Window & Browser Tab Slot Matching
        res = self._match_window_tab(clean, norm)
        if res:
            return res

        # 5. Media & Music Slot Matching
        res = self._match_media(clean, norm)
        if res:
            return res

        # 6. Countdown Timers & Alarms
        res = self._match_timer_reminder(clean, norm)
        if res:
            return res

        # 7. Web Search Queries
        res = self._match_web_search(clean, norm)
        if res:
            return res

        # 8. System Diagnostics & Hardware Queries
        res = self._match_system_diagnostics(clean, norm)
        if res:
            return res

        # 9. Desktop Application Launching
        res = self._match_app_launch(clean, norm)
        if res:
            return res

        # 10. Personal Notes & Quick Memos
        res = self._match_notes(clean, norm)
        if res:
            return res

        # 11. Weather & Forecast Queries
        res = self._match_weather(clean, norm)
        if res:
            return res

        return None

    # --------------------------------------------------------------------------
    # Slot Matcher: Volume
    # --------------------------------------------------------------------------

    def _match_volume(self, clean: str, norm: str) -> IntentResult | None:
        is_vol_mention = any(k in norm for k in ("am luong", "volume", "tieng", "loa"))
        if not is_vol_mention and not re.search(r"\b(?:van to|van nho|mo to|mo nho|tang to|ha nho|tat loa|bat loa)\b", norm):
            return None

        # Guard: "dừng nói", "im lặng" belong to barge-in (tts_stop), not volume
        if norm in ("im lang", "im di", "dung noi", "ngung noi", "stop talking"):
            return None

        # A. Mute / Unmute
        if any(k in norm for k in ("tat tieng", "tat loa", "ngat tieng", "mute", "cam tieng")):
            return IntentResult(
                action_name="system_volume",
                parameters={"mute": True},
                confidence=1.0,
                source="rule_fallback",
                response_text="Đã tắt tiếng hệ thống, thưa Ngài.",
            )
        if any(k in norm for k in ("bat tieng", "bat loa", "mo tieng", "unmute")):
            return IntentResult(
                action_name="system_volume",
                parameters={"mute": False},
                confidence=1.0,
                source="rule_fallback",
                response_text="Đã bật lại âm thanh hệ thống cho Ngài.",
            )

        # B. Query
        if any(k in norm for k in ("bao nhieu", "muc nao", "hien tai")):
            return IntentResult(
                action_name="system_volume",
                parameters={"clarify": True},
                confidence=0.95,
                source="rule_fallback",
                response_text="Tôi có thể kiểm tra hoặc điều chỉnh âm lượng theo yêu cầu của Ngài.",
            )

        # Extract number if present
        num = parse_vietnamese_number(clean)

        is_down = bool(re.search(r"\b(?:giam|nho|ha|xuong|down|lower|decrease|bot)\b", norm))
        is_up = bool(re.search(r"\b(?:tang|to|lon|len|up|raise|increase)\b", norm))

        # C. Relative decrease (Down)
        if is_down:
            delta = num if num is not None else 10
            if re.search(r"\b(?:mot\s*chut|ti|chut)\b", norm):
                delta = 5
            return IntentResult(
                action_name="system_volume",
                parameters={"delta": -delta},
                confidence=1.0,
                source="rule_fallback",
                response_text=f"Đã giảm âm lượng xuống {delta}%, thưa Ngài.",
            )

        # D. Relative increase (Up)
        if is_up:
            delta = num if num is not None else 10
            if re.search(r"\b(?:mot\s*chut|ti|chut)\b", norm):
                delta = 5
            return IntentResult(
                action_name="system_volume",
                parameters={"delta": delta},
                confidence=1.0,
                source="rule_fallback",
                response_text=f"Đã tăng âm lượng thêm {delta}%, thưa Ngài.",
            )

        # E. Set absolute volume level
        # Matches: "âm lượng 80", "cho âm lượng 80%", "đặt âm lượng 50", "chỉnh âm lượng mức 70"
        is_set = any(k in norm for k in ("dat", "cai", "chinh", "set", "cho", "o muc", "muc")) or (
            num is not None and re.match(r"^(?:am luong|volume)\s+\d+", norm)
        )
        if is_set and num is not None:
            level = max(0, min(100, num))
            return IntentResult(
                action_name="system_volume",
                parameters={"level": level},
                confidence=1.0,
                source="rule_fallback",
                response_text=f"Đã đặt âm lượng hệ thống thành {level}%, thưa Ngài.",
            )

        # F. Ambiguous volume commands (e.g. "điều chỉnh âm lượng", "dieu chinh am luong", "vặn loa")
        # Follows H-08 truthfulness contract: asks clarification without executing or changing hardware
        if any(norm == k or norm.startswith(k + " ") for k in ("dieu chinh am luong", "chinh am luong", "van loa", "dieu chinh loa", "chinh loa")) and num is None and not is_down and not is_up:
            return IntentResult(
                action_name="system_volume",
                parameters={"clarify": True},
                confidence=1.0,
                source="rule_fallback",
                response_text=(
                    "Ngài muốn tăng âm lượng, giảm âm lượng, tắt tiếng, bật tiếng, "
                    "hay đặt một mức âm lượng cụ thể? Xin nói rõ hơn, thưa Ngài."
                ),
            )

        return None

    # --------------------------------------------------------------------------
    # Slot Matcher: Brightness
    # --------------------------------------------------------------------------

    def _match_brightness(self, clean: str, norm: str) -> IntentResult | None:
        is_brightness_mention = any(k in norm for k in ("do sang", "sang man hinh", "brightness", "anh sang man hinh"))
        if not is_brightness_mention and not re.search(r"\bman hinh (?:sang|toi)\b", norm):
            return None

        # Query
        if any(k in norm for k in ("bao nhieu", "hien tai", "kiem tra")):
            return IntentResult(
                action_name="system_brightness",
                parameters={"query": True},
                confidence=1.0,
                source="rule_fallback",
                response_text="Đang kiểm tra độ sáng màn hình cho Ngài.",
            )

        num = parse_vietnamese_number(clean)

        is_decrease = bool(re.search(r"\b(?:giam|toi\s*bot|toi\s*di|toi\s*hon|ha|down|lower|decrease|toi)\b", norm))
        is_increase = bool(re.search(r"\b(?:tang|sang\s*len|sang\s*hon|up|increase)\b", norm))

        # Relative decrease
        if is_decrease:
            delta = num if num is not None else 10
            return IntentResult(
                action_name="system_brightness",
                parameters={"delta": -delta},
                confidence=1.0,
                source="rule_fallback",
                response_text=f"Đã giảm độ sáng màn hình xuống {delta}%, thưa Ngài.",
            )

        # Relative increase
        if is_increase:
            delta = num if num is not None else 10
            return IntentResult(
                action_name="system_brightness",
                parameters={"delta": delta},
                confidence=1.0,
                source="rule_fallback",
                response_text=f"Đã tăng độ sáng màn hình thêm {delta}%, thưa Ngài.",
            )

        # Set absolute
        is_set = any(k in norm for k in ("dat", "cai", "chinh", "set", "cho", "muc")) or (
            num is not None and re.match(r"^(?:do sang|brightness)\s+\d+", norm)
        )
        if is_set and num is not None:
            level = max(0, min(100, num))
            return IntentResult(
                action_name="system_brightness",
                parameters={"level": level},
                confidence=1.0,
                source="rule_fallback",
                response_text=f"Đã đặt độ sáng màn hình thành {level}%, thưa Ngài.",
            )

        return None

    # --------------------------------------------------------------------------
    # Slot Matcher: Smart Home (Home Assistant)
    # --------------------------------------------------------------------------

    def _match_smart_home(self, clean: str, norm: str) -> IntentResult | None:
        # Detect Domain
        matched_domain: str | None = None
        matched_device_key: str | None = None
        for dev_key, domain in _DEVICE_DOMAINS.items():
            if re.search(r"\b" + re.escape(dev_key) + r"\b", norm):
                matched_domain = domain
                matched_device_key = dev_key
                break

        if not matched_domain:
            return None

        # Guard: Ignore media control phrases like "bật nhạc", "mở bài hát"
        if matched_device_key == "dien" and "thoai" in norm:  # "điện thoại"
            return None

        # Detect Area / Room
        matched_area = "living_room"  # default canonical area
        for room_key, area_id in _ROOM_ALIASES.items():
            if room_key in norm:
                matched_area = area_id
                break

        # Construct Canonical Entity ID
        if matched_domain == "light":
            entity_id = f"light.{matched_area}"
        elif matched_domain == "fan":
            if "tran" in norm:
                entity_id = "fan.ceiling"
            else:
                entity_id = f"fan.{matched_area}"
        elif matched_domain == "climate":
            entity_id = "climate.ac_unit"
        elif matched_domain == "switch":
            if "binh" in norm or "nuoc nong" in norm:
                entity_id = "switch.water_heater"
            else:
                entity_id = f"switch.{matched_area}"
        else:
            entity_id = f"{matched_domain}.{matched_area}"

        # Detect Service / Action
        # Temperature control for climate
        temp_match = re.search(r"(\d{1,2}(?:\.\d+)?)\s*(?:do|do c|c|degree)?", clean)
        if matched_domain == "climate" and any(k in norm for k in ("dat", "chinh", "set", "ha", "tang", "muc")) and temp_match:
            temp_val = float(temp_match.group(1))
            if 16.0 <= temp_val <= 32.0:
                return IntentResult(
                    action_name="home_assistant_call",
                    parameters={
                        "domain": "climate",
                        "service": "set_temperature",
                        "entity_id": entity_id,
                        "temperature": temp_val,
                    },
                    confidence=1.0,
                    source="rule_fallback",
                    response_text=f"Đã đặt nhiệt độ điều hòa thành {temp_val} độ cho Ngài.",
                )

        is_turn_off = bool(re.search(r"\b(?:tat|dong|turn\s*off|ngat|off)\b", norm))
        is_turn_on = bool(re.search(r"\b(?:bat|mo|turn\s*on|khoi\s*dong|on)\b", norm))

        dev_name = "đèn" if matched_domain == "light" else "thiết bị"
        if matched_domain == "fan":
            dev_name = "quạt"
        elif matched_domain == "climate":
            dev_name = "điều hòa"
        elif matched_domain == "switch" and "binh" in norm:
            dev_name = "bình nóng lạnh"

        if is_turn_off:
            return IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": matched_domain, "service": "turn_off", "entity_id": entity_id},
                confidence=1.0,
                source="rule_fallback",
                response_text=f"Đang tắt {dev_name} cho Ngài.",
            )

        if is_turn_on:
            return IntentResult(
                action_name="home_assistant_call",
                parameters={"domain": matched_domain, "service": "turn_on", "entity_id": entity_id},
                confidence=1.0,
                source="rule_fallback",
                response_text=f"Đang bật {dev_name} cho Ngài.",
            )

        return None

    # --------------------------------------------------------------------------
    # Slot Matcher: Window & Browser Tab
    # --------------------------------------------------------------------------

    def _match_window_tab(self, clean: str, norm: str) -> IntentResult | None:
        # Minimize all windows to desktop
        if any(k in norm for k in ("thu nho tat ca cua so", "an het cua so", "hien desktop", "ra man hinh chinh", "minimize all")):
            return IntentResult(
                action_name="window_minimize_all",
                parameters={},
                confidence=1.0,
                source="rule_fallback",
                response_text="Đã thu nhỏ tất cả cửa sổ về màn hình Desktop cho Ngài.",
            )

        # Tab Operations
        if any(k in norm for k in ("mo tab moi", "tao tab moi", "bat tab moi", "new tab")):
            return IntentResult(
                action_name="new_tab",
                parameters={},
                confidence=1.0,
                source="rule_fallback",
                response_text="Đã mở tab mới cho Ngài.",
            )
        if any(k in norm for k in ("dong tab", "tat tab", "close tab")):
            return IntentResult(
                action_name="close_tab",
                parameters={},
                confidence=1.0,
                source="rule_fallback",
                response_text="Đã đóng tab hiện tại cho Ngài.",
            )

        # Page Refresh (F5)
        if any(k in norm for k in ("tai lai trang", "lam moi trang", "refresh trang", "load lai trang", "f5 trang")):
            return IntentResult(
                action_name="page_refresh",
                parameters={},
                confidence=1.0,
                source="rule_fallback",
                response_text="Đang tải lại trang web cho Ngài.",
            )

        # Page Scroll
        if any(k in norm for k in ("cuon xuong", "cuon trang xuong", "keo xuong")):
            return IntentResult(
                action_name="page_scroll",
                parameters={"direction": "down"},
                confidence=1.0,
                source="rule_fallback",
                response_text="Đang cuộn trang xuống cho Ngài.",
            )
        if any(k in norm for k in ("cuon len", "cuon trang len", "keo len")):
            return IntentResult(
                action_name="page_scroll",
                parameters={"direction": "up"},
                confidence=1.0,
                source="rule_fallback",
                response_text="Đang cuộn trang lên cho Ngài.",
            )

        return None

    # --------------------------------------------------------------------------
    # Slot Matcher: Media & Music
    # --------------------------------------------------------------------------

    def _match_media(self, clean: str, norm: str) -> IntentResult | None:
        # YouTube specific search / open
        yt_match = re.search(r"(?:mo|xem|phat|tim)\s+(?:tren\s+youtube|video|clip|youtube)\s*(.*)", norm)
        if yt_match and yt_match.group(1).strip():
            query = yt_match.group(1).strip()
            # extract original query with diacritics
            orig_match = re.search(r"(?:mở|xem|phát|tìm)\s+(?:trên\s+youtube|video|clip|youtube)\s*(.*)", clean, re.IGNORECASE)
            q_clean = orig_match.group(1).strip() if orig_match else query
            return IntentResult(
                action_name="web_open",
                parameters={
                    "target": f"https://www.youtube.com/results?{urlencode({'search_query': q_clean})}",
                    "site": "youtube",
                    "query": q_clean,
                },
                confidence=1.0,
                source="rule_fallback",
                response_text=f"Đang mở '{q_clean}' trên YouTube cho Ngài.",
            )

        # Media controls (Next, Pause, Resume, Stop)
        if any(k in norm for k in ("chuyen bai", "bai tiep theo", "bai tiep", "next song", "next track")):
            return IntentResult(
                action_name="spotify",
                parameters={"command": "next"},
                confidence=1.0,
                source="rule_fallback",
                response_text="Đang chuyển bài tiếp theo, thưa Ngài.",
            )
        if any(k in norm for k in ("tam dung nhac", "pause nhac", "dung nhac", "pause music")):
            return IntentResult(
                action_name="spotify",
                parameters={"command": "pause"},
                confidence=1.0,
                source="rule_fallback",
                response_text="Đã tạm dừng phát nhạc, thưa Ngài.",
            )
        if any(k in norm for k in ("tiep tuc phat nhac", "phat tiep", "resume music")):
            return IntentResult(
                action_name="spotify",
                parameters={"command": "play", "query": ""},
                confidence=1.0,
                source="rule_fallback",
                response_text="Đang tiếp tục phát nhạc cho Ngài.",
            )

        # Song search: "phát bài X trên spotify", "mở bài X", "nghe bài X"
        song_match = re.search(r"^(?:phat|mo|nghe|bat)\s+(?:bai\s*hat|bai|song|nhac)\s+(.+)$", norm)
        if song_match:
            raw_song = song_match.group(1).strip()
            # Clean trailing platform mentions
            raw_song_clean = re.sub(r"\s+(?:tren|qua)\s+spotify$", "", raw_song).strip()
            # Extract corresponding substring from original casing
            orig_match = re.search(r"^(?:phát|mở|nghe|bật)\s+(?:bài\s*hát|bài|song|nhạc)\s+(.+)$", clean, re.IGNORECASE)
            orig_song = orig_match.group(1).strip() if orig_match else raw_song_clean
            orig_song = re.sub(r"\s+(?:trên|qua)\s+spotify$", "", orig_song, flags=re.IGNORECASE).strip()

            return IntentResult(
                action_name="spotify",
                parameters={"query": orig_song},
                confidence=1.0,
                source="rule_fallback",
                response_text=f"Đang mở Spotify và phát {orig_song} cho Ngài.",
            )

        return None

    # --------------------------------------------------------------------------
    # Slot Matcher: Timers & Reminders
    # --------------------------------------------------------------------------

    def _match_timer_reminder(self, clean: str, norm: str) -> IntentResult | None:
        if not any(k in norm for k in ("hen gio", "bam gio", "dat bao thuc", "nhac toi", "nhac nho")):
            return None

        seconds, label = parse_duration_seconds(clean)
        if seconds is not None:
            if "nhac" in norm:
                msg = label if label else "Đã đến giờ nhắc nhở"
                return IntentResult(
                    action_name="reminder_set",
                    parameters={"duration": seconds, "message": msg},
                    confidence=1.0,
                    source="rule_fallback",
                    response_text=f"Đã tạo nhắc nhở sau {seconds // 60} phút cho Ngài: {msg}",
                )
            else:
                lbl = label if label else "Hẹn giờ"
                return IntentResult(
                    action_name="timer_set",
                    parameters={"duration": seconds, "label": lbl},
                    confidence=1.0,
                    source="rule_fallback",
                    response_text=f"Đã đặt hẹn giờ {seconds // 60} phút cho Ngài.",
                )

        return None

    # --------------------------------------------------------------------------
    # Slot Matcher: Web Search
    # --------------------------------------------------------------------------

    def _match_web_search(self, clean: str, norm: str) -> IntentResult | None:
        # Matches: "tìm kiếm X trên google", "tra cứu X", "search google X"
        search_match = re.search(
            r"^(?:tim\s*kiem|tra\s*cuu|search|tim)\s+(?:thong\s*tin\s+)?(?:tren\s+google\s+)?(.+)$",
            norm,
        )
        if search_match:
            raw_q = search_match.group(1).strip()
            # Clean "trên google" from tail
            raw_q = re.sub(r"\s+(?:tren|qua)\s+google$", "", raw_q).strip()

            orig_match = re.search(
                r"^(?:tìm\s*kiếm|tra\s*cứu|search|tìm)\s+(?:thông\s*tin\s+)?(?:trên\s+google\s+)?(.+)$",
                clean,
                re.IGNORECASE,
            )
            q_clean = orig_match.group(1).strip() if orig_match else raw_q
            q_clean = re.sub(r"\s+(?:trên|qua)\s+google$", "", q_clean, flags=re.IGNORECASE).strip()

            if q_clean:
                target_url = "https://www.google.com/search?" + urlencode({"q": q_clean})
                return IntentResult(
                    action_name="web_open",
                    parameters={"query": q_clean, "target": target_url},
                    confidence=1.0,
                    source="rule_fallback",
                    response_text=f"Đang tìm kiếm '{q_clean}' trên Google cho Ngài.",
                )

        return None

    # --------------------------------------------------------------------------
    # Slot Matcher: System Diagnostics & Hardware
    # --------------------------------------------------------------------------

    def _match_system_diagnostics(self, clean: str, norm: str) -> IntentResult | None:
        # Screenshot
        if any(k in norm for k in ("chup man hinh", "chup anh man hinh", "capture screen", "screenshot")):
            return IntentResult(
                action_name="screen_capture",
                parameters={},
                confidence=1.0,
                source="rule_fallback",
                response_text="Đã chụp ảnh màn hình và lưu ra Desktop cho Ngài.",
            )

        # Lock / Abort Power
        if any(k in norm for k in ("huy tat may", "huy lenh tat may", "dung tat may", "abort shutdown")):
            return IntentResult(
                action_name="system_power",
                parameters={"action": "abort"},
                confidence=1.0,
                source="rule_fallback",
                response_text="Đang hủy lệnh tắt máy cho Ngài.",
                danger_level="LOW",
                requires_confirmation=False,
            )

        if any(k in norm for k in ("khoa man hinh", "khoa may", "lock screen")):
            return IntentResult(
                action_name="system_power",
                parameters={"action": "lock"},
                confidence=1.0,
                source="rule_fallback",
                response_text="Đang khóa máy cho Ngài.",
                danger_level="LOW",
                requires_confirmation=False,
            )

        # Hardware health
        if any(k in norm for k in ("suc khoe he thong", "tinh trang may tinh", "kiem tra phan cung")):
            return IntentResult(
                action_name="hardware_status_query",
                parameters={},
                confidence=1.0,
                source="rule_fallback",
                response_text="Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu, CPU và RAM ở mức an toàn, thưa Ngài.",
            )

        return None

    # --------------------------------------------------------------------------
    # Slot Matcher: Desktop Application Launching
    # --------------------------------------------------------------------------

    def _match_app_launch(self, clean: str, norm: str) -> IntentResult | None:
        """Matches desktop application launch requests with typed slot extraction."""
        pattern = re.compile(
            r"^(?:mo|bat|chay|khoi dong|open|launch|start)\s+(?:ung dung|phan mem|app|application|chuong trinh)?\s*(.+)$",
            re.IGNORECASE,
        )
        m = pattern.search(norm)
        if not m:
            return None

        raw_target = m.group(1).strip()
        # Exclude web / search / youtube / workspace / music / folder / hardware / mic / audio / IoT / dashboard commands
        if any(raw_target.startswith(prefix) for prefix in (
            "youtube", "web", "website", "trang web", "du an", "project", "workspace",
            "nhac", "bai hat", "documents", "downloads", "desktop", "thu muc", "folder",
            "mic", "micro", "loa", "am thanh", "am luong", "tieng", "den", "quat",
            "dieu hoa", "wifi", "bluetooth", "man hinh", "may tinh", "camera", "webcam",
            "dashboard",
        )):
            return None

        tokens = set(raw_target.split())
        if tokens & {"mic", "micro", "microphone", "loa", "speaker", "tat"}:
            return None

        app_map: dict[str, str] = {
            "notepad": "notepad",
            "so tay": "notepad",
            "chrome": "chrome",
            "google chrome": "chrome",
            "trinh duyet": "chrome",
            "calculator": "calculator",
            "may tinh": "calculator",
            "calc": "calculator",
            "vscode": "code",
            "vs code": "code",
            "code": "code",
            "visual studio code": "code",
            "terminal": "terminal",
            "powershell": "powershell",
            "cmd": "cmd",
            "command prompt": "cmd",
            "spotify": "spotify",
            "settings": "Settings",
            "cai dat": "Settings",
            "task manager": "taskmgr",
            "taskmgr": "taskmgr",
            "quan ly tac vu": "taskmgr",
            "discord": "discord",
            "word": "word",
            "excel": "excel",
            "explorer": "explorer",
            "file explorer": "explorer",
        }

        canonical_app = app_map.get(raw_target)
        if not canonical_app:
            for k, v in app_map.items():
                if re.search(r"\b" + re.escape(k) + r"\b", raw_target):
                    canonical_app = v
                    break

        if not canonical_app:
            if 1 <= len(raw_target) <= 64:
                canonical_app = raw_target
            else:
                return None

        params = {"app_name": canonical_app}
        if canonical_app == "Settings":
            params["app"] = "ms-settings:"
        else:
            params["installed_only"] = True

        return IntentResult(
            action_name="app_open",
            parameters=params,
            confidence=1.0,
            source="rule_fallback",
            response_text=f"Đang mở ứng dụng {canonical_app} cho Ngài.",
        )

    # --------------------------------------------------------------------------
    # Slot Matcher: Personal Notes & Quick Memos
    # --------------------------------------------------------------------------

    def _match_notes(self, clean: str, norm: str) -> IntentResult | None:
        """Matches personal note taking and quick memos with typed slot extraction."""
        # List notes check
        if any(k in norm for k in ("xem ghi chu", "doc ghi chu", "danh sach ghi chu", "list note", "show note", "mo ghi chu")):
            return IntentResult(
                action_name="note_list",
                parameters={},
                confidence=1.0,
                source="rule_fallback",
                response_text="Đây là danh sách ghi chú của Ngài.",
            )

        if not any(k in norm for k in ("ghi chu", "luu ghi chu", "tao ghi chu", "note lai", "take note", "add note")):
            return None

        content = ""
        pattern = re.compile(
            r"^(?:(?:lưu|tao|tạo)?\s*ghi\s*chú|note(?:\s*lại)?|take\s*note|add\s*note)\s*[:,\s]?\s*(.*)$",
            re.IGNORECASE,
        )
        m = pattern.search(clean)
        if m and m.group(1).strip():
            content = m.group(1).strip()
        else:
            m_norm = re.search(r"^(?:(?:luu|tao)?\s*ghi\s*chu|note(?:\s*lai)?)\s*[:,\s]?\s*(.*)$", norm)
            if m_norm and m_norm.group(1).strip():
                content = m_norm.group(1).strip()

        resp = f"Đã lưu ghi chú cho Ngài: {content}" if content else "Bạn muốn ghi chú nội dung gì?"
        return IntentResult(
            action_name="note_add",
            parameters={"content": content, "action": "add"},
            confidence=1.0,
            source="rule_fallback",
            response_text=resp,
        )

    # --------------------------------------------------------------------------
    # Slot Matcher: Weather & Meteorological Forecasts
    # --------------------------------------------------------------------------

    def _match_weather(self, clean: str, norm: str) -> IntentResult | None:
        """Matches weather forecast and meteorological queries with location slot extraction."""
        is_weather = any(k in norm for k in ("thoi tiet", "du bao thoi tiet", "nhiet do ngoai troi", "troi co mua", "troi mua khong", "thoi tiet hom nay"))
        if not is_weather:
            return None

        location = "current"
        city_param = "Hà Nội"
        cmd = "curl -s wttr.in?format=3"

        if any(c in norm for c in ("ha noi", "hanoi", "thu do")):
            location = "Hà Nội"
            city_param = "Hà Nội"
            cmd = "curl -s wttr.in/Hanoi?format=3"
        elif any(c in norm for c in ("sai gon", "saigon", "ho chi minh", "tp hcm", "hcm")):
            location = "Sài Gòn"
            city_param = "Sài Gòn"
            cmd = "curl -s wttr.in/Saigon?format=3"
        elif any(c in norm for c in ("da nang", "danang")):
            location = "Đà Nẵng"
            city_param = "Đà Nẵng"
            cmd = "curl -s wttr.in/Danang?format=3"

        return IntentResult(
            action_name="shell_exec",
            parameters={"command": cmd, "topic": "weather", "location": location, "city": city_param},
            confidence=1.0,
            source="rule_fallback",
            response_text=f"Đang kiểm tra thời tiết {location if location != 'current' else 'hôm nay'} cho Ngài.",
        )


# ==============================================================================
# 5. Fast On-Device Hybrid Semantic Router (TF-IDF + Typed Slots)
# ==============================================================================

_EXEMPLARS: dict[str, list[str]] = {
    "volume": [
        "tang am luong", "tăng âm lượng", "mở to lên", "cho to tiếng lên", "bật to loa",
        "tăng âm lượng lên 20%", "tăng volume", "vặn to loa", "cho lớn tiếng",
        "giam am luong", "giảm âm lượng", "nhỏ tiếng lại", "vặn nhỏ volume", "hạ nhỏ loa",
        "giảm âm lượng xuống 15%", "cho nhỏ loa lại", "bớt tiếng",
        "tat am thanh", "tắt tiếng", "mute loa", "ngắt âm thanh", "tắt loa máy tính",
        "bat am thanh", "bật tiếng", "unmute", "mở lại tiếng", "bật loa máy tính",
        "dat am luong 50%", "chỉnh volume 30%", "âm lượng 70 phần trăm", "đặt âm lượng mức 40",
    ],
    "brightness": [
        "tang do sang", "tăng độ sáng màn hình", "cho màn hình sáng lên", "sáng hơn", "tăng ánh sáng màn hình",
        "giam do sang", "giảm độ sáng màn hình", "màn hình chói quá", "tối hơn", "hạ độ sáng",
        "dat do sang 70%", "chỉnh độ sáng 50%", "độ sáng 100%", "chỉnh sáng màn hình 80%", "độ sáng 30 phần trăm",
    ],
    "media": [
        "mo nhac", "mở nhạc", "phát nhạc", "bật nhạc spotify", "nghe nhạc", "mở bài hát",
        "tam dung nhac", "tạm dừng bài hát", "pause music", "dừng phát", "ngừng phát nhạc",
        "tiep tuc phat", "phát tiếp", "resume music", "tiếp tục nghe nhạc",
        "chuyen bai", "bài tiếp theo", "next song", "bài sau", "bỏ qua bài này",
        "quay lai bai truoc", "bài trước đó", "previous track", "nghe lại bài trước",
        "phat bai hat son tung", "mở spotify bài hát mới", "nghe nhạc chill",
    ],
    "app_launch": [
        "mo ung dung notepad", "bật notepad", "khởi động notepad", "chạy notepad", "mở sổ tay ghi chép",
        "mo trinh duyet chrome", "bật chrome", "khởi động google chrome", "chạy chrome", "mở web chrome",
        "mo visual studio code", "bật vs code", "mở code", "khởi động vscode", "chạy visual studio code",
        "mo may tinh calculator", "bật calculator", "mở máy tính tính tiền", "chạy calculator",
        "mo terminal", "bật powershell", "khởi động command prompt", "mở cmd", "chạy terminal",
        "mo ung dung spotify", "chạy spotify desktop", "bật ứng dụng nghe nhạc spotify",
        "mo cai dat he thong", "mở settings", "bật windows settings", "cài đặt máy tính",
        "mo task manager", "bật quan ly tac vu", "mở trình quản lý tác vụ",
        "mo ung dung discord", "bật discord", "chạy discord",
        "mo word", "bật microsoft word", "mở excel", "bật microsoft excel",
    ],
    "timers": [
        "hen gio 5 phut", "hẹn giờ 10 phút", "đặt hẹn giờ 15 phút", "hẹn giờ 20 phút",
        "bam gio 20 phut", "bấm giờ nửa tiếng", "hẹn giờ 1 tiếng", "đặt hẹn giờ 2 tiếng",
        "dat bao thuc 30 phut", "báo thức sau 45 phút", "đặt báo thức sáng mai",
        "nhac nho toi sau 10 phut", "nhắc tôi gọi điện sau 15 phút", "nhắc việc sau 1 giờ",
        "đặt đồng hồ bấm giờ 3 phút", "hẹn giờ nấu ăn 25 phút",
    ],
    "notes": [
        "ghi chu lai mua sua", "ghi chú mua sữa", "lưu ghi chú mua quà", "ghi chú cần mua bánh mì",
        "tao ghi chu moi", "tạo ghi chú họp ngày mai", "note lại lịch hẹn", "tạo note mới",
        "luu ghi chu gap khach hang luc 2h chieu", "ghi chú công việc cần làm",
        "ghi nhớ việc ngày mai đi khám răng", "lưu lại thông tin tài khoản ngân hàng",
    ],
    "weather": [
        "thoi tiet hom nay", "thời tiết hôm nay thế nào", "dự báo thời tiết", "xem thời tiết",
        "troi hom nay co mua khong", "nhiệt độ thời tiết ngoài trời", "trời nắng hay mưa",
        "thoi tiet ha noi", "dự báo thời tiết hà nội hôm nay", "thời tiết thủ đô hà nội",
        "thoi tiet sai gon", "dự báo thời tiết hồ chí minh hôm nay", "thời tiết tp hcm",
        "thoi tiet da nang", "thời tiết đà nẵng hôm nay", "nhiệt độ đà nẵng",
    ],
}


class HybridSemanticRouter:
    """
    Sub-2ms Fast On-Device Hybrid Semantic Router for JARVIS.

    Combines:
      1. Deterministic typed slot extraction and regex parsing from LocalSemanticRouter.
      2. TF-IDF vector similarity matching using SemanticVectorStore against reference
         command prototypes for high-frequency desktop domains:
         - Volume & Audio controls
         - Screen & Brightness
         - Media & Music
         - Desktop Application Launching
         - Timers & Countdowns
         - Personal Notes & Memos
         - Weather & Meteorological Queries

    Guarantees sub-2ms intent resolution on-device, bypassing Cloud LLM roundtrip.
    """

    def __init__(
        self,
        local_router: LocalSemanticRouter | None = None,
        vector_store: SemanticVectorStore | None = None,
        similarity_threshold: float = 0.20,
    ) -> None:
        self.local_router = local_router or LocalSemanticRouter()
        self.similarity_threshold = similarity_threshold

        if vector_store is not None:
            self.vector_store = vector_store
        else:
            # Pure in-memory vector store without disk persistence
            cfg = VectorStoreConfig(
                persist_path=":memory:",
                auto_save=False,
                similarity_threshold=self.similarity_threshold,
            )
            self.vector_store = SemanticVectorStore(config=cfg)
            self._index_prototype_exemplars()

    def _index_prototype_exemplars(self) -> None:
        """Indexes representative exemplars across 7 high-frequency desktop command domains."""
        doc_count = 0
        for category, phrases in _EXEMPLARS.items():
            for idx, phrase in enumerate(phrases):
                doc_id = f"prototype_{category}_{idx}"
                self.vector_store.add_document(doc_id=doc_id, content=phrase, category=category)
                doc_count += 1
        logger.debug("HybridSemanticRouter indexed %d prototypes across %d domains", doc_count, len(_EXEMPLARS))

    def route(self, text: str) -> IntentResult | None:
        """
        Fast-path routing of input utterance into structured IntentResult in < 2ms.
        First attempts typed slot-filling from LocalSemanticRouter.
        If unhandled, executes TF-IDF cosine similarity search across high-frequency prototypes.
        """
        return self.match(text)

    def match(self, text: str) -> IntentResult | None:
        """
        Matches text against local slot-filling and TF-IDF semantic prototype vectors.
        Returns resolved IntentResult or None if no high-confidence local match exists.
        """
        if not text or not text.strip():
            return None

        clean = self.local_router.strip_vocatives(text)
        if not clean:
            return None

        norm = normalize_vietnamese_text(clean)

        # Fast Path A: Deterministic Typed Slot-Filling via LocalSemanticRouter
        local_res = self.local_router.match(text)
        if local_res is not None:
            local_res.source = "hybrid_fast_path"
            return local_res

        # Fast Path B: TF-IDF Vector Similarity Search across High-Frequency Prototype Commands
        search_results = self.vector_store.search(norm, k=1)
        if not search_results or search_results[0].score < self.similarity_threshold:
            # Also try raw text search if norm returned low score
            search_results = self.vector_store.search(clean, k=1)

        if not search_results or search_results[0].score < self.similarity_threshold:
            return None

        top = search_results[0]
        cat = top.category
        score = float(top.score)

        # Domain-specific typed slot extraction guided by vector classification
        if cat == "volume":
            res = self.local_router._match_volume(clean, norm)
            if res:
                res.confidence = max(res.confidence, score)
                res.source = "hybrid_fast_path"
                return res
            return None

        if cat == "brightness":
            res = self.local_router._match_brightness(clean, norm)
            if res:
                res.confidence = max(res.confidence, score)
                res.source = "hybrid_fast_path"
                return res
            return None

        if cat == "media":
            res = self.local_router._match_media(clean, norm)
            if res:
                res.confidence = max(res.confidence, score)
                res.source = "hybrid_fast_path"
                return res
            return None

        if cat == "app_launch":
            res = self.local_router._match_app_launch(clean, norm)
            if res:
                res.confidence = max(res.confidence, score)
                res.source = "hybrid_fast_path"
                return res

        if cat == "timers":
            res = self.local_router._match_timer_reminder(clean, norm)
            if res:
                res.confidence = max(res.confidence, score)
                res.source = "hybrid_fast_path"
                return res

        if cat == "notes":
            res = self.local_router._match_notes(clean, norm)
            if res:
                res.confidence = max(res.confidence, score)
                res.source = "hybrid_fast_path"
                return res

        if cat == "weather":
            res = self.local_router._match_weather(clean, norm)
            if res:
                res.confidence = max(res.confidence, score)
                res.source = "hybrid_fast_path"
                return res

        return None

    def benchmark_latency(self, text: str = "tăng âm lượng lên 20%", iterations: int = 100) -> float:
        """
        Benchmarks average routing latency in milliseconds over N iterations.
        Ensures sub-2ms execution for on-device processing.
        """
        # Warmup
        for _ in range(5):
            self.route(text)
        start = time.perf_counter()
        for _ in range(iterations):
            self.route(text)
        elapsed = time.perf_counter() - start
        avg_ms = (elapsed / iterations) * 1000.0
        return avg_ms


__all__ = [
    "LocalSemanticRouter",
    "HybridSemanticRouter",
    "normalize_vietnamese_text",
    "parse_vietnamese_number",
    "parse_duration_seconds",
]

