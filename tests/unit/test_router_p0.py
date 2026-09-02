"""
Comprehensive Unit Tests for JARVIS v4.6.0 P0-C & P0-D LLM Router.
Covers:
  - P0-C: Tier-2 LLM routing fallback pipeline (force_llm, OpenAI tool calls, structured actions, logging).
  - P0-D: Tier-1 fast-path regex/rules expansion (80+ non-diacritic, English, domain rules).
  - Tier-3: Graceful exception fallback on LLM network/auth/timeout failure.
"""

from unittest.mock import MagicMock
import pytest

from jarvis.llm.client import LLMClient, LLMResponse, ToolCall
from jarvis.llm.router import LLMIntentRouter, IntentResult
from jarvis.core.dispatcher import ActionDispatcher


@pytest.fixture
def mock_llm():
    """Mock LLM client returning empty response by default."""
    llm = MagicMock(spec=LLMClient)
    llm.generate.return_value = LLMResponse(
        content="Xin chào! Tôi có thể giúp gì cho Ngài?",
        tool_calls=[],
        model="gpt-4o",
    )
    return llm


@pytest.fixture
def router(mock_llm):
    """Instantiate an LLMIntentRouter with the mock LLM."""
    dispatcher = ActionDispatcher()
    return LLMIntentRouter(llm_client=mock_llm, dispatcher=dispatcher, fast_path_enabled=True)


# ============================================================================
# P0-D: Tier-1 Fast-Path Regex & Rules Expansion (80+ Non-diacritic & English)
# ============================================================================

class TestTier1FastPathRules:
    """Verify all 11 categories of non-diacritic Vietnamese, English, and domain rules."""

    @pytest.mark.parametrize(
        ("query", "expected_action"),
        [
            # 1. App Launchers
            ("mo chrome", "app_open"),
            ("mo ung dung chrome", "app_open"),
            ("mo notepad", "app_open"),
            ("open chrome", "app_open"),
            ("launch notepad", "app_open"),
            ("mo word", "app_open"),
            ("mo excel", "app_open"),
            ("mo paint", "app_open"),
            ("open file explorer", "app_open"),
            ("mo calculator", "app_open"),
            ("mo powerpoint", "app_open"),
            ("mo cai dat", "app_open"),
            ("cai dat he thong", "app_open"),
            ("cai dat windows", "app_open"),
            ("settings", "app_open"),
            ("open settings", "app_open"),
            ("cai dat", "app_open"),
            ("mo settings", "app_open"),
            # 2. Websites
            ("mo youtube", "web_open"),
            ("open youtube", "web_open"),
            ("vao youtube", "web_open"),
            ("mo facebook", "web_open"),
            ("open facebook", "web_open"),
            ("vao facebook", "web_open"),
            ("open website", "web_open"),
            ("mo trang web", "web_open"),
            # 3. System Power & Power Off
            ("tat may tinh", "system_power"),
            ("shutdown may", "system_power"),
            ("tat may", "system_power"),
            ("tat nguon", "system_power"),
            ("shut down", "system_power"),
            ("turn off computer", "system_power"),
            ("tat may di", "system_power"),
            ("tắt", "system_power"),
            ("power off", "system_power"),
            ("stop", "system_power"),
            ("thoi", "system_power"),
            ("huy", "system_power"),
            ("cancel", "system_power"),
            ("dung lai", "system_power"),
            # 4. System Restart
            ("khoi dong lai may", "system_power"),
            ("khoi dong lai", "system_power"),
            ("restart may tinh", "system_power"),
            ("restart windows", "system_power"),
            ("restart may", "system_power"),
            ("reboot", "system_power"),
            ("restart", "system_power"),
            # 5. Volume & Mute
            ("tang am luong", "system_volume"),
            ("giam am luong", "system_volume"),
            ("dieu chinh am luong", "system_volume"),
            ("volume up", "system_volume"),
            ("volume down", "system_volume"),
            ("giảm âm", "system_volume"),
            ("tat tieng", "system_volume"),
            ("mute", "system_volume"),
            # 6. Brightness & Screen Off
            ("tang do sang", "system_brightness"),
            ("giam do sang", "system_brightness"),
            ("brightness up", "system_brightness"),
            ("brightness down", "system_brightness"),
            ("tat man hinh", "system_brightness"),
            ("tat monitor", "system_brightness"),
            ("turn off screen", "system_brightness"),
            ("turn off monitor", "system_brightness"),
            ("tat man", "system_brightness"),
            ("screen off", "system_brightness"),
            # 7. Weather
            ("thoi tiet hom nay", "shell_exec"),
            ("thoi tiet ngay mai", "shell_exec"),
            ("du bao thoi tiet", "shell_exec"),
            ("troi hom nay", "shell_exec"),
            ("weather today", "shell_exec"),
            ("thoi tiet ha noi", "shell_exec"),
            ("bao nhieu do", "shell_exec"),
            ("weather forecast", "shell_exec"),
            # 8. Spotify & Music
            ("mo nhac", "spotify"),
            ("phat nhac", "spotify"),
            ("play music", "spotify"),
            ("mo spotify", "spotify"),
            ("launch spotify", "spotify"),
            ("open spotify", "spotify"),
            ("play song", "spotify"),
            ("bat nhac len", "spotify"),
            ("spotify", "spotify"),
            # 9. Hardware & System Status
            ("tinh trang he thong", "hardware_status_query"),
            ("kiem tra he thong", "hardware_status_query"),
            ("trang thai may", "hardware_status_query"),
            ("system status", "hardware_status_query"),
            ("hardware status", "hardware_status_query"),
            ("kiem tra cpu", "hardware_telemetry_check"),
            ("xem ram", "hardware_telemetry_check"),
            # 10. News & Morning Briefing
            ("tin tuc hom nay", "news_headlines"),
            ("tin moi nhat", "news_headlines"),
            ("doc tin tuc", "news_headlines"),
            ("news today", "news_headlines"),
            ("tin tuc", "news_headlines"),
            ("latest news", "news_headlines"),
            ("doc bao", "news_headlines"),
            ("bao cao buoi sang", "morning_briefing"),
            ("morning briefing", "morning_briefing"),
            ("thong tin buoi sang", "morning_briefing"),
            # 11. Memory Facts & Daily Summary
            ("nho cho toi", "memory_save_fact"),
            ("save this", "memory_save_fact"),
            ("tom tat hom nay", "memory_summarize_daily"),
            ("summarize today", "memory_summarize_daily"),
            # 12. Screen Capture
            ("chup man hinh", "screen_capture"),
            ("chup anh man hinh", "screen_capture"),
            ("take screenshot", "screen_capture"),
            ("printscreen", "screen_capture"),
            ("chup anh", "screen_capture"),
            # 13. Search Web & File Search
            ("tim kiem google", "web_open"),
            ("search chrome", "web_open"),
            ("tim kiem youtube", "web_open"),
            ("google thoi tiet", "web_open"),
            ("search for news", "web_open"),
            ("tim kiem tren google", "web_open"),
            ("tim file word", "file_search"),
            ("find file", "file_search"),
            ("tim file pdf", "file_search"),
            # 14. Folders
            ("mo thu muc downloads", "folder_open"),
            ("open folder downloads", "folder_open"),
            ("mo thu muc desktop", "folder_open"),
            ("open documents", "folder_open"),
            ("mo thu muc", "folder_open"),
            ("mo folder", "folder_open"),
            # 15. Projects & Workspaces
            ("mo du an jarvis", "workspace_prepare"),
            ("open project jarvis", "workspace_prepare"),
            ("switch sang project core", "workspace_prepare"),
            ("chuyen sang workspace dev", "workspace_prepare"),
            ("tao project moi", "project_create"),
            ("create project backend", "project_create"),
            ("liet ke project", "project_list"),
            ("show projects", "project_list"),
            ("git status", "skill_git_assistant"),
            ("git commit", "skill_git_assistant"),
            ("git push", "skill_git_assistant"),
        ],
    )
    def test_fast_path_intent_routing(self, router, query, expected_action):
        res = router.parse_intent(query, force_llm=False)
        assert isinstance(res, IntentResult)
        assert res.action_name == expected_action, f"Query '{query}' expected {expected_action} but got {res.action_name}"
        assert res.source in ("rule_fast_path", "rule_fallback")


# ============================================================================
# P0-C: Tier-2 LLM Routing Fallback Pipeline
# ============================================================================

class TestTier2LLMRouting:
    """Verify Tier-2 semantic reasoning, tool call parsing, and force_llm behavior."""

    def test_tier2_fallback_on_fast_path_miss(self, router, mock_llm):
        """When query is not recognized by Tier-1, router falls back to Tier-2 LLM with tool calling."""
        mock_llm.generate.return_value = LLMResponse(
            content="Đang tạo lịch hẹn lúc 3 giờ chiều cho Ngài.",
            tool_calls=[
                ToolCall(
                    id="call_remind_1",
                    name="reminder",
                    arguments={"message": "họp nhóm", "time_str": "15:00"},
                )
            ],
            model="gpt-4o",
        )

        query = "đặt hẹn họp lúc 3 giờ chiều"
        res = router.parse_intent(query, force_llm=False)

        assert res.action_name == "reminder"
        assert res.parameters == {"message": "họp nhóm", "time_str": "15:00"}
        assert res.source == "llm"
        assert res.confidence >= 0.95
        mock_llm.generate.assert_called_once()

    def test_force_llm_bypasses_tier1(self, router, mock_llm):
        """When force_llm=True, even static commands route through LLM semantic reasoning."""
        mock_llm.generate.return_value = LLMResponse(
            content="Đang mở Google Chrome cho Ngài.",
            tool_calls=[
                ToolCall(
                    id="call_app_1",
                    name="app_open",
                    arguments={"app_name": "chrome"},
                )
            ],
            model="gpt-4o",
        )

        res = router.parse_intent("mở chrome", force_llm=True)

        assert res.action_name == "app_open"
        assert res.source == "llm"
        mock_llm.generate.assert_called_once()

    def test_tier2_json_string_arguments_parsing(self, router, mock_llm):
        """Ensure tool arguments returned as JSON string are properly deserialized into dict."""
        mock_llm.generate.return_value = LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="call_ha_1",
                    name="home_assistant_call",
                    arguments='{"domain": "light", "service": "turn_on", "entity_id": "light.desk_lamp"}',
                )
            ],
            model="gpt-4o",
        )

        res = router.parse_intent("thiết lập không gian ánh sáng tập trung học tập", force_llm=False)

        assert res.action_name == "home_assistant_call"
        assert isinstance(res.parameters, dict)
        assert res.parameters.get("entity_id") == "light.desk_lamp"
        assert res.source == "llm"

    def test_tier2_conversational_response_when_no_tool(self, router, mock_llm):
        """When LLM produces general conversation with no tool calls, return generic_llm_response."""
        mock_llm.generate.return_value = LLMResponse(
            content="Tôi là JARVIS, trợ lý AI cá nhân của Ngài.",
            tool_calls=[],
            model="gpt-4o",
        )

        res = router.parse_intent("bạn là ai", force_llm=False)

        assert res.action_name == "generic_llm_response"
        assert res.parameters.get("reply") == "Tôi là JARVIS, trợ lý AI cá nhân của Ngài."
        assert res.source == "llm"


# ============================================================================
# Tier-3: Graceful Error Fallback
# ============================================================================

class TestTier3ErrorFallback:
    """Verify router does not crash on LLM network/auth/timeout exceptions."""

    def test_llm_exception_falls_back_to_rules(self, router, mock_llm):
        """When LLM raises an exception and fast-path was bypassed or missed, fallback rules execute."""
        mock_llm.generate.side_effect = ConnectionError("OpenAI API unreachable")

        # Query with force_llm=True triggers LLM exception, then catches and uses Tier-3 fallback
        res = router.parse_intent("mở chrome", force_llm=True)

        assert res.action_name == "app_open"
        assert res.source == "rule_fallback"
        assert res.confidence == 0.85

    def test_llm_exception_unknown_intent_when_no_rules_match(self, router, mock_llm):
        """When LLM fails and query is completely unknown, return unknown_intent cleanly."""
        mock_llm.generate.side_effect = TimeoutError("Request timed out")

        res = router.parse_intent("qwerty asdfgh zxcvbn", force_llm=False)

        assert res.action_name == "unknown_intent"
        assert res.confidence == 0.0
