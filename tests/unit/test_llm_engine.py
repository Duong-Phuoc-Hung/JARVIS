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
import requests

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
# 1B. LLM PROVIDER TRUTHFULNESS TESTS (v4.5.2 P0 hotfix)
# A real configured provider's request failure must never silently become a
# synthetic mock success. Mock behavior remains available ONLY through an
# explicit provider=MOCK or mock_mode=True path.
# ============================================================================

def test_llm_explicit_mock_provider_still_returns_deterministic_success():
    """[1] Explicit provider='mock' still returns deterministic mock success."""
    client = LLMClient(provider="mock")
    resp = client.generate("Hello")
    assert resp.success is True
    assert "mock" in resp.provider


def test_llm_explicit_mock_mode_on_real_provider_still_uses_mock(monkeypatch):
    """[2] Explicit mock_mode=True on a real provider still intentionally uses mock."""
    def _fail_post(*args, **kwargs):
        raise AssertionError("A real HTTP call must not happen when mock_mode=True")

    client = LLMClient(provider="openai", api_key="sk-real-looking-key", mock_mode=True)
    monkeypatch.setattr(client.session, "post", _fail_post)

    resp = client.generate("Hello")
    assert resp.success is True
    assert resp.provider == "openai"


def test_llm_invalid_provider_string_does_not_become_mock():
    """[3] An invalid provider string must fail closed, not silently become MOCK."""
    with pytest.raises(ValueError) as exc_info:
        LLMClient(provider="definitely-not-a-provider")
    assert "definitely-not-a-provider" in str(exc_info.value)


@pytest.mark.parametrize("exc_to_raise", [
    requests.ConnectionError("Connection refused"),
    requests.Timeout("Request timed out"),
])
def test_llm_ollama_real_failure_never_calls_execute_mock(monkeypatch, exc_to_raise):
    """[4][5] Real OLLAMA connection failure/timeout must never call _execute_mock()."""
    def _fail_execute_mock(*args, **kwargs):
        raise AssertionError("_execute_mock() must not be called for a real OLLAMA failure")

    def _raise(*args, **kwargs):
        raise exc_to_raise

    client = LLMClient(provider="ollama", max_retries=0)
    monkeypatch.setattr(client, "_execute_mock", _fail_execute_mock)
    monkeypatch.setattr(client.session, "post", _raise)
    monkeypatch.setattr("time.sleep", lambda *a, **k: None)

    if isinstance(exc_to_raise, requests.Timeout):
        with pytest.raises(LLMTimeoutError):
            client.generate("Local prompt")
    else:
        with pytest.raises(LLMProviderError):
            client.generate("Local prompt")


def test_llm_ollama_connection_error_respects_retry_policy(monkeypatch):
    """[4] Ollama ConnectionError retries per max_retries, then raises truthfully (no mock)."""
    call_count = {"n": 0}

    def _raise(*args, **kwargs):
        call_count["n"] += 1
        raise requests.ConnectionError("Connection refused")

    def _fail_execute_mock(*args, **kwargs):
        raise AssertionError("_execute_mock() must not be called")

    client = LLMClient(provider="ollama", max_retries=2)
    monkeypatch.setattr(client, "_execute_mock", _fail_execute_mock)
    monkeypatch.setattr(client.session, "post", _raise)
    monkeypatch.setattr("time.sleep", lambda *a, **k: None)

    with pytest.raises(LLMProviderError):
        client.generate("Local prompt")

    # max_retries=2 => 3 total attempts
    assert call_count["n"] == 3


@pytest.mark.parametrize("provider", ["openai", "gemini", "claude"])
@pytest.mark.parametrize("exc_to_raise", [
    requests.ConnectionError("Connection refused"),
    requests.Timeout("Request timed out"),
    requests.RequestException("Generic transport failure"),
])
def test_llm_cloud_provider_real_failure_never_calls_execute_mock(monkeypatch, provider, exc_to_raise):
    """[6] Real OPENAI/GEMINI/CLAUDE connection/request failure never calls _execute_mock() and surfaces truthfully."""
    def _fail_execute_mock(*args, **kwargs):
        raise AssertionError(f"_execute_mock() must not be called for a real {provider} failure")

    def _raise(*args, **kwargs):
        raise exc_to_raise

    client = LLMClient(provider=provider, api_key="sk-real-looking-key", max_retries=0)
    monkeypatch.setattr(client, "_execute_mock", _fail_execute_mock)
    monkeypatch.setattr(client.session, "post", _raise)
    monkeypatch.setattr("time.sleep", lambda *a, **k: None)

    with pytest.raises(LLMError):
        client.generate("Hello")


def test_llm_generic_request_exception_does_not_synthesize_response(monkeypatch):
    """[7] A generic requests.RequestException must not synthesize a response."""
    def _fail_execute_mock(*args, **kwargs):
        raise AssertionError("_execute_mock() must not be called")

    def _raise(*args, **kwargs):
        raise requests.RequestException("Generic transport failure")

    client = LLMClient(provider="openai", api_key="sk-real-looking-key", max_retries=0)
    monkeypatch.setattr(client, "_execute_mock", _fail_execute_mock)
    monkeypatch.setattr(client.session, "post", _raise)

    with pytest.raises(LLMProviderError):
        client.generate("Hello")


def test_llm_os_error_does_not_synthesize_response(monkeypatch):
    """[8] A bare OSError during transport must not synthesize a response."""
    def _fail_execute_mock(*args, **kwargs):
        raise AssertionError("_execute_mock() must not be called")

    def _raise(*args, **kwargs):
        raise OSError("Network is unreachable")

    client = LLMClient(provider="openai", api_key="sk-real-looking-key", max_retries=0)
    monkeypatch.setattr(client, "_execute_mock", _fail_execute_mock)
    monkeypatch.setattr(client.session, "post", _raise)

    with pytest.raises(LLMProviderError):
        client.generate("Hello")


def test_llm_unsupported_provider_dispatch_state_does_not_synthesize_response(monkeypatch):
    """[9] An unexpected/unsupported provider-dispatch state must fail closed, not synthesize a response."""
    def _fail_execute_mock(*args, **kwargs):
        raise AssertionError("_execute_mock() must not be called for an unsupported dispatch state")

    class _FakeUnsupportedProvider:
        """Stand-in with a `.value` attribute (used unconditionally by chat()'s
        call-history recording and error messages) that is never equal to any
        real LLMProvider member, so it exercises the dispatch loop's fail-closed
        else-branch instead of any explicit provider branch."""
        value = "unsupported_provider"

        def __eq__(self, other):
            return False

        def __hash__(self):
            return id(self)

    client = LLMClient(provider="openai", api_key="sk-real-looking-key", max_retries=0)
    monkeypatch.setattr(client, "_execute_mock", _fail_execute_mock)
    # Force the dispatch loop's else-branch by mutating provider after
    # construction to an impossible-in-practice value not handled by any
    # explicit branch (constructor validation normally prevents this).
    client.provider = _FakeUnsupportedProvider()

    with pytest.raises(LLMProviderError):
        client.generate("Hello")


def test_llm_dummy_looking_api_key_does_not_activate_mock_for_real_provider(monkeypatch):
    """[10] A dummy-looking API key alone must not switch a real provider into mock."""
    def _fail_execute_mock(*args, **kwargs):
        raise AssertionError("_execute_mock() must not be called just because the key looks dummy/test-like")

    def _fake_post(url, headers=None, json=None, timeout=None):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {
            "choices": [{"message": {"content": "real response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
        }
        return resp

    for dummy_key in ("test_dummy_ci_key", "mock-key", "dummy", "fake", "key", "gemini_key_123"):
        client = LLMClient(provider="openai", api_key=dummy_key, max_retries=0)
        monkeypatch.setattr(client, "_execute_mock", _fail_execute_mock)
        monkeypatch.setattr(client.session, "post", _fake_post)

        resp = client.generate("Hello")
        assert resp.success is True
        assert resp.content == "real response"


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
