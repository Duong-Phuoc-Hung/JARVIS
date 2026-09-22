"""
tests/unit/test_llm_fixes_m3.py
===============================
Regression and verification test suite for Milestone 3 (LLM & Integration Remediation).
Covers BUG-LLM-01 through BUG-LLM-08:
  1. BUG-LLM-01: Non-diacritic duration unit parsing (gio, tieng, phut, giay)
  2. BUG-LLM-02: Negation checks covering Spotify and Claude targets
  3. BUG-LLM-03: OpenAPI/Gemini array tool schema items requirement
  4. BUG-LLM-04: Action contract aliases registered in core app dispatcher
  5. BUG-LLM-05: _handle_proactive_reminder parameter and delay_s normalization
  6. BUG-LLM-06: Gemini safety block null content handling
  7. BUG-LLM-07: Standard GOOGLE_API_KEY & ANTHROPIC_API_KEY resolution
  8. BUG-LLM-08: Ollama tool arguments deserialization from JSON string to dict
"""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch
import pytest

from jarvis.core.app import JarvisApp
from jarvis.core.dispatcher import ActionDispatcher
from jarvis.llm.client import LLMClient, LLMProvider, ToolCall
from jarvis.llm.router import (
    LLMIntentRouter,
    _parse_duration_seconds,
    generate_tool_schema_from_dispatcher,
)


# ============================================================================
# 1. BUG-LLM-01: Non-Diacritic Duration Unit Parsing
# ============================================================================

def test_bug_llm_01_duration_parsing_non_diacritic_units():
    """Verify unaccented duration units (gio, tieng, phut, giay) evaluate to correct seconds."""
    # Accented baseline
    assert _parse_duration_seconds(2, "giờ") == 7200
    assert _parse_duration_seconds(1, "tiếng") == 3600
    assert _parse_duration_seconds(10, "phút") == 600
    assert _parse_duration_seconds(45, "giây") == 45

    # Non-diacritic units that previously collapsed to amount * 60
    assert _parse_duration_seconds(30, "giay") == 30
    assert _parse_duration_seconds(2, "gio") == 7200
    assert _parse_duration_seconds(2, "tieng") == 7200
    assert _parse_duration_seconds(15, "phut") == 900


# ============================================================================
# 2. BUG-LLM-02: Negation Bypass for Spotify and Claude Launch Targets
# ============================================================================

@pytest.mark.parametrize("query", [
    "đừng mở spotify",
    "dung mo spotify",
    "never open spotify",
    "do not open spotify",
    "đừng mở claude",
    "dung mo claude",
    "đừng bật spotify",
    "dung bat spotify",
])
def test_bug_llm_02_negated_spotify_and_claude_launch(query: str):
    """Verify negated music and Claude commands do not trigger app/web launch."""
    router = LLMIntentRouter(llm_client=None, dispatcher=None, fast_path_enabled=True)
    res = router.parse_intent(query)
    is_launch = (
        res.action_name == "spotify"
        or (res.action_name == "web_open" and res.parameters.get("site") == "claude")
    )
    assert not is_launch, f"Query '{query}' produced unauthorized launch intent: {res.action_name}"


# ============================================================================
# 3. BUG-LLM-03: Missing items in Generated Array Tool Schemas
# ============================================================================

def test_bug_llm_03_tool_schema_array_items_field():
    """Verify generated OpenAPI parameter schemas specify 'items' for array types."""
    dispatcher = ActionDispatcher()

    def sample_tool(items: list[str], tags: list[int], payload: dict):
        pass

    dispatcher.register_action("sample_tool", sample_tool, description="Sample tool for schema test")
    tools = generate_tool_schema_from_dispatcher(dispatcher)
    props = tools[0]["function"]["parameters"]["properties"]

    assert props["items"]["type"] == "array"
    assert "items" in props["items"], "Array property 'items' missing mandatory 'items' schema"
    assert props["items"]["items"]["type"] == "string"

    assert props["tags"]["type"] == "array"
    assert "items" in props["tags"], "Array property 'tags' missing mandatory 'items' schema"
    assert props["tags"]["items"]["type"] == "integer"

    assert props["payload"]["type"] == "object"


# ============================================================================
# 4. BUG-LLM-04: Action Contract Drift Between Router and Core Dispatcher
# ============================================================================

def test_bug_llm_04_action_aliases_registered_in_core():
    """Verify actions emitted by router are registered in JarvisApp dispatcher."""
    app = JarvisApp()
    app._register_core_actions()
    registered = set(app.dispatcher.list_actions().keys())

    expected_actions = [
        "hardware_telemetry_check",
        "reminder",
        "workspace_prepare",
        "project_create",
        "project_list",
        "skill_git_assistant",
    ]
    for act in expected_actions:
        assert act in registered, f"Action '{act}' missing from core dispatcher registration"

    # Verify dispatch does not return ACTION_NOT_FOUND
    res = app.dispatcher.dispatch_action("hardware_telemetry_check", {})
    assert res.error_code != "ACTION_NOT_FOUND"


# ============================================================================
# 5. BUG-LLM-05: Parameter Key & Positional Argument Mismatch on _handle_proactive_reminder
# ============================================================================

def test_bug_llm_05_proactive_reminder_parameter_normalization():
    """Verify _handle_proactive_reminder handles kwargs, missing message, and sub-minute delay_s."""
    app = JarvisApp()
    app.proactive_engine = MagicMock()
    app.proactive_engine.add_reminder.return_value = "rem_123"

    # Sub-minute timer (30s) via delay_s without explicit message positional arg
    res = app._handle_proactive_reminder(delay_s=30, action="timer")
    assert res["status"] == "success"
    app.proactive_engine.add_reminder.assert_called_with(text="timer", delay_seconds=30.0)

    # With message and delay_s
    res2 = app._handle_proactive_reminder(message="Uống nước", delay_s=45)
    assert res2["status"] == "success"
    app.proactive_engine.add_reminder.assert_called_with(text="Uống nước", delay_seconds=45.0)


# ============================================================================
# 6. BUG-LLM-06: Gemini Safety Block Null Content Unhandled AttributeError
# ============================================================================

def test_bug_llm_06_gemini_safety_block_null_content():
    """Verify Gemini safety filter with null content returns polite refusal instead of AttributeError."""
    client = LLMClient(provider=LLMProvider.GEMINI, api_key="dummy_key", mock_mode=False)
    client.session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "candidates": [
            {"finishReason": "SAFETY", "content": None}
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    client.session.post.return_value = mock_resp

    res = client._call_gemini(messages=[], tools=None, temperature=0.7, max_tokens=100)
    assert "bộ lọc an toàn" in res.content or res.content != ""


# ============================================================================
# 7. BUG-LLM-07: Missing Standard Fallback Environment Variables for Gemini and Claude
# ============================================================================

def test_bug_llm_07_api_key_fallbacks_gemini_and_claude(monkeypatch):
    """Verify standard ANTHROPIC_API_KEY and GOOGLE_API_KEY environment variables are resolved."""
    monkeypatch.delenv("JARVIS_CLAUDE_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-auth-key")

    claude_client = LLMClient(provider=LLMProvider.CLAUDE)
    assert claude_client.api_key == "sk-ant-test-auth-key"

    monkeypatch.delenv("JARVIS_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "AIzaSyTest-Google-Key")

    gemini_client = LLMClient(provider=LLMProvider.GEMINI)
    assert gemini_client.api_key == "AIzaSyTest-Google-Key"


# ============================================================================
# 8. BUG-LLM-08: Ollama Tool Arguments Type Drift
# ============================================================================

def test_bug_llm_08_ollama_tool_arguments_string_deserialization():
    """Verify modern Ollama JSON string arguments are deserialized into dict."""
    client = LLMClient(provider=LLMProvider.OLLAMA, base_url="http://localhost:11434")
    client.session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "message": {
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "system_volume",
                        "arguments": "{\"level\": 50, \"action\": \"set\"}"
                    }
                }
            ]
        }
    }
    mock_resp.raise_for_status = MagicMock()
    client.session.post.return_value = mock_resp

    res = client._call_ollama(messages=[], tools=None, temperature=0.7, max_tokens=100)
    assert len(res.tool_calls) == 1
    tc = res.tool_calls[0]
    assert isinstance(tc.arguments, dict), f"Expected dict for arguments, got {type(tc.arguments)}"
    assert tc.arguments.get("level") == 50
    assert tc.arguments.get("action") == "set"
