"""H-01: source-rate audio must reach every STT consumer at 16 kHz."""
import io
import threading
import wave
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.stt.engine import (
    FasterWhisperSTT, MockSTTEngine, STTEngine, TieredSTTEngine,
    prepare_stt_audio, resample_audio,
    STTStreamNormalizer, OpenAIWhisperSTT,
)
from jarvis.core.app import JarvisApp
from jarvis.core.config import ConfigManager


@pytest.fixture
def capture_app():
    app = JarvisApp.__new__(JarvisApp)
    app.config = ConfigManager()
    app.config.set("stt.timeout_s", 3.0)
    app.config.set("audio.sample_rate", 44100)
    app.headless = False
    app.audio_engine = SimpleNamespace(_active_device_index=3)
    app.tts_manager = None
    app.proactive_engine = app.overlay = app.tray_controller = None
    app._voice_lock = threading.Lock()
    app._is_voice_interacting = False
    app.process_text_command = MagicMock(return_value={})
    app.log_interaction = MagicMock()
    return app


@pytest.mark.parametrize("rate", [8000, 16000, 22050, 24000, 44100, 48000])
def test_production_capture_keeps_rate_across_config_reload(rate, capture_app, whisper_model):
    app = capture_app
    app.config.set("stt.sample_rate", rate)
    app.stt_engine = STTEngine(primary_engine=FasterWhisperSTT({"device": "cpu"}),
                              fallback_engine=MockSTTEngine())
    with patch("sounddevice.InputStream") as stream, patch("jarvis.core.app.time.sleep"), patch(
        "jarvis.stt.engine.resample_audio", wraps=resample_audio
    ) as convert:
        stream.return_value.__enter__.return_value.read.side_effect = lambda n: (
            np.full((n, 1), .25, dtype=np.float32), False
        )
        # Simulate config reload after recording ends, before transcription begins.
        stream.return_value.__exit__.side_effect = lambda *args: app.config.set("stt.sample_rate", 8000)
        app._start_voice_interaction(greeting_phrase="", sync=True)
    assert stream.call_args.kwargs["samplerate"] == rate
    assert stream.call_args.kwargs["device"] == 3
    # Existing capture uses 20 integer-sized 150ms blocks: at 22050 Hz,
    # 20 * 3307 = 66140 source samples, i.e. 47992 complete 16-kHz samples.
    expected = 47992 if rate == 22050 else 48000
    assert whisper_model.transcribe.call_args.args[0].shape == (expected,)
    assert convert.call_count == (0 if rate == 16000 else 1)


def test_capture_explicit_override_and_none_config(capture_app):
    capture_app.headless = True
    capture_app.config.set("stt.sample_rate", None)
    assert capture_app.record_audio().shape == (1600,)
    capture = capture_app.record_audio(sample_rate=48000, return_capture=True)
    assert capture.source_sample_rate == 48000
    assert capture.samples.shape == (4800,)
    assert prepare_stt_audio(capture).shape == (1600,)


@pytest.fixture
def whisper_model():
    model = MagicMock()
    model.transcribe.return_value = ([SimpleNamespace(text="test")], SimpleNamespace())
    with patch("jarvis.stt.engine.FASTER_WHISPER_AVAILABLE", True), patch(
        "jarvis.stt.engine.WhisperModel", return_value=model
    ):
        yield model


@pytest.mark.parametrize("rate", [8000, 16000, 22050, 24000, 44100, 48000])
def test_coordinator_preserves_one_second_at_provider_boundary(rate):
    provider = MagicMock()
    provider.is_available.return_value = True
    provider.transcribe.return_value = "test"
    engine = STTEngine(primary_engine=provider, fallback_engine=MockSTTEngine())
    audio = np.full(rate, 0.25, dtype=np.float32)

    assert engine.transcribe(audio, source_sample_rate=rate) == "test"

    received = provider.transcribe.call_args.args[0]
    assert received.shape == (16000,)
    assert "source_sample_rate" not in provider.transcribe.call_args.kwargs


@pytest.mark.parametrize("route", ["direct", "tiered", "coordinator_tiered"])
@pytest.mark.parametrize("rate", [16000, 44100, 48000])
def test_model_gets_one_second_without_metadata_or_double_resample(route, rate, whisper_model):
    engine = FasterWhisperSTT({"device": "cpu"})
    if route != "direct":
        engine = TieredSTTEngine(local_engine=engine)
    if route == "coordinator_tiered":
        engine = STTEngine(primary_engine=engine, fallback_engine=MockSTTEngine())
    with patch("jarvis.stt.engine.resample_audio", wraps=resample_audio) as convert:
        engine.transcribe(np.full(rate, .25, dtype=np.float32), source_sample_rate=rate)
    assert whisper_model.transcribe.call_args.args[0].shape == (16000,)
    assert "source_sample_rate" not in whisper_model.transcribe.call_args.kwargs
    assert convert.call_count == (0 if rate == 16000 else 1)


@pytest.mark.parametrize("rate", [16000, 44100, 48000])
@pytest.mark.parametrize("container", ["bytes", "buffer", "path"])
def test_wav_header_is_authoritative(rate, container, tmp_path):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(np.full((rate, 2), 8192, dtype=np.int16).tobytes())
    audio = buf.getvalue()
    if container == "buffer":
        audio = io.BytesIO(audio)
    elif container == "path":
        path = tmp_path / "audio.wav"
        path.write_bytes(audio)
        audio = path
    with patch("jarvis.stt.engine.resample_audio", wraps=resample_audio) as convert:
        result = prepare_stt_audio(audio, source_sample_rate=8000)
    assert result.shape == (16000,)
    np.testing.assert_allclose(result, .25)
    assert convert.call_count == (0 if rate == 16000 else 1)


@pytest.mark.parametrize("kind", ["int16_stereo", "float_stereo", "pcm"])
def test_normalize_before_resampling(kind):
    audio = np.full((48000, 2), 8192, dtype=np.int16)
    if kind == "float_stereo":
        audio = audio.astype(np.float64) / 32768
    elif kind == "pcm":
        audio = audio[:, 0].tobytes()
    result = prepare_stt_audio(audio, source_sample_rate=48000)
    assert result.shape == (16000,)
    assert result.dtype == np.float32
    np.testing.assert_allclose(result, .25)


@pytest.mark.parametrize("rate", [None, 0, -1, True, 16000.5, "bad", float("nan"), float("inf")])
def test_invalid_source_rate_rejected_before_provider(rate):
    provider = MagicMock()
    engine = STTEngine(primary_engine=provider, fallback_engine=MockSTTEngine())
    with pytest.raises(ValueError, match="sample rate"):
        engine.transcribe(np.zeros(16, dtype=np.float32), source_sample_rate=rate)
    provider.transcribe.assert_not_called()


def test_legacy_ndarray_is_already_16k_and_silence_stays_silent():
    provider = MockSTTEngine()
    engine = STTEngine(primary_engine=provider, fallback_engine=MockSTTEngine())
    engine.transcribe(np.full(48000, .25, dtype=np.float32))
    assert provider.call_history[-1]["samples"] == 48000
    assert engine.transcribe(np.zeros(48000, dtype=np.float32), source_sample_rate=48000) == ""
    assert len(provider.call_history) == 1


@pytest.mark.parametrize("rate", [8000, 16000, 44100, 48000])
@pytest.mark.parametrize("incremental", [False, True])
def test_streaming_vad_honors_source_rate(rate, incremental):
    provider = MockSTTEngine()
    engine = STTEngine(primary_engine=provider, fallback_engine=MockSTTEngine())
    # 100ms frames, 0.5s speech and 1s trailing silence.
    blocks = [np.full(rate // 10, .25 if i < 5 else 0, dtype=np.float32) for i in range(15)]
    if incremental:
        results = [engine.feed_audio_block(block, sample_rate=rate) for block in blocks]
        assert any(results)
    else:
        assert engine.transcribe_stream(iter(blocks), sample_rate=rate)
    assert len(provider.call_history) == 1
    # 0.5s speech + 0.8s retained trailing silence + 0.1s duplicated pre-roll.
    # Upsampling delays one sample for the next block; pre-roll duplicates
    # that initial block, so the 8-kHz segment is two samples shorter.
    assert provider.call_history[0]["samples"] == (22398 if rate == 8000 else 22400)


def test_legacy_offline_adapter_uses_shared_boundary(whisper_model):
    from jarvis.stt.faster_whisper import FasterWhisperSTTEngine
    adapter = FasterWhisperSTTEngine()
    with patch.object(adapter, "_load_model", return_value=whisper_model):
        adapter.transcribe(np.full(48000, .25, dtype=np.float32), source_sample_rate=48000)
    assert whisper_model.transcribe.call_args.args[0].shape == (16000,)
    assert "source_sample_rate" not in whisper_model.transcribe.call_args.kwargs


@pytest.mark.parametrize("rate", [44100, 48000])
def test_streaming_tiny_blocks_do_not_lose_duration(rate):
    engine = STTEngine(primary_engine=MockSTTEngine(), fallback_engine=MockSTTEngine())
    # Observing the actual VAD clock catches cumulative rounding of each block.
    for block in np.array_split(np.full(rate, .25, dtype=np.float32), 1000):
        engine.feed_audio_block(block, sample_rate=rate)
    assert engine.vad._samples_count == 16000


@pytest.mark.parametrize("rate", [8000, 22050, 24000, 44100, 48000])
def test_tone_keeps_frequency_and_amplitude(rate):
    source = (.5 * np.sin(2 * np.pi * 440 * np.arange(rate) / rate)).astype(np.float32)
    prepared = prepare_stt_audio(source, source_sample_rate=rate)
    assert prepared.shape == (16000,)
    assert np.argmax(np.abs(np.fft.rfft(prepared))) == 440
    assert np.max(np.abs(prepared)) == pytest.approx(.5, abs=.01)


@pytest.mark.parametrize("rate", [8000, 16000, 22050, 44100, 48000])
def test_stream_conversion_is_independent_of_block_splits(rate):
    source = np.linspace(-.5, .5, rate, dtype=np.float32)
    whole = STTStreamNormalizer(rate).feed(source)
    converter = STTStreamNormalizer(rate)
    split = np.concatenate([converter.feed(b) for b in np.array_split(source, 997)])
    np.testing.assert_allclose(split, whole, atol=1e-7)
    assert len(split) == (15999 if rate == 8000 else 16000)


def test_stream_rate_switch_requires_explicit_reset():
    engine = STTEngine(primary_engine=MockSTTEngine(), fallback_engine=MockSTTEngine())
    engine.feed_audio_block(np.zeros(480, dtype=np.float32), sample_rate=48000)
    with pytest.raises(ValueError, match="reset_stream"):
        engine.feed_audio_block(np.zeros(441, dtype=np.float32), sample_rate=44100)
    engine.reset_stream(44100)
    assert engine.feed_audio_block(np.zeros(441, dtype=np.float32), sample_rate=44100) is None


def test_cloud_seam_and_capture_fallback(capture_app):
    with patch("sounddevice.InputStream", side_effect=RuntimeError("unavailable")), patch(
        "sounddevice.rec", return_value=np.full((48000, 1), .25, dtype=np.float32)
    ) as rec, patch("sounddevice.wait"):
        capture = capture_app.record_audio(duration_s=1, sample_rate=48000, return_capture=True)
    assert rec.call_args.kwargs["samplerate"] == capture.source_sample_rate == 48000
    cloud = OpenAIWhisperSTT({"api_key": "fake"})
    http = MagicMock()
    cloud.transcribe(capture, mock_http=http)
    assert http.handle_whisper_transcription.call_args.args[0].shape == (16000,)


@pytest.mark.parametrize("rate", [0, -1, True, "bad", 22050.5])
def test_capture_rejects_invalid_rates_before_hardware(rate, capture_app):
    with patch("sounddevice.InputStream") as stream, pytest.raises(ValueError):
        capture_app.record_audio(sample_rate=rate)
    stream.assert_not_called()
