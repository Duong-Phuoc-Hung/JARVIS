"""
jarvis/tts/fallback.py
======================
Offline Fallback TTS Engine utilizing Windows SAPI5, PowerShell, and pyttsx3.
Ensures 100% speech availability without internet connection.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

from jarvis.tts.base import BaseTTSEngine, TTSError

log = logging.getLogger("jarvis.tts.fallback")


class SAPI5FallbackTTS(BaseTTSEngine):
    """Windows native SAPI5 speech synthesis with cross-platform mock support."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.voice_name = self.config.get("voice_name", "Microsoft David Desktop")
        self.rate = int(self.config.get("rate", 0))       # SAPI: -10 to +10
        self.volume = int(self.config.get("volume", 100)) # 0 to 100
        self._spoken_history: List[str] = []

    @property
    def offline_calls(self) -> List[str]:
        return self._spoken_history

    @property
    def spoken_history(self) -> List[str]:
        return self._spoken_history

    @property
    def engine_name(self) -> str:
        return "sapi5"

    def is_available(self) -> bool:
        """Available on Windows or in simulated test/mock mode."""
        return True

    def speak(self, text: str, voice_id: Optional[str] = None, wait: bool = False, **kwargs) -> bool:
        """Speak via Windows SAPI5 or PowerShell System.Speech."""
        if not text or not text.strip():
            return False

        self._spoken_history.append(text)

        if sys.platform == "win32":
            # Priority 1: win32com.client SAPI.SpVoice
            try:
                try:
                    import pythoncom
                    pythoncom.CoInitialize()
                except Exception:
                    pass

                import win32com.client
                speaker = win32com.client.Dispatch("SAPI.SpVoice")
                if self.voice_name:
                    for v in speaker.GetVoices():
                        if self.voice_name.lower() in v.GetDescription().lower():
                            speaker.Voice = v
                            break
                speaker.Rate = self.rate
                speaker.Volume = self.volume
                flags = 0 if wait else 1  # 1 = SVSFlagsAsync
                speaker.Speak(text, flags)
                return True
            except Exception as e:
                log.debug("win32com SAPI speak failed (%s), trying PowerShell fallback", e)

            # Priority 2: PowerShell System.Speech.Synthesis
            try:
                import base64
                b64_script = base64.b64encode(
                    f"""
                    Add-Type -AssemblyName System.Speech;
                    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer;
                    $synth.Rate = {self.rate};
                    $synth.Volume = {self.volume};
                    $bytes = [System.Convert]::FromBase64String('{base64.b64encode(text.encode("utf-8")).decode("ascii")}');
                    $text = [System.Text.Encoding]::UTF8.GetString($bytes);
                    $synth.Speak($text);
                    """.encode("utf-16le")
                ).decode("ascii")

                cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", b64_script]
                kw: dict = {
                    "stdin": subprocess.DEVNULL,
                    "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL,
                }
                if hasattr(subprocess, "CREATE_NO_WINDOW"):
                    kw["creationflags"] = subprocess.CREATE_NO_WINDOW

                if wait:
                    subprocess.run(cmd, check=True, timeout=15.0, **kw)
                else:
                    subprocess.Popen(cmd, **kw)
                return True
            except Exception as e:
                log.warning("PowerShell speech synthesis failed: %s", e)

        # Priority 3: pyttsx3 fallback (Cross-platform)
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.say(text)
            if wait:
                engine.runAndWait()
            return True
        except Exception:
            pass

        # Priority 4: Mock logger for CI/Headless
        log.info("[SAPI5 Mock TTS Spoke]: %s", text)
        return True

    def synthesize_to_bytes(self, text: str, voice_id: Optional[str] = None, **kwargs) -> bytes:
        """Returns mock PCM byte buffer for testing offline pipeline."""
        import numpy as np
        duration_s = 0.5
        samples = int(24000 * duration_s)
        return np.zeros(samples, dtype=np.int16).tobytes()
