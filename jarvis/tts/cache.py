"""
jarvis/tts/cache.py
===================
Local TTS Audio Cache and High-Fidelity Audio Playback Subsystem.
Implements SHA-256 disk caching under .cache/jarvis_welcome/ and zero-latency audio playback.
"""
from __future__ import annotations

import hashlib
import logging
import os
import sys
import wave
from pathlib import Path

import numpy as np

log = logging.getLogger("jarvis.tts.cache")


class TTSAudioCache:
    """Manages persistent SHA-256 WAV cache and audio playback."""

    def __init__(self, cache_dir: str | Path | None = None, enabled: bool = True) -> None:
        if cache_dir:
            self.cache_dir = Path(cache_dir).expanduser().resolve()
            if not self.cache_dir.name == "jarvis_welcome" and not (self.cache_dir / "jarvis_welcome").exists():
                self.cache_dir = self.cache_dir / "jarvis_welcome"
        else:
            import os as _os, sys as _sys
            _appdata = _os.environ.get("LOCALAPPDATA") or _os.environ.get("APPDATA")
            _base = Path(_appdata) / "JARVIS" if (_appdata and _sys.platform == "win32") else Path.home() / ".jarvis"
            self.cache_dir = (_base / "cache" / "tts").resolve()

        self.enabled = enabled
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def compute_key(
        self,
        text: str,
        voice_id: str = "",
        model_id: str = "eleven_multilingual_v2",
        output_format: str = "pcm_24000",
    ) -> str:
        """
        Computes 24-character SHA-256 hex digest matching legacy schema:
        key = f"{text}|{voice_id}|{model_id}|{output_format}"
        """
        clean_text = text.strip()
        raw = f"{clean_text}|{voice_id}|{model_id}|{output_format}".encode()
        return hashlib.sha256(raw).hexdigest()[:24]

    def get_cache_path(
        self,
        text: str,
        voice_id: str = "",
        model_id: str = "eleven_multilingual_v2",
        output_format: str = "pcm_24000",
    ) -> Path:
        digest = self.compute_key(text, voice_id, model_id, output_format)
        return self.cache_dir / f"{digest}.wav"

    def get(
        self,
        text: str,
        voice_id: str = "",
        model_id: str = "eleven_multilingual_v2",
        output_format: str = "pcm_24000",
    ) -> Path | None:
        """Returns Path to valid cached WAV file if exists and uncorrupted, otherwise None."""
        if not self.enabled:
            return None
        path = self.get_cache_path(text, voice_id, model_id, output_format)
        if not path.is_file():
            return None
        # Corruption guard: Check minimum size for valid RIFF WAV header (44 bytes)
        try:
            size = path.stat().st_size
            if size < 44:
                log.warning("Corrupt cached WAV detected (%d bytes): %s. Invalidating.", size, path)
                path.unlink(missing_ok=True)
                return None
            return path
        except OSError as e:
            log.warning("Failed to access cache file %s: %s", path, e)
            return None

    def get_bytes(
        self,
        text: str,
        voice_id: str = "",
        model_id: str = "eleven_multilingual_v2",
        output_format: str = "pcm_24000",
    ) -> bytes | None:
        """Returns raw bytes of cached WAV if valid."""
        if not self.enabled:
            return None
        path = self.get_cache_path(text, voice_id, model_id, output_format)
        if not path.is_file():
            return None
        try:
            size = path.stat().st_size
            if size < 44:
                path.unlink(missing_ok=True)
                return None
            return path.read_bytes()
        except Exception:
            return None

    def put_pcm(
        self,
        text: str,
        voice_id: str,
        model_id: str,
        output_format: str,
        pcm_bytes: bytes,
        sample_rate: int = 24000,
    ) -> Path:
        """Atomically saves raw 16-bit mono PCM bytes as a standard WAV file."""
        if not self.enabled:
            return self.get_cache_path(text, voice_id, model_id, output_format)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.get_cache_path(text, voice_id, model_id, output_format)

        import threading
        import time
        thread_id = threading.get_ident()
        ts = time.time_ns()
        tmp_path = path.parent / f".tmp_{path.stem}_{thread_id}_{ts}.wav"
        try:
            with wave.open(str(tmp_path), "wb") as wf:
                wf.setnchannels(1)       # Mono
                wf.setsampwidth(2)      # 16-bit
                wf.setframerate(sample_rate)
                wf.writeframes(pcm_bytes)
            try:
                tmp_path.replace(path)
            except (PermissionError, FileExistsError, OSError):
                # On Windows, if another thread replaced it simultaneously, verify valid target exists
                if path.is_file() and path.stat().st_size >= 44:
                    if tmp_path.is_file():
                        try:
                            tmp_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                    return path
                time.sleep(0.01)
                tmp_path.replace(path)
            log.debug("Saved cached WAV atomically to %s", path)
            return path
        except Exception as e:
            if tmp_path.is_file():
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass
            if path.is_file() and path.stat().st_size >= 44:
                return path
            log.warning("Could not write cache file %s: %s", path, e)
            raise


    def put(
        self,
        text: str,
        voice_id: str,
        model_id: str,
        pcm_bytes: bytes,
        output_format: str = "pcm_24000",
        sample_rate: int = 24000,
    ) -> Path:
        """Convenience alias for put_pcm."""
        return self.put_pcm(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
            output_format=output_format,
            pcm_bytes=pcm_bytes,
            sample_rate=sample_rate,
        )

    def play_wav(self, path: str | Path, wait: bool = True) -> bool:
        """Plays a WAV file via sounddevice with winsound/system fallbacks."""
        wav_path = Path(path)
        if not wav_path.is_file():
            log.warning("Cannot play missing audio file: %s", wav_path)
            return False

        if os.environ.get("JARVIS_MOCK_AUDIO") == "1":
            log.debug("JARVIS_MOCK_AUDIO=1: skipping physical playback for %s", wav_path)
            return True

        # Method 1: sounddevice (high-fidelity float32 streaming)
        try:
            import sounddevice as sd
            with wave.open(str(wav_path), "rb") as wf:
                ch = wf.getnchannels()
                sw = wf.getsampwidth()
                rate = wf.getframerate()
                raw = wf.readframes(wf.getnframes())
            if raw and ch in (1, 2) and sw == 2:
                pcm_i16 = np.frombuffer(raw, dtype=np.int16)
                pcm_f = pcm_i16.astype(np.float32) / 32768.0
                if ch == 2:
                    pcm_f = pcm_f.reshape(-1, 2)
                sd.play(pcm_f, samplerate=rate)
                if wait:
                    sd.wait()
                return True
        except Exception as e:
            log.debug("sounddevice playback failed (%s), falling back to platform player", e)

        # Method 2: Windows native winsound
        if sys.platform == "win32":
            try:
                import winsound
                flags = winsound.SND_FILENAME
                if not wait:
                    flags |= winsound.SND_ASYNC
                winsound.PlaySound(str(wav_path), flags)
                return True
            except Exception as e:
                log.warning("winsound playback failed: %s", e)

        return False


class LocalTTSCache(TTSAudioCache):
    """
    Subclass providing exact byte-returning get() contract for test fixtures
    expecting get() -> bytes.
    """

    def get(  # type: ignore[override]
        self,
        text: str,
        voice_id: str = "",
        model_id: str = "eleven_multilingual_v2",
        output_format: str = "pcm_24000",
    ) -> bytes | None:
        return self.get_bytes(text, voice_id, model_id, output_format)
