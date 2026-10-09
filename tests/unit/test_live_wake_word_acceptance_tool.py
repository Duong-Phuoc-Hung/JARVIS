"""
tests/unit/test_live_wake_word_acceptance_tool.py
===================================================
Unit tests for tools/live_wake_word_acceptance.py.
Verifies fail-closed, evidence-truthful semantics without accessing a real microphone.
Fast execution time: uses simulated time seam to avoid wall-clock delays.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from tools.live_wake_word_acceptance import (
    main,
    parse_args,
    run_wake_word_acceptance,
)

TEST_PROD_CONFIG = {
    "enabled": True,
    "sensitivity": 0.60,
    "cooldown_s": 2.0,
    "allow_packaged_openwakeword_model": True,
    "openwakeword_threshold": 0.50,
    "openwakeword_candidate_threshold": 0.02,
    "openwakeword_verification_enabled": True,
    "openwakeword_verification_postroll_s": 0.40,
    "acoustic_fallback_policy": "auto",
    "whisper_model_size": "tiny",
    "allow_acoustic_passive_trigger": False,
}


@pytest.fixture
def mock_prod_config():
    with patch(
        "tools.live_wake_word_acceptance.get_production_wake_word_config",
        return_value=dict(TEST_PROD_CONFIG),
    ):
        yield TEST_PROD_CONFIG


def make_fast_clock(duration: float):
    current_time = 1000.0

    def mock_time():
        return current_time

    def mock_sleep(step):
        nonlocal current_time
        current_time += duration + 1.0

    return mock_time, mock_sleep


def test_parse_args_defaults_and_validation():
    args = parse_args(["--duration", "25", "--label", "true_wake"])
    assert args.duration == 25.0
    assert args.label == "true_wake"
    assert args.sensitivity is None
    assert args.expected_wakes == 10
    assert args.min_recall == 0.95
    assert args.min_ambient_seconds == 120.0
    assert args.overwrite is False


def test_thresholds_cannot_be_weakened():
    # expected-wakes < 10 must be rejected
    with pytest.raises(SystemExit):
        parse_args(["--expected-wakes", "9"])

    # min-recall < 0.95 must be rejected
    with pytest.raises(SystemExit):
        parse_args(["--min-recall", "0.90"])

    # min-ambient-seconds < 120.0 must be rejected
    with pytest.raises(SystemExit):
        parse_args(["--min-ambient-seconds", "60"])

    with pytest.raises(SystemExit):
        parse_args(["--sensitivity", "-0.01"])

    with pytest.raises(SystemExit):
        parse_args(["--sensitivity", "1.01"])


def test_config_load_failure_returns_not_configured(tmp_path):
    args = parse_args(["--duration", "25", "--out", str(tmp_path / "report.json")])
    with patch("tools.live_wake_word_acceptance.get_production_wake_word_config", return_value=None):
        report = run_wake_word_acceptance(args)
        assert report["status"] == "NOT_CONFIGURED"
        assert report["success"] is False
        assert report["code"] == "CONFIG_LOAD_FAILED"
        assert "CONFIG_LOAD_FAILED" in report["verdict"]


def test_missing_sounddevice_returns_unavailable(tmp_path, mock_prod_config):
    args = parse_args(["--probe-only", "--out", str(tmp_path / "report.json")])
    with patch.dict(sys.modules, {"sounddevice": None}):
        report = run_wake_word_acceptance(args)
        assert report["status"] == "UNAVAILABLE"
        assert report["success"] is False
        assert report["code"] == "MISSING_SOUNDDEVICE"
        assert "MISSING_SOUNDDEVICE" in report["verdict"]


def test_probe_only_success_and_failure(tmp_path, mock_prod_config):
    out = tmp_path / "report.json"
    args = parse_args(["--probe-only", "--out", str(out)])

    mock_sd = MagicMock()
    mock_sd.query_devices.return_value = [{"index": 0, "name": "Mock Mic", "max_input_channels": 1}]
    mock_sd.default.device = [0, 0]

    with patch.dict(sys.modules, {"sounddevice": mock_sd}):
        report = run_wake_word_acceptance(args)
        assert report["status"] == "SUCCESS"
        assert report["success"] is True
        assert report["code"] == "PROBE_SUCCESS"
        assert report["verdict"] == "PASS engineering"

    # Failure case: no mic available
    mock_sd.query_devices.return_value = []
    with patch.dict(sys.modules, {"sounddevice": mock_sd}):
        report = run_wake_word_acceptance(args)
        assert report["status"] == "UNAVAILABLE"
        assert report["success"] is False
        assert report["code"] == "NO_MICROPHONE"


def test_true_wake_feasibility_boundary(tmp_path, mock_prod_config):
    # Cooldown = 2.0s, trial spacing = 2.5s, expected 10 wakes -> minimum required duration = 25.0s
    args_below = parse_args([
        "--duration", "24.9",
        "--label", "true_wake",
        "--expected-wakes", "10",
        "--out", str(tmp_path / "report.json"),
    ])
    report_below = run_wake_word_acceptance(args_below)
    assert report_below["status"] == "BLOCKED"
    assert report_below["success"] is False
    assert report_below["code"] == "INSUFFICIENT_TRUE_WAKE_DURATION"

    # At requirement (25.0s) -> passes feasibility check (and fails at mic or detector pre-flight)
    args_at = parse_args([
        "--duration", "25.0",
        "--label", "true_wake",
        "--expected-wakes", "10",
        "--out", str(tmp_path / "report.json"),
    ])
    with patch.dict(sys.modules, {"sounddevice": None}):
        report_at = run_wake_word_acceptance(args_at)
        assert report_at["code"] == "MISSING_SOUNDDEVICE"  # Passed duration feasibility!


def test_insufficient_ambient_duration_blocked(tmp_path, mock_prod_config):
    # Default min_ambient_seconds = 120.0s, test passing duration = 25.0s
    args = parse_args([
        "--duration", "25.0",
        "--label", "ambient",
        "--min-ambient-seconds", "120.0",
        "--out", str(tmp_path / "report.json"),
    ])
    report = run_wake_word_acceptance(args)
    assert report["status"] == "BLOCKED"
    assert report["success"] is False
    assert report["code"] == "INSUFFICIENT_AMBIENT_DURATION"


def test_engine_mismatch_returns_not_configured(tmp_path, mock_prod_config):
    args = parse_args(["--duration", "25.0", "--out", str(tmp_path / "report.json")])

    mock_sd = MagicMock()
    mock_sd.query_devices.return_value = [{"index": 0, "name": "Mic", "max_input_channels": 1}]
    mock_sd.default.device = [0, 0]

    mock_detector_cls = MagicMock()
    mock_detector = MagicMock()
    mock_detector.engine_type = "vosk"
    mock_detector_cls.return_value = mock_detector

    with patch.dict(sys.modules, {"sounddevice": mock_sd}), patch(
        "jarvis.audio.wake_word.WakeWordDetector", mock_detector_cls
    ):
        report = run_wake_word_acceptance(args)
        assert report["status"] == "NOT_CONFIGURED"
        assert report["success"] is False
        assert report["code"] == "ENGINE_MISMATCH"


def test_verifier_unavailable_returns_unavailable(tmp_path, mock_prod_config):
    args = parse_args(["--duration", "25.0", "--out", str(tmp_path / "report.json")])

    mock_sd = MagicMock()
    mock_sd.query_devices.return_value = [{"index": 0, "name": "Mic", "max_input_channels": 1}]
    mock_sd.default.device = [0, 0]

    mock_detector_cls = MagicMock()
    mock_detector = MagicMock()
    mock_detector.engine_type = "openwakeword"
    mock_detector._whisper_detector._get_model.return_value = None
    mock_detector_cls.return_value = mock_detector

    with patch.dict(sys.modules, {"sounddevice": mock_sd}), patch(
        "jarvis.audio.wake_word.WakeWordDetector", mock_detector_cls
    ):
        report = run_wake_word_acceptance(args)
        assert report["status"] == "UNAVAILABLE"
        assert report["success"] is False
        assert report["code"] == "VERIFIER_UNAVAILABLE"


def test_detector_initialization_failure_returns_structured_error(tmp_path, mock_prod_config):
    args = parse_args(["--duration", "25.0", "--out", str(tmp_path / "report.json")])
    mock_sd = MagicMock()
    mock_sd.query_devices.return_value = [{"index": 0, "name": "Mic", "max_input_channels": 1}]
    mock_sd.default.device = [0, 0]

    with patch.dict(sys.modules, {"sounddevice": mock_sd}), patch(
        "jarvis.audio.wake_word.WakeWordDetector", side_effect=RuntimeError("model load failed")
    ):
        report = run_wake_word_acceptance(args)

    assert report["status"] == "UNAVAILABLE"
    assert report["success"] is False
    assert report["code"] == "DETECTOR_UNAVAILABLE"
    assert report["retryable"] is True


def test_no_audio_evidence_returns_error(tmp_path, mock_prod_config):
    args = parse_args(["--duration", "25.0", "--out", str(tmp_path / "report.json")])

    mock_sd = MagicMock()
    mock_sd.query_devices.return_value = [{"index": 0, "name": "Mic", "max_input_channels": 1}]
    mock_sd.default.device = [0, 0]

    mock_detector_cls = MagicMock()
    mock_detector = MagicMock()
    mock_detector.engine_type = "openwakeword"
    mock_detector._whisper_detector._get_model.return_value = MagicMock()
    mock_detector_cls.return_value = mock_detector

    m_time, m_sleep = make_fast_clock(25.0)

    with patch.dict(sys.modules, {"sounddevice": mock_sd}), patch(
        "jarvis.audio.wake_word.WakeWordDetector", mock_detector_cls
    ):
        report = run_wake_word_acceptance(args, time_func=m_time, sleep_func=m_sleep)
        assert report["status"] == "ERROR"
        assert report["success"] is False
        assert report["code"] == "NO_AUDIO_EVIDENCE"


def test_true_wake_zero_detections_fails(tmp_path, mock_prod_config):
    args = parse_args(["--duration", "25.0", "--label", "true_wake", "--out", str(tmp_path / "report.json")])

    mock_sd = MagicMock()
    mock_sd.query_devices.return_value = [{"index": 0, "name": "Mic", "max_input_channels": 1}]
    mock_sd.default.device = [0, 0]

    def fake_input_stream(*a_inner, **kw_inner):
        callback = kw_inner.get("callback")
        stream_context = MagicMock()

        def enter_stream(*a, **kw):
            if callback:
                callback(MagicMock(), 1600, None, None)
            return stream_context

        stream_context.__enter__ = enter_stream
        stream_context.__exit__ = MagicMock(return_value=False)
        return stream_context

    mock_sd.InputStream = fake_input_stream

    mock_detector_cls = MagicMock()
    mock_detector = MagicMock()
    mock_detector.engine_type = "openwakeword"
    mock_detector._whisper_detector._get_model.return_value = MagicMock()

    def init_detector(*a, **kw):
        on_score = kw.get("on_score")
        if on_score:
            on_score(MagicMock(to_dict=lambda: {"score": 0.1}))
        return mock_detector

    mock_detector_cls.side_effect = init_detector
    m_time, m_sleep = make_fast_clock(25.0)

    with patch.dict(sys.modules, {"sounddevice": mock_sd}), patch(
        "jarvis.audio.wake_word.WakeWordDetector", mock_detector_cls
    ):
        report = run_wake_word_acceptance(args, time_func=m_time, sleep_func=m_sleep)
        assert report["status"] == "ERROR"
        assert report["success"] is False
        assert report["code"] == "ZERO_DETECTIONS"
        assert report["verdict"] == "FAIL runtime (0 detections for true_wake)"


def test_true_wake_low_trigger_ratio_fails(tmp_path, mock_prod_config):
    args = parse_args([
        "--duration", "25.0",
        "--label", "true_wake",
        "--expected-wakes", "10",
        "--min-recall", "0.95",
        "--out", str(tmp_path / "report.json"),
    ])

    mock_sd = MagicMock()
    mock_sd.query_devices.return_value = [{"index": 0, "name": "Mic", "max_input_channels": 1}]
    mock_sd.default.device = [0, 0]

    def fake_input_stream(*a_inner, **kw_inner):
        callback = kw_inner.get("callback")
        stream_context = MagicMock()

        def enter_stream(*a, **kw):
            if callback:
                callback(MagicMock(), 1600, None, None)
            return stream_context

        stream_context.__enter__ = enter_stream
        stream_context.__exit__ = MagicMock(return_value=False)
        return stream_context

    mock_sd.InputStream = fake_input_stream

    mock_detector_cls = MagicMock()
    mock_detector = MagicMock()
    mock_detector.engine_type = "openwakeword"
    mock_detector._whisper_detector._get_model.return_value = MagicMock()

    def init_detector(*a, **kw):
        on_wake = kw.get("on_wake_word")
        on_score = kw.get("on_score")
        if on_score:
            on_score(MagicMock(to_dict=lambda: {"score": 0.8}))
        if on_wake:
            for _ in range(5):
                on_wake("hey_jarvis", 0.9)
        return mock_detector

    mock_detector_cls.side_effect = init_detector
    m_time, m_sleep = make_fast_clock(25.0)

    with patch.dict(sys.modules, {"sounddevice": mock_sd}), patch(
        "jarvis.audio.wake_word.WakeWordDetector", mock_detector_cls
    ):
        report = run_wake_word_acceptance(args, time_func=m_time, sleep_func=m_sleep)
        assert report["status"] == "ERROR"
        assert report["success"] is False
        assert report["code"] == "LOW_TRIGGER_RATIO"
        assert report["observed_trigger_ratio"] == 0.5
        assert report["credited_detections"] == 5


def test_true_wake_sufficient_trigger_ratio_passes(tmp_path, mock_prod_config):
    args = parse_args([
        "--duration", "25.0",
        "--label", "true_wake",
        "--expected-wakes", "10",
        "--min-recall", "0.95",
        "--out", str(tmp_path / "report.json"),
    ])

    mock_sd = MagicMock()
    mock_sd.query_devices.return_value = [{"index": 0, "name": "Mic", "max_input_channels": 1}]
    mock_sd.default.device = [0, 0]

    def fake_input_stream(*a_inner, **kw_inner):
        callback = kw_inner.get("callback")
        stream_context = MagicMock()

        def enter_stream(*a, **kw):
            if callback:
                callback(MagicMock(), 1600, None, None)
            return stream_context

        stream_context.__enter__ = enter_stream
        stream_context.__exit__ = MagicMock(return_value=False)
        return stream_context

    mock_sd.InputStream = fake_input_stream

    mock_detector_cls = MagicMock()
    mock_detector = MagicMock()
    mock_detector.engine_type = "openwakeword"
    mock_detector._whisper_detector._get_model.return_value = MagicMock()

    def init_detector(*a, **kw):
        on_wake = kw.get("on_wake_word")
        on_score = kw.get("on_score")
        if on_score:
            on_score(MagicMock(to_dict=lambda: {"score": 0.95}))
        if on_wake:
            for _ in range(10):
                on_wake("hey_jarvis", 0.95)
        return mock_detector

    mock_detector_cls.side_effect = init_detector
    m_time, m_sleep = make_fast_clock(25.0)

    with patch.dict(sys.modules, {"sounddevice": mock_sd}), patch(
        "jarvis.audio.wake_word.WakeWordDetector", mock_detector_cls
    ):
        report = run_wake_word_acceptance(args, time_func=m_time, sleep_func=m_sleep)
        assert report["status"] == "SUCCESS"
        assert report["success"] is True
        assert report["code"] == "OK"
        assert report["verdict"] == "PASS runtime"
        assert report["observed_trigger_ratio"] == 1.0


def test_ambient_zero_false_alarms_passes(tmp_path, mock_prod_config):
    args = parse_args([
        "--duration", "120.0",
        "--label", "ambient",
        "--min-ambient-seconds", "120.0",
        "--out", str(tmp_path / "report.json"),
    ])

    mock_sd = MagicMock()
    mock_sd.query_devices.return_value = [{"index": 0, "name": "Mic", "max_input_channels": 1}]
    mock_sd.default.device = [0, 0]

    def fake_input_stream(*a_inner, **kw_inner):
        callback = kw_inner.get("callback")
        stream_context = MagicMock()

        def enter_stream(*a, **kw):
            if callback:
                callback(MagicMock(), 1600, None, None)
            return stream_context

        stream_context.__enter__ = enter_stream
        stream_context.__exit__ = MagicMock(return_value=False)
        return stream_context

    mock_sd.InputStream = fake_input_stream

    mock_detector_cls = MagicMock()
    mock_detector = MagicMock()
    mock_detector.engine_type = "openwakeword"
    mock_detector._whisper_detector._get_model.return_value = MagicMock()

    def init_detector(*a, **kw):
        on_score = kw.get("on_score")
        if on_score:
            on_score(MagicMock(to_dict=lambda: {"score": 0.05}))
        return mock_detector

    mock_detector_cls.side_effect = init_detector
    m_time, m_sleep = make_fast_clock(120.0)

    with patch.dict(sys.modules, {"sounddevice": mock_sd}), patch(
        "jarvis.audio.wake_word.WakeWordDetector", mock_detector_cls
    ):
        report = run_wake_word_acceptance(args, time_func=m_time, sleep_func=m_sleep)
        assert report["status"] == "SUCCESS"
        assert report["success"] is True
        assert report["code"] == "OK"
        assert report["verdict"] == "PASS runtime (0 false alarms)"
        assert report["false_alarm_count"] == 0


def test_environment_independent_config_passed_to_detector(tmp_path, mock_prod_config):
    args = parse_args(["--duration", "25.0", "--sensitivity", "0.75", "--out", str(tmp_path / "report.json")])

    mock_sd = MagicMock()
    mock_sd.query_devices.return_value = [{"index": 0, "name": "Mic", "max_input_channels": 1}]
    mock_sd.default.device = [0, 0]

    detector_kwargs = {}

    def init_detector(*a, **kw):
        detector_kwargs.update(kw)
        mock_detector = MagicMock()
        mock_detector.engine_type = "openwakeword"
        mock_detector._whisper_detector._get_model.return_value = MagicMock()
        return mock_detector

    m_time, m_sleep = make_fast_clock(25.0)

    with patch.dict(sys.modules, {"sounddevice": mock_sd}), patch(
        "jarvis.audio.wake_word.WakeWordDetector", side_effect=init_detector
    ):
        run_wake_word_acceptance(args, time_func=m_time, sleep_func=m_sleep)

    received_config = detector_kwargs.get("config", {})
    expected_config = dict(TEST_PROD_CONFIG)
    expected_config["sensitivity"] = 0.75
    assert received_config == expected_config


def test_default_sensitivity_preserves_production_config(tmp_path, mock_prod_config):
    args = parse_args(["--duration", "25.0", "--out", str(tmp_path / "report.json")])
    mock_sd = MagicMock()
    mock_sd.query_devices.return_value = [{"index": 0, "name": "Mic", "max_input_channels": 1}]
    mock_sd.default.device = [0, 0]
    detector_kwargs = {}

    def init_detector(*a, **kw):
        detector_kwargs.update(kw)
        detector = MagicMock()
        detector.engine_type = "openwakeword"
        detector._whisper_detector._get_model.return_value = MagicMock()
        return detector

    m_time, m_sleep = make_fast_clock(25.0)
    with patch.dict(sys.modules, {"sounddevice": mock_sd}), patch(
        "jarvis.audio.wake_word.WakeWordDetector", side_effect=init_detector
    ):
        run_wake_word_acceptance(args, time_func=m_time, sleep_func=m_sleep)

    assert detector_kwargs["sensitivity"] == TEST_PROD_CONFIG["sensitivity"]
    assert detector_kwargs["config"]["sensitivity"] == TEST_PROD_CONFIG["sensitivity"]


def test_same_second_collision_safe_report_saving(tmp_path, mock_prod_config):
    out_file = tmp_path / "report.json"
    args_no_over = parse_args(["--probe-only", "--out", str(out_file)])

    mock_sd = MagicMock()
    mock_sd.query_devices.return_value = [{"index": 0, "name": "Mic", "max_input_channels": 1}]
    mock_sd.default.device = [0, 0]

    with patch.dict(sys.modules, {"sounddevice": mock_sd}):
        report1 = run_wake_word_acceptance(args_no_over)
        report2 = run_wake_word_acceptance(args_no_over)
        report3 = run_wake_word_acceptance(args_no_over)

    path1 = Path(report1["saved_report_path"])
    path2 = Path(report2["saved_report_path"])
    path3 = Path(report3["saved_report_path"])

    assert path1 != path2
    assert path2 != path3
    assert path1 != path3

    assert path1.exists()
    assert path2.exists()
    assert path3.exists()

    # Assert saved_report_path is present inside serialized JSON file content
    content1 = json.loads(path1.read_text(encoding="utf-8"))
    content2 = json.loads(path2.read_text(encoding="utf-8"))
    assert content1.get("saved_report_path") == str(path1)
    assert content2.get("saved_report_path") == str(path2)


def test_main_exit_codes_for_all_non_success_outcomes(monkeypatch, tmp_path):
    out = tmp_path / "report.json"

    # Success probe -> exit code 0
    monkeypatch.setattr(sys, "argv", ["live_wake_word_acceptance.py", "--probe-only", "--out", str(out)])
    mock_sd = MagicMock()
    mock_sd.query_devices.return_value = [{"index": 0, "name": "Mic", "max_input_channels": 1}]
    mock_sd.default.device = [0, 0]

    with patch("tools.live_wake_word_acceptance.get_production_wake_word_config", return_value=TEST_PROD_CONFIG):
        with patch.dict(sys.modules, {"sounddevice": mock_sd}):
            assert main() == 0

    # Config load failure -> exit code 1
    with patch("tools.live_wake_word_acceptance.get_production_wake_word_config", return_value=None):
        assert main() == 1

    # Insufficient ambient duration -> exit code 1
    monkeypatch.setattr(
        sys, "argv", ["live_wake_word_acceptance.py", "--label", "ambient", "--duration", "10", "--out", str(out)]
    )
    with patch("tools.live_wake_word_acceptance.get_production_wake_word_config", return_value=TEST_PROD_CONFIG):
        assert main() == 1
