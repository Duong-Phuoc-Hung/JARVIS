"""
jarvis/tts/vieneu.py
====================
High-Fidelity On-Device Vietnamese Neural TTS Adapter using VieNeu-TTS (pnnbao97/VieNeu-TTS).
Features:
  - Instant Voice Cloning via 3-5 second reference audio (`ref_audio`).
  - Seamless English-Vietnamese Bilingual Code-Switching powered by sea-g2p.
  - Up to 48kHz high-fidelity speech synthesis.
  - Zero GPU VRAM footprint on CPU (runs via ONNX Runtime).
  - Full fail-closed fallback support.
"""
from __future__ import annotations

import io
import logging
import os
import re
import sys
import tempfile
import threading
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from jarvis.tts.base import BaseTTSEngine, TTSError

log = logging.getLogger("jarvis.tts.vieneu")


@dataclass
class VieNeuConfig:
    """Configuration schema for VieNeu-TTS Engine."""
    model_name: str = "pnnbao-ump/VieNeu-TTS-0.3B"
    codec_repo: str = "neuphonic/distill-neucodec"
    device: str = "cpu"  # "cpu" or "cuda"
    emotion: str = "natural"  # "natural", "storytelling"
    reference_audio: str = ""  # Path to reference audio clip for voice cloning
    sample_rate: int = 48000
    speed: float = 1.0
    enabled: bool = True


class VieNeuTTSEngine(BaseTTSEngine):
    """
    On-Device Vietnamese Neural TTS Engine using VieNeu-TTS.
    Implements BaseTTSEngine for seamless integration into TTSManager.
    """

    def __init__(self, config: dict[str, Any] | VieNeuConfig | None = None) -> None:
        if isinstance(config, VieNeuConfig):
            self.cfg = config
            raw_cfg = {
                "model_name": config.model_name,
                "codec_repo": config.codec_repo,
                "device": config.device,
                "emotion": config.emotion,
                "reference_audio": config.reference_audio,
                "sample_rate": config.sample_rate,
                "speed": config.speed,
                "enabled": config.enabled,
            }
        elif isinstance(config, dict):
            raw_cfg = config
            self.cfg = VieNeuConfig(
                model_name=config.get("model_name", "pnnbao-ump/VieNeu-TTS-0.3B"),
                codec_repo=config.get("codec_repo", "neuphonic/distill-neucodec"),
                device=config.get("device", "cpu"),
                emotion=config.get("emotion", "natural"),
                reference_audio=config.get("reference_audio", ""),
                sample_rate=int(config.get("sample_rate", 48000)),
                speed=float(config.get("speed", 1.0)),
                enabled=bool(config.get("enabled", True)),
            )
        else:
            self.cfg = VieNeuConfig()
            raw_cfg = {}

        super().__init__(config=raw_cfg)
        self._tts_instance: Any | None = None
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        """
        Check whether VieNeu-TTS SDK (vieneu) is installed and available.
        Fail-closed: Returns False if library is missing.
        """
        if not self.cfg.enabled:
            return False
        try:
            import vieneu  # type: ignore[import-untyped]  # noqa: F401
            return True
        except ImportError:
            return False
        except Exception as exc:
            log.debug("VieNeu availability check exception: %s", exc)
            return False

    @property
    def engine_name(self) -> str:
        return "vieneu"

    @property
    def sample_rate(self) -> int:
        return self.cfg.sample_rate

    def _get_model(self) -> Any:
        """Lazy load and initialize the VieNeu model instance."""
        with self._lock:
            if self._tts_instance is None:
                if not self.is_available():
                    raise TTSError(
                        "VieNeu-TTS engine is unavailable. "
                        "Please install via: pip install vieneu"
                    )
                try:
                    from vieneu import Vieneu  # type: ignore[import-untyped]
                    kwargs: dict[str, Any] = {
                        "backbone_repo": self.cfg.model_name,
                        "codec_repo": self.cfg.codec_repo,
                        "backbone_device": self.cfg.device,
                        "codec_device": self.cfg.device,
                    }
                    if hasattr(self.cfg, "emotion") and self.cfg.emotion:
                        kwargs["emotion"] = self.cfg.emotion
                    self._tts_instance = Vieneu(**kwargs)
                    log.info(
                        "VieNeu-TTS engine loaded successfully (model=%s, device=%s)",
                        self.cfg.model_name, self.cfg.device
                    )
                except Exception as exc:
                    log.error("Failed to load VieNeu-TTS model: %s", exc)
                    raise TTSError(f"VieNeu-TTS initialization failed: {exc}") from exc
        return self._tts_instance

    def _convert_to_pcm_bytes(self, audio_data: Any) -> bytes:
        """Convert arbitrary audio array / tensor output from VieNeu into raw 16-bit PCM bytes."""
        if hasattr(audio_data, "cpu"):
            audio_np = audio_data.detach().cpu().numpy()
        elif isinstance(audio_data, np.ndarray):
            audio_np = audio_data
        else:
            audio_np = np.asarray(audio_data, dtype=np.float32)

        # Ensure 1D mono
        audio_np = np.squeeze(audio_np)
        if audio_np.ndim > 1:
            audio_np = audio_np[0]

        # Convert float (-1.0 to 1.0) to int16
        if audio_np.dtype != np.int16:
            audio_max = np.max(np.abs(audio_np)) if len(audio_np) > 0 else 1.0
            if audio_max > 1.0:
                audio_np = audio_np / audio_max
            audio_int16 = (audio_np * 32767.0).astype(np.int16)
        else:
            audio_int16 = audio_np

        return audio_int16.tobytes()

    def _convert_to_wav_bytes(self, audio_data: Any, sample_rate: int) -> bytes:
        """Convert arbitrary audio array / tensor / PCM bytes from VieNeu into valid 16-bit PCM WAV bytes."""
        pcm_bytes = audio_data if isinstance(audio_data, bytes) else self._convert_to_pcm_bytes(audio_data)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)

        return buf.getvalue()

    def synthesize_to_bytes(
        self,
        text: str,
        voice_id: str | None = None,
        ref_audio: str | None = None,
        **kwargs: Any,
    ) -> bytes:
        """
        Synthesize text to raw 48kHz 16-bit mono PCM bytes using VieNeu-TTS.
        Supports voice cloning if ref_audio or config.reference_audio is specified.
        Automatically chunks long text to maintain maximum prosodic fidelity.
        """
        if not text or not text.strip():
            raise TTSError("Cannot synthesize empty text.")

        model = self._get_model()
        target_ref = ref_audio or voice_id or self.cfg.reference_audio

        infer_kwargs: dict[str, Any] = {}
        if target_ref and Path(target_ref).is_file():
            infer_kwargs["ref_audio"] = target_ref

        # Sentence chunking if text has multiple punctuation boundaries and length > 120 chars
        clean_text = text.strip()
        chunks = [c.strip() for c in re.split(r"(?<=[.!?;\n])\s+", clean_text) if c.strip()]
        if not chunks:
            chunks = [clean_text]

        pcm_results: list[bytes] = []
        try:
            for chunk in chunks:
                audio_out = model.infer(text=chunk, **infer_kwargs)
                pcm_results.append(self._convert_to_pcm_bytes(audio_out))
            return b"".join(pcm_results)
        except Exception as exc:
            log.error("VieNeu-TTS synthesis failed: %s", exc)
            raise TTSError(f"VieNeu-TTS synthesis error: {exc}") from exc

    def synthesize_to_wav_bytes(
        self,
        text: str,
        voice_id: str | None = None,
        ref_audio: str | None = None,
        **kwargs: Any,
    ) -> bytes:
        """Synthesize text and pack directly into a full 48kHz WAV container."""
        pcm_bytes = self.synthesize_to_bytes(text, voice_id=voice_id, ref_audio=ref_audio, **kwargs)
        return self._convert_to_wav_bytes(pcm_bytes, self.cfg.sample_rate)

    def speak(
        self,
        text: str,
        voice_id: str | None = None,
        wait: bool = False,
        **kwargs: Any,
    ) -> bool:
        """Synthesize text and play audio via sounddevice (48kHz studio) with winsound fallback."""
        try:
            pcm_bytes = self.synthesize_to_bytes(text, voice_id=voice_id, **kwargs)
            if not pcm_bytes:
                return False

            # Method 1: sounddevice high-fidelity 48kHz playback
            try:
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
                log.debug("sounddevice playback failed (%s), falling back to winsound", e)

            # Method 2: Windows native winsound
            if sys.platform == "win32":
                import winsound
                wav_bytes = self._convert_to_wav_bytes(pcm_bytes, self.sample_rate)
                flags = winsound.SND_MEMORY
                if not wait:
                    flags |= winsound.SND_ASYNC
                winsound.PlaySound(wav_bytes, flags)
                return True
            else:
                # Portable temporary file playback fallback
                wav_bytes = self._convert_to_wav_bytes(pcm_bytes, self.sample_rate)
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp.write(wav_bytes)
                    tmp_name = tmp.name
                try:
                    import subprocess
                    cmd = ["aplay", tmp_name] if sys.platform == "linux" else ["afplay", tmp_name]
                    subprocess.run(cmd, check=False)
                finally:
                    try:
                        os.unlink(tmp_name)
                    except OSError:
                        pass
                return True

        except Exception as exc:
            log.warning("VieNeuTTSEngine.speak failed: %s", exc)
            return False
