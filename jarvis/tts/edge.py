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
import threading
from typing import Any

from jarvis.tts.base import BaseTTSEngine, TTSError

log = logging.getLogger("jarvis.tts.edge")

_DEFAULT_VOICE = "vi-VN-HoaiMyNeural"
_DEFAULT_RATE = "+0%"


def _run_async(coro) -> Any:
    """Run async coroutine from sync context, thread-safe."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already in async context (shouldn't happen here, but safe)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(asyncio.run, coro)
                return fut.result(timeout=15)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


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

    def is_available(self) -> bool:
        if self._available is None:
            try:
                import edge_tts  # noqa: F401
                self._available = True
            except ImportError:
                self._available = False
        return self._available

    def synthesize_to_bytes(self, text: str, voice_id: str | None = None, **kwargs) -> bytes:
        """Synthesize to MP3 bytes (edge-tts native format)."""
        if not self.is_available():
            raise TTSError("edge-tts not installed — pip install edge-tts")
        import edge_tts

        voice = voice_id or self.voice

        async def _synth() -> bytes:
            communicate = edge_tts.Communicate(text, voice, rate=self.rate)
            buf = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
            return buf.getvalue()

        return _run_async(_synth())

    def speak(self, text: str, voice_id: str | None = None, wait: bool = False, **kwargs) -> bool:
        """Synthesize and play via sounddevice (PCM) or pygame fallback."""
        if not self.is_available():
            return False
        try:
            mp3_bytes = self.synthesize_to_bytes(text, voice_id=voice_id)
            if not mp3_bytes:
                return False
            return self._play(mp3_bytes, wait=wait)
        except Exception as e:
            log.warning("EdgeTTS speak failed: %s", e)
            return False

    def _play(self, mp3_bytes: bytes, wait: bool) -> bool:
        """Play MP3 bytes. Tries sounddevice→pydub, then pygame, then temp file."""
        # Method 1: pydub + sounddevice (best quality, no temp file)
        try:
            from pydub import AudioSegment
            import sounddevice as sd
            import numpy as np
            seg = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
            seg = seg.set_channels(1).set_frame_rate(24000)
            samples = np.array(seg.get_array_of_samples(), dtype=np.float32) / 32768.0
            if wait:
                sd.play(samples, samplerate=24000)
                sd.wait()
            else:
                threading.Thread(target=lambda: (sd.play(samples, samplerate=24000), sd.wait()), daemon=True).start()
            return True
        except Exception:
            pass

        # Method 2: pygame
        try:
            import pygame
            pygame.mixer.init()
            sound = pygame.mixer.Sound(io.BytesIO(mp3_bytes))
            sound.play()
            if wait:
                while pygame.mixer.get_busy():
                    pygame.time.wait(50)
            return True
        except Exception:
            pass

        # Method 3: write temp file + playsound
        try:
            import tempfile, os, subprocess
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(mp3_bytes)
                tmp = f.name
            cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                   f"(New-Object Media.SoundPlayer).PlaySync()"]
            # Use Windows Media Player via PowerShell for MP3
            ps = (
                f"Add-Type -AssemblyName presentationCore;"
                f"$p=New-Object System.Windows.Media.MediaPlayer;"
                f"$p.Open([uri]'{tmp}');$p.Play();"
                f"Start-Sleep -Milliseconds 100;"
                f"while($p.Position -lt $p.NaturalDuration.TimeSpan){{Start-Sleep -Milliseconds 200}};"
            )
            kw: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                        "stderr": subprocess.DEVNULL}
            if hasattr(subprocess, "CREATE_NO_WINDOW"):
                kw["creationflags"] = subprocess.CREATE_NO_WINDOW
            proc = subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps], **kw)
            if wait:
                proc.wait(timeout=15)
            else:
                threading.Thread(target=lambda: proc.wait(), daemon=True).start()
            # ponytail: cleanup temp file after playback
            threading.Thread(target=lambda: (proc.wait(), os.unlink(tmp)), daemon=True).start()
            return True
        except Exception as e:
            log.warning("EdgeTTS all playback methods failed: %s", e)
            return False
