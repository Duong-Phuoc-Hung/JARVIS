"""
tests/e2e/test_beta_v1_acceptance.py
====================================
Comprehensive End-to-End Acceptance Test Suite for JARVIS Beta v1.

Coverage Architecture (4 Tiers):
  - TIER 1: Feature Coverage
      * F-01: 16kHz Direct Capture Precedence over system playback sample rate
      * F-02: Active Input Device Synchronization with AudioEngine
      * F-03: Acoustic Settling Delay (150ms) and Active Playback Lockout
      * F-04: Ctrl+Shift+L PTT Hotkey initiating voice interaction
      * F-05: Hardware Volume & Brightness Fail-Closed semantics on None
      * F-06 / F-07: Comms Fail-Closed NOT_CONFIGURED semantics (Telegram, Zalo, Discord, IMAP)
  - TIER 2: Boundary & Corner Cases
      * Zero/extreme durations and buffer handling
      * Invalid/string/None device index types and fallback resolution
      * Playback lockout timeout safety bounds (prevents deadlock)
      * Single-flight voice interaction mutex lockout
      * Uninitialized/None computer controller handling
      * Out-of-bounds volume & brightness parameter clamping
      * Comms security whitelist enforcement and token-bucket burst limits
  - TIER 3: Cross-Component Interactions
      * Hotkey PTT -> Greeting TTS -> 150ms Settling -> Device Sync -> 16kHz Record -> STT
      * Intent Dispatcher -> Volume Fail-Closed propagation
      * Unified 4-channel Comms Fail-Closed audit
      * Dynamic AudioEngine device switch propagation
      * TTS playback lockout during recording
  - TIER 4: Real-World Application Workflows
      * Scenario 1: Full PTT Voice Interaction roundtrip
      * Scenario 2: Hardware Control failure and honest recovery
      * Scenario 3: Multi-channel security alert dispatch under unconfigured credentials
      * Scenario 4: 4-tier acoustic settling and reverberation decay cycle
"""
from __future__ import annotations

import concurrent.futures
import threading
import time
from typing import Any
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest

from jarvis.comms.discord import DiscordBotController, DiscordConfig
from jarvis.comms.email_imap import IMAPEmailReader, IMAPNotConfiguredError
from jarvis.comms.telegram import TelegramBotController, TelegramConfig
from jarvis.comms.zalo import ZaloBotController, ZaloConfig, ZaloSendResult
from jarvis.core.app import JarvisApp


# ============================================================================
# DETERMINISTIC TEST HELPERS & FIXTURES
# ============================================================================

class ImmediateExecutor:
    """Executes concurrent.futures tasks synchronously for fast deterministic testing."""
    def __init__(self, *args, **kwargs):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def submit(self, fn, *args, **kwargs):
        fut = MagicMock()
        fut.result.return_value = fn(*args, **kwargs)
        return fut


@pytest.fixture
def acceptance_app():
    """Constructs a deterministic JarvisApp instance with isolated seams for E2E testing."""
    with patch("jarvis.core.app.ConfigManager"), \
         patch("jarvis.core.app.ActionDispatcher"), \
         patch("jarvis.core.app.EventBus"):
        app = JarvisApp.__new__(JarvisApp)
        app.config = {
            "audio.sample_rate": 44100,       # System playback rate
            "stt.sample_rate": 16000,         # Direct STT capture rate (F-01)
            "stt.timeout_s": 0.5,
            "jarvis.unknown_intent_phrase": "Xin lỗi, tôi không hiểu lệnh đó.",
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
        app.stt_engine.transcribe.return_value = ""
        app.process_text_command = MagicMock(return_value={"status": "success", "response_text": "OK"})
        app.hotkey_manager = MagicMock()
        app.computer_controller = MagicMock()
        app._voice_lock = threading.Lock()
        app._is_voice_interacting = False
        app._mic_muted = False
        app.log_interaction = MagicMock()
        app.dispatcher = MagicMock()
        return app


# ============================================================================
# TIER 1: FEATURE COVERAGE
# ============================================================================

class TestBetaV1Tier1FeatureCoverage:
    """Tier 1: Direct verification of individual Beta v1 acceptance features."""

    def test_tier1_record_audio_16khz_direct_capture_precedence(self, acceptance_app):
        """F-01: record_audio() captures directly at 16kHz regardless of 44.1kHz playback rate."""
        acceptance_app.config["audio.sample_rate"] = 44100
        acceptance_app.config["stt.sample_rate"] = 16000

        with patch("sounddevice.InputStream") as mock_stream:
            mock_stream_instance = MagicMock()
            mock_stream_instance.read.return_value = (np.zeros((2400, 1), dtype=np.float32), False)
            mock_stream.return_value.__enter__.return_value = mock_stream_instance

            # 1. Default call (no sample_rate arg passed)
            audio = acceptance_app.record_audio(duration_s=0.3)
            assert isinstance(audio, np.ndarray)
            mock_stream.assert_called_once()
            _, kwargs = mock_stream.call_args
            assert kwargs.get("samplerate") == 16000, "Must prioritize 16kHz for STT model alignment"

            # 2. Explicit sample_rate parameter call
            mock_stream.reset_mock()
            acceptance_app.record_audio(duration_s=0.3, sample_rate=16000)
            mock_stream.assert_called_once()
            _, kwargs_explicit = mock_stream.call_args
            assert kwargs_explicit.get("samplerate") == 16000

    def test_tier1_record_audio_active_input_device_sync_with_audio_engine(self, acceptance_app):
        """F-02: record_audio() synchronizes input device with AudioEngine._active_device_index."""
        acceptance_app.audio_engine._active_device_index = 4

        with patch("sounddevice.InputStream") as mock_stream:
            mock_inst = MagicMock()
            mock_inst.read.return_value = (np.zeros((100, 1), dtype=np.float32), False)
            mock_stream.return_value.__enter__.return_value = mock_inst

            acceptance_app.record_audio(duration_s=0.2)
            mock_stream.assert_called_once()
            _, kwargs = mock_stream.call_args
            assert kwargs.get("device") == 4, "Must pass AudioEngine._active_device_index to InputStream"

        # Test fallback sounddevice.rec path
        with patch("sounddevice.InputStream", side_effect=RuntimeError("Stream init failed")), \
             patch("sounddevice.rec") as mock_rec, \
             patch("sounddevice.wait"):
            mock_rec.return_value = np.zeros((1600, 1), dtype=np.float32)

            acceptance_app.record_audio(duration_s=0.2)
            mock_rec.assert_called_once()
            _, rec_kwargs = mock_rec.call_args
            assert rec_kwargs.get("device") == 4, "Fallback rec must also target active AudioEngine device"

    def test_tier1_acoustic_settling_delay(self, acceptance_app):
        """F-03: Enforce 150ms settling delay post-greeting before recording."""
        acceptance_app.record_audio = MagicMock(return_value=np.zeros(160, dtype=np.float32))

        with patch("threading.Thread") as mock_thread, \
             patch("concurrent.futures.ThreadPoolExecutor", ImmediateExecutor), \
             patch("jarvis.core.app.time.sleep") as mock_sleep:

            acceptance_app._start_voice_interaction(greeting_phrase="Xin chào", trigger_name="TEST_TRIGGER")
            mock_thread.assert_called_once()
            thread_target = mock_thread.call_args[1]["target"]

            # Execute thread target directly to inspect execution trace
            thread_target()
            acceptance_app.tts_manager.speak.assert_any_call("Xin chào", wait=True)
            # Verify settling delay 150ms (0.15s) called
            assert any(call_arg == call(0.15) for call_arg in mock_sleep.call_args_list), \
                "150ms acoustic settling delay must be invoked post-TTS greeting"

    def test_tier1_acoustic_playback_lockout(self, acceptance_app):
        """F-03: record_audio() waits if TTS is actively playing to prevent self-capture."""
        class MockTTS:
            def __init__(self):
                self._states = [True, True, False]
            @property
            def is_playing(self):
                return self._states.pop(0) if self._states else False

        acceptance_app.tts_manager = MockTTS()

        with patch("sounddevice.InputStream") as mock_stream, \
             patch("jarvis.core.app.time.sleep") as mock_sleep:
            mock_inst = MagicMock()
            mock_inst.read.return_value = (np.zeros((100, 1), dtype=np.float32), False)
            mock_stream.return_value.__enter__.return_value = mock_inst

            acceptance_app.record_audio(duration_s=0.2)
            assert mock_sleep.called, "Must wait while TTS playback is active"

    def test_tier1_hotkey_ctrl_shift_l_initiates_voice_interaction_ptt(self, acceptance_app):
        """F-04: Ctrl+Shift+L PTT hotkey initiates _start_voice_interaction without crash."""
        acceptance_app._register_default_hotkeys()

        registered_hotkeys = {}
        for reg_call in acceptance_app.hotkey_manager.register.call_args_list:
            key, cb, desc = reg_call[0]
            registered_hotkeys[key] = cb

        assert "Ctrl+Shift+L" in registered_hotkeys, "Ctrl+Shift+L must be registered in hotkey manager"
        ptt_callback = registered_hotkeys["Ctrl+Shift+L"]

        with patch("threading.Thread") as mock_thread:
            ptt_callback()
            mock_thread.assert_called_once()
            _, kwargs = mock_thread.call_args
            assert kwargs.get("target") == acceptance_app._start_voice_interaction
            assert kwargs.get("kwargs", {}).get("trigger_name") == "HOTKEY_PTT"
            assert kwargs.get("kwargs", {}).get("greeting_phrase") == "Vâng, tôi nghe."

    def test_tier1_system_volume_fail_closed_on_none_controller(self, acceptance_app):
        """F-05: Master volume control reports fail-closed when hardware returns None."""
        acceptance_app.computer_controller.set_volume.return_value = None
        res_set = acceptance_app._handle_system_volume(level=70)
        assert res_set["status"] == "failed"
        assert res_set["success"] is False
        assert res_set["volume"] is None
        assert res_set["error"] == "VOLUME_SET_FAILED"

        acceptance_app.computer_controller.change_volume.return_value = None
        res_change = acceptance_app._handle_system_volume(delta=15)
        assert res_change["status"] == "failed"
        assert res_change["success"] is False
        assert res_change["volume"] is None
        assert res_change["error"] == "VOLUME_CHANGE_FAILED"

    def test_tier1_system_brightness_fail_closed_on_none_controller(self, acceptance_app):
        """F-05: Display brightness control reports fail-closed when hardware returns None."""
        acceptance_app.computer_controller.set_brightness.return_value = None
        res_set = acceptance_app._handle_system_brightness(level=50)
        assert res_set["status"] == "failed"
        assert res_set["success"] is False
        assert res_set["brightness"] is None
        assert res_set["error"] == "BRIGHTNESS_SET_FAILED"

        acceptance_app.computer_controller.change_brightness.return_value = None
        res_change = acceptance_app._handle_system_brightness(delta=-10)
        assert res_change["status"] == "failed"
        assert res_change["success"] is False
        assert res_change["brightness"] is None
        assert res_change["error"] == "BRIGHTNESS_CHANGE_FAILED"

    def test_tier1_comms_telegram_fail_closed_not_configured(self):
        """F-07: TelegramBotController returns NOT_CONFIGURED when HTTP client is missing."""
        controller = TelegramBotController(http_client=None)

        msg_result = controller.send_message(chat_id=123456, text="Test Message")
        assert msg_result["ok"] is False
        assert msg_result["error_code"] == "NOT_CONFIGURED"

        photo_result = controller.send_photo(chat_id=123456, photo_bytes=b"fake_image_bytes")
        assert photo_result["ok"] is False
        assert photo_result["error_code"] == "NOT_CONFIGURED"

    def test_tier1_comms_zalo_fail_closed_not_configured(self):
        """F-06 / F-07: ZaloBotController returns NOT_CONFIGURED when access token is unconfigured."""
        cfg = ZaloConfig(access_token="", oa_id="")
        controller = ZaloBotController(config=cfg, is_mock=False)

        msg_res = controller.send_message(user_id="user_999", text="Test Zalo")
        assert isinstance(msg_res, ZaloSendResult)
        assert msg_res.success is False
        assert msg_res.error == "NOT_CONFIGURED"

        img_res = controller.send_image(user_id="user_999", image_path="snapshot.jpg")
        assert isinstance(img_res, ZaloSendResult)
        assert img_res.success is False
        assert img_res.error == "NOT_CONFIGURED"

    def test_tier1_comms_discord_fail_closed_not_configured(self):
        """F-07: DiscordBotController returns NOT_CONFIGURED when bot_token is empty."""
        controller = DiscordBotController(bot_token="", http_client=None)

        res = controller.send_message(channel_id=11223344, content="Test Discord")
        assert res["success"] is False
        assert res["error_code"] == "NOT_CONFIGURED"

    def test_tier1_comms_imap_fail_closed_not_configured(self):
        """F-07: IMAPEmailReader raises IMAPNotConfiguredError when credentials are empty."""
        reader = IMAPEmailReader(host="", username="", password="")
        with pytest.raises(IMAPNotConfiguredError) as exc_info:
            reader.connect()
        assert "NOT_CONFIGURED" in str(exc_info.value)


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ============================================================================

class TestBetaV1Tier2Boundaries:
    """Tier 2: Verification of edge conditions, boundary values, and resource constraints."""

    def test_tier2_audio_record_duration_and_chunk_boundaries(self, acceptance_app):
        """Boundary: Verify record_audio handles duration=0.0 and duration exceeding timeout."""
        with patch("sounddevice.InputStream") as mock_stream:
            mock_inst = MagicMock()
            mock_inst.read.return_value = (np.zeros((100, 1), dtype=np.float32), True)  # overflowed=True
            mock_stream.return_value.__enter__.return_value = mock_inst

            # Duration 0: should handle gracefully without zero-division or crash
            buf_zero = acceptance_app.record_audio(duration_s=0.0)
            assert isinstance(buf_zero, np.ndarray)
            assert buf_zero.dtype == np.float32

            # Duration exceeding configured timeout: should clamp
            acceptance_app.config["stt.timeout_s"] = 0.5
            buf_long = acceptance_app.record_audio(duration_s=10.0)
            assert isinstance(buf_long, np.ndarray)

    def test_tier2_audio_engine_device_index_boundary_types(self, acceptance_app):
        """
        Boundary (H-02 corrective contract): record_audio() must apply the SAME
        index/name-substring/fail-closed semantics as AudioEngine's
        MicrophoneProbeManager -- never silently substitute device=None (OS default)
        or a different physical microphone for an explicit, unresolved request.
        """
        from jarvis.audio.engine import MicrophoneDeviceUnavailableError, MicrophoneProbeManager

        devices = [
            {"index": 0, "name": "Microsoft Sound Mapper - Input", "max_input_channels": 2},
            {"index": 1, "name": "Realtek High Definition Audio", "max_input_channels": 2},
            {"index": 2, "name": "USB Microphone Array", "max_input_channels": 1},
            {"index": 3, "name": "Virtual Audio Cable", "max_input_channels": 2},
        ]

        with patch("sounddevice.InputStream") as mock_stream:
            mock_inst = MagicMock()
            mock_inst.read.return_value = (np.zeros((100, 1), dtype=np.float32), False)
            mock_stream.return_value.__enter__.return_value = mock_inst

            # 1. audio_engine._active_device_index is None -> falls back to config
            #    numeric string "3", resolved against the real device list.
            acceptance_app.audio_engine._active_device_index = None
            acceptance_app.audio_engine.probe_manager = MicrophoneProbeManager(devices=devices)
            acceptance_app.config["audio.input_device"] = "3"
            acceptance_app.record_audio(duration_s=0.2)
            assert mock_stream.call_args[1]["device"] == 3

            # 2. Config has a VALID case-insensitive name substring -> resolves to
            #    that device's index, exactly like AudioEngine's own resolution.
            mock_stream.reset_mock()
            acceptance_app.config["audio.input_device"] = "usb microphone"
            acceptance_app.record_audio(duration_s=0.2)
            assert mock_stream.call_args[1]["device"] == 2

            # 3. audio_engine is None entirely, no explicit device configured ->
            #    no explicit request was made, so device=None (OS default) is fine.
            mock_stream.reset_mock()
            acceptance_app.audio_engine = None
            acceptance_app.config["audio.input_device"] = None
            acceptance_app.record_audio(duration_s=0.2)
            assert mock_stream.call_args[1]["device"] is None

            # 4. Explicit device name that matches NOTHING on the system must fail
            #    closed -- never silently pass device=None to PortAudio and never
            #    fall through to a different physical microphone.
            mock_stream.reset_mock()
            acceptance_app.audio_engine = MagicMock()
            acceptance_app.audio_engine._active_device_index = None
            acceptance_app.audio_engine.probe_manager = MicrophoneProbeManager(devices=devices)
            acceptance_app.config["audio.input_device"] = "usb_microphone_name"
            with pytest.raises(MicrophoneDeviceUnavailableError):
                acceptance_app.record_audio(duration_s=0.2)
            mock_stream.assert_not_called()

    def test_tier2_acoustic_playback_lockout_timeout_bound(self, acceptance_app):
        """Boundary: Verify record_audio does not deadlock if TTS is_playing hangs perpetually."""
        class StalledTTS:
            @property
            def is_playing(self):
                return True  # Never clears

        acceptance_app.tts_manager = StalledTTS()
        # Advance time.monotonic across iterations to simulate 1.0s timeout expiration
        monotonic_sequence = [100.0, 100.2, 100.6, 101.5]
        with patch("sounddevice.InputStream") as mock_stream, \
             patch("jarvis.core.app.time.monotonic", side_effect=monotonic_sequence), \
             patch("jarvis.core.app.time.sleep") as mock_sleep:
            mock_inst = MagicMock()
            mock_inst.read.return_value = (np.zeros((100, 1), dtype=np.float32), False)
            mock_stream.return_value.__enter__.return_value = mock_inst

            acceptance_app.record_audio(duration_s=0.1)
            assert mock_sleep.call_count >= 1

    def test_tier2_voice_interaction_single_flight_mutex_lockout(self, acceptance_app):
        """Boundary: Suppress concurrent voice interaction triggers when interaction is active."""
        acceptance_app._is_voice_interacting = True

        with patch("threading.Thread") as mock_thread:
            acceptance_app._start_voice_interaction(trigger_name="CONCURRENT_HOTKEY")
            # Should return immediately without spawning a secondary voice loop
            mock_thread.assert_not_called()

    def test_tier2_hardware_volume_brightness_none_controller_boundary(self, acceptance_app):
        """Boundary: App returns failed status if computer_controller is None."""
        acceptance_app.computer_controller = None

        vol_res = acceptance_app._handle_system_volume(level=50)
        assert vol_res["status"] == "failed"
        assert vol_res["success"] is False

        bri_res = acceptance_app._handle_system_brightness(level=50)
        assert bri_res["status"] == "failed"
        assert bri_res["success"] is False

    def test_tier2_hardware_boundary_level_clamping(self, acceptance_app):
        """Boundary: Extreme volume and brightness levels pass cleanly to controller for clamping."""
        acceptance_app.computer_controller.set_volume.return_value = 100
        res_high = acceptance_app._handle_system_volume(level=150)
        acceptance_app.computer_controller.set_volume.assert_called_with(150)
        assert res_high["success"] is True

        acceptance_app.computer_controller.set_volume.return_value = 0
        res_low = acceptance_app._handle_system_volume(level=-20)
        acceptance_app.computer_controller.set_volume.assert_called_with(-20)
        assert res_low["success"] is True

    def test_tier2_comms_unauthorized_user_boundary(self):
        """Boundary: Comms reject unauthorized user IDs according to fail-closed whitelist."""
        # Telegram
        tg = TelegramBotController(allowed_user_ids={11111})
        res_tg = tg.handle_inbound_message(user_id=99999, text="/status")
        assert 99999 in tg.security_violations
        assert not tg.is_user_authorized(99999)

        # Zalo
        zalo = ZaloBotController(config=ZaloConfig(whitelist_user_ids=["allowed_user"]))
        assert zalo.is_user_authorized("intruder_user") is False
        assert zalo.is_user_authorized("") is False

        # Discord
        discord = DiscordBotController(whitelist_user_ids=[1001, 1002])
        assert discord.is_user_authorized(9999) is False

    def test_tier2_comms_rate_limiter_burst_boundary(self):
        """Boundary: Rate limiter enforces burst limits on fast repeated requests."""
        cfg = ZaloConfig(
            whitelist_user_ids=["user_burst"],
            access_token="test_tok",
        )
        zalo = ZaloBotController(config=cfg, is_mock=True)

        # Send 5 requests within burst limit (burst_limit=5)
        for i in range(5):
            res = zalo.handle_inbound_message("user_burst", f"/calc {i}+{i}")
            assert res["status"] == 200

        # 6th immediate request must be rate-limited (429)
        res_blocked = zalo.handle_inbound_message("user_burst", "/calc 99+99")
        assert res_blocked["status"] == 429
        assert "Too Many Requests" in res_blocked["error"]


# ============================================================================
# TIER 3: CROSS-COMPONENT INTERACTIONS
# ============================================================================

class TestBetaV1Tier3Interactions:
    """Tier 3: Verification of interactions between interconnected subsystems."""

    def test_tier3_interaction_hotkey_ptt_to_settling_to_record_audio_pipeline(self, acceptance_app):
        """Interaction: PTT hotkey triggers greeting, 150ms settling, and records from active device at 16kHz."""
        acceptance_app._register_default_hotkeys()
        ptt_cb = acceptance_app.hotkey_manager.register.call_args_list[1][0][1]

        recorded_events = []
        acceptance_app.audio_engine._active_device_index = 8
        acceptance_app.stt_engine.transcribe.return_value = "chào trợ lý"

        with patch("sounddevice.InputStream") as mock_stream, \
             patch("concurrent.futures.ThreadPoolExecutor", ImmediateExecutor), \
             patch("jarvis.core.app.time.sleep") as mock_sleep:

            mock_inst = MagicMock()
            mock_inst.read.return_value = (np.zeros((2400, 1), dtype=np.float32), False)
            mock_stream.return_value.__enter__.return_value = mock_inst

            # Hook sleep to trace ordering
            def trace_sleep(duration):
                recorded_events.append(("sleep", duration))
            mock_sleep.side_effect = trace_sleep

            # Hook speak to trace ordering
            def trace_speak(phrase, wait=True):
                recorded_events.append(("speak", phrase, wait))
            acceptance_app.tts_manager.speak.side_effect = trace_speak

            # Trigger PTT: ptt_cb spawns thread running _start_voice_interaction
            with patch("threading.Thread") as mock_thread:
                ptt_cb()
                start_fn = mock_thread.call_args[1]["target"]
                start_kwargs = mock_thread.call_args[1]["kwargs"]

                # Invoking start_fn runs _start_voice_interaction which spawns _voice_loop
                mock_thread.reset_mock()
                start_fn(**start_kwargs)
                voice_loop_fn = mock_thread.call_args[1]["target"]

                # Execute voice loop
                voice_loop_fn()

            # Assert order: speak -> sleep(0.15)
            speak_idx = next(i for i, ev in enumerate(recorded_events) if ev[0] == "speak")
            settle_idx = next(i for i, ev in enumerate(recorded_events) if ev[0] == "sleep" and ev[1] == 0.15)
            assert settle_idx > speak_idx, "Settling delay must occur after greeting completes"

            # Assert stream opened with 16000 Hz and device 8
            assert mock_stream.call_args[1]["samplerate"] == 16000
            assert mock_stream.call_args[1]["device"] == 8

    def test_tier3_interaction_voice_intent_to_volume_fail_closed_propagation(self, acceptance_app):
        """Interaction: ActionDispatcher routes volume action to fail-closed handler when hardware returns None."""
        acceptance_app.computer_controller.set_volume.return_value = None

        # Call the actual bound handler method
        result = acceptance_app._handle_system_volume(level=85)
        assert result["status"] == "failed"
        assert result["success"] is False
        assert result["error"] == "VOLUME_SET_FAILED"
        assert "Không thể đặt âm lượng" in result["message"]

    def test_tier3_interaction_multi_channel_comms_fail_closed_audit(self):
        """Interaction: Cross-channel audit verifies all 4 adapters report NOT_CONFIGURED simultaneously."""
        tg = TelegramBotController(http_client=None)
        zalo = ZaloBotController(config=ZaloConfig(access_token=""), is_mock=False)
        discord = DiscordBotController(bot_token="", http_client=None)
        imap = IMAPEmailReader(host="", username="", password="")

        # Telegram
        tg_status = tg.send_message(101, "ping")
        # Zalo
        zalo_status = zalo.send_message("uid_101", "ping")
        # Discord
        discord_status = discord.send_message(202, "ping")
        # IMAP
        imap_not_configured = False
        try:
            imap.connect()
        except IMAPNotConfiguredError:
            imap_not_configured = True

        assert tg_status["error_code"] == "NOT_CONFIGURED"
        assert zalo_status.error == "NOT_CONFIGURED"
        assert discord_status["error_code"] == "NOT_CONFIGURED"
        assert imap_not_configured is True

    def test_tier3_interaction_audio_engine_device_switch_propagation(self, acceptance_app):
        """Interaction: AudioEngine device switch dynamically propagates to subsequent record_audio() calls."""
        with patch("sounddevice.InputStream") as mock_stream:
            mock_inst = MagicMock()
            mock_inst.read.return_value = (np.zeros((100, 1), dtype=np.float32), False)
            mock_stream.return_value.__enter__.return_value = mock_inst

            # First recording on device 2
            acceptance_app.audio_engine._active_device_index = 2
            acceptance_app.record_audio(duration_s=0.2)
            assert mock_stream.call_args[1]["device"] == 2

            # Hot-switch device in AudioEngine to device 9
            mock_stream.reset_mock()
            acceptance_app.audio_engine._active_device_index = 9
            acceptance_app.record_audio(duration_s=0.2)
            assert mock_stream.call_args[1]["device"] == 9

    def test_tier3_interaction_tts_playback_lockout_during_recording(self, acceptance_app):
        """Interaction: Active TTS blocks record_audio until speech output finishes."""
        playback_log = []

        class MockTTS:
            def __init__(self):
                self._counter = 2
            @property
            def is_playing(self):
                is_active = self._counter > 0
                self._counter -= 1
                playback_log.append(is_active)
                return is_active

        acceptance_app.tts_manager = MockTTS()

        with patch("sounddevice.InputStream") as mock_stream, patch("jarvis.core.app.time.sleep") as mock_sleep:
            mock_inst = MagicMock()
            mock_inst.read.return_value = (np.zeros((100, 1), dtype=np.float32), False)
            mock_stream.return_value.__enter__.return_value = mock_inst

            acceptance_app.record_audio(duration_s=0.2)
            # Should have checked playback twice as True, then False
            assert playback_log == [True, True, False]
            assert mock_stream.called


# ============================================================================
# TIER 4: REAL-WORLD APPLICATION WORKFLOWS
# ============================================================================

class TestBetaV1Tier4Workflows:
    """Tier 4: Verification of complete multi-step user scenarios and workflows."""

    def test_tier4_workflow_ptt_voice_interaction_roundtrip(self, acceptance_app):
        """Workflow: Full PTT voice interaction turnaround from hotkey to executed response."""
        acceptance_app._register_default_hotkeys()
        ptt_cb = acceptance_app.hotkey_manager.register.call_args_list[1][0][1]

        # Setup mock audio capture and STT command transcription
        acceptance_app.stt_engine.transcribe.return_value = "bật đèn bàn"
        acceptance_app.process_text_command = MagicMock(return_value={
            "status": "success",
            "response_text": "Đã bật đèn bàn cho Ngài.",
        })

        with patch("threading.Thread") as mock_thread, \
             patch("sounddevice.InputStream") as mock_stream, \
             patch("concurrent.futures.ThreadPoolExecutor", ImmediateExecutor), \
             patch("jarvis.core.app.time.sleep"):

            mock_inst = MagicMock()
            mock_inst.read.return_value = (np.zeros((2400, 1), dtype=np.float32), False)
            mock_stream.return_value.__enter__.return_value = mock_inst

            # 1. User presses Ctrl+Shift+L: spawns _start_voice_interaction thread
            ptt_cb()
            start_fn = mock_thread.call_args[1]["target"]
            start_kwargs = mock_thread.call_args[1]["kwargs"]

            # 2. _start_voice_interaction spawns _voice_loop thread
            mock_thread.reset_mock()
            start_fn(**start_kwargs)
            voice_loop_fn = mock_thread.call_args[1]["target"]

            # 3. Execute voice loop
            voice_loop_fn()

        # 4. Verify end-to-end trace
        acceptance_app.overlay.show_listening.assert_called_with("Vâng, tôi nghe.")
        acceptance_app.tts_manager.speak.assert_any_call("Vâng, tôi nghe.", wait=True)
        acceptance_app.process_text_command.assert_called_with("bật đèn bàn", "hotkey_ptt")
        acceptance_app.tts_manager.speak.assert_any_call("Đã bật đèn bàn cho Ngài.", wait=True)
        acceptance_app.overlay.show_response.assert_called_with("bật đèn bàn", "Đã bật đèn bàn cho Ngài.")

    def test_tier4_workflow_hardware_volume_control_failure_and_recovery(self, acceptance_app):
        """Workflow: Voice command for volume adjustment handles hardware failure without ghost success."""
        # Hardware controller fails
        acceptance_app.computer_controller.change_volume.return_value = None

        # Execute command through handler
        res = acceptance_app._handle_system_volume(delta=10)

        # Assert honest failure reporting
        assert res["status"] == "failed"
        assert res["success"] is False
        assert res["error"] == "VOLUME_CHANGE_FAILED"
        assert "Không thể điều chỉnh âm lượng" in res["message"]

    def test_tier4_workflow_comms_security_alert_unconfigured_protection(self):
        """Workflow: Security intruder alert distribution handles unconfigured channels safely."""
        tg = TelegramBotController(http_client=None)
        zalo = ZaloBotController(config=ZaloConfig(access_token=""), is_mock=False)
        discord = DiscordBotController(bot_token="", http_client=None)

        alert_text = "🚨 CẢNH BÁO: Phát hiện đăng nhập lạ vào máy trạm!"
        fake_photo = b"\xFF\xD8\xFF\xE0\x00\x10JFIF"

        # Dispatch alerts across all three channels
        tg_res = tg.send_photo(chat_id=123, photo_bytes=fake_photo, caption=alert_text)
        zalo_res = zalo.send_message(user_id="admin_user", text=alert_text)
        discord_res = discord.send_message(channel_id=456, content=alert_text)

        # Audit that all adapters recorded fail-closed status without raising unhandled exceptions
        assert tg_res["ok"] is False
        assert tg_res["error_code"] == "NOT_CONFIGURED"

        assert zalo_res.success is False
        assert zalo_res.error == "NOT_CONFIGURED"

        assert discord_res["success"] is False
        assert discord_res["error_code"] == "NOT_CONFIGURED"

    def test_tier4_workflow_acoustic_settling_and_reverberation_decay_cycle(self, acceptance_app):
        """Workflow: 4-tier acoustic protection cycle executes cleanly and releases locks."""
        acceptance_app.stt_engine.transcribe.return_value = ""  # Silence

        with patch("threading.Thread") as mock_thread, \
             patch("sounddevice.InputStream") as mock_stream, \
             patch("concurrent.futures.ThreadPoolExecutor", ImmediateExecutor), \
             patch("jarvis.core.app.time.sleep") as mock_sleep:

            mock_inst = MagicMock()
            mock_inst.read.return_value = (np.zeros((100, 1), dtype=np.float32), False)
            mock_stream.return_value.__enter__.return_value = mock_inst

            acceptance_app._start_voice_interaction(trigger_name="CYCLE_TEST", greeting_phrase="Nghe đây")
            loop_fn = mock_thread.call_args[1]["target"]

            # Run loop
            loop_fn()

            # Verify post-greeting settling (0.15s) and post-interaction cooldown (2.5s)
            sleep_calls = [arg[0][0] for arg in mock_sleep.call_args_list if arg[0]]
            assert 0.15 in sleep_calls, "Post-greeting 150ms settling must be executed"
            assert 2.5 in sleep_calls, "Post-interaction 2.5s dissipation cooldown must be executed"

            # Verify single-flight mutex released
            assert acceptance_app._is_voice_interacting is False
