"""
tests/unit/test_h03_echo_guard.py
==================================
H-03 FINAL regression tests: a shared acoustic I/O exclusion gate between
TTS playback and command microphone capture, closing the TOCTOU race a
polling-based is_playing check can never fully close.

Background (three successive corrections to the same subsystem):

1. The original guard polled tts_manager.is_playing in a bounded loop
   before opening the microphone. This has an inherent check-then-act race:
   is_playing can be observed False, then a NEW, unrelated TTS output (e.g.
   a hotkey-triggered status report, not just the current interaction's own
   greeting) can start in the gap before the microphone stream actually
   opens -- JARVIS's own voice could still reach STT.

2. TTSManager._execute_speak() used to hold its own state lock (self._lock)
   across the entire synthesis+playback operation, so is_playing()/
   is_in_echo_window() reads from other threads could block for the full
   TTS duration instead of returning near-instantly -- fixed by moving the
   actual I/O under a dedicated `_playback_resource_lock`, leaving `_lock`
   (and therefore is_playing()/is_in_echo_window()) always fast.

3. THIS fix: record_audio() no longer polls is_playing at all. It acquires
   the SAME `_playback_resource_lock` TTSManager._execute_speak() holds for
   real playback, via TTSManager.try_acquire_acoustic_gate(timeout=...) /
   release_acoustic_gate(). Holding it for the complete recording period
   makes it structurally impossible for TTS playback and microphone capture
   to overlap acoustically -- there is no gap for a race to occur, because
   both sides contend for literally the same lock. Acquisition is bounded;
   on timeout, record_audio() raises AcousticGateTimeoutError and the
   microphone is NEVER opened -- never a fabricated silent buffer.

These tests exercise the REAL jarvis.tts.manager.TTSManager (its actual
locking/threading behavior) using stub TTS engines -- no real network/audio
hardware -- to keep them deterministic and fast, plus tests.conftest's
FakeGateTTS (a real threading.Lock-backed stand-in) where a full TTSManager
isn't needed.
"""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from jarvis.core.app import JarvisApp
from jarvis.tts.manager import AcousticGateTimeoutError, TTSManager
from tests.conftest import FakeGateTTS


class _UnavailablePrimary:
    """Stub primary engine that is never available -- forces the fallback path."""

    def is_available(self) -> bool:
        return False

    def synthesize_to_bytes(self, text, voice_id=None, **kwargs) -> bytes:
        raise AssertionError("Primary engine should not be called when unavailable")

    voice_id = ""
    model_id = "stub"
    output_format = "pcm_24000"
    sample_rate = 24000


class _SlowFallback:
    """Stub fallback engine whose speak() blocks for a controlled duration,
    simulating real (slow) network synthesis + audio playback without
    touching any real hardware or network."""

    def __init__(self, duration_s: float) -> None:
        self.duration_s = duration_s
        self.call_count = 0

    def speak(self, text, voice_id=None, wait=True, **kwargs) -> bool:
        self.call_count += 1
        time.sleep(self.duration_s)
        return True


class _FailingFallback:
    """Stub fallback engine that always raises during speak()."""

    def speak(self, text, voice_id=None, wait=True, **kwargs) -> bool:
        raise RuntimeError("synthesis/playback hardware failure (simulated)")


def _make_tts(fallback) -> TTSManager:
    tts = TTSManager(
        config={"cache": {"enabled": False}},
        primary_engine=_UnavailablePrimary(),
        fallback_engine=fallback,
    )
    tts.stop()  # stop the background worker thread; tests drive speak() directly
    return tts


def _make_app(tts) -> JarvisApp:
    app = JarvisApp.__new__(JarvisApp)
    app.config = {"audio.sample_rate": 44100, "stt.timeout_s": 0.3}
    app.headless = False
    app.audio_engine = None
    app.tts_manager = tts
    return app


def _patched_input_stream():
    mock_inst = MagicMock()
    mock_inst.read.return_value = (np.zeros((100, 1), dtype=np.float32), False)
    return mock_inst


# ============================================================================
# 1. Long TTS beyond the OLD 1.0s guard can never overlap capture
# 3. Capture-side gate wait is bounded
# 4. Gate timeout fails closed with a typed error; mic is never opened
# (one real-TTSManager test proves all three together end-to-end)
# ============================================================================

def test_long_tts_beyond_old_guard_fails_closed_never_opens_microphone():
    """
    TTS lasting longer than record_audio()'s own gate timeout (1.0s) must
    NEVER result in an overlapping capture. Under the OLD is_playing-polling
    design, the wait loop simply gave up after 1.0s and proceeded to open
    the microphone anyway -- exactly the defect this fix eliminates. The
    NEW design must instead fail closed: raise AcousticGateTimeoutError,
    return within a small bounded margin of the timeout (not the full TTS
    duration), and never call sounddevice.InputStream at all.
    """
    fallback = _SlowFallback(duration_s=3.0)  # far exceeds the 1.0s gate timeout
    tts = _make_tts(fallback)
    app = _make_app(tts)

    speak_thread = threading.Thread(target=lambda: tts.speak("noi rat dai", wait=True), daemon=True)
    speak_thread.start()
    time.sleep(0.1)  # let playback actually start and acquire the gate

    with patch("sounddevice.InputStream") as mock_stream:
        t0 = time.monotonic()
        with pytest.raises(AcousticGateTimeoutError) as exc_info:
            app.record_audio(duration_s=0.2)
        elapsed = time.monotonic() - t0

        mock_stream.assert_not_called()

    assert exc_info.value.timeout == 1.0
    assert elapsed < 2.0, (
        f"record_audio() took {elapsed:.2f}s to fail -- must be bounded near its own "
        "1.0s gate timeout, not the full 3s TTS duration."
    )

    speak_thread.join(timeout=5.0)
    assert not speak_thread.is_alive()
    assert fallback.call_count == 1


def test_short_tts_within_gate_timeout_capture_waits_then_succeeds_no_overlap():
    """
    Complementary happy path: when TTS finishes WITHIN the gate timeout,
    record_audio() must wait for it (not fail), then proceed -- and the
    microphone must only ever open strictly after the TTS playback interval
    has fully ended, proven via real wall-clock timestamps instrumented on
    both operations (not merely "no assertion failure").
    """
    fallback = _SlowFallback(duration_s=0.3)
    tts = _make_tts(fallback)
    app = _make_app(tts)

    speak_interval: dict = {}

    def _speak():
        speak_interval["start"] = time.monotonic()
        tts.speak("noi ngan", wait=True)
        speak_interval["end"] = time.monotonic()

    capture_interval: dict = {}

    with patch("sounddevice.InputStream") as mock_stream:
        mock_ctx = MagicMock()

        def _enter():
            capture_interval["start"] = time.monotonic()
            return _patched_input_stream()

        def _exit(*_a):
            capture_interval["end"] = time.monotonic()

        mock_ctx.__enter__.side_effect = _enter
        mock_ctx.__exit__.side_effect = _exit
        mock_stream.return_value = mock_ctx

        speak_thread = threading.Thread(target=_speak, daemon=True)
        speak_thread.start()
        time.sleep(0.05)  # let playback actually start

        app.record_audio(duration_s=0.1)

    speak_thread.join(timeout=5.0)

    assert "start" in capture_interval and "end" in capture_interval
    assert "start" in speak_interval and "end" in speak_interval
    assert capture_interval["start"] >= speak_interval["end"], (
        f"Capture started at {capture_interval['start']:.3f} before TTS playback "
        f"ended at {speak_interval['end']:.3f} -- acoustic overlap."
    )


# ============================================================================
# 2. TOCTOU reproduction: TTS begins immediately before capture, no overlap
# ============================================================================

def test_toctou_tts_starts_immediately_before_capture_no_overlap():
    """
    Reproduces the exact race the old is_playing-polling design was
    vulnerable to: a NEW, unrelated TTS output starts in the narrow window
    right around when record_audio() is about to open the microphone --
    not the current interaction's own greeting, but some other concurrent
    speak() call (e.g. a hotkey status report) racing it. With the atomic
    gate, whichever side wins the race to acquire the lock excludes the
    other for its full duration -- this must be structurally impossible to
    overlap, proven by real wall-clock timestamps on both operations,
    regardless of which one happens to win the race on a given run.
    """
    fallback = _SlowFallback(duration_s=0.25)
    tts = _make_tts(fallback)
    app = _make_app(tts)

    speak_interval: dict = {}
    capture_interval: dict = {}

    def _speak():
        speak_interval["start"] = time.monotonic()
        tts.speak("toctou race", wait=True)
        speak_interval["end"] = time.monotonic()

    with patch("sounddevice.InputStream") as mock_stream:
        mock_ctx = MagicMock()

        def _enter():
            capture_interval["start"] = time.monotonic()
            return _patched_input_stream()

        def _exit(*_a):
            capture_interval["end"] = time.monotonic()

        mock_ctx.__enter__.side_effect = _enter
        mock_ctx.__exit__.side_effect = _exit
        mock_stream.return_value = mock_ctx

        # Fire the competing TTS output on a razor-thin delay -- deliberately
        # racing record_audio()'s own gate acquisition, simulating "TTS
        # begins right as capture is about to proceed", not comfortably
        # before or after it.
        speak_thread = threading.Thread(target=_speak, daemon=True)
        speak_thread.start()
        time.sleep(0.005)

        try:
            app.record_audio(duration_s=0.1)
        except AcousticGateTimeoutError:
            # Losing the race and failing closed is an acceptable outcome of
            # a genuine race (the gate timeout is 1.0s > the 0.25s TTS, so
            # this should not normally happen, but is not itself a defect
            # if it does under extreme scheduling delay) -- what matters is
            # captured below: no overlap ever occurred.
            pass

    speak_thread.join(timeout=5.0)

    assert "start" in speak_interval and "end" in speak_interval
    if "start" in capture_interval:
        # Capture actually ran -- it must never have overlapped the speak interval.
        assert "end" in capture_interval
        no_overlap = (
            capture_interval["start"] >= speak_interval["end"]
            or speak_interval["start"] >= capture_interval["end"]
        )
        assert no_overlap, (
            f"Capture interval {capture_interval} overlapped with TTS speak "
            f"interval {speak_interval} -- acoustic contamination possible."
        )


# ============================================================================
# 5. is_playing/is_in_echo_window reads must stay fast while TTS is active
# ============================================================================

def test_is_playing_and_echo_window_reads_stay_fast_during_slow_playback():
    """
    While a REAL, slow (2s) speak(wait=True) call is in progress on one
    thread (holding the acoustic gate), reading is_playing/is_in_echo_window
    from ANOTHER thread must return almost instantly -- these go through
    the separate, fast self._lock, never the gate itself.
    """
    fallback = _SlowFallback(duration_s=2.0)
    tts = _make_tts(fallback)

    result: dict = {}

    def _speak_slowly():
        result["ok"] = tts.speak("xin chao", wait=True)

    t = threading.Thread(target=_speak_slowly, daemon=True)
    t0 = time.monotonic()
    t.start()

    # Deliberately do NOT perform a separate "sanity check" read here first
    # -- under the lock-scope bug this test guards against, that read would
    # itself block for the remaining playback duration and silently absorb
    # the delay before the timed measurement below ever started.
    time.sleep(0.3)

    read_start = time.monotonic()
    still_playing = tts.is_playing
    in_echo = tts.is_in_echo_window(cooldown_s=2.5)
    read_elapsed = time.monotonic() - read_start

    assert still_playing is True, "Slow playback should still be in progress at this point"
    assert in_echo is True
    assert read_elapsed < 0.2, (
        f"is_playing/is_in_echo_window took {read_elapsed:.3f}s to return while playback "
        "was in progress -- state reads must never block on the playback lock."
    )

    t.join(timeout=5.0)
    assert not t.is_alive(), "Speak thread did not finish within the bound"
    assert result.get("ok") is True
    assert fallback.call_count == 1
    assert tts.is_playing is False
    total_elapsed = time.monotonic() - t0
    assert total_elapsed >= 2.0, "Sanity check: the slow speak() must have actually taken ~2s"


# ============================================================================
# 6. 150ms settling occurs before capture after the gate releases
# ============================================================================

def test_settle_delay_applied_after_gate_contended_not_when_idle():
    """
    record_audio() must apply a short (150ms) acoustic settling delay after
    it had to genuinely WAIT for the gate (TTS was using it), but skip that
    delay when the gate was immediately free (TTS idle) -- the common fast
    path (e.g. after _start_voice_interaction's own greeting+settle already
    ran) must not pay a redundant extra delay.

    Measured via real wall-clock elapsed time rather than patching
    jarvis.core.app.time.sleep: that patch would also intercept
    FakeGateTTS's own background release thread (import time is a process-
    wide singleton module, so a global monkeypatch of time.sleep silences
    every caller, not just record_audio()'s), making the fake gate release
    instantly regardless of held_for_s and masking exactly the behavior
    this test needs to observe.
    """
    with patch("sounddevice.InputStream") as mock_stream:
        mock_stream.return_value.__enter__.return_value = _patched_input_stream()

        # Case A: gate is held (TTS "playing") for 0.1s -- record_audio()
        # must wait for it AND then apply the 150ms settle, so total real
        # elapsed time must clearly exceed the hold duration alone.
        app_a = _make_app(FakeGateTTS(held_for_s=0.1))
        t0 = time.monotonic()
        app_a.record_audio(duration_s=0.2)
        elapsed_a = time.monotonic() - t0
        assert elapsed_a >= 0.1 + 0.15 - 0.03, (
            f"Case A took {elapsed_a:.3f}s -- expected the ~0.1s gate wait PLUS the "
            "150ms settle delay to both have elapsed."
        )

        # Case B: gate is free immediately -- no wait, no settle -- must be fast.
        app_b = _make_app(FakeGateTTS(held_for_s=0.0))
        t0 = time.monotonic()
        app_b.record_audio(duration_s=0.2)
        elapsed_b = time.monotonic() - t0
        assert elapsed_b < 0.1, (
            f"Case B took {elapsed_b:.3f}s -- an immediately-free gate must not incur "
            "the 150ms settle delay."
        )


# ============================================================================
# TTS failure must not leave stale is_playing / a permanently stuck echo window
# ============================================================================

def test_tts_exception_during_playback_clears_state_and_closes_echo_window():
    """
    If the fallback engine raises during synthesis/playback, TTSManager must
    still clear is_playing (via its finally block) and release the gate, and
    start a real, BOUNDED cooldown from a genuine _last_playback_finish_time
    -- not leave is_playing or the gate stuck forever, which would
    permanently block all future command capture and wake-word detection.
    """
    tts = _make_tts(_FailingFallback())

    with pytest.raises(RuntimeError):
        tts.speak("se that bai", wait=True)

    assert tts.is_playing is False
    assert tts.last_playback_finish_time > 0.0

    # The gate itself must have been released too -- a subsequent capture
    # attempt must be able to acquire it immediately, not hang.
    acquired = tts.try_acquire_acoustic_gate(timeout=0.5)
    assert acquired is True, "Gate must be released even when synthesis/playback raised"
    tts.release_acoustic_gate()

    finish_time = tts.last_playback_finish_time
    # Still within the short cooldown right after the failure -- expected,
    # not a bug (partial/undefined audio may still have reached the speakers).
    assert tts.is_in_echo_window(current_time=finish_time + 0.1, cooldown_s=2.5) is True
    # But the window is genuinely BOUNDED: it closes once cooldown_s elapses.
    assert tts.is_in_echo_window(current_time=finish_time + 2.6, cooldown_s=2.5) is False


# ============================================================================
# 7. Bounded concurrency: rapid repeated voice triggers around TTS completion
# ============================================================================

def test_rapid_repeated_voice_triggers_around_tts_completion_no_deadlock():
    """
    Fire _start_voice_interaction() many times in rapid succession,
    overlapping with an active greeting TTS playback, using the REAL
    TTSManager (fast stub engine) and the real single-flight
    (_voice_lock/_is_voice_interacting) guard PLUS the new acoustic gate.
    Must complete within a small bounded time with no deadlock/hang and no
    unhandled exception -- concurrent extra triggers must be cleanly
    suppressed or fail closed via AcousticGateTimeoutError, never hang.
    """
    fallback = _SlowFallback(duration_s=0.05)
    tts = _make_tts(fallback)

    app = _make_app(tts)
    app.config["stt.timeout_s"] = 0.1
    app.proactive_engine = MagicMock()
    app.overlay = MagicMock()
    app.tray_controller = MagicMock()
    app.stt_engine = MagicMock()
    app.stt_engine.transcribe.return_value = ""
    app._voice_lock = threading.Lock()
    app._is_voice_interacting = False
    app.computer_controller = MagicMock()
    app._mic_muted = False
    app.log_interaction = MagicMock()

    with patch("sounddevice.InputStream") as mock_stream:
        mock_stream.return_value.__enter__.return_value = _patched_input_stream()

        threads = []
        t0 = time.monotonic()
        for i in range(8):
            th = threading.Thread(
                target=app._start_voice_interaction,
                kwargs={"greeting_phrase": "chao", "trigger_name": f"RACE_{i}", "sync": True},
                daemon=True,
            )
            threads.append(th)

        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=10.0)
        elapsed = time.monotonic() - t0

    assert all(not th.is_alive() for th in threads), "A voice-interaction thread did not complete -- possible deadlock"
    assert elapsed < 8.0, f"Rapid concurrent triggers took {elapsed:.2f}s -- suggests contention/deadlock, not clean suppression"
    assert app._is_voice_interacting is False, "Single-flight flag must be released after all threads finish"
    # At least one interaction actually ran (logged); others may have been
    # suppressed by the single-flight guard or failed closed on the gate,
    # but none should have crashed unhandled or hung.
    assert app.log_interaction.call_count >= 1
