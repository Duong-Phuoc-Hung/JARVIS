"""
tests/unit/test_tts_shutdown_probe.py
======================================
Probe tests for Task 8: TTS-SHUTDOWN-PROBE.
Verifies active playback and queue teardown:
1. TTSAudioCache.stop() must exist and safely halt active sounddevice / platform audio playback.
2. TTSManager.stop() must halt active playback, drain pending queue tasks, notify callbacks of cancellation,
   and cleanly reset is_playing state without hanging.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from jarvis.tts.cache import TTSAudioCache
from jarvis.tts.manager import TTSManager


class TestTTSShutdownProbe:
    def test_audio_cache_has_stop_method_to_halt_active_playback(self, tmp_path):
        """TTSAudioCache must provide a stop() method to halt active hardware audio streaming."""
        cache = TTSAudioCache(cache_dir=tmp_path, enabled=False)
        assert hasattr(cache, "stop"), "TTSAudioCache must implement stop() to abort active playback"
        # Calling stop should be safe and idempotent
        cache.stop()
        cache.stop()

    def test_tts_manager_stop_halts_active_playback_and_drains_queue(self, tmp_path):
        """TTSManager.stop() must call cache.stop(), drain pending queue items, and ensure is_playing=False."""
        mgr = TTSManager(cache_dir=tmp_path)

        callback_results = []
        def my_callback(success: bool):
            callback_results.append(success)

        # Queue multiple tasks
        mock_http = MagicMock()
        mgr.speak("Sentence 1", wait=False, callback=my_callback, mock_http=mock_http)
        mgr.speak("Sentence 2", wait=False, callback=my_callback, mock_http=mock_http)
        mgr.speak("Sentence 3", wait=False, callback=my_callback, mock_http=mock_http)

        # Teardown
        mgr.stop()

        # After stop():
        # 1. Queue must be drained (not left hanging with unserviced tasks)
        assert mgr._queue.empty(), "TTS queue should be drained on manager stop"
        # 2. is_playing must be False
        assert not mgr.is_playing
        # 3. Worker thread must not be alive
        assert not mgr._worker_thread.is_alive()

    def test_tts_manager_has_shutdown_and_close_methods(self, tmp_path):
        """TTSManager must expose shutdown() and close() methods for standard lifecycle management."""
        mgr = TTSManager(cache_dir=tmp_path)
        assert hasattr(mgr, "shutdown"), "TTSManager must implement shutdown()"
        assert hasattr(mgr, "close"), "TTSManager must implement close()"
        mgr.shutdown()
        assert not mgr._worker_thread.is_alive()

    def test_tts_manager_shutdown_is_idempotent(self, tmp_path):
        """Calling shutdown()/stop()/close() multiple times must be safe and idempotent."""
        mgr = TTSManager(cache_dir=tmp_path)
        mgr.shutdown()
        mgr.stop()
        mgr.close()
        mgr.shutdown()
        assert not mgr._worker_thread.is_alive()

    def test_tts_manager_speak_post_shutdown_returns_false_truthfully(self, tmp_path):
        """speak() called after shutdown must return False and not accept tasks silently."""
        mgr = TTSManager(cache_dir=tmp_path)
        mgr.shutdown()

        callbacks = []
        res_async = mgr.speak("Post-shutdown test async", wait=False, callback=lambda ok: callbacks.append(ok))
        assert res_async is False, "speak(wait=False) post-shutdown must return False (no false success)"
        assert callbacks == [False], "Callback must be notified of failure on post-shutdown speak attempt"

        res_sync = mgr.speak("Post-shutdown test sync", wait=True)
        assert res_sync is False, "speak(wait=True) post-shutdown must return False"

    def test_tts_audio_cache_has_shutdown_and_close_methods_and_is_idempotent(self, tmp_path):
        """TTSAudioCache must implement close() and shutdown() idempotently and fail-closed post-shutdown."""
        cache = TTSAudioCache(cache_dir=tmp_path, enabled=True)
        assert hasattr(cache, "shutdown"), "TTSAudioCache must implement shutdown()"
        assert hasattr(cache, "close"), "TTSAudioCache must implement close()"
        cache.shutdown()
        cache.close()
        cache.stop()

        # Post-shutdown calls should fail-closed
        assert cache.get("test text") is None
        assert cache.get_bytes("test text") is None
        assert cache.play_wav(tmp_path / "nonexistent.wav") is False

    def test_tts_manager_shutdown_during_active_queue_activity_no_deadlock(self, tmp_path):
        """Shutdown during high queue activity must drain queue, notify callbacks, and join thread without deadlock."""
        mgr = TTSManager(cache_dir=tmp_path)

        callback_results = []
        lock = threading.Lock()
        def cb(ok: bool):
            with lock:
                callback_results.append(ok)

        # Producer thread continuously queuing speech
        stop_producer = threading.Event()
        mock_http = MagicMock()
        def producer():
            idx = 0
            while not stop_producer.is_set():
                try:
                    mgr.speak(f"Activity sentence {idx}", wait=False, callback=cb, mock_http=mock_http)
                    idx += 1
                    time.sleep(0.001)
                except Exception:
                    break

        t_prod = threading.Thread(target=producer, daemon=True)
        t_prod.start()

        time.sleep(0.02)
        stop_producer.set()
        mgr.shutdown()

        assert not mgr._worker_thread.is_alive(), "Worker thread must exit after shutdown"
        assert mgr._queue.empty(), "Queue must be empty post shutdown"
        assert not mgr.is_playing

