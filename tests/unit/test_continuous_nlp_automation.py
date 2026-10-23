"""
tests/unit/test_continuous_nlp_automation.py
============================================
Unit tests for Continuous Learning Loop & Quality Gating:
  - UnrecognizedTurnCollector: PII scrubbing, record storage, count.
  - ContinuousDatasetManager: Deduplication, label conflicts.
  - AutomatedEvaluatorGate: CV thresholds & golden regression enforcement.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jarvis.llm.local_classifier import ClassificationResult, VietnameseNLPClassifier
from jarvis.nlp.automation.dataset_manager import ContinuousDatasetManager
from jarvis.nlp.automation.evaluator_gate import AutomatedEvaluatorGate
from jarvis.nlp.automation.unrecognized_collector import (
    UnrecognizedTurnCollector,
    scrub_pii,
)


def test_scrub_pii():
    text = "Gửi mật khẩu 123456 vào email hung@gmail.com hoặc gọi 0912345678 kèm thẻ 1234-5678-9012-3456"
    scrubbed = scrub_pii(text)
    assert "hung@gmail.com" not in scrubbed
    assert "[REDACTED_EMAIL]" in scrubbed
    assert "0912345678" not in scrubbed
    assert "[REDACTED_PHONE]" in scrubbed
    assert "123456" not in scrubbed
    assert "[REDACTED_PASSWORD]" in scrubbed
    assert "1234-5678-9012-3456" not in scrubbed
    assert "[REDACTED_CARD]" in scrubbed


def test_unrecognized_turn_collector_lifecycle():
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "test_feedback.jsonl"
        collector = UnrecognizedTurnCollector(log_path=log_file)

        assert collector.count_turns() == 0

        # Record turns
        ok1 = collector.record_turn("câu lệnh lạ 1", confidence=0.25, source="test")
        ok2 = collector.record_turn("câu lệnh lạ 2 với email test@domain.com", confidence=0.30, source="test")
        assert ok1 is True
        assert ok2 is True

        assert collector.count_turns() == 2
        loaded = collector.load_turns()
        assert len(loaded) == 2
        assert loaded[0].raw_text == "câu lệnh lạ 1"
        assert "[REDACTED_EMAIL]" in loaded[1].raw_text

        # Clear
        assert collector.clear() is True
        assert collector.count_turns() == 0


def test_continuous_dataset_manager_dedup_and_conflicts():
    canonical = [
        ("tăng âm lượng", "system_volume"),
        ("giảm âm lượng", "system_volume"),
    ]
    manager = ContinuousDatasetManager(canonical_data=canonical)
    assert manager.total_samples == 2

    # Add duplicate
    added = manager.add_samples([("TĂNG ÂM LƯỢNG", "system_volume")])
    assert added == 0
    assert manager.total_samples == 2

    # Add new unique
    added = manager.add_samples([("bật đèn phòng khách", "smart_home")])
    assert added == 1
    assert manager.total_samples == 3

    # Add conflicting label
    manager.add_samples([("tăng âm lượng", "system_brightness")])
    assert len(manager.conflicts) == 1
    assert manager.conflicts[0].existing_label == "system_volume"
    assert manager.conflicts[0].new_label == "system_brightness"


def test_automated_evaluator_gate_pass():
    mock_clf = MagicMock(spec=VietnameseNLPClassifier)
    # Mock predict to always return expected intent
    mock_clf.predict.side_effect = lambda q: ClassificationResult(
        intent="system_volume" if "âm lượng" in q or "tiếng" in q else "app_launch",
        confidence=0.95,
        all_scores={},
        latency_ms=1.0,
    )

    gate = AutomatedEvaluatorGate(
        min_cv_accuracy=0.95,
        min_cv_f1=0.90,
        golden_tests=[("tăng âm lượng", "system_volume"), ("mở chrome", "app_launch")],
    )

    report = {"cv_accuracy_mean": 0.98, "cv_f1_macro_mean": 0.97}
    res = gate.evaluate(mock_clf, report)
    assert res.passed is True
    assert len(res.rejection_reasons) == 0


def test_automated_evaluator_gate_fail_closed_on_low_accuracy():
    mock_clf = MagicMock(spec=VietnameseNLPClassifier)
    gate = AutomatedEvaluatorGate(min_cv_accuracy=0.975, min_cv_f1=0.960, golden_tests=[])

    # Low CV accuracy
    report = {"cv_accuracy_mean": 0.92, "cv_f1_macro_mean": 0.91}
    res = gate.evaluate(mock_clf, report)
    assert res.passed is False
    assert any("CV Accuracy" in r for r in res.rejection_reasons)
