"""
tests/unit/test_local_classifier.py
====================================
Unit tests for on-device Vietnamese NLP Intent Classifier.
Verifies text normalization, training, confidence calibration,
Windows atomic persistence, and latency bounds.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from jarvis.llm.local_classifier import (
    ClassificationResult,
    VietnameseNLPClassifier,
    normalize_vietnamese_text,
)


def test_normalize_vietnamese_text():
    assert normalize_vietnamese_text("") == ""
    assert normalize_vietnamese_text("   ") == ""
    assert normalize_vietnamese_text("Tăng Âm Lượng!!!") == "tăng âm lượng"
    assert normalize_vietnamese_text("Mở Chrome, rồi bật nhạc?") == "mở chrome rồi bật nhạc"
    assert normalize_vietnamese_text("  chào   JARVIS   nhé  ") == "chào jarvis nhé"


def test_untrained_classifier_predict():
    with tempfile.TemporaryDirectory() as tmpdir:
        dummy_path = Path(tmpdir) / "nonexistent.joblib"
        clf = VietnameseNLPClassifier(model_path=dummy_path)
        assert clf.is_trained is False

        result = clf.predict("xin chào jarvis")
        assert isinstance(result, ClassificationResult)
        assert result.intent == "unknown"
        assert result.confidence == 0.0
        assert result.all_scores == {}
        assert result.latency_ms >= 0.0


def test_train_insufficient_samples_raises():
    clf = VietnameseNLPClassifier(model_path=Path("dummy.joblib"))
    with pytest.raises(ValueError, match="Insufficient"):
        clf.train(samples=["câu 1", "câu 2"], labels=["a", "b"])

    with pytest.raises(ValueError, match="distinct intent classes"):
        clf.train(samples=["câu " + str(i) for i in range(12)], labels=["a"] * 12)


def test_train_save_and_predict_roundtrip():
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
        "system_volume",
        "system_volume",
        "system_volume",
        "system_volume",
        "system_volume",
        "system_volume",
        "system_volume",
        "system_volume",
        "system_volume",
        "smart_home",
        "smart_home",
        "smart_home",
        "smart_home",
        "smart_home",
        "smart_home",
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        model_file = Path(tmpdir) / "test_model.joblib"
        clf = VietnameseNLPClassifier(model_path=model_file, min_confidence=0.35)

        # Train with 3-fold CV
        report = clf.train(samples=samples, labels=labels, cv_folds=3)
        assert clf.is_trained is True
        assert report["num_samples"] == len(samples)
        assert report["num_classes"] == 2
        assert "cv_accuracy_mean" in report

        # Predict
        res_vol = clf.predict("vặn to loa lên")
        assert res_vol.intent == "system_volume"
        assert res_vol.confidence >= 0.35
        assert "system_volume" in res_vol.all_scores
        assert "smart_home" in res_vol.all_scores
        assert sum(res_vol.all_scores.values()) == pytest.approx(1.0, abs=1e-3)

        res_light = clf.predict("bật đèn trần")
        assert res_light.intent == "smart_home"
        assert res_light.confidence >= 0.35

        # Test atomic save and reload
        saved = clf.save()
        assert saved is True
        assert model_file.exists()

        # Reload in a fresh instance
        clf2 = VietnameseNLPClassifier(model_path=model_file)
        assert clf2.is_trained is True
        res_reload = clf2.predict("tắt đèn phòng ngủ")
        assert res_reload.intent == "smart_home"


def test_confidence_threshold_fallback():
    with tempfile.TemporaryDirectory() as tmpdir:
        model_file = Path(tmpdir) / "high_thresh.joblib"
        clf = VietnameseNLPClassifier(model_path=model_file, min_confidence=0.99)
        samples = [
            "tăng âm lượng",
            "cho âm lượng to",
            "vặn to loa",
            "bật đèn",
            "tắt đèn",
            "mở đèn",
        ] * 3
        labels = ["volume", "volume", "volume", "light", "light", "light"] * 3
        clf.train(samples, labels, cv_folds=3)

        # Query that is somewhat ambiguous or does not reach 0.99
        res = clf.predict("hôm nay thời tiết thế nào bạn ơi")
        # Since confidence won't exceed 0.99, intent must be 'unknown'
        assert res.intent == "unknown"


def test_production_model_if_exists():
    default_model = Path("data/models/vietnamese_nlp_intent.joblib")
    if not default_model.exists():
        pytest.skip("Production model artifact not yet trained on disk.")

    clf = VietnameseNLPClassifier(model_path=default_model, min_confidence=0.35)
    assert clf.is_trained is True
    assert len(clf.classes_) >= 10

    test_queries = [
        ("vặn nhỏ âm lượng loa xuống đi", "system_volume"),
        ("chỉnh màn hình tối bớt chói quá", "system_brightness"),
        ("mở visual studio code", "app_launch"),
        ("dừng phát nhạc", "media_control"),
        ("nhiệt độ cpu hiện tại bao nhiêu", "system_status"),
        ("bật đèn phòng khách", "smart_home"),
        ("đặt hẹn giờ 10 phút", "timer_reminder"),
        ("tìm kiếm thông tin trên google", "web_search"),
        ("chào jarvis", "greeting_chat"),
    ]

    for query, expected_intent in test_queries:
        res = clf.predict(query)
        assert res.intent == expected_intent, f"Query '{query}' predicted {res.intent}, expected {expected_intent}"
        assert res.confidence >= 0.35
        assert res.latency_ms < 50.0  # Must be fast on local CPU


def test_extract_slots_various_intents():
    from jarvis.llm.local_classifier import extract_slots_for_intent

    # System volume
    slots_vol = extract_slots_for_intent("system_volume", "cho âm lượng lên 80%")
    assert slots_vol.get("target_level") == 80
    assert slots_vol.get("action") == "set"

    slots_mute = extract_slots_for_intent("system_volume", "tat am thanh")
    assert slots_mute.get("action") == "mute"

    slots_vol_inc = extract_slots_for_intent("system_volume", "tăng âm lượng lên xíu")
    assert slots_vol_inc.get("action") == "increase"
    assert slots_vol_inc.get("delta") == 10

    # System brightness
    slots_bri = extract_slots_for_intent("system_brightness", "chỉnh độ sáng lên 90%")
    assert slots_bri.get("target_level") == 90
    assert slots_bri.get("action") == "set"

    # App launch & close
    slots_launch = extract_slots_for_intent("app_launch", "mo chrome")
    assert slots_launch.get("app_name") == "chrome"

    slots_close = extract_slots_for_intent("app_close", "dong trinh duyet chrome")
    assert slots_close.get("app_name") == "chrome"

    # Smart home
    slots_home = extract_slots_for_intent("smart_home", "tat may lanh phong ngu")
    assert slots_home.get("device") == "climate"
    assert slots_home.get("location") == "bedroom"
    assert slots_home.get("state") == "off"

    slots_ac = extract_slots_for_intent("smart_home", "bật điều hòa 24 độ")
    assert slots_ac.get("device") == "climate"
    assert slots_ac.get("state") == "on"
    assert slots_ac.get("temperature") == 24

    # Timer & reminder
    slots_timer = extract_slots_for_intent("timer_reminder", "hẹn giờ 10 phút")
    assert slots_timer.get("duration_seconds") == 600.0
    assert slots_timer.get("type") == "timer"

    slots_remind = extract_slots_for_intent("timer_reminder", "nhắc tôi uống thuốc sau 1 tiếng")
    assert slots_remind.get("type") == "reminder"
    assert slots_remind.get("duration_seconds") == 3600.0
    assert "uống thuốc sau 1 tiếng" in slots_remind.get("message", "")

    # Web search
    slots_search = extract_slots_for_intent("web_search", "tra cứu thời tiết sài gòn ngày mai")
    assert "thời tiết sài gòn ngày mai" in slots_search.get("query", "")


def test_unaccented_speech_recognition_on_production_model():
    default_model = Path("data/models/vietnamese_nlp_intent.joblib")
    if not default_model.exists():
        pytest.skip("Production model artifact not available.")

    clf = VietnameseNLPClassifier(model_path=default_model, min_confidence=0.35)
    assert clf.is_trained is True

    unaccented_queries = [
        ("tang am luong", "system_volume"),
        ("tat am thanh", "system_volume"),
        ("mo chrome", "app_launch"),
        ("dong visual studio code", "app_close"),
        ("chuyen sang bai hat tiep theo", "media_control"),
        ("tat may lanh phong ngu", "smart_home"),
        ("hen gio 10 phut", "timer_reminder"),
        ("ram con trong bao nhieu", "system_status"),
    ]

    for q, exp_intent in unaccented_queries:
        res = clf.predict(q)
        assert res.intent == exp_intent, f"Unaccented '{q}' -> got {res.intent}, expected {exp_intent}"


def test_ood_negative_sample_rejection():
    default_model = Path("data/models/vietnamese_nlp_intent.joblib")
    if not default_model.exists():
        pytest.skip("Production model artifact not available.")

    clf = VietnameseNLPClassifier(model_path=default_model, min_confidence=0.40)
    assert clf.is_trained is True

    ood_queries = [
        "công thức nấu món phở bò truyền thống",
        "giải bài toán phương trình bậc hai",
        "chiến tranh thế giới thứ hai diễn ra năm nào",
        "núi everest cao bao nhiêu mét",
    ]

    for q in ood_queries:
        res = clf.predict(q)
        assert res.intent == "unknown", f"OOD '{q}' should be unknown, got {res.intent} (conf={res.confidence:.2f})"


def test_predict_batch():
    default_model = Path("data/models/vietnamese_nlp_intent.joblib")
    if not default_model.exists():
        pytest.skip("Production model artifact not available.")

    clf = VietnameseNLPClassifier(model_path=default_model)
    queries = ["tăng âm lượng", "bật đèn phòng khách", "xin chào jarvis"]
    results = clf.predict_batch(queries)
    assert len(results) == 3
    assert results[0].intent == "system_volume"
    assert results[1].intent == "smart_home"
    assert results[2].intent == "greeting_chat"
