"""
tests/unit/test_adversarial_telegram_voice_challenger.py
========================================================
Adversarial Stress Test Suite for Telegram Voice Fail-Closed Remediation (Milestone 1).
Author: Challenger 1 (teamwork_preview_challenger)

Empirically challenges:
1. Immunity against synthetic fallback: 'Lệnh thoại đã nhận' must NEVER be returned under any condition.
2. STT engine severe failure modes: MemoryError, TimeoutError, custom unhandled exceptions.
3. STT return payload corruption: None, empty string, whitespace-only, unexpected types (int, list, dict, float).
4. Audio payload corruption: empty bytes (b""), None voice_bytes, malformed/fuzzed bytes.
5. Parameter boundary conditions: user_id=None, chat_id=None.
"""

from typing import Any
from unittest.mock import MagicMock
import pytest

from jarvis.comms.telegram import TelegramBotController


# Custom exception class to test arbitrary exception resilience
class CustomSTTFailureException(Exception):
    """Simulated custom provider exception."""
    pass


class MalformedAudioEngine:
    """Mock STT engine that validates voice_bytes and raises on corruption."""
    def transcribe(self, voice_bytes: Any) -> str:
        if voice_bytes is None:
            raise ValueError("voice_bytes cannot be None")
        if not isinstance(voice_bytes, (bytes, bytearray)):
            raise TypeError(f"Expected bytes, got {type(voice_bytes)}")
        if len(voice_bytes) == 0:
            raise ValueError("voice_bytes is empty")
        if voice_bytes.startswith(b"\x00\xff\xfe"):
            raise RuntimeError("Corrupt audio header")
        return "Valid transcription"


# ============================================================================
# 1. Verification that "Lệnh thoại đã nhận" is NEVER returned
# ============================================================================

@pytest.mark.parametrize(
    "stt_setup",
    [
        None,  # No STT engine
        object(),  # Engine without transcribe method
        MagicMock(transcribe=MagicMock(side_effect=RuntimeError("CUDA OOM"))),
        MagicMock(transcribe=MagicMock(side_effect=MemoryError("OOM"))),
        MagicMock(transcribe=MagicMock(side_effect=TimeoutError("Timed out"))),
        MagicMock(transcribe=MagicMock(side_effect=CustomSTTFailureException("Crash"))),
        MagicMock(transcribe=MagicMock(return_value="")),
        MagicMock(transcribe=MagicMock(return_value=None)),
        MagicMock(transcribe=MagicMock(return_value="   ")),
        MagicMock(transcribe=MagicMock(return_value=12345)),
    ],
)
def test_adversarial_voice_never_returns_fake_received_text(stt_setup: Any) -> None:
    """Invariant: 'Lệnh thoại đã nhận' must NEVER be produced in any response field."""
    tg = TelegramBotController(bot_token="test_token", allowed_user_ids={12345}, stt_engine=stt_setup)
    try:
        res = tg.handle_inbound_voice(user_id=12345, voice_bytes=b"sample_audio", chat_id=12345)
    except Exception as exc:
        # If an unhandled exception occurred, that is also a failure mode, but definitely did not return the fake string
        res = {"exception": str(exc)}

    res_str = str(res)
    assert "Lệnh thoại đã nhận" not in res_str, f"Found forbidden synthetic text in: {res}"


# ============================================================================
# 2. STT Engine Exception Resilience
# ============================================================================

def test_adversarial_voice_stt_memory_error_fail_closed() -> None:
    """STT engine raising MemoryError must be caught and return STT_UNAVAILABLE."""
    mock_stt = MagicMock()
    mock_stt.transcribe.side_effect = MemoryError("Host system out of memory")

    tg = TelegramBotController(bot_token="test_token", allowed_user_ids={12345}, stt_engine=mock_stt)
    res = tg.handle_inbound_voice(user_id=12345, voice_bytes=b"audio_payload")

    assert res.get("ok") is False
    assert res.get("error_code") == "STT_UNAVAILABLE"
    assert "offline or not configured" in res.get("message", "")


def test_adversarial_voice_stt_timeout_error_fail_closed() -> None:
    """STT engine raising TimeoutError must be caught and return STT_UNAVAILABLE."""
    mock_stt = MagicMock()
    mock_stt.transcribe.side_effect = TimeoutError("Transcription RPC timed out after 30s")

    tg = TelegramBotController(bot_token="test_token", allowed_user_ids={12345}, stt_engine=mock_stt)
    res = tg.handle_inbound_voice(user_id=12345, voice_bytes=b"audio_payload")

    assert res.get("ok") is False
    assert res.get("error_code") == "STT_UNAVAILABLE"
    assert "offline or not configured" in res.get("message", "")


def test_adversarial_voice_stt_custom_exception_fail_closed() -> None:
    """STT engine raising custom provider exception must be caught and return STT_UNAVAILABLE."""
    mock_stt = MagicMock()
    mock_stt.transcribe.side_effect = CustomSTTFailureException("Deepgram network socket closed unexpectedly")

    tg = TelegramBotController(bot_token="test_token", allowed_user_ids={12345}, stt_engine=mock_stt)
    res = tg.handle_inbound_voice(user_id=12345, voice_bytes=b"audio_payload")

    assert res.get("ok") is False
    assert res.get("error_code") == "STT_UNAVAILABLE"
    assert "offline or not configured" in res.get("message", "")


# ============================================================================
# 3. STT Engine Return Payload Stress-Testing (Empty, Whitespace, Unexpected Types)
# ============================================================================

def test_adversarial_voice_stt_returns_none_fail_closed() -> None:
    """STT returning None must trigger fail-closed STT_UNAVAILABLE."""
    mock_stt = MagicMock()
    mock_stt.transcribe.return_value = None

    tg = TelegramBotController(bot_token="test_token", allowed_user_ids={12345}, stt_engine=mock_stt)
    res = tg.handle_inbound_voice(user_id=12345, voice_bytes=b"audio_payload")

    assert res.get("ok") is False
    assert res.get("error_code") == "STT_UNAVAILABLE"


def test_adversarial_voice_stt_returns_empty_string_fail_closed() -> None:
    """STT returning empty string '' must trigger fail-closed STT_UNAVAILABLE."""
    mock_stt = MagicMock()
    mock_stt.transcribe.return_value = ""

    tg = TelegramBotController(bot_token="test_token", allowed_user_ids={12345}, stt_engine=mock_stt)
    res = tg.handle_inbound_voice(user_id=12345, voice_bytes=b"audio_payload")

    assert res.get("ok") is False
    assert res.get("error_code") == "STT_UNAVAILABLE"


@pytest.mark.parametrize(
    "whitespace_text",
    [
        "   ",
        "\t",
        "\n",
        "\r\n",
        "  \t  \n  ",
    ],
)
def test_adversarial_voice_stt_returns_whitespace_fail_closed(whitespace_text: str) -> None:
    """
    STT returning whitespace-only string must NOT be routed as a valid command.
    It MUST fail-closed with STT_UNAVAILABLE instead of returning status 200 with empty command.
    """
    mock_stt = MagicMock()
    mock_stt.transcribe.return_value = whitespace_text

    tg = TelegramBotController(bot_token="test_token", allowed_user_ids={12345}, stt_engine=mock_stt)
    res = tg.handle_inbound_voice(user_id=12345, voice_bytes=b"audio_payload")

    # Anti-fabrication check: must fail-closed, NOT report status 200 with "Đã nhận lệnh: "
    assert res.get("status") != 200, f"Whitespace transcription was falsely accepted as valid command: {res}"
    assert res.get("ok") is False, f"Expected fail-closed ok=False, got: {res}"
    assert res.get("error_code") == "STT_UNAVAILABLE", f"Expected error_code STT_UNAVAILABLE, got: {res}"


@pytest.mark.parametrize(
    "unexpected_payload",
    [
        12345,
        3.14159,
        ["not", "a", "string"],
        {"text": "malformed_json_dict"},
        object(),
    ],
)
def test_adversarial_voice_stt_returns_unexpected_type_fail_closed(unexpected_payload: Any) -> None:
    """
    STT returning unexpected non-string type must NOT crash with unhandled AttributeError.
    It MUST fail-closed safely with STT_UNAVAILABLE.
    """
    mock_stt = MagicMock()
    mock_stt.transcribe.return_value = unexpected_payload

    tg = TelegramBotController(bot_token="test_token", allowed_user_ids={12345}, stt_engine=mock_stt)
    res = tg.handle_inbound_voice(user_id=12345, voice_bytes=b"audio_payload")

    assert res.get("ok") is False, f"Expected fail-closed ok=False, got: {res}"
    assert res.get("error_code") == "STT_UNAVAILABLE", f"Expected error_code STT_UNAVAILABLE, got: {res}"


# ============================================================================
# 4. Audio Payload Stress-Testing (Empty bytes, None bytes, Malformed bytes)
# ============================================================================

def test_adversarial_voice_empty_bytes_with_raising_stt_fail_closed() -> None:
    """Empty audio bytes b'' raising in STT must fail-closed with STT_UNAVAILABLE."""
    tg = TelegramBotController(
        bot_token="test_token",
        allowed_user_ids={12345},
        stt_engine=MalformedAudioEngine(),
    )
    res = tg.handle_inbound_voice(user_id=12345, voice_bytes=b"")

    assert res.get("ok") is False
    assert res.get("error_code") == "STT_UNAVAILABLE"


def test_adversarial_voice_empty_bytes_handler_guard_fail_closed() -> None:
    """Empty audio bytes b'' must fail-closed with STT_UNAVAILABLE even if STT returns text."""
    mock_stt = MagicMock()
    mock_stt.transcribe.return_value = "phantom_command"

    tg = TelegramBotController(bot_token="test_token", allowed_user_ids={12345}, stt_engine=mock_stt)
    res = tg.handle_inbound_voice(user_id=12345, voice_bytes=b"")

    assert res.get("ok") is False
    assert res.get("error_code") == "STT_UNAVAILABLE"


def test_adversarial_voice_none_bytes_handler_guard_fail_closed() -> None:
    """None voice_bytes must fail-closed with STT_UNAVAILABLE even if STT returns text."""
    mock_stt = MagicMock()
    mock_stt.transcribe.return_value = "phantom_command"

    tg = TelegramBotController(bot_token="test_token", allowed_user_ids={12345}, stt_engine=mock_stt)
    res = tg.handle_inbound_voice(user_id=12345, voice_bytes=None)  # type: ignore[arg-type]

    assert res.get("ok") is False
    assert res.get("error_code") == "STT_UNAVAILABLE"


def test_adversarial_voice_malformed_bytes_fail_closed() -> None:
    """Corrupted audio bytes must be caught and fail-closed with STT_UNAVAILABLE."""
    tg = TelegramBotController(
        bot_token="test_token",
        allowed_user_ids={12345},
        stt_engine=MalformedAudioEngine(),
    )
    res = tg.handle_inbound_voice(user_id=12345, voice_bytes=b"\x00\xff\xfe\xca\xfe\xba\xbe")

    assert res.get("ok") is False
    assert res.get("error_code") == "STT_UNAVAILABLE"


# ============================================================================
# 5. Parameter Boundary Conditions (user_id=None, chat_id=None)
# ============================================================================

def test_adversarial_voice_none_user_id() -> None:
    """user_id=None must be rejected with 403 Forbidden without crashing."""
    tg = TelegramBotController(bot_token="test_token", allowed_user_ids={12345}, stt_engine=MagicMock())
    res = tg.handle_inbound_voice(user_id=None, voice_bytes=b"valid_audio")  # type: ignore[arg-type]

    assert res.get("status") == 403
    assert res.get("rejected") is True


def test_adversarial_voice_none_chat_id_routes_successfully() -> None:
    """Valid audio note with chat_id=None routes successfully without error."""
    mock_stt = MagicMock()
    mock_stt.transcribe.return_value = "/help"

    tg = TelegramBotController(bot_token="test_token", allowed_user_ids={12345}, stt_engine=mock_stt)
    res = tg.handle_inbound_voice(user_id=12345, voice_bytes=b"valid_audio", chat_id=None)

    assert res.get("status") == 200
    assert "JARVIS Telegram Commands" in res.get("text", "")
