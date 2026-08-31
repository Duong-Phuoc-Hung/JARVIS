"""
jarvis/security/prompt_guard.py
===============================
Prompt Injection Defense & Content Sanitization Pipeline (R4).
Sanitizes and isolates untrusted web pages, DOM snippets, structured metadata,
and screen perception / vision text before feeding into LLM prompts.

Features:
- Unicode NFKC normalization to neutralize homoglyphs and formatted symbols.
- Zero-width character and hidden control code stripping.
- Delimiter spoofing neutralization (ChatML, Llama [INST], Anthropic/Markdown markers).
- Instruction override and goal hijacking detection (Bilingual EN + VI).
- Data exfiltration payload neutralization (Markdown image / tracking links).
- Structural XML isolation wrapping (<untrusted_external_content>).
"""
from __future__ import annotations

import html as html_module
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("jarvis.security.prompt_guard")


class SanitizationResult(str):
    """
    String subclass representing sanitized untrusted content enclosed in XML isolation boundaries.
    Acts identically to a standard Python `str` while providing metadata attributes
    (clean_text, is_suspicious, detected_patterns, risk_level, source).
    """
    clean_text: str
    original_length: int
    cleaned_length: int
    is_suspicious: bool
    detected_patterns: list[str]
    risk_level: str
    source: str

    def __new__(
        cls,
        wrapped_text: str,
        clean_text: str = "",
        original_length: int = 0,
        cleaned_length: int = 0,
        is_suspicious: bool = False,
        detected_patterns: list[str] | None = None,
        risk_level: str = "LOW",
        source: str = "web",
    ) -> SanitizationResult:
        obj = super().__new__(cls, wrapped_text)
        obj.clean_text = clean_text or wrapped_text
        obj.original_length = original_length
        obj.cleaned_length = cleaned_length
        obj.is_suspicious = is_suspicious
        obj.detected_patterns = detected_patterns or []
        obj.risk_level = risk_level
        obj.source = source
        return obj


class PromptGuard:
    """
    Multi-stage sanitizer isolating untrusted web and vision content
    from contaminating LLM system instructions.
    """

    # Zero-width spaces and hidden bidirectional control characters
    ZERO_WIDTH_CHARS = re.compile(r"[\u200B-\u200D\uFEFF\u00AD\u202A-\u202E\u2066-\u2069]")

    # Raw script tags (especially with system payloads)
    SCRIPT_TAG_PATTERN = re.compile(r"<script[^>]*>([\s\S]*?)</script>", re.IGNORECASE)

    # Chat and system template delimiters
    DELIMITER_PATTERNS = [
        re.compile(r"<\|(?:im_start|im_end|system|user|assistant|endoftext|turn_start|turn_end)\|>", re.IGNORECASE),
        re.compile(r"\[/?INST\]|<<SYS>>|<</SYS>>|\[/?SYSTEM\]", re.IGNORECASE),
        re.compile(r"###\s*(?:System|Instruction|Human|Assistant|User):", re.IGNORECASE),
        re.compile(r"<script[^>]*>\s*(?:SYSTEM|JAILBREAK):[^<]*</script>", re.IGNORECASE),
        re.compile(r"<!--\s*(?:SYSTEM|INSTRUCTION|PROMPT|JAILBREAK):?[^>]*-->", re.IGNORECASE),
    ]

    # Direct instruction override, persona hijacking, and jailbreaks (EN + VI)
    OVERRIDE_PATTERNS = [
        # English instruction override & goal hijacking
        re.compile(
            r"(?i)\b(?:ignore|disregard|forget|override|bypass|clear|reset)\s+(?:all\s+)?"
            r"(?:previous|prior|system|earlier|existing|above)\s+"
            r"(?:instructions|directives|prompts|rules|commands|constraints|guidelines)\b"
        ),
        # English persona hijacking & jailbreaks
        re.compile(
            r"(?i)\b(?:you are no longer \w+|you are now (?:in )?(?:DAN|developer mode)|jailbroken|jailbreak|"
            r"developer mode enabled|unrestricted mode|god mode|always obey the user)\b"
        ),
        # Destructive system commands in untrusted payload
        re.compile(
            r"(?i)\b(?:delete all files|format\s+[a-z]:?|drop database|"
            r"rm\s+-rf(?:\s+[/~])?|del\s+/[sfq](?:\s+[a-z]:?)?)(?=\s|$|[.,;!?])"
        ),
        # English prompt injection prefix spoofing
        re.compile(
            r"(?i)\b(?:new instruction:|system prompt:|system override:|system message:|system instruction:|system:)"
        ),
        # HTML comment system injection
        re.compile(
            r"(?i)<!--\s*system:[^>]*-->"
        ),
        # Vietnamese instruction override & goal hijacking
        re.compile(
            r"(?i)\b(?:bỏ qua|hủy bỏ|quên|vượt qua|xóa)\s+(?:tất cả\s+)?"
            r"(?:chỉ dẫn|hướng dẫn|lệnh|mệnh lệnh|quy tắc|ràng buộc)\s+"
            r"(?:trước|trước đó|hệ thống|cũ|ban đầu)\b"
        ),
        # Vietnamese persona hijacking & jailbreaks
        re.compile(
            r"(?i)\b(?:bạn bây giờ là|chế độ không giới hạn|chế độ nhà phát triển|"
            r"vượt qua kiểm duyệt|bỏ qua kiểm duyệt)\b"
        ),
        # Vietnamese destructive commands
        re.compile(
            r"(?i)\b(?:xóa toàn bộ (?:tệp|file|dữ liệu)|format ổ(?:\s+[a-z]:?)?|xóa cơ sở dữ liệu)(?=\s|$|[.,;!?])"
        ),
    ]

    # Markdown / Image data exfiltration patterns
    EXFILTRATION_PATTERNS = [
        re.compile(
            r"!\[.*?\]\(https?://[^)]*(?:exfil|steal|log\?|token=|key=|data=)[^)]*\)",
            re.IGNORECASE,
        ),
    ]

    @classmethod
    def sanitize(cls, content: str | None, source: str = "web") -> SanitizationResult:
        """
        Sanitizes raw untrusted text, strips injection vectors, normalizes Unicode,
        and wraps the output in XML quarantine boundaries (<untrusted_external_content>).

        Returns a SanitizationResult (subclass of str) conforming to PROJECT.md interface.
        """
        if not content:
            empty_wrapped = f'<untrusted_external_content source="{source}">\n\n</untrusted_external_content>'
            return SanitizationResult(
                wrapped_text=empty_wrapped,
                clean_text="",
                original_length=0,
                cleaned_length=0,
                is_suspicious=False,
                detected_patterns=[],
                risk_level="LOW",
                source=source,
            )

        orig_len = len(content)
        detected: list[str] = []

        # 1. Unicode NFKC normalization (collapses homoglyphs, math formatting, fullwidth chars)
        normalized = unicodedata.normalize("NFKC", content)

        # 2. Strip zero-width and invisible control characters
        normalized = cls.ZERO_WIDTH_CHARS.sub("", normalized)

        # 3. Strip <script>...</script> tags entirely from untrusted text
        if cls.SCRIPT_TAG_PATTERN.search(normalized):
            detected.append("SCRIPT_TAG")
            normalized = cls.SCRIPT_TAG_PATTERN.sub(r"\1", normalized)

        # 4. Neutralize template and chat delimiters
        for pat in cls.DELIMITER_PATTERNS:
            if pat.search(normalized):
                detected.append(pat.pattern)
                normalized = pat.sub("[NEUTRALIZED_DELIMITER]", normalized)

        # 5. Neutralize direct instruction overrides and jailbreaks
        for pat in cls.OVERRIDE_PATTERNS:
            if pat.search(normalized):
                detected.append(pat.pattern)
                normalized = pat.sub("[REDACTED_INJECTION_ATTEMPT]", normalized)

        # 6. Neutralize markdown image / data exfiltration patterns
        for pat in cls.EXFILTRATION_PATTERNS:
            if pat.search(normalized):
                detected.append(pat.pattern)
                normalized = pat.sub("[BLOCKED_EXFILTRATION_LINK]", normalized)

        # Clean any remaining redundant whitespace created by redactions
        normalized = re.sub(r"[ \t]+", " ", normalized).strip()

        # Neutralize any existing raw untrusted_external_content tags to prevent XML escaping
        normalized_escaped = (
            normalized.replace("</untrusted_external_content>", "&lt;/untrusted_external_content&gt;")
            .replace("<untrusted_external_content", "&lt;untrusted_external_content")
        )

        is_suspicious = len(detected) > 0
        risk = "HIGH" if is_suspicious else "LOW"

        if is_suspicious:
            log.warning(
                "PromptGuard detected suspicious injection patterns (%d matches) in content from '%s'",
                len(detected),
                source,
            )

        wrapped = (
            f'<untrusted_external_content source="{source}">\n'
            f"{normalized_escaped}\n"
            f"</untrusted_external_content>"
        )

        return SanitizationResult(
            wrapped_text=wrapped,
            clean_text=normalized,
            original_length=orig_len,
            cleaned_length=len(normalized),
            is_suspicious=is_suspicious,
            detected_patterns=detected,
            risk_level=risk,
            source=source,
        )

    @classmethod
    def contains_injection(cls, content: str | None) -> tuple[bool, str | None]:
        """
        Checks whether content contains malicious prompt injection / jailbreak signatures.

        Returns:
            (True, matched_pattern) if an injection pattern is detected, else (False, None).
        """
        if not content:
            return False, None

        # Pre-normalize for accurate detection
        normalized = unicodedata.normalize("NFKC", content)
        normalized = cls.ZERO_WIDTH_CHARS.sub("", normalized)

        # Check script tags
        if cls.SCRIPT_TAG_PATTERN.search(normalized):
            return True, "SCRIPT_TAG"

        # Check delimiters
        for pat in cls.DELIMITER_PATTERNS:
            m = pat.search(normalized)
            if m:
                return True, m.group(0)

        # Check instruction overrides
        for pat in cls.OVERRIDE_PATTERNS:
            m = pat.search(normalized)
            if m:
                return True, m.group(0)

        # Check exfiltration
        for pat in cls.EXFILTRATION_PATTERNS:
            m = pat.search(normalized)
            if m:
                return True, m.group(0)

        return False, None

    @classmethod
    def wrap_untrusted_context(cls, content: str, source: str = "web") -> str:
        """
        Sanitizes untrusted text and encloses it within XML isolation boundaries.

        Format:
        <untrusted_external_content source="{source}" risk="{risk_level}">
        {sanitized_content}
        </untrusted_external_content>
        """
        sanitized = cls.sanitize(content, source=source)
        return (
            f'<untrusted_external_content source="{source}" risk="{sanitized.risk_level}">\n'
            f"{sanitized.clean_text}\n"
            f"</untrusted_external_content>"
        )

    # Aliases for interface compatibility
    wrap_untrusted_content = wrap_untrusted_context
    sanitize_and_wrap = wrap_untrusted_context
