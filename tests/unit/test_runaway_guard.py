"""
tests/unit/test_runaway_guard.py
=================================
Regression tests for jarvis/core/runaway_guard.py -- the P0 runaway-hardening
circuit breaker (PassiveTriggerGuard) and external-launch dedupe/rate-limit
(LaunchDedupeGuard) added after a real-world CPU/GPU/RAM resource-exhaustion
incident (see CHANGELOG.md / docs/PROJECT_STATE.md for the full writeup).

Pure logic only -- no mocking needed: both guards are deterministic,
monotonic-time-based, and accept an explicit `now` for fully reproducible
tests. No real process/app/audio/GPU side effects anywhere in this file.
"""
from __future__ import annotations

import unittest

from jarvis.core.runaway_guard import (
    LaunchDedupeGuard,
    PassiveTriggerGuard,
    TriggerDecision,
    canonical_app_key,
    canonical_url_key,
)


class TestPassiveTriggerGuardMinInterval(unittest.TestCase):
    def setUp(self) -> None:
        self.guard = PassiveTriggerGuard(min_rearm_interval_s=2.5, max_triggers=5, window_s=60.0, lockout_s=120.0)

    def test_first_trigger_allowed(self) -> None:
        decision = self.guard.try_acquire("WAKE_WORD:hey_jarvis", now=0.0)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "OK")

    def test_immediate_retrigger_blocked_by_min_interval(self) -> None:
        self.guard.try_acquire("WAKE_WORD:hey_jarvis", now=0.0)
        decision = self.guard.try_acquire("WAKE_WORD:hey_jarvis", now=0.1)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "MIN_INTERVAL")
        self.assertGreater(decision.retry_after_s, 0.0)

    def test_retrigger_after_min_interval_elapses_is_allowed(self) -> None:
        self.guard.try_acquire("WAKE_WORD:hey_jarvis", now=0.0)
        decision = self.guard.try_acquire("WAKE_WORD:hey_jarvis", now=2.6)
        self.assertTrue(decision.allowed)

    def test_per_call_min_interval_override(self) -> None:
        """Lets one shared guard instance honor different established per-trigger-type cooldowns."""
        self.guard.try_acquire("GESTURE:double_clap", now=0.0, min_rearm_interval_s=3.0)
        blocked = self.guard.try_acquire("GESTURE:double_clap", now=2.9, min_rearm_interval_s=3.0)
        self.assertFalse(blocked.allowed)
        allowed = self.guard.try_acquire("GESTURE:double_clap", now=3.1, min_rearm_interval_s=3.0)
        self.assertTrue(allowed.allowed)

    def test_different_keys_are_independent(self) -> None:
        self.guard.try_acquire("WAKE_WORD:hey_jarvis", now=0.0)
        decision = self.guard.try_acquire("GESTURE:double_clap", now=0.05)
        self.assertTrue(decision.allowed)


class TestPassiveTriggerGuardSlidingWindowLockout(unittest.TestCase):
    """
    This is the actual fix for the incident's core mechanism: previously
    there was NO upper bound on how many times a passive trigger could fire
    over an extended period -- only a minimum interval between triggers, so
    a sustained acoustic feedback loop (e.g. music/TTS bleeding back into
    the microphone) could retrigger a heavy pipeline forever, once every
    `min_rearm_interval_s`. The sliding-window lockout below is the circuit
    breaker that actually trips.
    """

    def setUp(self) -> None:
        self.guard = PassiveTriggerGuard(min_rearm_interval_s=1.0, max_triggers=3, window_s=10.0, lockout_s=20.0)

    def test_repeated_triggers_within_window_eventually_trip_lockout(self) -> None:
        key = "GESTURE:double_clap"
        results = [self.guard.try_acquire(key, now=float(i)) for i in range(5)]
        allowed_flags = [r.allowed for r in results]
        # First 3 triggers (t=0,1,2) fill the window; the 4th (t=3) trips the lockout.
        self.assertEqual(allowed_flags, [True, True, True, False, False])
        self.assertEqual(results[3].reason, "LOCKOUT_TRIPPED")
        self.assertEqual(results[4].reason, "LOCKOUT_ACTIVE")

    def test_lockout_expires_after_lockout_s(self) -> None:
        key = "WAKE_WORD:hey_jarvis"
        for i in range(3):
            self.assertTrue(self.guard.try_acquire(key, now=float(i)).allowed)
        tripped = self.guard.try_acquire(key, now=3.0)
        self.assertFalse(tripped.allowed)
        self.assertEqual(tripped.reason, "LOCKOUT_TRIPPED")

        still_locked = self.guard.try_acquire(key, now=3.0 + 19.9)
        self.assertFalse(still_locked.allowed)

        after_lockout = self.guard.try_acquire(key, now=3.0 + 20.1)
        self.assertTrue(after_lockout.allowed)

    def test_old_triggers_age_out_of_the_window(self) -> None:
        """Triggers spaced further apart than window_s never accumulate toward the lockout."""
        key = "GESTURE:triple_clap"
        for i in range(6):
            decision = self.guard.try_acquire(key, now=float(i) * 11.0)  # 11s apart, window_s=10.0
            self.assertTrue(decision.allowed, f"iteration {i} should be allowed (aged out of window)")

    def test_explicit_hotkey_or_text_trigger_uses_a_distinct_key_and_is_unaffected(self) -> None:
        """
        This guard must never be applied to explicit user actions -- callers
        achieve that simply by never invoking try_acquire() for hotkey/text
        triggers in the first place. This test documents/locks in that a
        differently-prefixed key (as a hotkey/text call site would use, if
        it were ever mistakenly routed through this guard) is tracked
        independently of an exhausted WAKE_WORD/GESTURE key.
        """
        passive_key = "GESTURE:double_clap"
        for i in range(4):
            self.guard.try_acquire(passive_key, now=float(i))
        exhausted = self.guard.try_acquire(passive_key, now=4.0)
        self.assertFalse(exhausted.allowed)

        explicit_key = "HOTKEY:ctrl_shift_j"
        decision = self.guard.try_acquire(explicit_key, now=4.0)
        self.assertTrue(decision.allowed)

    def test_reset_clears_one_key(self) -> None:
        key = "GESTURE:double_clap"
        for i in range(3):
            self.guard.try_acquire(key, now=float(i))
        self.guard.try_acquire(key, now=3.0)  # trips lockout
        self.guard.reset(key)
        decision = self.guard.try_acquire(key, now=3.01)
        self.assertTrue(decision.allowed)


class TestLaunchDedupeGuard(unittest.TestCase):
    def setUp(self) -> None:
        self.guard = LaunchDedupeGuard(default_cooldown_s=5.0)

    def test_first_launch_allowed(self) -> None:
        self.assertTrue(self.guard.should_allow("spotify", "track_uri", now=0.0))

    def test_immediate_duplicate_blocked(self) -> None:
        self.guard.should_allow("spotify", "track_uri", now=0.0)
        self.assertFalse(self.guard.should_allow("spotify", "track_uri", now=0.5))

    def test_different_target_handled_independently(self) -> None:
        self.guard.should_allow("chrome_open_url", "https://claude.ai/new", now=0.0)
        allowed = self.guard.should_allow("chrome_open_url", "https://www.binance.com/en/trade/BTC_USDT", now=0.1)
        self.assertTrue(allowed)

    def test_different_action_same_target_handled_independently(self) -> None:
        self.guard.should_allow("open_app", "cursor", now=0.0)
        allowed = self.guard.should_allow("cursor_spawn", "cursor", now=0.1)
        self.assertTrue(allowed)

    def test_cooldown_elapsed_permits_later_execution(self) -> None:
        self.guard.should_allow("spotify", "track_uri", now=0.0)
        self.assertFalse(self.guard.should_allow("spotify", "track_uri", now=4.9))
        self.assertTrue(self.guard.should_allow("spotify", "track_uri", now=5.1))

    def test_blocked_attempt_does_not_reset_the_cooldown_clock(self) -> None:
        """A blocked call must not extend the cooldown -- only an allowed launch does."""
        self.guard.should_allow("spotify", "track_uri", now=0.0)
        self.guard.should_allow("spotify", "track_uri", now=1.0)  # blocked, must not reset clock
        self.guard.should_allow("spotify", "track_uri", now=2.0)  # blocked, must not reset clock
        allowed = self.guard.should_allow("spotify", "track_uri", now=5.1)
        self.assertTrue(allowed)

    def test_per_call_cooldown_override(self) -> None:
        self.guard.should_allow("cursor_spawn", "cursor", cooldown_s=1.0, now=0.0)
        blocked = self.guard.should_allow("cursor_spawn", "cursor", cooldown_s=1.0, now=0.5)
        self.assertFalse(blocked)
        allowed = self.guard.should_allow("cursor_spawn", "cursor", cooldown_s=1.0, now=1.1)
        self.assertTrue(allowed)

    def test_normalize_key_is_case_and_whitespace_insensitive(self) -> None:
        self.assertEqual(
            LaunchDedupeGuard.normalize_key(" Spotify ", " Track_URI "),
            LaunchDedupeGuard.normalize_key("spotify", "track_uri"),
        )

    def test_bounded_memory_prunes_oldest_entries(self) -> None:
        guard = LaunchDedupeGuard(default_cooldown_s=0.01)
        for i in range(guard._MAX_TRACKED_KEYS + 50):
            guard.should_allow("open_app", f"target_{i}", now=float(i))
        self.assertLessEqual(len(guard._last_launch), guard._MAX_TRACKED_KEYS)

    def test_reset_single_action(self) -> None:
        self.guard.should_allow("spotify", "track_uri", now=0.0)
        self.guard.reset("spotify", "track_uri")
        self.assertTrue(self.guard.should_allow("spotify", "track_uri", now=0.5))


class TestPassiveTriggerGuardBoundedMemory(unittest.TestCase):
    """Pre-commit review requirement: no ever-growing tracked-key dictionary."""

    def test_many_distinct_keys_never_exceed_the_cap(self) -> None:
        guard = PassiveTriggerGuard(min_rearm_interval_s=0.0, max_triggers=1000, window_s=1000.0)
        for i in range(guard._MAX_TRACKED_KEYS + 100):
            guard.try_acquire(f"GESTURE:synthetic_{i}", now=float(i))
        self.assertLessEqual(len(guard._last_trigger), guard._MAX_TRACKED_KEYS)
        # The three tracked dicts must never drift out of sync with each other.
        self.assertEqual(set(guard._last_trigger.keys()), set(guard._history.keys()))


class TestCanonicalLaunchKeys(unittest.TestCase):
    """
    Pre-commit review requirement #3: the SAME real external target reached
    through independent code paths (a dedicated plugin action vs. the
    generic ComputerController.open_app()/open_website() path) must
    canonicalize to the SAME LaunchDedupeGuard key, so one shared guard
    instance is genuinely authoritative across all of them.
    """

    def test_known_cursor_aliases_canonicalize_together(self) -> None:
        self.assertEqual(canonical_app_key("cursor"), "cursor")
        self.assertEqual(canonical_app_key("cursor ide"), "cursor")
        self.assertEqual(canonical_app_key("cursor ai"), "cursor")
        self.assertEqual(canonical_app_key(" Cursor IDE "), "cursor")

    def test_spotify_canonicalizes_to_itself(self) -> None:
        self.assertEqual(canonical_app_key("spotify"), "spotify")
        self.assertEqual(canonical_app_key("Spotify"), "spotify")

    def test_unrecognized_app_name_passes_through_normalized(self) -> None:
        self.assertEqual(canonical_app_key(" Notepad "), "notepad")

    def test_different_urls_same_domain_canonicalize_together(self) -> None:
        self.assertEqual(
            canonical_url_key("https://claude.ai/new"),
            canonical_url_key("https://claude.ai"),
        )
        self.assertEqual(canonical_url_key("https://claude.ai/new"), "claude.ai")

    def test_different_domains_remain_distinct(self) -> None:
        self.assertNotEqual(
            canonical_url_key("https://claude.ai/new"),
            canonical_url_key("https://www.binance.com/en/trade/BTC_USDT"),
        )

    def test_malformed_url_does_not_raise(self) -> None:
        # Falls back to the raw (normalized) string rather than raising.
        result = canonical_url_key("not a url at all :::")
        self.assertIsInstance(result, str)

    def test_empty_url_returns_empty(self) -> None:
        self.assertEqual(canonical_url_key(""), "")
        self.assertEqual(canonical_url_key(None), "")


class TestTriggerDecisionShape(unittest.TestCase):
    def test_trigger_decision_is_a_frozen_dataclass_with_expected_fields(self) -> None:
        d = TriggerDecision(allowed=True, reason="OK")
        self.assertTrue(d.allowed)
        self.assertEqual(d.reason, "OK")
        self.assertEqual(d.retry_after_s, 0.0)
        with self.assertRaises(Exception):
            d.allowed = False  # frozen -- must not be mutable


if __name__ == "__main__":
    unittest.main()
