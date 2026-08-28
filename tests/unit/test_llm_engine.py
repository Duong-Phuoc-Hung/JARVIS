"""
tests/unit/test_llm_engine.py
=============================
Unit tests for JARVIS LLM Semantic Intent Subsystem (F-15).
Covers:
  - LLMClient multi-provider normalization (OpenAI, Gemini, Claude, Ollama, Mock)
  - TokenUsage tracking and cost estimation
  - Mock client behaviors, error injection, canned responses, call history
  - Dynamic tool schema generation from ActionDispatcher
  - Bilingual system prompt builder
  - Two-tier LLMIntentRouter (fast rules, LLM semantic tool calling, error fallback)
  - Action execution bridge via ActionDispatcher
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from jarvis.core.dispatcher import ActionDispatcher, EventBus
from jarvis.core.models import ActionResult, PrivilegeLevel
from jarvis.llm.client import (
    ChatMessage,
    LLMAuthenticationError,
    LLMClient,
    LLMError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponse,
    LLMTimeoutError,
    TokenUsage,
    ToolCall,
)
from jarvis.llm.router import (
    IntentResult,
    LLMIntentRouter,
    build_jarvis_system_prompt,
    generate_tool_schema_from_dispatcher,
)

# ============================================================================
# 1. LLMCLIENT INITIALIZATION & MULTI-PROVIDER TESTS
# ============================================================================

def test_llm_client_initialization_all_providers():
    """Verify LLMClient initialization for OpenAI, Gemini, Claude, Ollama, Mock."""
    c_openai = LLMClient(provider="openai", api_key="sk-test-key")
    assert c_openai.provider == LLMProvider.OPENAI
    assert c_openai.model == "gpt-4o"

    c_gemini = LLMClient(provider="gemini", api_key="test-key")
    assert c_gemini.provider == LLMProvider.GEMINI

    c_claude = LLMClient(provider="claude", api_key="test-key")
    assert c_claude.provider == LLMProvider.CLAUDE

    c_ollama = LLMClient(provider="ollama")
    assert c_ollama.provider == LLMProvider.OLLAMA

    c_mock = LLMClient(provider="mock")
    assert c_mock.provider == LLMProvider.MOCK


def test_llm_client_missing_key_raises_auth_error():
    """Verify missing API key raises LLMAuthenticationError / PermissionError."""
    client = LLMClient(provider="openai", api_key="")
    with pytest.raises(LLMAuthenticationError):
        client.generate("Hello JARVIS")

    with pytest.raises(PermissionError):
        client.generate("Hello JARVIS")


def test_llm_client_mock_behavior_and_call_history():
    """Test programmable mock behaviors, rules, canned responses, and call history."""
    client = LLMClient(provider="mock")

    # 1. Custom mock rules
    client.set_mock_behavior(rules={
        "turn on lamp": {"tool": "home_assistant_call", "args": {"entity_id": "light.desk_lamp"}},
        "weather": "Sunny and 25C",
    })

    resp_tool = client.generate("Please turn on lamp now")
    assert isinstance(resp_tool, LLMResponse)
    assert len(resp_tool.tool_calls) == 1
    assert resp_tool.tool_calls[0].name == "home_assistant_call"
    assert resp_tool.tool_calls[0].arguments["entity_id"] == "light.desk_lamp"

    resp_text = client.generate("What is the weather today?")
    assert "Sunny and 25C" in resp_text.content

    # 2. Canned response queue
    canned = LLMResponse(content="Canned response 1", provider="mock", success=True)
    client.set_mock_behavior(canned_responses=[canned])
    resp_canned = client.generate("Any prompt")
    assert resp_canned.content == "Canned response 1"

    # 3. Call history verification
    assert len(client.call_history) >= 3


def test_llm_client_mock_error_injections():
    """Test mock error injections (rate limit, timeout, auth)."""
    client = LLMClient(provider="mock")

    client.set_mock_behavior(mock_error="rate_limit")
    with pytest.raises(LLMRateLimitError):
        client.generate("test")

    client.set_mock_behavior(mock_error="timeout")
    with pytest.raises(LLMTimeoutError):
        client.generate("test")

    client.set_mock_behavior(mock_error="auth_error")
    with pytest.raises(LLMAuthenticationError):
        client.generate("test")


def test_llm_client_token_usage_and_cost_estimation():
    """Test token usage accumulation and USD cost estimation."""
    client = LLMClient(provider="openai", model="gpt-4o")
    usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
    client._update_usage(usage, "gpt-4o")

    assert client._total_usage.prompt_tokens == 1000
    assert client._total_usage.completion_tokens == 500
    assert client._total_usage.total_tokens == 1500
    # gpt-4o pricing: $2.50 / 1M prompt + $10.00 / 1M completion
    expected_cost = (1000 / 1e6 * 2.50) + (500 / 1e6 * 10.00)
    assert pytest.approx(client._total_usage.estimated_cost_usd, abs=1e-5) == expected_cost


def test_llm_client_clean_and_parse_json():
    """Test JSON cleaning with markdown code blocks and regex recovery."""
    client = LLMClient(provider="mock")

    # Clean JSON
    assert client._clean_and_parse_json('{"key": "value"}') == {"key": "value"}

    # Markdown fenced JSON
    fenced = "```json\n{\n  \"action\": \"test_action\",\n  \"count\": 5\n}\n```"
    parsed = client._clean_and_parse_json(fenced)
    assert parsed["action"] == "test_action"
    assert parsed["count"] == 5

    # Malformed text regex extraction fallback
    malformed = "action: 'spotify_play', track: 'daft_punk'"
    res = client._clean_and_parse_json(malformed)
    assert res.get("action") == "spotify_play"


# ============================================================================
# 2. SCHEMA GENERATOR & PROMPT BUILDER TESTS
# ============================================================================

def test_generate_tool_schema_from_dispatcher():
    """Test dynamic tool schema generation inspecting ActionDispatcher."""
    dispatcher = ActionDispatcher()

    # 1. Action with explicit schema
    dispatcher.register_action(
        name="custom_action",
        handler=lambda x: x,
        schema={"type": "object", "properties": {"target": {"type": "string"}}},
        description="Custom action with explicit schema",
    )

    # 2. Action with dynamic python signature
    def sample_handler(component: str, timeout: int = 5) -> Dict:
        return {}

    dispatcher.register_action(
        name="dynamic_action",
        handler=sample_handler,
        description="Dynamic signature action",
    )

    tools = generate_tool_schema_from_dispatcher(dispatcher)
    assert len(tools) == 2

    tool_names = [t["function"]["name"] for t in tools]
    assert "custom_action" in tool_names
    assert "dynamic_action" in tool_names

    # Check dynamic signature schema properties
    dyn_tool = next(t for t in tools if t["function"]["name"] == "dynamic_action")
    params = dyn_tool["function"]["parameters"]["properties"]
    assert "component" in params
    assert "timeout" in params
    assert params["component"]["type"] == "string"
    assert params["timeout"]["type"] == "integer"


def test_build_jarvis_system_prompt():
    """Test bilingual system prompt generator embedding persona and context."""
    prompt = build_jarvis_system_prompt(context_info={"Host": "DESKTOP-JARVIS", "OS": "Windows 11"})
    assert "JARVIS" in prompt
    assert "DESKTOP-JARVIS" in prompt
    assert "home_assistant_call" in prompt
    assert "hardware_telemetry_check" in prompt


# ============================================================================
# 3. TWO-TIER INTENT ROUTER TESTS
# ============================================================================

def test_intent_router_tier1_fast_rules():
    """Test sub-millisecond Tier 1 fast rule table and regex matches."""
    client = LLMClient(provider="mock")
    router = LLMIntentRouter(client)

    # Exact / Substring commands
    r1 = router.parse_intent("bật đèn phòng khách")
    assert r1.action_name == "home_assistant_call"
    assert r1.parameters["service"] == "turn_on"
    assert r1.source == "rule_fallback"

    r2 = router.parse_intent("tắt đèn phòng khách")
    assert r2.action_name == "home_assistant_call"
    assert r2.parameters["service"] == "turn_off"

    r3 = router.parse_intent("kiểm tra nhiệt độ cpu")
    assert r3.action_name == "hardware_telemetry_check"
    assert r3.parameters["component"] == "cpu"

    r4 = router.parse_intent("tình trạng hệ thống")
    assert r4.action_name == "hardware_status_query"

    r5 = router.parse_intent("quét mạng nội bộ")
    assert r5.action_name == "security_nmap_scan"
    assert r5.parameters["target"] == "192.168.1.0/24"

    r6 = router.parse_intent("mở spotify")
    assert r6.action_name == "spotify"

    r7 = router.parse_intent("chuẩn bị môi trường làm việc")
    assert r7.action_name == "workspace_prepare"

    r8 = router.parse_intent("tự phục hồi hệ thống")
    assert r8.action_name == "healing_watchdog_heal"


def test_intent_router_tier1_parametric_regex():
    """Test flexible regex pattern matching for variations in Vietnamese and English."""
    client = LLMClient(provider="mock")
    router = LLMIntentRouter(client)

    # Regex variation: "Jarvis, turn on light living room please"
    res_en = router.parse_intent("turn on light living room")
    assert res_en.action_name == "home_assistant_call"
    assert res_en.parameters["service"] == "turn_on"

    # Regex variation: "check temp gpu"
    res_gpu = router.parse_intent("check temperature gpu")
    assert res_gpu.action_name == "hardware_telemetry_check"
    assert res_gpu.parameters["component"] == "gpu"

    # Regex variation: "scan subnet 10.0.0.0/24"
    res_scan = router.parse_intent("scan network 10.0.0.0/24")
    assert res_scan.action_name == "security_nmap_scan"
    assert res_scan.parameters["target"] == "10.0.0.0/24"


def test_intent_router_tier2_llm_tool_calling():
    """Test Tier 2 LLM semantic reasoning and tool call extraction."""
    client = LLMClient(provider="mock")
    client.set_mock_behavior(rules={
        "analyze data": {
            "tool": "data_analysis_run",
            "args": {"dataset": "sales.csv", "mode": "monte_carlo"},
        }
    })

    router = LLMIntentRouter(client)
    res = router.parse_intent("Jarvis, please analyze data for sales.csv with monte carlo simulation", force_llm=True)

    assert res.source == "llm"
    assert res.action_name == "data_analysis_run"
    assert res.parameters["dataset"] == "sales.csv"
    assert res.confidence >= 0.90


def test_intent_router_tier2_conversational_natural_reply():
    """Test Tier 2 conversational reply mapping to generic_llm_response."""
    client = LLMClient(provider="mock")
    client.set_mock_behavior(rules={
        "who are you": "I am JARVIS, your personal desktop AI assistant, Sir.",
    })

    router = LLMIntentRouter(client)
    res = router.parse_intent("Who are you?", force_llm=True)

    assert res.source == "llm"
    assert res.action_name == "generic_llm_response"
    assert "JARVIS" in res.parameters["reply"]


def test_intent_router_tier3_graceful_error_fallback():
    """Test Tier 3 rule fallback when LLM encounters error (e.g. rate limit)."""
    client = LLMClient(provider="mock")
    client.set_mock_behavior(mock_error="rate_limit")

    router = LLMIntentRouter(client)
    # Known command phrase falls back gracefully to rule
    res = router.parse_intent("kiểm tra nhiệt độ cpu", force_llm=True)
    assert res.source == "rule_fallback"
    assert res.action_name == "hardware_telemetry_check"

    # Completely unrecognized phrase returns unknown_intent without crashing
    res_unknown = router.parse_intent("random nonsense queryxyz", force_llm=True)
    assert res_unknown.action_name == "unknown_intent"
    assert res_unknown.confidence == 0.0


def test_intent_router_execute_intent():
    """Test execute_intent bridge executing actions on ActionDispatcher."""
    dispatcher = ActionDispatcher()
    executed = []
    dispatcher.register_action(
        name="test_service",
        handler=lambda target: executed.append(target) or {"status": "ok"},
        description="Test action",
    )

    client = LLMClient(provider="mock")
    router = LLMIntentRouter(client, dispatcher=dispatcher)

    # 1. Normal tool execution
    intent = IntentResult(action_name="test_service", parameters={"target": "printer_1"})
    res = router.execute_intent(intent)
    assert res.success is True
    assert "printer_1" in executed

    # 2. Generic LLM response
    intent_chat = IntentResult(action_name="generic_llm_response", parameters={"reply": "Hello Sir"})
    res_chat = router.execute_intent(intent_chat)
    assert res_chat.success is True
    assert res_chat.data["reply"] == "Hello Sir"

    # 3. Unknown intent
    intent_unknown = IntentResult(action_name="unknown_intent", parameters={})
    res_unknown = router.execute_intent(intent_unknown)
    assert res_unknown.success is False
