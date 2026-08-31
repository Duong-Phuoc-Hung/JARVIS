"""
tests/test_router_project_intents.py
====================================
Test Suite for Project, Workspace, and Git Assistant Intent Recognition (Requirement R1).
Validates:
  - Group A: Open & switch project / workspace intents
  - Group B: Create project / workspace intents
  - Group C: List projects / workspaces intents
  - Group D: Git operations on projects (status, commit, push, log, branch, diff)
  - Natural Vietnamese response generation & parameter extraction
  - Deterministic fast-path execution (force_llm=False) without unknown_intent
"""
from __future__ import annotations

import pytest

from jarvis.llm.client import LLMClient
from jarvis.llm.router import IntentResult, LLMIntentRouter


@pytest.fixture
def offline_router() -> LLMIntentRouter:
    """Provides an LLMIntentRouter configured with an offline/mock LLMClient."""
    client = LLMClient(provider="mock")
    return LLMIntentRouter(client)


# ============================================================================
# 1. GROUP A: OPEN & SWITCH PROJECT / WORKSPACE INTENTS
# ============================================================================

def test_r1_open_and_switch_project_intents(offline_router: LLMIntentRouter):
    """
    [R1 - Group A] Validate opening and switching project/workspace intents
    properly map to action_name='workspace_prepare' with action='open'.
    """
    test_cases = [
        ("mở dự án jarvis", "jarvis"),
        ("mở dự án X", "X"),
        ("mở project Y", "Y"),
        ("switch sang project Y", "Y"),
        ("switch sang dự án jarvis", "jarvis"),
        ("chuyển sang workspace AI", "AI"),
        ("open project jarvis", "jarvis"),
        ("open workspace jarvis", "jarvis"),
        ("chuyển workspace", ""),
        ("mở dự án", ""),
        ("open project", ""),
    ]

    for utterance, expected_proj in test_cases:
        res = offline_router.parse_intent(utterance, force_llm=False)
        assert isinstance(res, IntentResult)
        assert res.action_name == "workspace_prepare", f"Failed for utterance: '{utterance}'"
        assert res.action_name != "unknown_intent"
        assert res.action_name != "generic_llm_response"
        assert res.parameters.get("action") == "open"
        if expected_proj:
            assert res.parameters.get("project") == expected_proj
            assert res.parameters.get("recipe") == expected_proj
            assert expected_proj in res.response_text
        else:
            assert "chuẩn bị môi trường" in res.response_text or "mở không gian" in res.response_text or "chuyển" in res.response_text


# ============================================================================
# 2. GROUP B: CREATE PROJECT & WORKSPACE INTENTS
# ============================================================================

def test_r1_create_project_and_workspace_intents(offline_router: LLMIntentRouter):
    """
    [R1 - Group B] Validate creating new project/workspace intents
    properly map to action_name='project_create' with action='create'.
    """
    test_cases = [
        ("tạo project mới", ""),
        ("tạo workspace mới", ""),
        ("tạo dự án mới", ""),
        ("tạo workspace tên ABC", "ABC"),
        ("tạo project tên ABC", "ABC"),
        ("tạo dự án XYZ", "XYZ"),
        ("khởi tạo dự án JARVIS_CORE", "JARVIS_CORE"),
        ("create project demo", "demo"),
        ("tạo workspace", ""),
        ("tạo project", ""),
        ("tạo dự án", ""),
    ]

    for utterance, expected_name in test_cases:
        res = offline_router.parse_intent(utterance, force_llm=False)
        assert isinstance(res, IntentResult)
        assert res.action_name == "project_create", f"Failed for utterance: '{utterance}'"
        assert res.action_name != "unknown_intent"
        assert res.action_name != "generic_llm_response"
        assert res.parameters.get("action") == "create"
        if expected_name:
            assert res.parameters.get("name") == expected_name
            assert res.parameters.get("project_name") == expected_name
            assert expected_name in res.response_text
        else:
            assert "khởi tạo dự án mới" in res.response_text


# ============================================================================
# 3. GROUP C: LIST PROJECTS & WORKSPACES INTENTS
# ============================================================================

def test_r1_list_projects_and_workspaces_intents(offline_router: LLMIntentRouter):
    """
    [R1 - Group C] Validate listing projects/workspaces queries
    properly map to action_name='project_list' with action='list'.
    """
    test_cases = [
        "liệt kê dự án",
        "show projects",
        "các project đang có",
        "liệt kê project",
        "danh sách dự án",
        "danh sách project",
        "danh sách workspace",
        "liệt kê workspace",
        "các dự án đang có",
        "list projects",
        "xem danh sách dự án",
    ]

    for utterance in test_cases:
        res = offline_router.parse_intent(utterance, force_llm=False)
        assert isinstance(res, IntentResult)
        assert res.action_name == "project_list", f"Failed for utterance: '{utterance}'"
        assert res.action_name != "unknown_intent"
        assert res.action_name != "generic_llm_response"
        assert res.parameters.get("action") == "list"
        assert "liệt kê" in res.response_text or "danh sách" in res.response_text


# ============================================================================
# 4. GROUP D: GIT OPERATIONS ON PROJECTS
# ============================================================================

def test_r1_git_project_commands(offline_router: LLMIntentRouter):
    """
    [R1 - Group D] Validate git operations on projects
    properly map to action_name='skill_git_assistant' with appropriate action.
    """
    test_cases = [
        ("git status dự án", "status", ""),
        ("commit dự án", "commit", ""),
        ("push project", "push", ""),
        ("git commit dự án", "commit", ""),
        ("git push project", "push", ""),
        ("git log dự án", "log", ""),
        ("git branch dự án", "branch", ""),
        ("git status dự án jarvis", "status", "jarvis"),
        ("commit dự án jarvis", "commit", "jarvis"),
        ("push project jarvis", "push", "jarvis"),
        ("git status", "status", ""),
        ("git commit", "commit", ""),
        ("git push", "push", ""),
        ("kiểm tra git dự án", "status", ""),
        ("trạng thái git project", "status", ""),
    ]

    for utterance, expected_action, expected_proj in test_cases:
        res = offline_router.parse_intent(utterance, force_llm=False)
        assert isinstance(res, IntentResult)
        assert res.action_name == "skill_git_assistant", f"Failed for utterance: '{utterance}'"
        assert res.action_name != "unknown_intent"
        assert res.action_name != "generic_llm_response"
        assert res.parameters.get("action") == expected_action
        if expected_proj:
            assert res.parameters.get("project") == expected_proj
            assert expected_proj in res.response_text


# ============================================================================
# 5. PARAMETER EXTRACTION AND NATURAL RESPONSES
# ============================================================================

def test_r1_parameter_extraction_and_natural_responses(offline_router: LLMIntentRouter):
    """
    [R1] Verify natural Vietnamese response generation and formatting across all
    project, workspace, and git operations.
    """
    # 1. Workspace open response
    resp_open = offline_router.get_natural_response(
        "workspace_prepare", {"action": "open", "project": "jarvis"}
    )
    assert "Đang mở dự án jarvis cho Ngài." == resp_open

    # 2. Workspace open fallback response
    resp_open_empty = offline_router.get_natural_response(
        "workspace_prepare", {"action": "open", "project": ""}
    )
    assert "Đang chuẩn bị môi trường làm việc cho Ngài." == resp_open_empty

    # 3. Project create response with name
    resp_create = offline_router.get_natural_response(
        "project_create", {"action": "create", "name": "AI_Assistant"}
    )
    assert "Đang khởi tạo dự án AI_Assistant cho Ngài." == resp_create

    # 4. Project create response without name
    resp_create_empty = offline_router.get_natural_response(
        "project_create", {"action": "create", "name": ""}
    )
    assert "Đang khởi tạo dự án mới cho Ngài." == resp_create_empty

    # 5. Project list response
    resp_list = offline_router.get_natural_response(
        "project_list", {"action": "list"}
    )
    assert "Đang liệt kê danh sách các dự án cho Ngài." == resp_list

    # 6. Git assistant responses
    resp_git_status = offline_router.get_natural_response(
        "skill_git_assistant", {"action": "status", "project": "JARVIS"}
    )
    assert "Đang kiểm tra trạng thái Git dự án JARVIS cho Ngài." == resp_git_status

    resp_git_commit = offline_router.get_natural_response(
        "skill_git_assistant", {"action": "commit", "project": "JARVIS"}
    )
    assert "Đang thực hiện commit dự án JARVIS cho Ngài." == resp_git_commit

    resp_git_push = offline_router.get_natural_response(
        "skill_git_assistant", {"action": "push", "project": "JARVIS"}
    )
    assert "Đang đẩy code dự án JARVIS lên Git cho Ngài." == resp_git_push


# ============================================================================
# 6. ACCEPTANCE CRITERIA EXPLICIT VERIFICATION
# ============================================================================

def test_r1_acceptance_criteria_explicit_phrases(offline_router: LLMIntentRouter):
    """
    [R1 Acceptance Criteria]
    - router.parse_intent("mở dự án jarvis", force_llm=False).action_name != "unknown_intent"
    - router.parse_intent("tạo workspace mới", force_llm=False).action_name != "unknown_intent"
    - router.parse_intent("liệt kê project", force_llm=False).action_name != "unknown_intent"
    - router.parse_intent("git status dự án", force_llm=False).action_name != "unknown_intent"
    """
    res1 = offline_router.parse_intent("mở dự án jarvis", force_llm=False)
    assert res1.action_name != "unknown_intent"
    assert res1.action_name != "generic_llm_response"
    assert res1.action_name == "workspace_prepare"

    res2 = offline_router.parse_intent("tạo workspace mới", force_llm=False)
    assert res2.action_name != "unknown_intent"
    assert res2.action_name != "generic_llm_response"
    assert res2.action_name == "project_create"

    res3 = offline_router.parse_intent("liệt kê project", force_llm=False)
    assert res3.action_name != "unknown_intent"
    assert res3.action_name != "generic_llm_response"
    assert res3.action_name == "project_list"

    res4 = offline_router.parse_intent("git status dự án", force_llm=False)
    assert res4.action_name != "unknown_intent"
    assert res4.action_name != "generic_llm_response"
    assert res4.action_name == "skill_git_assistant"
