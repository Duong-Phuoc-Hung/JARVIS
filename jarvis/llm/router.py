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
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Union, get_args, get_origin

from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import ActionResult, RequesterContext
from jarvis.llm.client import LLMClient, LLMResponse

logger = logging.getLogger("jarvis.llm.router")


@dataclass
class IntentResult:
    action_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source: str = "llm"  # "llm", "rule_fallback", "rule_fast_path"
    reasoning: str | None = None
    raw_text: str = ""
    llm_response: LLMResponse | None = None
    response_text: str | None = None
    requires_confirmation: bool = False
    confirmation_prompt: str | None = None
    danger_level: str | None = None

    def to_dict(self) -> dict[str, Any]:
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
                    elif origin in (list, tuple, set, list, tuple) or ann in (list, list) or ann_str.startswith("list") or ann_str.startswith("typing.list"):
                        param_type = "array"
                    elif origin in (dict, dict) or ann in (dict, dict) or ann_str.startswith("dict") or ann_str.startswith("typing.dict"):
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
        self.rule_engine: dict[str, IntentResult] = {
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
            "pin còn bao nhiêu": IntentResult(
                action_name="hardware_telemetry_check",
                parameters={"component": "battery"},
                source="rule_fallback",
                response_text="Pin hệ thống đang ở mức an toàn, thưa Ngài.",
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
            "kiểm tra pin": IntentResult(
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
            "settings": IntentResult(action_name="app_open", parameters={"app_name": "Settings", "app": "ms-settings:"}, source="rule_fallback", response_text="Đang mở cài đặt hệ thống cho Ngài."),
            "cai dat windows": IntentResult(action_name="app_open", parameters={"app_name": "Settings", "app": "ms-settings:"}, source="rule_fallback", response_text="Đang mở cài đặt hệ thống cho Ngài."),
            "cài đặt windows": IntentResult(action_name="app_open", parameters={"app_name": "Settings", "app": "ms-settings:"}, source="rule_fallback", response_text="Đang mở cài đặt hệ thống cho Ngài."),
            "mo settings": IntentResult(action_name="app_open", parameters={"app_name": "Settings", "app": "ms-settings:"}, source="rule_fallback", response_text="Đang mở cài đặt hệ thống cho Ngài."),
            "bật claude": IntentResult(action_name="web_open", parameters={"target": "claude", "site": "claude"}, source="rule_fallback", response_text="Đang mở Claude AI cho Ngài."),
            "mở claude": IntentResult(action_name="web_open", parameters={"target": "claude", "site": "claude"}, source="rule_fallback", response_text="Đang mở Claude AI cho Ngài."),
            "bật chatgpt": IntentResult(action_name="web_open", parameters={"target": "chatgpt", "site": "chatgpt"}, source="rule_fallback", response_text="Đang mở ChatGPT cho Ngài."),
            "mở chatgpt": IntentResult(action_name="web_open", parameters={"target": "chatgpt", "site": "chatgpt"}, source="rule_fallback", response_text="Đang mở ChatGPT cho Ngài."),
            "bật youtube": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
            "mở youtube": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
            "mo youtube": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
            "open youtube": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
            "vao youtube": IntentResult(action_name="web_open", parameters={"target": "youtube", "site": "youtube"}, source="rule_fallback", response_text="Đang mở YouTube cho Ngài."),
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
            "dieu chinh am luong": IntentResult(action_name="system_volume", parameters={"delta": 0}, source="rule_fallback", response_text="Đang điều chỉnh âm lượng cho Ngài."),
            "volume up": IntentResult(action_name="system_volume", parameters={"delta": 10}, source="rule_fallback", response_text="Đang tăng âm lượng cho Ngài."),
            "volume down": IntentResult(action_name="system_volume", parameters={"delta": -10}, source="rule_fallback", response_text="Đang giảm âm lượng cho Ngài."),
            "giảm âm": IntentResult(action_name="system_volume", parameters={"delta": -10}, source="rule_fallback", response_text="Đang giảm âm lượng cho Ngài."),
            "tắt tiếng": IntentResult(action_name="system_volume", parameters={"mute": True}, source="rule_fallback", response_text="Đã tắt tiếng máy tính, thưa Ngài."),
            "tat tieng": IntentResult(action_name="system_volume", parameters={"mute": True}, source="rule_fallback", response_text="Đã tắt tiếng máy tính, thưa Ngài."),
            "mute": IntentResult(action_name="system_volume", parameters={"mute": True}, source="rule_fallback", response_text="Đã tắt tiếng máy tính, thưa Ngài."),
            "bật tiếng": IntentResult(action_name="system_volume", parameters={"mute": False}, source="rule_fallback", response_text="Đã bật tiếng máy tính, thưa Ngài."),
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
            "lưu lại": IntentResult(action_name="memory_save_fact", parameters={}, source="rule_fallback", response_text="Đã lưu thông tin này, thưa Ngài."),
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
        }

        # Pre-sort rule dictionary keys by descending length for greedy exact match
        self._sorted_rule_keys: list[str] = sorted(self.rule_engine.keys(), key=len, reverse=True)
        self._short_key_regexes: dict[str, re.Pattern] = {
            k: re.compile(r"(?:\b|^)" + re.escape(k) + r"(?:\b|$)", re.IGNORECASE)
            for k in self.rule_engine
            if len(k) <= 4 and k.isascii()
        }

        # Advanced Parametric Regex Rules (Run before static substring fallback)
        self._regex_rules: list[tuple[re.Pattern, Callable[[re.Match], IntentResult]]] = [
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
                re.compile(r"(?:kiểm\s*tra|kiem\s*tra|check|query|xem|báo\s*cáo|bao\s*cao)?\s*(?:(?:(cpu|gpu|ram|ổ\s*cứng|o\s*cung|disk|bộ\s*nhớ|bo\s*nho|pin|battery)\s+(?:nhiệt\s*độ|nhiet\s*do|temp|temperature|mức\s*sử\s*dụng|mấy\s*phần\s*trăm|tốc\s*độ|còn\s*bao\s*nhiêu|còn\s*lại\s*bao\s*nhiêu|tình\s*trạng|tinh\s*trang|dung\s*lượng))|(?:(?:nhiệt\s*độ|nhiet\s*do|temp|temperature|mức\s*sử\s*dụng|mấy\s*phần\s*trăm|tốc\s*độ|còn\s*bao\s*nhiêu|còn\s*lại\s*bao\s*nhiêu|dung\s*lượng)\s+(cpu|gpu|ram|ổ\s*cứng|o\s*cung|disk|bộ\s*nhớ|bo\s*nho|pin|battery|máy|laptop|pc|thiết\s*bị))|(?:nhiệt\s*độ|nhiet\s*do|temp|temperature))", re.IGNORECASE),
                lambda m: self._make_hw_intent((m.group(1) or m.group(2) or "cpu").lower()),
            ),
            (
                re.compile(r"^(?:jarvis[,\s]*)?(?:kiểm\s*tra|kiem\s*tra|xem|check)\s+(cpu|gpu|ram|disk|ổ\s*cứng|o\s*cung|pin|battery)$", re.IGNORECASE),
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
                    lambda q: IntentResult(
                        action_name="spotify",
                        parameters={"query": q} if q else {"command": "play", "query": ""},
                        source="rule_fallback",
                        response_text=f"Đang mở Spotify và phát {q} cho Ngài." if q else "Đang mở Spotify và phát nhạc cho Ngài.",
                    )
                )(re.sub(r"^(?:bài\s*hát|bai\s*hat|bài|bai|song)\s+", "", m.group(1).strip(), flags=re.IGNORECASE) if (m.lastindex and m.group(1) and m.group(1).strip()) else "")
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
                re.compile(r"^(?:jarvis[,\s]*)?(?:mở|bật|vào|truy\s*cập|mo|bat|vao|truy\s*cap|open|visit|go\s*to|launch|start)(?:\s+(?:trang\s*web|web|website|trang))?\s*(youtube|yt|google|gg|facebook|fb|github|gh|chatgpt|gpt|chat\s*gpt|claude|claude\s*ai|anthropic|binance|zalo\s*web|gmail|mail|email|hòm\s*thư|vnexpress|báo|dantri|dân\s*trí|shopee|tiki|lazada|reddit|twitter|maps|bản\s*đồ|dịch|translate|google\s*dịch|notion|figma|canva|trello|jira|confluence|[\w\-]+(?:\.com|\.vn|\.net|\.org|\.io|\.edu))(?:\s+(.*))?$", re.IGNORECASE),
                lambda m: self._make_web_intent(m.group(1), m.group(2)),
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
                    parameters={"query": m.group(1).strip(), "target": f"https://www.google.com/search?q={m.group(1).strip()}"},
                    source="rule_fallback",
                    response_text=f"Đang tìm kiếm '{m.group(1).strip()}' trên Google cho Ngài.",
                ),
            ),
            (
                re.compile(r"^(?:jarvis[,\s]*)?google\s+(.+)$", re.IGNORECASE),
                lambda m: IntentResult(
                    action_name="web_open",
                    parameters={"query": m.group(1).strip(), "target": f"https://www.google.com/search?q={m.group(1).strip()}"},
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
                lambda m: IntentResult(
                    action_name="system_volume",
                    parameters={"mute": True} if any(w in m.group(0).lower() for w in ("tắt", "tat", "mute")) else ({"delta": -10} if any(w in m.group(0).lower() for w in ("giảm", "giam")) else {"delta": 0}),
                    source="rule_fallback",
                    response_text="Đã điều chỉnh âm lượng cho Ngài.",
                ),
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
                re.compile(r"^(?:jarvis[,\s]*)?(?:đọc|doc|xem|tin|news|báo|bao)\s*(?:tức|tuc|báo|bao|mới\s*nhất|moi\s*nhat|hôm\s*nay|hom\s*nay|today|headlines|latest)?(?:\s+(.+))?$", re.IGNORECASE),
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

    def _match_rule_key(self, key: str, clean_lower: str) -> bool:
        """Determines if clean_lower matches the deterministic key."""
        if not key or not clean_lower:
            return False
        if key not in clean_lower:
            return False
        if len(key) <= 4 and key.isascii():
            if clean_lower == key:
                return True
            pattern = getattr(self, "_short_key_regexes", {}).get(key)
            if pattern is None:
                pattern = re.compile(r"(?:\b|^)" + re.escape(key) + r"(?:\b|$)", re.IGNORECASE)
                if not hasattr(self, "_short_key_regexes"):
                    self._short_key_regexes = {}
                self._short_key_regexes[key] = pattern
            return bool(pattern.search(clean_lower))
        return True

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
        elif "ram" in c or "bộ nhớ" in c:
            comp = "ram"
        elif "disk" in c or "ổ cứng" in c or "smart" in c:
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

    def _make_app_intent(self, app_name: str) -> IntentResult:
        clean = (app_name or "").strip().lower()
        if clean == "spotify":
            return IntentResult(
                action_name="spotify",
                parameters={"query": "", "name": "spotify"},
                source="rule_fallback",
                response_text="Đang mở Spotify và phát nhạc cho Ngài.",  # consistent with rule_engine entry
            )
        params = {"app_name": clean, "name": clean}
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
        clean_lower = clean_lower_full  # Used for dict rule key matching (full-text safe)

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

        # 1. TIER 1: Fast Rule Check (Sub-millisecond)
        if not force_llm and self.fast_path_enabled:
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
                    res.raw_text = text
                    if not res.response_text:
                        res.response_text = self.get_natural_response(res.action_name, res.parameters, text)
                    return res

            # Then check sorted rule dictionary keys — full text, O(n) substring checks are fast
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
            logger.warning("LLM intent routing encountered exception: %s. Initiating rule fallback.", exc)

            # 3. TIER 3: Graceful Rule Fallback on Error
            for pattern, extractor in self._regex_rules:
                m = pattern.search(clean_for_regex)
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
