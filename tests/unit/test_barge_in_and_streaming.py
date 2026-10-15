"""
tests/unit/test_barge_in_and_streaming.py
=========================================
Unit and integration tests for:
1. Barge-in speech interruption (tts_stop / barge_in dispatcher action, PTT interrupt).
2. Sentence-level streaming TTS for low-latency time-to-first-audio.
3. Whisper sliding window Vietnamese phonetic aliases matching.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from jarvis.audio.wake_word import WhisperSlidingWindowDetector
from jarvis.core.app import JarvisApp
from jarvis.tts.manager import TTSManager


def test_whisper_vietnamese_phonetic_aliases():
    """Verify WhisperSlidingWindowDetector correctly normalizes and recognizes Vietnamese aliases."""
    detector = WhisperSlidingWindowDetector()

    # Verify new Vietnamese aliases are present in keywords
    assert "chao jarvis" in detector.keywords
    assert "oi jarvis" in detector.keywords
    assert "e jarvis" in detector.keywords
    assert "tra vit" in detector.keywords

    # Verify normalization matches various diacritic and case variations
    assert detector._contains_wake_alias("Chào JARVIS") is True
    assert detector._contains_wake_alias("chào jarvis em ơi") is True
    assert detector._contains_wake_alias("Ơi Jarvis, giúp tôi với") is True
    assert detector._contains_wake_alias("Ê Jarvis") is True
    assert detector._contains_wake_alias("Trà Vít mở nhạc lên") is True
    assert detector._contains_wake_alias("Giá Vít bật đèn") is True

    # Negative cases (unrelated words)
    assert detector._contains_wake_alias("xin chào bạn") is False
    assert detector._contains_wake_alias("thời tiết hôm nay thế nào") is False


def test_barge_in_dispatcher_action():
    """Verify tts_stop and barge_in actions interrupt TTS via dispatcher."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    mock_tts = MagicMock(spec=TTSManager)
    mock_tts.interrupt.return_value = True
    mock_tts.is_playing = True
    app.tts_manager = mock_tts

    # Dispatch 'tts_stop'
    result_stop = app.dispatcher.dispatch("tts_stop")
    assert result_stop.success is True
    assert result_stop.data.get("interrupted") is True
    mock_tts.interrupt.assert_called_once()

    mock_tts.interrupt.reset_mock()

    # Dispatch 'barge_in' alias
    result_barge = app.dispatcher.dispatch("barge_in")
    assert result_barge.success is True
    assert result_barge.data.get("interrupted") is True
    mock_tts.interrupt.assert_called_once()

    app.stop()


def test_start_voice_interaction_interrupts_active_tts():
    """Verify starting voice interaction immediately interrupts active TTS playback (barge-in)."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    mock_tts = MagicMock(spec=TTSManager)
    mock_tts.is_playing = True
    mock_tts.interrupt.return_value = True
    app.tts_manager = mock_tts

    # Mock record_audio and stt_engine to avoid blocking
    app.record_audio = MagicMock(return_value=[0.0] * 1600)
    mock_stt = MagicMock()
    mock_stt.transcribe.return_value = ""
    app.stt_engine = mock_stt

    # Start interaction synchronously
    app._start_voice_interaction(trigger_name="HOTKEY_PTT", greeting_phrase="", sync=True)

    # Verify interrupt was called immediately upon interaction start
    assert mock_tts.interrupt.call_count >= 1

    app.stop()


def test_voice_interaction_sentence_level_streaming():
    """Verify voice loop splits response into conversational sentences for streaming speech."""
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()

    mock_tts = MagicMock(spec=TTSManager)
    mock_tts.is_playing = False
    mock_tts.split_sentences.side_effect = TTSManager.split_sentences
    mock_tts.speak_sentences.return_value = True
    app.tts_manager = mock_tts

    # Mock text command returning multi-sentence response
    multi_sentence_text = "Hệ thống đang hoạt động tối ưu. Nhiệt độ CPU là 45 độ C. Bạn có cần hỗ trợ gì khác không?"
    app.process_text_command = MagicMock(return_value={"response_text": multi_sentence_text})
    app.record_audio = MagicMock(return_value=[0.0] * 1600)
    mock_stt = MagicMock()
    mock_stt.transcribe.return_value = "báo cáo hệ thống"
    app.stt_engine = mock_stt

    # Execute voice interaction
    app._start_voice_interaction(trigger_name="HOTKEY_PTT", greeting_phrase="", sync=True)

    # Verify speak_sentences was called with the individual sentences
    mock_tts.speak_sentences.assert_called_once()
    called_sentences = mock_tts.speak_sentences.call_args[0][0]
    assert len(called_sentences) == 3
    assert called_sentences[0] == "Hệ thống đang hoạt động tối ưu."
    assert called_sentences[1] == "Nhiệt độ CPU là 45 độ C."
    assert called_sentences[2] == "Bạn có cần hỗ trợ gì khác không?"

    app.stop()


def test_router_barge_in_and_tts_stop_phrases():
    """Verify LLMIntentRouter maps speech interruption phrases to action 'tts_stop'."""
    from jarvis.llm.client import LLMClient
    from jarvis.llm.router import LLMIntentRouter

    router = LLMIntentRouter(llm_client=MagicMock(spec=LLMClient), fast_path_enabled=True)

    phrases = [
        "dừng nói",
        "dừng phát",
        "dừng âm thanh",
        "im lặng",
        "im đi",
        "thôi im đi",
        "stop talking",
        "be quiet",
        "shut up",
        "Hey JARVIS, dừng nói",
        "JARVIS im lặng",
    ]

    for p in phrases:
        intent = router.route(p)
        assert intent is not None, f"Expected intent for phrase: {p}"
        assert intent.action_name == "tts_stop", f"Failed for phrase {p}: got {intent.action_name}"
        assert intent.response_text == ""

