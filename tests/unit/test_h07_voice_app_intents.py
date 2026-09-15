"""
tests/unit/test_h07_voice_app_intents.py
=========================================
H-07 contract tests: standardized voice-intent routing for the three
canonical launch targets -- Settings, Spotify, Claude.

Covers, per the H-07 audit:
  A. Alias matrix -- every Settings/Spotify/Claude alias normalizes to one
     canonical intent/target (jarvis/llm/router.py).
  B. Diacritic / non-diacritic equivalence.
  C. English aliases.
  D. Negative/non-command phrases (questions, comparisons, negations) do NOT
     launch anything.
  E. One spoken command -> exactly one real-world launch target, no fanout
     into an unrelated app/site.
  F. 20 interleaved rounds (60 evaluations total) -- deterministic, mocked
     execution proving no cross-target leakage.
  G. Rate-limit proof with controlled monotonic timestamps, including
     cross-path dedupe (SpotifyPlugin vs generic ComputerController.open_app,
     ChromeMultiMonitorPlugin.open_claude vs generic open_website).
  H. gesture.patterns.double_clap.allow_side_effect_fanout stays default
     False and is untouched by any H-07 router change.

All mocked at the OS boundary only (os.startfile / subprocess.Popen /
webbrowser.open) -- this file never starts a real Spotify/Chrome/Settings
process and never opens a real browser window.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from jarvis.automation.control import ComputerController
from jarvis.core.app import JarvisApp
from jarvis.core.runaway_guard import canonical_app_key, canonical_url_key, launch_dedupe_guard
from jarvis.llm.router import LLMIntentRouter
from jarvis.plugins.chrome import ChromeMultiMonitorPlugin
from jarvis.plugins.spotify import SpotifyPlugin

# ============================================================================
# Alias fixtures (drawn directly from the H-07 contract's example lists)
# ============================================================================

SETTINGS_ALIASES = [
    "mở cài đặt",
    "mở cài đặt windows",
    "bật settings",
    "mở settings",
    "mo settings",
    "open settings",
    "cài đặt",
    "mo cai dat",
]

SPOTIFY_ALIASES = [
    "mở spotify",
    "bật spotify",
    "mở nhạc spotify",
    "mo spotify",
    "open spotify",
]

CLAUDE_ALIASES = [
    "mở claude",
    "bật claude",
    "mở claude ai",
    "mo claude",
    "open claude",
    "open claude ai",
]

NEGATIVE_PHRASES = [
    "spotify có tốt không",
    "claude là gì",
    "settings nghĩa là gì",
    "so sánh claude với chatgpt",
    "tôi không muốn mở spotify",
    "mở tủ lạnh giúp tôi",  # contains "mở" but not any H-07 target
]


def _router() -> LLMIntentRouter:
    return LLMIntentRouter(llm_client=None, dispatcher=None, fast_path_enabled=True)


def _make_handler_app() -> JarvisApp:
    """
    A lightweight (not fully-initialized) JarvisApp exposing only the real,
    unmodified _handle_app_open()/_handle_web_open() methods bound to a real
    ComputerController -- the exact production dataflow router-output params
    pass through, without booting audio/STT/TTS/plugins/dashboard.
    """
    app = JarvisApp.__new__(JarvisApp)
    app.computer_controller = ComputerController(win32=MagicMock())
    return app


def _make_spotify_plugin() -> SpotifyPlugin:
    plugin = SpotifyPlugin()
    plugin.initialize({}, dispatcher=MagicMock())
    return plugin


def _dispatch(app: JarvisApp, spotify: SpotifyPlugin, intent) -> dict:
    """
    Routes an IntentResult to the SAME real handler ActionDispatcher would
    pick by action_name in production: "spotify" -> SpotifyPlugin.play_track,
    "app_open" -> JarvisApp._handle_app_open, "web_open" ->
    JarvisApp._handle_web_open. Only this routing-by-name is test scaffolding;
    every handler/plugin/controller call below it is the real production code.
    """
    if intent.action_name == "spotify":
        return spotify.play_track(**intent.parameters)
    if intent.action_name == "app_open":
        return app._handle_app_open(**intent.parameters)
    if intent.action_name == "web_open":
        return app._handle_web_open(**intent.parameters)
    return {"success": False, "status": "unexpected_action", "action_name": intent.action_name}


class _BaseCase(unittest.TestCase):
    def setUp(self) -> None:
        launch_dedupe_guard.reset()

    def tearDown(self) -> None:
        launch_dedupe_guard.reset()


# ============================================================================
# A / B / C. Alias matrix: diacritic, non-diacritic, and English forms all
# normalize to ONE canonical intent/target per H-07 target.
# ============================================================================


class TestSettingsAliasMatrix(_BaseCase):
    def test_all_settings_aliases_produce_the_same_canonical_app_open(self):
        router = _router()
        for phrase in SETTINGS_ALIASES:
            with self.subTest(phrase=phrase):
                r = router.parse_intent(phrase)
                self.assertEqual(r.action_name, "app_open", f"{phrase!r} did not route to app_open")
                self.assertEqual(r.parameters.get("app_name"), "Settings")
                self.assertEqual(r.parameters.get("app"), "ms-settings:")

    def test_all_settings_aliases_share_one_launch_dedupe_identity(self):
        router = _router()
        keys = set()
        for phrase in SETTINGS_ALIASES:
            r = router.parse_intent(phrase)
            app_name = r.parameters.get("app_name")
            keys.add(canonical_app_key(app_name))
        self.assertEqual(keys, {"settings"}, f"Settings aliases diverged to multiple dedupe keys: {keys}")


class TestSpotifyAliasMatrix(_BaseCase):
    def test_all_spotify_aliases_produce_the_canonical_spotify_action(self):
        router = _router()
        for phrase in SPOTIFY_ALIASES:
            with self.subTest(phrase=phrase):
                r = router.parse_intent(phrase)
                self.assertEqual(r.action_name, "spotify", f"{phrase!r} did not route to spotify")

    def test_all_spotify_aliases_resolve_to_the_same_real_launch(self):
        """
        SpotifyPlugin.play_track() only ever consumes `song_uri` (every
        other router param is inert) and keys its dedupe identity on the
        fixed string "spotify" regardless of caller params -- so every
        alias must launch the exact same URI and share one dedupe budget,
        proving one canonical downstream identity even though the router's
        own parameter shapes differ cosmetically across aliases.
        """
        router = _router()
        spotify = _make_spotify_plugin()
        launched_uris = set()
        for phrase in SPOTIFY_ALIASES:
            launch_dedupe_guard.reset()
            r = router.parse_intent(phrase)
            with patch("os.startfile", create=True) as mock_startfile:
                res = spotify.play_track(**r.parameters)
            self.assertTrue(res.get("success"), f"{phrase!r} failed to launch Spotify: {res}")
            launched_uris.add(mock_startfile.call_args[0][0])
        self.assertEqual(len(launched_uris), 1, f"Spotify aliases launched different URIs: {launched_uris}")


class TestClaudeAliasMatrix(_BaseCase):
    def test_all_claude_aliases_produce_web_open_targeting_claude(self):
        router = _router()
        for phrase in CLAUDE_ALIASES:
            with self.subTest(phrase=phrase):
                r = router.parse_intent(phrase)
                self.assertEqual(r.action_name, "web_open", f"{phrase!r} did not route to web_open")
                self.assertEqual(r.parameters.get("site"), "claude")

    def test_all_claude_aliases_resolve_to_the_same_real_domain(self):
        """
        Regression lock for the confirmed H-07 gap: "mở claude ai" (and
        "open claude ai") used to reconstruct target="claude ai", which was
        NOT a WEBSITE_MAP key, silently falling through to a Google search
        for "claude ai" instead of opening Claude. Every Claude alias must
        now resolve to the identical claude.ai domain end-to-end.
        """
        router = _router()
        app = _make_handler_app()
        domains = set()
        for phrase in CLAUDE_ALIASES:
            launch_dedupe_guard.reset()
            r = router.parse_intent(phrase)
            with patch("webbrowser.open") as mock_open:
                res = app._handle_web_open(**r.parameters)
            self.assertEqual(res.get("status"), "success", f"{phrase!r} failed to open Claude: {res}")
            opened_url = mock_open.call_args[0][0]
            domains.add(canonical_url_key(opened_url))
        self.assertEqual(domains, {"claude.ai"}, f"Claude aliases diverged to multiple domains: {domains}")


# ============================================================================
# D. Negative / non-command phrases must NOT launch anything.
# ============================================================================


class TestNegativePhrasesDoNotLaunch(_BaseCase):
    _H07_LAUNCHES = {
        ("spotify",),
        ("app_open", "Settings"),
        ("web_open", "claude"),
    }

    def test_questions_comparisons_and_negations_never_launch(self):
        router = _router()
        for phrase in NEGATIVE_PHRASES:
            with self.subTest(phrase=phrase):
                r = router.parse_intent(phrase)
                is_h07_launch = (
                    r.action_name == "spotify"
                    or (r.action_name == "app_open" and r.parameters.get("app_name") == "Settings")
                    or (r.action_name == "web_open" and r.parameters.get("site") == "claude")
                )
                self.assertFalse(
                    is_h07_launch,
                    f"{phrase!r} incorrectly resolved to a launch: "
                    f"{r.action_name} {r.parameters}",
                )

    def test_negated_spotify_request_reaches_no_real_launch_call(self):
        """End-to-end: the negated phrase must not even reach os.startfile."""
        router = _router()
        spotify = _make_spotify_plugin()
        app = _make_handler_app()
        r = router.parse_intent("tôi không muốn mở spotify")
        with patch("os.startfile", create=True) as mock_startfile, \
             patch("webbrowser.open") as mock_browser_open, \
             patch("subprocess.Popen") as mock_popen:
            _dispatch(app, spotify, r)
        mock_startfile.assert_not_called()
        mock_browser_open.assert_not_called()
        mock_popen.assert_not_called()


# ============================================================================
# E / F. One command -> exactly one launch target, no fanout. 20 interleaved
# rounds (60 evaluations) across Settings / Spotify / Claude.
# ============================================================================


class TestNoFanoutAndInterleavedRounds(_BaseCase):
    _ROUNDS = [
        ("mở cài đặt", "settings"),
        ("mở spotify", "spotify"),
        ("mở claude", "claude"),
    ]

    def test_single_settings_command_touches_only_the_settings_boundary(self):
        router = _router()
        app = _make_handler_app()
        spotify = _make_spotify_plugin()
        r = router.parse_intent("mở cài đặt")
        with patch("os.startfile", create=True) as mock_startfile, \
             patch("webbrowser.open") as mock_browser_open, \
             patch("subprocess.Popen") as mock_popen:
            res = _dispatch(app, spotify, r)
        self.assertEqual(res.get("status"), "success")
        mock_startfile.assert_called_once_with("ms-settings:")
        mock_browser_open.assert_not_called()
        mock_popen.assert_not_called()

    def test_single_spotify_command_touches_only_the_spotify_boundary(self):
        router = _router()
        app = _make_handler_app()
        spotify = _make_spotify_plugin()
        r = router.parse_intent("mở spotify")
        with patch("os.startfile", create=True) as mock_startfile, \
             patch("webbrowser.open") as mock_browser_open, \
             patch("subprocess.Popen") as mock_popen:
            res = _dispatch(app, spotify, r)
        self.assertTrue(res.get("success"))
        mock_startfile.assert_called_once()
        self.assertNotEqual(mock_startfile.call_args[0][0], "ms-settings:")
        mock_browser_open.assert_not_called()
        mock_popen.assert_not_called()

    def test_single_claude_command_touches_only_the_claude_boundary(self):
        router = _router()
        app = _make_handler_app()
        spotify = _make_spotify_plugin()
        r = router.parse_intent("mở claude")
        with patch("os.startfile", create=True) as mock_startfile, \
             patch("webbrowser.open") as mock_browser_open, \
             patch("subprocess.Popen") as mock_popen:
            res = _dispatch(app, spotify, r)
        self.assertEqual(res.get("status"), "success")
        mock_browser_open.assert_called_once()
        self.assertEqual(canonical_url_key(mock_browser_open.call_args[0][0]), "claude.ai")
        mock_startfile.assert_not_called()
        mock_popen.assert_not_called()

    def test_20_interleaved_rounds_no_cross_target_leakage(self):
        """
        20 rounds x (Settings, Spotify, Claude) = 60 intent evaluations /
        dispatch attempts. Each round's dedupe state is reset so this test
        isolates ROUTING correctness (section F) from rate-limiting
        (covered separately in section G) -- every one of the 60 attempts
        must resolve to exactly its own target and touch only that target's
        OS-level boundary; never any other target's.
        """
        router = _router()
        app = _make_handler_app()
        spotify = _make_spotify_plugin()

        total_evaluations = 0
        for round_num in range(20):
            for phrase, expected_target in self._ROUNDS:
                launch_dedupe_guard.reset()
                with patch("os.startfile", create=True) as mock_startfile, \
                     patch("webbrowser.open") as mock_browser_open, \
                     patch("subprocess.Popen") as mock_popen:
                    r = router.parse_intent(phrase)
                    res = _dispatch(app, spotify, r)
                total_evaluations += 1

                if expected_target == "settings":
                    self.assertEqual(r.action_name, "app_open", f"round {round_num}: {phrase!r}")
                    self.assertEqual(res.get("status"), "success")
                    mock_startfile.assert_called_once_with("ms-settings:")
                    mock_browser_open.assert_not_called()
                    mock_popen.assert_not_called()
                elif expected_target == "spotify":
                    self.assertEqual(r.action_name, "spotify", f"round {round_num}: {phrase!r}")
                    self.assertTrue(res.get("success"))
                    mock_startfile.assert_called_once()
                    self.assertNotEqual(mock_startfile.call_args[0][0], "ms-settings:")
                    mock_browser_open.assert_not_called()
                    mock_popen.assert_not_called()
                elif expected_target == "claude":
                    self.assertEqual(r.action_name, "web_open", f"round {round_num}: {phrase!r}")
                    self.assertEqual(res.get("status"), "success")
                    mock_browser_open.assert_called_once()
                    self.assertEqual(canonical_url_key(mock_browser_open.call_args[0][0]), "claude.ai")
                    mock_startfile.assert_not_called()
                    mock_popen.assert_not_called()

        self.assertEqual(total_evaluations, 60)


# ============================================================================
# G. Rate-limit proof with controlled monotonic timestamps.
# ============================================================================


class TestH07RateLimitProof(_BaseCase):
    def test_settings_too_fast_repeat_suppressed_then_allowed_after_cooldown(self):
        controller = ComputerController(win32=MagicMock())
        times = iter([0.0, 1.0, 10.0])
        with patch("jarvis.core.runaway_guard.time.monotonic", side_effect=lambda: next(times)):
            with patch("os.startfile", create=True) as m1:
                r1 = controller.open_app("Settings")
            self.assertTrue(r1.get("success"))
            m1.assert_called_once()

            with patch("os.startfile", create=True) as m2:
                r2 = controller.open_app("Settings")
            self.assertFalse(r2.get("success"), "immediate repeat must be suppressed truthfully")
            self.assertEqual(r2.get("error_code"), "LAUNCH_RATE_LIMITED")
            m2.assert_not_called()

            with patch("os.startfile", create=True) as m3:
                r3 = controller.open_app("Settings")
            self.assertTrue(r3.get("success"), "same target must be allowed again after cooldown elapses")

    def test_spotify_too_fast_repeat_suppressed_then_allowed_after_cooldown(self):
        spotify = _make_spotify_plugin()
        times = iter([0.0, 1.0, 10.0])
        with patch("jarvis.core.runaway_guard.time.monotonic", side_effect=lambda: next(times)):
            with patch("os.startfile", create=True) as m1:
                r1 = spotify.play_track()
            self.assertTrue(r1.get("success"))
            m1.assert_called_once()

            with patch("os.startfile", create=True) as m2:
                r2 = spotify.play_track()
            self.assertFalse(r2.get("success"))
            self.assertEqual(r2.get("error_code"), "LAUNCH_RATE_LIMITED")
            m2.assert_not_called()

            with patch("os.startfile", create=True) as m3:
                r3 = spotify.play_track()
            self.assertTrue(r3.get("success"))

    def test_claude_too_fast_repeat_suppressed_then_allowed_after_cooldown(self):
        app = _make_handler_app()
        times = iter([0.0, 1.0, 10.0])
        with patch("jarvis.core.runaway_guard.time.monotonic", side_effect=lambda: next(times)):
            with patch("webbrowser.open") as m1:
                r1 = app._handle_web_open(target="claude", site="claude")
            self.assertEqual(r1.get("status"), "success")
            m1.assert_called_once()

            with patch("webbrowser.open") as m2:
                r2 = app._handle_web_open(target="claude", site="claude")
            self.assertEqual(r2.get("status"), "failed")
            m2.assert_not_called()

            with patch("webbrowser.open") as m3:
                r3 = app._handle_web_open(target="claude", site="claude")
            self.assertEqual(r3.get("status"), "success")

    def test_different_targets_are_not_incorrectly_cross_suppressed(self):
        controller = ComputerController(win32=MagicMock())
        spotify = _make_spotify_plugin()
        app = _make_handler_app()
        with patch("jarvis.core.runaway_guard.time.monotonic", return_value=0.0):
            with patch("os.startfile", create=True) as m1:
                r_settings = controller.open_app("Settings")
            with patch("os.startfile", create=True) as m2:
                r_spotify = spotify.play_track()
            with patch("webbrowser.open") as m3:
                r_claude = app._handle_web_open(target="claude", site="claude")
        self.assertTrue(r_settings.get("success"))
        self.assertTrue(r_spotify.get("success"))
        self.assertEqual(r_claude.get("status"), "success")
        m1.assert_called_once()
        m2.assert_called_once()
        m3.assert_called_once()

    def test_spotify_plugin_and_generic_app_path_share_one_dedupe_budget(self):
        """Cross-path dedupe: SpotifyPlugin.play_track() vs
        ComputerController.open_app("spotify") -- the same real app reached
        through two independent code paths must not double the budget."""
        spotify = _make_spotify_plugin()
        controller = ComputerController(win32=MagicMock())
        with patch("os.startfile", create=True) as m1:
            first = spotify.play_track()
        self.assertTrue(first.get("success"))
        m1.assert_called_once()

        with patch("os.startfile", create=True) as m2, patch("subprocess.Popen") as m2b:
            second = controller.open_app("spotify")
        self.assertFalse(second.get("success"))
        self.assertEqual(second.get("error_code"), "LAUNCH_RATE_LIMITED")
        m2.assert_not_called()
        m2b.assert_not_called()

    def test_chrome_claude_plugin_and_generic_website_path_share_one_dedupe_budget(self):
        """Cross-path dedupe: ChromeMultiMonitorPlugin.open_claude()
        ("https://claude.ai/new") vs the generic web_open path
        ("https://claude.ai") -- different exact URLs, same domain, must
        share one budget via canonical_url_key()."""
        chrome = ChromeMultiMonitorPlugin()
        chrome.initialize({}, dispatcher=MagicMock())
        app = _make_handler_app()

        with patch("subprocess.Popen") as m1:
            first = chrome.open_claude()
        self.assertTrue(first.get("success"))
        m1.assert_called_once()

        with patch("webbrowser.open") as m2:
            second = app._handle_web_open(target="claude", site="claude")
        self.assertEqual(second.get("status"), "failed")
        m2.assert_not_called()


# ============================================================================
# H. double_clap side-effect fanout stays default False, untouched by H-07.
# ============================================================================


class TestDoubleClapFanoutStillDefaultFalse(unittest.TestCase):
    def test_default_config_yaml_declares_fanout_disabled(self):
        """
        Stdlib-only check (no PyYAML -- CI intentionally does not install
        it): locates the unique `double_clap:` block in
        config/default_config.yaml via indentation-bounded textual
        inspection (never a YAML parser, never a regex loose enough to
        match another section) and asserts it contains exactly the line
        `allow_side_effect_fanout: false`.
        """
        config_text = Path("config/default_config.yaml").read_text(encoding="utf-8")
        lines = config_text.splitlines()

        def indent_of(line: str) -> int:
            return len(line) - len(line.lstrip(" "))

        double_clap_indices = [i for i, line in enumerate(lines) if line.strip() == "double_clap:"]
        self.assertEqual(
            len(double_clap_indices),
            1,
            "Expected exactly one 'double_clap:' section in "
            f"config/default_config.yaml, found {len(double_clap_indices)} "
            "-- a missing or duplicated section must not silently pass.",
        )
        header_index = double_clap_indices[0]
        header_indent = indent_of(lines[header_index])

        # Bounded block: every line strictly more indented than the
        # "double_clap:" header, up to (not including) the next line at the
        # same or lesser indentation -- i.e. the next sibling key
        # ("triple_clap:") or an enclosing section. This is a structural
        # (indentation-based) bound, not a fixed line count, so it can never
        # accidentally spill into -- or stop short of -- the real section.
        block: list[str] = []
        for line in lines[header_index + 1:]:
            if line.strip() == "":
                block.append(line)
                continue
            if indent_of(line) <= header_indent:
                break
            block.append(line)

        fanout_disabled_lines = [line for line in block if line.strip() == "allow_side_effect_fanout: false"]
        self.assertEqual(
            len(fanout_disabled_lines),
            1,
            "gesture.patterns.double_clap block must contain exactly one "
            "'allow_side_effect_fanout: false' line -- got "
            f"{len(fanout_disabled_lines)} (missing, duplicated, or the "
            "value differs).",
        )

        fanout_enabled_lines = [line for line in block if line.strip() == "allow_side_effect_fanout: true"]
        self.assertEqual(
            len(fanout_enabled_lines),
            0,
            "gesture.patterns.double_clap.allow_side_effect_fanout must "
            "default to false, but found it set to true.",
        )

    def test_double_clap_first_activation_does_not_launch_spotify_or_claude(self):
        """
        End-to-end: with no explicit override, a double_clap gesture must
        fall back to a safe voice activation and must NOT dispatch any of
        the external-app fanout actions (spotify/chrome_claude/
        chrome_binance/cursor) -- proving H-07's router/alias changes did
        not alter this gate's behavior.
        """
        app = JarvisApp(headless=True, no_hot_reload=True)
        app.initialize()
        try:
            dispatched: list[str] = []
            app.dispatcher.dispatch_action = (
                lambda action_name, **kw: dispatched.append(action_name) or MagicMock(success=True, error=None)
            )
            voice_calls: list[dict] = []
            app._start_voice_interaction = lambda **kw: voice_calls.append(kw)

            self.assertFalse(
                app.config.get("gesture.patterns.double_clap.allow_side_effect_fanout", False)
            )

            class _SyncThread:
                def __init__(self, target=None, args=(), kwargs=None, daemon=None, name=None) -> None:
                    self._target = target
                    self._args = args
                    self._kwargs = kwargs or {}

                def start(self) -> None:
                    if self._target:
                        self._target(*self._args, **self._kwargs)

                def join(self, timeout=None) -> None:
                    pass

            with patch("threading.Thread", _SyncThread):
                app._on_gesture_event("double_clap", confidence=1.0)

            self.assertEqual(dispatched, [], "no external app/browser action may fire by default")
            self.assertEqual(len(voice_calls), 1)
        finally:
            app.stop()


if __name__ == "__main__":
    unittest.main()
