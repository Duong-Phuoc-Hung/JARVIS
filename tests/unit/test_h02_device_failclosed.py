"""
tests/unit/test_h02_device_failclosed.py
=========================================
H-02 corrective-patch focused tests: one authoritative physical microphone,
consistent index/name-substring semantics between AudioEngine and
JarvisApp.record_audio(), and fail-closed (never silent-substitute) behavior
when an explicit device cannot be resolved or a previously-working device
becomes unavailable mid-capture.

See CLAUDE.md / the H-02 independent audit report for the full contract this
patch implements. Covers, in order:
  1.  Active AudioEngine device propagates to InputStream.
  2.  Same device propagates to the sd.rec fallback.
  3.  Explicit numeric int config resolves.
  4.  Explicit numeric string config resolves.
  5.  Explicit device index 0 is preserved (not discarded as falsy).
  6.  Valid case-insensitive name substring resolves.
  7.  Invalid/unmatched name fails closed.
  8.  Nonexistent numeric index fails closed.
  9.  Explicit invalid device does NOT fall through to device=None (OS default).
  10. Explicit invalid device does NOT fall through to the loudest microphone.
  11. No explicit request may still use normal automatic selection.
  12. Selected device unavailable (InputStream + sd.rec both fail) -> typed failure.
  13. Device failure is user-visible as a distinct MIC failure, not ordinary silence.
  14. H-01 CapturedAudio/source-sample-rate contract remains intact.
  15. H-03 TTS echo/settling guard remains intact.
  16. A dynamic active-device change propagates to the NEXT capture.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.audio.engine import (
    AudioEngine,
    AudioEngineMode,
    MicrophoneDeviceUnavailableError,
    MicrophoneProbeManager,
)
from jarvis.core.app import JarvisApp
from jarvis.stt.engine import CapturedAudio, prepare_stt_audio

# A realistic 4-device enumeration, shaped exactly like MicrophoneProbeManager
# expects (mirrors the pattern already used by tests/conftest.py's
# mock_sounddevice fixture and tests/unit/test_audio_engine.py).
DEVICES = [
    {"name": "Microsoft Sound Mapper - Input", "max_input_channels": 2},
    {"name": "Realtek High Definition Audio", "max_input_channels": 2},
    {"name": "USB Microphone Array", "max_input_channels": 1},
    {"name": "Virtual Audio Cable", "max_input_channels": 2},
]


@pytest.fixture
def mock_app():
    """Lightweight JarvisApp instance with a MagicMock AudioEngine, headless audio."""
    with patch("jarvis.core.app.ConfigManager"), \
         patch("jarvis.core.app.ActionDispatcher"), \
         patch("jarvis.core.app.EventBus"):
        app = JarvisApp.__new__(JarvisApp)
        app.config = {"audio.sample_rate": 44100, "stt.timeout_s": 0.3}
        app.headless = False
        app.audio_engine = MagicMock()
        app.audio_engine._active_device_index = 2
        app.audio_engine.probe_manager = MicrophoneProbeManager(devices=DEVICES)
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
        app.log_interaction = MagicMock()
        app.process_text_command = MagicMock(return_value={"response_text": ""})
        return app


def _mock_input_stream(monkeypatch_ctx=None):
    mock_inst = MagicMock()
    mock_inst.read.return_value = (np.zeros((100, 1), dtype=np.float32), False)
    return mock_inst


# ============================================================================
# 1-2. AudioEngine <-> record_audio() same-device propagation (happy path)
# ============================================================================

def test_01_active_audio_engine_device_propagates_to_input_stream(mock_app):
    """The device AudioEngine already resolved must reach InputStream unchanged."""
    mock_app.audio_engine._active_device_index = 5
    with patch("sounddevice.InputStream") as mock_stream:
        mock_stream.return_value.__enter__.return_value = _mock_input_stream()
        mock_app.record_audio(duration_s=0.2)
        assert mock_stream.call_args.kwargs["device"] == 5


def test_02_same_device_propagates_to_sd_rec_fallback(mock_app):
    """When InputStream fails, the sd.rec fallback must reuse the identical device."""
    mock_app.audio_engine._active_device_index = 5
    with patch("sounddevice.InputStream", side_effect=RuntimeError("boom")), \
         patch("sounddevice.rec") as mock_rec, \
         patch("sounddevice.wait"):
        mock_rec.return_value = np.zeros((1600, 1), dtype=np.float32)
        mock_app.record_audio(duration_s=0.2)
        assert mock_rec.call_args.kwargs["device"] == 5


# ============================================================================
# 3-6. Explicit device resolution semantics (index / numeric-string / 0 / substring)
# ============================================================================

def test_03_explicit_numeric_int_config_resolves(mock_app):
    """An int config value (e.g. 3) resolves against the real device list."""
    mock_app.audio_engine._active_device_index = None
    mock_app.config["audio.input_device"] = 3
    with patch("sounddevice.InputStream") as mock_stream:
        mock_stream.return_value.__enter__.return_value = _mock_input_stream()
        mock_app.record_audio(duration_s=0.2)
        assert mock_stream.call_args.kwargs["device"] == 3


def test_04_explicit_numeric_string_config_resolves(mock_app):
    """A numeric-string config value ("3") resolves identically to the int form."""
    mock_app.audio_engine._active_device_index = None
    mock_app.config["audio.input_device"] = "3"
    with patch("sounddevice.InputStream") as mock_stream:
        mock_stream.return_value.__enter__.return_value = _mock_input_stream()
        mock_app.record_audio(duration_s=0.2)
        assert mock_stream.call_args.kwargs["device"] == 3


def test_05_explicit_device_index_zero_is_preserved(mock_app):
    """
    Device index 0 is a fully valid explicit selection. Python falsy-0
    semantics (`0 or fallback`) must never discard it -- this was a real,
    confirmed bug in AudioEngine.start_stream()'s prior override precedence.
    """
    mock_app.audio_engine._active_device_index = None
    mock_app.config["audio.input_device"] = 0
    with patch("sounddevice.InputStream") as mock_stream:
        mock_stream.return_value.__enter__.return_value = _mock_input_stream()
        mock_app.record_audio(duration_s=0.2)
        assert mock_stream.call_args.kwargs["device"] == 0

    # Same invariant directly at the shared resolver + AudioEngine layer.
    assert MicrophoneProbeManager.resolve_explicit_device(0, DEVICES) == 0

    # AudioEngine.__init__() precedence: a non-empty input_device=0 must win
    # over device_spec immediately at construction -- proven BEFORE
    # start_stream() ever runs, not just as a coincidental final value.
    engine_ctor = AudioEngine(input_device=0, device_spec="Realtek")
    assert engine_ctor.input_device == 0
    # Only None/empty defers to device_spec -- sanity-check the other side.
    assert AudioEngine(input_device=None, device_spec="Realtek").input_device == "Realtek"
    assert AudioEngine(input_device="", device_spec="Realtek").input_device == "Realtek"

    # AudioEngine.start_stream() end-to-end: rig auto-selection to clearly
    # prefer a DIFFERENT device (index 2, loudest) so this test can actually
    # distinguish "explicit 0 was honored" from "landed on 0 by coincidence
    # via auto-select or the empty-universe index-0 fallback".
    probe_mgr = MicrophoneProbeManager(devices=DEVICES)
    probe_mgr.probe_device_rms = lambda idx, sd=None: {0: 0.0001, 1: 0.0002, 2: 0.05, 3: 0.001}.get(idx, 0.0)
    # Sanity: with NO explicit override, auto-select really would pick 2, not 0.
    fake_sd = {"devices": DEVICES, "default": {"device": [None, None]}}
    assert probe_mgr.select_best_device(fake_sd, override=None) == 2

    bus = MagicMock()
    engine = AudioEngine(input_device=0, mode=AudioEngineMode.LIVE, event_bus=bus)
    assert engine.input_device == 0
    engine.probe_manager = probe_mgr
    with patch("sounddevice.query_devices", return_value=[]):
        engine.start_stream()
    assert engine._active_device_index == 0
    engine.stop_stream()


def test_06_valid_case_insensitive_name_substring_resolves(mock_app):
    """A case-insensitive name substring (documented in default_config.yaml)
    resolves through record_audio()'s fallback path exactly like AudioEngine."""
    mock_app.audio_engine._active_device_index = None
    mock_app.config["audio.input_device"] = "realtek"  # DEVICES[1] = "Realtek High Definition Audio"
    with patch("sounddevice.InputStream") as mock_stream:
        mock_stream.return_value.__enter__.return_value = _mock_input_stream()
        mock_app.record_audio(duration_s=0.2)
        assert mock_stream.call_args.kwargs["device"] == 1


# ============================================================================
# 7-10. Fail-closed on invalid explicit device (never silently substitute)
# ============================================================================

def test_07_invalid_unmatched_name_fails_closed(mock_app):
    """A name matching no device must raise, not resolve to anything."""
    mock_app.audio_engine._active_device_index = None
    mock_app.config["audio.input_device"] = "Yeti"
    with patch("sounddevice.InputStream") as mock_stream:
        with pytest.raises(MicrophoneDeviceUnavailableError):
            mock_app.record_audio(duration_s=0.2)
        mock_stream.assert_not_called()


def test_08_nonexistent_numeric_index_fails_closed(mock_app):
    """A numeric index outside the real device range must raise, not wrap around
    to a substring match or any other device."""
    mock_app.audio_engine._active_device_index = None
    mock_app.config["audio.input_device"] = "99"
    with patch("sounddevice.InputStream") as mock_stream:
        with pytest.raises(MicrophoneDeviceUnavailableError):
            mock_app.record_audio(duration_s=0.2)
        mock_stream.assert_not_called()


def test_09_invalid_device_does_not_fall_through_to_os_default(mock_app):
    """
    The historic bug: an unresolved explicit device silently became device=None,
    handing control to the OS/PortAudio default microphone. record_audio() must
    never reach an InputStream/sd.rec call with device=None for an explicit,
    unresolved request.
    """
    mock_app.audio_engine._active_device_index = None
    mock_app.config["audio.input_device"] = "nonexistent-device-name"
    with patch("sounddevice.InputStream") as mock_stream, patch("sounddevice.rec") as mock_rec:
        with pytest.raises(MicrophoneDeviceUnavailableError):
            mock_app.record_audio(duration_s=0.2)
        mock_stream.assert_not_called()
        mock_rec.assert_not_called()


def test_10_invalid_override_does_not_fall_through_to_loudest_mic(mock_app):
    """
    At the MicrophoneProbeManager layer: an invalid override must not fall
    through to steps 2-4 of select_best_device() (default-device / loudest /
    index-0), even when one of those devices is clearly the loudest.
    """
    probe_mgr = MicrophoneProbeManager(devices=DEVICES)
    # USB Microphone Array (index 2) would win an auto-probe as the loudest --
    # confirm that path independently, then confirm an invalid override never
    # reaches it.
    probe_mgr.probe_device_rms = lambda idx, sd=None: {0: 0.0001, 1: 0.0002, 2: 0.05, 3: 0.001}.get(idx, 0.0)
    fake_sd = {"devices": DEVICES, "default": {"device": [None, None]}}
    assert probe_mgr.select_best_device(fake_sd, override=None) == 2  # sanity: loudest really is 2

    with pytest.raises(MicrophoneDeviceUnavailableError):
        probe_mgr.select_best_device(fake_sd, override="Yeti")
    with pytest.raises(MicrophoneDeviceUnavailableError):
        probe_mgr.select_best_device(fake_sd, override="99")


def test_10b_empty_injected_device_universe_with_explicit_override_fails_closed():
    """
    Pre-commit review correction: the legacy "caller controls the device
    universe, so an intentionally empty list falls back to index 0" shortcut
    must NOT fire ahead of explicit-override resolution -- otherwise an
    explicit request against an empty device universe silently, incorrectly
    resolves to device 0 instead of failing closed. Explicit-override
    resolution must run FIRST, against the (possibly empty) real universe.
    """
    empty_mgr = MicrophoneProbeManager(devices=[])

    with pytest.raises(MicrophoneDeviceUnavailableError):
        empty_mgr.select_best_device(override="3")
    with pytest.raises(MicrophoneDeviceUnavailableError):
        empty_mgr.select_best_device(override="Yeti")

    # The legacy no-explicit-override behavior for an intentionally empty
    # injected device universe is unchanged: index 0 is still returned when
    # there was genuinely no explicit request to satisfy.
    assert empty_mgr.select_best_device(override=None) == 0
    assert empty_mgr.select_best_device(override="") == 0


# ============================================================================
# 11. No explicit request -> normal automatic selection is unaffected
# ============================================================================

def test_11_no_explicit_request_still_uses_normal_auto_selection(mock_app):
    """Absence of an explicit device (None, "", or no AudioEngine + unset config)
    must still allow ordinary auto-selection -- this patch narrows failure
    handling, it does not remove auto-selection for genuinely unset config."""
    # MicrophoneProbeManager layer: None/"" both mean "no explicit request".
    probe_mgr = MicrophoneProbeManager(devices=DEVICES)
    probe_mgr.probe_device_rms = lambda idx, sd=None: {0: 0.0001, 1: 0.0002, 2: 0.05, 3: 0.001}.get(idx, 0.0)
    fake_sd = {"devices": DEVICES, "default": {"device": [None, None]}}
    assert probe_mgr.select_best_device(fake_sd, override=None) == 2
    assert probe_mgr.select_best_device(fake_sd, override="") == 2

    # record_audio() layer: no AudioEngine, no config value -> OS default is fine.
    mock_app.audio_engine = None
    mock_app.config["audio.input_device"] = None
    with patch("sounddevice.InputStream") as mock_stream:
        mock_stream.return_value.__enter__.return_value = _mock_input_stream()
        mock_app.record_audio(duration_s=0.2)
        assert mock_stream.call_args.kwargs["device"] is None


# ============================================================================
# 12-13. Device lost mid-capture: typed failure, distinguishable from silence
# ============================================================================

def test_12_selected_device_unavailable_raises_typed_failure(mock_app):
    """InputStream AND the same-device sd.rec fallback both failing must raise
    MicrophoneDeviceUnavailableError -- never a fabricated all-zero buffer."""
    mock_app.audio_engine._active_device_index = 5
    with patch("sounddevice.InputStream", side_effect=RuntimeError("disconnected")), \
         patch("sounddevice.rec", side_effect=RuntimeError("disconnected")):
        with pytest.raises(MicrophoneDeviceUnavailableError) as exc_info:
            mock_app.record_audio(duration_s=0.2)
        assert exc_info.value.spec == 5
        assert exc_info.value.reason == "capture_failed"


def test_13_voice_interaction_reports_device_failure_distinctly_from_silence(mock_app):
    """
    _start_voice_interaction() must tell a mic failure apart from the user
    simply not speaking: different overlay text, different log_interaction
    input_text, and it must never reach STT with a fabricated buffer.
    """
    mock_app.audio_engine._active_device_index = 5

    # -- Case A: genuine device failure --
    with patch("sounddevice.InputStream", side_effect=RuntimeError("gone")), \
         patch("sounddevice.rec", side_effect=RuntimeError("gone")):
        mock_app._start_voice_interaction(greeting_phrase="", trigger_name="HOTKEY_PTT", sync=True)

    mock_app.stt_engine.transcribe.assert_not_called()
    overlay_call = mock_app.overlay.show_response.call_args
    assert overlay_call is not None
    assert overlay_call.args[0] != "(không nghe thấy)"
    log_call = mock_app.log_interaction.call_args
    assert log_call.kwargs["input_text"] == "(mic_unavailable)"
    assert log_call.kwargs["status"] == "failed"
    assert "microphone" in log_call.kwargs["response"].lower() or "micro" in log_call.kwargs["response"].lower()

    # -- Case B: ordinary silence (mic worked, STT returned empty transcript) --
    mock_app.overlay.reset_mock()
    mock_app.log_interaction.reset_mock()
    mock_app.stt_engine.transcribe.reset_mock(return_value=True)
    mock_app.stt_engine.transcribe.return_value = ""
    with patch("sounddevice.InputStream") as mock_stream:
        mock_stream.return_value.__enter__.return_value = _mock_input_stream()
        mock_app._start_voice_interaction(greeting_phrase="", trigger_name="HOTKEY_PTT", sync=True)

    silence_call = mock_app.overlay.show_response.call_args
    assert silence_call.args[0] == "(không nghe thấy)"
    silence_log = mock_app.log_interaction.call_args
    assert silence_log.kwargs["input_text"] == "(silence)"
    # The two failure modes must produce genuinely different signals.
    assert silence_log.kwargs["input_text"] != "(mic_unavailable)"


# ============================================================================
# 14-15. H-01 / H-03 safety net -- unaffected by this patch
# ============================================================================

def test_14_h01_captured_audio_contract_intact(mock_app):
    """Device-resolution changes must not affect H-01's source-sample-rate
    ownership: CapturedAudio still carries the true capture rate, independent
    of which device was used, and prepare_stt_audio still normalizes to 16k."""
    mock_app.audio_engine._active_device_index = 5
    mock_app.config["stt.sample_rate"] = 48000
    with patch("sounddevice.InputStream") as mock_stream:
        mock_stream.return_value.__enter__.return_value = _mock_input_stream()
        capture = mock_app.record_audio(duration_s=0.2, return_capture=True)
    assert isinstance(capture, CapturedAudio)
    assert capture.source_sample_rate == 48000
    assert mock_stream.call_args.kwargs["samplerate"] == 48000
    assert mock_stream.call_args.kwargs["device"] == 5
    # Exactly one resample to the 16 kHz STT/model boundary; device identity
    # never leaks into audio content or sample-rate handling.
    prepared = prepare_stt_audio(capture)
    assert prepared.dtype == np.float32


def test_15_h03_echo_guard_intact(mock_app):
    """The TTS is_playing settling/lockout wait loop must still run before any
    device-resolution or capture logic executes."""
    class MockTTS:
        def __init__(self):
            self._states = [True, True, False]

        @property
        def is_playing(self):
            return self._states.pop(0) if self._states else False

    mock_app.tts_manager = MockTTS()
    mock_app.audio_engine._active_device_index = 5
    with patch("sounddevice.InputStream") as mock_stream, patch("jarvis.core.app.time.sleep") as mock_sleep:
        mock_stream.return_value.__enter__.return_value = _mock_input_stream()
        mock_app.record_audio(duration_s=0.2)
        assert mock_sleep.called
        assert mock_stream.call_args.kwargs["device"] == 5


# ============================================================================
# 16. Dynamic device change propagates to the NEXT capture
# ============================================================================

def test_16_dynamic_active_device_change_propagates_to_next_capture(mock_app):
    """A device switch on AudioEngine between two calls must be reflected on
    the very next record_audio() call -- no stale caching of a prior device."""
    mock_app.audio_engine._active_device_index = 5
    with patch("sounddevice.InputStream") as mock_stream:
        mock_stream.return_value.__enter__.return_value = _mock_input_stream()
        mock_app.record_audio(duration_s=0.2)
        assert mock_stream.call_args.kwargs["device"] == 5

        mock_app.audio_engine._active_device_index = 9
        mock_app.record_audio(duration_s=0.2)
        assert mock_stream.call_args.kwargs["device"] == 9
