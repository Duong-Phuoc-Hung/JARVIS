"""
jarvis/audio/sound_effects.py
==============================
Stark UI Sound Effects — Synthesizes short tones for JARVIS feedback.
No audio files required: generates WAV bytes dynamically using numpy.
"""
from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass
from typing import List, Optional, Tuple

log = logging.getLogger("jarvis.audio.sound_effects")


@dataclass
class SoundConfig:
    enabled: bool = True
    volume: float = 0.3          # 0.0-1.0
    sample_rate: int = 22050
    async_playback: bool = True  # Play in background thread


class SoundEffectsPlayer:
    """
    Generates and plays short synthetic tones using numpy + sounddevice.
    Falls back silently if audio hardware is unavailable.
    """

    def __init__(self, config: Optional[SoundConfig] = None, is_mock: bool = False) -> None:
        self.config = config or SoundConfig()
        self.is_mock = is_mock
        self._lock = threading.Lock()
        log.info("SoundEffectsPlayer initialized (enabled=%s, volume=%.2f)", self.config.enabled, self.config.volume)

    # ------------------------------------------------------------------
    # Public Methods
    # ------------------------------------------------------------------

    def play_activation(self) -> None:
        """3-tone ascending chime: 440 → 550 → 660 Hz (80ms each)."""
        self._play_sequence([(440, 0.08), (550, 0.08), (660, 0.10)], gap_ms=15)

    def play_completion(self) -> None:
        """2-tone descending: 660 → 440 Hz (100ms each)."""
        self._play_sequence([(660, 0.10), (440, 0.10)], gap_ms=15)

    def play_error(self) -> None:
        """Low buzz: 200 Hz, 200ms."""
        self._play_sequence([(200, 0.20)], gap_ms=0)

    def play_thinking(self) -> None:
        """Gentle pulse: 330 Hz, 50ms × 3 with 80ms gaps."""
        self._play_sequence([(330, 0.05), (330, 0.05), (330, 0.05)], gap_ms=80)

    def play_alert(self) -> None:
        """Alert tone: 880 Hz short burst."""
        self._play_sequence([(880, 0.15), (660, 0.10)], gap_ms=20)

    def play_tone(self, frequency_hz: float, duration_s: float) -> None:
        """Play a single custom tone."""
        self._play_sequence([(frequency_hz, duration_s)], gap_ms=0)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _synthesize_tone(self, frequency_hz: float, duration_s: float) -> Optional[object]:
        """Generate a sine wave as numpy array."""
        try:
            import numpy as np  # type: ignore[import]
            sr = self.config.sample_rate
            n = int(sr * duration_s)
            t = np.linspace(0, duration_s, n, endpoint=False)
            # Apply soft fade-in/out to avoid clicks
            tone = np.sin(2 * np.pi * frequency_hz * t).astype(np.float32)
            fade = min(50, n // 4)
            tone[:fade] *= np.linspace(0, 1, fade)
            tone[-fade:] *= np.linspace(1, 0, fade)
            return tone * self.config.volume
        except ImportError:
            return None
        except Exception as exc:
            log.debug("Tone synthesis error: %s", exc)
            return None

    def _play_sequence(self, tones: List[Tuple[float, float]], gap_ms: int = 0) -> None:
        """Play a sequence of (frequency_hz, duration_s) tones."""
        if self.is_mock or not self.config.enabled:
            return

        def _worker() -> None:
            try:
                import sounddevice as sd  # type: ignore[import]
                import numpy as np        # type: ignore[import]
                sr = self.config.sample_rate
                gap_samples = int(sr * gap_ms / 1000)

                for i, (freq, dur) in enumerate(tones):
                    tone = self._synthesize_tone(freq, dur)
                    if tone is None:
                        return
                    sd.play(tone, samplerate=sr, blocking=True)
                    if gap_ms > 0 and i < len(tones) - 1:
                        sd.play(np.zeros(gap_samples, dtype=np.float32), samplerate=sr, blocking=True)
            except ImportError:
                log.debug("sounddevice/numpy not available — sound effects disabled")
            except Exception as exc:
                log.debug("Sound playback error: %s", exc)

        if self.config.async_playback:
            threading.Thread(target=_worker, daemon=True, name="sound-fx").start()
        else:
            _worker()


__all__ = ["SoundEffectsPlayer", "SoundConfig"]
