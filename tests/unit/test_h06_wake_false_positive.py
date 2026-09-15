"""
tests/unit/test_h06_wake_false_positive.py
============================================
H-06 contract tests: wake-word / acoustic-fallback false-positive reduction.

Covers, per the H-06 audit:
  1. Idle-soak runner sample-rate truthfulness (detector sample_rate must
     equal the real InputStream rate -- the confirmed defect that silently
     mislabeled/resampled 16kHz audio as 44.1kHz).
  2. sensitivity / vad_threshold are distinct, correctly-wired parameters
     (the confirmed defect where --threshold was logged as a sensitivity
     value but actually landed in vad_threshold).
  3. Explicit engine-selection policy: Tier-2 acoustic fallback no longer
     runs unconditionally alongside a reliable, actively-processing Tier-1
     engine unless explicitly configured ("always").
  4. Background negative classes: the deterministic synthetic benchmark
     (tests/eval/wake_word_fp_benchmark.py) produces zero false positives
     across all 10 negative classes at the default sensitivity.
  5. True wake-word positives: recall does not regress below the measured
     floor across the amplitude/noise/sample-rate sweep.
  6. Fallback policy is respected for both "auto" and "always".
  7. No regression to Vosk/Porcupine/OpenWakeWord selection or detection
     pathways.
  8. Circuit-breaker (PassiveTriggerGuard) compatibility: still bounds
     repeated ambient triggers; explicit PTT still bypasses it entirely;
     H-04 single-flight semantics are untouched.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.audio.wake_word import (
    AcousticSpectralDetector,
    WakeWordDetector,
    WakeWordEngineType,
    WakeWordResult,
    generate_wake_word_signal,
)
from jarvis.core.runaway_guard import PassiveTriggerGuard

ROOT = Path(__file__).resolve().parent.parent.parent


# ============================================================================
# 1. Idle-soak runner sample-rate truthfulness
# ============================================================================

class _FakeInputStream:
    def __init__(self, *a, **kw):
        self.kwargs = kw
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def read(self, n):
        return (np.zeros((n, 1), dtype=np.int16), False)


def test_runner_constructs_detector_with_the_real_stream_sample_rate():
    """
    The confirmed H-06 measurement-harness defect: the runner opened a
    16kHz InputStream but let WakeWordDetector default to 44100. This test
    fails if that regresses -- the detector's sample_rate must always equal
    the value the runner used to open the real stream, for every rate the
    runner is asked to use, not just the default.
    """
    from tests.eval.wake_word_idle_runner import run_idle_evaluation

    for requested_rate in (16000, 44100, 48000):
        captured_kwargs = {}
        real_init = WakeWordDetector.__init__

        def _spy_init(self, *a, **kw):
            captured_kwargs.clear()
            captured_kwargs.update(kw)
            return real_init(self, *a, **kw)

        with patch("sounddevice.InputStream", _FakeInputStream), \
             patch("jarvis.audio.engine.AudioEngine.get_active_device", return_value=None), \
             patch.object(WakeWordDetector, "__init__", _spy_init):
            run_idle_evaluation(
                duration_seconds=0.05,
                sample_rate=requested_rate,
                engine_override="mock",
                out_path=None,
            )

        assert captured_kwargs.get("sample_rate") == requested_rate, (
            f"Detector was constructed with sample_rate={captured_kwargs.get('sample_rate')} "
            f"but the runner opened the stream at {requested_rate} Hz"
        )


def test_runner_report_records_actual_configured_sample_rate():
    from tests.eval.wake_word_idle_runner import run_idle_evaluation

    with patch("sounddevice.InputStream", _FakeInputStream), \
         patch("jarvis.audio.engine.AudioEngine.get_active_device", return_value=None):
        report = run_idle_evaluation(
            duration_seconds=0.05, sample_rate=16000, engine_override="mock", out_path=None,
        )
    assert report["sample_rate"] == 16000
    assert report["status"] == "COMPLETED"


# ============================================================================
# 2. sensitivity / vad_threshold config separation
# ============================================================================

def test_runner_sensitivity_and_vad_threshold_are_independently_wired():
    """
    The confirmed defect: --threshold (described as sensitivity) was
    actually passed as vad_threshold. Assert the two CLI-level values land
    on their own, correct, distinct WakeWordDetector constructor parameters.
    """
    from tests.eval.wake_word_idle_runner import run_idle_evaluation

    captured_kwargs = {}
    real_init = WakeWordDetector.__init__

    def _spy_init(self, *a, **kw):
        captured_kwargs.clear()
        captured_kwargs.update(kw)
        return real_init(self, *a, **kw)

    with patch("sounddevice.InputStream", _FakeInputStream), \
         patch("jarvis.audio.engine.AudioEngine.get_active_device", return_value=None), \
         patch.object(WakeWordDetector, "__init__", _spy_init):
        run_idle_evaluation(
            duration_seconds=0.05,
            sensitivity=0.77,
            vad_threshold=0.0123,
            sample_rate=16000,
            engine_override="mock",
            out_path=None,
        )

    assert captured_kwargs.get("sensitivity") == 0.77
    assert captured_kwargs.get("vad_threshold") == 0.0123
    assert captured_kwargs.get("sensitivity") != captured_kwargs.get("vad_threshold")


def test_runner_report_exposes_sensitivity_and_vad_threshold_separately():
    from tests.eval.wake_word_idle_runner import run_idle_evaluation

    with patch("sounddevice.InputStream", _FakeInputStream), \
         patch("jarvis.audio.engine.AudioEngine.get_active_device", return_value=None):
        report = run_idle_evaluation(
            duration_seconds=0.05, sensitivity=0.6, vad_threshold=0.007,
            sample_rate=16000, engine_override="mock", out_path=None,
        )
    assert report["sensitivity"] == 0.6
    assert report["vad_threshold"] == 0.007


def test_runner_trigger_events_use_real_detector_result_not_fabricated_confidence():
    """
    The confirmed defect: getattr(detector, "last_confidence", 1.0) always
    fell back to a fabricated 1.0 (the attribute never existed). Force a
    real trigger via the "mock" engine forced-detection test hook and
    verify the recorded confidence/engine/keyword come from the genuine
    WakeWordResult, not a hardcoded default.
    """
    from tests.eval.wake_word_idle_runner import run_idle_evaluation

    fake_result = WakeWordResult(keyword="hey_jarvis", confidence=0.42, engine="vosk")

    with patch("sounddevice.InputStream", _FakeInputStream), \
         patch("jarvis.audio.engine.AudioEngine.get_active_device", return_value=None), \
         patch.object(WakeWordDetector, "feed_audio_block", return_value=fake_result):
        report = run_idle_evaluation(
            duration_seconds=0.05, sample_rate=16000, engine_override="mock", out_path=None,
        )

    assert report["total_false_triggers"] >= 1
    event = report["events"][0]
    assert event["confidence"] == pytest.approx(0.42)
    assert event["engine"] == "vosk"
    assert event["keyword"] == "hey_jarvis"
    assert event["confidence"] != 1.0  # would be the old fabricated default


def test_runner_report_includes_reproducibility_metadata():
    from tests.eval.wake_word_idle_runner import run_idle_evaluation

    with patch("sounddevice.InputStream", _FakeInputStream), \
         patch("jarvis.audio.engine.AudioEngine.get_active_device", return_value=None):
        report = run_idle_evaluation(
            duration_seconds=0.05, sample_rate=16000, condition="fan",
            engine_override="mock", out_path=None,
        )

    for key in (
        "sample_rate", "sensitivity", "vad_threshold", "acoustic_fallback_policy",
        "engine_selected", "condition", "device_index", "chunk_size", "cooldown_s",
    ):
        assert key in report, f"Missing reproducibility metadata field: {key}"
    assert report["condition"] == "fan"
    assert report["engine_selected"] == "mock"


def test_runner_supports_all_named_conditions():
    from tests.eval.wake_word_idle_runner import VALID_CONDITIONS, run_idle_evaluation

    assert set(VALID_CONDITIONS) == {"quiet", "fan", "music", "youtube", "conversation", "custom"}

    with patch("sounddevice.InputStream", _FakeInputStream), \
         patch("jarvis.audio.engine.AudioEngine.get_active_device", return_value=None):
        for condition in VALID_CONDITIONS:
            report = run_idle_evaluation(
                duration_seconds=0.02, condition=condition, engine_override="mock", out_path=None,
            )
            assert report["condition"] == condition

        bad = run_idle_evaluation(duration_seconds=0.02, condition="not_a_real_condition", out_path=None)
        assert bad.get("error") == "INVALID_CONDITION"


# ============================================================================
# 3 & 6. Explicit engine-selection / fallback policy
# ============================================================================

def _mock_vosk_engine(matches: bool) -> MagicMock:
    rec = MagicMock()
    rec.AcceptWaveform.return_value = True
    rec.Result.return_value = json.dumps({"text": "hey jarvis"} if matches else {"text": "the weather is nice"})
    return rec


def test_auto_policy_does_not_run_tier2_when_tier1_cleanly_finds_nothing():
    detector = WakeWordDetector(config={"acoustic_fallback_policy": "auto"})
    detector._engine_type = WakeWordEngineType.VOSK
    detector._tier1_engine = _mock_vosk_engine(matches=False)

    with patch.object(
        detector._spectral_detector, "analyze_window", wraps=detector._spectral_detector.analyze_window
    ) as spy:
        result = detector.feed_audio_block(np.random.normal(0, 0.05, 16000).astype(np.float32))
        spy.assert_not_called()
    assert result is None


def test_always_policy_still_runs_tier2_supplementary_check():
    detector = WakeWordDetector(config={"acoustic_fallback_policy": "always"})
    detector._engine_type = WakeWordEngineType.VOSK
    detector._tier1_engine = _mock_vosk_engine(matches=False)

    with patch.object(
        detector._spectral_detector, "analyze_window", wraps=detector._spectral_detector.analyze_window
    ) as spy:
        detector.feed_audio_block(np.random.normal(0, 0.05, 16000).astype(np.float32))
        spy.assert_called()


def test_auto_is_the_default_policy_without_explicit_config():
    detector = WakeWordDetector()
    assert detector.config.get("acoustic_fallback_policy", "auto") == "auto"


def test_tier1_genuine_exception_still_gets_tier2_fallback_this_block():
    """Robustness, not a false-positive-rate concern: a real Tier-1
    processing failure (not a confident no-match) must still let Tier 2
    have a chance at that specific block -- preserves the pre-existing
    test_wake_word_tier1_failure_smooth_fallback_to_tier2 contract."""
    detector = WakeWordDetector()
    detector._engine_type = WakeWordEngineType.VOSK
    faulty_rec = MagicMock()
    faulty_rec.AcceptWaveform.side_effect = RuntimeError("Vosk corrupted model buffer")
    detector._tier1_engine = faulty_rec

    keyword_audio = generate_wake_word_signal(sample_rate=44100)
    res = detector.feed_audio_block(keyword_audio)
    assert res is not None
    assert res.engine == WakeWordEngineType.ACOUSTIC_FALLBACK.value


def test_unrecognized_policy_value_fails_closed_to_auto():
    detector = WakeWordDetector(config={"acoustic_fallback_policy": "some_typo"})
    detector._engine_type = WakeWordEngineType.VOSK
    detector._tier1_engine = _mock_vosk_engine(matches=False)

    with patch.object(
        detector._spectral_detector, "analyze_window", wraps=detector._spectral_detector.analyze_window
    ) as spy:
        detector.feed_audio_block(np.random.normal(0, 0.05, 16000).astype(np.float32))
        spy.assert_not_called()  # unrecognized value must NOT behave like "always"


def test_headless_ci_with_no_tier1_engine_still_uses_tier2_under_auto_policy():
    """CI/headless operation (no Vosk/Porcupine/OpenWakeWord installed) must
    keep working: with no primary engine at all, "auto" policy must still
    allow Tier 2 to run -- this is the ONLY reliable detector present."""
    detector = WakeWordDetector(config={"acoustic_fallback_policy": "auto"})
    assert detector.engine_type == WakeWordEngineType.ACOUSTIC_FALLBACK.value

    keyword_audio = generate_wake_word_signal(sample_rate=44100)
    res = detector.feed_audio_block(keyword_audio)
    assert res is not None
    assert res.engine == WakeWordEngineType.ACOUSTIC_FALLBACK.value


# ============================================================================
# 4 & 5. Deterministic benchmark: background negatives + true positives
# ============================================================================

def test_acoustic_detector_zero_false_positives_on_synthetic_negative_benchmark():
    from tests.eval.wake_word_fp_benchmark import run_benchmark

    result = run_benchmark(sensitivity=0.5)
    neg = result["negative"]
    assert neg["fp"] == 0, f"False positives found: {neg['fp_by_class']}"
    for class_name, count in neg["fp_by_class"].items():
        assert count == 0, f"Negative class '{class_name}' produced {count} false positive(s)"


def test_acoustic_detector_recall_does_not_regress_below_measured_floor():
    from tests.eval.wake_word_fp_benchmark import run_benchmark

    result = run_benchmark(sensitivity=0.5)
    pos = result["positive"]
    # Measured floor at the time of this fix: 7/9 (77.8%). Set the assertion
    # floor a bit below that to avoid brittleness on minor future tuning,
    # while still catching a real recall regression.
    assert pos["recall"] >= 0.6, f"Recall dropped to {pos['recall']:.1%} (measured floor was 77.8%)"


def test_benchmark_is_deterministic_across_repeated_runs():
    from tests.eval.wake_word_fp_benchmark import run_benchmark

    r1 = run_benchmark(sensitivity=0.5)
    r2 = run_benchmark(sensitivity=0.5)
    assert r1["positive"]["tp"] == r2["positive"]["tp"]
    assert r1["negative"]["fp"] == r2["negative"]["fp"]
    assert r1["negative"]["fp_by_class"] == r2["negative"]["fp_by_class"]


def test_music_harmonic_negative_class_specifically_rejected():
    """Regression-locks the exact structural fix: a harmonic-tone-plus-
    percussive-transient signal (the class that measured 0.89+ confidence
    -- above even the strictest threshold -- before the minimum-sustained-
    duration fix) must now be rejected."""
    from tests.eval.wake_word_fp_benchmark import gen_music_harmonic
    import zlib

    detector = AcousticSpectralDetector(sample_rate=16000)
    for variant in range(8):
        seed = zlib.crc32(f"music_harmonic:{variant}".encode("utf-8"))
        buf = gen_music_harmonic(seed, 16000)
        detected, _, confidence = detector.analyze_window(buf, sensitivity=0.5)
        assert not detected, f"music_harmonic variant {variant} still triggers (confidence={confidence:.3f})"


# ============================================================================
# 7. No regression to Vosk / Porcupine / OpenWakeWord pathways
# ============================================================================

def test_vosk_still_detects_a_genuine_keyword_match():
    detector = WakeWordDetector()
    detector._engine_type = WakeWordEngineType.VOSK
    detector._tier1_engine = _mock_vosk_engine(matches=True)

    res = detector.feed_audio_block(np.zeros(16000, dtype=np.float32))
    assert res is not None
    assert res.engine == WakeWordEngineType.VOSK.value


def test_porcupine_selection_and_hit_path_unaffected():
    mock_engine = MagicMock()
    mock_engine.frame_length = 512
    mock_engine.sample_rate = 16000
    mock_engine.process.return_value = 0  # immediate hit

    fake_pvporcupine = MagicMock()
    fake_pvporcupine.create.return_value = mock_engine

    with patch("jarvis.audio.wake_word.PORCUPINE_AVAILABLE", True), \
         patch("jarvis.audio.wake_word.pvporcupine", fake_pvporcupine):
        detector = WakeWordDetector(config={"porcupine_access_key": "fake-key"})
        assert detector.engine_type == WakeWordEngineType.PORCUPINE.value

        res = detector.feed_audio_block(np.random.normal(0, 0.05, 16000).astype(np.float32))
        assert res is not None
        assert res.engine == WakeWordEngineType.PORCUPINE.value
        detector.shutdown()


def _mock_openwakeword_module(model_key: str = "hey_jarvis", predict_return: dict | None = None):
    """
    Build a fake `openwakeword` module whose Model() returns a mock shaped
    like the real dscripka/openWakeWord API: a `.models` dict keyed by
    loaded-model label (used by JARVIS's init-time label-matching check),
    and a `.predict(frame)` returning a dict of label -> score (0-1).
    """
    fake_model_instance = MagicMock()
    fake_model_instance.models = {model_key: MagicMock()}
    if predict_return is not None:
        fake_model_instance.predict.return_value = predict_return
    fake_module = MagicMock()
    fake_module.Model.return_value = fake_model_instance
    return fake_module, fake_model_instance


def test_openwakeword_positive_uses_real_mocked_model_score():
    """(A) A usable, JARVIS-compatible OpenWakeWord model whose real
    predict() score for the configured wake label is above threshold must
    produce a genuine WakeWordResult with engine="openwakeword" and the
    EXACT mocked score as confidence -- never a fabricated value."""
    fake_module, fake_model = _mock_openwakeword_module(
        model_key="hey_jarvis", predict_return={"hey_jarvis": 0.87},
    )
    with patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", True), \
         patch("jarvis.audio.wake_word.openwakeword", fake_module):
        detector = WakeWordDetector(config={
            "acoustic_fallback_policy": "auto",
            "openwakeword_model_paths": [__file__],
            "openwakeword_threshold": 0.5,
        })
        assert detector.engine_type == WakeWordEngineType.OPENWAKEWORD.value

        res = detector.feed_audio_block(np.random.normal(0, 0.05, 16000).astype(np.float32))
        assert res is not None
        assert res.engine == WakeWordEngineType.OPENWAKEWORD.value
        assert res.confidence == pytest.approx(0.87)
        fake_model.predict.assert_called()


def test_openwakeword_negative_does_not_trigger_tier2_under_auto():
    """(B) A model that successfully processes the block but scores below
    threshold is "processed, no match" -- Tier 2 must NOT also run under
    the "auto" policy (this is the exact bug this pass fixes: a selected-
    but-dead OpenWakeWord previously made Tier 2 its silent de facto
    processor even on a clean non-match)."""
    fake_module, fake_model = _mock_openwakeword_module(
        model_key="hey_jarvis", predict_return={"hey_jarvis": 0.1},
    )
    with patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", True), \
         patch("jarvis.audio.wake_word.openwakeword", fake_module):
        detector = WakeWordDetector(config={
            "acoustic_fallback_policy": "auto",
            "openwakeword_model_paths": [__file__],
            "openwakeword_threshold": 0.5,
        })
        assert detector.engine_type == WakeWordEngineType.OPENWAKEWORD.value

        with patch.object(
            detector._spectral_detector, "analyze_window", wraps=detector._spectral_detector.analyze_window
        ) as spy:
            res = detector.feed_audio_block(np.random.normal(0, 0.05, 16000).astype(np.float32))
            spy.assert_not_called()
        assert res is None
        fake_model.predict.assert_called()


def test_openwakeword_runtime_failure_allows_tier2_fallback():
    """(C) A genuine predict() exception is a real engine failure, not a
    confident no-match -- Tier 2 fallback IS allowed for that block under
    "auto", same robustness contract as the pre-existing Vosk-exception
    test."""
    fake_model = MagicMock()
    fake_model.models = {"hey_jarvis": MagicMock()}
    fake_model.predict.side_effect = RuntimeError("native predict crashed")
    fake_module = MagicMock()
    fake_module.Model.return_value = fake_model

    with patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", True), \
         patch("jarvis.audio.wake_word.openwakeword", fake_module):
        detector = WakeWordDetector(config={
            "acoustic_fallback_policy": "auto",
            "openwakeword_model_paths": [__file__],
        })
        assert detector.engine_type == WakeWordEngineType.OPENWAKEWORD.value

        keyword_audio = generate_wake_word_signal(sample_rate=44100)
        res = detector.feed_audio_block(keyword_audio)
        assert res is not None
        assert res.engine == WakeWordEngineType.ACOUSTIC_FALLBACK.value


def test_openwakeword_unusable_model_does_not_claim_engine_type():
    """(D) Package available and a model path is configured, but the loaded
    model has no label matching any configured JARVIS wake label --
    OpenWakeWord must NOT be claimed as the selected engine; backend
    selection continues truthfully (falls through to acoustic fallback
    here, since no other Tier-1 backend is configured in this test)."""
    fake_model = MagicMock()
    fake_model.models = {"some_other_wakeword": MagicMock()}
    fake_module = MagicMock()
    fake_module.Model.return_value = fake_model

    with patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", True), \
         patch("jarvis.audio.wake_word.openwakeword", fake_module):
        detector = WakeWordDetector(config={
            "acoustic_fallback_policy": "auto",
            "openwakeword_model_paths": [__file__],
        })
        assert detector.engine_type != WakeWordEngineType.OPENWAKEWORD.value
        assert detector.engine_type == WakeWordEngineType.ACOUSTIC_FALLBACK.value


def test_openwakeword_no_configured_model_path_does_not_select_it():
    """(D, cont.) No model path configured at all -- must never call
    Model() with no arguments (the real upstream API treats that as
    "auto-load every pretrained model from a default location", a form of
    implicit provisioning this repository does not explicitly support);
    backend selection continues without ever touching openwakeword.Model()."""
    fake_module = MagicMock()
    with patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", True), \
         patch("jarvis.audio.wake_word.openwakeword", fake_module):
        detector = WakeWordDetector(config={"acoustic_fallback_policy": "auto"})
        assert detector.engine_type != WakeWordEngineType.OPENWAKEWORD.value
        fake_module.Model.assert_not_called()


def test_openwakeword_always_policy_still_runs_tier2_after_clean_non_match():
    """(E) A successful OpenWakeWord non-match can still be followed by
    Tier 2 acoustic fallback ONLY because "always" was explicitly selected
    -- distinct from the "auto" behavior in test B above."""
    fake_module, fake_model = _mock_openwakeword_module(
        model_key="hey_jarvis", predict_return={"hey_jarvis": 0.1},
    )
    with patch("jarvis.audio.wake_word.OPENWAKEWORD_AVAILABLE", True), \
         patch("jarvis.audio.wake_word.openwakeword", fake_module):
        detector = WakeWordDetector(config={
            "acoustic_fallback_policy": "always",
            "openwakeword_model_paths": [__file__],
        })
        assert detector.engine_type == WakeWordEngineType.OPENWAKEWORD.value

        with patch.object(
            detector._spectral_detector, "analyze_window", wraps=detector._spectral_detector.analyze_window
        ) as spy:
            detector.feed_audio_block(np.random.normal(0, 0.05, 16000).astype(np.float32))
            spy.assert_called()


def test_whisper_primary_engine_gates_tier2_under_auto_policy():
    # faster_whisper is an optional dependency, not installed in this test
    # environment -- mock its availability flag so the "engine": "whisper"
    # config override actually selects WHISPER (matching what a real
    # environment with faster_whisper installed would do), rather than
    # silently falling through to ACOUSTIC_FALLBACK and testing nothing.
    with patch("jarvis.audio.wake_word.FASTER_WHISPER_AVAILABLE", True):
        detector = WakeWordDetector(config={"engine": "whisper", "acoustic_fallback_policy": "auto"})
    assert detector.engine_type == WakeWordEngineType.WHISPER.value

    fake_whisper_detector = MagicMock()
    fake_whisper_detector.analyze_window.return_value = (False, "", 0.0)
    detector._whisper_detector = fake_whisper_detector

    with patch.object(
        detector._spectral_detector, "analyze_window", wraps=detector._spectral_detector.analyze_window
    ) as spy:
        detector.feed_audio_block(np.random.normal(0, 0.05, 16000).astype(np.float32))
        spy.assert_not_called()


# ============================================================================
# 8. Circuit-breaker (PassiveTriggerGuard) compatibility
# ============================================================================

def test_passive_trigger_guard_still_bounds_repeated_ambient_wake_triggers():
    """Unmodified by this H-06 pass -- verifies the real, shared
    PassiveTriggerGuard class still trips its lockout after max_triggers
    within window_s, exactly as before."""
    guard = PassiveTriggerGuard(min_rearm_interval_s=0.0, max_triggers=5, window_s=60.0, lockout_s=120.0)
    key = "WAKE_WORD:hey_jarvis"

    allowed_count = 0
    t = 1000.0
    decisions = []
    for i in range(8):
        d = guard.try_acquire(key, now=t)
        decisions.append(d)
        if d.allowed:
            allowed_count += 1
        t += 0.01  # rapid repeated triggers

    assert allowed_count == 5, f"Expected exactly 5 allowed triggers before lockout, got {allowed_count}"
    assert decisions[5].reason == "LOCKOUT_TRIPPED"
    assert decisions[6].reason == "LOCKOUT_ACTIVE"
    assert decisions[7].reason == "LOCKOUT_ACTIVE"


def test_explicit_ptt_path_never_touches_passive_trigger_guard():
    """Sanity re-check specific to H-06: this pass did not introduce any
    new call from the PTT path into the passive-trigger guard."""
    from jarvis.core.app import JarvisApp

    app = JarvisApp.__new__(JarvisApp)
    app.hotkey_manager = MagicMock()
    app.overlay = MagicMock()
    app.wake_word_detector = MagicMock()
    app.tts_manager = MagicMock()
    app._voice_lock = threading.Lock()
    app._is_voice_interacting = False
    app._passive_trigger_guard = MagicMock()
    app._start_voice_interaction = MagicMock()

    app._register_default_hotkeys()
    registered = {c.args[0]: c.args[1] for c in app.hotkey_manager.register.call_args_list}
    registered["Ctrl+Shift+L"]()

    app._passive_trigger_guard.try_acquire.assert_not_called()
    app._start_voice_interaction.assert_called_once_with(
        trigger_name="HOTKEY_PTT", greeting_phrase="Vâng, tôi nghe.",
    )


def test_wake_word_trigger_path_does_go_through_passive_trigger_guard():
    """Complementary to the PTT check above: the AMBIENT wake-word path
    (_on_wake_word_triggered) must still route through the guard -- proving
    H-06's detector-level fix and the circuit breaker are two independent,
    still-cooperating layers (fix reduces false triggers BEFORE the guard;
    the guard still bounds whatever gets through)."""
    from jarvis.core.app import JarvisApp

    app = JarvisApp.__new__(JarvisApp)
    app._passive_trigger_guard = PassiveTriggerGuard(min_rearm_interval_s=2.5)
    app._start_voice_interaction = MagicMock()

    app._on_wake_word_triggered()
    app._start_voice_interaction.assert_called_once()

    # A second immediate trigger within the 2.5s rearm interval must be suppressed.
    app._start_voice_interaction.reset_mock()
    app._on_wake_word_triggered()
    app._start_voice_interaction.assert_not_called()
