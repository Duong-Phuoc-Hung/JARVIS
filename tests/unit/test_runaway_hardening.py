"""
tests/unit/test_runaway_hardening.py
=====================================
P0 runaway-hardening wiring regression tests (branch
fix/voice-control-truthfulness). Covers integration of
jarvis/core/runaway_guard.py into:

  - JarvisApp._on_wake_word_triggered() / _on_gesture_event() (passive
    trigger circuit breaker)
  - JarvisApp._on_gesture_event()'s double_clap heavy external-app fanout
    (now opt-in via gesture.patterns.double_clap.allow_side_effect_fanout)
  - SpotifyPlugin / ChromeMultiMonitorPlugin / CursorPlugin (external-launch
    dedupe)
  - ComputerController.open_app() / open_website() (canonical launch path
    dedupe)
  - STTEngine._on_config_reloaded() (no duplicate heavy-engine construction
    on a no-op reload) and FasterWhisperSTT's lazy-by-default preload

All mocked/faked -- this file never starts a real Spotify/Chrome/Cursor
process, never opens a real browser/Settings window, never loads a real
Whisper model, and never touches a real audio device.
"""
from __future__ import annotations

import os
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from jarvis.automation.control import ComputerController
from jarvis.core.app import JarvisApp
from jarvis.core.runaway_guard import LaunchDedupeGuard, launch_dedupe_guard
from jarvis.plugins.chrome import ChromeMultiMonitorPlugin
from jarvis.plugins.cursor import CursorPlugin
from jarvis.plugins.spotify import SpotifyPlugin
from jarvis.stt.engine import FasterWhisperSTT, STTEngine


class _SyncThread:
    """threading.Thread stand-in that runs its target synchronously on .start()."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None, name=None) -> None:
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self) -> None:
        if self._target:
            self._target(*self._args, **self._kwargs)

    def join(self, timeout=None) -> None:
        pass


def _make_app() -> JarvisApp:
    app = JarvisApp(headless=True, no_hot_reload=True)
    app.initialize()
    return app


# ============================================================================
# 0. Safety-guard config application timing (pre-commit review correction)
# ============================================================================


class TestSafetyGuardConfigTiming(unittest.TestCase):
    """
    Pre-commit review correction: JarvisApp.__init__() previously read
    safety.passive_trigger_guard.*/safety.launch_dedupe_cooldown_s from
    self.config BEFORE self.config.load() ever ran (load() only happens in
    initialize()) -- self.config._data was still {} at that point, so a
    real custom config value was always silently ignored in favor of the
    hardcoded Python default. Proves the fix: __init__() only uses safe
    built-in defaults, and initialize() applies the REAL loaded value
    in-place onto the existing guard objects (never reconstructing them).
    """

    def setUp(self) -> None:
        self._orig_launch_cooldown = launch_dedupe_guard.default_cooldown_s

    def tearDown(self) -> None:
        launch_dedupe_guard.default_cooldown_s = self._orig_launch_cooldown

    def test_custom_safety_config_is_actually_applied_after_initialize(self) -> None:
        import json
        import tempfile

        custom_cfg = {
            "safety": {
                "passive_trigger_guard": {"max_triggers": 17, "window_s": 42.0, "lockout_s": 99.0},
                "launch_dedupe_cooldown_s": 13.0,
            }
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = os.path.join(tmp_dir, "custom.json")
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(custom_cfg, f)

            app = JarvisApp(headless=True, no_hot_reload=True, config_path=cfg_path)
            try:
                # Before initialize(): config hasn't loaded yet -- must still
                # be the guard class's own safe built-in default, proving the
                # constructor genuinely does not (mis)read the custom value early.
                self.assertEqual(app._passive_trigger_guard.max_triggers, 5)

                app.initialize()

                self.assertEqual(app._passive_trigger_guard.max_triggers, 17)
                self.assertEqual(app._passive_trigger_guard.window_s, 42.0)
                self.assertEqual(app._passive_trigger_guard.lockout_s, 99.0)
                self.assertEqual(launch_dedupe_guard.default_cooldown_s, 13.0)
            finally:
                app.stop()

    def test_hot_reload_updates_limits_without_clearing_trigger_history(self) -> None:
        app = JarvisApp(headless=True, no_hot_reload=True)
        app.initialize()
        try:
            app._passive_trigger_guard.try_acquire("GESTURE:double_clap", now=0.0)
            app._passive_trigger_guard.try_acquire("GESTURE:double_clap", now=10.0)
            history_before = list(app._passive_trigger_guard._history["GESTURE:double_clap"])
            self.assertEqual(len(history_before), 2)

            new_cfg = {"safety": {"passive_trigger_guard": {"max_triggers": 2}, "launch_dedupe_cooldown_s": 8.0}}
            app._on_safety_config_reloaded(new_cfg)

            self.assertEqual(app._passive_trigger_guard.max_triggers, 2)
            self.assertEqual(launch_dedupe_guard.default_cooldown_s, 8.0)
            # The two timestamps recorded before the reload must be untouched --
            # a config reload must never silently reset live circuit-breaker state.
            self.assertEqual(list(app._passive_trigger_guard._history["GESTURE:double_clap"]), history_before)
        finally:
            app.stop()

    def test_default_config_yaml_values_are_the_effective_defaults(self) -> None:
        """
        With no custom config override, the values actually applied after
        initialize() must match config/default_config.yaml's
        safety.passive_trigger_guard.*/safety.launch_dedupe_cooldown_s
        (5 / 60.0 / 120.0 / 5.0) -- proving the loaded default file, not just
        the Python class defaults, is genuinely being read.
        """
        app = _make_app()
        try:
            self.assertEqual(app._passive_trigger_guard.max_triggers, 5)
            self.assertEqual(app._passive_trigger_guard.window_s, 60.0)
            self.assertEqual(app._passive_trigger_guard.lockout_s, 120.0)
            self.assertEqual(launch_dedupe_guard.default_cooldown_s, 5.0)
        finally:
            app.stop()


# ============================================================================
# 1. Passive-trigger circuit breaker wiring
# ============================================================================


class TestWakeWordPassiveTriggerGuardWiring(unittest.TestCase):
    def setUp(self) -> None:
        self.app = _make_app()
        self.calls: list[dict] = []
        self.app._start_voice_interaction = lambda **kw: self.calls.append(kw)

    def tearDown(self) -> None:
        self.app.stop()

    def test_repeated_wake_word_triggers_are_bounded(self) -> None:
        # Spaced exactly at the wake-word min-rearm interval (2.5s) apart, so
        # MIN_INTERVAL never blocks any individual call -- only the sliding-
        # window lockout (default max_triggers=5 within window_s=60.0) can.
        times = [i * 2.5 for i in range(7)]  # 0, 2.5, 5.0, ..., 15.0
        with patch("jarvis.core.runaway_guard.time.monotonic", side_effect=lambda: times.pop(0)):
            for _ in range(7):
                self.app._on_wake_word_triggered()
        self.assertEqual(len(self.calls), 5, "circuit breaker must trip after max_triggers within the window")

    def test_immediate_retrigger_suppressed_by_min_interval(self) -> None:
        seq = iter([0.0, 0.1])
        with patch("jarvis.core.runaway_guard.time.monotonic", side_effect=lambda: next(seq)):
            self.app._on_wake_word_triggered()
            self.app._on_wake_word_triggered()
        self.assertEqual(len(self.calls), 1)


class TestGesturePassiveTriggerGuardWiring(unittest.TestCase):
    def setUp(self) -> None:
        self.app = _make_app()
        self.dispatched: list[str] = []
        self.app.dispatcher.dispatch_action = lambda action_name, **kw: self.dispatched.append(action_name) or MagicMock(success=True, error=None)

    def tearDown(self) -> None:
        self.app.stop()

    def test_repeated_triple_clap_triggers_are_bounded(self) -> None:
        # triple_clap's own established cooldown (_action_fanout_cooldown_s) is 3.0s.
        times = [i * 3.0 for i in range(7)]  # 0, 3, 6, ..., 18
        with patch("jarvis.core.runaway_guard.time.monotonic", side_effect=lambda: times.pop(0)):
            for _ in range(7):
                self.app._on_gesture_event("triple_clap", confidence=1.0)
        # Each allowed trigger dispatches exactly one action ("system_status").
        self.assertEqual(len(self.dispatched), 5)

    def test_immediate_regesture_suppressed_by_min_interval(self) -> None:
        seq = iter([0.0, 0.5])
        with patch("jarvis.core.runaway_guard.time.monotonic", side_effect=lambda: next(seq)):
            self.app._on_gesture_event("triple_clap", confidence=1.0)
            self.app._on_gesture_event("triple_clap", confidence=1.0)
        self.assertEqual(len(self.dispatched), 1)


class TestPassiveGuardDoesNotBlockExplicitActions(unittest.TestCase):
    """
    The passive-trigger circuit breaker must never permanently disable an
    explicit, user-initiated operation (typed text command / dispatcher
    call) just because ambient wake-word/gesture triggers tripped their own
    lockout.
    """

    def setUp(self) -> None:
        self.app = _make_app()

    def tearDown(self) -> None:
        self.app.stop()

    def test_exhausted_wake_word_lockout_does_not_affect_explicit_dispatch(self) -> None:
        # Exhaust and trip the WAKE_WORD:hey_jarvis passive-trigger lockout.
        for i in range(6):
            self.app._passive_trigger_guard.try_acquire(
                "WAKE_WORD:hey_jarvis", now=float(i) * 2.5, min_rearm_interval_s=2.5
            )
        decision = self.app._passive_trigger_guard.try_acquire(
            "WAKE_WORD:hey_jarvis", now=100.0, min_rearm_interval_s=2.5
        )
        self.assertFalse(decision.allowed)

        # An explicit dispatcher call for an ordinary registered action must
        # still succeed -- it never goes through _passive_trigger_guard at all.
        self.app.dispatcher.register_action("test_explicit_ok", lambda **kw: {"success": True})
        result = self.app.dispatcher.dispatch_action("test_explicit_ok")
        self.assertTrue(result.success)


# ============================================================================
# 2. double_clap heavy external-app fanout: opt-in, not default-on
# ============================================================================


class TestDoubleClapFanoutOptIn(unittest.TestCase):
    def setUp(self) -> None:
        self.app = _make_app()
        self.dispatched: list[str] = []
        self.app.dispatcher.dispatch_action = (
            lambda action_name, **kw: self.dispatched.append(action_name) or MagicMock(success=True, error=None)
        )
        self.voice_calls: list[dict] = []
        self.app._start_voice_interaction = lambda **kw: self.voice_calls.append(kw)

    def tearDown(self) -> None:
        self.app.stop()

    def test_default_first_activation_does_not_launch_external_apps(self) -> None:
        self.assertFalse(
            self.app.config.get("gesture.patterns.double_clap.allow_side_effect_fanout", False)
        )
        with patch("threading.Thread", _SyncThread):
            self.app._on_gesture_event("double_clap", confidence=1.0)
        self.assertEqual(self.dispatched, [], "no external app/browser action may fire by default")
        self.assertEqual(len(self.voice_calls), 1, "default first activation must fall back to a safe voice activation")
        self.assertTrue(self.app.welcome_executed)

    def test_explicit_opt_in_restores_full_fanout(self) -> None:
        self.app.config.set("gesture.patterns.double_clap.allow_side_effect_fanout", True)
        with patch("threading.Thread", _SyncThread):
            self.app._on_gesture_event("double_clap", confidence=1.0)
        self.assertEqual(
            self.dispatched,
            ["spotify", "chrome_claude", "chrome_binance", "tts_welcome", "cursor"],
        )

    def test_subsequent_double_clap_never_launches_external_apps_either_way(self) -> None:
        self.app.config.set("gesture.patterns.double_clap.allow_side_effect_fanout", True)
        self.app.welcome_executed = True  # simulate a prior activation already happened
        with patch("threading.Thread", _SyncThread):
            self.app._on_gesture_event("double_clap", confidence=1.0)
        self.assertEqual(self.dispatched, [])
        self.assertEqual(len(self.voice_calls), 1)

    def test_false_positive_repeated_double_clap_cannot_repeatedly_launch_fanout(self) -> None:
        """
        Even with fanout explicitly enabled, a false-positive/repeated
        double_clap sequence (e.g. from the music the fanout itself just
        started) can launch the heavy fanout at most once -- gated by
        welcome_executed AND the passive-trigger circuit breaker.
        """
        self.app.config.set("gesture.patterns.double_clap.allow_side_effect_fanout", True)
        times = [i * 3.0 for i in range(10)]
        with patch("threading.Thread", _SyncThread), \
             patch("jarvis.core.runaway_guard.time.monotonic", side_effect=lambda: times.pop(0)):
            for _ in range(10):
                self.app._on_gesture_event("double_clap", confidence=1.0)
        spotify_launches = [a for a in self.dispatched if a == "spotify"]
        self.assertEqual(len(spotify_launches), 1, "spotify must only ever be launched once from double_clap")


# ============================================================================
# 3. External-launch dedupe: plugins
# ============================================================================


class TestSpotifyPluginLaunchDedupe(unittest.TestCase):
    def setUp(self) -> None:
        launch_dedupe_guard.reset()
        self.plugin = SpotifyPlugin()
        self.plugin.initialize({}, dispatcher=MagicMock())

    def tearDown(self) -> None:
        launch_dedupe_guard.reset()

    def test_first_launch_allowed(self) -> None:
        with patch("os.startfile", create=True) as mock_startfile:
            result = self.plugin.play_track()
        self.assertTrue(result.get("success"))
        mock_startfile.assert_called_once()

    def test_immediate_repeat_suppressed_truthfully(self) -> None:
        with patch("os.startfile", create=True):
            self.plugin.play_track()
        with patch("os.startfile", create=True) as mock_startfile_2:
            result = self.plugin.play_track()
        self.assertFalse(result.get("success"))
        self.assertEqual(result.get("error_code"), "LAUNCH_RATE_LIMITED")
        mock_startfile_2.assert_not_called()


class TestChromePluginLaunchDedupe(unittest.TestCase):
    def setUp(self) -> None:
        launch_dedupe_guard.reset()
        self.plugin = ChromeMultiMonitorPlugin()
        self.plugin.initialize({}, dispatcher=MagicMock())

    def tearDown(self) -> None:
        launch_dedupe_guard.reset()

    def test_first_open_claude_allowed(self) -> None:
        with patch("subprocess.Popen") as mock_popen:
            result = self.plugin.open_claude()
        self.assertTrue(result.get("success"))
        mock_popen.assert_called_once()

    def test_immediate_repeat_open_claude_suppressed(self) -> None:
        with patch("subprocess.Popen"):
            self.plugin.open_claude()
        with patch("subprocess.Popen") as mock_popen_2:
            result = self.plugin.open_claude()
        self.assertFalse(result.get("success"))
        self.assertEqual(result.get("error_code"), "LAUNCH_RATE_LIMITED")
        mock_popen_2.assert_not_called()

    def test_claude_and_binance_are_independent_targets(self) -> None:
        with patch("subprocess.Popen"):
            r1 = self.plugin.open_claude()
        with patch("subprocess.Popen") as mock_popen:
            r2 = self.plugin.open_binance()
        self.assertTrue(r1.get("success"))
        self.assertTrue(r2.get("success"))
        mock_popen.assert_called_once()


class TestCursorPluginLaunchDedupe(unittest.TestCase):
    def setUp(self) -> None:
        launch_dedupe_guard.reset()
        self.plugin = CursorPlugin()
        self.plugin.initialize({"focus_existing": False}, dispatcher=MagicMock())

    def tearDown(self) -> None:
        launch_dedupe_guard.reset()

    def test_first_spawn_allowed(self) -> None:
        with patch.object(self.plugin, "_get_cursor_exe", return_value="Cursor.exe"), \
             patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 111
            result = self.plugin.focus_cursor()
        self.assertNotEqual(result.get("status"), "suppressed")
        mock_popen.assert_called_once()

    def test_immediate_repeat_spawn_suppressed(self) -> None:
        with patch.object(self.plugin, "_get_cursor_exe", return_value="Cursor.exe"), \
             patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 111
            self.plugin.focus_cursor()
        with patch.object(self.plugin, "_get_cursor_exe", return_value="Cursor.exe"), \
             patch("subprocess.Popen") as mock_popen_2:
            result = self.plugin.focus_cursor()
        self.assertEqual(result.get("status"), "suppressed")
        self.assertEqual(result.get("error_code"), "LAUNCH_RATE_LIMITED")
        mock_popen_2.assert_not_called()

    def test_focusing_an_existing_window_is_never_deduped(self) -> None:
        """Focusing an already-open window is cheap/idempotent and must keep working every call."""
        self.plugin.focus_existing = True
        fake_window = MagicMock(process_name="Cursor.exe", width=800, height=600, hwnd=1, pid=222)
        with patch("jarvis.platform.windows.list_windows", return_value=[fake_window]), \
             patch("jarvis.platform.windows.restore_window"), \
             patch("jarvis.platform.windows.focus_window"):
            r1 = self.plugin.focus_cursor(fullscreen=False)
            r2 = self.plugin.focus_cursor(fullscreen=False)
        self.assertTrue(r1.get("focused"))
        self.assertTrue(r2.get("focused"))


# ============================================================================
# 4. External-launch dedupe: canonical ComputerController path
# ============================================================================


class TestComputerControllerLaunchDedupe(unittest.TestCase):
    def setUp(self) -> None:
        launch_dedupe_guard.reset()
        self.controller = ComputerController(win32=MagicMock())

    def tearDown(self) -> None:
        launch_dedupe_guard.reset()

    def test_open_app_first_call_allowed(self) -> None:
        with patch("subprocess.Popen") as mock_popen:
            result = self.controller.open_app("some_random_unmapped_app")
        self.assertTrue(result.get("success"))
        mock_popen.assert_called_once()

    def test_open_app_immediate_repeat_suppressed(self) -> None:
        with patch("subprocess.Popen"):
            self.controller.open_app("some_random_unmapped_app")
        with patch("subprocess.Popen") as mock_popen_2:
            result = self.controller.open_app("some_random_unmapped_app")
        self.assertFalse(result.get("success"))
        self.assertEqual(result.get("error_code"), "LAUNCH_RATE_LIMITED")
        mock_popen_2.assert_not_called()

    def test_open_app_settings_repeat_is_suppressed(self) -> None:
        """
        Regression for the incident's reported symptom: "settings" maps to
        ms-settings: in APP_MAP and must not be repeatedly re-opened.
        """
        with patch("os.startfile", create=True) as mock_startfile:
            self.controller.open_app("settings")
        with patch("os.startfile", create=True) as mock_startfile_2:
            result = self.controller.open_app("settings")
        self.assertFalse(result.get("success"))
        mock_startfile_2.assert_not_called()

    def test_open_website_immediate_repeat_suppressed(self) -> None:
        with patch("webbrowser.open"):
            self.controller.open_website("github")
        with patch("webbrowser.open") as mock_open_2:
            result = self.controller.open_website("github")
        self.assertFalse(result.get("success"))
        self.assertEqual(result.get("error_code"), "LAUNCH_RATE_LIMITED")
        mock_open_2.assert_not_called()

    def test_open_website_different_targets_independent(self) -> None:
        with patch("webbrowser.open"):
            r1 = self.controller.open_website("github")
        with patch("webbrowser.open") as mock_open:
            r2 = self.controller.open_website("youtube")
        self.assertTrue(r1.get("success"))
        self.assertTrue(r2.get("success"))
        mock_open.assert_called_once()


# ============================================================================
# 4b. Cross-path launch dedupe: the SAME real external target reached
#     through two INDEPENDENT code paths must share ONE budget, not two
#     mutually-unaware ones (pre-commit review requirement #3).
# ============================================================================


class TestCrossPathLaunchDedupeIsUnified(unittest.TestCase):
    """
    Proves jarvis/core/runaway_guard.py's canonical_app_key()/
    canonical_url_key() actually unify independent call sites onto one
    shared LaunchDedupeGuard budget -- e.g. a direct "cursor" action
    dispatch (CursorPlugin) and the generic "mở cursor ide" voice command
    (ComputerController.open_app()) must not be usable as two independent
    ways to bypass the same rate limit for the same real application.
    """

    def setUp(self) -> None:
        launch_dedupe_guard.reset()
        self.controller = ComputerController(win32=MagicMock())
        self.spotify = SpotifyPlugin()
        self.spotify.initialize({}, dispatcher=MagicMock())
        self.cursor = CursorPlugin()
        self.cursor.initialize({"focus_existing": False}, dispatcher=MagicMock())
        self.chrome = ChromeMultiMonitorPlugin()
        self.chrome.initialize({}, dispatcher=MagicMock())

    def tearDown(self) -> None:
        launch_dedupe_guard.reset()

    def test_spotify_plugin_then_open_app_spotify_is_deduped_across_paths(self) -> None:
        with patch("os.startfile", create=True) as mock_startfile:
            first = self.spotify.play_track()
        self.assertTrue(first.get("success"))
        mock_startfile.assert_called_once()

        # A SEPARATE code path (ComputerController.open_app, reachable via
        # the generic "mở spotify"/app_open voice command) requesting the
        # SAME real application must be suppressed too -- not treated as an
        # independent, unrelated launch budget.
        with patch("subprocess.Popen") as mock_popen, patch("os.startfile", create=True) as mock_startfile_2:
            second = self.controller.open_app("spotify")
        self.assertFalse(second.get("success"))
        self.assertEqual(second.get("error_code"), "LAUNCH_RATE_LIMITED")
        mock_popen.assert_not_called()
        mock_startfile_2.assert_not_called()

    def test_cursor_plugin_then_open_app_cursor_ide_is_deduped_across_paths(self) -> None:
        with patch.object(self.cursor, "_get_cursor_exe", return_value="Cursor.exe"), \
             patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 111
            first = self.cursor.focus_cursor()
        self.assertNotEqual(first.get("status"), "suppressed")
        mock_popen.assert_called_once()

        # "cursor ide" is a distinct phrasing/alias reaching the SAME real
        # application via the completely independent ComputerController
        # path (APP_MAP-based subprocess spawn) -- must still be suppressed.
        with patch("subprocess.Popen") as mock_popen_2:
            second = self.controller.open_app("cursor ide")
        self.assertFalse(second.get("success"))
        self.assertEqual(second.get("error_code"), "LAUNCH_RATE_LIMITED")
        mock_popen_2.assert_not_called()

    def test_chrome_claude_then_open_website_claude_same_domain_is_deduped(self) -> None:
        """
        ChromeMultiMonitorPlugin's claude_url ("https://claude.ai/new") and
        ComputerController's WEBSITE_MAP["claude"] ("https://claude.ai") are
        different exact URLs but the same real site -- canonical_url_key()
        (domain-based) must unify them onto one budget.
        """
        with patch("subprocess.Popen") as mock_popen:
            first = self.chrome.open_claude()
        self.assertTrue(first.get("success"))
        mock_popen.assert_called_once()

        with patch("webbrowser.open") as mock_open, patch("subprocess.Popen") as mock_popen_2:
            second = self.controller.open_website("claude")
        self.assertFalse(second.get("success"))
        self.assertEqual(second.get("error_code"), "LAUNCH_RATE_LIMITED")
        mock_open.assert_not_called()
        mock_popen_2.assert_not_called()

    def test_different_apps_remain_independent_across_paths(self) -> None:
        """Cross-path unification must not over-collide unrelated targets."""
        with patch("os.startfile", create=True):
            self.spotify.play_track()
        with patch.object(self.cursor, "_get_cursor_exe", return_value="Cursor.exe"), \
             patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value.pid = 222
            result = self.cursor.focus_cursor()
        self.assertNotEqual(result.get("status"), "suppressed")
        mock_popen.assert_called_once()


# ============================================================================
# 5. STTEngine config-reload dedup + FasterWhisperSTT lazy-by-default preload
# ============================================================================


class TestSTTConfigReloadDedup(unittest.TestCase):
    def test_unchanged_reload_does_not_reconstruct_engine(self) -> None:
        cfg = {"provider": "faster_whisper", "faster_whisper": {"model_size": "base", "preload": False}}
        with patch.object(FasterWhisperSTT, "__init__", return_value=None) as mock_init:
            mock_init.return_value = None
            engine = STTEngine(config=dict(cfg))
        first_primary = engine.primary_engine
        self.assertEqual(mock_init.call_count, 1)

        # Reload with an unrelated field changed (vad_threshold), STT-engine-
        # relevant fields untouched.
        new_cfg = {"stt": {**cfg, "vad_threshold": 0.05}}
        engine._on_config_reloaded(new_cfg)
        self.assertIs(engine.primary_engine, first_primary, "engine must not be reconstructed on a no-op reload")
        self.assertEqual(mock_init.call_count, 1, "FasterWhisperSTT must not be constructed a second time")

    def test_changed_engine_relevant_field_reconstructs_engine_once(self) -> None:
        cfg = {"provider": "faster_whisper", "faster_whisper": {"model_size": "base", "preload": False}}
        with patch.object(FasterWhisperSTT, "__init__", return_value=None) as mock_init:
            engine = STTEngine(config=dict(cfg))
        self.assertEqual(mock_init.call_count, 1)

        new_cfg = {"stt": {"provider": "faster_whisper", "faster_whisper": {"model_size": "large-v3", "preload": False}}}
        with patch.object(FasterWhisperSTT, "__init__", return_value=None) as mock_init_2:
            engine._on_config_reloaded(new_cfg)
        self.assertEqual(mock_init_2.call_count, 1, "a genuinely changed model_size must reconstruct exactly once")

    def test_repeated_unchanged_reloads_never_accumulate_reconstructions(self) -> None:
        cfg = {"provider": "faster_whisper", "faster_whisper": {"model_size": "base", "preload": False}}
        with patch.object(FasterWhisperSTT, "__init__", return_value=None) as mock_init:
            engine = STTEngine(config=dict(cfg))
        new_cfg = {"stt": dict(cfg)}
        with patch.object(FasterWhisperSTT, "__init__", return_value=None) as mock_init_2:
            for _ in range(20):
                engine._on_config_reloaded(new_cfg)
        self.assertEqual(mock_init_2.call_count, 0, "20 no-op reloads must not construct a single new heavy engine")


class TestFasterWhisperLazyPreloadDefault(unittest.TestCase):
    def test_preload_defaults_to_false(self) -> None:
        with patch("jarvis.stt.engine.FASTER_WHISPER_AVAILABLE", True), \
             patch.object(FasterWhisperSTT, "_get_model") as mock_get_model:
            engine = FasterWhisperSTT(config={"model_size": "base"})
            if engine._preload_thread is not None:
                engine._preload_thread.join(timeout=1.0)
        mock_get_model.assert_not_called()

    def test_explicit_preload_true_still_preloads(self) -> None:
        with patch("jarvis.stt.engine.FASTER_WHISPER_AVAILABLE", True), \
             patch.object(FasterWhisperSTT, "_get_model") as mock_get_model:
            engine = FasterWhisperSTT(config={"model_size": "base", "preload": True})
            self.assertIsNotNone(engine._preload_thread)
            engine._preload_thread.join(timeout=2.0)
        mock_get_model.assert_called_once()


class TestFasterWhisperCrossInstanceModelConstructionSerialization(unittest.TestCase):
    """
    Pre-commit review requirement #3: the per-instance double-checked
    locking in FasterWhisperSTT._get_model() only prevents concurrent
    construction WITHIN one instance -- it does nothing to stop an OLD
    engine's still-in-flight preload thread from constructing its model at
    the same time as a NEW replacement engine's preload thread (exactly
    what can happen when preload=True and STTEngine._on_config_reloaded()
    genuinely reconstructs the engine). Proves the new process-wide
    FasterWhisperSTT._model_construction_lock serializes real construction
    across independent instances. Entirely mocked -- no real Whisper model,
    no real CUDA, anywhere in this test.
    """

    def test_two_instances_never_construct_models_concurrently(self) -> None:
        concurrent_count = {"current": 0, "max": 0}
        count_lock = threading.Lock()

        class _SlowFakeWhisperModel:
            def __init__(self, *args, **kwargs) -> None:
                with count_lock:
                    concurrent_count["current"] += 1
                    concurrent_count["max"] = max(concurrent_count["max"], concurrent_count["current"])
                time.sleep(0.05)
                with count_lock:
                    concurrent_count["current"] -= 1

        with patch("jarvis.stt.engine.FASTER_WHISPER_AVAILABLE", True), \
             patch("jarvis.stt.engine.WhisperModel", _SlowFakeWhisperModel):
            engine_a = FasterWhisperSTT(config={"model_size": "base", "preload": False})
            engine_b = FasterWhisperSTT(config={"model_size": "large-v3", "preload": False})

            t1 = threading.Thread(target=engine_a._get_model)
            t2 = threading.Thread(target=engine_b._get_model)
            t1.start()
            t2.start()
            t1.join(timeout=5.0)
            t2.join(timeout=5.0)

        self.assertFalse(t1.is_alive())
        self.assertFalse(t2.is_alive())
        self.assertEqual(concurrent_count["max"], 1, "two FasterWhisperSTT instances constructed models concurrently")
        self.assertIsNotNone(engine_a._model)
        self.assertIsNotNone(engine_b._model)

    def test_construction_lock_is_shared_across_all_instances(self) -> None:
        engine_a = FasterWhisperSTT(config={"preload": False})
        engine_b = FasterWhisperSTT(config={"preload": False})
        self.assertIs(engine_a._model_construction_lock, engine_b._model_construction_lock)
        self.assertIs(FasterWhisperSTT._model_construction_lock, engine_a._model_construction_lock)


if __name__ == "__main__":
    unittest.main()
