"""
jarvis/tts/edge.py
==================
Edge TTS engine — Microsoft Neural voices via edge-tts (no API key required).
Supports Vietnamese: vi-VN-HoaiMyNeural (female) / vi-VN-NamMinhNeural (male).
"""
from __future__ import annotations

import asyncio
import io
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Any

from jarvis.tts.base import BaseTTSEngine, TTSError

log = logging.getLogger("jarvis.tts.edge")

_DEFAULT_VOICE = "vi-VN-HoaiMyNeural"
_DEFAULT_RATE = "+0%"


def _run_async(coro) -> Any:
    """Run async coroutine from sync context, thread-safe."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(asyncio.run, coro)
            return fut.result(timeout=20)
    return asyncio.run(coro)


def _mp3_to_pcm(mp3_bytes: bytes, target_sr: int = 24000) -> bytes:
    """Decode MP3 bytes to 16-bit mono PCM bytes."""
    if not mp3_bytes:
        return b""
    # Method 1: soundfile (fast libsndfile)
    try:
        import soundfile as sf
        data, sr = sf.read(io.BytesIO(mp3_bytes), dtype="int16")
        if data.ndim > 1:
            data = data[:, 0]
        if sr != target_sr:
            import numpy as np
            from scipy import signal
            num_samples = int(len(data) * target_sr / sr)
            data = signal.resample(data.astype(np.float32), num_samples).astype(np.int16)
        return data.tobytes()
    except Exception as e:
        log.debug("soundfile MP3 decode failed (%s), trying PyAV", e)

    # Method 2: av (PyAV fallback)
    try:
        import av
        container = av.open(io.BytesIO(mp3_bytes))
        resampler = av.AudioResampler(format="s16", layout="mono", rate=target_sr)
        chunks = []
        for frame in container.decode(audio=0):
            for r_frame in resampler.resample(frame):
                chunks.append(bytes(r_frame.planes[0]))
        for r_frame in resampler.resample(None):
            chunks.append(bytes(r_frame.planes[0]))
        return b"".join(chunks)
    except Exception as e:
        log.debug("PyAV MP3 decode failed (%s)", e)

    raise TTSError("Unable to decode Edge TTS audio to PCM; no usable decoder")


class EdgeTTS(BaseTTSEngine):
    """Microsoft Edge Neural TTS — free, no API key, Vietnamese support."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.voice = self.config.get("voice", _DEFAULT_VOICE)
        self.rate = self.config.get("rate", _DEFAULT_RATE)
        self._available: bool | None = None
        self._lock = threading.Lock()

    @property
    def engine_name(self) -> str:
        return "edge_tts"

    @property
    def voice_id(self) -> str:
        return self.voice

    @property
    def model_id(self) -> str:
        return "edge_neural"

    @property
    def output_format(self) -> str:
        return "pcm_24000"

    def is_available(self) -> bool:
        if self._available is None:
            try:
                import edge_tts  # noqa: F401
                self._available = True
            except ImportError:
                self._available = False
        return self._available

    def synthesize_to_bytes(self, text: str, voice_id: str | None = None, **kwargs) -> bytes:
        """Synthesize text and return decoded 16-bit mono PCM bytes."""
        if not self.is_available():
            raise TTSError("edge-tts not installed — pip install edge-tts")
        import edge_tts

        voice = voice_id or self.voice

        async def _synth(v: str) -> bytes:
            communicate = edge_tts.Communicate(text, v, rate=self.rate)
            buf = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
            data = buf.getvalue()
            if not data:
                raise TTSError("EdgeTTS stream produced empty audio data")
            return data

        try:
            mp3_bytes = _run_async(_synth(voice))
        except Exception as first_err:
            fallback_v = "vi-VN-NamMinhNeural" if voice != "vi-VN-NamMinhNeural" else "vi-VN-HoaiMyNeural"
            log.warning("EdgeTTS primary voice %s failed (%s), retrying with %s...", voice, first_err, fallback_v)
            try:
                mp3_bytes = _run_async(_synth(fallback_v))
            except Exception as final_err:
                raise TTSError(f"EdgeTTS synthesis failed on all attempts: {final_err}") from final_err

        return _mp3_to_pcm(mp3_bytes, target_sr=self.sample_rate)

    def speak(self, text: str, voice_id: str | None = None, wait: bool = False, **kwargs) -> bool:
        """Synthesize and play via sounddevice (PCM) or winsound fallback."""
        if not self.is_available():
            return False
        try:
            pcm_bytes = self.synthesize_to_bytes(text, voice_id=voice_id)
            if not pcm_bytes:
                return False
            return self._play(pcm_bytes, wait=wait)
        except Exception as e:
            log.warning("EdgeTTS speak failed: %s", e)
            return False

    def _play(self, pcm_bytes: bytes, wait: bool) -> bool:
        """Play 16-bit PCM bytes via sounddevice with winsound fallback."""
        if not pcm_bytes:
            return False
        # Method 1: sounddevice (high-fidelity streaming)
        try:
            import numpy as np
            import sounddevice as sd
            samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            if wait:
                sd.play(samples, samplerate=self.sample_rate)
                sd.wait()
            else:
                threading.Thread(
                    target=lambda: (sd.play(samples, samplerate=self.sample_rate), sd.wait()),
                    daemon=True,
                ).start()
            return True
        except Exception as e:
            log.debug("EdgeTTS sounddevice playback failed: %s", e)

        # Method 2: winsound via temporary WAV file
        if sys.platform == "win32":
            try:
                import tempfile
                import wave
                import winsound
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    tmp = f.name
                with wave.open(tmp, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.sample_rate)
                    wf.writeframes(pcm_bytes)
                flags = winsound.SND_FILENAME
                if not wait:
                    flags |= winsound.SND_ASYNC
                winsound.PlaySound(tmp, flags)
                threading.Thread(target=lambda: (time.sleep(15), Path(tmp).unlink(missing_ok=True)), daemon=True).start()
                return True
            except Exception as e:
                log.warning("EdgeTTS winsound playback failed: %s", e)

        return False
