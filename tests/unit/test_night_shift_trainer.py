"""
tests/unit/test_night_shift_trainer.py
======================================
Unit tests for Autonomous Night-Shift Continuous Learning Flywheel.
Tests:
  - PII scrubbing on feedback ingestion.
  - Unsupervised semantic clustering of unrecognized turns.
  - Counterfactual phonetic and unaccented data augmentation.
  - End-to-end retraining cycle with AutomatedEvaluatorGate verification.
  - Fail-closed refusal to deploy when quality thresholds are not met.
  - Immutable audit logging to JSONLines log.
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
import pytest

from jarvis.llm.local_classifier import VietnameseNLPClassifier
from jarvis.nlp.automation.unrecognized_collector import UnrecognizedTurnCollector
from jarvis.workers.night_shift_trainer import (
    NightShiftConfig,
    NightShiftReport,
    NightShiftTrainer,
)


def test_night_shift_pii_scrubbing_and_ingestion():
    """Verify that sensitive user data is redacted before training ingestion."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fb_path = Path(tmpdir) / "unrecognized_turns.jsonl"
        collector = UnrecognizedTurnCollector(log_path=fb_path)

        # Record turns with PII
        collector.record_turn(
            raw_text="mở email của user@domain.com và mật khẩu là Secret123",
            confidence=0.2,
        )
        collector.record_turn(
            raw_text="gọi đến số 0987654321 cho tôi",
            confidence=0.3,
        )
        collector.record_turn(
            raw_text="tăng âm lượng lên 80%",
            confidence=0.1,
        )

        cfg = NightShiftConfig(feedback_file=fb_path)
        trainer = NightShiftTrainer(config=cfg)

        ingested = trainer.ingest_unrecognized_turns()
        assert len(ingested) >= 2
        for text in ingested:
            assert "Secret123" not in text
            assert "user@domain.com" not in text
            assert "0987654321" not in text


def test_night_shift_clustering_and_augmentation():
    """Verify semantic clustering and multi-axis augmentation."""
    trainer = NightShiftTrainer()

    queries = [
        "bật đèn phòng khách",
        "bật đèn nhà bếp",
        "mở đèn phòng khách",
        "tăng âm lượng loa",
        "cho âm lượng to hơn",
    ]
    clusters = trainer.cluster_unknown_queries(queries)
    assert len(clusters) >= 2

    # Test augmentation
    base = [("bật đèn phòng khách", "smart_home"), ("tăng âm lượng", "system_volume")]
    augmented = trainer.augment_dataset(base)
    assert len(augmented) > len(base)
    texts = [a[0] for a in augmented]
    # Contains unaccented variant
    assert "bat den phong khach" in texts or "tang am luong" in texts


def test_night_shift_full_cycle_success():
    """Verify full successful night-shift cycle passing all gating requirements."""
    with tempfile.TemporaryDirectory() as tmpdir:
        model_path = Path(tmpdir) / "test_model.joblib"
        joint_path = Path(tmpdir) / "test_joint.joblib"
        audit_path = Path(tmpdir) / "night_shift_audit.log"
        fb_path = Path(tmpdir) / "feedback.jsonl"

        # Provide a few feedback turns
        fb_path.write_text(
            json.dumps({"raw_text": "chỉnh độ sáng màn hình lên 80%"}) + "\n" +
            json.dumps({"raw_text": "vặn nhỏ loa xuống"}) + "\n",
            encoding="utf-8",
        )

        cfg = NightShiftConfig(
            feedback_file=fb_path,
            model_path=model_path,
            joint_model_path=joint_path,
            audit_log=audit_path,
            min_cv_accuracy=0.90,
            min_cv_f1=0.88,
            cv_folds=3,
        )

        active_clf = VietnameseNLPClassifier(model_path=model_path)
        trainer = NightShiftTrainer(config=cfg, active_classifier=active_clf)

        report = trainer.run_training_cycle()

        assert report.gating_passed is True
        assert report.cv_accuracy >= 0.90
        assert report.golden_accuracy == 1.0
        assert report.hot_reload_success is True
        assert model_path.exists()
        assert audit_path.exists()

        # Audit log format check
        lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1
        entry = json.loads(lines[-1])
        assert entry["gating_passed"] is True
        assert entry["hot_reload_success"] is True


def test_night_shift_fail_closed_on_strict_gate():
    """Verify fail-closed behavior when impossible gating threshold rejects candidate."""
    with tempfile.TemporaryDirectory() as tmpdir:
        model_path = Path(tmpdir) / "test_model.joblib"
        audit_path = Path(tmpdir) / "night_shift_audit.log"
        fb_path = Path(tmpdir) / "feedback.jsonl"

        # Initial dummy model
        model_path.write_text("initial_valid_model", encoding="utf-8")

        cfg = NightShiftConfig(
            feedback_file=fb_path,
            model_path=model_path,
            audit_log=audit_path,
            min_cv_accuracy=0.9999,  # Unattainable threshold to force rejection
            min_cv_f1=0.9999,
            cv_folds=3,
        )

        trainer = NightShiftTrainer(config=cfg)
        report = trainer.run_training_cycle()

        assert report.gating_passed is False
        assert report.hot_reload_success is False
        assert len(report.rejection_reasons) > 0
        # Original model file must NOT have been overwritten
        assert model_path.read_text(encoding="utf-8") == "initial_valid_model"
