"""
tests/eval/test_voice_generalization_heldout.py
===============================================
Held-out generalization evaluation test suite (Milestone 4 - Anti-Overfitting).

Purpose:
  Evaluates JARVIS Voice Pipeline v4.8.1 Intent Router on completely unseen utterances
  that have ZERO overlap with PHRASE_MANIFEST (the 45 recorded acoustic training phrases).
  Guarantees that improvements from diacritic normalization and phonetic drift aliases
  do not overfit or degrade routing performance on fresh, realistic voice inputs.

Acceptance Criteria:
  - Total unseen utterances: >= 25–30 (here: 35 cases across 7 domains).
  - Covered domains: weather, reminder, system, search, volume, notes, apps (>= 5 cases each).
  - Overlap with PHRASE_MANIFEST: exactly 0.
  - CORRECT rate: >= 85% (target: 100%).
  - MISROUTED count: 0.
  - 100% pytest pass.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from jarvis.llm.client import LLMClient, LLMResponse
from jarvis.llm.router import LLMIntentRouter
from jarvis.core.dispatcher import ActionDispatcher
from tests.eval.phrase_manifest import PHRASE_MANIFEST


# ─── HELD-OUT TEST CORPUS: 35 Unseen Utterances across 7 Domains ─────────────
# Guaranteed ZERO overlap with PHRASE_MANIFEST (the 45 acoustic eval phrases).
HELDOUT_TEST_SET: list[tuple[str, str, str]] = [
    # 1. Weather domain (expected: shell_exec)
    ("thời tiết hà nội", "shell_exec", "weather"),
    ("weather today", "shell_exec", "weather"),
    ("weather forecast", "shell_exec", "weather"),
    ("bao nhiêu độ", "shell_exec", "weather"),
    ("thoi tiet ha noi", "shell_exec", "weather"),

    # 2. Reminder domain (expected: reminder)
    ("đặt báo thức", "reminder", "reminder"),
    ("tạo nhắc nhở", "reminder", "reminder"),
    ("đặt lịch", "reminder", "reminder"),
    ("nhắc tôi", "reminder", "reminder"),
    ("reminder", "reminder", "reminder"),

    # 3. System domain (power, lock, display; expected: system_power / system_brightness)
    ("turn off computer", "system_power", "system"),
    ("power off", "system_power", "system"),
    ("tắt máy đi", "system_power", "system"),
    ("restart windows", "system_power", "system"),
    ("tắt monitor", "system_brightness", "system"),

    # 4. Search domain (web search & file search; expected: web_open / file_search)
    ("tìm kiếm trên google", "web_open", "search"),
    ("google thời tiết", "web_open", "search"),
    ("search for news", "web_open", "search"),
    ("tìm file pdf", "file_search", "search"),
    ("find file", "file_search", "search"),

    # 5. Volume domain (expected: system_volume)
    ("volume up", "system_volume", "volume"),
    ("volume down", "system_volume", "volume"),
    ("giảm âm", "system_volume", "volume"),
    ("bật tiếng", "system_volume", "volume"),
    ("giam am luong", "system_volume", "volume"),

    # 6. Notes & memory domain (expected: memory_save_fact / memory_summarize_daily)
    ("nhớ rằng", "memory_save_fact", "notes"),
    ("lưu lại", "memory_save_fact", "notes"),
    ("tôi tên là", "memory_save_fact", "notes"),
    ("save this", "memory_save_fact", "notes"),
    ("tóm tắt hôm nay", "memory_summarize_daily", "notes"),

    # 7. Apps domain (expected: app_open)
    ("mở word", "app_open", "apps"),
    ("mở excel", "app_open", "apps"),
    ("mở calculator", "app_open", "apps"),
    ("mở terminal", "app_open", "apps"),
    ("cài đặt hệ thống", "app_open", "apps"),
]


@pytest.fixture(scope="module")
def router() -> LLMIntentRouter:
    """Instantiate Tier-1 production router without external LLM dependency."""
    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.generate.return_value = LLMResponse(
        content="Default mock response", tool_calls=[], model="mock"
    )
    dispatcher = ActionDispatcher()
    return LLMIntentRouter(llm_client=mock_llm, dispatcher=dispatcher, fast_path_enabled=True)


def test_zero_manifest_overlap():
    """Verify strictly 0 overlap between held-out test utterances and PHRASE_MANIFEST."""
    all_manifest_phrases = {
        phrase.strip().lower()
        for phrase_list in PHRASE_MANIFEST.values()
        for phrase in phrase_list
    }
    assert len(all_manifest_phrases) == 45, f"Expected 45 manifest phrases, got {len(all_manifest_phrases)}"

    heldout_utterances = [u.strip().lower() for u, _, _ in HELDOUT_TEST_SET]
    assert len(heldout_utterances) >= 30, f"Expected >= 30 heldout utterances, got {len(heldout_utterances)}"

    overlap = set(heldout_utterances).intersection(all_manifest_phrases)
    assert not overlap, f"Violation: held-out set must have 0 overlap with PHRASE_MANIFEST, found: {overlap}"


def test_seven_domains_covered():
    """Verify all 7 required domains are represented with >= 3 utterances each."""
    expected_domains = {"weather", "reminder", "system", "search", "volume", "notes", "apps"}
    domains_present = {domain for _, _, domain in HELDOUT_TEST_SET}
    assert expected_domains.issubset(domains_present), f"Missing domains: {expected_domains - domains_present}"

    for domain in expected_domains:
        domain_items = [u for u, _, d in HELDOUT_TEST_SET if d == domain]
        assert len(domain_items) >= 3, f"Domain {domain} has insufficient items: {len(domain_items)}"


@pytest.mark.parametrize("utterance,expected_action,domain", HELDOUT_TEST_SET)
def test_heldout_individual_utterance_routing(router: LLMIntentRouter, utterance: str, expected_action: str, domain: str):
    """Test individual held-out utterance routes correctly to the expected action."""
    res = router.parse_intent(utterance, force_llm=False)
    assert res is not None, f"Router returned None for '{utterance}'"
    assert res.action_name == expected_action, (
        f"Mismatch for '{utterance}' in domain '{domain}': "
        f"expected '{expected_action}', got '{res.action_name}'"
    )


def test_heldout_aggregate_metrics(router: LLMIntentRouter):
    """
    Verify aggregate held-out generalization metrics:
    CORRECT >= 85%, MISROUTED == 0.
    """
    total = len(HELDOUT_TEST_SET)
    correct_count = 0
    misrouted_count = 0
    abstain_count = 0

    for utterance, expected_action, _ in HELDOUT_TEST_SET:
        res = router.parse_intent(utterance, force_llm=False)
        action = res.action_name if res else "unknown_intent"
        if action in ("unknown_intent", "generic_llm_response", ""):
            abstain_count += 1
        elif action == expected_action:
            correct_count += 1
        else:
            misrouted_count += 1

    correct_rate = correct_count / total
    assert misrouted_count == 0, f"Expected 0 misrouted utterances, got {misrouted_count}"
    assert correct_rate >= 0.85, f"Expected CORRECT >= 85%, got {correct_rate:.1%}"
    assert correct_rate == 1.0, f"Expected 100% accuracy on standard held-out set, got {correct_rate:.1%}"
