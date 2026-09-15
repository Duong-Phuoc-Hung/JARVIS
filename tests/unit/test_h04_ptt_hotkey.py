"""
tests/unit/test_h04_ptt_hotkey.py
==================================
H-04 FINAL regression tests: Ctrl+Shift+L PTT must invoke the real voice
interaction entry point directly -- no redundant wrapper thread, no
nonexistent _handle_voice_command path, correct single-flight semantics
under genuinely concurrent rapid presses, and no interference with passive/
runaway safety semantics.

Contract under test (see jarvis/core/app.py::_register_default_hotkeys /
_start_voice_interaction):
  A. Ctrl+Shift+L is registered exactly to the PTT callback.
  B. The PTT callback invokes _start_voice_interaction(trigger_name=
     "HOTKEY_PTT", greeting_phrase="Vâng, tôi nghe.") directly. No reference
     to a _handle_voice_command path exists anywhere in the codebase.
  C. Calling the PTT callback does not itself spawn a wrapper thread around
     _start_voice_interaction -- _start_voice_interaction() already owns
     the single-flight decision and its own async dispatch internally.
  D. Firing the real registered callback from many concurrent threads while
     an interaction is active results in exactly ONE real
     "JARVIS-VoiceInteraction" work thread; every caller thread returns in
     bounded time (no deadlock).
  E. Once the active interaction releases _is_voice_interacting, pressing
     PTT again creates a new legitimate interaction (the guard is not a
     permanent lockout).
  G. None of the above happens at the expense of the passive-trigger/
     runaway guard (PTT never touches it) or the H-02/H-03 fail-closed
     device/acoustic-gate contracts already covered by their own suites.
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jarvis.core.app import JarvisApp

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _make_hotkey_app() -> JarvisApp:
    app = JarvisApp.__new__(JarvisApp)
    app.hotkey_manager = MagicMock()
    app.overlay = MagicMock()
    app.wake_word_detector = MagicMock()
    app.tts_manager = MagicMock()
    return app


def _get_ptt_callback(app: JarvisApp):
    app._register_default_hotkeys()
    registered = {}
    for call in app.hotkey_manager.register.call_args_list:
        args, _ = call
        registered[args[0]] = args[1]
    assert "Ctrl+Shift+L" in registered
    return registered["Ctrl+Shift+L"]


# ============================================================================
# A. Registration
# ============================================================================

def test_a_ctrl_shift_l_registered_exactly_to_ptt_callback():
    app = _make_hotkey_app()
    ptt_cb = _get_ptt_callback(app)

    # Exactly one registration call for this combination.
    matching_calls = [
        c for c in app.hotkey_manager.register.call_args_list
        if c.args[0] == "Ctrl+Shift+L"
    ]
    assert len(matching_calls) == 1
    assert matching_calls[0].args[1] is ptt_cb
    assert callable(ptt_cb)


# ============================================================================
# B. Correct entry point; no _handle_voice_command path anywhere
# ============================================================================

def test_b_ptt_callback_invokes_start_voice_interaction_with_exact_args():
    app = _make_hotkey_app()
    ptt_cb = _get_ptt_callback(app)

    app._start_voice_interaction = MagicMock()
    ptt_cb()
    app._start_voice_interaction.assert_called_once_with(
        trigger_name="HOTKEY_PTT",
        greeting_phrase="Vâng, tôi nghe.",
    )


def test_b_no_handle_voice_command_reference_anywhere_in_jarvis():
    """
    _handle_voice_command never existed as a real method; the original H-04
    defect was a dangling reference to it. Assert no REAL usage (a
    definition, an attribute access, or a call) of that identifier exists
    anywhere in the production source tree -- not merely that the current
    PTT path happens to avoid it. Deliberately does not flag prose mentions
    in comments/docstrings explaining the historical defect (e.g. this
    project's own CLAUDE.md and jarvis/core/app.py's H-04 fix comment both
    legitimately name it for documentation purposes).
    """
    usage_pattern = re.compile(
        r"def\s+_handle_voice_command\b"       # a definition
        r"|\.\s*_handle_voice_command\s*\("    # obj._handle_voice_command(...)
        r"|\bself\._handle_voice_command\b"    # self._handle_voice_command (any form)
    )
    violations = []
    for py_file in (REPO_ROOT / "jarvis").rglob("*.py"):
        text = py_file.read_text(encoding="utf-8", errors="replace")
        if usage_pattern.search(text):
            violations.append(str(py_file))
    assert not violations, f"_handle_voice_command actually used (not just mentioned) in: {violations}"

    # And the real JarvisApp class has no such attribute.
    assert not hasattr(JarvisApp, "_handle_voice_command")


# ============================================================================
# C. No redundant wrapper thread around _start_voice_interaction
# ============================================================================

def test_c_ptt_callback_creates_no_wrapper_thread():
    """
    Calling the PTT callback must not itself construct a threading.Thread --
    _start_voice_interaction() is already non-blocking and owns its own
    thread dispatch internally (or none at all, if suppressed by
    single-flight). With _start_voice_interaction mocked out here, ZERO
    threads should be created by the callback itself.
    """
    app = _make_hotkey_app()
    ptt_cb = _get_ptt_callback(app)
    app._start_voice_interaction = MagicMock()

    with patch("threading.Thread") as mock_thread:
        ptt_cb()
        mock_thread.assert_not_called()


# ============================================================================
# D. Rapid concurrent presses: exactly one real voice interaction
# ============================================================================

def test_d_rapid_concurrent_presses_single_flight_exactly_one_interaction():
    """
    Fire the ACTUAL registered Ctrl+Shift+L callback from 20 genuinely
    concurrent threads (a threading.Barrier forces them to call in as tight
    a window as possible), using the REAL _voice_lock (threading.Lock) and
    _is_voice_interacting guard inside the real _start_voice_interaction().
    threading.Thread is patched so the one real "JARVIS-VoiceInteraction"
    work thread that IS allowed to spawn never actually runs its body (and
    therefore never resets _is_voice_interacting) -- this deliberately keeps
    the first interaction "active" for the whole burst, proving the other
    19 presses are suppressed by the guard, not merely lucky timing.
    """
    app = _make_hotkey_app()
    ptt_cb = _get_ptt_callback(app)

    app._voice_lock = threading.Lock()
    app._is_voice_interacting = False
    app.proactive_engine = MagicMock()
    app.tray_controller = MagicMock()
    app.stt_engine = MagicMock()

    N = 20
    barrier = threading.Barrier(N)
    results: list = [None] * N

    def _fire(i: int) -> None:
        barrier.wait(timeout=5.0)
        try:
            results[i] = ptt_cb()
        except Exception as exc:  # pragma: no cover - failure surfaced via assertion below
            results[i] = exc

    # Construct the REAL driver threads BEFORE patching threading.Thread --
    # patch("threading.Thread") replaces the constructor globally (the
    # `threading` module is a process-wide singleton), so if these were
    # constructed *inside* the patch context, the driver threads themselves
    # would silently become MagicMocks too (never actually running _fire,
    # and .is_alive()/.join() would be meaningless mock calls) -- only the
    # INTERNAL threading.Thread(...) call _start_voice_interaction() makes
    # once patching is active should be intercepted.
    threads = [threading.Thread(target=_fire, args=(i,), daemon=True) for i in range(N)]

    with patch("threading.Thread") as mock_thread:
        mock_thread.return_value = MagicMock()  # .start() is a no-op stand-in

        t0 = time.monotonic()
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=5.0)
        elapsed = time.monotonic() - t0

    assert all(not th.is_alive() for th in threads), "A caller thread never returned -- possible deadlock"
    assert elapsed < 5.0, f"20 rapid presses took {elapsed:.2f}s -- suggests contention/deadlock"
    assert not any(isinstance(r, Exception) for r in results), f"Unhandled exception(s): {results}"

    voice_interaction_launches = [
        c for c in mock_thread.call_args_list
        if c.kwargs.get("name") == "JARVIS-VoiceInteraction"
    ]
    assert len(voice_interaction_launches) == 1, (
        f"Expected exactly ONE JARVIS-VoiceInteraction thread from {N} rapid presses, "
        f"got {len(voice_interaction_launches)}"
    )
    # The single-flight flag remains set -- the (stubbed) work thread never
    # ran to completion, so the guard is still correctly held by the first
    # interaction, not silently released.
    assert app._is_voice_interacting is True


# ============================================================================
# E. Release / retry: the guard is not a permanent lockout
# ============================================================================

def test_e_ptt_works_again_after_first_interaction_releases_the_guard():
    app = _make_hotkey_app()
    ptt_cb = _get_ptt_callback(app)

    app._voice_lock = threading.Lock()
    app._is_voice_interacting = False
    app.proactive_engine = MagicMock()
    app.tray_controller = MagicMock()
    app.stt_engine = MagicMock()

    with patch("threading.Thread") as mock_thread:
        mock_thread.return_value = MagicMock()

        # First press: acquires the guard, "spawns" (stubbed) the work thread.
        ptt_cb()
        assert app._is_voice_interacting is True
        first_launches = [c for c in mock_thread.call_args_list if c.kwargs.get("name") == "JARVIS-VoiceInteraction"]
        assert len(first_launches) == 1

        # A second, concurrent-style press while still active must be suppressed.
        mock_thread.reset_mock()
        ptt_cb()
        assert mock_thread.call_count == 0, "Second press while active must not spawn another interaction"

        # Simulate the first interaction's own finally block releasing the guard.
        with app._voice_lock:
            app._is_voice_interacting = False

        # Pressing PTT again must now succeed and create a genuine new interaction.
        mock_thread.reset_mock()
        ptt_cb()
        assert app._is_voice_interacting is True
        second_launches = [c for c in mock_thread.call_args_list if c.kwargs.get("name") == "JARVIS-VoiceInteraction"]
        assert len(second_launches) == 1, "PTT must work again once the guard is released -- not a permanent lockout"


# ============================================================================
# G. Safety: PTT never touches the passive-trigger/runaway guard
# ============================================================================

def test_g_ptt_never_touches_passive_trigger_guard():
    """
    PTT is an explicit user action; only ambient wake-word/gesture triggers
    go through the passive-trigger circuit breaker (see
    _on_wake_word_triggered / _on_gesture_event in jarvis/core/app.py).
    Verified two ways: at runtime (the guard's try_acquire is never called
    when PTT fires) and at the source level (the PTT callback's own
    definition never references _passive_trigger_guard at all).
    """
    app = _make_hotkey_app()
    ptt_cb = _get_ptt_callback(app)

    app._voice_lock = threading.Lock()
    app._is_voice_interacting = False
    app._passive_trigger_guard = MagicMock()
    app._start_voice_interaction = MagicMock()

    ptt_cb()

    app._passive_trigger_guard.try_acquire.assert_not_called()

    import inspect
    ptt_source = inspect.getsource(ptt_cb)
    assert "_passive_trigger_guard" not in ptt_source
