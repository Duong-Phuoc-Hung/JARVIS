"""
tests/test_rebuilt_nlp.py
=========================
Behavioral tests for rebuilt/nlp_classifier.py.
Verifies rules NLP-01 through NLP-11 (NTEST-01 to NTEST-11).
"""
from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

import pytest

REBUILT_DIR = Path(__file__).resolve().parent.parent
if str(REBUILT_DIR) not in sys.path:
    sys.path.insert(0, str(REBUILT_DIR))

from nlp_classifier import (
    ClassificationResult,
    VietnameseNLPClassifier,
    normalize_vietnamese_text,
)


def test_ntest_01_normalization_empty_and_whitespace():
    """NTEST-01: Empty string or whitespace normalizes to empty string."""
    assert normalize_vietnamese_text("") == ""
    assert normalize_vietnamese_text("   \t\n  ") == ""


def test_ntest_02_normalization_vietnamese_punctuation():
    """NTEST-02: Punctuation is stripped, accents and lower-case preserved."""
    assert normalize_vietnamese_text("  TÀI CHÍNH!!!  ") == "tài chính"
    assert normalize_vietnamese_text("Bật đèn phòng khách???") == "bật đèn phòng khách"


def test_ntest_03_untrained_classifier_fallback():
    """NTEST-03: Untrained classifier returns intent='unknown' and confidence=0.0 without exception."""
    with tempfile.TemporaryDirectory() as tmpdir:
        dummy_path = Path(tmpdir) / "empty_model.joblib"
        clf = VietnameseNLPClassifier(model_path=dummy_path)
        assert clf.is_trained is False

        res = clf.predict("xin chào jarvis")
        assert isinstance(res, ClassificationResult)
        assert res.intent == "unknown"
        assert res.confidence == 0.0
        assert res.all_scores == {}
        assert res.latency_ms >= 0.0


def test_ntest_04_training_validation_insufficient_samples():
    """NTEST-04: Training with < 10 samples raises ValueError with 'Insufficient'."""
    clf = VietnameseNLPClassifier(model_path=Path("dummy.joblib"))
    with pytest.raises(ValueError, match="Insufficient"):
        clf.train(samples=["câu 1", "câu 2"], labels=["a", "b"])


def test_ntest_05_training_validation_single_class():
    """NTEST-05: Training with single unique class raises ValueError with 'distinct intent classes'."""
    clf = VietnameseNLPClassifier(model_path=Path("dummy.joblib"))
    with pytest.raises(ValueError, match="distinct intent classes"):
        clf.train(samples=["câu " + str(i) for i in range(12)], labels=["single_class"] * 12)


def test_ntest_06_train_and_predict_flow():
    """NTEST-06: Train with multi-class data yields successful prediction >= 0.35."""
    samples = [
        "tăng âm lượng",
        "tăng âm lượng lên",
        "cho âm thanh to hơn",
        "vặn to loa",
        "bật to tiếng",
        "giảm âm lượng",
        "giảm âm lượng xuống",
        "vặn nhỏ loa lại",
        "cho nhỏ tiếng",
        "bật đèn",
        "bật đèn phòng khách",
        "bật đèn phòng ngủ",
        "tắt đèn",
        "tắt đèn phòng khách",
        "tắt hết đèn đi",
    ]
    labels = [
        "volume", "volume", "volume", "volume", "volume",
        "volume", "volume", "volume", "volume",
        "light", "light", "light", "light", "light", "light",
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        model_file = Path(tmpdir) / "trained.joblib"
        clf = VietnameseNLPClassifier(model_path=model_file, min_confidence=0.35)
        report = clf.train(samples=samples, labels=labels, cv_folds=2)

        assert clf.is_trained is True
        assert report["num_samples"] == len(samples)

        res = clf.predict("vặn to loa lên")
        assert res.intent == "volume"
        assert res.confidence >= 0.35


def test_ntest_07_all_scores_sum_to_one():
    """NTEST-07: Predicted class probabilities sum to 1.0 (within 1e-3)."""
    samples = ["bật đèn " + str(i) for i in range(8)] + ["tăng loa " + str(i) for i in range(8)]
    labels = ["light"] * 8 + ["volume"] * 8

    with tempfile.TemporaryDirectory() as tmpdir:
        clf = VietnameseNLPClassifier(model_path=Path(tmpdir) / "m.joblib")
        clf.train(samples, labels, cv_folds=2)
        res = clf.predict("bật đèn")
        assert sum(res.all_scores.values()) == pytest.approx(1.0, abs=1e-3)


def test_ntest_08_confidence_threshold_fallback():
    """NTEST-08: When top score does not meet min_confidence, intent falls back to 'unknown'."""
    samples = ["bật đèn " + str(i) for i in range(8)] + ["tăng loa " + str(i) for i in range(8)]
    labels = ["light"] * 8 + ["volume"] * 8

    with tempfile.TemporaryDirectory() as tmpdir:
        clf = VietnameseNLPClassifier(model_path=Path(tmpdir) / "m.joblib", min_confidence=0.99)
        clf.train(samples, labels, cv_folds=2)
        res = clf.predict("thời tiết hôm nay ra sao")
        assert res.intent == "unknown"


def test_ntest_09_save_and_reload_persistence():
    """NTEST-09: Atomic save persists model that reloads faithfully in a new instance."""
    samples = ["bật đèn " + str(i) for i in range(8)] + ["tắt đèn " + str(i) for i in range(8)]
    labels = ["on"] * 8 + ["off"] * 8

    with tempfile.TemporaryDirectory() as tmpdir:
        model_file = Path(tmpdir) / "saved_model.joblib"
        clf1 = VietnameseNLPClassifier(model_path=model_file)
        clf1.train(samples, labels, cv_folds=2)
        assert clf1.save() is True
        assert model_file.exists()

        clf2 = VietnameseNLPClassifier(model_path=model_file)
        assert clf2.is_trained is True
        res = clf2.predict("bật đèn phòng khách")
        assert res.intent == "on"


def test_ntest_10_prediction_latency_bound():
    """NTEST-10: On-device CPU inference completes within 50ms bound."""
    samples = ["lệnh " + str(i) for i in range(10)] + ["hành động " + str(i) for i in range(10)]
    labels = ["cmd"] * 10 + ["act"] * 10

    with tempfile.TemporaryDirectory() as tmpdir:
        clf = VietnameseNLPClassifier(model_path=Path(tmpdir) / "m.joblib")
        clf.train(samples, labels, cv_folds=2)
        res = clf.predict("thực hiện hành động")
        assert res.latency_ms < 50.0


def test_ntest_11_concurrent_predictions():
    """NTEST-11: 10 concurrent threads executing predict encounter no race conditions."""
    samples = ["bật đèn " + str(i) for i in range(8)] + ["tăng loa " + str(i) for i in range(8)]
    labels = ["light"] * 8 + ["volume"] * 8

    with tempfile.TemporaryDirectory() as tmpdir:
        clf = VietnameseNLPClassifier(model_path=Path(tmpdir) / "m.joblib")
        clf.train(samples, labels, cv_folds=2)

        results = []
        errors = []

        def worker():
            try:
                for _ in range(10):
                    r = clf.predict("bật đèn")
                    results.append(r.intent)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert len(errors) == 0
        assert len(results) == 100
        assert all(intent == "light" for intent in results)
