"""
tests/unit/test_router_nlp_integration.py
=========================================
Unit tests verifying the deep integration of VietnameseNLPClassifier into
LLMIntentRouter as Tier 0 ML Fast-Path.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from jarvis.llm.client import LLMClient
from jarvis.llm.local_classifier import VietnameseNLPClassifier
from jarvis.llm.router import LLMIntentRouter


@pytest.fixture
def dummy_llm():
    mock = MagicMock(spec=LLMClient)
    mock.provider = "mock_provider"
    return mock


def test_router_initializes_ml_classifier(dummy_llm):
    router = LLMIntentRouter(llm_client=dummy_llm)
    assert hasattr(router, "ml_classifier")
    if router.ml_classifier is not None:
        assert isinstance(router.ml_classifier, VietnameseNLPClassifier)
        assert router.ml_classifier.is_trained is True


def test_router_ml_fast_path_volume(dummy_llm):
    router = LLMIntentRouter(llm_client=dummy_llm, ml_fast_path_enabled=True)
    # Tone-stripped volume command that won't match strict rules
    res = router.parse_intent("tat am thanh")
    assert res.action_name == "system_volume"
    assert res.parameters.get("mute") is True


def test_router_ml_fast_path_brightness(dummy_llm):
    router = LLMIntentRouter(llm_client=dummy_llm, ml_fast_path_enabled=True)
    res = router.parse_intent("chỉnh độ sáng lên 90%")
    assert res.action_name == "system_brightness"
    assert res.parameters.get("level") == 90 or res.parameters.get("delta") is not None


def test_router_ml_fast_path_app_close(dummy_llm):
    router = LLMIntentRouter(llm_client=dummy_llm, ml_fast_path_enabled=True)
    res = router.parse_intent("dong trinh duyet chrome")
    assert res.action_name == "app_close"
    assert res.parameters.get("app_name") == "chrome"


def test_router_ml_fast_path_smart_home(dummy_llm):
    router = LLMIntentRouter(llm_client=dummy_llm, ml_fast_path_enabled=True)
    res = router.parse_intent("tat may lanh phong ngu")
    assert res.action_name == "home_assistant_call"
    assert res.parameters.get("domain") in ("climate", "switch")
    assert res.parameters.get("service") == "turn_off"


def test_router_ml_fast_path_reminder(dummy_llm):
    router = LLMIntentRouter(llm_client=dummy_llm, ml_fast_path_enabled=True)
    res = router.parse_intent("nhắc tôi uống thuốc sau 1 tiếng")
    assert res.action_name == "reminder"
    assert "uống thuốc" in res.parameters.get("message", "") or res.parameters.get("duration_seconds") == 3600.0


def test_router_ml_offline_automatic_fallback():
    # When llm is None (offline edge mode), ML classifier automatically resolves intent!
    router = LLMIntentRouter(llm_client=None)
    res = router.parse_intent("tat may lanh phong ngu")
    assert res.action_name == "home_assistant_call"


def test_router_ml_disabled_graceful_fallback(dummy_llm):
    router = LLMIntentRouter(llm_client=dummy_llm)
    # Explicitly disable ML classifier
    router.ml_classifier = None
    # Standard rule command should still work
    res = router.parse_intent("tăng âm lượng")
    assert res.action_name == "system_volume"
