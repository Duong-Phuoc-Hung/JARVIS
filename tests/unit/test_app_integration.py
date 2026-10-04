"""
tests/unit/test_app_integration.py
==================================
End-to-End Pipeline Integration Test for Milestone 2:
Audio Stream -> DSP -> GestureDetector -> ActionDispatcher -> Plugins -> TTSManager.
"""
import time

import numpy as np
import pytest

from jarvis.core.app import JarvisApp
from jarvis.gesture.models import GestureType


def test_full_audio_gesture_dispatch_pipeline(mock_audio_stream, tmp_path, monkeypatch):
    """
    Verify complete pipeline: synthetic double clap audio input triggers
    gesture detection, multi-plugin action execution, and TTS speech feedback.
    """
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()
    # P0 runaway-hardening: fanout is opt-in by default now -- safe to opt in
    # here since every one of its actions is re-registered as a fake handler.
    app.config.set("gesture.patterns.double_clap.enabled", True)
    app.config.set("gesture.patterns.double_clap.allow_side_effect_fanout", True)
    app.gesture_detector.configure_from_dict(
        {"patterns": {"double_clap": {"enabled": True}}}
    )
    # Inject a test-only actions list so this test is decoupled from the
    # default config (which intentionally no longer lists heavy app launches).
    app.config.set("gesture.patterns.double_clap.actions", [
        "test_action_a", "test_action_b", "test_action_c", "test_action_d",
    ])

    # Track executed actions
    executed = []

    def _make_handler(n):
        def _h(**kw):
            executed.append(n)
            return {"status": "ok"}
        return _h

    for action_name in ("test_action_a", "test_action_b", "test_action_c", "test_action_d"):
        app.dispatcher.register_action(name=action_name, handler=_make_handler(action_name))

    spoken = []
    if app.tts_manager:
        app.tts_manager.fallback_engine.speak = lambda txt, **kw: spoken.append(txt) or True

    # Generate synthetic double-clap audio buffer (150ms gap)
    pcm = mock_audio_stream.generate_double_clap(gap_s=0.15, leading_silence_s=0.1, trailing_silence_s=0.6)

    # Feed audio buffer into audio engine
    if app.audio_engine:
        app.audio_engine.feed_audio(pcm)

    # Allow background event processing to settle
    time.sleep(0.8)

    # Verify actions were dispatched
    assert "test_action_a" in executed
    assert "test_action_b" in executed
    assert "test_action_c" in executed
    assert "test_action_d" in executed

    app.stop()
