"""
jarvis/stt/engine.py
====================
Speech-to-Text (STT) Engine Subsystem for JARVIS.
Provides:
  - Multi-provider architecture: OpenAI Whisper API REST, Local faster-whisper, Windows SAPI, and Mock STT.
  - Voice Activity Detection (VAD) buffer segmentation using jarvis.audio.dsp RMS energy.
  - Pre-speech circular ring buffering, trailing silence completion, and zero-crash fault isolation.
  - Universal audio conversion (np.ndarray, bytes, Path, io.BytesIO) to 16-bit PCM WAV.
"""
from __future__ import annotations

import io
import logging
import os
import subprocess
import sys
import tempfile
import threading
import wave
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np

from jarvis.audio.dsp import calculate_rms

log = logging.getLogger("jarvis.stt.engine")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    requests = None  # type: ignore[assignment]
    REQUESTS_AVAILABLE = False


# ── Windows: make nvidia pip-wheel DLLs discoverable by ctranslate2.
#    ctranslate2 uses Windows LoadLibrary() which searches os.environ["PATH"],
#    NOT the directories added via os.add_dll_directory().
#    We add both for maximum compatibility.
#    Structure: site-packages/nvidia/<pkg>/bin/*.dll
if sys.platform == "win32":
    try:
        import site as _site
        for _sp in _site.getsitepackages():
            _nvidia_root = os.path.join(_sp, "nvidia")
            if not os.path.isdir(_nvidia_root):
                continue
            for _pkg_name in os.listdir(_nvidia_root):
                _bin_dir = os.path.join(_nvidia_root, _pkg_name, "bin")
                if not os.path.isdir(_bin_dir):
                    continue
                # Add to DLL search path (Python-level)
                if hasattr(os, "add_dll_directory"):
                    try:
                        os.add_dll_directory(_bin_dir)
                    except OSError:
                        pass
                # Add to PATH (for LoadLibrary / ctranslate2 C extension)
                if _bin_dir not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = _bin_dir + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass

try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    WhisperModel = None
    FASTER_WHISPER_AVAILABLE = False


class STTError(Exception):
    """Base exception for Speech-to-Text transcription errors."""
    pass


# ============================================================================
# Audio Format & Resampling Helpers
# ============================================================================

def resample_audio(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Linear interpolation resampling for 1D float32 audio arrays."""
    if orig_sr == target_sr or len(samples) == 0:
        return samples
    duration = len(samples) / float(orig_sr)
    num_target_samples = int(duration * target_sr)
    if num_target_samples == 0:
        return np.empty(0, dtype=samples.dtype)
    orig_indices = np.linspace(0.0, 1.0, len(samples), endpoint=False)
    target_indices = np.linspace(0.0, 1.0, num_target_samples, endpoint=False)
    return np.interp(target_indices, orig_indices, samples).astype(samples.dtype)


def audio_to_float32(
    audio: np.ndarray | bytes | Path | io.BytesIO | str,
    sample_rate: int = 16000,
) -> np.ndarray:
    """
    Normalizes any supported audio input into a 1D float32 NumPy array [-1.0, 1.0].
    """
    if audio is None:
        return np.empty(0, dtype=np.float32)

    if isinstance(audio, (str, Path)):
        p = Path(audio)
        if not p.exists():
            return np.empty(0, dtype=np.float32)
        try:
            with wave.open(str(p), "rb") as wf:
                sr = wf.getframerate()
                n_frames = wf.getnframes()
                raw_bytes = wf.readframes(n_frames)
                sampwidth = wf.getsampwidth()
                n_channels = wf.getnchannels()
                if sampwidth == 2:
                    arr = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                elif sampwidth == 4:
                    arr = np.frombuffer(raw_bytes, dtype=np.float32)
                else:
                    arr = np.frombuffer(raw_bytes, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0
                if n_channels > 1:
                    arr = arr.reshape(-1, n_channels).mean(axis=1)
                return resample_audio(arr, sr, sample_rate)
        except Exception as e:
            log.warning("Failed reading audio file %s: %s", audio, e)
            return np.empty(0, dtype=np.float32)

    if isinstance(audio, io.BytesIO):
        audio = audio.getvalue()

    if isinstance(audio, bytes):
        if audio.startswith(b"RIFF"):
            try:
                buf = io.BytesIO(audio)
                with wave.open(buf, "rb") as wf:
                    sr = wf.getframerate()
                    n_frames = wf.getnframes()
                    raw_bytes = wf.readframes(n_frames)
                    sampwidth = wf.getsampwidth()
                    n_channels = wf.getnchannels()
                    if sampwidth == 2:
                        arr = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                    else:
                        arr = np.frombuffer(raw_bytes, dtype=np.float32)
                    if n_channels > 1:
                        arr = arr.reshape(-1, n_channels).mean(axis=1)
                    return resample_audio(arr, sr, sample_rate)
            except Exception as e:
                log.warning("Failed parsing WAV bytes: %s", e)
                return np.empty(0, dtype=np.float32)
        else:
            # Assume raw 16-bit PCM bytes
            try:
                arr = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
                return arr
            except Exception:
                return np.empty(0, dtype=np.float32)

    if isinstance(audio, np.ndarray):
        if audio.size == 0:
            return np.empty(0, dtype=np.float32)
        arr = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
        if np.issubdtype(arr.dtype, np.integer):
            arr = arr.astype(np.float32) / 32768.0
        elif arr.dtype != np.float32:
            arr = arr.astype(np.float32)
        if arr.ndim > 1:
            arr = np.mean(arr, axis=1)
        return np.clip(arr, -1.0, 1.0)

    return np.empty(0, dtype=np.float32)


def float32_to_pcm16_wav_bytes(
    audio: np.ndarray,
    sample_rate: int = 16000,
) -> io.BytesIO:
    """
    Encodes a 1D float32 audio array into an in-memory 16-bit mono PCM WAV container.
    """
    arr = audio_to_float32(audio, sample_rate=sample_rate)
    pcm16 = (np.clip(arr, -1.0, 1.0) * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())
    buf.seek(0)
    return buf


# Backward compatibility helper
audio_to_wav_bytes = float32_to_pcm16_wav_bytes


# ============================================================================
# Voice Activity Detection (VAD) & Buffer Segmenter
# ============================================================================

class VADSegmenter:
    """
    Voice Activity Detection and real-time audio stream buffer segmenter.
    Maintains pre-speech circular ring buffer and sample-accurate trailing silence debounce.
    """

    def __init__(
        self,
        vad_threshold: float = 0.015,
        sample_rate: int = 16000,
        silence_trailing_s: float = 0.8,
        pre_speech_s: float = 0.3,
        min_speech_s: float = 0.25,
        max_speech_s: float = 10.0,
    ) -> None:
        self.vad_threshold = float(vad_threshold)
        self.sample_rate = int(sample_rate)
        self.silence_trailing_s = float(silence_trailing_s)
        self.pre_speech_s = float(pre_speech_s)
        self.min_speech_s = float(min_speech_s)
        self.max_speech_s = float(max_speech_s)

        self.pre_speech_samples = int(self.sample_rate * self.pre_speech_s)
        self.silence_trailing_samples = int(self.sample_rate * self.silence_trailing_s)
        self.min_speech_samples = int(self.sample_rate * self.min_speech_s)
        self.max_speech_samples = int(self.sample_rate * self.max_speech_s)

        self._pre_buffer: list[float] = []
        self._active_buffer: list[float] = []
        self._is_speech_active: bool = False
        self._samples_count: int = 0
        self._silence_start_sample: int | None = None
        self._speech_start_sample: int | None = None
        self._lock = threading.RLock()

    def reset(self) -> None:
        """Reset segmenter state and empty all internal buffers."""
        with self._lock:
            self._pre_buffer.clear()
            self._active_buffer.clear()
            self._is_speech_active = False
            self._samples_count = 0
            self._silence_start_sample = None
            self._speech_start_sample = None

    def is_speech(self, block: np.ndarray | None, threshold: float | None = None) -> bool:
        """Evaluates whether an audio block exceeds the RMS speech threshold."""
        if block is None or getattr(block, "size", 0) == 0:
            return False
        rms = calculate_rms(block)
        th = threshold if threshold is not None else self.vad_threshold
        return rms >= th

    def feed_block(self, block: np.ndarray) -> np.ndarray | None:
        """
        Feed an incoming audio frame.
        Returns a complete 1D float32 audio segment when an utterance completes, or None.
        """
        if block is None or block.size == 0:
            return None

        samples = audio_to_float32(block, sample_rate=self.sample_rate).tolist()
        if not samples:
            return None

        num_samples = len(samples)
        block_rms = calculate_rms(np.array(samples, dtype=np.float32))
        is_voice = block_rms >= self.vad_threshold

        with self._lock:
            self._samples_count += num_samples

            if not self._is_speech_active:
                # Accumulate circular pre-speech ring buffer
                self._pre_buffer.extend(samples)
                if len(self._pre_buffer) > self.pre_speech_samples:
                    self._pre_buffer = self._pre_buffer[-self.pre_speech_samples:]

                if is_voice:
                    self._is_speech_active = True
                    self._speech_start_sample = self._samples_count
                    self._silence_start_sample = None
                    self._active_buffer = list(self._pre_buffer)
                    self._active_buffer.extend(samples)
                    self._pre_buffer.clear()
                return None
            else:
                # Speech is actively being captured
                self._active_buffer.extend(samples)
                speech_len = len(self._active_buffer)

                # Hard cutoff if maximum duration exceeded
                if speech_len >= self.max_speech_samples:
                    segment: np.ndarray | None = np.array(self._active_buffer, dtype=np.float32)
                    self.reset()
                    return segment

                if is_voice:
                    self._silence_start_sample = None
                else:
                    if self._silence_start_sample is None:
                        self._silence_start_sample = self._samples_count - num_samples
                    if (self._samples_count - self._silence_start_sample) >= self.silence_trailing_samples:
                        # Utterance complete!
                        total_samples = len(self._active_buffer)
                        segment = (
                            np.array(self._active_buffer, dtype=np.float32)
                            if total_samples >= self.min_speech_samples
                            else None
                        )
                        self.reset()
                        return segment

                return None


# ============================================================================
# Abstract Base STT Engine
# ============================================================================

class BaseSTTEngine(ABC):
    """Abstract interface that all STT providers must implement."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config: dict[str, Any] = config or {}

    @abstractmethod
    def transcribe(
        self,
        audio: np.ndarray | bytes | Path | io.BytesIO | str,
        language: str = "vi",
        **kwargs: Any,
    ) -> str:
        """
        Transcribe audio input to text.

        Args:
            audio: Audio samples array, raw bytes, WAV buffer, or file path.
            language: ISO language code (e.g. 'vi', 'en').

        Returns:
            str: Transcribed speech text (empty string on silence or error).
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is operational and configured."""
        pass

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Identifier name of the STT engine."""
        pass

    @property
    def supported_languages(self) -> list[str]:
        return ["vi", "en"]


# ============================================================================
# Provider 1: OpenAI Whisper API (REST Multipart)
# ============================================================================

class OpenAIWhisperSTT(BaseSTTEngine):
    """OpenAI Whisper API speech-to-text engine via direct HTTP REST."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        if "api_key" in self.config:
            self.api_key = self.config["api_key"]
        else:
            self.api_key = (
                os.environ.get("OPENAI_API_KEY")
                or os.environ.get("JARVIS_OPENAI_API_KEY", "")
            )
        self.model_name = self.config.get("model", "whisper-1")
        self.endpoint = self.config.get("endpoint", "https://api.openai.com/v1/audio/transcriptions")
        self.temperature = float(self.config.get("temperature", 0.0))
        self.timeout_s = float(self.config.get("timeout_s", 10.0))

    @property
    def engine_name(self) -> str:
        return "openai_whisper_api"

    def is_available(self) -> bool:
        return bool(self.api_key and str(self.api_key).strip())

    def transcribe(
        self,
        audio: np.ndarray | bytes | Path | io.BytesIO | str,
        language: str = "vi",
        mock_http: Any | None = None,
        **kwargs: Any,
    ) -> str:
        arr = audio_to_float32(audio)
        if arr.size == 0 or calculate_rms(arr) < 0.001:
            return ""

        if mock_http is not None:
            if hasattr(mock_http, "handle_whisper_transcription"):
                return mock_http.handle_whisper_transcription(arr, language=language)
            return "bật đèn phòng khách"

        if not self.is_available():
            raise STTError("OpenAI API key missing or invalid")

        if not REQUESTS_AVAILABLE:
            raise STTError("requests library not installed")

        wav_io = float32_to_pcm16_wav_bytes(arr, sample_rate=16000)
        files = {
            "file": ("audio.wav", wav_io.getvalue(), "audio/wav"),
        }
        data = {
            "model": self.model_name,
            "language": language,
            "temperature": str(self.temperature),
            "response_format": "json",
        }
        headers = {
            "Authorization": f"Bearer {self.api_key.strip()}",
        }

        try:
            resp = requests.post(
                self.endpoint,
                files=files,
                data=data,
                headers=headers,
                timeout=self.timeout_s,
            )
            if resp.status_code != 200:
                log.warning("OpenAI Whisper API failed with HTTP %d: %s", resp.status_code, resp.text)
                raise STTError(f"HTTP {resp.status_code}: {resp.text}")

            result_json = resp.json()
            return result_json.get("text", "").strip()
        except Exception as e:
            log.error("OpenAI Whisper request error: %s", e)
            raise STTError(f"Transcription failed: {e}") from e


# Backward compatibility alias
OpenAIWhisperAPI = OpenAIWhisperSTT


# ============================================================================
# Provider 2: Local Faster-Whisper
# ============================================================================

class FasterWhisperSTT(BaseSTTEngine):
    """Local offline speech transcriber using faster-whisper (CTranslate2)."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.model_size = self.config.get("model_size", "base")
        self.compute_type = self.config.get("compute_type", "int8")
        _raw_root = self.config.get("download_root", "") or ""
        if not _raw_root:
            _appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            _base = Path(_appdata) / "JARVIS" if _appdata else Path.home() / ".jarvis"
            _raw_root = str(_base / "cache" / "whisper")
        self.download_root = _raw_root
        self._model: Any | None = None
        self._lock = threading.RLock()

        # Auto-detect CUDA availability; fall back to CPU if CUDA libs missing
        requested_device = self.config.get("device", "cpu")
        self.device = self._resolve_device(requested_device)
        if self.device != requested_device:
            log.warning(
                "faster-whisper: requested device=%r but CUDA unavailable — falling back to device=%r. "
                "Install 'nvidia-cublas-cu12' or CUDA Toolkit 12.x to use GPU.",
                requested_device, self.device,
            )
            # CPU-friendly compute type
            if self.compute_type in ("float16", "int8_float16", "bfloat16"):
                self.compute_type = "int8"

    @staticmethod
    def _resolve_device(requested: str) -> str:
        """Returns 'cuda' if CUDA is truly usable, else 'cpu'."""
        if requested != "cuda":
            return requested
        if not FASTER_WHISPER_AVAILABLE:
            return "cpu"
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() < 1:
                return "cpu"
            # Quick smoke-test: verify cublas DLL loads
            import ctypes
            for dll in ("cublas64_12.dll", "cublas64_11.dll"):
                try:
                    ctypes.CDLL(dll)
                    return "cuda"
                except OSError:
                    continue
            # DLL not in PATH — try locating via nvidia wheel
            try:
                import nvidia.cublas.lib  # noqa: F401 (nvidia-cublas-cu12 wheel)
                return "cuda"
            except ImportError:
                pass
            log.warning("CUDA device found but cublas DLL missing. Falling back to CPU.")
            return "cpu"
        except Exception:
            return "cpu"

    @property
    def engine_name(self) -> str:
        return "faster_whisper"

    def is_available(self) -> bool:
        return FASTER_WHISPER_AVAILABLE

    def _get_model(self) -> Any:
        if self._model is None:
            with self._lock:
                if self._model is None and FASTER_WHISPER_AVAILABLE:
                    os.makedirs(self.download_root, exist_ok=True)
                    self._model = WhisperModel(
                        self.model_size,
                        device=self.device,
                        compute_type=self.compute_type,
                        download_root=self.download_root,
                    )
        return self._model

    def transcribe(
        self,
        audio: np.ndarray | bytes | Path | io.BytesIO | str,
        language: str = "vi",
        **kwargs: Any,
    ) -> str:
        if not self.is_available():
            raise STTError("faster-whisper is not installed")

        arr = audio_to_float32(audio, sample_rate=16000)
        if arr.size == 0 or calculate_rms(arr) < 0.001:
            return ""

        model = self._get_model()
        if model is None:
            raise STTError("Failed loading faster-whisper model")

        with self._lock:
            segments, _ = model.transcribe(arr, language=language, beam_size=5)
            text = " ".join(s.text.strip() for s in segments)
            return text.strip()


# Backward compatibility alias
LocalWhisperSTT = FasterWhisperSTT


# ============================================================================
# Provider 3: Windows Speech API / PowerShell SAPI
# ============================================================================

class WindowsSpeechSTT(BaseSTTEngine):
    """Offline Windows Speech Recognition via PowerShell System.Speech / SAPI."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.timeout_s = float(self.config.get("timeout_s", 5.0))

    @property
    def engine_name(self) -> str:
        return "windows_speech"

    def is_available(self) -> bool:
        return sys.platform == "win32"

    def transcribe(
        self,
        audio: np.ndarray | bytes | Path | io.BytesIO | str,
        language: str = "vi",
        **kwargs: Any,
    ) -> str:
        if not self.is_available():
            return ""

        arr = audio_to_float32(audio, sample_rate=16000)
        if arr.size == 0 or calculate_rms(arr) < 0.001:
            return ""

        wav_io = float32_to_pcm16_wav_bytes(arr, sample_rate=16000)

        # Write to temporary file for PowerShell SAPI recognition
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(wav_io.getvalue())

        # Normalize language to Windows BCP-47 culture code
        lang_code = language.strip()
        if lang_code in ("vi", "vie", "vi_VN"):
            culture_code = "vi-VN"
        elif lang_code in ("en", "en_US", "eng"):
            culture_code = "en-US"
        else:
            # Map ll -> ll-LL (e.g. "zh" -> "zh-CN", "ja" -> "ja-JP")
            culture_code = f"{lang_code[:2].lower()}-{lang_code[:2].upper()}"

        try:
            # Try with the requested language culture first (requires language pack)
            ps_script = (
                f"Add-Type -AssemblyName System.Speech; "
                f"$culture = [System.Globalization.CultureInfo]::GetCultureInfo('{culture_code}'); "
                f"$engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine($culture); "
                f"$engine.SetInputToWaveFile('{tmp_path}'); "
                f"$grammar = New-Object System.Speech.Recognition.DictationGrammar; "
                f"$engine.LoadGrammar($grammar); "
                f"$res = $engine.Recognize([TimeSpan]::FromSeconds({int(self.timeout_s)})); "
                f"if ($res) {{ Write-Output $res.Text }}"
            )
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout_s + 2.0,
                creationflags=creationflags,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()

            # Fallback: no culture (uses system default) — still better than garbage
            log.debug("WindowsSpeechSTT culture '%s' failed, falling back to default engine", culture_code)
            ps_fallback = (
                f"Add-Type -AssemblyName System.Speech; "
                f"$engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine; "
                f"$engine.SetInputToWaveFile('{tmp_path}'); "
                f"$grammar = New-Object System.Speech.Recognition.DictationGrammar; "
                f"$engine.LoadGrammar($grammar); "
                f"$res = $engine.Recognize([TimeSpan]::FromSeconds({int(self.timeout_s)})); "
                f"if ($res) {{ Write-Output $res.Text }}"
            )
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            res2 = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_fallback],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout_s + 2.0,
                creationflags=creationflags,
            )
            return res2.stdout.strip()
        except Exception as e:
            log.debug("Windows Speech recognition failed: %s", e)
            return ""
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# ============================================================================
# Provider 4: Mock STT Engine
# ============================================================================

class MockSTTEngine(BaseSTTEngine):
    """Deterministic Mock STT engine for automated testing and CI."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        default_transcript: str = "bật đèn phòng khách",
        canned_transcripts: dict[str, str] | None = None,
    ) -> None:
        super().__init__(config)
        self.default_transcript = default_transcript
        self.canned_transcripts = canned_transcripts or {
            "bật đèn": "bật đèn phòng khách",
            "nhiệt độ": "kiểm tra nhiệt độ cpu",
            "hệ thống": "tình trạng hệ thống",
            "quét mạng": "quét mạng nội bộ",
        }
        self.call_history: list[dict[str, Any]] = []

    @property
    def engine_name(self) -> str:
        return "mock"

    def is_available(self) -> bool:
        return True

    def set_transcript(self, text: str) -> None:
        """Set default canned transcript returned on non-silent audio."""
        self.default_transcript = text

    def transcribe(
        self,
        audio: np.ndarray | bytes | Path | io.BytesIO | str,
        language: str = "vi",
        **kwargs: Any,
    ) -> str:
        arr = audio_to_float32(audio)
        if arr.size == 0:
            return ""
        rms = calculate_rms(arr)
        if rms < 0.001:
            return ""

        self.call_history.append({"rms": rms, "samples": len(arr), "language": language})

        # Allow per-call override via kwargs
        if "transcript" in kwargs and kwargs["transcript"] is not None:
            return str(kwargs["transcript"])
        canned_key = kwargs.get("canned_key")
        if canned_key and canned_key in self.canned_transcripts:
            return self.canned_transcripts[canned_key]

        return self.default_transcript


# ============================================================================
# Master Unified STTEngine Coordinator
# ============================================================================

class STTEngine:
    """
    Unified Speech-to-Text coordinator managing multi-provider resolution,
    VAD segmentation, streaming transcription, and zero-crash fallbacks.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        provider: str | None = None,
        primary_engine: BaseSTTEngine | None = None,
        fallback_engine: BaseSTTEngine | None = None,
        event_bus: Any | None = None,
        config_manager: Any | None = None,
    ) -> None:
        self.config = config or {}
        self.event_bus = event_bus
        self.config_manager = config_manager
        self.provider_name = provider or self.config.get("provider", "mock")
        self.default_language = self.config.get("language", "vi")
        self.vad_threshold = float(self.config.get("vad_threshold", 0.015))
        self.silence_trailing_s = float(self.config.get("silence_trailing_s", 0.8))

        self.vad = VADSegmenter(
            vad_threshold=self.vad_threshold,
            silence_trailing_s=self.silence_trailing_s,
        )

        self._lock = threading.RLock()
        self.primary_engine: BaseSTTEngine = primary_engine or self._resolve_engine(self.provider_name)
        self.fallback_engine: BaseSTTEngine = fallback_engine or (
            WindowsSpeechSTT(self.config.get("windows_sapi", self.config.get("web_speech", {})))
            if (sys.platform == "win32" and not isinstance(self.primary_engine, WindowsSpeechSTT))
            else MockSTTEngine(self.config)
        )

        if self.config_manager and hasattr(self.config_manager, "register_reload_callback"):
            self.config_manager.register_reload_callback(self._on_config_reloaded)

    def _resolve_engine(self, name: str) -> BaseSTTEngine:
        name_lower = name.lower() if isinstance(name, str) else "mock"
        if name_lower in ("whisper_api", "openai", "openai_whisper"):
            return OpenAIWhisperSTT(self.config.get("whisper_api", {}))
        elif name_lower in ("faster_whisper", "local_whisper"):
            return FasterWhisperSTT(self.config.get("faster_whisper", {}))
        elif name_lower in ("windows_sapi", "windows_speech", "sapi5", "web_speech", "windows", "web"):
            if sys.platform == "win32":
                return WindowsSpeechSTT(self.config.get("windows_sapi", self.config.get("web_speech", {})))
            return MockSTTEngine(self.config)
        elif name_lower == "auto":
            # Auto-detection resolution
            api_eng = OpenAIWhisperSTT(self.config.get("whisper_api", {}))
            if api_eng.is_available():
                return api_eng
            local_eng = FasterWhisperSTT(self.config.get("faster_whisper", {}))
            if local_eng.is_available():
                return local_eng
            if sys.platform == "win32":
                return WindowsSpeechSTT(self.config.get("windows_sapi", self.config.get("web_speech", {})))
            return MockSTTEngine(self.config)
        return MockSTTEngine(self.config)

    def _on_config_reloaded(self, new_cfg: Any) -> None:
        with self._lock:
            stt_cfg = new_cfg.get("stt", {}) if hasattr(new_cfg, "get") else {}
            if stt_cfg:
                self.config = stt_cfg
                self.provider_name = stt_cfg.get("provider", self.provider_name)
                self.vad_threshold = float(stt_cfg.get("vad_threshold", self.vad_threshold))
                self.vad.vad_threshold = self.vad_threshold
                self.primary_engine = self._resolve_engine(self.provider_name)

    def is_speech_present(self, audio_buffer: np.ndarray | None, threshold: float | None = None) -> bool:
        """Fast RMS check to verify speech presence."""
        th = threshold if threshold is not None else self.vad_threshold
        return self.vad.is_speech(audio_buffer, threshold=th)

    def transcribe(
        self,
        audio: np.ndarray | bytes | Path | io.BytesIO | str,
        language: str | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Public transcription entrypoint. Sanitizes input, enforces fast silence gating,
        and manages zero-crash provider fallback.
        """
        target_lang = language or self.default_language
        arr = audio_to_float32(audio)
        if arr.size == 0:
            return ""

        # Fast silence gate
        if calculate_rms(arr) < 0.001:
            return ""

        with self._lock:
            # 1. Try Primary Engine
            if self.primary_engine.is_available() or "mock_http" in kwargs or isinstance(self.primary_engine, MockSTTEngine):
                try:
                    text = self.primary_engine.transcribe(arr, language=target_lang, **kwargs)
                    if text:
                        if self.event_bus:
                            self.event_bus.publish("stt.transcribed", text=text, engine=self.primary_engine.engine_name)
                        return text
                except Exception as e:
                    log.warning("Primary STT (%s) failed: %s; trying fallback.", self.primary_engine.engine_name, e)

            # 2. Try Fallback Engine
            if self.fallback_engine and self.fallback_engine.is_available():
                try:
                    text = self.fallback_engine.transcribe(arr, language=target_lang, **kwargs)
                    if text:
                        if self.event_bus:
                            self.event_bus.publish("stt.transcribed", text=text, engine=self.fallback_engine.engine_name)
                        return text
                except Exception as e:
                    log.error("Fallback STT (%s) failed: %s", self.fallback_engine.engine_name, e)

        return ""

    def transcribe_stream(
        self,
        audio_generator: Iterator[np.ndarray],
        language: str | None = None,
        sample_rate: int = 16000,
    ) -> str:
        """
        Consumes an audio block generator until VAD segments a complete utterance,
        then transcribes and returns the result.
        """
        self.vad.reset()
        for block in audio_generator:
            segment = self.vad.feed_block(block)
            if segment is not None:
                return self.transcribe(segment, language=language)
        return ""

    def feed_audio_block(self, block: np.ndarray) -> str | None:
        """
        Feeds a real-time frame from AudioEngine.
        Returns transcribed text if an utterance completed on this block, otherwise None.
        """
        segment = self.vad.feed_block(block)
        if segment is not None:
            return self.transcribe(segment)
        return None
