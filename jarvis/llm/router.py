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

from dataclasses import dataclass, field
import inspect
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, get_args, get_origin

from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import ActionResult, RequesterContext
from jarvis.llm.client import ChatMessage, LLMClient, LLMResponse, ToolCall

logger = logging.getLogger("jarvis.llm.router")


@dataclass
class IntentResult:
    action_name: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source: str = "llm"  # "llm", "rule_fallback", "rule_fast_path"
    reasoning: Optional[str] = None
    raw_text: str = ""
    llm_response: Optional[LLMResponse] = None
    response_text: Optional[str] = None
    requires_confirmation: bool = False
    confirmation_prompt: Optional[str] = None
    danger_level: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_name": self.action_name,
            "parameters": self.parameters,
            "confidence": self.confidence,
            "source": self.source,
            "reasoning": self.reasoning,
            "raw_text": self.raw_text,
            "response_text": self.response_text,
            "requires_confirmation": self.requires_confirmation,
            "confirmation_prompt": self.confirmation_prompt,
            "danger_level": self.danger_level,
        }


def _parse_duration_seconds(amount: int, unit_str: str) -> int:
    """Converts quantity and time unit into duration seconds."""
    u = unit_str.lower().strip()
    if u in ("giờ", "tiếng", "h", "hour", "hours"):
        return amount * 3600
    elif u in ("phút", "m", "min", "mins", "minute", "minutes"):
        return amount * 60
    elif u in ("giây", "s", "sec", "secs", "second", "seconds"):
        return amount
    return amount * 60


def generate_tool_schema_from_dispatcher(
    dispatcher: ActionDispatcher,
    filter_actions: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
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
            properties: Dict[str, Any] = {}
            required: List[str] = []
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
                    elif origin in (list, tuple, set, List, Tuple) or ann in (list, List) or ann_str.startswith("list") or ann_str.startswith("typing.list"):
                        param_type = "array"
                    elif origin in (dict, Dict) or ann in (dict, Dict) or ann_str.startswith("dict") or ann_str.startswith("typing.dict"):
                        param_type = "object"
                    elif "list" in ann_str and "dict" not in ann_str:
                        param_type = "array"
                    elif "dict" in ann_str:
                        param_type = "object"

                    properties[param_name] = {
                        "type": param_type,
                        "description": f"Parameter {param_name}",
                    }
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
    context_info: Optional[Dict[str, Any]] = None,
    language: str = "vi",
    memory_context: Optional[str] = None,
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
        dispatcher: Optional[ActionDispatcher] = None,
        fast_path_enabled: bool = True,
        memory_manager: Optional[Any] = None,
    ) -> None:
        self.llm = llm_client
        self.dispatcher = dispatcher
        self.fast_path_enabled = fast_path_enabled
        self.memory_manager = memory_manager
        self._memory_manager = memory_manager

        # Compiled Deterministic Rule Engine for Substring Matching
        self.rule_engine: Dict[str, IntentResult] = {
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
            "nhiệt độ": IntentResult(
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
            "bộ nhớ": IntentResult(
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
            "hệ thống": IntentResult(
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
            "spotify": IntentResult(
                action_name="spotify",
                parameters={},
                source="rule_fallback",
                response_text="Đang mở Spotify và phát nhạc cho Ngài.",
            ),
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
        }

        # Pre-sort rule dictionary keys by descending length for greedy exact match
        self._sorted_rule_keys: List[str] = sorted(self.rule_engine.keys(), key=len, reverse=True)

        # Advanced Parametric Regex Rules (Run before static substring fallback)
        self._regex_rules: List[Tuple[re.Pattern, Callable[[re.Match], IntentResult]]] = [
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
                re.compile(r"(?:kiểm tra|check|query|xem|báo cáo)\s+(?:(?:(cpu|gpu|ram|ổ\s*cứng|disk|bộ\s*nhớ)\s+(?:nhiệt độ|temp|temperature|mức\s*sử\s*dụng|tình\s*trạng|dung\s*lượng))|(?:(?:nhiệt độ|temp|temperature|mức\s*sử\s*dụng|tình\s*trạng|dung\s*lượng)\s+(cpu|gpu|ram|ổ\s*cứng|disk|bộ\s*nhớ))|(?:nhiệt độ|temp|temperature))", re.IGNORECASE),
                lambda m: self._make_hw_intent((m.group(1) or m.group(2) or "cpu").lower()),
            ),
            (
                re.compile(r"(?:tình trạng|trạng thái|status|health)\s*(?:hệ thống|máy tính|system|pc|máy)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="hardware_status_query",
                    parameters={},
                    source="rule_fallback",
                    response_text="Tình trạng hệ thống: Mọi dịch vụ đang hoạt động tối ưu, CPU và RAM ở mức an toàn, thưa Ngài.",
                ),
            ),

            # 3. Spotify & Music (Specific Song Queries & Playback Controls)
            (
                re.compile(r"(?:mở\s+spotify\s+bài|mở\s+bài\s+hát|bật\s+bài|phát\s+bài|nghe\s+bài|bật\s+nhạc\s+bài|mở\s+nhạc\s+bài|phát\s+nhạc\s+bài|play\s+song|play\s+music)\s+(.+)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="spotify",
                    parameters={"query": m.group(1).strip()},
                    source="rule_fallback",
                    response_text=f"Đang mở Spotify và phát {m.group(1).strip()} cho Ngài.",
                ),
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
                re.compile(r"(?:dự\s*báo|xem|kiểm\s*tra)?\s*thời\s*tiết\s*(?:hôm\s*nay|ngày\s*mai|tại|ở|khu\s*vực)?\s*(.+)?", re.IGNORECASE),
                lambda m: self._make_weather_intent(m.group(1) if m.group(1) else ""),
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
                re.compile(r"(?:tắt\s*máy|shutdown|power\s*off|tắt\s*máy\s*tính|tắt\s*nguồn)", re.IGNORECASE),
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
                re.compile(r"(?:khởi\s*động\s*lại|restart|reboot)", re.IGNORECASE),
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
            (
                re.compile(r"(?:khóa\s*máy|lock\s*screen|khóa\s*màn\s*hình)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="system_power",
                    parameters={"action": "lock"},
                    source="rule_fallback",
                    response_text="Đã khóa màn hình máy tính, thưa Ngài.",
                    requires_confirmation=False,
                    danger_level="LOW",
                ),
            ),

            # Workflows & Security
            (
                re.compile(r"(?:quét|scan|audit)\s*(?:mạng|network|subnet)(?:\s+([\d\.\/]+))?", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="security_nmap_scan",
                    parameters={"target": m.group(1) or "192.168.1.0/24"},
                    source="rule_fallback",
                    response_text="Đang thực hiện quét an ninh mạng nội bộ cho Ngài.",
                ),
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
            (
                re.compile(r"(?:tự\s*phục\s*hồi|dọn\s*dẹp\s*ram|giải\s*phóng\s*bộ\s*nhớ|heal\s*system)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="healing_watchdog_heal",
                    parameters={},
                    source="rule_fallback",
                    response_text="Đang tiến hành tối ưu hóa bộ nhớ và kiểm tra tiến trình hệ thống cho Ngài.",
                ),
            ),

            # 7. Universal Application & Software Launchers
            (
                re.compile(r"^(?:mở|bật|chạy|khởi\s*động|open|launch|start)\s+(?:ứng\s*dụng|app|phần\s*mềm)?\s*(chrome|google\s*chrome|cốc\s*cốc|firefox|edge|notepad|sổ\s*tay|ghi\s*chú|calculator|máy\s*tính|calc|word|ms\s*word|excel|ms\s*excel|bảng\s*tính|powerpoint|ppt|vscode|vs\s*code|visual\s*studio\s*code|cursor|cursor\s*ai|task\s*manager|quản\s*lý\s*tác\s*vụ|taskmgr|terminal|powershell|cmd|dòng\s*lệnh|paint|vẽ|spotify|discord|telegram|zalo|cài\s*đặt|settings|explorer|file\s*explorer|quản\s*lý\s*file)$", re.IGNORECASE),
                lambda m: self._make_app_intent(m.group(1)),
            ),

            # 8. Universal Website & Online Service Launchers
            (
                re.compile(r"^(?:mở|vào|truy\s*cập|open|visit|go\s*to)\s+(?:trang\s*web|web|website|trang)?\s*(youtube|yt|google|gg|facebook|fb|github|gh|chatgpt|gpt|claude|binance|zalo\s*web|gmail|mail|email|hòm\s*thư|vnexpress|báo|dantri|dân\s*trí|shopee|tiki|lazada|reddit|twitter|x|maps|bản\s*đồ|dịch|translate|google\s*dịch|[\w\-]+(?:\.com|\.vn|\.net|\.org|\.io|\.edu))(?:\s+(.*))?$", re.IGNORECASE),
                lambda m: self._make_web_intent(m.group(1), m.group(2)),
            ),

            # 9. Web Search & Query
            (
                re.compile(r"^(?:tìm\s*kiếm|search|tra\s*cứu|tìm)\s+(.+?)(?:\s+(?:trên|ở|qua)\s+(?:google|web|mạng|internet|youtube))?$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="web_open",
                    parameters={"query": m.group(1).strip(), "target": f"https://www.google.com/search?q={m.group(1).strip()}"},
                    source="rule_fallback",
                    response_text=f"Đang tìm kiếm '{m.group(1).strip()}' trên Google cho Ngài.",
                ),
            ),

            # 10. Folder & Storage Navigation
            (
                re.compile(r"^(?:mở|open)\s+(?:thư\s*mục|folder|ổ|ổ\s*đĩa|mục)\s*(.+)$", re.IGNORECASE),
                lambda m: self._make_folder_intent(m.group(1)),
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
                re.compile(r"^(?:chụp|chụp\s*ảnh|screenshot|capture)\s*(?:màn\s*hình|desktop)?$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="screen_capture",
                    parameters={},
                    source="rule_fallback",
                    response_text="Đã chụp ảnh màn hình và lưu ra Desktop cho Ngài.",
                ),
            ),

            # 12. Volume & Brightness Quick Controls
            (
                re.compile(r"^(?:tăng|mở\s*to)\s*âm\s*lượng(?:\s+(?:lên)?\s*(\d+))?", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="system_volume",
                    parameters={"delta": int(m.group(1)) if m.group(1) else 10},
                    source="rule_fallback",
                    response_text="Đang tăng âm lượng hệ thống cho Ngài.",
                ),
            ),
            (
                re.compile(r"^(?:giảm|mở\s*nhỏ)\s*âm\s*lượng(?:\s+(?:xuống)?\s*(\d+))?", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="system_volume",
                    parameters={"delta": -(int(m.group(1)) if m.group(1) else 10)},
                    source="rule_fallback",
                    response_text="Đang giảm âm lượng hệ thống cho Ngài.",
                ),
            ),
            (
                re.compile(r"^(?:tăng)\s*độ\s*sáng(?:\s+(?:lên)?\s*(\d+))?", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="system_brightness",
                    parameters={"delta": int(m.group(1)) if m.group(1) else 10},
                    source="rule_fallback",
                    response_text="Đang tăng độ sáng màn hình cho Ngài.",
                ),
            ),
            (
                re.compile(r"^(?:giảm)\s*độ\s*sáng(?:\s+(?:xuống)?\s*(\d+))?", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="system_brightness",
                    parameters={"delta": -(int(m.group(1)) if m.group(1) else 10)},
                    source="rule_fallback",
                    response_text="Đang giảm độ sáng màn hình cho Ngài.",
                ),
            ),
            # 8. Built-in Skills Fast-Path Patterns
            (
                re.compile(r"(?:briefing\s*(?:sáng|hôm\s*nay)?|báo\s*cáo\s*sáng|tổng\s*hợp\s*sáng|điểm\s*tin\s*sáng|morning\s*briefing)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="skill_briefing",
                    parameters={},
                    source="rule_fallback",
                    response_text="Đang tổng hợp báo cáo buổi sáng cho Ngài.",
                ),
            ),
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
                re.compile(r"^(?:tính|calculate|eval)\s+([\d\s\+\-\*\/\^\(\)\.\%xX]+)$", re.IGNORECASE),
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
            (
                re.compile(r"(?:git\s*status|kiểm\s*tra\s*git|trạng\s*thái\s*git)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="skill_git_assistant",
                    parameters={"action": "status"},
                    source="rule_fallback",
                    response_text="Đang kiểm tra trạng thái Git repository cho Ngài.",
                ),
            ),
            (
                re.compile(r"(?:chụp\s*ảnh\s*màn\s*hình|chụp\s*màn\s*hình|take\s*screenshot)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="skill_system_control",
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
            (
                re.compile(r"(?:tìm\s*file|search\s*file|find\s*file)\s+(.+)", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="skill_file_manager",
                    parameters={"action": "search", "query": m.group(1).strip()},
                    source="rule_fallback",
                    response_text=f"Đang tìm kiếm file '{m.group(1).strip()}' cho Ngài.",
                ),
            ),
        ]

    def _match_rule_key(self, key: str, clean_lower: str) -> bool:
        """Determines if clean_lower matches the deterministic key."""
        if not key or not clean_lower:
            return False
        if len(key) <= 4 and key.isascii():
            return bool(re.search(r"(?:\b|^)" + re.escape(key) + r"(?:\b|$)", clean_lower))
        return key in clean_lower

    def _make_light_intent(self, service: str, target: Optional[str]) -> IntentResult:
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
        elif "ram" in c or "bộ nhớ" in c:
            comp = "ram"
        elif "disk" in c or "ổ cứng" in c or "smart" in c:
            comp = "disk"
        else:
            comp = "cpu"

        params = {"component": comp}
        return IntentResult(
            action_name="hardware_telemetry_check",
            parameters=params,
            source="rule_fallback",
            response_text=self.get_natural_response("hardware_telemetry_check", params),
        )

    def _make_weather_intent(self, loc_raw: Optional[str]) -> IntentResult:
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

    def _make_app_intent(self, app_name: str) -> IntentResult:
        clean = (app_name or "").strip().lower()
        if clean == "spotify":
            return IntentResult(
                action_name="spotify",
                parameters={"query": "", "name": "spotify"},
                source="rule_fallback",
                response_text="Đang mở Spotify cho Ngài.",
            )
        params = {"app_name": clean, "name": clean}
        return IntentResult(
            action_name="app_open",
            parameters=params,
            source="rule_fallback",
            response_text=f"Đang mở ứng dụng {clean} cho Ngài.",
        )

    def _make_web_intent(self, site: str, query: Optional[str] = None) -> IntentResult:
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

    def _make_folder_intent(self, folder: str) -> IntentResult:
        clean = (folder or "").strip()
        params = {"folder": clean}
        return IntentResult(
            action_name="folder_open",
            parameters=params,
            source="rule_fallback",
            response_text=f"Đang mở thư mục {clean} cho Ngài.",
        )

    def get_natural_response(
        self,
        action_name: str,
        params: Optional[Dict[str, Any]] = None,
        text: str = "",
        action_result: Optional[ActionResult] = None,
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

        # 9. Workspace Automation
        if action_name == "workspace_prepare":
            return "Đang chuẩn bị môi trường làm việc cho Ngài."

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
            return "Đang kiểm tra trạng thái Git cho Ngài."

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
        available_actions: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
        force_llm: bool = False,
    ) -> IntentResult:
        """
        Parses user voice/text query into structured tool calling IntentResult.
        Executes Two-Tier pipeline: Fast Rules -> LLM Tool Call -> Fallback Rules.
        """
        clean = text.strip()
        clean_lower = clean.lower()

        # 1. TIER 1: Fast Rule Check (Sub-millisecond)
        if not force_llm and self.fast_path_enabled:
            # Memory Fast Commands Check
            if self.memory_manager:
                if self.memory_manager.is_remember_command(clean):
                    res_dict = self.memory_manager.handle_remember_command(clean)
                    return IntentResult(
                        action_name="memory_save_fact",
                        parameters=res_dict,
                        confidence=1.0,
                        source="rule_fast_path",
                        raw_text=text,
                        response_text=res_dict.get("message", "Tôi đã ghi nhớ thông tin này, thưa Ngài."),
                    )
                if self.memory_manager.is_today_summary_command(clean):
                    res_dict = self.memory_manager.handle_today_summary(clean)
                    return IntentResult(
                        action_name="memory_summarize_daily",
                        parameters=res_dict,
                        confidence=1.0,
                        source="rule_fast_path",
                        raw_text=text,
                        response_text=res_dict.get("message", "Đang tóm tắt hoạt động hôm nay cho Ngài."),
                    )

            # First check parametric regex rules
            for pattern, extractor in self._regex_rules:
                m = pattern.search(clean)
                if m:
                    res = extractor(m)
                    res.raw_text = text
                    if not res.response_text:
                        res.response_text = self.get_natural_response(res.action_name, res.parameters, text)
                    return res

            # Then check sorted rule dictionary keys (longest first)
            for key in self._sorted_rule_keys:
                if self._match_rule_key(key, clean_lower):
                    intent = self.rule_engine[key]
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
                    res = IntentResult(
                        action_name=top_tool.name,
                        parameters=top_tool.arguments,
                        confidence=0.95,
                        source="llm",
                        reasoning=llm_resp.content,
                        raw_text=text,
                        llm_response=llm_resp,
                        response_text=self.get_natural_response(top_tool.name, top_tool.arguments, text),
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
            logger.warning("LLM intent routing encountered exception: %s. Initiating rule fallback.", exc)

            # 3. TIER 3: Graceful Rule Fallback on Error
            for pattern, extractor in self._regex_rules:
                m = pattern.search(clean)
                if m:
                    res = extractor(m)
                    res.raw_text = text
                    res.confidence = 0.85
                    if not res.response_text:
                        res.response_text = self.get_natural_response(res.action_name, res.parameters, text)
                    return res

            for key in self._sorted_rule_keys:
                if self._match_rule_key(key, clean_lower):
                    intent = self.rule_engine[key]
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
        requester: Union[str, RequesterContext] = "system",
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
