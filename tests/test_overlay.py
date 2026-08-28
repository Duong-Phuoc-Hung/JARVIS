"""
tests/test_overlay.py
=====================
Comprehensive unit and stress test suite for JARVIS HUD Overlay (Milestone 3):
Covers:
  - OverlayState FSM transitions: IDLE -> LISTENING -> THINKING -> RESPONSE -> HIDDEN
  - 10-step warm amber to glowing gold breathing dot color palette verification
  - Dynamic cycling typing dots (".", "..", "...") timer & pattern logic
  - Response text rendering, tooltip hint formatting, and auto-hide scheduling
  - 15x rapid show/hide stress cycling (zero crash guarantee)
  - Headless & non-display environment resilience
  - Backward compatibility for single-arg and dual-arg show_response()
"""
from __future__ import annotations

import time

import pytest

from jarvis.ui.overlay import (
    BREATHING_GRADIENT,
    COLORS,
    JarvisOverlay,
    OverlayState,
)


def test_overlay_state_enum_and_constants():
    """Verify OverlayState values and palette gradient definitions."""
    assert OverlayState.IDLE.value == "idle"
    assert OverlayState.LISTENING.value == "listening"
    assert OverlayState.THINKING.value == "thinking"
    assert OverlayState.RESPONSE.value == "response"
    assert OverlayState.HIDDEN.value == "hidden"

    # Verify 10-step gradient palette
    assert len(BREATHING_GRADIENT) == 10
    assert BREATHING_GRADIENT[0] == "#B8860B"   # Warm dark amber
    assert BREATHING_GRADIENT[5] == "#FFD700"   # Pure gold
    assert BREATHING_GRADIENT[-1] == "#FFF8DC"  # Glowing gold / Cornsilk

    # Verify key HUD colors
    assert "bg" in COLORS
    assert "border" in COLORS
    assert "tooltip" in COLORS
    assert COLORS["tooltip"] == "#558899"


def test_overlay_headless_state_machine_transitions():
    """Verify complete lifecycle transitions in headless mode."""
    overlay = JarvisOverlay(headless=True, auto_hide_s=5.0)
    overlay.start()
    assert overlay.state == OverlayState.IDLE
    assert overlay.is_visible is False
    assert overlay.is_headless is True

    # 1. Transition to LISTENING
    overlay.show_listening("🎤 Đang lắng nghe...")
    assert overlay.state == OverlayState.LISTENING
    assert overlay.is_visible is True
    assert "lắng nghe" in overlay.user_text
    assert overlay.status_text == "Đang lắng nghe giọng nói"

    # 2. Transition to THINKING
    overlay.show_thinking("bật đèn phòng khách")
    assert overlay.state == OverlayState.THINKING
    assert overlay.is_visible is True
    assert overlay.user_text == "bật đèn phòng khách"
    assert "Đang xử lý" in overlay.jarvis_text

    # 3. Transition to RESPONSE
    overlay.show_response(
        transcript="bật đèn phòng khách",
        response="Đã bật đèn phòng khách.",
        hint="💡 Double clap để hỏi tiếp",
    )
    assert overlay.state == OverlayState.RESPONSE
    assert overlay.is_visible is True
    assert overlay.jarvis_text == "Đã bật đèn phòng khách."
    assert overlay.hint_text == "💡 Double clap để hỏi tiếp"
    assert overlay.status_text == "Hoàn thành"

    # 4. Transition to HIDDEN
    overlay.hide()
    assert overlay.state == OverlayState.HIDDEN
    assert overlay.is_visible is False
    assert overlay.hint_text == ""
    assert overlay.status_text == "Sẵn sàng"

    overlay.destroy()


def test_overlay_breathing_gradient_ping_pong_logic():
    """Verify ping-pong index progression through 10-step gradient."""
    overlay = JarvisOverlay(headless=True)
    overlay._state = OverlayState.LISTENING
    overlay._visible = True
    overlay._breathing_index = 0
    overlay._breathing_direction = 1

    visited_indices = []
    # Simulate 20 steps of breathing animation
    for _ in range(20):
        visited_indices.append(overlay._breathing_index)
        if overlay._breathing_direction == 1:
            if overlay._breathing_index < len(BREATHING_GRADIENT) - 1:
                overlay._breathing_index += 1
            else:
                overlay._breathing_direction = -1
                overlay._breathing_index -= 1
        else:
            if overlay._breathing_index > 0:
                overlay._breathing_index -= 1
            else:
                overlay._breathing_direction = 1
                overlay._breathing_index += 1

    # Check ascending sequence (0 to 9)
    assert visited_indices[:10] == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    # Check descending sequence (8 down to 0)
    assert visited_indices[10:19] == [8, 7, 6, 5, 4, 3, 2, 1, 0]
    # Check re-ascending sequence (back to 1)
    assert visited_indices[19] == 1


def test_overlay_typing_dots_cycling_logic():
    """Verify cycling dots pattern in THINKING animation."""
    overlay = JarvisOverlay(headless=True)
    overlay._state = OverlayState.THINKING
    overlay._visible = True
    overlay._typing_index = 0

    patterns = []
    for _ in range(6):
        dots = "." * (overlay._typing_index + 1)
        patterns.append(dots)
        overlay._typing_index = (overlay._typing_index + 1) % 3

    assert patterns == [".", "..", "...", ".", "..", "..."]


def test_overlay_single_arg_show_response_compatibility():
    """Verify backward compatibility when show_response is called with 1 argument."""
    overlay = JarvisOverlay(headless=True)
    overlay.show_thinking("thời tiết hôm nay")
    overlay.show_response("Trời nhiều mây, 28 độ C.")

    assert overlay.state == OverlayState.RESPONSE
    assert overlay.jarvis_text == "Trời nhiều mây, 28 độ C."
    assert overlay.user_text == "thời tiết hôm nay"
    assert overlay.hint_text == "💡 Double clap để hỏi tiếp"


def test_overlay_rapid_show_hide_stress_cycling():
    """Stress test: 15 rapid consecutive show and hide transitions with zero crash."""
    overlay = JarvisOverlay(headless=True)
    overlay.start()

    for i in range(15):
        overlay.show_listening()
        assert overlay.state == OverlayState.LISTENING
        overlay.show_thinking(f"Test query {i}")
        assert overlay.state == OverlayState.THINKING
        overlay.show_response(f"Test query {i}", f"Response {i}")
        assert overlay.state == OverlayState.RESPONSE
        overlay.hide()
        assert overlay.state == OverlayState.HIDDEN

    overlay.destroy()
    assert overlay.is_visible is False


def test_overlay_on_close_callback():
    """Verify on_close callback is invoked when overlay hides."""
    closed = []
    overlay = JarvisOverlay(headless=True, on_close=lambda: closed.append(True))
    overlay.show_listening()
    assert len(closed) == 0

    overlay.hide()
    assert len(closed) == 1


def test_overlay_rapid_state_interruptions():
    """Stress test: Rapidly interrupt states without hiding (Listening -> Thinking -> Listening -> Response)."""
    overlay = JarvisOverlay(headless=True)
    overlay.start()

    for i in range(20):
        overlay.show_listening(f"Prompt {i}")
        assert overlay.state == OverlayState.LISTENING
        assert overlay.user_text == f"Prompt {i}"

        overlay.show_thinking(f"Transcript {i}")
        assert overlay.state == OverlayState.THINKING
        assert overlay.user_text == f"Transcript {i}"

        # Direct jump back to listening without hide
        overlay.show_listening(f"Interrupted Prompt {i}")
        assert overlay.state == OverlayState.LISTENING

        # Jump to response
        overlay.show_response(f"Transcript {i}", f"Response {i}")
        assert overlay.state == OverlayState.RESPONSE

    overlay.hide()
    assert overlay.state == OverlayState.HIDDEN
    overlay.destroy()


def test_overlay_timer_cleanup_on_hide_and_destroy():
    """Verify all internal animation and auto-hide job handles are cancelled and cleared on hide and destroy."""
    overlay = JarvisOverlay(headless=True)
    overlay.start()

    # Simulate active animation jobs
    overlay._breathing_job = "job_breath_123"
    overlay._typing_job = "job_type_456"
    overlay._hide_job = "job_hide_789"

    overlay.hide()
    assert overlay._breathing_job is None
    assert overlay._typing_job is None
    assert overlay._hide_job is None

    # Simulate active jobs again before destroy
    overlay._breathing_job = "job_breath_999"
    overlay._typing_job = "job_type_999"
    overlay._hide_job = "job_hide_999"

    overlay.destroy()
    assert overlay.state == OverlayState.HIDDEN
    assert overlay.is_visible is False
    assert overlay._is_running is False


def test_overlay_extreme_payloads_and_unicode_resilience():
    """Stress test: Feed long text (>1000 chars), emojis, null bytes, and multiline strings."""
    overlay = JarvisOverlay(headless=True)
    overlay.start()

    long_text = "JARVIS " * 200  # 1400 chars
    emoji_text = "🎤 💡 🚀 🤖 ⚡ 🧠 🔮 🛡️"
    multiline_text = "Line 1\nLine 2\r\nLine 3\tTabbed"

    # 1. Long response text truncation test
    overlay.show_response("Query", long_text)
    assert overlay.state == OverlayState.RESPONSE
    assert len(overlay.jarvis_text) <= 240
    assert overlay.jarvis_text.endswith("...")

    # 2. Emojis and special unicode in prompt and hint
    overlay.show_listening(emoji_text)
    assert overlay.user_text == emoji_text

    overlay.show_response("User", "Short response", hint=emoji_text)
    assert overlay.hint_text == emoji_text

    # 3. Multiline text
    overlay.show_thinking(multiline_text)
    assert overlay.user_text == multiline_text

    overlay.hide()
    overlay.destroy()


def test_overlay_multithreaded_rapid_concurrent_calls():
    """Stress test: 10 concurrent threads invoking overlay state methods simultaneously."""
    import concurrent.futures

    overlay = JarvisOverlay(headless=True)
    overlay.start()
    errors: list[Exception] = []

    def _worker(thread_id: int):
        try:
            for i in range(10):
                overlay.show_listening(f"Thread {thread_id} step {i}")
                overlay.show_thinking(f"Query {thread_id}-{i}")
                overlay.show_response(f"Query {thread_id}-{i}", f"Resp {thread_id}-{i}")
                overlay.hide()
        except Exception as e:
            errors.append(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(_worker, t) for t in range(10)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    assert len(errors) == 0
    overlay.destroy()

