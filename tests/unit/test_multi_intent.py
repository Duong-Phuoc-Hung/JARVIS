"""
tests/unit/test_multi_intent.py
===============================
Unit tests for Compound Multi-Intent Decomposer and Sequential Execution Pipeline.
Verifies:
  - Splitting compound utterances joined by conjunctions ('và', 'rồi', 'đồng thời', 'sau đó').
  - Predicate ellipsis resolution (inheriting verbs for elided clauses).
  - Entity protection for search queries and media titles (preventing false splits).
  - Integration with LLMIntentRouter.parse_multi_intent.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from jarvis.llm.client import LLMClient
from jarvis.llm.router import LLMIntentRouter
from jarvis.nlp.multi_intent import (
    CompoundIntentDecomposer,
    split_compound_utterance,
)


def test_split_single_utterance():
    text = "tăng âm lượng lên 80%"
    clauses = split_compound_utterance(text)
    assert len(clauses) == 1
    assert clauses[0] == "tăng âm lượng lên 80%"


def test_split_two_distinct_actions():
    text = "tắt đèn phòng khách và bật điều hòa 24 độ"
    clauses = split_compound_utterance(text)
    assert len(clauses) == 2
    assert "tắt đèn phòng khách" in clauses[0]
    assert "bật điều hòa 24 độ" in clauses[1]


def test_split_three_actions_with_various_conjunctions():
    text = "mở chrome, sau đó bật spotify rồi tăng âm lượng lên 70%"
    clauses = split_compound_utterance(text)
    assert len(clauses) == 3
    assert "mở chrome" in clauses[0]
    assert "bật spotify" in clauses[1]
    assert "tăng âm lượng lên 70%" in clauses[2]


def test_split_predicate_ellipsis_resolution():
    # 'tắt đèn phòng khách và phòng ngủ' -> elided verb 'tắt đèn' should be restored
    text = "tắt đèn phòng khách và phòng ngủ"
    clauses = split_compound_utterance(text)
    assert len(clauses) == 2
    assert "tắt đèn phòng khách" in clauses[0]
    assert "tắt đèn phòng ngủ" in clauses[1]


def test_entity_protection_web_search():
    # Conjunction inside search query should not be split
    text = "tìm kiếm tom và jerry trên mạng"
    clauses = split_compound_utterance(text)
    assert len(clauses) == 1
    assert "tom và jerry" in clauses[0]


def test_router_parse_multi_intent_integration():
    mock_llm = MagicMock(spec=LLMClient)
    router = LLMIntentRouter(llm_client=mock_llm, ml_fast_path_enabled=True)

    text = "tắt đèn phòng khách và bật điều hòa 24 độ"
    results = router.parse_multi_intent(text)
    assert len(results) == 2

    # Intent 1: smart_home light off
    assert results[0].action_name == "home_assistant_call"
    assert results[0].parameters.get("domain") == "light"
    assert results[0].parameters.get("service") == "turn_off"

    # Intent 2: smart_home climate on with temp 24
    assert results[1].action_name == "home_assistant_call"
    assert results[1].parameters.get("domain") in ("climate", "switch")
    assert results[1].parameters.get("service") == "turn_on"
    assert results[1].parameters.get("temperature") == 24


def test_router_compound_action_backward_compatibility():
    mock_llm = MagicMock(spec=LLMClient)
    router = LLMIntentRouter(llm_client=mock_llm, ml_fast_path_enabled=True)

    text = "tắt đèn phòng khách và bật điều hòa 24 độ"
    single_res = router.parse_intent(text)
    assert single_res.action_name == "compound_multi_action"
    assert "actions" in single_res.parameters
    assert len(single_res.parameters["actions"]) == 2
