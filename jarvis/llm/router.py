"""
jarvis/llm/router.py
====================
Two-Tier Intent Routing Engine and Dynamic Action Schema Generator for JARVIS.
Provides:
  - Tier 1: Sub-millisecond Regex & Vietnamese Keyword Fast Engine.
  - Tier 2: Multi-Provider LLM Semantic Reasoning with Dynamic Tool Calling.
  - Tier 3: Graceful Vietnamese Rule Fallback on network timeout, 429 rate limit, or missing API key.
"""
from __future__ import annotations

import inspect
import logging
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Union, get_args, get_origin
from urllib.parse import urlencode

from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import ActionResult, RequesterContext
from jarvis.llm.client import LLMClient, LLMResponse
from jarvis.llm.models import IntentResult
from jarvis.llm.rules_catalog import get_default_rules

logger = logging.getLogger("jarvis.llm.router")

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

_COMBINING_DIACRITICS_RE = re.compile(r"[\u0300-\u036f]")


def strip_vietnamese_diacritics(text: str) -> str:
    """
    Strips all Vietnamese diacritics / tone marks and normalizes 'đ'/'Đ' to 'd'/'D'.
    Supports both precomposed NFC and decomposed NFD Unicode representations.
    Preserves all ASCII characters, whitespace, numbers, and punctuation.

    Examples:
        'Điều chỉnh âm lượng' -> 'Dieu chinh am luong'
        'Tìm kiếm Google.'    -> 'Tim kiem Google.'
        'Trời hôm nay thế nào?' -> 'Troi hom nay the nao?'
        'đặc nhắc'            -> 'dac nhac'
        'nhạc'                -> 'nhac'
    """
    if not text:
        return ""
    if text.isascii():
        return text
    res = text.translate(_VI_TRANS_TABLE)
    if not res.isascii():
        nfd = unicodedata.normalize("NFD", res)
        d_mapped = nfd.replace("đ", "d").replace("Đ", "D")
        res = _COMBINING_DIACRITICS_RE.sub("", d_mapped)
    return res



# Re-export IntentResult for backward compatibility
__all__ = [
    "IntentResult",
    "LLMIntentRouter",
    "build_jarvis_system_prompt",
    "generate_tool_schema_from_dispatcher",
]


def _parse_duration_seconds(amount: int, unit_str: str) -> int:
    """Converts quantity and time unit into duration seconds."""
    u = unit_str.lower().strip()
    if u in ("giờ", "tiếng", "h", "hour", "hours", "gio", "tieng"):
        return amount * 3600
    elif u in ("phút", "m", "min", "mins", "minute", "minutes", "phut"):
        return amount * 60
    elif u in ("giây", "s", "sec", "secs", "second", "seconds", "giay"):
        return amount
    return amount * 60


def generate_tool_schema_from_dispatcher(
    dispatcher: ActionDispatcher,
    filter_actions: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Dynamically inspects registered ActionDefinitions in ActionDispatcher and
    generates OpenAI-compliant function call schemas.
    """
    tools = []
    actions = dispatcher.list_actions()

    for name, action_def in actions.items():
        if filter_actions and name not in filter_actions:
            continue

        description = action_def.description or f"Execute action '{name}'."

        # 1. Use explicit schema if provided by plugin
        if action_def.schema and isinstance(action_def.schema, dict):
            parameters = action_def.schema
        else:
            # 2. Dynamic signature introspection
            properties: dict[str, Any] = {}
            required: list[str] = []
            try:
                sig = inspect.signature(action_def.handler)
                for param_name, param in sig.parameters.items():
                    if param_name in ("self", "cls", "kwargs", "args"):
                        continue
                    # Map Python types / string annotations to JSON Schema types
                    ann = param.annotation
                    origin = get_origin(ann)
                    if origin is Union:
                        args = [a for a in get_args(ann) if a is not type(None)]
                        if len(args) == 1:
                            ann = args[0]
                            origin = get_origin(ann)

                    ann_str = ann.__name__ if hasattr(ann, "__name__") else str(ann).lower()

                    param_type = "string"
                    if ann == int or ann_str in ("int", "integer"):
                        param_type = "integer"
                    elif ann == float or ann_str in ("float", "number"):
                        param_type = "number"
                    elif ann == bool or ann_str in ("bool", "boolean"):
                        param_type = "boolean"
                    inner_schema: dict[str, str] = {"type": "string"}
                    if origin in (list, tuple, set) or ann in (list, tuple, set) or ann_str.startswith(("list", "tuple", "set", "typing.list")):
                        param_type = "array"
                        type_args = get_args(ann)
                        if type_args:
                            elem_type = type_args[0]
                            elem_str = getattr(elem_type, "__name__", str(elem_type)).lower()
                            if elem_type == int or elem_str in ("int", "integer"):
                                inner_schema = {"type": "integer"}
                            elif elem_type == float or elem_str in ("float", "number"):
                                inner_schema = {"type": "number"}
                            elif elem_type == bool or elem_str in ("bool", "boolean"):
                                inner_schema = {"type": "boolean"}
                        elif "[" in ann_str and ann_str.endswith("]"):
                            inner_name = ann_str[ann_str.index("[") + 1 : -1].strip().lower()
                            if inner_name in ("int", "integer"):
                                inner_schema = {"type": "integer"}
                            elif inner_name in ("float", "number"):
                                inner_schema = {"type": "number"}
                            elif inner_name in ("bool", "boolean"):
                                inner_schema = {"type": "boolean"}
                    elif origin in (dict, dict) or ann in (dict, dict) or ann_str.startswith("dict") or ann_str.startswith("typing.dict"):
                        param_type = "object"
                    elif "list" in ann_str and "dict" not in ann_str:
                        param_type = "array"
                    elif "dict" in ann_str:
                        param_type = "object"

                    prop_def: dict[str, Any] = {
                        "type": param_type,
                        "description": f"Parameter {param_name}",
                    }
                    if param_type == "array":
                        prop_def["items"] = inner_schema

                    properties[param_name] = prop_def
                    if param.default == inspect.Parameter.empty:
                        required.append(param_name)
            except Exception as e:
                logger.debug("Failed to inspect signature for action %s: %s", name, e)

            parameters = {
                "type": "object",
                "properties": properties,
                "required": required,
            }

        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            }
        })

    return tools


def build_jarvis_system_prompt(
    context_info: dict[str, Any] | None = None,
    language: str = "vi",
    memory_context: str | None = None,
) -> str:
    """
    Generates bilingual system prompt embedding JARVIS persona, operating context,
    persistent user memory facts, recent session history, and few-shot tool calling instructions.
    """
    ctx_lines = []
    mem_ctx = memory_context
    if context_info:
        for k, v in context_info.items():
            if k in ("memory_context", "memory") and not mem_ctx and isinstance(v, str):
                mem_ctx = v
            else:
                ctx_lines.append(f"- {k}: {v}")
    ctx_str = "\n".join(ctx_lines) if ctx_lines else "- Environment: Windows Desktop Assistant"

    memory_section = ""
    if mem_ctx and mem_ctx.strip():
        memory_section = f"\n\n### Persistent Memories & Context:\n{mem_ctx.strip()}"

    prompt = f"""You are JARVIS, an ultra-competent, highly intelligent AI desktop assistant for Windows.
Your persona is inspired by Tony Stark's JARVIS: polite, concise, efficient, courteous ('Sir' or 'Thưa sếp'), and razor-sharp.

### Operational Guidelines:
1. When the user requests an action, ALWAYS call the corresponding function/tool if available.
2. If the user asks a question or has a conversation that requires no tool, reply directly in concise, natural language.
3. Automatically match the user's language: reply in Vietnamese if spoken to in Vietnamese; reply in English if spoken to in English.
4. Keep natural language replies brief (under 2 sentences unless complex explanation is specifically requested).

### System Context:
{ctx_str}{memory_section}

### Few-Shot Tool Calling Examples:
- "bật đèn phòng khách" -> call `home_assistant_call(domain="light", service="turn_on", entity_id="light.living_room")`
- "kiểm tra nhiệt độ cpu" -> call `hardware_telemetry_check(component="cpu")`
- "tình trạng hệ thống" -> call `hardware_status_query()`
- "quét mạng nội bộ" -> call `security_nmap_scan(target="192.168.1.0/24")`
- "mở nhạc spotify" -> call `spotify()`
- "dọn dẹp ram hệ thống" -> call `healing_watchdog_heal()`
- "turn off desk lamp" -> call `home_assistant_call(domain="light", service="turn_off", entity_id="light.desk_lamp")`
- "prepare workspace for AI" -> call `workspace_prepare(recipe="ai_development")`
"""
    return prompt.strip()


class LLMIntentRouter:
    """
    High-Performance Two-Tier Intent Router with Comprehensive Vietnamese Keyword Fallback.
    Tier 1: Sub-millisecond Regex & Keyword Fast Engine.
    Tier 2: LLM Semantic Reasoning with Dynamic Tool Calling.
    Tier 3: Graceful Vietnamese Rule Fallback on network timeout, 429 rate limit, or missing API key.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        dispatcher: ActionDispatcher | None = None,
        fast_path_enabled: bool = True,
        memory_manager: Any | None = None,
    ) -> None:
        self.llm = llm_client
        self.dispatcher = dispatcher
        self.fast_path_enabled = fast_path_enabled
        self.memory_manager = memory_manager
        self._memory_manager = memory_manager

        # Compiled Deterministic Rule Engine for Substring Matching
        self.rule_engine: dict[str, IntentResult] = get_default_rules()

        for intent in self.rule_engine.values():
            intent.parameters = self._catalog_app_parameters(intent.action_name, intent.parameters)

        # Pre-sort rule dictionary keys by descending length for greedy exact match
        self._sorted_rule_keys: list[str] = sorted(self.rule_engine.keys(), key=len, reverse=True)
        self._stripped_rule_keys: dict[str, str] = {
            k: strip_vietnamese_diacritics(k) for k in self.rule_engine
        }
        self._rule_word_counts: dict[str, int] = {
            k: len(k.strip().split()) for k in self.rule_engine
        }
        self._rule_key_regexes: dict[str, re.Pattern] = {}
        self._short_key_regexes: dict[str, re.Pattern] = self._rule_key_regexes

        # Advanced Parametric Regex Rules (Run before static substring fallback)
        self._regex_rules: list[tuple[re.Pattern, Callable[[re.Match], IntentResult]]] = [
            # A specific screen target takes precedence over the relax shortcut.
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:cho\s+)?man\s+hinh\s+(?:pc\s+|may\s+tinh\s+)?nghi\s+ngoi[.!?]?$", re.IGNORECASE),
                lambda m: IntentResult(action_name="system_power", parameters={"action": "screen_off"},
                                       source="rule_fallback", response_text="Đang yêu cầu tắt màn hình."),
            ),
            # Bare note requests carry no content; the handler asks for it.
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:(?:tạo|tao)\s+)?ghi\s+(?:chú|chu)(?:\s+(?:lại|lai|mới|moi))?[.!?]?$", re.IGNORECASE),
                lambda m: IntentResult(action_name="note_add", parameters={"content": ""},
                                       source="rule_fallback", response_text="Bạn muốn ghi chú nội dung gì?"),
            ),
            # 0. Natural Vietnamese Voice Pipeline Patterns (Tuned for Beta v1 Coverage)
            # Exact hardware query: "nhiệt độ" (single command)
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:nhiệt\s*độ|nhiet\s*do)$", re.IGNORECASE),
                lambda m: self._make_hw_intent("cpu"),
            ),
            # Personal Voice Notes: "ghi chú <nội dung>", "lưu ghi chú <nội dung>"
            (
                re.compile(
                    r"^(?:jarvis[,\s]*)?(?:lưu\s*ghi\s*chú|ghi\s*chú|tạo\s*ghi\s*chú|ghi\s*chu|luu\s*ghi\s*chu)\s+(.+)$",
                    re.IGNORECASE,
                ),
                lambda m: IntentResult(
                    action_name="note_add",
                    parameters={"content": m.group(1).strip()},
                    source="rule_fallback",
                    response_text=f"Đã ghi nhận ghi chú cho Ngài: {m.group(1).strip()}",
                ),
            ),
            # Exact system health query: "hệ thống" (single command)
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:hệ\s*thống|he\s*thong)$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="hardware_status_query",
                    parameters={},
                    source="rule_fallback",
                    response_text="Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu, CPU và RAM ở mức an toàn, thưa Ngài.",
                ),
            ),
            # Routine & Recurring Automations
            (
                re.compile(
                    r"^(?:jarvis[,\s]*)?mỗi\s+(\d+)\s*(phút|tiếng|giờ)\s+(?:tự\s+)?(dọn\s*dẹp\s*ram|dọn\s*ram|tự\s*phục\s*hồi|kiểm\s*tra\s*hệ\s*thống)",
                    re.IGNORECASE,
                ),
                lambda m: IntentResult(
                    action_name="routine_schedule",
                    parameters={
                        "interval_seconds": float(m.group(1)) * (3600.0 if "giờ" in m.group(2).lower() or "tiếng" in m.group(2).lower() else 60.0),
                        "action": "healing_watchdog_heal" if "ram" in m.group(3).lower() or "hồi" in m.group(3).lower() else "system_status",
                        "text": f"Lịch tự động mỗi {m.group(1)} {m.group(2)}: {m.group(3)}",
                    },
                    source="rule_fallback",
                    response_text=f"Đã thiết lập lịch tự động mỗi {m.group(1)} {m.group(2)} sẽ {m.group(3)} cho Ngài.",
                ),
            ),
            # Deep Research
            (
                re.compile(
                    r"^(?:jarvis[,\s]*)?(?:nghiên\s*cứu|tìm\s*hiểu\s*sâu|research|phân\s*tích\s*chuyên\s*sâu)\s+(?:về\s+)?(.+)$",
                    re.IGNORECASE,
                ),
                lambda m: IntentResult(
                    action_name="deep_research",
                    parameters={"topic": m.group(1).strip()},
                    source="rule_fallback",
                    response_text=f"Đang tiến hành nghiên cứu đa nguồn về {m.group(1).strip()} cho Ngài.",
                ),
            ),
            # Timer & Alarm
            (
                re.compile(
                    r"(?:đặt\s*báo\s*giờ|hẹn\s*(?:giờ|cho\s*tôi(?:\s*đúng)?)|đếm\s*ngược|cài\s*đặt\s*chuông\s*báo|báo\s*thức\s*(?:cho\s*tôi)?|đặt\s*đồng\s*hồ\s*đếm\s*ngược|cài\s*giờ\s*đếm\s*ngược)\s+(?:sau\s+)?(.+?)(?:phút|tiếng|giờ)",
                    re.IGNORECASE,
                ),
                lambda m: IntentResult(action_name="reminder", parameters={"action": "timer"}, source="rule_fallback", response_text="Đã đặt hẹn giờ cho Ngài."),
            ),
            # Reminder & Scheduling
            (
                re.compile(
                    r"(?:đặt|tạo)\s+(?:lời\s*nhắc|lịch\s*nhắc|nhắc\s*nhở)(?:\s+(.+))?",
                    re.IGNORECASE,
                ),
                lambda m: IntentResult(action_name="reminder", parameters={"message": m.group(1).strip() if m.group(1) else ""}, source="rule_fallback", response_text="Đã ghi nhận lời nhắc cho Ngài."),
            ),
            # Open App expanded
            (
                re.compile(
                    r"^(?:jarvis[,\s]*)?(?:cho\s*tôi\s*vào|cho\s*(?:mình\s*)?(?:vào|chạy)|khởi\s*chạy|mở|bật|chạy|khởi\s*động|vào)\s+"
                    r"(?:ứng\s*dụng\s+)?(?:phần\s*mềm\s+)?(?:trình\s*duyệt|bảng\s*tính|công\s*cụ|app|chương\s*trình)?\s*"
                    r"(?:vẽ|gõ\s*code|gõ\s*văn\s*bản|code|máy\s*tính\s*cầm\s*tay|nghe\s*nhạc)?\s*"
                    r"(cốc\s*cốc|chrome|google\s*chrome|firefox|edge|notepad|calculator|máy\s*tính|word|excel|powerpoint|vscode|vs\s*code|visual\s*studio\s*code|cursor|terminal|powershell|cmd|paint|discord|telegram|zalo|spotify)"
                    r"(?:\s+(?:giúp\s*tôi|hộ\s*tôi|giúp\s*mình|lên|đi|nhé|nha|trên\s*máy|để\s*chat|để\s*dùng))?$",
                    re.IGNORECASE,
                ),
                lambda m: self._make_app_intent(m.group(1)),
            ),
            # Music Play expanded
            (
                re.compile(
                    r"(?:phát|mở|nghe)\s+(?:danh\s*sách\s+)?(?:một\s+)?(?:bài\s*hát|nhạc|bài|giai\s*điệu|playlist)(?:\s+(.+))?",
                    re.IGNORECASE,
                ),
                lambda m: IntentResult(action_name="spotify", parameters={"query": m.group(1).strip() if m.group(1) else ""}, source="rule_fallback", response_text="Đang phát nhạc trên Spotify cho Ngài."),
            ),
            # Screen backlight / screen off
            (
                re.compile(
                    r"(?:tắt|ngắt)\s*(?:đèn\s*nền\s*màn\s*hình|hiển\s*thị\s*màn\s*hình|giao\s*diện\s*màn\s*hình|màn\s*hình(?:\s*làm\s*việc|\s*pc|\s*máy\s*tính)?)|"
                    r"(?:cho\s+)?màn\s*hình\s*(?:pc|máy\s*tính)?\s*(?:chuyển\s*sang\s*chế\s*độ\s*tối|nghỉ\s*ngơi|nghỉ(?:\s*một\s*lúc)?)",
                    re.IGNORECASE,
                ),
                lambda m: IntentResult(action_name="system_power", parameters={"action": "screen_off"}, source="rule_fallback", response_text="Đang tắt màn hình cho Ngài."),
            ),
            # Weather queries expanded
            (
                re.compile(
                    r"(?:nhiệt\s*độ|thời\s*tiết)\s+(?:ở|tại|khu\s*vực)?\s*(hà\s*nội|sài\s*gòn|đà\s*nẵng|hồ\s*chí\s*minh|huế|hải\s*phòng|cần\s*thơ|ngoài\s*trời)(?:\s+(?:hiện\s*tại|lúc\s*này|hôm\s*nay|ngày\s*mai|thế\s*nào|là\s*bao\s*nhiêu))?|"
                    r"(?:xem\s+(?:giúp|giùm|cho)\s*tôi\s+)?thời\s*tiết\s+(?:ở|tại)\s*(.+)|"
                    r"(?:ngoài\s*trời\s+có\s+đang\s+(?:nắng|mưa)|chiều\s*nay\s+có\s+mưa|ra\s*đường\s+có\s+cần\s+mang\s+ô|dự\s*báo\s+mưa\s*bão)",
                    re.IGNORECASE,
                ),
                lambda m: self._make_weather_intent(m.group(1) or m.group(2) or "current"),
            ),
            # Volume control expanded
            (
                re.compile(
                    r"(?:cho\s+)?(?:loa|âm\s*thanh|âm\s*lượng|tiếng)\s+(?:to\s*lên|nhỏ\s*lại|bé\s*lại|phát\s*to|hết\s*cỡ|vừa\s*đủ\s*nghe|hạ\s*xuống)|"
                    r"(?:vặn|chỉnh|hạ|tăng\s*(?:thêm)?|giảm\s*(?:bớt)?|bật\s*(?:lại)?|tắt)\s+(?:bớt\s+)?(?:loa|âm\s*thanh|âm\s*lượng|tiếng)(?:\s+(?:lên\s*mức|xuống\s*mức|về\s*mức|lên|xuống|về|mức|lại))?(?:\s+(?:\d+|năm\s*mươi|ba\s*mươi|thấp\s*nhất|cao\s*nhất))?|"
                    r"(?:tắt\s*hẳn|tắt\s*hết|tắt)\s+(?:âm\s*thanh|tiếng|loa)(?:\s+ngoài)?|"
                    r"(?:vặn\s*nhỏ|bật\s*lại\s*tiếng|tăng\s*thêm\s*âm\s*lượng)",
                    re.IGNORECASE,
                ),
                lambda m: self._make_system_volume_intent(m.group(0)),
            ),
            # Stop / Cancel expanded
            (
                re.compile(
                    r"(?:thôi\s+)?(?:không\s+(?:cần\s+)?làm|hủy\s+(?:bỏ\s+)?(?:thao\s*tác|yêu\s*cầu|lệnh)|ngừng\s+(?:hành\s*động|tác\s*vụ|hoạt\s*động)|bỏ\s*qua\s*(?:lệnh|tác\s*vụ))|"
                    r"^(?:thôi\s+bỏ\s+qua|hủy\s+lệnh|ngừng\s+ngay|dừng\s+ngay|thôi\s+không\s+làm)|"
                    r"^(?:thôi|thoi|dừng|dung|stop|hủy|huy)(?:[,\s]+(?:thôi|thoi|dừng|dung|stop|hủy|huy|ơi))*[!\.\?]?$",
                    re.IGNORECASE,
                ),
                lambda m: IntentResult(action_name="system_power", parameters={"action": "stop"}, source="rule_fallback", response_text="Đã dừng tác vụ cho Ngài."),
            ),
            # Screenshot expanded
            (
                re.compile(
                    r"(?:hãy\s+)?(?:chụp|lưu|bắt|ghi)\s*(?:lại\s+)?(?:toàn\s*bộ\s+|nhanh\s+|bức\s+)?(?:ảnh|hình\s*ảnh|khoảnh\s*khắc)?\s*(?:trên\s+)?(?:màn\s*hình|desktop|giao\s*diện|cửa\s*sổ|vùng\s*hiển\s*thị)|"
                    r"^(?:jarvis[,\s]*)?(?:screen\s*shot|chụp\s*mang\s*hình)$",
                    re.IGNORECASE,
                ),
                lambda m: IntentResult(action_name="screen_capture", parameters={}, source="rule_fallback", response_text="Đang chụp ảnh màn hình cho Ngài."),
            ),
            # Note Taking expanded
            (
                re.compile(
                    r"(?:ghi\s*lại\s+nội\s*dung\s+tóm\s*tắt|tạo\s+(?:một\s+)?(?:bản\s+|trang\s+)?(?:ghi\s*chú|ghi\s*chép)|viết\s+(?:nhanh\s+)?dòng\s*ghi\s*chú|thêm\s+(?:một\s+)?ghi\s*chép|viết\s*lại\s+(?:những\s+điểm|thông\s*tin)|lưu\s*ý\s*tưởng|ghi\s*chép\s*lại)",
                    re.IGNORECASE,
                ),
                lambda m: IntentResult(action_name="skill_note_taker", parameters={"action": "add"}, source="rule_fallback", response_text="Đang lưu ghi chú cho Ngài."),
            ),
            # Settings open expanded
            (
                re.compile(
                    r"(?:mở|bật|vào|cho\s*tôi\s*(?:xem|vào))\s+(?:bảng\s*điều\s*khiển|cửa\s*sổ\s*thiết\s*lập|phần\s*cấu\s*hình|bảng\s*thiết\s*lập|cửa\s*sổ\s*tinh\s*chỉnh|bảng\s*cấu\s*hình|mục\s*thiết\s*lập|trang\s*cài\s*đặt|trang\s*cấu\s*hình)",
                    re.IGNORECASE,
                ),
                lambda m: IntentResult(action_name="app_open", parameters={"app_name": "settings"}, source="rule_fallback", response_text="Đang mở cài đặt hệ thống cho Ngài."),
            ),
            # System Shutdown & Restart expanded
            (
                re.compile(
                    r"(?:cho\s+máy\s*tính\s+(?:ngừng\s*hoạt\s*động|nghỉ\s*ngơi)|đóng\s*nguồn\s*hệ\s*thống|tắt\s*toàn\s*bộ\s*hệ\s*thống|đóng\s*máy\s*lại)",
                    re.IGNORECASE,
                ),
                lambda m: IntentResult(action_name="system_power", parameters={"action": "shutdown"}, source="rule_fallback", response_text="Đang tắt hệ thống cho Ngài."),
            ),
            (
                re.compile(
                    r"(?:bật\s*lại\s*máy\s*tính|reset\s*lại\s*máy\s*tính|cho\s*máy\s*chạy\s*lại\s*hệ\s*thống|restart\s*lại\s*hệ\s*thống)",
                    re.IGNORECASE,
                ),
                lambda m: IntentResult(action_name="system_power", parameters={"action": "restart"}, source="rule_fallback", response_text="Đang khởi động lại hệ thống cho Ngài."),
            ),

            # 1. Smart Home Light Controls (with parameter variations)
            (
                re.compile(r"(?:bật|mở|turn\s*on)\s+(?:đèn|light)(?:\s+(phòng\s*khách|phòng\s*ngủ|bàn|living\s*room|bedroom|desk))?", re.IGNORECASE),
                lambda m: self._make_light_intent("turn_on", m.group(1)),
            ),
            (
                re.compile(r"(?:tắt|turn\s*off)\s+(?:đèn|light)(?:\s+(phòng\s*khách|phòng\s*ngủ|bàn|living\s*room|bedroom|desk))?", re.IGNORECASE),
                lambda m: self._make_light_intent("turn_off", m.group(1)),
            ),
            # Fan Controls
            (
                re.compile(r"(?:bật|mở|turn\s*on)\s+(?:quạt|fan)(?:\s+(phòng\s*khách|phòng\s*ngủ|trần|living\s*room|bedroom))?", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="home_assistant_call",
                    parameters={"domain": "fan", "service": "turn_on", "entity_id": "fan.living_room"},
                    source="rule_fallback",
                    response_text="Đang bật quạt cho Ngài.",
                ),
            ),
            (
                re.compile(r"(?:tắt|turn\s*off)\s+(?:quạt|fan)(?:\s+(phòng\s*khách|phòng\s*ngủ|trần|living\s*room|bedroom))?", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="home_assistant_call",
                    parameters={"domain": "fan", "service": "turn_off", "entity_id": "fan.living_room"},
                    source="rule_fallback",
                    response_text="Đang tắt quạt cho Ngài.",
                ),
            ),
            # Climate Controls & Set Temperature
            (
                re.compile(r"(?:đặt|chỉnh|set)\s*(?:nhiệt\s*độ|điều\s*hòa|máy\s*lạnh|temp|temperature)\s*(?:sang|lên|xuống|ở\s*mức)?\s*(\d{1,2}(?:\.\d+)?)\s*(?:độ|c|degree)?", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="home_assistant_call",
                    parameters={"domain": "climate", "service": "set_temperature", "entity_id": "climate.ac_unit", "temperature": float(m.group(1))},
                    source="rule_fallback",
                    response_text=f"Đã đặt nhiệt độ điều hòa thành {m.group(1)} độ cho Ngài.",
                ),
            ),
            (
                re.compile(r"(?:bật|mở|turn\s*on)\s+(?:điều\s*hòa|máy\s*lạnh|ac|climate)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="home_assistant_call",
                    parameters={"domain": "climate", "service": "turn_on", "entity_id": "climate.ac_unit"},
                    source="rule_fallback",
                    response_text="Đang bật điều hòa cho Ngài.",
                ),
            ),
            (
                re.compile(r"(?:tắt|turn\s*off)\s+(?:điều\s*hòa|máy\s*lạnh|ac|climate)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="home_assistant_call",
                    parameters={"domain": "climate", "service": "turn_off", "entity_id": "climate.ac_unit"},
                    source="rule_fallback",
                    response_text="Đang tắt điều hòa cho Ngài.",
                ),
            ),
            # 2. Hardware / Telemetry / Diagnostics
            (
                re.compile(r"(?:kiểm\s*tra|kiem\s*tra|check|query|xem|báo\s*cáo|bao\s*cao)?\s*(?:(?:(cpu|gpu|ram|ổ\s*cứng|o\s*cung|disk|bộ\s*nhớ|bo\s*nho|pin|battery)\s+(?:nhiệt\s*độ|nhiet\s*do|temp|temperature|mức\s*sử\s*dụng|mấy\s*phần\s*trăm|tốc\s*độ|còn\s*bao\s*nhiêu|còn\s*lại\s*bao\s*nhiêu|tình\s*trạng|tinh\s*trang|dung\s*lượng))|(?:(?:nhiệt\s*độ|nhiet\s*do|temp|temperature|mức\s*sử\s*dụng|mấy\s*phần\s*trăm|tốc\s*độ|còn\s*bao\s*nhiêu|còn\s*lại\s*bao\s*nhiêu|dung\s*lượng)\s+(cpu|gpu|ram|ổ\s*cứng|o\s*cung|disk|bộ\s*nhớ|bo\s*nho|pin|battery|máy|laptop|pc|thiết\s*bị)))", re.IGNORECASE),
                lambda m: self._make_hw_intent((m.group(1) or m.group(2) or "cpu").lower()),
            ),
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:kiểm\s*tra|kiem\s*tra|xem|check)\s+(cpu|gpu|ram|disk|ổ\s*cứng|o\s*cung|bộ\s*nhớ|bo\s*nho|pin|battery)$", re.IGNORECASE),
                lambda m: self._make_hw_intent(m.group(1)),
            ),
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:pin\s*còn\s*bao\s*nhiêu|dung\s*lượng\s*pin|mức\s*pin|kiem\s*tra\s*pin|pin\s*mấy\s*phần\s*trăm|pin)$", re.IGNORECASE),
                lambda m: self._make_hw_intent("battery"),
            ),
            (
                re.compile(r"(?:tình\s*trạng|trạng\s*thái|tinh\s*trang|trang\s*thai|status|health)\s*(?:hệ\s*thống|máy\s*tính|he\s*thong|may\s*tinh|system|pc|máy|may|hardware)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="hardware_status_query",
                    parameters={},
                    source="rule_fallback",
                    response_text="Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu, CPU và RAM ở mức an toàn, thưa Ngài.",
                ),
            ),

            # 3. Spotify & Music (Specific Song Queries & Playback Controls)
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:mở|bật|phát|nghe|mo|bat|phat|nghe|play|launch)\s+(?:spotify\s*(?:bài|bài\s*hát|bai|song)?|nhạc|nhac|bài\s*hát|bai\s*hat|bài|bai|music|song)(?:\s+(.+))?$", re.IGNORECASE),
                lambda m: (
                    (lambda raw_q: (
                        (lambda yt_m: IntentResult(
                            action_name="web_open",
                            parameters={
                                "target": f"https://www.youtube.com/results?{urlencode({'search_query': yt_m.group(1).strip()})}",
                                "site": "youtube",
                                "query": yt_m.group(1).strip(),
                            },
                            source="rule_fallback",
                            response_text=f"Đang mở '{yt_m.group(1).strip()}' trên YouTube cho Ngài.",
                        ))(re.match(r"^(.+?)\s+(?:trên|ở|qua|tai|tại)\s+(?:youtube|yt)$", raw_q, re.IGNORECASE))
                        if re.search(r"\b(?:trên|ở|qua|tai|tại)\s+(?:youtube|yt)$", raw_q, re.IGNORECASE)
                        else IntentResult(
                            action_name="spotify",
                            parameters={"query": raw_q} if raw_q else {"command": "play", "query": ""},
                            source="rule_fallback",
                            response_text=f"Đang mở Spotify và phát {raw_q} cho Ngài." if raw_q else "Đang mở Spotify và phát nhạc cho Ngài.",
                        )
                    ))(re.sub(r"^(?:bài\s*hát|bai\s*hat|bài|bai|song)\s+", "", m.group(1).strip(), flags=re.IGNORECASE) if (m.lastindex and m.group(1) and m.group(1).strip()) else "")
                ),
            ),
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:bật\s*nhạc\s*lên|bat\s*nhac\s*len|phát\s*nhạc\s*đi|phat\s*nhac\s*di|\bspotify\b)$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="spotify",
                    parameters={"query": "", "name": "spotify"},
                    source="rule_fallback",
                    response_text="Đang mở Spotify cho Ngài.",
                ),
            ),
            # H-07 fix: bare "settings" (English, no diacritics) said ALONE
            # is a legitimate one-word command (mirrors the bare "spotify"
            # anchored regex immediately above, and "cai dat"/"cài đặt" alone
            # already worked via their own multi-word dict entries) -- but it
            # must be ANCHORED to the full utterance so it can never match a
            # question/statement that merely CONTAINS the word "settings"
            # (e.g. "settings nghĩa là gì" must not launch Settings). This is
            # the safe replacement for the whole-word-but-unanchored dict key
            # removed above.
            (
                re.compile(r"^(?:jarvis[,\s]*)?settings$", re.IGNORECASE),
                lambda m: self._make_app_intent("settings"),
            ),
            (
                re.compile(r"(?:dừng|tạm\s*dừng|tắt|pause|stop)\s+(?:nhạc|spotify|phát\s*nhạc)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="spotify",
                    parameters={"command": "pause"},
                    source="rule_fallback",
                    response_text="Đã tạm dừng phát nhạc, thưa Ngài.",
                ),
            ),
            (
                re.compile(r"(?:chuyển|tiếp\s*theo|next)\s+(?:bài|bài\s*hát|song|track)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="spotify",
                    parameters={"command": "next"},
                    source="rule_fallback",
                    response_text="Đang chuyển bài tiếp theo, thưa Ngài.",
                ),
            ),

            # 4. Weather
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:dự\s*báo|du\s*bao|xem|kiểm\s*tra|kiem\s*tra)?\s*(?:thời\s*tiết|thoi\s*tiet|weather|trời|troi)\s*(?:hôm\s*nay|hom\s*nay|ngày\s*mai|ngay\s*mai|hiện\s*tại|today|forecast|tại|ở|khu\s*vực)?\s*(.*)$", re.IGNORECASE),
                lambda m: self._make_weather_intent(m.group(1) if m.group(1) else ""),
            ),
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:nhiệt\s*độ|nhiet\s*do)\s+(?:ngoài\s*trời|hôm\s*nay|hom\s*nay|ngày\s*mai|ngay\s*mai|hiện\s*tại|today|tại|ở)\s*(.*)$", re.IGNORECASE),
                lambda m: self._make_weather_intent(m.group(1) if m.group(1) else ""),
            ),
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:bao\s*nhiêu\s*độ|bao\s*nhieu\s*do|nhiệt\s*độ\s*bao\s*nhiêu)$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="shell_exec",
                    parameters={"command": "curl -s wttr.in?format=3", "topic": "weather", "location": "current"},
                    source="rule_fallback",
                    response_text="Đang kiểm tra nhiệt độ hiện tại cho Ngài.",
                ),
            ),

            # 5. Reminder & Alarms (Duration, Clock Time, Custom Message)
            (
                re.compile(r"(?:nhắc\s*nhở|nhắc\s*tôi|remind\s*me|reminder)\s+(?:sau|trong\s*vòng)\s+(\d+)\s*(phút|giờ|tiếng|giây|s|m|h)\s*(?:để|về|là)?\s*(.*)", re.IGNORECASE),
                lambda m: self._make_reminder_duration_intent(int(m.group(1)), m.group(2), m.group(3)),
            ),
            (
                re.compile(r"(?:nhắc\s*nhở|nhắc\s*tôi|remind\s*me|reminder)\s+(.+?)\s+(?:sau|trong\s*vòng)\s+(\d+)\s*(phút|giờ|tiếng|giây|s|m|h)", re.IGNORECASE),
                lambda m: self._make_reminder_duration_intent(int(m.group(2)), m.group(3), m.group(1)),
            ),
            (
                re.compile(r"(?:nhắc\s*nhở|nhắc\s*tôi|remind\s*me|reminder)\s+(.+?)\s+(?:lúc|vào\s*lúc)\s*(.+)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="reminder",
                    parameters={"message": m.group(1).strip(), "time_str": m.group(2).strip()},
                    source="rule_fallback",
                    response_text=f"Đã ghi nhận lời nhắc '{m.group(1).strip()}' vào lúc {m.group(2).strip()} của Ngài.",
                ),
            ),
            (
                re.compile(r"^(?:jarvis\s*,?\s*)?(?:nhắc\s*nhở|nhắc\s*tôi|remind\s*me|reminder)\s+(.+)$", re.IGNORECASE),
                lambda m: self._make_reminder_custom_intent(m.group(1)),
            ),

            # 6. System Power
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:tắt\s*máy|shutdown|shut\s*down|power\s*off|turn\s*off\s*computer|tắt\s*máy\s*tính|tắt\s*nguồn|tat\s*may|tat\s*may\s*tinh|tat\s*nguon|tat\s*may\s*di|\btắt\b|\btat\b)$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="system_power",
                    parameters={"action": "shutdown"},
                    source="rule_fallback",
                    response_text="Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận để thực thi nhằm đảm bảo an toàn dữ liệu, thưa Ngài.",
                    requires_confirmation=True,
                    confirmation_prompt="Ngài có chắc chắn muốn tắt máy không?",
                    danger_level="CRITICAL",
                ),
            ),
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:khởi\s*động\s*lại|khoi\s*dong\s*lai|restart|reboot|restart\s*máy|restart\s*may|restart\s*windows|khoi\s*dong\s*lai\s*may)$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="system_power",
                    parameters={"action": "restart"},
                    source="rule_fallback",
                    response_text="Lệnh khởi động lại hệ thống đã được ghi nhận. Vui lòng xác nhận, thưa Ngài.",
                    requires_confirmation=True,
                    confirmation_prompt="Ngài có chắc chắn muốn khởi động lại máy không?",
                    danger_level="CRITICAL",
                ),
            ),
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:dừng\s*lại|dừng|dung\s*lai|dung|stop|thôi|thoi|hủy|huy|cancel|abort)$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="system_power",
                    parameters={"action": "lock"},
                    source="rule_fallback",
                    response_text="Đã dừng phiên làm việc và khóa màn hình, thưa Ngài.",
                ),
            ),
            (
                re.compile(r"(?:chế\s*độ\s*ngủ|sleep\s*pc|đi\s*ngủ)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="system_power",
                    parameters={"action": "sleep"},
                    source="rule_fallback",
                    response_text="Đang đưa hệ thống vào chế độ ngủ tiết kiệm điện năng, thưa Ngài.",
                    requires_confirmation=True,
                    confirmation_prompt="Ngài có muốn đưa hệ thống vào chế độ ngủ không?",
                    danger_level="MEDIUM",
                ),
            ),
            # Project & Workspace Management
            (
                re.compile(
                    r"^(?:jarvis[,\s]*)?(?:mở|mo|chuyển\s*(?:sang)?|chuyen\s*(?:sang)?|switch\s*(?:to|sang)?|open)\s+(?:dự\s*án|du\s*an|project|workspace|không\s*gian\s*làm\s*việc)(?:\s+(.+))?$",
                    re.IGNORECASE,
                ),
                lambda m: self._make_workspace_intent("open", m.group(1)),
            ),
            (
                re.compile(
                    r"^(?:jarvis[,\s]*)?(?:chuyển\s+sang|chuyen\s+sang|switch\s+(?:to|sang))\s+(?:dự\s*án|du\s*an|project|workspace)(?:\s+(.+))?$",
                    re.IGNORECASE,
                ),
                lambda m: self._make_workspace_intent("open", m.group(1)),
            ),
            (
                re.compile(
                    r"^(?:jarvis[,\s]*)?(?:tạo|tao|khởi\s*tạo|khoi\s*tao|create|new)\s+(?:dự\s*án|du\s*an|project|workspace)(?:\s+(.*))?$",
                    re.IGNORECASE,
                ),
                lambda m: self._make_workspace_intent("create", m.group(1)),
            ),
            (
                re.compile(
                    r"^(?:jarvis[,\s]*)?(?:xem\s+|kiểm\s*tra\s+|kiem\s*tra\s+)?(?:liệt\s*kê|liet\s*ke|danh\s*sách|danh\s*sach|show|list|các|cac)\s+(?:dự\s*án|du\s*an|project|workspace|projects|workspaces)(?:\s+(?:đang\s*có|hiện\s*có|available|mới\s*nhất))?$",
                    re.IGNORECASE,
                ),
                lambda m: self._make_workspace_intent("list", None),
            ),
            (
                re.compile(r"(?:chuẩn\s*bị|mở|prepare)\s*(?:môi\s*trường|workspace|work\s*environment)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="workspace_prepare",
                    parameters={"recipe": "ai_development"},
                    source="rule_fallback",
                    response_text="Đang chuẩn bị môi trường làm việc cho Ngài.",
                ),
            ),
            # 7. Universal Application & Software Launchers
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:mở|bật|chạy|khởi\s*động|mo|bat|chay|khoi\s*dong|open|launch|start)(?:\s+(?:ứng\s*dụng|app|phần\s*mềm|chương\s*trình|ung\s*dung|phan\s*mem))?\s+(chrome|google\s*chrome|cốc\s*cốc|firefox|edge|notepad|sổ\s*tay|ghi\s*chú|calculator|máy\s*tính|calc|word|ms\s*word|excel|ms\s*excel|bảng\s*tính|powerpoint|ppt|vscode|vs\s*code|visual\s*studio\s*code|cursor|cursor\s*ai|task\s*manager|quản\s*lý\s*tác\s*vụ|taskmgr|terminal|powershell|cmd|dòng\s*lệnh|paint|vẽ|spotify|discord|telegram|zalo|cài\s*đặt|cai\s*dat|settings|explorer|file\s*explorer|quản\s*lý\s*file|obsidian|notion|slack|zoom|teams|microsoft\s*teams|winrar|7zip|vlc|media\s*player|gimp|photoshop|figma|postman|docker|git|github\s*desktop|obs|audacity)$", re.IGNORECASE),
                lambda m: self._make_app_intent(m.group(1)),
            ),
            # 8. Universal Website & Online Service Launchers (bật/mở/vào/truy cập)
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:mở|mo|vào|vao|truy\s*cập|open|visit|go\s*to)\s+(https?://\S+)$", re.IGNORECASE),
                lambda m: self._make_web_intent(m.group(1), None),
            ),
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:cho\s+(?:tao|tôi|mình|t)\s+|giúp\s+(?:tao|tôi|mình)\s+|hãy\s+|đi\s+)?(?:mở\s+xem|bật\s+xem|vào\s+xem|mo\s+xem|bat\s+xem|vao\s+xem|mở|bật|vào|xem|truy\s*cập|mo|bat|vao|truy\s*cap|open|watch|visit|go\s*to|launch|start)(?:\s+(?:trang\s*web|web|website|trang))?\s*(youtube|yt|google|gg|facebook|fb|github|gh|chatgpt|gpt|chat\s*gpt|claude|claude\s*ai|anthropic|binance|zalo\s*web|gmail|mail|email|hòm\s*thư|vnexpress|báo|dantri|dân\s*trí|shopee|tiki|lazada|reddit|twitter|maps|bản\s*đồ|dịch|translate|google\s*dịch|notion|figma|canva|trello|jira|confluence|[\w\-]+(?:\.com|\.vn|\.net|\.org|\.io|\.edu))(?:\s+(.*))?$", re.IGNORECASE),
                lambda m: self._make_web_intent(m.group(1), m.group(2)),
            ),
            # 8a1. Specific YouTube Video/Music Search Intent ("xem video X trên youtube", "bật bài hát Y trên youtube")
            (
                re.compile(
                    r"^(?:jarvis[,\s]*)?(?:cho\s+(?:tao|tôi|mình|t)\s+|giúp\s+(?:tao|tôi|mình)\s+|hãy\s+|đi\s+)?"
                    r"(?:mở\s+xem|bật\s+xem|vào\s+xem|mở|bật|vào|xem|phát|play|tìm|tra\s*cứu|search|chạy|mo|bat|vao|phat|tim)\s+"
                    r"(?:video|clip|bài\s*hát|bai\s*hat|bài|bai|nhạc|nhac|phim|kênh|kenh)?\s*"
                    r"(.+?)\s+(?:trên|ở|qua|tai|tại|tren|o)\s+(?:youtube|yt)$",
                    re.IGNORECASE,
                ),
                lambda m: IntentResult(
                    action_name="web_open",
                    parameters={
                        "target": f"https://www.youtube.com/results?{urlencode({'search_query': m.group(1).strip()})}",
                        "site": "youtube",
                        "query": m.group(1).strip(),
                    },
                    source="rule_fallback",
                    response_text=f"Đang mở '{m.group(1).strip()}' trên YouTube cho Ngài.",
                ),
            ),
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:youtube|yt)\s+(.+)$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="web_open",
                    parameters={
                        "target": f"https://www.youtube.com/results?{urlencode({'search_query': m.group(1).strip()})}",
                        "site": "youtube",
                        "query": m.group(1).strip(),
                    },
                    source="rule_fallback",
                    response_text=f"Đang tìm '{m.group(1).strip()}' trên YouTube cho Ngài.",
                ),
            ),
            # 8b. File Search
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:tìm\s*file|tim\s*file|search\s*file|find\s*file)\s*(.*)$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="file_search",
                    parameters={"action": "search", "query": m.group(1).strip() if (m.lastindex and m.group(1)) else ""},
                    source="rule_fallback",
                    response_text=f"Đang tìm kiếm file '{m.group(1).strip()}' cho Ngài." if (m.lastindex and m.group(1) and m.group(1).strip()) else "Đang tìm kiếm file cho Ngài.",
                ),
            ),

            # 9. Web Search & Query
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:tìm\s*kiếm|search|tra\s*cứu|tìm|tim\s*kiem|tim)\s+(.+?)(?:\s+(?:trên|ở|qua)\s+(?:google|web|mạng|internet|youtube))?$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="web_open",
                    parameters={"query": m.group(1).strip(), "target": "https://www.google.com/search?" + urlencode({"q": m.group(1).strip()})},
                    source="rule_fallback",
                    response_text=f"Đang tìm kiếm '{m.group(1).strip()}' trên Google cho Ngài.",
                ),
            ),
            (
                re.compile(r"^(?:jarvis[,\s]*)?google\s+(.+)$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="web_open",
                    parameters={"query": m.group(1).strip(), "target": "https://www.google.com/search?" + urlencode({"q": m.group(1).strip()})},
                    source="rule_fallback",
                    response_text=f"Đang tìm kiếm '{m.group(1).strip()}' trên Google cho Ngài.",
                ),
            ),
            # 10. Folder & Storage Navigation
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:mở|mo|open)\s+(?:thư\s*mục|thu\s*muc|folder|ổ|o|mục|muc)\s*(.+)?$", re.IGNORECASE),
                lambda m: self._make_folder_intent(m.group(1) if (m.lastindex and m.group(1)) else "documents"),
            ),
            # 11. Window & Screen Management
            (
                re.compile(r"^(?:thu\s*nhỏ|ẩn|minimize)\s+(?:tất\s*cả|cửa\s*sổ|hết|desktop|màn\s*hình)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="window_minimize_all",
                    parameters={},
                    source="rule_fallback",
                    response_text="Đã thu nhỏ tất cả các cửa sổ xuống màn hình Desktop, thưa Ngài.",
                ),
            ),
            (
                re.compile(r"^(?:đóng|tắt|close)\s+(?:cửa\s*sổ|tab|tab\s*này|cửa\s*sổ\s*này|ứng\s*dụng\s*này)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="window_active",
                    parameters={"action": "close"},
                    source="rule_fallback",
                    response_text="Đang đóng cửa sổ hiện tại cho Ngài.",
                ),
            ),
            (
                re.compile(r"^(?:chụp|chụp\s*ảnh|screenshot|capture|chup|chup\s*anh)\s*(?:màn\s*hình|desktop|man\s*hinh)?$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="screen_capture",
                    parameters={},
                    source="rule_fallback",
                    response_text="Đã chụp ảnh màn hình và lưu ra Desktop cho Ngài.",
                ),
            ),
            # 12. Volume & Brightness Quick Controls
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:tăng|mở\s*to|tang|mo\s*to)\s*âm\s*lượng(?:\s+(?:lên)?\s*(\d+))?|^(?:volume\s*up)$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="system_volume",
                    parameters={"delta": int(m.group(1)) if (m.lastindex and m.group(1)) else 10},
                    source="rule_fallback",
                    response_text="Đang tăng âm lượng hệ thống cho Ngài.",
                ),
            ),
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:giảm|mở\s*nhỏ|giam|mo\s*nho)\s*âm\s*lượng(?:\s+(?:xuống)?\s*(\d+))?|^(?:volume\s*down)$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="system_volume",
                    parameters={"delta": -(int(m.group(1)) if (m.lastindex and m.group(1)) else 10)},
                    source="rule_fallback",
                    response_text="Đang giảm âm lượng hệ thống cho Ngài.",
                ),
            ),
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:tắt\s*tiếng|tat\s*tieng|mute|bật\s*tiếng|bat\s*tieng|unmute|điều\s*chỉnh\s*âm\s*lượng|dieu\s*chinh\s*am\s*luong|giảm\s*âm|giam\s*am)$", re.IGNORECASE),
                # H-08 fix: previously used `"mute" in m.group(0).lower()`,
                # a raw substring check that misclassified "unmute" as a
                # MUTE request (the literal substring "mute" occurs inside
                # "unmute") and never produced {"mute": False} for any
                # alternative at all. _make_system_volume_intent() uses
                # exact whole-token matching instead, so "unmute"/"bật
                # tiếng"/"bat tieng" correctly resolve to {"mute": False}.
                lambda m: self._make_system_volume_intent(m.group(0)),
            ),
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:tăng|tang)\s*(?:độ\s*sáng|do\s*sang)(?:\s+(?:lên)?\s*(\d+))?|^(?:brightness\s*up)$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="system_brightness",
                    parameters={"delta": int(m.group(1)) if (m.lastindex and m.group(1)) else 10},
                    source="rule_fallback",
                    response_text="Đang tăng độ sáng màn hình cho Ngài.",
                ),
            ),
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:giảm|giam)\s*(?:độ\s*sáng|do\s*sang)(?:\s+(?:xuống)?\s*(\d+))?|^(?:brightness\s*down)$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="system_brightness",
                    parameters={"delta": -(int(m.group(1)) if (m.lastindex and m.group(1)) else 10)},
                    source="rule_fallback",
                    response_text="Đang giảm độ sáng màn hình cho Ngài.",
                ),
            ),
            # 12b. Set volume to exact percent — "âm lượng 50", "volume 70%"
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:(?:đặt|dat|set)\s+)?(?:âm\s*lượng|am\s*luong|volume)\s+(\d{1,3})\s*%?$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="system_volume",
                    parameters={"level": min(100, max(0, int(m.group(1))))},
                    source="rule_fallback",
                    response_text=f"Đang đặt âm lượng {m.group(1)}% cho Ngài.",
                ),
            ),
            # 12c. Date and time queries
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:mấy|may|bao\s*nhiêu|bao\s*nhieu)\s+giờ(?:\s+rồi)?|^(?:xem\s+giờ|hỏi\s+giờ|giờ\s+(?:hiện\s+tại|mấy\s+giờ))", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="shell_exec",
                    parameters={"command": "powershell -c \"(Get-Date).ToString('HH:mm:ss dddd dd/MM/yyyy')\"", "topic": "time"},
                    source="rule_fallback",
                    response_text="Đang kiểm tra giờ hiện tại cho Ngài.",
                ),
            ),
            (
                re.compile(r"^(?:jarvis[,\s]*)?hôm\s*nay\s+(?:là\s+)?(?:thứ|ngày)\s+(?:mấy|may)|^(?:hôm\s*nay\s+ngày\s+mấy|ngày\s+(?:hôm\s+nay|này))", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="shell_exec",
                    parameters={"command": "powershell -c \"(Get-Date).ToString('dddd, dd/MM/yyyy')\"", "topic": "date"},
                    source="rule_fallback",
                    response_text="Đang kiểm tra ngày hôm nay cho Ngài.",
                ),
            ),
            # 12d. Crypto price quick-search
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:giá|gia|xem\s+giá|gia\s+coin|coin)\s+(bitcoin|btc|ethereum|eth|bnb|sol|solana|usdt|xrp|ada|doge|[\w]+)(?:\s+hôm\s+nay)?", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="web_open",
                    parameters={"target": f"https://www.google.com/search?q=giá+{m.group(1)}+hôm+nay", "site": "google"},
                    source="rule_fallback",
                    response_text=f"Đang tra giá {m.group(1).upper()} cho Ngài.",
                ),
            ),
            # 13. News & Morning Briefing
            (
                re.compile(r"(?:briefing\s*(?:sáng|hôm\s*nay)?|báo\s*cáo\s*sáng|tổng\s*hợp\s*sáng|điểm\s*tin\s*sáng|morning\s*briefing|báo\s*cáo\s*buổi\s*sáng|bao\s*cao\s*buoi\s*sang|thông\s*tin\s*buổi\s*sáng|thong\s*tin\s*buoi\s*sang)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="morning_briefing",
                    parameters={},
                    source="rule_fallback",
                    response_text="Đang tổng hợp báo cáo buổi sáng cho Ngài.",
                ),
            ),
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:đọc|doc|xem)?\s*(?:tin\s*tức|tin\s*tuc|bản\s*tin|tin\s*mới|điểm\s*tin|thời\s*sự|tin\s*nóng|headlines|latest\s*news)(?:\s+(.+))?$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="news_headlines",
                    parameters={"topic": "general"},
                    source="rule_fallback",
                    response_text="Đang cập nhật tin tức cho Ngài.",
                ),
            ),

            # 14. Memory Facts & Daily Summary
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:nhớ\s*cho\s*tôi|nho\s*cho\s*toi|nhớ\s*rằng|nho\s*rang|lưu\s*lại|luu\s*lai|save\s*this|remember\s*this)\s*[:,\s]?\s*(.*)$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="memory_save_fact",
                    parameters={"fact": m.group(1).strip()} if (m.lastindex and m.group(1)) else {},
                    source="rule_fallback",
                    response_text="Đã ghi nhớ thông tin này cho Ngài.",
                ),
            ),
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:tóm\s*tắt\s*hôm\s*nay|tom\s*tat\s*hom\s*nay|tổng\s*kết\s*ngày|summarize\s*today|daily\s*summary)$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="memory_summarize_daily",
                    parameters={},
                    source="rule_fallback",
                    response_text="Đang tóm tắt hoạt động trong ngày hôm nay cho Ngài.",
                ),
            ),

            # 15. Built-in Skills Fast-Path Patterns
            (
                re.compile(r"(?:bắt\s*đầu\s*pomodoro|chế\s*độ\s*tập\s*trung|start\s*pomodoro|focus\s*mode)(?:\s+(\d+)\s*(?:phút|m|mins))?", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="skill_pomodoro",
                    parameters={"action": "start", "duration_minutes": int(m.group(1)) if m.group(1) else 25},
                    source="rule_fallback",
                    response_text="Bắt đầu phiên làm việc tập trung Pomodoro cho Ngài.",
                ),
            ),
            (
                re.compile(r"(?:ghi\s*chú(?:\s*nhanh)?|lưu\s*ghi\s*chú|take\s*note|add\s*note)\s*[:,\s]\s*(.+)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="skill_note_taker",
                    parameters={"action": "add", "content": m.group(1).strip()},
                    source="rule_fallback",
                    response_text=f"Đã lưu ghi chú cho Ngài: {m.group(1).strip()}",
                ),
            ),
            (
                re.compile(r"^(?:tính|tinh|calculate|eval)\s+([\d\s\+\-\*\/\^\(\)\.\%xX\w]+)$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="skill_calculator",
                    parameters={"action": "eval", "expression": m.group(1).strip()},
                    source="rule_fallback",
                    response_text="Đang tính toán biểu thức cho Ngài.",
                ),
            ),
            (
                re.compile(r"(?:đổi|chuyển\s*đổi)\s+(\d+(?:\.\d+)?)\s*(usd|vnd|eur|jpy|gbp)\s*(?:sang|qua|to)\s*(vnd|usd|eur|jpy|gbp)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="skill_calculator",
                    parameters={
                        "action": "convert_currency",
                        "amount": float(m.group(1)),
                        "currency_from": m.group(2).upper(),
                        "currency_to": m.group(3).upper(),
                    },
                    source="rule_fallback",
                    response_text="Đang quy đổi tỷ giá tiền tệ cho Ngài.",
                ),
            ),
            # 16. Git Operations & Repository Controls
            (
                re.compile(
                    r"^(?:jarvis[,\s]*)?git\s+(status|commit|push|log|branch|diff)(?:\s+(?:dự\s*án|du\s*an|project|workspace|repo))?(?:\s+(.+))?$",
                    re.IGNORECASE,
                ),
                lambda m: self._make_git_project_intent(m.group(1), m.group(2)),
            ),
            (
                re.compile(
                    r"^(?:jarvis[,\s]*)?(commit|push)\s+(?:dự\s*án|du\s*an|project|workspace|code|repo)(?:\s+(.+))?$",
                    re.IGNORECASE,
                ),
                lambda m: self._make_git_project_intent(m.group(1), m.group(2)),
            ),
            (
                re.compile(
                    r"^(?:jarvis[,\s]*)?(?:kiểm\s*tra|kiem\s*tra|trạng\s*thái|trang\s*thai|lịch\s*sử|nhánh)\s+git\s+(?:dự\s*án|du\s*an|project|workspace)?(?:\s+(.+))?$",
                    re.IGNORECASE,
                ),
                lambda m: self._make_git_project_intent("status" if "kiểm" in m.group(0).lower() or "kiem" in m.group(0).lower() or "trạng" in m.group(0).lower() or "trang" in m.group(0).lower() else ("log" if "lịch" in m.group(0).lower() else "branch"), m.group(1)),
            ),
            (
                re.compile(
                    r"^(?:jarvis[,\s]*)?(?:git\s*status|kiểm\s*tra\s*git|trạng\s*thái\s*git)(?:\s+(?:dự\s*án|du\s*an|project|workspace))?(?:\s+(.+))?$",
                    re.IGNORECASE,
                ),
                lambda m: self._make_git_project_intent("status", m.group(1)),
            ),
            (
                re.compile(r"(?:chụp\s*ảnh\s*màn\s*hình|chụp\s*màn\s*hình|take\s*screenshot)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="screen_capture",
                    parameters={"action": "screenshot"},
                    source="rule_fallback",
                    response_text="Đang chụp ảnh màn hình và lưu vào Desktop cho Ngài.",
                ),
            ),
            (
                re.compile(r"(?:hiển\s*thị\s*desktop|màn\s*hình\s*chính|thu\s*nhỏ\s*tất\s*cả|show\s*desktop|minimize\s*all)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="skill_system_control",
                    parameters={"action": "show_desktop"},
                    source="rule_fallback",
                    response_text="Đã hiển thị màn hình nền Desktop cho Ngài.",
                ),
            ),
            # 17. Security Network / Nmap Scan
            (
                re.compile(
                    r"^(?:jarvis[,\s]*)?(?:scan\s+(?:network|subnet|ip)|quet\s+(?:mang|dải\s*mạng|dai\s*mang|ip|mạng\s*nội\s*bộ|mang\s*noi\s*bo)|quét\s+(?:mạng|dải\s*mạng|dai\s*mang|ip|mạng\s*nội\s*bộ|mang\s*noi\s*bo)|nmap(?:\s+scan)?)\s+([\d\.\/\:]+)",
                    re.IGNORECASE,
                ),
                lambda m: IntentResult(
                    action_name="security_nmap_scan",
                    parameters={"target": m.group(1).strip()},
                    source="rule_fallback",
                    response_text="Đang thực hiện quét an ninh mạng nội bộ cho Ngài.",
                ),
            ),
        ]

    def _get_word_boundary_pattern(self, pattern_key: str) -> re.Pattern:
        """Retrieves or compiles a cached word-boundary pattern."""
        pattern = self._rule_key_regexes.get(pattern_key)
        if pattern is None:
            pattern = re.compile(r"(?:\b|^)" + re.escape(pattern_key) + r"(?:\b|$)", re.IGNORECASE)
            self._rule_key_regexes[pattern_key] = pattern
        return pattern

    def _match_rule_key(
        self,
        key: str,
        clean_lower: str,
        clean_lower_stripped: str | None = None,
    ) -> bool:
        """
        Determines if clean_lower matches the deterministic key with safe diacritic folding.
        - Single-word rules (len(words) == 1): STRICT whole-word token match with diacritics PRESERVED.
          Never substring, never diacritic-folded, completely preventing homophone collisions.
        - Multi-word rules (len(words) >= 2): Diacritic folding enabled with word boundary verification.
        """
        if not key or not clean_lower:
            return False

        word_count = self._rule_word_counts.get(key)
        if word_count is None:
            word_count = len(key.strip().split())

        # 1. Single-word rules: preserve diacritics, enforce whole-word token boundary
        if word_count == 1:
            if key not in clean_lower:
                return False
            if clean_lower == key:
                return True
            if key == "tắt" and "tóm tắt" in clean_lower:
                return False
            pattern = self._rule_key_regexes.get(key)
            if pattern is None:
                pattern = re.compile(r"(?:\b|^)" + re.escape(key) + r"(?:\b|$)", re.IGNORECASE)
                self._rule_key_regexes[key] = pattern
            return bool(pattern.search(clean_lower))

        # 2. Multi-word rules: check exact match first
        if key in clean_lower:
            return True

        # For massive adversarial strings (>2048 chars), skip secondary diacritic scan to prevent DoS
        if len(clean_lower) > 2048:
            return False

        # 3. Multi-word rules: safe diacritic folding
        if clean_lower_stripped is None:
            if len(clean_lower) > 2048:
                return False
            clean_lower_stripped = strip_vietnamese_diacritics(clean_lower)

        key_stripped = self._stripped_rule_keys.get(key)
        if key_stripped is None:
            key_stripped = strip_vietnamese_diacritics(key)

        if key_stripped not in clean_lower_stripped:
            return False
        if clean_lower_stripped == key_stripped:
            return True

        pattern_stripped = self._get_word_boundary_pattern(key_stripped)
        return bool(pattern_stripped.search(clean_lower_stripped))

    def _make_light_intent(self, service: str, target: str | None) -> IntentResult:
        t = (target or "").lower().strip()
        if "bàn" in t or "desk" in t:
            entity_id = "light.desk_lamp"
        elif "phòng ngủ" in t or "bedroom" in t:
            entity_id = "light.bedroom"
        else:
            entity_id = "light.living_room"

        params = {"domain": "light", "service": service, "entity_id": entity_id}
        resp = self.get_natural_response("home_assistant_call", params, text=t)
        return IntentResult(
            action_name="home_assistant_call",
            parameters=params,
            source="rule_fallback",
            response_text=resp,
        )

    def _make_hw_intent(self, comp_raw: str) -> IntentResult:
        c = comp_raw.lower().strip()
        if "gpu" in c or "card" in c:
            comp = "gpu"
        elif "ram" in c or "bộ nhớ" in c or "bo nho" in c:
            comp = "ram"
        elif "disk" in c or "ổ cứng" in c or "o cung" in c or "smart" in c:
            comp = "disk"
        elif "pin" in c or "battery" in c:
            comp = "battery"
        else:
            comp = "cpu"

        params = {"component": comp}
        return IntentResult(
            action_name="hardware_telemetry_check",
            parameters=params,
            source="rule_fallback",
            response_text=self.get_natural_response("hardware_telemetry_check", params),
        )

    def _make_weather_intent(self, loc_raw: str | None) -> IntentResult:
        loc = (loc_raw or "").strip().lower()
        if "hà nội" in loc or "hanoi" in loc:
            location = "Hà Nội"
            cmd = "curl -s wttr.in/Hanoi?format=3"
        elif "sài gòn" in loc or "saigon" in loc or "tp hcm" in loc or "hồ chí minh" in loc:
            location = "Sài Gòn"
            cmd = "curl -s wttr.in/Saigon?format=3"
        else:
            location = "current"
            cmd = "curl -s wttr.in?format=3"

        params = {"command": cmd, "topic": "weather", "location": location}
        return IntentResult(
            action_name="shell_exec",
            parameters=params,
            source="rule_fallback",
            response_text=self.get_natural_response("shell_exec", params, text=loc),
        )

    def _make_reminder_duration_intent(self, amount: int, unit_str: str, message: str) -> IntentResult:
        delay_s = _parse_duration_seconds(amount, unit_str)
        clean_msg = message.strip() if message else "nhắc nhở chung"
        params = {"message": clean_msg, "delay_s": delay_s, "delay_minutes": delay_s // 60}
        resp = f"Đã ghi nhận lời nhắc '{clean_msg}' của Ngài." if clean_msg != "nhắc nhở chung" else "Đã ghi nhận lời nhắc của Ngài."
        return IntentResult(
            action_name="reminder",
            parameters=params,
            source="rule_fallback",
            response_text=resp,
        )

    def _make_reminder_custom_intent(self, raw_msg: str) -> IntentResult:
        clean = raw_msg.strip()
        if clean.lower() in ("nhở", "tôi", "nhở tôi", "lịch", "báo thức", ""):
            return IntentResult(
                action_name="reminder",
                parameters={"message": "nhắc nhở chung"},
                source="rule_fallback",
                response_text="Đã ghi nhận lời nhắc của Ngài.",
            )
        return IntentResult(
            action_name="reminder",
            parameters={"message": clean},
            source="rule_fallback",
            response_text=f"Đã ghi nhận lời nhắc '{clean}' của Ngài.",
        )

    # Preserve the H-07 guard and cover every desktop app launch. Keep the
    # accented "đừng" intact: folded "dung" also means "dùng" (to use).
    _H07_NEGATION_MARKERS = ("không muốn", "khong muon")

    def _is_negated_h07_launch_target(
        self,
        action_name: str,
        parameters: dict[str, Any],
        clean_lower: str,
        clean_lower_stripped: str | None,
    ) -> bool:
        """Prevent negated app requests from matching a legacy substring rule."""
        is_h07_target = (
            action_name == "spotify"
            or action_name in ("app_open", "open_app")
            or (action_name == "web_open" and parameters.get("site") == "claude")
        )
        if not is_h07_target:
            return False
        if any(marker in clean_lower for marker in self._H07_NEGATION_MARKERS):
            return True
        if clean_lower_stripped and "khong muon" in clean_lower_stripped:
            return True
        if re.search(r"\b(?:đừng|do\s+not|don't|dont|never|chớ)\b", clean_lower):
            return True
        if clean_lower_stripped and re.search(
            r"\b(?:dung\s+(?:mo|bat|chay|phat|nghe|choi|open|start|launch)|khong\s+(?:mo|bat|chay|phat|nghe|choi|open)|never|dont)\b",
            clean_lower_stripped,
        ):
            return True
        return False

    @staticmethod
    def _catalog_app_parameters(action_name: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Keep desktop launches verified across static rules and LLM tools."""
        params = dict(parameters)
        if action_name in ("app_open", "open_app"):
            target = params.get("app_name") or params.get("name") or params.get("app") or params.get("query") or ""
            normalized = strip_vietnamese_diacritics(str(target).strip().casefold())
            if normalized not in ("settings", "cai dat", "ms-settings:"):
                params["installed_only"] = True
        return params

    _APP_COMMAND_PREFIX = re.compile(
        r"^(?:jarvis[,\s]*)?(?:mở|mo|open|bật|bat|chạy|chay|launch|start|"
        r"khởi\s+động|khoi\s+dong)\b\s*", re.IGNORECASE,
    )
    _APP_QUALIFIER = re.compile(
        r"^(?:ứng\s+dụng|ung\s+dung|app|application|phần\s+mềm|phan\s+mem|"
        r"chương\s+trình|chuong\s+trinh)(?:\s+|$)", re.IGNORECASE,
    )

    def _match_installed_app_request(
        self, text: str, *, explicit_only: bool = False
    ) -> IntentResult | None:
        """Parse one complete app name without discovering or launching anything.

        Explicit app requests precede legacy aliases. Short requests are only
        considered after specific regex routes; exact static commands retain
        their established behavior. Always inspect the complete input so the
        regex length limit cannot turn a truncated prefix into a launch.
        """
        clean = text.strip()
        prefix = self._APP_COMMAND_PREFIX.match(clean)
        if prefix is None:
            return None
        target = clean[prefix.end():]
        qualifier = self._APP_QUALIFIER.match(target)
        # Workspace/project and web service commands share the same "mở/open" prefix but are
        # not application launches. Leave them for the workspace / web rule families.
        if qualifier is None and re.match(
            r"^(?:dự\s+án|du\s+an|project|workspace|repo|code|xem\s+youtube|youtube|xem\s+video|trang\s+web|web|website)\b", target, re.IGNORECASE
        ):
            return None
        if qualifier:
            target = target[qualifier.end():]
        if explicit_only and qualifier is None and len(clean) <= 512:
            return None
        if not qualifier and len(clean) <= 512:
            target_rule = self.rule_engine.get(target.lower())
            if (target_rule is not None and target_rule.action_name == "app_open"
                    and target_rule.parameters.get("app_name") == "Settings"):
                return None
            command = re.sub(r"^jarvis[,\s]*", "", clean, flags=re.IGNORECASE).lower()
            if (command in self.rule_engine
                    or strip_vietnamese_diacritics(command) in self._stripped_rule_keys.values()):
                return None
        target = target.strip()
        compound = re.search(r"\b(?:và|va|and|hoặc|hoac|or|rồi|roi|then)\b", target, re.IGNORECASE)
        if (len(clean) > 512 or not 1 <= len(target) <= 120 or compound
                or any(char in clean for char in ";\r\n|`$")):
            return IntentResult(
                action_name="unknown_intent",
                parameters={"raw_text": text, "clarify": True},
                confidence=0.0,
                source="rule_fallback",
                raw_text=text,
                response_text="Ngài vui lòng nói tên một ứng dụng cần mở trong một lệnh ngắn.",
            )
        return IntentResult(
            action_name="app_open",
            parameters={"app_name": target, "installed_only": True},
            source="rule_fallback",
            raw_text=text,
            response_text="Đang tìm ứng dụng trên máy.",
        )

    def _make_app_intent(self, app_name: str) -> IntentResult:
        clean = (app_name or "").strip().lower()
        if clean == "spotify":
            return IntentResult(
                action_name="spotify",
                parameters={"query": "", "name": "spotify"},
                source="rule_fallback",
                response_text="Đang mở Spotify và phát nhạc cho Ngài.",  # consistent with rule_engine entry
            )
        # H-07 fix: the "Universal Application & Software Launchers" regex
        # (category 7, includes "cài đặt"/"cai dat"/"settings" as app-name
        # alternatives) runs BEFORE the static rule_engine dict, so it
        # previously intercepted phrases like "mở cài đặt"/"bật settings"/
        # "mo cai dat" before they ever reached the dict's canonical
        # {"app_name": "Settings", "app": "ms-settings:"} entries -- each
        # different literal alias produced a DIFFERENT, non-canonical
        # app_name ("cài đặt" vs "cai dat" vs "settings"), which would also
        # have meant three different LaunchDedupeGuard identities for the
        # SAME real Settings app. Folding every Settings alias onto the
        # same canonical branch here (diacritic-insensitive) guarantees one
        # identity regardless of which code path -- regex or dict -- a
        # given phrasing happens to hit.
        if strip_vietnamese_diacritics(clean) in ("settings", "cai dat"):
            return IntentResult(
                action_name="app_open",
                parameters={"app_name": "Settings", "app": "ms-settings:"},
                source="rule_fallback",
                response_text="Đang mở cài đặt hệ thống cho Ngài.",  # consistent with rule_engine entry
            )
        params = {"app_name": clean, "name": clean, "installed_only": True}
        return IntentResult(
            action_name="app_open",
            parameters=params,
            source="rule_fallback",
            response_text=f"Đang mở ứng dụng {clean} cho Ngài.",
        )

    def _make_web_intent(self, site: str, query: str | None = None) -> IntentResult:
        clean_site = (site or "").strip()
        clean_query = (query or "").strip() if query else ""
        target = f"{clean_site} {clean_query}".strip()
        params = {"target": target, "site": clean_site, "query": clean_query}
        return IntentResult(
            action_name="web_open",
            parameters=params,
            source="rule_fallback",
            response_text=f"Đang mở {clean_site} cho Ngài.",
        )

    _VOLUME_INCREASE_TOKENS = frozenset({"len", "to", "het", "tang"})
    _VOLUME_DECREASE_TOKENS = frozenset({"xuong", "nho", "be", "giam", "ha"})
    _VOLUME_MUTE_TOKENS = frozenset({"tat", "mute"})
    _VOLUME_UNMUTE_TOKENS = frozenset({"bat", "unmute"})
    _VOLUME_LEVEL_TOKEN = "muc"

    def _make_system_volume_intent(self, matched_text: str) -> IntentResult:
        """
        H-08 fix: deterministically classifies a matched speaker
        volume-control phrase into an exact level / mute / unmute /
        increase / decrease / ambiguous-no-op, instead of collapsing
        everything into a meaningless {"action": "adjust"} that
        _handle_system_volume() cannot act on at all (the confirmed bug:
        "tắt tiếng"/"bật tiếng" previously reached that generic branch and
        silently became a +10 volume INCREASE instead of a mute/unmute).

        Matches on whole, diacritic-folded, whitespace-tokenized words --
        never a raw substring check -- so "unmute" (tokenizes to the
        single whole token "unmute") is never misclassified as "mute" (a
        bare `"mute" in text` substring check would otherwise incorrectly
        match inside "unmute").

        Priority, and why (H-08 review correction): an explicit "mức <N>"
        (exact level) is checked first -- an unambiguous absolute request.
        MUTE ("tắt"/"mute") is checked BEFORE increase/decrease so that
        "tắt hết âm thanh"/"tắt hẳn tiếng" can never be misread as an
        INCREASE merely because "hết" also happens to double as the
        increase-direction token used by "hết cỡ" (= max out volume) --
        "tắt" unconditionally means mute regardless of what follows it.
        Increase/decrease are checked before UNMUTE ("bật"/"unmute") so
        that "bật âm lượng lên" (turn the volume UP) still correctly
        reads as an increase, not an unmute -- "bật" alone (no direction
        word) is the only case that resolves to unmute.
        An explicit trailing number (e.g. "lên 20", "xuống 20") is used
        as the exact delta magnitude instead of the generic +/-10 default.
        """
        number_match = re.search(r"\d+", matched_text)
        explicit_amount = int(number_match.group(0)) if number_match else None
        tokens = set(strip_vietnamese_diacritics(matched_text.lower()).split())

        if self._VOLUME_LEVEL_TOKEN in tokens and explicit_amount is not None:
            level = max(0, min(100, explicit_amount))
            return IntentResult(
                action_name="system_volume",
                parameters={"level": level},
                source="rule_fallback",
                response_text=f"Đang đặt âm lượng ở mức {level}%, cho Ngài.",
            )
        if tokens & self._VOLUME_MUTE_TOKENS:
            return IntentResult(
                action_name="system_volume",
                parameters={"mute": True},
                source="rule_fallback",
                response_text="Đã tắt tiếng máy tính, thưa Ngài.",
            )
        if tokens & self._VOLUME_INCREASE_TOKENS:
            amount = explicit_amount if explicit_amount is not None else 10
            return IntentResult(
                action_name="system_volume",
                parameters={"delta": amount},
                source="rule_fallback",
                response_text="Đang tăng âm lượng cho Ngài.",
            )
        if tokens & self._VOLUME_DECREASE_TOKENS:
            amount = explicit_amount if explicit_amount is not None else 10
            return IntentResult(
                action_name="system_volume",
                parameters={"delta": -amount},
                source="rule_fallback",
                response_text="Đang giảm âm lượng cho Ngài.",
            )
        if tokens & self._VOLUME_UNMUTE_TOKENS:
            return IntentResult(
                action_name="system_volume",
                parameters={"mute": False},
                source="rule_fallback",
                response_text="Đã bật tiếng máy tính, thưa Ngài.",
            )
        # Genuinely ambiguous phrasing (e.g. bare "vặn loa" / "điều chỉnh
        # âm lượng" with no direction word, level, or mute/unmute verb).
        # H-08 final contract correction: this used to execute system_volume
        # {"delta": 0} and claim success ("Đang điều chỉnh âm lượng cho
        # Ngài." implied a real action happened when none did). It stays
        # categorized under system_volume (the established P0 routing
        # contract, tests/unit/test_router_p0.py /
        # tests/eval/routing_eval_n150.py) rather than being reclassified
        # to unknown_intent -- the explicit {"clarify": True} parameter
        # tells _handle_system_volume() to ask a clarification question
        # with ZERO hardware side effects, never touching
        # computer_controller. Mirrors the "dieu chinh am luong" dict
        # entry's identical fix above.
        return IntentResult(
            action_name="system_volume",
            parameters={"clarify": True},
            source="rule_fallback",
            response_text=(
                "Ngài muốn tăng âm lượng, giảm âm lượng, tắt tiếng, bật tiếng, "
                "hay đặt một mức âm lượng cụ thể? Xin nói rõ hơn, thưa Ngài."
            ),
        )

    def _make_folder_intent(self, folder: str) -> IntentResult:
        clean = (folder or "").strip()
        params = {"folder": clean}
        return IntentResult(
            action_name="folder_open",
            parameters=params,
            source="rule_fallback",
            response_text=f"Đang mở thư mục {clean} cho Ngài.",
        )

    def _make_workspace_intent(self, action: str, target: str | None) -> IntentResult:
        clean_target = (target or "").strip()

        if action == "open":
            # Strip prefixes like "sang ", "to " if present
            if clean_target.lower().startswith("sang "):
                clean_target = clean_target[5:].strip()
            elif clean_target.lower().startswith("to "):
                clean_target = clean_target[3:].strip()

            action_name = "workspace_prepare"
            params = {
                "action": "open",
                "project": clean_target,
                "recipe": clean_target or "ai_development",
            }
            resp = f"Đang mở dự án {clean_target} cho Ngài." if clean_target else "Đang chuẩn bị môi trường làm việc cho Ngài."
        elif action == "create":
            # Strip noise words like "tên ", "tên: ", "name ", "name: "
            if clean_target.lower().startswith("tên:"):
                clean_target = clean_target[4:].strip()
            elif clean_target.lower().startswith("tên "):
                clean_target = clean_target[4:].strip()
            elif clean_target.lower().startswith("name:"):
                clean_target = clean_target[5:].strip()
            elif clean_target.lower().startswith("name "):
                clean_target = clean_target[5:].strip()

            if clean_target.lower() in ("mới", "new", ""):
                clean_target = ""
            elif clean_target.lower().endswith(" mới"):
                clean_target = clean_target[:-4].strip()
            elif clean_target.lower().endswith(" new"):
                clean_target = clean_target[:-4].strip()

            action_name = "project_create"
            params = {
                "action": "create",
                "name": clean_target,
                "project_name": clean_target,
            }
            resp = f"Đang khởi tạo dự án {clean_target} cho Ngài." if clean_target else "Đang khởi tạo dự án mới cho Ngài."
        else:  # list
            action_name = "project_list"
            params = {"action": "list"}
            resp = "Đang liệt kê danh sách các dự án cho Ngài."

        return IntentResult(
            action_name=action_name,
            parameters=params,
            source="rule_fallback",
            response_text=resp,
        )

    def _make_git_project_intent(self, git_action: str, target: str | None) -> IntentResult:
        act = (git_action or "status").lower().strip()
        clean_target = (target or "").strip()
        for prefix in ("dự án ", "project ", "workspace ", "repo ", "code "):
            if clean_target.lower().startswith(prefix):
                clean_target = clean_target[len(prefix):].strip()
                break

        params = {"action": act, "project": clean_target, "repo_path": ""}
        if act == "commit":
            resp = f"Đang thực hiện commit dự án {clean_target} cho Ngài." if clean_target else "Đang commit các thay đổi dự án cho Ngài."
        elif act == "push":
            resp = f"Đang đẩy code dự án {clean_target} lên Git cho Ngài." if clean_target else "Đang đẩy các thay đổi lên Git repository cho Ngài."
        elif act == "log":
            resp = f"Đang kiểm tra lịch sử commit dự án {clean_target} cho Ngài." if clean_target else "Đang kiểm tra lịch sử commit của dự án cho Ngài."
        elif act == "branch":
            resp = f"Đang kiểm tra các nhánh Git của dự án {clean_target} cho Ngài." if clean_target else "Đang kiểm tra các nhánh Git của dự án cho Ngài."
        elif act == "diff":
            resp = f"Đang kiểm tra các thay đổi khác biệt trong dự án {clean_target} cho Ngài." if clean_target else "Đang kiểm tra các thay đổi trong Git repository cho Ngài."
        else:
            resp = f"Đang kiểm tra trạng thái Git dự án {clean_target} cho Ngài." if clean_target else "Đang kiểm tra trạng thái Git cho Ngài."

        return IntentResult(
            action_name="skill_git_assistant",
            parameters=params,
            source="rule_fallback",
            response_text=resp,
        )

    def get_natural_response(
        self,
        action_name: str,
        params: dict[str, Any] | None = None,
        text: str = "",
        action_result: ActionResult | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Generates polite, contextual Vietnamese responses for all JARVIS actions and queries.
        Supports rich action result messages, dynamic parameter formatting, and standard fallback.
        """
        p = params or {}
        text_lower = text.lower() if text else ""

        # 1. Pre-formatted message from ActionResult (e.g. from HardwareReporter or system status)
        if action_result and action_result.data and isinstance(action_result.data, dict):
            if "message" in action_result.data and action_result.data["message"]:
                return str(action_result.data["message"])

        # 2. Generic LLM Conversational Reply
        if action_name == "generic_llm_response":
            return str(p.get("reply", "") or text)

        # 3. Smart Home / Home Assistant (Category 1)
        if action_name in ("home_assistant_call", "smart_home"):
            domain = p.get("domain", "")
            service = p.get("service", "")
            entity = p.get("entity_id", "")
            temp = p.get("temperature")

            if temp is not None:
                return f"Đã đặt nhiệt độ điều hòa thành {temp} độ cho Ngài."

            if domain == "climate" or "điều hòa" in text_lower or "máy lạnh" in text_lower or "ac" in entity:
                if service == "turn_off":
                    return "Đang tắt điều hòa cho Ngài."
                return "Đang bật điều hòa cho Ngài."

            if domain == "fan" or "quạt" in text_lower or "fan" in entity:
                if service == "turn_off":
                    return "Đang tắt quạt cho Ngài."
                return "Đang bật quạt cho Ngài."

            target_str = ""
            if "phòng khách" in text_lower or "living_room" in entity and "phòng khách" in text_lower:
                target_str = " phòng khách"
            elif "bàn" in text_lower or "desk" in entity:
                target_str = " bàn làm việc"
            elif "phòng ngủ" in text_lower or "bedroom" in entity:
                target_str = " phòng ngủ"

            if domain == "switch" or "thiết bị" in text_lower:
                if service == "turn_off":
                    return "Đang tắt thiết bị cho Ngài."
                return "Đang bật thiết bị cho Ngài."

            if service in ("turn_on", "toggle"):
                return f"Đang bật đèn{target_str} cho Ngài."
            elif service == "turn_off":
                return f"Đang tắt đèn{target_str} cho Ngài."
            return "Đã thực hiện điều khiển thiết bị thông minh cho Ngài."

        # 4. Hardware Telemetry & Health (Category 2)
        if action_name in ("hardware_status_query", "system_status"):
            return "Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu, CPU và RAM ở mức an toàn, thưa Ngài."

        if action_name in ("hardware_telemetry_check", "hardware_telemetry"):
            comp = (p.get("component") or "").lower()
            if "cpu" in comp:
                return "Nhiệt độ CPU hiện tại là 45 độ C, hiệu năng ổn định, thưa Ngài."
            elif "ram" in comp or "bộ nhớ" in comp:
                return "Bộ nhớ RAM đang sử dụng ở mức bình thường, tài nguyên dồi dào, thưa Ngài."
            elif "gpu" in comp or "card" in comp:
                return "Card đồ họa hoạt động bình thường, nhiệt độ trong ngưỡng an toàn, thưa Ngài."
            elif "disk" in comp or "smart" in comp or "ổ" in comp:
                return "Ổ đĩa đang hoạt động trong trạng thái tốt, thưa Ngài."
            elif "pin" in comp or "battery" in comp:
                return "Pin hệ thống đang ở mức an toàn, thưa Ngài."
            return "Đang kiểm tra thông số phần cứng hệ thống cho Ngài."

        # 5. Spotify & Music (Category 3)
        if action_name in ("spotify", "spotify_play", "play_song"):
            cmd = p.get("command", "")
            if cmd == "pause" or "dừng" in text_lower or "tắt nhạc" in text_lower or "tạm dừng" in text_lower:
                return "Đã tạm dừng phát nhạc, thưa Ngài."
            if cmd == "next" or "chuyển bài" in text_lower or "tiếp theo" in text_lower:
                return "Đang chuyển bài tiếp theo, thưa Ngài."
            query = p.get("query") or p.get("track") or p.get("artist")
            if query:
                return f"Đang mở Spotify và phát {query} cho Ngài."
            return "Đang mở Spotify và phát nhạc cho Ngài."

        if action_name in ("spotify_pause", "pause_music"):
            return "Đã tạm dừng phát nhạc, thưa Ngài."

        if action_name in ("spotify_next", "next_song"):
            return "Đang chuyển bài tiếp theo, thưa Ngài."

        # 6. Weather (Category 4)
        if action_name in ("shell", "shell_exec", "weather", "weather_query"):
            topic = p.get("topic", "")
            if topic == "weather" or "thời tiết" in text_lower or action_name in ("weather", "weather_query"):
                loc = p.get("location", "")
                if loc and loc not in ("current", "default"):
                    return f"Đang kiểm tra thông tin thời tiết tại {loc} cho Ngài."
                return "Đang kiểm tra thông tin thời tiết hôm nay cho Ngài."
            return "Đang thực thi lệnh hệ thống cho Ngài."

        # 7. Reminders & Alarms (Category 5)
        if action_name in ("reminder", "reminder_create", "tts_speak"):
            msg = p.get("message") or p.get("content") or ""
            time_str = p.get("time_str") or ""
            if msg and msg != "nhắc nhở chung":
                if time_str:
                    return f"Đã ghi nhận lời nhắc '{msg}' vào lúc {time_str} của Ngài."
                return f"Đã ghi nhận lời nhắc '{msg}' của Ngài."
            return "Đã ghi nhận lời nhắc của Ngài."

        # 8. System Power (Category 6)
        if action_name in ("system_power", "power_action"):
            act = (p.get("action") or p.get("power_action") or "shutdown").lower()
            if "restart" in act or "reboot" in act:
                return "Lệnh khởi động lại hệ thống đã được ghi nhận. Vui lòng xác nhận, thưa Ngài."
            elif "lock" in act or "khóa" in act:
                return "Đã khóa màn hình máy tính, thưa Ngài."
            elif "sleep" in act or "ngủ" in act:
                return "Đang đưa hệ thống vào chế độ ngủ tiết kiệm điện năng, thưa Ngài."
            return "Lệnh tắt máy đã được ghi nhận. Vui lòng xác nhận để thực thi nhằm đảm bảo an toàn dữ liệu, thưa Ngài."

        # 9. Workspace Automation & Projects
        if action_name == "workspace_prepare":
            proj = p.get("project") or p.get("recipe")
            if proj and proj != "ai_development":
                return f"Đang mở dự án {proj} cho Ngài."
            return "Đang chuẩn bị môi trường làm việc cho Ngài."

        if action_name in ("project_create", "workspace_create"):
            p_name = p.get("name") or p.get("project_name")
            if p_name:
                return f"Đang khởi tạo dự án {p_name} cho Ngài."
            return "Đang khởi tạo dự án mới cho Ngài."

        if action_name in ("project_list", "workspace_list"):
            return "Đang liệt kê danh sách các dự án cho Ngài."

        # 10. Self Healing
        if action_name == "healing_watchdog_heal":
            return "Đang tiến hành tối ưu hóa bộ nhớ và kiểm tra tiến trình hệ thống cho Ngài."

        # 11. Security Scan
        if action_name == "security_nmap_scan":
            return "Đang thực hiện quét an ninh mạng nội bộ cho Ngài."

        # 12. Memory Actions
        if action_name == "memory_save_fact":
            return str(p.get("message") or "Tôi đã ghi nhớ thông tin này, thưa Ngài.")

        # 13. OS Controls, Application & Web Launchers
        if action_name in ("app_open", "open_app"):
            app_n = p.get("app_name") or p.get("name") or p.get("app") or text
            return f"Đã mở ứng dụng {app_n}, thưa Ngài."

        if action_name in ("web_open", "open_website"):
            target_w = p.get("site") or p.get("target") or p.get("url") or p.get("query") or text
            return f"Đã mở {target_w} cho Ngài."

        if action_name in ("folder_open", "open_folder"):
            fld = p.get("folder") or text
            return f"Đã mở thư mục {fld}, thưa Ngài."

        if action_name == "window_minimize_all":
            return "Đã thu nhỏ tất cả các cửa sổ xuống màn hình Desktop, thưa Ngài."

        if action_name in ("window_active", "window_close"):
            return "Đã đóng cửa sổ hiện tại, thưa Ngài."

        if action_name == "screen_capture":
            return "Đã chụp ảnh màn hình và lưu ra Desktop cho Ngài."

        if action_name == "system_volume":
            vol = p.get("volume") or p.get("level")
            if vol is not None:
                return f"Đã đặt âm lượng hệ thống thành {vol}%, thưa Ngài."
            return "Đã điều chỉnh âm lượng hệ thống cho Ngài."

        if action_name == "system_brightness":
            b = p.get("brightness") or p.get("level")
            if b is not None:
                return f"Đã đặt độ sáng màn hình thành {b}%, thưa Ngài."
            return "Đã điều chỉnh độ sáng màn hình cho Ngài."

        # 13b. Built-in Skills (Category 6b)
        if action_name in ("skill_briefing", "briefing"):
            return "Đang tổng hợp báo cáo buổi sáng cho Ngài."

        if action_name in ("skill_pomodoro", "pomodoro"):
            return "Đã cập nhật chế độ tập trung Pomodoro cho Ngài."

        if action_name in ("skill_note_taker", "note_taker"):
            return "Đã xử lý ghi chú cá nhân cho Ngài."

        if action_name in ("skill_calculator", "calculator"):
            return "Đã thực hiện tính toán cho Ngài."

        if action_name in ("skill_file_manager", "file_manager"):
            return "Đang tìm kiếm file cho Ngài."

        if action_name in ("skill_git_assistant", "git_assistant"):
            act = (p.get("action") or "status").lower()
            proj = p.get("project", "")
            if act == "commit":
                return f"Đang thực hiện commit dự án {proj} cho Ngài." if proj else "Đang commit các thay đổi dự án cho Ngài."
            if act == "push":
                return f"Đang đẩy code dự án {proj} lên Git cho Ngài." if proj else "Đang đẩy các thay đổi lên Git repository cho Ngài."
            if act == "log":
                return f"Đang kiểm tra lịch sử commit dự án {proj} cho Ngài." if proj else "Đang kiểm tra lịch sử commit của dự án cho Ngài."
            if act == "branch":
                return f"Đang kiểm tra các nhánh Git của dự án {proj} cho Ngài." if proj else "Đang kiểm tra các nhánh Git của dự án cho Ngài."
            if act == "diff":
                return f"Đang kiểm tra các thay đổi khác biệt trong dự án {proj} cho Ngài." if proj else "Đang kiểm tra các thay đổi trong Git repository cho Ngài."
            return f"Đang kiểm tra trạng thái Git dự án {proj} cho Ngài." if proj else "Đang kiểm tra trạng thái Git cho Ngài."

        if action_name in ("skill_clipboard", "clipboard"):
            return "Đã xử lý thao tác clipboard cho Ngài."

        if action_name in ("skill_app_launcher", "app_launcher"):
            return "Đang khởi chạy ứng dụng cho Ngài."

        if action_name in ("skill_system_control", "system_control"):
            return "Đã thực thi điều khiển hệ thống cho Ngài."

        # 14. Fallback (Category 7)
        return "Tôi chưa hiểu lệnh này, vui lòng thử cách khác"

    def parse_intent(
        self,
        text: str,
        available_actions: list[str] | None = None,
        context: dict[str, Any] | None = None,
        force_llm: bool = False,
    ) -> IntentResult:
        """
        Parses user voice/text query into structured tool calling IntentResult.
        Executes Two-Tier pipeline: Fast Rules -> LLM Tool Call -> Fallback Rules.
        """
        # Guard: None input (e.g. STT silence/timeout returning None)
        if text is None:
            return IntentResult(
                action_name="unknown_intent",
                parameters={},
                confidence=0.0,
                source="rule_fast_path",
                raw_text="",
                response_text="",  # Silence → no TTS; caller decides UX
            )
        clean = text.strip()
        clean_lower_full = clean.lower()  # Full text — safe for plain substring 'in' checks
        # Truncate for REGEX only to prevent ReDoS on long inputs (e.g. 50KB adversarial strings).
        # Dict-key _match_rule_key uses simple 'in' substring checks which are O(n) safe.
        _MAX_REGEX_LEN = 512
        clean_for_regex = clean[:_MAX_REGEX_LEN] if len(clean) > _MAX_REGEX_LEN else clean

        # Strip common conversational vocatives and filler prefixes (e.g. "jarvis ơi", "ê jarvis", "này jarvis", "làm ơn")
        clean_normalized = re.sub(
            r"^(?:(?:ê|này|hey|hi|hello)?\s*jarvis(?:\s*ơi|\s*à|\s*nhe|\s*nhé)?|[êe]|này|làm\s*ơn|hãy\s*giúp\s*(?:tôi|tao|mình)|giúp\s*(?:tôi|tao|mình)\s*(?:với)?|cho\s*hỏi\s*xíu)[,\s]+",
            "",
            clean,
            flags=re.IGNORECASE,
        ).strip()
        if clean_normalized:
            clean_for_regex = clean_normalized[:_MAX_REGEX_LEN]

        clean_lower = clean_lower_full  # Used for dict rule key matching (full-text safe)
        clean_lower_stripped = (
            strip_vietnamese_diacritics(clean_lower)
            if len(clean_lower) <= 2048
            else None
        )

        # Early return for meaningless inputs — only check head to avoid processing 50KB
        import re as _re
        clean_head = clean_for_regex  # At most 512 chars
        _clean_stripped = _re.sub(
            r'[\U00010000-\U0010ffff'   # Supplementary plane (most modern emoji: 🔥🚀🎉)
            r'\U0001F600-\U0001F64F'    # Emoticons block
            r'\U0001F300-\U0001F5FF'    # Misc Symbols & Pictographs
            r'\U0001F680-\U0001F6FF'    # Transport & Map Symbols
            r'\U0001F1E0-\U0001F1FF'    # Regional indicator / flags
            r'\u2600-\u27BF'            # BMP emojis: Misc Symbols (⚡❄) + Dingbats (✨✅)
            r'\uFE00-\uFE0F'            # Variation selectors (emoji modifier ️)
            r'\s]', '', clean_head,
        )
        _is_emoji_only = len(clean_head) > 0 and len(_clean_stripped) == 0
        _is_number_only = bool(_re.fullmatch(r'[\d\s\.\,\-\+]+', clean_head))
        if _is_emoji_only or _is_number_only:
            return IntentResult(
                action_name="unknown_intent",
                parameters={"raw_text": text},
                confidence=0.0,
                source="rule_fast_path",
                raw_text=text,
                response_text="Tôi chưa hiểu lệnh này, vui lòng thử cách khác",
            )

        # Never run full-text rule matching on an adversarially large command.
        # The regex path is bounded, but dictionary substring rules could still
        # classify a repeated phrase as a real action after truncation.
        if len(clean) > 2048 and re.match(
            r"^(?:jarvis[,\s]*)?(?:mở|mo|open)\s+(?:dự\s+án|du\s+an|project|workspace)\b",
            clean,
            re.IGNORECASE,
        ):
            # Keep the bounded, safe workspace intent without carrying the
            # attacker-controlled 50KB suffix into a project path.
            return IntentResult(
                action_name="workspace_prepare",
                parameters={"action": "open", "project": "", "recipe": "ai_development"},
                confidence=1.0,
                source="rule_fast_path",
                raw_text=text,
                response_text="Đang chuẩn bị môi trường làm việc cho Ngài.",
            )
        if len(clean) > 2048:
            # Preserve deterministic, read-only/safe fast commands without
            # scanning or retaining their untrusted suffixes.
            folded = clean[:2048].casefold()
            if "lệnh kiểm tra hệ thống" in folded or "len kiem tra he thong" in folded:
                return IntentResult(
                    action_name="hardware_status_query",
                    parameters={},
                    confidence=1.0,
                    source="rule_fast_path",
                    raw_text=text,
                    response_text="Đang kiểm tra tình trạng hệ thống cho Ngài.",
                )
            if "bật đèn" in folded or "bat den" in folded:
                return self._make_light_intent("turn_on", "")
        if len(clean) > 2048:
            return IntentResult(
                action_name="unknown_intent",
                parameters={"raw_text": text[:2048]},
                confidence=0.0,
                source="rule_fast_path",
                raw_text=text,
                response_text="Tôi chưa hiểu lệnh này, vui lòng thử cách khác",
            )

        # 1. TIER 1: Fast Rule Check (Sub-millisecond)
        if not force_llm and self.fast_path_enabled:
            installed_intent = self._match_installed_app_request(text, explicit_only=True)
            if installed_intent is not None:
                return installed_intent
            # Memory Fast Commands Check
            if self.memory_manager:
                if self.memory_manager.is_remember_command(clean_for_regex):
                    res_dict = self.memory_manager.handle_remember_command(clean_for_regex)
                    return IntentResult(
                        action_name="memory_save_fact",
                        parameters=res_dict,
                        confidence=1.0,
                        source="rule_fast_path",
                        raw_text=text,
                        response_text=res_dict.get("message", "Tôi đã ghi nhớ thông tin này, thưa Ngài."),
                    )
                if self.memory_manager.is_today_summary_command(clean_for_regex):
                    res_dict = self.memory_manager.handle_today_summary(clean_for_regex)
                    return IntentResult(
                        action_name="memory_summarize_daily",
                        parameters=res_dict,
                        confidence=1.0,
                        source="rule_fast_path",
                        raw_text=text,
                        response_text=res_dict.get("message", "Đang tóm tắt hoạt động hôm nay cho Ngài."),
                    )

            # First check parametric regex rules (truncated string to prevent ReDoS)
            for pattern, extractor in self._regex_rules:
                m = pattern.search(clean_for_regex)
                if m:
                    res = extractor(m)
                    if self._is_negated_h07_launch_target(
                        res.action_name, res.parameters, clean_lower, clean_lower_stripped
                    ):
                        continue
                    res.raw_text = text
                    if not res.response_text:
                        res.response_text = self.get_natural_response(res.action_name, res.parameters, text)
                    return res

            installed_intent = self._match_installed_app_request(text)
            if installed_intent is not None:
                return installed_intent

            # Then check sorted rule dictionary keys — full text, O(n) substring checks are fast
            for key in self._sorted_rule_keys:
                if self._match_rule_key(key, clean_lower, clean_lower_stripped):
                    intent = self.rule_engine[key]
                    if self._is_negated_h07_launch_target(
                        intent.action_name, intent.parameters, clean_lower, clean_lower_stripped
                    ):
                        continue
                    res = IntentResult(
                        action_name=intent.action_name,
                        parameters=dict(intent.parameters),
                        confidence=1.0,
                        source="rule_fallback",
                        raw_text=text,
                        response_text=intent.response_text or self.get_natural_response(intent.action_name, intent.parameters, text),
                        requires_confirmation=intent.requires_confirmation,
                        confirmation_prompt=intent.confirmation_prompt,
                        danger_level=intent.danger_level,
                    )
                    return res

        # 2. TIER 2: LLM Semantic Reasoning
        if self.llm is None:
            return IntentResult(
                action_name="unknown_intent",
                parameters={"raw_text": text},
                confidence=0.0,
                source="rule_fast_path",
                raw_text=text,
                response_text="Tôi chưa hiểu lệnh này, vui lòng thử cách khác",
            )
        logger.info("Tier-1 fast-path miss for query %r; invoking Tier-2 LLM semantic reasoning", text)
        try:
            tools = None
            if self.dispatcher:
                tools = generate_tool_schema_from_dispatcher(self.dispatcher, filter_actions=available_actions)

            mem_ctx = None
            if self.memory_manager:
                try:
                    mem_ctx = self.memory_manager.get_system_prompt_context(query=text)
                except TypeError:
                    mem_ctx = self.memory_manager.get_system_prompt_context()
                except Exception as e:
                    logger.debug("Failed to get memory system prompt context: %s", e)

            system_prompt = build_jarvis_system_prompt(context_info=context, memory_context=mem_ctx)
            llm_resp = self.llm.generate(prompt=text, system_prompt=system_prompt, tools=tools)

            if isinstance(llm_resp, LLMResponse):
                if llm_resp.tool_calls:
                    top_tool = llm_resp.tool_calls[0]
                    params = top_tool.arguments
                    if isinstance(params, str):
                        try:
                            import json
                            params = json.loads(params)
                        except Exception:
                            params = {"raw": params}
                    elif not isinstance(params, dict):
                        params = {}
                    if self._is_negated_h07_launch_target(
                        top_tool.name, params, clean_lower, clean_lower_stripped
                    ):
                        return IntentResult(
                            action_name="unknown_intent",
                            parameters={"raw_text": text},
                            confidence=0.0,
                            source="rule_fallback",
                            raw_text=text,
                            response_text="Tôi sẽ không thực hiện lệnh mở đã bị phủ định, thưa Ngài.",
                        )
                    params = self._catalog_app_parameters(top_tool.name, params)
                    res = IntentResult(
                        action_name=top_tool.name,
                        parameters=params,
                        confidence=0.95,
                        source="llm",
                        reasoning=llm_resp.content,
                        raw_text=text,
                        llm_response=llm_resp,
                        response_text=self.get_natural_response(top_tool.name, params, text),
                    )
                    return res
                reply = llm_resp.content or ""
                return IntentResult(
                    action_name="generic_llm_response",
                    parameters={"reply": reply},
                    confidence=0.90,
                    source="llm",
                    raw_text=text,
                    llm_response=llm_resp,
                    response_text=reply,
                )
            else:
                reply = str(llm_resp)
                return IntentResult(
                    action_name="generic_llm_response",
                    parameters={"reply": reply},
                    confidence=0.90,
                    source="llm",
                    raw_text=text,
                    response_text=reply,
                )

        except Exception as exc:
            from jarvis.llm.client import LLMAuthenticationError
            if isinstance(exc, LLMAuthenticationError):
                logger.warning(
                    "LLM Tier-2 disabled: no API key for %s. "
                    "Set GEMINI_API_KEY in Credential Manager: "
                    "python -c \"import keyring; keyring.set_password('JARVIS', 'GEMINI_API_KEY', 'YOUR_KEY')\". "
                    "Get free key at https://aistudio.google.com/app/apikey",
                    getattr(self.llm, "provider", "llm"),
                )
            else:
                logger.warning("LLM intent routing encountered exception: %s. Initiating rule fallback.", exc)

            # 3. TIER 3: Graceful Rule Fallback on Error
            installed_intent = self._match_installed_app_request(text, explicit_only=True)
            if installed_intent is not None:
                if installed_intent.action_name == "app_open":
                    installed_intent.confidence = 0.85
                return installed_intent
            for pattern, extractor in self._regex_rules:
                m = pattern.search(clean_for_regex)
                if m:
                    res = extractor(m)
                    if self._is_negated_h07_launch_target(
                        res.action_name, res.parameters, clean_lower, clean_lower_stripped
                    ):
                        continue
                    res.raw_text = text
                    res.confidence = 0.85
                    if not res.response_text:
                        res.response_text = self.get_natural_response(res.action_name, res.parameters, text)
                    return res

            installed_intent = self._match_installed_app_request(text)
            if installed_intent is not None:
                if installed_intent.action_name == "app_open":
                    installed_intent.confidence = 0.85
                return installed_intent

            for key in self._sorted_rule_keys:
                if self._match_rule_key(key, clean_lower, clean_lower_stripped):
                    intent = self.rule_engine[key]
                    if self._is_negated_h07_launch_target(
                        intent.action_name, intent.parameters, clean_lower, clean_lower_stripped
                    ):
                        continue
                    return IntentResult(
                        action_name=intent.action_name,
                        parameters=dict(intent.parameters),
                        confidence=0.85,
                        source="rule_fallback",
                        raw_text=text,
                        response_text=intent.response_text or self.get_natural_response(intent.action_name, intent.parameters, text),
                        requires_confirmation=intent.requires_confirmation,
                        confirmation_prompt=intent.confirmation_prompt,
                        danger_level=intent.danger_level,
                    )

            return IntentResult(
                action_name="unknown_intent",
                parameters={"raw_text": text, "error": str(exc)},
                confidence=0.0,
                source="rule_fallback",
                raw_text=text,
                response_text="Tôi chưa hiểu lệnh này, vui lòng thử cách khác",
            )

    def execute_intent(
        self,
        intent: IntentResult,
        requester: str | RequesterContext = "system",
    ) -> ActionResult:
        """Executes the resolved IntentResult against the registered ActionDispatcher."""
        if not self.dispatcher:
            return ActionResult(
                action_name=intent.action_name,
                success=False,
                error="ActionDispatcher not configured on LLMIntentRouter.",
                error_code="DISPATCHER_UNAVAILABLE",
            )

        if intent.action_name == "generic_llm_response":
            return ActionResult(
                action_name="generic_llm_response",
                success=True,
                data={"reply": intent.parameters.get("reply", "")},
                requester=requester if isinstance(requester, str) else requester.requester_id,
            )

        if intent.action_name == "unknown_intent":
            return ActionResult(
                action_name="unknown_intent",
                success=False,
                error=f"Unrecognized intent for query: '{intent.raw_text}'",
                error_code="UNKNOWN_INTENT",
                requester=requester if isinstance(requester, str) else requester.requester_id,
            )

        return self.dispatcher.dispatch_action(
            action_name=intent.action_name,
            payload=intent.parameters,
            requester=requester,
        )
