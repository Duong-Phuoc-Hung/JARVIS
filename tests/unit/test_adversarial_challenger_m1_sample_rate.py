"""
tests/unit/test_adversarial_challenger_m1_sample_rate.py
=========================================================
Adversarial empirical stress tests for H-01 sample rate resolution logic
and audio capture pipeline in jarvis/core/app.py.

Evaluates:
  1. Combinatorial configurations of audio.sample_rate vs stt.sample_rate vs explicit argument.
  2. Exact buffer length calculations in headless mode (duration_s=0.1, 0.05, 1.0, etc.).
  3. Microphone device parameter propagation to sounddevice.InputStream and fallback sounddevice.rec.
  4. Robustness against double-stream failures (InputStream failure -> rec failure ->
     typed MicrophoneDeviceUnavailableError, per the H-02 corrective fail-closed contract).
  5. Anti-fabrication and truthfulness verification (no ghost success or fake intents).
"""

from unittest.mock import MagicMock, call, patch
import numpy as np
import pytest

from jarvis.core.app import JarvisApp


@pytest.fixture
def app_instance():
    """Builds an isolated, lightweight JarvisApp instance for adversarial testing."""
    with patch("jarvis.core.app.ConfigManager"), \
         patch("jarvis.core.app.ActionDispatcher"), \
         patch("jarvis.core.app.EventBus"):
        app = JarvisApp.__new__(JarvisApp)
        app.config = {
            "audio.sample_rate": 44100,
            "stt.timeout_s": 4.0,
        }
        app.headless = False
        app.audio_engine = MagicMock()
        app.audio_engine._active_device_index = 2
        app.tts_manager = MagicMock()
        app.tts_manager.is_playing = False
        app.proactive_engine = MagicMock()
        app.overlay = MagicMock()
        app.tray_controller = MagicMock()
        app.stt_engine = MagicMock()
        app._voice_lock = MagicMock()
        app._voice_lock.__enter__.return_value = True
        app._voice_lock.__exit__.return_value = False
        app._is_voice_interacting = False
        app.computer_controller = MagicMock()
        app._mic_muted = False
        return app


# ============================================================================
# 1. Combinatorial Sample Rate Resolution (H-01)
# ============================================================================

def test_sr_comb_audio_44100_no_stt_sample_rate(app_instance):
    """
    Scenario 1: audio.sample_rate is 44100, no stt.sample_rate configured, no arg.
    Expected: Captures directly at 16000 Hz.
    """
    app_instance.config = {"audio.sample_rate": 44100}
    with patch("sounddevice.InputStream") as mock_stream:
        mock_inst = MagicMock()
        mock_inst.read.return_value = (np.zeros((100, 1), dtype=np.float32), False)
        mock_stream.return_value.__enter__.return_value = mock_inst

        arr = app_instance.record_audio()
        assert isinstance(arr, np.ndarray)
        mock_stream.assert_called_once()
        _, kwargs = mock_stream.call_args
        assert kwargs["samplerate"] == 16000


def test_sr_comb_audio_48000_stt_16000(app_instance):
    """
    Scenario 2: audio.sample_rate is 48000, stt.sample_rate is 16000, no arg.
    Expected: Captures directly at 16000 Hz.
    """
    app_instance.config = {
        "audio.sample_rate": 48000,
        "stt.sample_rate": 16000,
    }
    with patch("sounddevice.InputStream") as mock_stream:
        mock_inst = MagicMock()
        mock_inst.read.return_value = (np.zeros((100, 1), dtype=np.float32), False)
        mock_stream.return_value.__enter__.return_value = mock_inst

        app_instance.record_audio()
        mock_stream.assert_called_once()
        _, kwargs = mock_stream.call_args
        assert kwargs["samplerate"] == 16000


def test_sr_comb_explicit_argument_8000(app_instance):
    """
    Scenario 3: Explicit sample_rate=8000 passed as argument.
    Expected: Must record at 8000 Hz regardless of config.
    """
    app_instance.config = {
        "audio.sample_rate": 44100,
        "stt.sample_rate": 16000,
    }
    with patch("sounddevice.InputStream") as mock_stream:
        mock_inst = MagicMock()
        mock_inst.read.return_value = (np.zeros((100, 1), dtype=np.float32), False)
        mock_stream.return_value.__enter__.return_value = mock_inst

        app_instance.record_audio(sample_rate=8000)
        mock_stream.assert_called_once()
        _, kwargs = mock_stream.call_args
        assert kwargs["samplerate"] == 8000


@pytest.mark.parametrize("cfg_audio,cfg_stt,arg_sr,expected_sr", [
    (44100, None, None, 16000),
    (48000, 16000, None, 16000),
    (48000, 22050, None, 22050),
    (44100, 16000, 8000, 8000),
    (44100, 16000, 24000, 24000),
    (96000, None, 16000, 16000),
    (44100, "16000", None, 16000),      # String in config
    (44100, None, "8000", 8000),         # String in argument
])
def test_sr_combinatorial_parameter_matrix(app_instance, cfg_audio, cfg_stt, arg_sr, expected_sr):
    """Parametric stress test covering all combinations of audio/stt configs and args."""
    cfg = {"audio.sample_rate": cfg_audio}
    if cfg_stt is not None:
        cfg["stt.sample_rate"] = cfg_stt
    app_instance.config = cfg

    with patch("sounddevice.InputStream") as mock_stream:
        mock_inst = MagicMock()
        mock_inst.read.return_value = (np.zeros((100, 1), dtype=np.float32), False)
        mock_stream.return_value.__enter__.return_value = mock_inst

        app_instance.record_audio(sample_rate=arg_sr)
        _, kwargs = mock_stream.call_args
        assert kwargs["samplerate"] == expected_sr


# ============================================================================
# 2. Headless Mode Exact Buffer Lengths
# ============================================================================

@pytest.mark.parametrize("dur_s,sr_arg,cfg_stt,expected_len", [
    (0.1, None, None, 1600),             # 0.1s * 16000 = 1600
    (0.1, 8000, None, 800),              # 0.1s * 8000 = 800
    (0.1, 44100, None, 4410),            # 0.1s * 44100 = 4410
    (0.05, None, None, 800),             # 0.05s * 16000 = 800 (min(0.05, 0.1) = 0.05)
    (0.05, 8000, None, 400),             # 0.05s * 8000 = 400
    (0.5, None, None, 1600),             # capped at 0.1s in headless mode -> 1600
    (1.0, None, None, 1600),             # capped at 0.1s in headless mode -> 1600
    (3.0, 8000, None, 800),              # capped at 0.1s in headless mode -> 800
    (None, None, 16000, 1600),           # default timeout 4.0s capped at 0.1s -> 1600
])
def test_headless_mode_exact_buffer_lengths(app_instance, dur_s, sr_arg, cfg_stt, expected_len):
    """
    Headless mode returns np.zeros(int(sr * min(max_dur, 0.1)), dtype=np.float32).
    Verifies exact integer sample length and float32 dtype across durations and sample rates.
    """
    app_instance.headless = True
    app_instance.config = {"audio.sample_rate": 44100}
    if cfg_stt:
        app_instance.config["stt.sample_rate"] = cfg_stt

    arr = app_instance.record_audio(duration_s=dur_s, sample_rate=sr_arg)
    assert isinstance(arr, np.ndarray)
    assert arr.dtype == np.float32
    assert len(arr) == expected_len
    assert np.all(arr == 0.0)


# ============================================================================
# 3. Device Parameter Passing to InputStream and Fallback rec
# ============================================================================

def test_device_passed_to_input_stream_from_audio_engine(app_instance):
    """Target device from AudioEngine._active_device_index must be passed to InputStream."""
    app_instance.audio_engine._active_device_index = 4
    with patch("sounddevice.InputStream") as mock_stream:
        mock_inst = MagicMock()
        mock_inst.read.return_value = (np.zeros((100, 1), dtype=np.float32), False)
        mock_stream.return_value.__enter__.return_value = mock_inst

        app_instance.record_audio()
        _, kwargs = mock_stream.call_args
        assert kwargs["device"] == 4


def test_device_fallback_to_config_when_audio_engine_none(app_instance):
    """
    When AudioEngine is None, record_audio() resolves an explicit numeric-string
    audio.input_device against the real device list via the SAME shared
    MicrophoneProbeManager semantics AudioEngine itself uses (H-02 corrective).
    """
    app_instance.audio_engine = None
    app_instance.config["audio.input_device"] = "3"

    devices = [
        {"name": "Microsoft Sound Mapper - Input", "max_input_channels": 2},
        {"name": "Realtek High Definition Audio", "max_input_channels": 2},
        {"name": "USB Microphone Array", "max_input_channels": 1},
        {"name": "Virtual Audio Cable", "max_input_channels": 2},
    ]

    with patch("sounddevice.InputStream") as mock_stream, \
         patch("sounddevice.query_devices", return_value=devices):
        mock_inst = MagicMock()
        mock_inst.read.return_value = (np.zeros((100, 1), dtype=np.float32), False)
        mock_stream.return_value.__enter__.return_value = mock_inst

        app_instance.record_audio()
        _, kwargs = mock_stream.call_args
        assert kwargs["device"] == 3


def test_device_name_substring_resolves_and_unmatched_fails_closed(app_instance):
    """
    H-02 corrective contract: record_audio()'s config-fallback path must honor a
    case-insensitive name-substring override exactly like AudioEngine's
    MicrophoneProbeManager does (config/default_config.yaml documents both index
    and name-substring as valid audio.input_device forms). An override that
    matches NOTHING must fail closed -- it must NEVER silently resolve to
    device=None (the previous, incorrect "unparseable -> None" behavior), since
    that would silently hand control to the OS default microphone.
    """
    from jarvis.audio.engine import MicrophoneDeviceUnavailableError

    app_instance.audio_engine = None
    devices = [
        {"name": "Microsoft Sound Mapper - Input", "max_input_channels": 2},
        {"name": "Realtek High Definition Audio", "max_input_channels": 2},
        {"name": "USB Microphone Array", "max_input_channels": 1},
    ]

    with patch("sounddevice.query_devices", return_value=devices):
        # A genuine, matching substring resolves to that device's index.
        with patch("sounddevice.InputStream") as mock_stream:
            mock_inst = MagicMock()
            mock_inst.read.return_value = (np.zeros((100, 1), dtype=np.float32), False)
            mock_stream.return_value.__enter__.return_value = mock_inst
            app_instance.config["audio.input_device"] = "usb microphone"
            app_instance.record_audio()
            assert mock_stream.call_args[1]["device"] == 2

        # An unmatched name must fail closed, not silently fall back to default.
        with patch("sounddevice.InputStream") as mock_stream:
            app_instance.config["audio.input_device"] = "default_mic_name"
            with pytest.raises(MicrophoneDeviceUnavailableError):
                app_instance.record_audio()
            mock_stream.assert_not_called()


def test_device_passed_to_fallback_rec_on_input_stream_error(app_instance):
    """
    When sounddevice.InputStream fails with an error, record_audio must fallback
    to sounddevice.rec using the exact same device and sample rate.
    """
    app_instance.audio_engine._active_device_index = 7
    with patch("sounddevice.InputStream", side_effect=RuntimeError("PortAudio InputStream unavailable")), \
         patch("sounddevice.rec") as mock_rec, \
         patch("sounddevice.wait") as mock_wait:

        mock_rec.return_value = np.zeros((48000, 1), dtype=np.float32)

        arr = app_instance.record_audio(duration_s=2.0)

        # InputStream was attempted and failed
        # Fallback rec was invoked
        mock_rec.assert_called_once()
        rec_args, rec_kwargs = mock_rec.call_args
        # Positional arg 0: num_frames = int(min(2.0, 3.0) * 16000) = 32000
        assert rec_args[0] == 32000
        assert rec_kwargs["samplerate"] == 16000
        assert rec_kwargs["channels"] == 1
        assert rec_kwargs["dtype"] == "float32"
        assert rec_kwargs["device"] == 7
        mock_wait.assert_called_once()
        assert len(arr) == 48000


def test_both_input_stream_and_rec_fail_raises_device_unavailable(app_instance):
    """
    Adversarial Double Failure (H-02 corrective):
    When InputStream AND sounddevice.rec both fail on the SAME selected device
    (e.g. mic completely unplugged or driver crash), record_audio must raise a
    typed MicrophoneDeviceUnavailableError -- it must NOT return a fabricated
    all-zero "silence" buffer, since that would make a genuine hardware failure
    indistinguishable from the user simply not speaking.
    """
    from jarvis.audio.engine import MicrophoneDeviceUnavailableError

    app_instance.audio_engine._active_device_index = 1
    with patch("sounddevice.InputStream", side_effect=RuntimeError("InputStream crashed")), \
         patch("sounddevice.rec", side_effect=RuntimeError("rec crashed")):

        with pytest.raises(MicrophoneDeviceUnavailableError) as exc_info:
            app_instance.record_audio()
        # Both capture attempts were made against the same physical device (1).
        assert exc_info.value.spec == 1
        assert exc_info.value.reason == "capture_failed"


# ============================================================================
# 4. Anti-Fabrication & Energy Cutoff Truthfulness
# ============================================================================

def test_energy_cutoff_truthfulness(app_instance):
    """
    Verify energy-based silence cutoff:
    - Initial silent calibration chunks establish ambient noise floor.
    - User speaks (440 Hz tone within bandpass 80-4000Hz, RMS > 0.018), has_speech_started becomes True.
    - Followed by 5 consecutive silent chunks (RMS <= 0.010, per app.py:1344), recording terminates early.
    """
    chunk_size = int(16000 * 0.15)  # 2400 samples
    t = np.arange(chunk_size) / 16000.0
    speech_chunk = (0.2 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32).reshape(-1, 1)
    silent_chunk = np.zeros((chunk_size, 1), dtype=np.float32)

    # Sequence: 2 silent chunks (noise floor calibration), 2 speech chunks, then 5 silent chunks (cutoff)
    stream_chunks = [silent_chunk] * 2 + [speech_chunk] * 2 + [silent_chunk] * 5 + [silent_chunk] * 5

    with patch("sounddevice.InputStream") as mock_stream, patch("sounddevice.rec") as mock_rec:
        mock_inst = MagicMock()
        mock_inst.read.side_effect = [(c, False) for c in stream_chunks]
        mock_stream.return_value.__enter__.return_value = mock_inst

        arr = app_instance.record_audio(duration_s=4.0)
        # Should have stopped after 2 + 2 + 5 = 9 chunks (early cutoff at 5 chunks, not reaching 26 chunks for 4.0s)
        assert mock_inst.read.call_count == 9
        assert len(arr) == 9 * chunk_size


def test_no_ghost_intent_on_hardware_failure(app_instance):
    """
    Verify fail-closed truthfulness (H-02 corrective):
    When hardware fails completely (InputStream AND sd.rec both fail), record_audio
    must raise a typed MicrophoneDeviceUnavailableError -- never manufacture a
    silent buffer that a caller could mistake for "the mic worked, user said
    nothing", which would risk a downstream ghost/no-op intent instead of a
    truthful, distinguishable device-failure report.
    """
    from jarvis.audio.engine import MicrophoneDeviceUnavailableError

    with patch("sounddevice.InputStream", side_effect=RuntimeError("No hardware")):
        with patch("sounddevice.rec", side_effect=RuntimeError("No hardware")):
            with pytest.raises(MicrophoneDeviceUnavailableError) as exc_info:
                app_instance.record_audio()
            assert exc_info.value.reason == "capture_failed"


# ============================================================================
# 5. Real ConfigManager Dot-Notation Integration
# ============================================================================

def test_real_config_manager_integration():
    """
    Verify that ConfigManager with dot-notation works directly with record_audio:
    - default YAML without stt section resolves stt.sample_rate default to 16000
    - config.set('stt.sample_rate', 24000) resolves to 24000
    """
    from jarvis.core.config import ConfigManager

    cfg = ConfigManager()
    cfg.load()
    # audio.sample_rate is 44100 in master default YAML
    assert cfg.get("audio.sample_rate") == 44100
    # stt.sample_rate is not explicitly in YAML, so fallback must be 16000
    assert cfg.get("stt.sample_rate", 16000) == 16000

    app = JarvisApp.__new__(JarvisApp)
    app.config = cfg
    app.headless = True
    app.audio_engine = None
    app.tts_manager = None

    # Default: 16000 Hz -> 1600 samples for 0.1s
    arr = app.record_audio(duration_s=0.1)
    assert len(arr) == 1600

    # Override stt.sample_rate in ConfigManager
    cfg.set("stt.sample_rate", 24000)
    arr2 = app.record_audio(duration_s=0.1)
    assert len(arr2) == 2400

    # Explicit argument overrides ConfigManager
    arr3 = app.record_audio(duration_s=0.1, sample_rate=8000)
    assert len(arr3) == 800

    # Capture overrides remain supported; the STT boundary consumes their rate.
    from jarvis.stt.engine import prepare_stt_audio
    capture = app.record_audio(duration_s=0.1, return_capture=True)
    assert capture.source_sample_rate == 24000
    assert len(prepare_stt_audio(capture)) == 1600
    cfg.set("stt.sample_rate", None)
    assert len(app.record_audio(duration_s=0.1)) == 1600


# ============================================================================
# 6. Empirical Adversarial Challenge: Silence, Frequencies, Waveforms, Rates
# ============================================================================

def test_adversarial_silence_boundary_4_chunks_no_early_cutoff(app_instance):
    """
    Stress-test silence chunk boundary:
    app.py:1344 specifies `if silence_chunks_after_speech >= 5: break`.
    If speech is followed by exactly 4 silent chunks, recording must NOT cut off early.
    Total: 2 calibration + 2 speech + 4 silence = 8 chunks (duration_s=1.2s -> max 8 chunks).
    Asserts mock_inst.read.call_count == 8 (no premature exit at 4 silence chunks).
    """
    chunk_size = int(16000 * 0.15)
    t = np.arange(chunk_size) / 16000.0
    speech_chunk = (0.2 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32).reshape(-1, 1)
    silent_chunk = np.zeros((chunk_size, 1), dtype=np.float32)

    stream_chunks = [silent_chunk] * 2 + [speech_chunk] * 2 + [silent_chunk] * 4

    with patch("sounddevice.InputStream") as mock_stream, patch("sounddevice.rec") as mock_rec:
        mock_inst = MagicMock()
        mock_inst.read.side_effect = [(c, False) for c in stream_chunks]
        mock_stream.return_value.__enter__.return_value = mock_inst

        arr = app_instance.record_audio(duration_s=1.2)
        assert mock_inst.read.call_count == 8
        assert len(arr) == 8 * chunk_size


def test_adversarial_intermittent_speech_resets_silence_counter(app_instance):
    """
    Stress-test silence counter reset:
    Speech -> 3 silent chunks -> Intermittent speech -> 3 silent chunks.
    Because silence never consecutively reaches 5 chunks, the counter resets to 0
    on each speech burst and recording continues until max_chunks.
    Total: 2 cal + 1 speech + 3 silence + 1 speech + 3 silence = 10 chunks (duration_s=1.5s).
    Asserts mock_inst.read.call_count == 10.
    """
    chunk_size = int(16000 * 0.15)
    t = np.arange(chunk_size) / 16000.0
    speech_chunk = (0.2 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32).reshape(-1, 1)
    silent_chunk = np.zeros((chunk_size, 1), dtype=np.float32)

    stream_chunks = (
        [silent_chunk] * 2 +
        [speech_chunk] * 1 +
        [silent_chunk] * 3 +
        [speech_chunk] * 1 +
        [silent_chunk] * 3
    )

    with patch("sounddevice.InputStream") as mock_stream, patch("sounddevice.rec") as mock_rec:
        mock_inst = MagicMock()
        mock_inst.read.side_effect = [(c, False) for c in stream_chunks]
        mock_stream.return_value.__enter__.return_value = mock_inst

        arr = app_instance.record_audio(duration_s=1.5)
        assert mock_inst.read.call_count == 10
        assert len(arr) == 10 * chunk_size


def test_adversarial_continuous_silence_runs_full_duration(app_instance):
    """
    Stress-test pure silence (user never speaks):
    has_speech_started remains False. Silence cutoff rule (silence_chunks_after_speech >= 5)
    must NEVER trigger when speech has not started.
    Recording must faithfully capture the full duration without truncating prematurely.
    Total: 10 silent chunks (duration_s=1.5s).
    """
    chunk_size = int(16000 * 0.15)
    silent_chunk = np.zeros((chunk_size, 1), dtype=np.float32)
    stream_chunks = [silent_chunk] * 10

    with patch("sounddevice.InputStream") as mock_stream, patch("sounddevice.rec") as mock_rec:
        mock_inst = MagicMock()
        mock_inst.read.side_effect = [(c, False) for c in stream_chunks]
        mock_stream.return_value.__enter__.return_value = mock_inst

        arr = app_instance.record_audio(duration_s=1.5)
        assert mock_inst.read.call_count == 10
        assert len(arr) == 10 * chunk_size


def test_adversarial_multi_frequency_speech_waveform(app_instance):
    """
    Stress-test multi-frequency speech signal:
    Composite waveform of realistic speech formants (300 Hz, 1200 Hz, 2500 Hz).
    All components fall within 80-4000 Hz speech passband.
    Verifies that multi-frequency waveforms trigger speech detection and cutoff correctly.
    """
    chunk_size = int(16000 * 0.15)
    t = np.arange(chunk_size) / 16000.0
    multi_freq_speech = (
        0.10 * np.sin(2 * np.pi * 300.0 * t) +
        0.10 * np.sin(2 * np.pi * 1200.0 * t) +
        0.05 * np.sin(2 * np.pi * 2500.0 * t)
    ).astype(np.float32).reshape(-1, 1)
    silent_chunk = np.zeros((chunk_size, 1), dtype=np.float32)

    # 2 cal + 2 multi-freq speech + 5 silence (cutoff) + 5 extra
    stream_chunks = [silent_chunk] * 2 + [multi_freq_speech] * 2 + [silent_chunk] * 5 + [silent_chunk] * 5

    with patch("sounddevice.InputStream") as mock_stream, patch("sounddevice.rec") as mock_rec:
        mock_inst = MagicMock()
        mock_inst.read.side_effect = [(c, False) for c in stream_chunks]
        mock_stream.return_value.__enter__.return_value = mock_inst

        arr = app_instance.record_audio(duration_s=4.0)
        assert mock_inst.read.call_count == 9
        assert len(arr) == 9 * chunk_size


def test_adversarial_out_of_band_sub_bass_rejection(app_instance):
    """
    Stress-test out-of-band rejection:
    A 25 Hz sub-audible AC rumble (e.g. HVAC / fan rumble) at moderate amplitude.
    The 4th-order Butterworth bandpass filter (80 Hz lowcut) attenuates 25 Hz,
    keeping filtered RMS below the speech threshold (0.018).
    Speech must NOT be triggered, and stream must NOT cut off as if speech ended.
    """
    chunk_size = int(16000 * 0.15)
    t = np.arange(chunk_size) / 16000.0
    rumble_chunk = (0.04 * np.sin(2 * np.pi * 25.0 * t)).astype(np.float32).reshape(-1, 1)
    silent_chunk = np.zeros((chunk_size, 1), dtype=np.float32)

    # 2 cal + 4 rumble chunks + 4 silent chunks (duration 1.5s = 10 chunks)
    stream_chunks = [silent_chunk] * 2 + [rumble_chunk] * 4 + [silent_chunk] * 4

    with patch("sounddevice.InputStream") as mock_stream, patch("sounddevice.rec") as mock_rec:
        mock_inst = MagicMock()
        mock_inst.read.side_effect = [(c, False) for c in stream_chunks]
        mock_stream.return_value.__enter__.return_value = mock_inst

        arr = app_instance.record_audio(duration_s=1.5)
        # Should NOT cut off at chunk 8 (which would happen if rumble was detected as speech);
        # reads all 10 chunks because speech was never detected
        assert mock_inst.read.call_count == 10
        assert len(arr) == 10 * chunk_size


def test_adversarial_dc_bias_with_noise_attenuation(app_instance):
    """
    Stress-test DC bias vs AC speech:
    A high DC bias (0.35) with tiny ambient noise (0.002).
    Because std > 1e-5, mean subtraction in filter_bandpass removes the 0.35 DC bias,
    leaving only ~0.002 RMS, far below speech threshold.
    Speech is not falsely triggered by DC bias.
    """
    chunk_size = int(16000 * 0.15)
    np.random.seed(42)
    dc_noise = (0.35 + np.random.normal(0, 0.002, (chunk_size, 1))).astype(np.float32)
    silent_chunk = np.zeros((chunk_size, 1), dtype=np.float32)

    stream_chunks = [silent_chunk] * 2 + [dc_noise] * 4 + [silent_chunk] * 4

    with patch("sounddevice.InputStream") as mock_stream, patch("sounddevice.rec") as mock_rec:
        mock_inst = MagicMock()
        mock_inst.read.side_effect = [(c, False) for c in stream_chunks]
        mock_stream.return_value.__enter__.return_value = mock_inst

        arr = app_instance.record_audio(duration_s=1.5)
        # All 10 chunks read because DC bias was filtered out and never triggered speech
        assert mock_inst.read.call_count == 10
        assert len(arr) == 10 * chunk_size


@pytest.mark.parametrize("target_sr,speech_freq", [
    (8000, 300.0),
    (22050, 440.0),
    (44100, 1000.0),
    (48000, 1000.0),
])
def test_adversarial_energy_cutoff_across_sample_rates(app_instance, target_sr, speech_freq):
    """
    Stress-test energy cutoff across diverse sample rates (8kHz, 22.05kHz, 44.1kHz, 48kHz).
    Verifies that chunk sizing, AcousticFrontEnd sample rate binding, and 5-chunk
    silence cutoff operate invariantly regardless of sampling frequency.
    """
    chunk_size = int(target_sr * 0.15)
    t = np.arange(chunk_size) / float(target_sr)
    speech_chunk = (0.2 * np.sin(2 * np.pi * speech_freq * t)).astype(np.float32).reshape(-1, 1)
    silent_chunk = np.zeros((chunk_size, 1), dtype=np.float32)

    # 2 cal + 2 speech + 5 silence (cutoff) + 5 extra
    stream_chunks = [silent_chunk] * 2 + [speech_chunk] * 2 + [silent_chunk] * 5 + [silent_chunk] * 5

    with patch("sounddevice.InputStream") as mock_stream, patch("sounddevice.rec") as mock_rec:
        mock_inst = MagicMock()
        mock_inst.read.side_effect = [(c, False) for c in stream_chunks]
        mock_stream.return_value.__enter__.return_value = mock_inst

        arr = app_instance.record_audio(duration_s=4.0, sample_rate=target_sr)
        # Always terminates at exactly 9 chunks (2 + 2 + 5)
        assert mock_inst.read.call_count == 9
        assert len(arr) == 9 * chunk_size


def test_adversarial_mock_isolation_protects_host_hardware(app_instance):
    """
    Stress-test mock isolation:
    Guarantees that when sounddevice.InputStream and sounddevice.rec are patched,
    no unmocked PortAudio stream, device query, or real hardware recording executes.
    Verifies zero hardware side effects during automated test suite runs.
    """
    with patch("sounddevice.InputStream") as mock_stream, \
         patch("sounddevice.rec") as mock_rec, \
         patch("sounddevice.wait") as mock_wait, \
         patch("sounddevice.play") as mock_play:

        mock_inst = MagicMock()
        mock_inst.read.return_value = (np.zeros((2400, 1), dtype=np.float32), False)
        mock_stream.return_value.__enter__.return_value = mock_inst

        app_instance.record_audio(duration_s=0.3)

        # InputStream was entered and cleaned up
        mock_stream.assert_called_once()
        mock_stream.return_value.__enter__.assert_called_once()
        mock_stream.return_value.__exit__.assert_called_once()
        # Fallback rec and unmocked sound playback were never touched
        mock_rec.assert_not_called()
        mock_wait.assert_not_called()
        mock_play.assert_not_called()


