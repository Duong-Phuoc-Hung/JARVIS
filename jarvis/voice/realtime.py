"""
jarvis/voice/realtime.py
========================
Full-Duplex Real-Time Voice Session Subsystem for JARVIS.
Provides:
  - Conversational State Machine: IDLE, LISTENING, THINKING, SPEAKING.
  - Hardware & Acoustic Barge-In Interruption: Instantly terminates TTS playback
    when user voice activity is detected during system speech.
  - Real-Time Streaming STT integration with live partial HUD feedback.
  - Voice Biometrics Gating: Filters out unauthorized or bystander speech.
  - Fail-closed exception isolation and thread-safe audio dispatching.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from jarvis.audio.dsp import calculate_rms, speech_bandpass_filter
from jarvis.stt.streaming import StreamingConfig, StreamingSTTSession
from jarvis.ui.overlay import OverlayState

logger = logging.getLogger("jarvis.voice.realtime")


class RealtimeVoiceState(str, Enum):
    """Lifecycle states of the real-time voice session."""
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"


@dataclass
class RealtimeSessionConfig:
    """Configuration settings for full-duplex realtime voice session."""
    sample_rate: int = 16000
    enable_barge_in: bool = True
    enable_biometrics: bool = True
    barge_in_threshold: float = 0.025         # RMS threshold to interrupt TTS
    barge_in_confirm_frames: int = 3          # Consecutive voiced frames needed to confirm barge-in
    turn_silence_cutoff_s: float = 0.75       # Trailing silence to close user turn
    step_interval_s: float = 0.25             # Cadence for partial STT hypothesis


class RealtimeVoiceSession:
    """
    Coordinates real-time bi-directional voice interactions with barge-in support,
    acoustic voice biometrics verification, and continuous HUD telemetry.
    """

    def __init__(
        self,
        stt_session_factory: Callable[..., StreamingSTTSession],
        tts_manager: Any | None = None,
        overlay: Any | None = None,
        biometrics_manager: Any | None = None,
        config: RealtimeSessionConfig | None = None,
        on_utterance_complete: Callable[[str], None] | None = None,
        on_state_change: Callable[[RealtimeVoiceState], None] | None = None,
        on_barge_in: Callable[[], None] | None = None,
    ) -> None:
        self.stt_session_factory = stt_session_factory
        self.tts_manager = tts_manager
        self.overlay = overlay
        self.biometrics_manager = biometrics_manager
        self.config = config or RealtimeSessionConfig()
        self.on_utterance_complete = on_utterance_complete
        self.on_state_change = on_state_change
        self.on_barge_in = on_barge_in

        self._lock = threading.RLock()
        self._state = RealtimeVoiceState.IDLE
        self._is_running = False

        # Barge-in tracking counters
        self._barge_in_consecutive = 0
        self._active_stt_session: StreamingSTTSession | None = None
        self._last_user_audio_buffer: list[float] = []

    @property
    def state(self) -> RealtimeVoiceState:
        """Current operational state of the session."""
        with self._lock:
            return self._state

    def start(self) -> None:
        """Starts the realtime session and begins listening."""
        with self._lock:
            self._is_running = True
            self._transition_to(RealtimeVoiceState.LISTENING)
            self._init_stt_session()

    def stop(self) -> None:
        """Stops the realtime session and cancels active STT."""
        with self._lock:
            self._is_running = False
            if self._active_stt_session:
                self._active_stt_session.cancel()
                self._active_stt_session = None
            self._transition_to(RealtimeVoiceState.IDLE)

    def _transition_to(self, new_state: RealtimeVoiceState) -> None:
        """Updates internal state and notifies listeners and overlay HUD."""
        if self._state == new_state:
            return
        logger.info("RealtimeVoiceSession state change: %s -> %s", self._state.value, new_state.value)
        self._state = new_state

        if self.overlay:
            try:
                if new_state == RealtimeVoiceState.LISTENING:
                    self.overlay.show_listening("🎤 Đang lắng nghe...")
                elif new_state == RealtimeVoiceState.THINKING:
                    self.overlay.show_thinking()
            except Exception as e:
                logger.warning("Overlay HUD state update failed: %s", e)

        if self.on_state_change:
            try:
                self.on_state_change(new_state)
            except Exception as e:
                logger.error("Error in on_state_change callback: %s", e)

    def _init_stt_session(self) -> None:
        """Initializes a new StreamingSTTSession."""
        if self._active_stt_session:
            self._active_stt_session.cancel()

        stt_cfg = StreamingConfig(
            sample_rate=self.config.sample_rate,
            step_interval_s=self.config.step_interval_s,
            silence_cutoff_s=self.config.turn_silence_cutoff_s,
        )
        self._last_user_audio_buffer.clear()
        self._active_stt_session = self.stt_session_factory(
            on_partial=self._handle_stt_partial,
            on_final=self._handle_stt_final,
            on_speech_start=self._handle_stt_speech_start,
            override_config=stt_cfg,
        )

    def _handle_stt_speech_start(self) -> None:
        """Invoked when user speech begins."""
        logger.debug("Speech activity detected by streaming session.")

    def _handle_stt_partial(self, partial_text: str) -> None:
        """Invoked with streaming intermediate partial tokens."""
        if self.overlay and self._state == RealtimeVoiceState.LISTENING:
            try:
                self.overlay.show_listening(f"Đang nghe: {partial_text}")
            except Exception as e:
                logger.debug("Failed updating overlay partial text: %s", e)

    def _handle_stt_final(self, final_text: str) -> None:
        """Invoked when an utterance concludes upon silence cutoff."""
        clean_text = final_text.strip()
        logger.info("Utterance concluded with final text: '%s'", clean_text)

        if not clean_text:
            # Empty utterance: return to listening
            self._init_stt_session()
            return

        with self._lock:
            self._transition_to(RealtimeVoiceState.THINKING)

            # Voice Biometrics verification check
            if self.config.enable_biometrics and self.biometrics_manager:
                if self.biometrics_manager.enrolled_speakers and self._last_user_audio_buffer:
                    user_audio_arr = np.array(self._last_user_audio_buffer, dtype=np.float32)
                    verified, speaker, score = self.biometrics_manager.verify_speaker(user_audio_arr)
                    if not verified:
                        logger.warning(
                            "Speaker biometrics rejected utterance: speaker=%s, score=%.3f. Ignoring.",
                            speaker, score,
                        )
                        if self.overlay:
                            self.overlay.show_response(
                                "(từ chối sinh trắc học)",
                                "Không nhận diện được giọng nói của chủ nhân.",
                            )
                        self._transition_to(RealtimeVoiceState.LISTENING)
                        self._init_stt_session()
                        return
                    logger.info("Speaker '%s' verified by biometrics with score %.3f", speaker, score)

            # Dispatch final utterance
            if self.on_utterance_complete:
                try:
                    self.on_utterance_complete(clean_text)
                except Exception as e:
                    logger.error("Error in on_utterance_complete callback: %s", e)

            # Re-arm STT for subsequent turns
            self._init_stt_session()

    def set_speaking(self, is_speaking: bool) -> None:
        """Call when TTS starts or stops speaking."""
        with self._lock:
            if is_speaking:
                self._transition_to(RealtimeVoiceState.SPEAKING)
            else:
                if self._state == RealtimeVoiceState.SPEAKING:
                    self._transition_to(RealtimeVoiceState.LISTENING)

    def feed_audio(self, chunk: np.ndarray | bytes) -> None:
        """
        Feeds microphone audio chunks into the realtime session.

        Handles:
          - Barge-In during TTS SPEAKING state.
          - Streaming STT ingestion during LISTENING state.
        """
        with self._lock:
            if not self._is_running:
                return

            if isinstance(chunk, bytes):
                from jarvis.stt.engine import audio_to_float32
                arr = audio_to_float32(chunk, sample_rate=self.config.sample_rate)
            else:
                arr = np.nan_to_num(chunk.flatten(), nan=0.0).astype(np.float32)

            if arr.size == 0:
                return

            # Case 1: System is speaking (TTS active) -> Monitor for Barge-In
            if self._state == RealtimeVoiceState.SPEAKING:
                if self.config.enable_barge_in:
                    filtered = speech_bandpass_filter(arr, sample_rate=self.config.sample_rate)
                    rms = calculate_rms(filtered)
                    if rms >= self.config.barge_in_threshold:
                        self._barge_in_consecutive += 1
                        if self._barge_in_consecutive >= self.config.barge_in_confirm_frames:
                            logger.info("Barge-in voice interrupt confirmed (RMS=%.4f). Interrupting TTS!", rms)
                            self._barge_in_consecutive = 0
                            # Stop TTS playback immediately
                            if self.tts_manager and hasattr(self.tts_manager, "interrupt"):
                                self.tts_manager.interrupt()

                            self._transition_to(RealtimeVoiceState.LISTENING)
                            self._init_stt_session()

                            if self.on_barge_in:
                                try:
                                    self.on_barge_in()
                                except Exception as e:
                                    logger.error("Error in on_barge_in callback: %s", e)
                    else:
                        self._barge_in_consecutive = 0
                return

            # Case 2: System is listening -> Feed audio to Streaming STT
            if self._state == RealtimeVoiceState.LISTENING and self._active_stt_session:
                self._last_user_audio_buffer.extend(arr.tolist())
                # Cap user audio buffer at 10s to prevent unbounded memory growth
                max_buffer_samples = int(self.config.sample_rate * 10.0)
                if len(self._last_user_audio_buffer) > max_buffer_samples:
                    self._last_user_audio_buffer = self._last_user_audio_buffer[-max_buffer_samples:]

                self._active_stt_session.feed(arr)
