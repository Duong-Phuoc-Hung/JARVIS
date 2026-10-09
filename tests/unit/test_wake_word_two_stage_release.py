"""Regression coverage for Vietnamese wake-word candidate verification."""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import yaml

from jarvis.audio.wake_word import (
    WakeWordDetector,
    WakeWordEngineType,
    WhisperSlidingWindowDetector,
)
from jarvis.gesture.detector import GestureDetector
from jarvis.gesture.models import ClapEvent


def _openwakeword_module(score: float, *, module_file: str = __file__):
    model = MagicMock()
    model.models = {"hey_jarvis_v0.1": MagicMock()}
    model.predict.return_value = {"hey_jarvis_v0.1": score}
    module = MagicMock()
    module.__file__ = module_file
    module.Model.return_value = model
    return module


def _make_openwakeword_detector(score: float, **config):
    module = _openwakeword_module(score)
    settings = {
        "openwakeword_model_paths": [__file__],
        "openwakeword_threshold": 0.5,
        "openwakeword_verification_enabled": True,
        **config,
    }
    patches = (
        patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False),
        patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", True),
        patch("jarvis.audio.wake_word.openwakeword", module),
        patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", False),
    )
    for item in patches:
        item.start()
    try:
        detector = WakeWordDetector(sensitivity=0.6, sample_rate=16000, config=settings)
    finally:
        for item in reversed(patches):
            item.stop()
    return detector


def _feed_candidate_postroll(detector, *, start: float = 100.0):
    """Feed enough 80 ms blocks to finish the configured 400 ms post-roll."""
    result = None
    for offset in range(6):
        current = detector.feed_audio_block(
            np.full(1280, 0.05, dtype=np.float32),
            timestamp=start + (offset * 0.08),
        )
        result = current or result
    return result


def test_packaged_openwakeword_model_is_discovered_without_user_configuration(tmp_path):
    package = tmp_path / "openwakeword"
    model = package / "resources" / "models" / "hey_jarvis_v0.1.onnx"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"model")
    module = _openwakeword_module(0.9, module_file=str(package / "__init__.py"))
    with patch("jarvis.audio.wake_word.VOSK_AVAILABLE", False), patch(
        "jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", True
    ), patch("jarvis.audio.wake_word.openwakeword", module), patch(
        "jarvis.audio.wake_word.PORCUPINE_AVAILABLE", False
    ):
        detector = WakeWordDetector(config={"allow_packaged_openwakeword_model": True})
    assert detector.engine_type == WakeWordEngineType.OPENWAKEWORD.value


def test_whisper_verifier_prefers_model_bundled_in_frozen_app(tmp_path, monkeypatch):
    model_dir = tmp_path / "models" / "faster-whisper-tiny"
    model_dir.mkdir(parents=True)
    (model_dir / "model.bin").write_bytes(b"model")
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert WhisperSlidingWindowDetector._resolve_model_identifier("tiny") == str(model_dir)


def test_vietnamese_candidate_requires_and_accepts_secondary_verification():
    detector = _make_openwakeword_detector(0.30)
    observations = []
    detector.on_score = observations.append
    verifier = MagicMock()
    verifier.verify_window.return_value = (True, "gia vit")
    detector._whisper_detector = verifier
    first = detector.feed_audio_block(np.full(1280, 0.05, dtype=np.float32), timestamp=100.0)
    assert first is None
    verifier.verify_window.assert_not_called()
    result = _feed_candidate_postroll(detector, start=100.08)
    assert result is not None
    assert result.engine == "openwakeword+whisper"
    assert result.confidence == 0.30
    assert observations[-1].detected is True
    assert observations[-1].verified is True
    assert observations[-1].candidate_threshold == 0.25
    assert observations[-1].verifier_transcript == "gia vit"


def test_candidate_with_affair_transcript_is_silently_rejected():
    detector = _make_openwakeword_detector(0.30)
    verifier = MagicMock()
    verifier.verify_window.return_value = (False, "affair")
    detector._whisper_detector = verifier
    assert _feed_candidate_postroll(detector) is None
    verifier.verify_window.assert_called_once()


def test_high_openwakeword_score_still_requires_transcript_verification():
    detector = _make_openwakeword_detector(0.81)
    verifier = MagicMock()
    verifier.verify_window.return_value = (False, "hey travis")
    detector._whisper_detector = verifier
    assert _feed_candidate_postroll(detector) is None
    verifier.verify_window.assert_called_once()


def test_high_openwakeword_score_is_accepted_after_verified_postroll():
    detector = _make_openwakeword_detector(0.91)
    verifier = MagicMock()
    verifier.verify_window.return_value = (True, "hey jarvis")
    detector._whisper_detector = verifier
    result = _feed_candidate_postroll(detector)
    assert result is not None
    assert result.engine == "openwakeword+whisper"
    assert result.confidence == 0.91


def test_rejected_candidate_does_not_loop_verifier_until_score_rearms():
    detector = _make_openwakeword_detector(0.30)
    verifier = MagicMock()
    verifier.verify_window.return_value = (False, "affair")
    detector._whisper_detector = verifier
    assert _feed_candidate_postroll(detector) is None
    for offset in range(20):
        detector.feed_audio_block(
            np.full(1280, 0.05, dtype=np.float32), timestamp=101.0 + offset * 0.08
        )
    verifier.verify_window.assert_called_once()


def test_score_below_candidate_gate_never_runs_verifier():
    detector = _make_openwakeword_detector(0.10)
    verifier = MagicMock()
    detector._whisper_detector = verifier
    assert detector.feed_audio_block(np.full(1280, 0.05, dtype=np.float32), timestamp=100.0) is None
    verifier.verify_window.assert_not_called()


def test_whisper_verifier_uses_keyword_biased_english_and_safe_aliases():
    model = MagicMock()
    model.transcribe.return_value = ([SimpleNamespace(text="  Gia vít  ")], MagicMock())
    verifier = WhisperSlidingWindowDetector(model=model, min_rms=0.001)
    accepted, transcript = verifier.verify_window(np.full(16000, 0.05, dtype=np.float32))
    assert accepted is True
    assert transcript == "gia vit"
    assert model.transcribe.call_args.kwargs["language"] == "en"
    assert model.transcribe.call_args.kwargs["vad_filter"] is True
    assert "initial_prompt" not in model.transcribe.call_args.kwargs
    assert "Jarvis" in model.transcribe.call_args.kwargs["hotwords"]


def test_whisper_verifier_rejects_hallucinated_keyword_on_no_speech():
    model = MagicMock()
    model.transcribe.return_value = ([SimpleNamespace(
        text="JARVIS", no_speech_prob=0.98, avg_logprob=-0.1
    )], MagicMock())
    verifier = WhisperSlidingWindowDetector(model=model, min_rms=0.001)
    assert verifier.verify_window(np.full(16000, 0.05, dtype=np.float32)) == (False, "jarvis")


def test_whisper_verifier_accepts_accented_boundary_but_rejects_very_low_logprob():
    model = MagicMock()
    model.transcribe.return_value = ([SimpleNamespace(
        text="and JARVIS", no_speech_prob=0.33, avg_logprob=-1.20
    )], MagicMock())
    verifier = WhisperSlidingWindowDetector(model=model, min_rms=0.001)
    assert verifier.verify_window(np.full(16000, 0.05, dtype=np.float32))[0] is True

    model.transcribe.return_value = ([SimpleNamespace(
        text="JARVIS", no_speech_prob=0.20, avg_logprob=-1.50
    )], MagicMock())
    assert verifier.verify_window(np.full(16000, 0.05, dtype=np.float32))[0] is False


def test_sensitivity_controls_candidate_gate_without_lowering_direct_acceptance():
    strict = _make_openwakeword_detector(0.30, openwakeword_candidate_threshold=None)
    strict.sensitivity = 0.0
    strict._openwakeword_candidate_threshold = 0.40
    strict_verifier = MagicMock()
    strict_verifier.verify_window.return_value = (True, "jarvis")
    strict._whisper_detector = strict_verifier
    assert strict.feed_audio_block(np.full(1280, 0.05, dtype=np.float32), timestamp=100.0) is None

    sensitive = _make_openwakeword_detector(0.30, openwakeword_candidate_threshold=None)
    sensitive_verifier = MagicMock()
    sensitive_verifier.verify_window.return_value = (True, "jarvis")
    sensitive._whisper_detector = sensitive_verifier
    assert _feed_candidate_postroll(sensitive) is not None


def test_default_config_does_not_turn_room_transients_into_voice_activation():
    config = yaml.safe_load(open("config/default_config.yaml", encoding="utf-8"))
    assert config["wake_word"]["openwakeword_candidate_threshold"] == 0.02
    assert config["wake_word"]["openwakeword_verification_enabled"] is True
    assert config["wake_word"]["openwakeword_verification_postroll_s"] == 0.40
    detector = GestureDetector(config=config["gesture"])
    assert detector.feed_clap(ClapEvent(timestamp=1.0, amplitude=0.8)) is None
    detector.feed_clap(ClapEvent(timestamp=1.2, amplitude=0.8))
    assert detector.tick(2.0) is None


def test_openwakeword_continuous_streaming_across_cooldown_and_frame_buffering():
    """Verify OpenWakeWord continues feeding predict() during cooldown and chunks frames."""
    detector = _make_openwakeword_detector(0.95, openwakeword_verification_enabled=False)
    detector.cooldown_s = 2.0
    mock_model = detector._tier1_engine

    # 1. Trigger detection at t=100.0
    result1 = detector.feed_audio_block(np.full(1280, 0.05, dtype=np.float32), timestamp=100.0)
    assert result1 is not None
    assert result1.keyword == "hey_jarvis_v0.1"
    initial_predict_calls = mock_model.predict.call_count
    assert initial_predict_calls >= 1

    # 2. Feed audio during cooldown (t=100.5, within 2.0s cooldown)
    cooldown_result = detector.feed_audio_block(
        np.full(1280, 0.05, dtype=np.float32), timestamp=100.5
    )
    assert cooldown_result is None  # Blocked by cooldown
    # But predict() WAS called so rolling spectrogram buffer does not freeze
    assert mock_model.predict.call_count == initial_predict_calls + 1

    # 3. Test frame buffering with non-1280 chunk size (e.g. 640 samples)
    detector._openwakeword_frame_buffer.reset()
    mock_model.predict.reset_mock()

    # Feed 640 samples: half frame -> predict() should not be called yet
    detector.feed_audio_block(np.full(640, 0.05, dtype=np.float32), timestamp=105.0)
    assert mock_model.predict.call_count == 0

    # Feed another 640 samples: completes 1280 frame -> predict() called with 1280 frame
    res = detector.feed_audio_block(np.full(640, 0.05, dtype=np.float32), timestamp=105.08)
    assert mock_model.predict.call_count == 1
    assert len(mock_model.predict.call_args[0][0]) == 1280
