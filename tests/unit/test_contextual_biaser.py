"""
tests/unit/test_contextual_biaser.py
====================================
Unit & Safety Verification for Dynamic Contextual Biasing in Whisper Initial Prompt
(Argon Sovereign Frontier 4).
Validates:
  - Token cap enforcement: strictly <= 15 tokens to prevent prompt regurgitation hallucination.
  - Active window context steering:
    - Code editor (VS Code, Cursor, PyCharm) -> 'Lập trình: code, visual studio, file, debug'
    - Browser (Chrome, Edge) -> 'Trình duyệt: youtube, chrome, web, tìm kiếm'
    - YouTube video sub-context -> 'Video: youtube, phát, dừng, phóng to'
    - Terminal (PowerShell, CMD, Bash) -> 'Dòng lệnh: terminal, powershell, git, run'
    - Media player (Spotify, VLC) -> 'Nhạc: spotify, video, bài hát, âm lượng'
    - Document editor (Word, Excel) -> 'Văn bản: word, excel, tài liệu, lưu'
  - Seamless wiring with DynamicTieredASREngine and FasterWhisperEngine.
"""
from __future__ import annotations

from unittest.mock import MagicMock
import numpy as np
import pytest

from jarvis.context.screen_context import AWACIEngine, WindowContext
from jarvis.stt.contextual_biaser import (
    MAX_INITIAL_PROMPT_TOKENS,
    ContextualPromptBiaser,
    cap_prompt_tokens,
    count_tokens,
)
from jarvis.stt.dynamic_tiered import DynamicTieredASREngine
from jarvis.stt.engine import BaseSTTEngine, STTMetricsResult
from jarvis.stt.faster_whisper import FasterWhisperEngine, FasterWhisperSTTEngine


class TestContextualPromptBiaser:
    """Unit tests for ContextualPromptBiaser and token safety capping."""

    def test_token_capping_under_limit(self) -> None:
        """Prompts under 15 tokens are preserved verbatim."""
        p = "Lập trình: code, visual studio, file, debug"
        assert count_tokens(p) <= MAX_INITIAL_PROMPT_TOKENS
        assert cap_prompt_tokens(p, max_tokens=15) == p

    def test_token_capping_strictly_enforced_on_long_prompts(self) -> None:
        """Prompts exceeding 15 tokens are strictly truncated to <= 15 tokens."""
        long_prompt = (
            "Ứng dụng lập trình Visual Studio Code, Cursor IDE, PyCharm, Sublime Text, "
            "Python, C++, Java, Rust, Docker, Kubernetes, Git, Terminal, Debugging, Testing"
        )
        assert count_tokens(long_prompt) > 15
        capped = cap_prompt_tokens(long_prompt, max_tokens=15)
        assert count_tokens(capped) <= 15
        # Must not be empty and must be bounded
        assert len(capped) > 0

    def test_code_editor_bias_prompt(self) -> None:
        """Generates programming-oriented bias prompt when in VS Code."""
        ctx = WindowContext(
            hwnd=1001,
            title="main.py - JARVIS - Visual Studio Code",
            process_name="code.exe",
            app_category="code_editor",
            sub_context="code_workspace",
            is_valid=True,
        )
        biaser = ContextualPromptBiaser()
        prompt = biaser.get_bias_prompt(context=ctx)
        assert "Lập trình:" in prompt
        assert count_tokens(prompt) <= MAX_INITIAL_PROMPT_TOKENS

    def test_browser_bias_prompt(self) -> None:
        """Generates web/browser-oriented bias prompt when in Chrome/Edge."""
        ctx = WindowContext(
            hwnd=1002,
            title="Google - Google Chrome",
            process_name="chrome.exe",
            app_category="browser",
            sub_context="general",
            is_valid=True,
        )
        biaser = ContextualPromptBiaser()
        prompt = biaser.get_bias_prompt(context=ctx)
        assert "Trình duyệt:" in prompt
        assert count_tokens(prompt) <= MAX_INITIAL_PROMPT_TOKENS

    def test_youtube_subcontext_bias_prompt(self) -> None:
        """Generates video playback prompt when on YouTube in browser."""
        ctx = WindowContext(
            hwnd=1003,
            title="Độ Mixi Live Stream - YouTube - Google Chrome",
            process_name="chrome.exe",
            app_category="browser",
            sub_context="youtube_video",
            is_valid=True,
        )
        biaser = ContextualPromptBiaser()
        prompt = biaser.get_bias_prompt(context=ctx)
        assert "Video:" in prompt
        assert count_tokens(prompt) <= MAX_INITIAL_PROMPT_TOKENS

    def test_terminal_bias_prompt(self) -> None:
        """Generates command line prompt when in Windows Terminal / PowerShell."""
        ctx = WindowContext(
            hwnd=1004,
            title="Windows PowerShell",
            process_name="powershell.exe",
            app_category="terminal",
            sub_context="general",
            is_valid=True,
        )
        biaser = ContextualPromptBiaser()
        prompt = biaser.get_bias_prompt(context=ctx)
        assert "Dòng lệnh:" in prompt
        assert count_tokens(prompt) <= MAX_INITIAL_PROMPT_TOKENS

    def test_media_player_bias_prompt(self) -> None:
        """Generates music playback prompt when in Spotify."""
        ctx = WindowContext(
            hwnd=1005,
            title="Spotify Free",
            process_name="spotify.exe",
            app_category="media_player",
            sub_context="music_playback",
            is_valid=True,
        )
        biaser = ContextualPromptBiaser()
        prompt = biaser.get_bias_prompt(context=ctx)
        assert "Nhạc:" in prompt
        assert count_tokens(prompt) <= MAX_INITIAL_PROMPT_TOKENS

    def test_document_editor_bias_prompt(self) -> None:
        """Generates document editing prompt when in Microsoft Word."""
        ctx = WindowContext(
            hwnd=1006,
            title="Document1 - Microsoft Word",
            process_name="winword.exe",
            app_category="document_editor",
            sub_context="general",
            is_valid=True,
        )
        biaser = ContextualPromptBiaser()
        prompt = biaser.get_bias_prompt(context=ctx)
        assert "Văn bản:" in prompt
        assert count_tokens(prompt) <= MAX_INITIAL_PROMPT_TOKENS

    def test_invalid_or_headless_context_fallback(self) -> None:
        """Falls back safely to default control prompt when window context is invalid."""
        ctx = WindowContext(is_valid=False)
        biaser = ContextualPromptBiaser()
        prompt = biaser.get_bias_prompt(context=ctx)
        assert "Điều khiển:" in prompt
        assert count_tokens(prompt) <= MAX_INITIAL_PROMPT_TOKENS


class MockUnderlyingEngine(BaseSTTEngine):
    """Mock STT engine recording received initial_prompt for verification."""

    def __init__(self) -> None:
        super().__init__()
        self.last_initial_prompt: str | None = None

    @property
    def engine_name(self) -> str:
        return "mock_underlying_engine"

    def is_available(self) -> bool:
        return True

    def transcribe(self, audio, language: str = "vi", **kwargs) -> str:
        self.last_initial_prompt = kwargs.get("initial_prompt")
        return "bật visual studio code"

    def transcribe_with_metrics(self, audio, language: str = "vi", **kwargs) -> STTMetricsResult:
        self.last_initial_prompt = kwargs.get("initial_prompt")
        return STTMetricsResult(text="bật visual studio code", avg_logprob=-0.2, no_speech_prob=0.01, duration_ms=10.0)


class TestASREngineContextualBiasingWiring:
    """Verifies wiring into DynamicTieredASREngine and FasterWhisperEngine."""

    def test_dynamic_tiered_asr_injects_bias_prompt(self) -> None:
        """DynamicTieredASREngine passes contextual prompt to underlying engine."""
        mock_awaci = MagicMock(spec=AWACIEngine)
        mock_awaci.get_active_window_context.return_value = WindowContext(
            hwnd=1001,
            title="code.py - Visual Studio Code",
            process_name="code.exe",
            app_category="code_editor",
            is_valid=True,
        )
        biaser = ContextualPromptBiaser(awaci_engine=mock_awaci)

        mock_small = MockUnderlyingEngine()
        asr = DynamicTieredASREngine(
            config={"device": "cpu"},
            small_engine=mock_small,
            contextual_biaser=biaser,
        )

        dummy_audio = np.ones(16000 * 2, dtype=np.float32) * 0.1  # 2 seconds
        res = asr.transcribe(dummy_audio)
        assert res.is_success is True
        assert mock_small.last_initial_prompt is not None
        assert "Lập trình:" in mock_small.last_initial_prompt

    def test_faster_whisper_engine_contextual_prompt(self) -> None:
        """FasterWhisperEngine / FasterWhisperSTTEngine mock transcribe receives bias prompt."""
        mock_awaci = MagicMock(spec=AWACIEngine)
        mock_awaci.get_active_window_context.return_value = WindowContext(
            hwnd=1002,
            title="Chrome",
            process_name="chrome.exe",
            app_category="browser",
            is_valid=True,
        )
        biaser = ContextualPromptBiaser(awaci_engine=mock_awaci)
        engine = FasterWhisperEngine(is_mock=True, contextual_biaser=biaser)

        dummy_bytes = b"\x00" * 32000
        res = engine.transcribe(dummy_bytes)
        assert res.is_mock is True
        assert "Trình duyệt:" in res.text
