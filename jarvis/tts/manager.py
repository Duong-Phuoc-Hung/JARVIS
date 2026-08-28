"""
jarvis/tts/manager.py
=====================
TTSManager: High-level coordinator managing cache hits, online ElevenLabs,
offline SAPI5 fallback, randomized non-repeating welcome greetings pool,
and non-blocking asynchronous audio playback.
"""
from __future__ import annotations

import logging
import queue
import random
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from jarvis.tts.base import BaseTTSEngine
from jarvis.tts.cache import TTSAudioCache
from jarvis.tts.elevenlabs import ElevenLabsTTS
from jarvis.tts.fallback import SAPI5FallbackTTS

log = logging.getLogger("jarvis.tts.manager")


WELCOME_PHRASES: list[str] = [
    "Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS.",
    "Chào mừng Ngài trở lại. Mọi hệ thống đang hoạt động tối ưu.",
    "Xin chào sếp, JARVIS đã sẵn sàng phục vụ.",
    "Welcome home sir. Tất cả các kết nối và cảm biến đã hoàn tất khởi động.",
    "Chào Ngài, tôi đã sẵn sàng phục vụ mọi yêu cầu.",
]


class TTSManager:
    """Thread-safe speech coordinator with caching, randomized greetings, and graceful fallbacks."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        cache_dir: str | Path | None = None,
        primary_engine: BaseTTSEngine | None = None,
        fallback_engine: BaseTTSEngine | None = None,
    ) -> None:
        self.config = config or {}
        cache_enabled = self.config.get("cache", {}).get("enabled", True)
        c_dir = cache_dir or self.config.get("cache", {}).get("dir") or ".cache/jarvis_welcome"

        self.cache = TTSAudioCache(cache_dir=c_dir, enabled=cache_enabled)
        self.primary_engine: BaseTTSEngine = (
            primary_engine or ElevenLabsTTS(self.config.get("elevenlabs", {}))
        )
        self.fallback_engine: BaseTTSEngine = (
            fallback_engine or SAPI5FallbackTTS(self.config.get("fallback", {}))
        )

        self._queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._last_welcome_phrase: str | None = None
        self._start_worker()

    def _start_worker(self) -> None:
        self._worker_thread = threading.Thread(target=self._process_queue, daemon=True, name="TTS-Worker")
        self._worker_thread.start()

    def _process_queue(self) -> None:
        while not self._stop_event.is_set():
            try:
                task = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            text, voice_id, callback, mock_http = task
            try:
                success = self._execute_speak(text, voice_id=voice_id, wait=True, mock_http=mock_http)
                if callback:
                    callback(success)
            except Exception as e:
                log.error("TTS worker failed speaking: %s", e)
                if callback:
                    callback(False)
            finally:
                self._queue.task_done()

    def speak(
        self,
        text: str,
        voice_id: str | None = None,
        wait: bool = False,
        callback: Callable[[bool], None] | None = None,
        mock_http: Any | None = None,
    ) -> bool:
        """
        Public entrypoint. If wait=False, queues speech asynchronously.
        If wait=True, executes immediately and blocks.
        """
        clean_text = text.strip() if text else ""
        if not clean_text:
            return False

        if not wait:
            self._queue.put((clean_text, voice_id, callback, mock_http))
            return True
        return self._execute_speak(clean_text, voice_id=voice_id, wait=True, mock_http=mock_http)

    def _execute_speak(
        self,
        text: str,
        voice_id: str | None = None,
        wait: bool = True,
        mock_http: Any | None = None,
    ) -> bool:
        with self._lock:
            v_id = voice_id or str(getattr(self.primary_engine, "voice_id", "") or "")
            m_id = getattr(self.primary_engine, "model_id", "eleven_multilingual_v2")
            out_fmt = getattr(self.primary_engine, "output_format", "pcm_24000")

            # 1. Check Local Cache Hit
            cached_path = self.cache.get(text, voice_id=v_id, model_id=m_id, output_format=out_fmt)
            if cached_path is not None:
                log.info("Playing synthesized voice from cache: %s", cached_path.name)
                if self.cache.play_wav(cached_path, wait=wait):
                    return True
                log.warning("Cache playback failed, regenerating audio...")

            # 2. Try Online Primary Engine (ElevenLabs)
            if self.primary_engine.is_available() or mock_http is not None:
                try:
                    pcm_bytes = self.primary_engine.synthesize_to_bytes(
                        text,
                        voice_id=v_id,
                        mock_http=mock_http,
                    )
                    if pcm_bytes:
                        # Save to cache atomically
                        saved_path = self.cache.put_pcm(
                            text=text,
                            voice_id=v_id,
                            model_id=m_id,
                            output_format=out_fmt,
                            pcm_bytes=pcm_bytes,
                            sample_rate=self.primary_engine.sample_rate,
                        )
                        return self.cache.play_wav(saved_path, wait=wait)
                except Exception as e:
                    log.warning("Primary TTS engine failed (%s); switching to SAPI5 fallback.", e)

            # 3. Offline Fallback (SAPI5 / pyttsx3)
            log.info("Using offline fallback TTS for: %r", text[:40])
            return self.fallback_engine.speak(text, voice_id=voice_id, wait=wait)

    def get_welcome_phrase(self, explicit_phrase: str | None = None) -> str:
        """
        Selects a welcome phrase. If a pool of phrases is configured or available,
        selects randomly without repeating the immediately previous phrase.
        Thread-safe.
        """
        if explicit_phrase and explicit_phrase.strip():
            return explicit_phrase.strip()

        welcome_cfg = self.config.get("welcome")
        if not isinstance(welcome_cfg, dict) and "tts" in self.config:
            welcome_cfg = self.config.get("tts", {}).get("welcome", {})
        if not isinstance(welcome_cfg, dict):
            welcome_cfg = {}

        # 1. Prioritize phrases list if configured with 1+ items
        phrases = welcome_cfg.get("phrases")
        if isinstance(phrases, list) and len(phrases) > 0:
            candidate_pool = [str(p).strip() for p in phrases if str(p).strip()]
        else:
            # 2. Check if a single phrase string is configured
            single = welcome_cfg.get("phrase")
            if single and isinstance(single, str) and single.strip():
                candidate_pool = [single.strip()]
            else:
                # 3. Fallback to default pool
                candidate_pool = list(WELCOME_PHRASES)

        with self._lock:
            if len(candidate_pool) > 1:
                available = [p for p in candidate_pool if p != self._last_welcome_phrase]
                if not available:
                    available = candidate_pool
            else:
                available = candidate_pool

            chosen = random.choice(available)
            self._last_welcome_phrase = chosen
            return chosen

    def speak_welcome(self, delay_s: float = 1.0, phrase: str | None = None) -> None:
        """Plays a randomized Tony Stark-style welcome phrase in a detached daemon thread."""
        welcome_phrase = self.get_welcome_phrase(explicit_phrase=phrase)

        def _runner():
            if delay_s > 0:
                time.sleep(delay_s)
            self.speak(welcome_phrase, wait=False)

        threading.Thread(target=_runner, daemon=True, name="WelcomeTTS").start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
