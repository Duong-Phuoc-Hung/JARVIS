"""
tests/test_adversarial_m1_intent_router.py
===========================================
Adversarial Stress Test Suite for Intent Recognition (Milestone 1 / Requirement R1).

Tests:
1. R1 Acceptance Criteria verification.
2. Punctuation, Whitespace & Special Character Noise.
3. Case Variations & Mixed Casing (UPPERCASE, TitleCase, AlTeRnAtInG).
4. Conversational Prefixes & Suffixes (Polite particles, wake words, fillers).
5. Open / Switch Project Variations & Parametric Extraction.
6. Create Project / Workspace Variations & Name Sanitization.
7. List Projects / Workspaces Variations.
8. Git Operations on Projects (status, commit, push, log, branch, diff).
9. Extreme Edge Cases (Empty, whitespace-only, emoji-only, number-only, long payloads / ReDoS resistance).
10. False Positive Isolation (Ensures smart home, system, apps, web don't misroute).
11. Tier 3 Exception Fallback (Simulated LLM network/API failure).
12. Fast-path sub-millisecond latency benchmark.
"""
from __future__ import annotations

import time
import pytest
from unittest.mock import MagicMock

from jarvis.llm.client import LLMClient
from jarvis.llm.router import IntentResult, LLMIntentRouter


@pytest.fixture
def router() -> LLMIntentRouter:
    """Fixture providing an offline LLMIntentRouter with mock client."""
    client = LLMClient(provider="mock")
    return LLMIntentRouter(client)


# ============================================================================
# 1. ACCEPTANCE CRITERIA VERIFICATION (R1)
# ============================================================================

class TestR1AcceptanceCriteria:
    """Explicitly verifies the 4 acceptance criteria from ORIGINAL_REQUEST.md."""

    def test_r1_ac1_open_project(self, router: LLMIntentRouter):
        res = router.parse_intent("mở dự án jarvis", force_llm=False)
        assert res.action_name not in ("unknown_intent", "generic_llm_response")
        assert res.action_name == "workspace_prepare"
        assert res.parameters.get("project") == "jarvis"
        assert res.parameters.get("action") == "open"

    def test_r1_ac2_create_workspace(self, router: LLMIntentRouter):
        res = router.parse_intent("tạo workspace mới", force_llm=False)
        assert res.action_name not in ("unknown_intent", "generic_llm_response")
        assert res.action_name == "project_create"
        assert res.parameters.get("action") == "create"

    def test_r1_ac3_list_projects(self, router: LLMIntentRouter):
        res = router.parse_intent("liệt kê project", force_llm=False)
        assert res.action_name not in ("unknown_intent", "generic_llm_response")
        assert res.action_name == "project_list"
        assert res.parameters.get("action") == "list"

    def test_r1_ac4_git_status(self, router: LLMIntentRouter):
        res = router.parse_intent("git status dự án", force_llm=False)
        assert res.action_name not in ("unknown_intent", "generic_llm_response")
        assert res.action_name == "skill_git_assistant"
        assert res.parameters.get("action") == "status"


# ============================================================================
# 2. NOISY PUNCTUATION & SPECIAL CHARACTER STRESS
# ============================================================================

class TestAdversarialPunctuation:
    """Tests noisy punctuation, quotes, trailing dots, question marks, exclamation marks."""

    @pytest.mark.parametrize(
        "utterance,expected_action",
        [
            ("Mở dự án jarvis!", "workspace_prepare"),
            ("Mở dự án jarvis...", "workspace_prepare"),
            ("mở dự án jarvis???", "workspace_prepare"),
            ("Jarvis, mở dự án: 'JARVIS-PRO'", "workspace_prepare"),
            ("  [mở dự án jarvis]  ", "workspace_prepare"),
            ("tạo workspace mới!!!", "project_create"),
            ("tạo project mới...", "project_create"),
            ("liệt kê dự án???", "project_list"),
            ("show projects!", "project_list"),
            ("git status dự án.", "skill_git_assistant"),
            ("git commit dự án!", "skill_git_assistant"),
            ("git push project...", "skill_git_assistant"),
        ],
    )
    def test_punctuation_tolerance(self, router: LLMIntentRouter, utterance: str, expected_action: str):
        if utterance is None:
            pytest.skip("Vietnamese parametrize value not decoded (encoding/pytest issue)")
        # We strip surrounding punctuation in clean query or test router resilience
        res = router.parse_intent(utterance, force_llm=False)
        assert res.action_name == expected_action, f"Failed on noisy input: '{utterance}' -> got {res.action_name}"
        assert res.action_name != "unknown_intent"


# ============================================================================
# 3. CAPITALIZATION & CASING VARIATIONS
# ============================================================================

class TestAdversarialCasing:
    """Tests uppercase, TitleCase, camelCase, mixed casing variations."""

    @pytest.mark.parametrize(
        "utterance,expected_action",
        [
            ("MỞ DỰ ÁN JARVIS", "workspace_prepare"),
            ("Mở Dự Án Jarvis", "workspace_prepare"),
            ("mỞ dỰ áN jArViS", "workspace_prepare"),
            ("SWITCH SANG PROJECT CORE", "workspace_prepare"),
            ("TẠO WORKSPACE MỚI", "project_create"),
            ("Tạo Project Tên BACKEND_V2", "project_create"),
            ("LIỆT KÊ DỰ ÁN", "project_list"),
            ("SHOW PROJECTS", "project_list"),
            ("CÁC PROJECT ĐANG CÓ", "project_list"),
            ("GIT STATUS DỰ ÁN", "skill_git_assistant"),
            ("GIT COMMIT DỰ ÁN", "skill_git_assistant"),
            ("GIT PUSH PROJECT", "skill_git_assistant"),
        ],
    )
    def test_casing_variations(self, router: LLMIntentRouter, utterance: str, expected_action: str):
        if utterance is None:
            pytest.skip("Vietnamese parametrize value not decoded (encoding/pytest issue)")
        res = router.parse_intent(utterance, force_llm=False)
        assert res.action_name == expected_action, f"Failed on casing variation: '{utterance}' -> got {res.action_name}"


# ============================================================================
# 4. CONVERSATIONAL PREFIXES, SUFFIXES & FILLERS
# ============================================================================

class TestConversationalPrefixesAndSuffixes:
    """Tests wake words, conversational particles, polite terms."""

    @pytest.mark.parametrize(
        "utterance,expected_action",
        [
            ("jarvis mở dự án web_app", "workspace_prepare"),
            ("jarvis, mở dự án mobile", "workspace_prepare"),
            ("jarvis switch sang project dev", "workspace_prepare"),
            ("jarvis tạo workspace tên demo", "project_create"),
            ("jarvis show projects", "project_list"),
            ("jarvis git status dự án", "skill_git_assistant"),
            ("jarvis git commit dự án", "skill_git_assistant"),
            ("jarvis git push project", "skill_git_assistant"),
            ("chuyển sang workspace analytics", "workspace_prepare"),
            ("switch to project frontend", "workspace_prepare"),
            ("tạo dự án test_repo", "project_create"),
            ("khởi tạo dự án microservices", "project_create"),
            ("create project fast_api", "project_create"),
        ],
    )
    def test_conversational_prefixes(self, router: LLMIntentRouter, utterance: str, expected_action: str):
        if utterance is None:
            pytest.skip("Vietnamese parametrize value not decoded (encoding/pytest issue)")
        res = router.parse_intent(utterance, force_llm=False)
        assert res.action_name == expected_action, f"Failed on prefix variation: '{utterance}' -> got {res.action_name}"


# ============================================================================
# 5. PARAMETRIC EXTRACTION INTEGRITY
# ============================================================================

class TestParametricExtractionIntegrity:
    """Tests extraction of project names, actions, flags."""

    def test_open_project_extraction(self, router: LLMIntentRouter):
        cases = [
            ("mở dự án e-commerce", "e-commerce"),
            ("switch sang project authentication_service", "authentication_service"),
            ("chuyển sang workspace ai_agent", "ai_agent"),
            ("open project jarvis-v4", "jarvis-v4"),
        ]
        for utterance, expected_target in cases:
            res = router.parse_intent(utterance, force_llm=False)
            assert res.action_name == "workspace_prepare"
            assert res.parameters.get("action") == "open"
            assert res.parameters.get("project") == expected_target

    def test_create_project_extraction(self, router: LLMIntentRouter):
        cases = [
            ("tạo workspace tên my_new_app", "my_new_app"),
            ("tạo project tên: payment_gateway", "payment_gateway"),
            ("tạo dự án cloud_infra", "cloud_infra"),
            ("create project search_engine", "search_engine"),
            ("tạo dự án sandbox mới", "sandbox"),
        ]
        for utterance, expected_name in cases:
            res = router.parse_intent(utterance, force_llm=False)
            assert res.action_name == "project_create"
            assert res.parameters.get("action") == "create"
            assert res.parameters.get("name") == expected_name

    def test_git_operations_extraction(self, router: LLMIntentRouter):
        cases = [
            ("git status dự án website", "status", "website"),
            ("git commit dự án mobile_app", "commit", "mobile_app"),
            ("git push project api_server", "push", "api_server"),
            ("git log dự án jarvis", "log", "jarvis"),
            ("git branch dự án jarvis", "branch", "jarvis"),
            ("git diff dự án jarvis", "diff", "jarvis"),
        ]
        for utterance, expected_act, expected_proj in cases:
            res = router.parse_intent(utterance, force_llm=False)
            assert res.action_name == "skill_git_assistant"
            assert res.parameters.get("action") == expected_act
            assert res.parameters.get("project") == expected_proj


# ============================================================================
# 6. EXTREME EDGE CASES & STRESS HARNESS
# ============================================================================

class TestExtremeEdgeCases:
    """Stress tests extreme inputs, empty inputs, huge payloads, emojis."""

    def test_empty_and_whitespace_inputs(self, router: LLMIntentRouter):
        for empty_val in ("", "   ", "\t\t\n\n", "   \r\n   "):
            res = router.parse_intent(empty_val, force_llm=False)
            assert isinstance(res, IntentResult)
            # Should not crash, returns unknown or fallback safely
            assert res.action_name in ("unknown_intent", "generic_llm_response", "")

    def test_emoji_and_symbol_only_inputs(self, router: LLMIntentRouter):
        # Emoji-only and symbol-only inputs → no meaningful intent, should not execute actions
        # Acceptable responses: 'unknown_intent' (fast-path) or 'generic_llm_response' (mock LLM fallback)
        meaningless_inputs = ["🚀🔥🎉", "💻📱🖥️", "???!!!@@@###"]
        for inp in meaningless_inputs:
            res = router.parse_intent(inp, force_llm=False)
            assert isinstance(res, IntentResult)
            assert res.action_name in ("unknown_intent", "generic_llm_response"), \
                f"Expected meaningless-input handling for {inp!r}, got action_name={res.action_name}"

    def test_number_only_inputs(self, router: LLMIntentRouter):
        numbers = ["123456", "999999999", "3.1415926"]
        for num in numbers:
            res = router.parse_intent(num, force_llm=False)
            assert isinstance(res, IntentResult)
            assert res.action_name == "unknown_intent"

    def test_huge_input_redos_resistance(self, router: LLMIntentRouter):
        """Passes 50KB adversarial string to confirm no ReDoS or catastrophic hang."""
        huge_text = "mở dự án " + ("a" * 50000)
        t0 = time.perf_counter()
        res = router.parse_intent(huge_text, force_llm=False)
        duration = time.perf_counter() - t0
        assert duration < 0.5, f"ReDoS vulnerability detected: execution took {duration:.3f}s"
        assert res.action_name == "workspace_prepare"

    def test_repetitive_nested_regex_stress(self, router: LLMIntentRouter):
        """Attempts pattern designed to trigger exponential regex backtracking."""
        adversarial_pattern = "chuyển sang " * 500 + "project jarvis"
        t0 = time.perf_counter()
        res = router.parse_intent(adversarial_pattern, force_llm=False)
        duration = time.perf_counter() - t0
        assert duration < 0.5, f"Catastrophic backtracking: execution took {duration:.3f}s"
        assert isinstance(res, IntentResult)


# ============================================================================
# 7. FALSE POSITIVE ISOLATION & NON-COLLISION
# ============================================================================

class TestFalsePositiveIsolation:
    """Verifies that non-project commands are NOT hijacked by project regexes."""

    @pytest.mark.parametrize(
        "utterance,expected_action",
        [
            ("bật đèn phòng khách", "home_assistant_call"),
            ("tắt quạt phòng khách", "home_assistant_call"),
            ("kiểm tra nhiệt độ cpu", "hardware_telemetry_check"),
            ("tình trạng hệ thống", "hardware_status_query"),
            ("mở spotify", "spotify"),
            ("thời tiết Hà Nội", "shell_exec"),
            ("tắt máy tính", "system_power"),
            ("mở chrome", "app_open"),
            ("mở youtube", "web_open"),
            ("mở thư mục downloads", "folder_open"),
            ("chụp màn hình", "screen_capture"),
            ("tăng âm lượng", "system_volume"),
        ],
    )
    def test_existing_core_intents_unaffected(self, router: LLMIntentRouter, utterance: str, expected_action: str):
        if utterance is None:
            pytest.skip("Vietnamese parametrize value not decoded (encoding/pytest issue)")
        res = router.parse_intent(utterance, force_llm=False)
        assert res.action_name == expected_action, f"False positive collision: '{utterance}' routed to {res.action_name}"


# ============================================================================
# 8. TIER 3 EXCEPTION FALLBACK SIMULATION
# ============================================================================

class TestTier3ExceptionFallback:
    """Simulates LLM client failures (timeout, connection error) and confirms fallback."""

    def test_llm_exception_fallback_to_project_rules(self):
        failing_client = MagicMock(spec=LLMClient)
        failing_client.generate.side_effect = ConnectionError("OpenAI API 503 Service Unavailable")
        router = LLMIntentRouter(failing_client)

        res = router.parse_intent("mở dự án jarvis", force_llm=True)
        assert res.action_name == "workspace_prepare"
        assert res.source == "rule_fallback"
        assert res.parameters.get("project") == "jarvis"

        res_create = router.parse_intent("tạo workspace mới", force_llm=True)
        assert res_create.action_name == "project_create"
        assert res_create.source == "rule_fallback"

        res_list = router.parse_intent("liệt kê project", force_llm=True)
        assert res_list.action_name == "project_list"
        assert res_list.source == "rule_fallback"

        res_git = router.parse_intent("git status dự án", force_llm=True)
        assert res_git.action_name == "skill_git_assistant"
        assert res_git.source == "rule_fallback"


# ============================================================================
# 9. LATENCY & THROUGHPUT BENCHMARK (EMPIRICAL)
# ============================================================================

class TestFastPathPerformance:
    """Empirically evaluates intent classification speed for sub-millisecond SLA."""

    def test_sub_millisecond_classification_speed(self, router: LLMIntentRouter):
        corpus = [
            "mở dự án jarvis",
            "tạo workspace mới",
            "liệt kê project",
            "git status dự án",
            "switch sang project backend",
            "tạo project tên auth_service",
            "show projects",
            "git commit dự án",
            "git push project",
            "chuyển sang workspace mobile",
        ]

        # Warm up
        for text in corpus:
            router.parse_intent(text, force_llm=False)

        # 1000 iterations benchmark
        iterations = 1000
        t0 = time.perf_counter()
        for i in range(iterations):
            text = corpus[i % len(corpus)]
            res = router.parse_intent(text, force_llm=False)
            assert res.action_name != "unknown_intent"
        total_time = time.perf_counter() - t0
        avg_latency_ms = (total_time / iterations) * 1000

        print(f"\n[BENCHMARK] Fast-path: {iterations} classifications in {total_time:.4f}s. Avg: {avg_latency_ms:.4f} ms/call.")
        assert avg_latency_ms < 1.0, f"Fast-path latency SLA exceeded: {avg_latency_ms:.4f} ms > 1.0 ms"
