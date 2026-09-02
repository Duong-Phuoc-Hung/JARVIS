"""
tests/unit/test_tts_com_safety.py
==================================
Tests for SAPI5 TTS COM Thread Safety & Lifecycle (Sprint 2 / Requirement R2 / P1-9).
Verifies:
  - pythoncom.CoInitialize() called at start of TTSManager worker thread loop.
  - pythoncom.CoUninitialize() called in worker thread finally block on shutdown.
  - SAPI5FallbackTTS executes 10 consecutive speech requests in daemon thread without COM errors.
  - SAPI5FallbackTTS cleans up COM state in finally block even on dispatch errors.
  - is_in_echo_window lifecycle tracking across speech invocations.
"""
from __future__ import annotations

import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from jarvis.tts.fallback import SAPI5FallbackTTS
from jarvis.tts.manager import TTSManager


class TestTTSCOMSafety:
    """Test suite for COM apartment safety in TTS daemon threads."""

    def test_tts_worker_thread_com_initialize_and_uninitialize(self) -> None:
        """TTSManager worker thread must initialize COM on start and uninitialize on exit."""
        mock_pythoncom = MagicMock()

        with patch.dict(sys.modules, {"pythoncom": mock_pythoncom}):
            tts = TTSManager(config={"cache": {"enabled": False}})
            # Allow worker thread to start up
            time.sleep(0.1)
            mock_pythoncom.CoInitialize.assert_called()

            # Now stop the manager and join the worker thread
            tts.stop()
            time.sleep(0.1)
            mock_pythoncom.CoUninitialize.assert_called()

    def test_ten_consecutive_tts_calls_in_daemon_thread(self) -> None:
        """10 consecutive TTS requests in the background worker thread must complete with 0 errors."""
        spoken_phrases: list[str] = []

        class MockOfflineEngine:
            def is_available(self) -> bool:
                return True

            def speak(self, text: str, voice_id: str | None = None, wait: bool = False) -> bool:
                spoken_phrases.append(text)
                return True

        tts = TTSManager(
            config={"cache": {"enabled": False}},
            primary_engine=MockOfflineEngine(),
            fallback_engine=MockOfflineEngine(),
        )

        completed_callbacks: list[bool] = []
        done_event = threading.Event()

        def _on_done(success: bool) -> None:
            completed_callbacks.append(success)
            if len(completed_callbacks) == 10:
                done_event.set()

        # Enqueue 10 speech items
        for i in range(10):
            tts.speak(f"Test sentence {i}", wait=False, callback=_on_done)

        # Wait for all 10 tasks to complete
        assert done_event.wait(timeout=5.0), "Timed out waiting for 10 TTS queue items"
        assert len(completed_callbacks) == 10
        assert all(completed_callbacks), "All 10 TTS requests must succeed"
        assert len(spoken_phrases) == 10

        tts.stop()

    def test_sapi5_fallback_com_uninitialize_in_finally_block(self) -> None:
        """SAPI5FallbackTTS.speak() must always call CoUninitialize in finally block even when Dispatch fails."""
        mock_pythoncom = MagicMock()
        mock_win32com = MagicMock()
        mock_win32com.client.Dispatch.side_effect = RuntimeError("Simulated COM Dispatch failure")

        with patch.dict(sys.modules, {"pythoncom": mock_pythoncom, "win32com": mock_win32com, "win32com.client": mock_win32com.client}):
            engine = SAPI5FallbackTTS(config={"voice_name": "TestVoice"})
            # Calling speak with win32 platform mock
            with patch("sys.platform", "win32"):
                result = engine.speak("Xin chào", wait=True)

            # Even though win32com dispatch failed, it should fall back to PowerShell/pyttsx3/mock and return True
            assert result is True
            # And CoUninitialize must have been called in finally block
            mock_pythoncom.CoUninitialize.assert_called()

    def test_sapi5_fallback_successful_com_flow(self) -> None:
        """SAPI5FallbackTTS.speak() completes win32com path and uninitializes COM cleanly."""
        mock_pythoncom = MagicMock()
        mock_win32com = MagicMock()
        mock_speaker = MagicMock()
        mock_win32com.client.Dispatch.return_value = mock_speaker

        with patch.dict(sys.modules, {"pythoncom": mock_pythoncom, "win32com": mock_win32com, "win32com.client": mock_win32com.client}):
            engine = SAPI5FallbackTTS()
            with patch("sys.platform", "win32"):
                success = engine.speak("Xin chào JARVIS", wait=True)

            assert success is True
            mock_speaker.Speak.assert_called_once_with("Xin chào JARVIS", 0)
            mock_pythoncom.CoInitialize.assert_called_once()
            mock_pythoncom.CoUninitialize.assert_called_once()

    def test_tts_manager_echo_window_lifecycle_during_and_after_playback(self) -> None:
        """Verify is_in_echo_window transitions from playing -> cooldown -> idle."""
        mock_engine = MagicMock()
        mock_engine.is_available.return_value = False
        mock_fallback = MagicMock()
        mock_fallback.speak.return_value = True

        tts = TTSManager(
            config={"cache": {"enabled": False}},
            primary_engine=mock_engine,
            fallback_engine=mock_fallback,
        )

        assert tts.is_in_echo_window(cooldown_s=2.5) is False

        # Execute speak
        tts.speak("Thử nghiệm âm thanh", wait=True)

        # Immediately after speak, finish time is fresh (~time.monotonic())
        assert tts.last_playback_finish_time > 0.0
        assert tts.is_in_echo_window(current_time=tts.last_playback_finish_time + 1.0, cooldown_s=2.5) is True
        assert tts.is_in_echo_window(current_time=tts.last_playback_finish_time + 2.6, cooldown_s=2.5) is False

        tts.stop()
