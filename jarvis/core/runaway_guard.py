"""
jarvis/core/runaway_guard.py
=============================
Centralized runaway-side-effect protection for JARVIS (P0 incident hardening,
branch fix/voice-control-truthfulness).

Two small, pure, deterministic, monotonic-clock-based guards -- no I/O, no
background threads, bounded memory:

- ``PassiveTriggerGuard``: bounds how often an AMBIENT/passive trigger (a
  wake-word detection, an acoustic gesture pattern) may initiate a heavy
  action pipeline (voice interaction, external app/browser fanout). Enforces
  both a minimum rearm interval AND a sliding-window max-count lockout, so a
  sustained acoustic feedback loop (e.g. music or TTS playback bleeding back
  into the microphone and repeatedly re-triggering wake-word/gesture
  detection) cannot retrigger indefinitely -- once it exceeds
  ``max_triggers`` within ``window_s``, further triggers for that key are
  suppressed for ``lockout_s``. Explicit user-initiated actions (a keyboard
  hotkey, a typed/dispatched text command) must NEVER be routed through this
  guard -- only ``WAKE_WORD:*``/``GESTURE:*``-style ambient trigger keys.

- ``LaunchDedupeGuard``: bounds how often the SAME external app/website
  launch target may actually spawn a new process/window. A burst of
  repeated dispatches naming the same target (whether from a runaway
  passive-trigger loop, a repeated voice command, or a bug) collapses to at
  most one real launch per cooldown window; a suppressed repeat must be
  reported truthfully by the caller (e.g. ``error_code="LAUNCH_RATE_LIMITED"``
  / a "suppressed" status) -- never silently re-reported as a fresh success.

Root-cause context (see CHANGELOG.md / docs/PROJECT_STATE.md for the full
incident writeup): prior to this module, JARVIS had only ad hoc,
minimum-interval-only cooldowns scattered across a few call sites (e.g.
``JarvisApp._on_gesture_event``'s local ``_pattern_last_fired`` dict), with
NO upper bound on how many times a passive trigger could fire over an
extended period, and NO deduplication at all in the external-launch plugins
(Spotify/Chrome/Cursor) or the canonical ``ComputerController.open_app()``/
``open_website()`` path -- every dispatch unconditionally spawned a new
process. Combined, a sustained acoustic feedback loop could drive an
unbounded stream of app/browser launches. These two guards close that gap
centrally, instead of scattering more one-off cooldown variables.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class TriggerDecision:
    """Result of a PassiveTriggerGuard.try_acquire() call."""

    allowed: bool
    reason: str  # "OK", "MIN_INTERVAL", "LOCKOUT_ACTIVE", "LOCKOUT_TRIPPED"
    retry_after_s: float = 0.0


class PassiveTriggerGuard:
    """
    Sliding-window circuit breaker for ambient/passive triggers.

    Never apply this guard to explicit user actions (hotkeys, typed/dispatched
    text commands) -- it exists specifically to bound AMBIENT triggers that
    have no human confirming each individual activation.
    """

    # In today's production wiring, `key` is drawn from a small, fixed
    # vocabulary (one WAKE_WORD:<keyword> per configured wake word, one
    # GESTURE:<pattern> per configured gesture pattern) -- but this cap is
    # kept as explicit defense-in-depth so the tracked-key dictionaries can
    # never grow unbounded even if a future caller ever derives a key from
    # less-bounded input.
    _MAX_TRACKED_KEYS = 256

    def __init__(
        self,
        min_rearm_interval_s: float = 2.5,
        max_triggers: int = 5,
        window_s: float = 60.0,
        lockout_s: float = 120.0,
    ) -> None:
        self.min_rearm_interval_s = float(min_rearm_interval_s)
        self.max_triggers = int(max_triggers)
        self.window_s = float(window_s)
        self.lockout_s = float(lockout_s)
        self._lock = threading.RLock()
        self._history: dict[str, deque[float]] = {}
        self._last_trigger: dict[str, float] = {}
        self._lockout_until: dict[str, float] = {}

    def _prune_locked(self) -> None:
        """
        Bounds total tracked-key count. Must be called with `self._lock` held.
        Evicts the oldest half by last-trigger time, across all three dicts
        together, so they never drift out of sync with each other.
        """
        if len(self._last_trigger) <= self._MAX_TRACKED_KEYS:
            return
        oldest = sorted(self._last_trigger.items(), key=lambda kv: kv[1])
        for k, _ in oldest[: len(oldest) // 2]:
            self._last_trigger.pop(k, None)
            self._history.pop(k, None)
            self._lockout_until.pop(k, None)

    def try_acquire(
        self,
        key: str,
        now: float | None = None,
        min_rearm_interval_s: float | None = None,
    ) -> TriggerDecision:
        """
        Atomically evaluates AND (if allowed) records a trigger attempt for
        `key`. A caller must only proceed with the heavy action when
        `.allowed` is True -- a suppressed decision must be logged/reported
        truthfully, never silently treated as if the action ran.

        `min_rearm_interval_s` optionally overrides the instance default for
        this one call, so a single shared guard instance (and its shared
        sliding-window/lockout policy) can still honor different existing
        per-trigger-type minimum intervals (e.g. wake-word's established 2.5s
        vs gesture's established 3.0s) without needing a separate guard
        instance per trigger type.
        """
        t = now if now is not None else time.monotonic()
        rearm = self.min_rearm_interval_s if min_rearm_interval_s is None else float(min_rearm_interval_s)
        with self._lock:
            lockout_until = self._lockout_until.get(key, 0.0)
            if t < lockout_until:
                return TriggerDecision(False, "LOCKOUT_ACTIVE", lockout_until - t)

            last = self._last_trigger.get(key, -1e9)
            gap = t - last
            if gap < rearm:
                return TriggerDecision(False, "MIN_INTERVAL", rearm - gap)

            hist = self._history.setdefault(key, deque())
            while hist and (t - hist[0]) > self.window_s:
                hist.popleft()

            if len(hist) >= self.max_triggers:
                self._lockout_until[key] = t + self.lockout_s
                return TriggerDecision(False, "LOCKOUT_TRIPPED", self.lockout_s)

            self._last_trigger[key] = t
            hist.append(t)
            self._prune_locked()
            return TriggerDecision(True, "OK")

    def reset(self, key: str | None = None) -> None:
        """Clears tracked state for `key`, or every key when omitted (tests only)."""
        with self._lock:
            if key is None:
                self._history.clear()
                self._last_trigger.clear()
                self._lockout_until.clear()
            else:
                self._history.pop(key, None)
                self._last_trigger.pop(key, None)
                self._lockout_until.pop(key, None)


# Known cross-path app-name aliases. Several independent call sites can
# reach the SAME real external application: e.g. a direct "cursor" action
# dispatch (-> CursorPlugin.focus_cursor()) and the generic
# ComputerController.open_app("cursor ide") path (-> APP_MAP) both launch
# Cursor. Mapping every known alias onto one canonical identity here is
# what makes LaunchDedupeGuard a single authoritative policy across those
# independent code paths -- without it, each path would keep its own,
# mutually-unaware launch budget for the exact same application, and a
# caller alternating between them could bypass the rate limit entirely.
_APP_CANONICAL_ALIASES: dict[str, str] = {
    "spotify": "spotify",
    "cursor": "cursor",
    "cursor ide": "cursor",
    "cursor ai": "cursor",
}


def canonical_app_key(name: str) -> str:
    """
    Maps a raw app name/alias onto one canonical identity for
    LaunchDedupeGuard. Unrecognized names pass through as their own
    (lowercased/stripped) identity -- they simply have no other known path
    to collide with yet.
    """
    n = (name or "").strip().lower()
    return _APP_CANONICAL_ALIASES.get(n, n)


def canonical_url_key(url: str) -> str:
    """
    Maps a URL onto its domain (netloc) for LaunchDedupeGuard. Two
    different exact URLs on the same domain (e.g. a plugin's own default
    deep link vs. a different default resolved elsewhere for "the same
    site") are still the same real-world "open a browser window to this
    site" resource-exhaustion target -- this is what lets
    ChromeMultiMonitorPlugin.open_url() and
    ComputerController.open_website() share one budget for the same site.
    """
    raw = (url or "").strip().lower()
    if not raw:
        return raw
    try:
        from urllib.parse import urlparse
        netloc = urlparse(raw).netloc
        return netloc or raw
    except Exception:
        return raw


class LaunchDedupeGuard:
    """
    Bounded dedupe/rate-limit for external app/website launch targets.

    Callers MUST pass an already-canonicalized `target` (via
    `canonical_app_key()`/`canonical_url_key()` above, or an equivalent
    caller-owned canonicalization) so that the SAME real-world external
    resource reached through different code paths shares one budget here
    -- this guard only de-duplicates by the exact key it is given; it does
    not itself know which raw identifiers refer to the same resource.
    """

    _MAX_TRACKED_KEYS = 512

    def __init__(self, default_cooldown_s: float = 5.0) -> None:
        self.default_cooldown_s = float(default_cooldown_s)
        self._lock = threading.RLock()
        self._last_launch: dict[str, float] = {}

    @staticmethod
    def normalize_key(action: str, target: str) -> str:
        return f"{(action or '').strip().lower()}::{(target or '').strip().lower()}"

    def should_allow(
        self,
        action: str,
        target: str = "",
        cooldown_s: float | None = None,
        now: float | None = None,
    ) -> bool:
        """
        Returns True (and records the launch) only if the normalized
        `action`+`target` key was not already launched within the cooldown
        window. A blocked (False) call does NOT reset the cooldown clock --
        only an allowed launch does -- so once the real cooldown elapses
        since the last ALLOWED launch, a later call is permitted again.
        """
        t = now if now is not None else time.monotonic()
        cd = self.default_cooldown_s if cooldown_s is None else float(cooldown_s)
        key = self.normalize_key(action, target)
        with self._lock:
            last = self._last_launch.get(key)
            if last is not None and (t - last) < cd:
                return False
            self._last_launch[key] = t
            if len(self._last_launch) > self._MAX_TRACKED_KEYS:
                # Bounded memory: evict the oldest half rather than growing forever.
                oldest = sorted(self._last_launch.items(), key=lambda kv: kv[1])
                for k, _ in oldest[: len(oldest) // 2]:
                    self._last_launch.pop(k, None)
            return True

    def reset(self, action: str | None = None, target: str = "") -> None:
        """Clears tracked state for one key, or every key when `action` is omitted (tests only)."""
        with self._lock:
            if action is None:
                self._last_launch.clear()
            else:
                self._last_launch.pop(self.normalize_key(action, target), None)


# Shared, process-wide default instances for production wiring. Callers that
# need isolated state (tests, alternate policies) should construct their own
# instances instead of importing these.
passive_trigger_guard = PassiveTriggerGuard()
launch_dedupe_guard = LaunchDedupeGuard()
