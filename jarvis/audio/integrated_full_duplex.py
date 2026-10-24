"""
jarvis/audio/integrated_full_duplex.py
======================================
Argon Continuous Conversational Full-Duplex Integration for Kokoro-82M & Piper TTS.
Engineered for Argon Sovereign v5.8.0.

Provides an end-to-end full-duplex conversational coordinator:
  1. Smooth Ducking Pipeline: Dynamically scales outgoing TTS audio frames by ducking_gain.
  2. Tri-State Barge-In Handling: Differentiates ambient typing, backchannels, and hard interrupts.
  3. Fail-Closed Speech Buffer Flushing: Instantly empties pending speech queues upon hard barge-in.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from typing import Any

import numpy as np

from jarvis.audio.fullduplex import (
    ArgonFullDuplexAudioController,
    BargeInDecision,
    TriStateBargeInClassifier,
)

logger = logging.getLogger("jarvis.audio.integrated_full_duplex")


class ArgonKokoroFullDuplexController:
    """
    End-to-end coordinator integrating TTS playback with real-time mic monitoring and ducking.
    """

    def __init__(
        self,
        audio_controller: ArgonFullDuplexAudioController | None = None,
        tts_synthesizer_fn: Callable[[str], np.ndarray] | None = None,
        playback_sink_fn: Callable[[np.ndarray], None] | None = None,
    ) -> None:
        self.audio_controller = audio_controller or ArgonFullDuplexAudioController()
        self.tts_synthesizer_fn = tts_synthesizer_fn
        self.playback_sink_fn = playback_sink_fn

        self._lock = threading.RLock()
        self._speech_queue: queue.Queue[tuple[str, np.ndarray]] = queue.Queue()
        self._is_active: bool = False
        self._worker_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Connect hard barge-in callback to flush speech queue
        self.audio_controller.on_hard_barge_in = self._on_hard_interrupt

    def _on_hard_interrupt(self) -> None:
        """Flushes speech queue and halts ongoing playback on hard barge-in."""
        with self._lock:
            # Drain queue
            while not self._speech_queue.empty():
                try:
                    self._speech_queue.get_nowait()
                except queue.Empty:
                    break
        logger.info("Speech queue flushed due to HARD_BARGE_IN.")

    def start_session(self) -> None:
        """Starts background playback worker."""
        with self._lock:
            if self._is_active:
                return
            self._is_active = True
            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._playback_loop,
                daemon=True,
                name="argon-kokoro-fullduplex",
            )
            self._worker_thread.start()
            logger.debug("ArgonKokoroFullDuplexController session started.")

    def stop_session(self) -> None:
        """Stops background playback worker."""
        with self._lock:
            self._is_active = False
            self._stop_event.set()
            self._on_hard_interrupt()
            self.audio_controller.reset()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
        logger.debug("ArgonKokoroFullDuplexController session stopped.")

    def enqueue_speech(self, text: str, audio_pcm: np.ndarray | None = None) -> None:
        """
        Enqueues text or synthesized PCM for playback.
        If audio_pcm is not provided and synthesizer is available, synthesizes immediately.
        """
        pcm = audio_pcm
        if pcm is None and self.tts_synthesizer_fn is not None:
            try:
                pcm = self.tts_synthesizer_fn(text)
            except Exception as exc:
                logger.error("TTS synthesis failed for '%s': %s", text, exc)
                return

        if pcm is None:
            # Generate simulated speech frame if no engine provided
            pcm = np.zeros(16000, dtype=np.float32)

        with self._lock:
            self._speech_queue.put((text, pcm))
            logger.debug("Enqueued speech for '%s' (samples=%d)", text, len(pcm))

    def feed_mic_frame(
        self,
        mic_pcm: np.ndarray,
        is_voice_detected: bool,
        transcript: str | None = None,
    ) -> BargeInDecision:
        """
        Feeds microphone frame into the full-duplex controller.
        Returns the Tri-State barge-in decision.
        """
        return self.audio_controller.evaluate_incoming_frame(
            mic_frame=mic_pcm,
            is_voice_detected=is_voice_detected,
            transcript=transcript,
        )

    def _playback_loop(self) -> None:
        """Background thread consuming and playing speech frames with dynamic ducking."""
        while not self._stop_event.is_set():
            try:
                text, pcm = self._speech_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            self.audio_controller.on_playback_started(session_id=f"tts_{hash(text)}")

            # Chunk audio into 50ms frames for fine-grained ducking application
            chunk_size = 800  # 50ms at 16kHz
            n_samples = len(pcm)
            offset = 0

            while offset < n_samples and not self._stop_event.is_set():
                if not self.audio_controller.is_tts_playing:
                    # Aborted mid-sentence by hard barge-in
                    break

                chunk = pcm[offset : offset + chunk_size]
                gain = self.audio_controller.ducking_gain
                ducked_chunk = chunk * gain

                if self.playback_sink_fn is not None:
                    try:
                        self.playback_sink_fn(ducked_chunk)
                    except Exception as exc:
                        logger.warning("Playback sink failed: %s", exc)

                offset += chunk_size
                time.sleep(0.01)  # Simulate real-time frame progression

            self.audio_controller.on_playback_finished()
