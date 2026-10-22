"""
jarvis/nlp/phonetic_normalizer.py
=================================
Vietnamese Acoustic & Phonetic STT Normalizer for Whisper and Speech Engines.
Translates Vietnamese transliterated loan words, teencode, and phonetic speech
transcriptions back to canonical software names, protocols, and technical terms.
"""
from __future__ import annotations

import re
from typing import Pattern

# Common Vietnamese phonetic transliterations from STT engines (Whisper / Vosk / Google Speech)
PHONETIC_REPLACEMENTS: list[tuple[str, str]] = [
    # Applications
    (r"\b(?:cờ\s*rôm|chôm|cơ\s*rôm|co\s*rom)\b", "chrome"),
    (r"\b(?:ét\s*xel|ếch\s*xel|ếch\s*seo|et\s*xel|ech\s*xel|ec\s*xen)\b", "excel"),
    (r"\b(?:quốt|uốt|uôt|quôt)\b", "word"),
    (r"\b(?:sì\s*po\s*ti\s*phai|sờ\s*po\s*ti\s*phai|sì\s*pót\s*ti\s*phai|xì\s*po\s*ti\s*phai|xờ\s*po\s*ti\s*phai)\b", "spotify"),
    (r"\b(?:phây\s*búc|phây|phây\s*book|phe\s*buc)\b", "facebook"),
    (r"\b(?:vê\s*ét\s*cốt|vê\s*ét\s*code|vi\s*ét\s*cốt|ve\s*et\s*code)\b", "vscode"),
    (r"\b(?:tê\s*lê\s*gam|te\s*le\s*gram|tê\s*lê\s*gram)\b", "telegram"),
    (r"\b(?:nốt\s*pét|nốt\s*pad|not\s*pad)\b", "notepad"),
    (r"\b(?:mai\s*cờ\s*rô\s*xốp|mai\s*cờ\s*rô\s*xóp|mai\s*co\s*ro\s*xop)\b", "microsoft"),
    (r"\b(?:gu\s*gồ|gúc\s*gồ|gút\s*gồ|gu\s*go)\b", "google"),
    (r"\b(?:bai\s*thần|pai\s*thơn|pai\s*thon)\b", "python"),
    (r"\b(?:pao\s*o\s*seo|pao\s*guốc\s*seo|pao\s*o\s*shell)\b", "powershell"),
    (r"\b(?:tát\s*man\s*nơ\s*giơ|tát\s*man\s*nơ\s*dơ|tát\s*mát\s*nơ\s*giơ)\b", "task manager"),
    (r"\b(?:cam\s*pu\s*tơ|con\s*pu\s*tơ|com\s*pu\s*ter)\b", "computer"),

    # Operating System & Hardware
    (r"\b(?:uýt\s*đo|uyn\s*đâu|uyn\s*đo|uynh\s*đo|win\s*đo)\b", "windows"),
    (r"\b(?:wai\s*phai|goai\s*phai|oai\s*phai|oai\s*fai)\b", "wifi"),
    (r"\b(?:bờ\s*lu\s*tút|bu\s*lu\s*tút|blu\s*tut)\b", "bluetooth"),
    (r"\b(?:cờ\s*líp\s*bo|cờ\s*líp\s*bót|cờ\s*lip\s*bo|clip\s*bo)\b", "clipboard"),
    (r"\b(?:xì\s*cờ\s*rin|xờ\s*cờ\s*rin|xờ\s*rin)\b", "screen"),

    # Multimedia & System
    (r"\b(?:bô\s*lum|vo\s*lum|vô\s*lum)\b", "volume"),
    (r"\b(?:sì\s*tóp|xì\s*tóp|xờ\s*tóp)\b", "stop"),
    (r"\b(?:bâu\s*dơ|pao\s*dơ|pau\s*dơ)\b", "pause"),
    (r"\b(?:nét\s*bài|nếch\s*bài|nếch)\b", "next bài"),
]

_COMPILED_RULES: list[tuple[Pattern, str]] = [
    (re.compile(pattern, re.IGNORECASE), replacement)
    for pattern, replacement in PHONETIC_REPLACEMENTS
]


class VietnamesePhoneticNormalizer:
    """
    Normalizes phonetic and acoustic transcription errors in Vietnamese speech input.
    """

    def __init__(self) -> None:
        self.rules = _COMPILED_RULES

    def normalize(self, text: str) -> str:
        """Normalizes phonetically corrupted speech input."""
        if not text:
            return ""
        result = text
        for pattern, replacement in self.rules:
            result = pattern.sub(replacement, result)
        return re.sub(r"\s+", " ", result).strip()


# Module-level singleton helper
_NORMALIZER_INSTANCE = VietnamesePhoneticNormalizer()


def normalize_phonetic_stt(text: str) -> str:
    """Convenience helper to normalize speech text using the singleton normalizer."""
    return _NORMALIZER_INSTANCE.normalize(text)
