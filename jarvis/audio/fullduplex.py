"""
jarvis/audio/fullduplex.py
==========================
Full-Duplex Barge-in Voice Manager.
Monitors microphone while TTS audio is playing, allowing user to
interrupt JARVIS mid-speech with a new command.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, Optional

log = logging.getLogger("jarvis.audio.fullduplex")


class VoiceState(Enum):
    IDLE = auto()
    LISTENING = auto()
    SPEAKING = auto()        # JARVIS is playing TTS
    INTERRUPTED = auto()     # User barged in


@dataclass
class BargeInConfig:
    vad_threshold: float = 0.02     # Energy threshold during playback
    confirmation_frames: int = 3    # Consecutive speech frames to trigger barge-in
    enabled: bool = True
    cooldown_s: float = 0.5         # Seconds after barge-in before re-listening


class FullDuplexVoiceManager:
    """
    Manages full-duplex voice: detects user speech while JARVIS is speaking,
    and interrupts TTS playback immediately (barge-in).
    """

    def __init__(
        self,
        config: Optional[BargeInConfig] = None,
        is_mock: bool = False,
    ) -> None:
        self.config = config or BargeInConfig()
        self.is_mock = is_mock
        self._state = VoiceState.IDLE
        self._lock = threading.RLock()
        self._playback_stop_event = threading.Event()
        self._barge_in_thread: Optional[threading.Thread] = None
        self._on_barge_in: Optional[Callable[[], None]] = None
        log.info(
            "FullDuplexVoiceManager initialized (enabled=%s, threshold=%.3f)",
            self.config.enabled,
            self.config.vad_threshold,
        )

    @property
    def state(self) -> VoiceState:
        with self._lock:
            return self._state

    def start_barge_in_detection(
        self,
        playback_stop_fn: Optional[Callable[[], None]] = None,
        on_barge_in: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        Start monitoring microphone for barge-in during TTS playback.

        Args:
            playback_stop_fn: Callable to stop current TTS playback
            on_barge_in: Optional callback fired when barge-in is detected
        """
        if self.is_mock or not self.config.enabled:
            return

        with self._lock:
            if self._state == VoiceState.SPEAKING:
                log.debug("Barge-in detection already active")
                return
            self._state = VoiceState.SPEAKING
            self._playback_stop_event.clear()
            self._on_barge_in = on_barge_in

        def _detect() -> None:
            consecutive = 0
            try:
                import sounddevice as sd  # type: ignore[import]
                import numpy as np        # type: ignore[import]
                sr = 16000
                frame_ms = 30
                chunk = int(sr * frame_ms / 1000)

                with sd.InputStream(samplerate=sr, channels=1, dtype="int16") as stream:
                    while not self._playback_stop_event.is_set():
                        data, _ = stream.read(chunk)
                        rms = float(np.sqrt(np.mean(data.astype(np.float32) ** 2))) / 32768.0
                        if rms > self.config.vad_threshold:
                            consecutive += 1
                            if consecutive >= self.config.confirmation_frames:
                                log.info("Barge-in detected (rms=%.4f)", rms)
                                if playback_stop_fn:
                                    playback_stop_fn()
                                with self._lock:
                                    self._state = VoiceState.INTERRUPTED
                                if on_barge_in:
                                    on_barge_in()
                                break
                        else:
                            consecutive = max(0, consecutive - 1)
            except ImportError:
                log.debug("sounddevice/numpy not available — barge-in disabled")
            except Exception as exc:
                log.warning("Barge-in detection error: %s", exc)

        self._barge_in_thread = threading.Thread(target=_detect, daemon=True, name="barge-in")
        self._barge_in_thread.start()

    def stop_current_speech(self) -> None:
        """Signal that TTS playback has ended (natural or interrupted)."""
        self._playback_stop_event.set()
        with self._lock:
            if self._state in (VoiceState.SPEAKING, VoiceState.INTERRUPTED):
                self._state = VoiceState.IDLE
        if self._barge_in_thread and self._barge_in_thread.is_alive():
            self._barge_in_thread.join(timeout=1.0)

    def set_state(self, state: VoiceState) -> None:
        with self._lock:
            old = self._state
            self._state = state
            log.debug("VoiceState: %s -> %s", old.name, state.name)

    def is_speaking(self) -> bool:
        return self.state == VoiceState.SPEAKING

    def is_interrupted(self) -> bool:
        return self.state == VoiceState.INTERRUPTED


__all__ = ["FullDuplexVoiceManager", "BargeInConfig", "VoiceState"]
