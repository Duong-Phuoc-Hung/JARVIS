"""
jarvis/stt/contextual_biaser.py
===============================
Dynamic Contextual Biasing in Whisper Initial Prompt (Argon Sovereign Frontier 4).
Generates dynamic, hyper-concise initial prompts (strictly <= 15 tokens) based on active
window context from AWACIEngine (Active Window & Context Injection).
Steers Whisper ASR toward active application vocabulary while strictly preventing
prompt regurgitation hallucinations through tight token bounds.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from jarvis.context.screen_context import AWACIEngine, WindowContext

logger = logging.getLogger("jarvis.stt.contextual_biaser")

# Strict maximum token budget for Whisper initial_prompt to prevent regurgitation hallucination
MAX_INITIAL_PROMPT_TOKENS: int = 15

# Hyper-concise category prompt templates (tuned for Vietnamese ASR steering)
_CATEGORY_BIAS_PROMPTS: dict[str, str] = {
    "code_editor": "Lập trình: code, visual studio, file, debug",
    "browser": "Trình duyệt: youtube, chrome, web, tìm kiếm",
    "terminal": "Dòng lệnh: terminal, powershell, git, run",
    "media_player": "Nhạc: spotify, video, bài hát, âm lượng",
    "document_editor": "Văn bản: word, excel, tài liệu, lưu",
    "system": "Hệ thống: cài đặt, cửa sổ, màn hình, ứng dụng",
    "other": "Điều khiển: mở, đóng, tìm kiếm, jarvis",
}

# Fine-grained sub-context bias overrides
_SUBCONTEXT_BIAS_OVERRIDES: dict[str, str] = {
    "youtube_video": "Video: youtube, phát, dừng, phóng to",
    "code_workspace": "Lập trình: code, visual studio, file, debug",
    "music_playback": "Nhạc: spotify, phát nhạc, bài hát, âm lượng",
    "web_document": "Trang web: đọc tin tức, tài liệu, chrome",
}


def count_tokens(text: str) -> int:
    """
    Estimates token count for Vietnamese + English text.
    Uses regex word and punctuation tokenization approximating BPE subwords.
    """
    if not text or not text.strip():
        return 0
    # Split on words and punctuation marks
    tokens = re.findall(r"\w+|[^\w\s]", text.strip(), re.UNICODE)
    return len(tokens)


def cap_prompt_tokens(prompt: str, max_tokens: int = MAX_INITIAL_PROMPT_TOKENS) -> str:
    """
    Strictly caps prompt text to at most max_tokens tokens.
    Guarantees no prompt regurgitation hallucination by truncating excess tokens
    and cleanly stripping trailing punctuation.
    """
    if not prompt or not prompt.strip() or max_tokens <= 0:
        return ""

    tokens = re.findall(r"\w+|[^\w\s]", prompt.strip(), re.UNICODE)
    if len(tokens) <= max_tokens:
        return prompt.strip().rstrip(",;: ")

    # Reconstruct string with capped tokens
    capped_tokens = tokens[:max_tokens]
    result: list[str] = []
    for i, tok in enumerate(capped_tokens):
        if i > 0 and tok not in (",", ".", ":", ";", "!", "?") and not result[-1].endswith(":"):
            result.append(" ")
        elif i > 0 and result[-1].endswith(":") and not tok.startswith(" "):
            result.append(" ")
        result.append(tok)

    return "".join(result).strip().rstrip(",;: ")


class ContextualPromptBiaser:
    """
    Inspects active foreground window context via AWACIEngine and produces
    hyper-concise initial prompts for Whisper decoding.
    """

    def __init__(
        self,
        awaci_engine: AWACIEngine | None = None,
        max_tokens: int = MAX_INITIAL_PROMPT_TOKENS,
        enabled: bool = True,
    ) -> None:
        self.awaci_engine = awaci_engine or AWACIEngine()
        self.max_tokens = int(max_tokens)
        self.enabled = bool(enabled)

    def get_bias_prompt(self, context: WindowContext | None = None) -> str:
        """
        Generates dynamic initial prompt from provided or freshly fetched active window context.
        Guarantees returned prompt is strictly <= max_tokens.
        """
        if not self.enabled:
            return ""

        win_ctx: WindowContext | None = context
        if win_ctx is None and self.awaci_engine is not None:
            try:
                if hasattr(self.awaci_engine, "get_active_window_context"):
                    win_ctx = self.awaci_engine.get_active_window_context()
                elif hasattr(self.awaci_engine, "get_current_window_context"):
                    win_ctx = self.awaci_engine.get_current_window_context()
            except Exception as e:
                logger.debug("Failed fetching active window context for biasing: %s", e)
                win_ctx = None

        if win_ctx is None or not win_ctx.is_valid:
            return cap_prompt_tokens(_CATEGORY_BIAS_PROMPTS["other"], self.max_tokens)

        # 1. Check sub-context override first
        if win_ctx.sub_context in _SUBCONTEXT_BIAS_OVERRIDES:
            raw_prompt = _SUBCONTEXT_BIAS_OVERRIDES[win_ctx.sub_context]
            return cap_prompt_tokens(raw_prompt, self.max_tokens)

        # 2. Check application category
        category = getattr(win_ctx, "app_category", "other") or "other"
        raw_prompt = _CATEGORY_BIAS_PROMPTS.get(category, _CATEGORY_BIAS_PROMPTS["other"])

        # 3. If process name is specific (e.g. devenv, cursor, pycharm), enrich if room permits
        proc = getattr(win_ctx, "process_name", "").lower()
        if "cursor" in proc or "pycharm" in proc:
            raw_prompt = "Lập trình: python, code, file, debug"
        elif "spotify" in proc:
            raw_prompt = "Nhạc: spotify, bài hát, phát, dừng"

        return cap_prompt_tokens(raw_prompt, self.max_tokens)


__all__ = [
    "ContextualPromptBiaser",
    "MAX_INITIAL_PROMPT_TOKENS",
    "cap_prompt_tokens",
    "count_tokens",
]
