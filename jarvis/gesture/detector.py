"""
jarvis/gesture/detector.py
==========================
Thread-safe, multi-pattern acoustic gesture detector with queue buffering,
temporal disambiguation, and action dispatching.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Union
import numpy as np

from jarvis.audio.dsp import AudioDSPProcessor
from jarvis.core.logger import log_trigger
from jarvis.core.models import RequesterContext
from jarvis.gesture.models import (
    ClapEvent,
    DetectorState,
    GesturePatternConfig,
    GestureResult,
    GestureType,
)
from jarvis.gesture.patterns import get_default_patterns

logger = logging.getLogger("jarvis.gesture.detector")

# Module-level epsilon tolerance for IEEE 754 float comparisons
EPS = 1e-4


class GestureDetector:
    """
    Real-time acoustic transient gesture detector.

    Processes audio stream blocks or discrete transient events, manages sliding
    event queues, resolves prefix collisions through calibrated disambiguation
    windows, enforces debounce cooldowns, and routes triggers to ActionDispatcher.
    """

    def __init__(
        self,
        min_double_gap_s: float = 0.05,
        max_double_gap_s: float = 0.35,
        cooldown_s: float = 0.45,
        triple_clap_gap_s: float = 0.40,
        pause_min_s: float = 0.50,
        pause_max_s: float = 1.20,
        disambiguation_timeout_s: Optional[float] = None,
        dsp: Optional[AudioDSPProcessor] = None,
        dispatcher: Optional[Any] = None,
        event_bus: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
        on_gesture: Optional[Callable[[str, float], None]] = None,
    ) -> None:
        self._lock = threading.RLock()
        self.dsp = dsp or AudioDSPProcessor()
        self.dispatcher = dispatcher
        self.event_bus = event_bus
        self.on_gesture = on_gesture

        # Timing parameters
        self.min_double_gap_s = float(min_double_gap_s)
        self.max_double_gap_s = float(max_double_gap_s)
        self.cooldown_s = float(cooldown_s)
        self.triple_clap_gap_s = float(triple_clap_gap_s)
        self.pause_min_s = float(pause_min_s)
        self.pause_max_s = float(pause_max_s)
        self.disambiguation_timeout_s = (
            float(disambiguation_timeout_s) if disambiguation_timeout_s is not None else self.max_double_gap_s
        )

        # Pattern registrations
        self._patterns: Dict[GestureType, GesturePatternConfig] = get_default_patterns(
            min_double_gap_s=self.min_double_gap_s,
            max_double_gap_s=self.max_double_gap_s,
            cooldown_s=self.cooldown_s,
            triple_clap_gap_s=self.triple_clap_gap_s,
            pause_min_s=self.pause_min_s,
            pause_max_s=self.pause_max_s,
        )

        if config:
            self.configure_from_dict(config)

        # State machine internals
        self._state: DetectorState = DetectorState.IDLE
        self._clap_buffer: List[ClapEvent] = []
        self._last_trigger_time: float = -100.0
        self._last_raw_clap_time: float = -100.0  # Tracks every transient for chatter suppression
        self._pending_deadline: float = 0.0
        self._callbacks: List[Callable[[GestureResult], None]] = []

    def register_pattern(self, pattern: GesturePatternConfig) -> None:
        """Register or update a gesture pattern configuration."""
        with self._lock:
            self._patterns[pattern.gesture_type] = pattern

    def add_callback(self, cb: Callable[[GestureResult], None]) -> None:
        """Register external listener callback."""
        with self._lock:
            if cb not in self._callbacks:
                self._callbacks.append(cb)

    def reset(self) -> None:
        """Reset internal buffers and state to IDLE."""
        with self._lock:
            self._state = DetectorState.IDLE
            self._clap_buffer.clear()
            self._pending_deadline = 0.0
            self._last_trigger_time = -100.0
            self._last_raw_clap_time = -100.0
            if hasattr(self.dsp, "reset"):
                self.dsp.reset()

    def configure_from_dict(self, cfg: Dict[str, Any]) -> None:
        """Update detector thresholds dynamically from configuration dictionary."""
        with self._lock:
            dsp_cfg = cfg.get("dsp", cfg)
            if "cooldown_s" in dsp_cfg:
                self.cooldown_s = float(dsp_cfg["cooldown_s"])
            if "min_double_gap_s" in dsp_cfg:
                self.min_double_gap_s = float(dsp_cfg["min_double_gap_s"])
            if "max_double_gap_s" in dsp_cfg:
                self.max_double_gap_s = float(dsp_cfg["max_double_gap_s"])

            patterns_cfg = cfg.get("patterns", {})
            for p_key, p_val in patterns_cfg.items():
                try:
                    g_type = GestureType(p_key)
                except ValueError:
                    continue
                if g_type in self._patterns:
                    p = self._patterns[g_type]
                    p.enabled = bool(p_val.get("enabled", p.enabled))
                    if "actions" in p_val:
                        p.actions = list(p_val.get("actions", p.actions))
                    if "min_gap_s" in p_val:
                        p.min_gap_s = float(p_val["min_gap_s"])
                    if "max_gap_s" in p_val:
                        p.max_gap_s = float(p_val["max_gap_s"])
                    if "pause_min_s" in p_val:
                        p.pause_min_s = float(p_val["pause_min_s"])
                    if "pause_max_s" in p_val:
                        p.pause_max_s = float(p_val["pause_max_s"])

    def process_block(self, block: np.ndarray) -> Optional[GestureResult]:
        """Alias for feed_audio_block."""
        return self.feed_audio_block(block)

    def feed_audio_block(self, block: np.ndarray, timestamp: Optional[float] = None) -> Optional[GestureResult]:
        """
        Process a real-time audio block through DSP and state machine.
        """
        now = timestamp if timestamp is not None else time.monotonic()
        dsp_res = self.dsp.process_block(block)

        result: Optional[GestureResult] = None

        if dsp_res.get("is_transient"):
            clap = ClapEvent(
                timestamp=now,
                amplitude=float(dsp_res.get("rms", 0.0)),
                duration=0.04,
                noise_floor=float(dsp_res.get("noise_floor", 0.0)),
                threshold=float(dsp_res.get("threshold", 0.0)),
                snr_ratio=float(dsp_res.get("rms", 0.0)) / max(float(dsp_res.get("noise_floor", 1e-7)), 1e-7),
            )
            result = self.feed_clap(clap)

        # Check pending timeout expiration if no immediate event was generated
        if result is None:
            result = self.tick(now)

        return result

    def feed_clap(self, clap: ClapEvent) -> Optional[GestureResult]:
        """
        Ingest a transient clap event into the pattern state machine.
        Enforces chatter suppression, epsilon-tolerant boundary validation,
        and clean dead-zone buffer resetting.
        """
        with self._lock:
            now = clap.timestamp

            # 1. Cooldown Check (with EPS tolerance)
            if now < self._last_trigger_time + self.cooldown_s - EPS:
                logger.debug("Clap at %.3fs dropped during active cooldown", now)
                self._last_raw_clap_time = now
                return None

            # 2. Echo / Chatter Suppression
            # Every transient updates _last_raw_clap_time so rapid bursts (<50ms) cannot accumulate
            if (now - self._last_raw_clap_time) < (self.min_double_gap_s - EPS):
                logger.debug("Clap at %.3fs ignored as acoustic echo/chatter (raw gap=%.3fs)", now, now - self._last_raw_clap_time)
                self._last_raw_clap_time = now
                return None

            self._last_raw_clap_time = now

            # 3. State Machine Transitions
            if not self._clap_buffer:
                # First clap of a potential pattern
                self._clap_buffer.append(clap)
                self._state = DetectorState.WAIT_CLAP_2
                logger.debug("State -> WAIT_CLAP_2: First clap at %.3fs", now)
                return None

            if len(self._clap_buffer) == 1:
                t1 = self._clap_buffer[0].timestamp
                gap1 = now - t1

                # A. 2-clap syncopation (Clap -> Pause -> Clap) check
                p_pause = self._patterns.get(GestureType.CLAP_PAUSE_CLAP)
                if p_pause and p_pause.enabled and (p_pause.pause_min_s - EPS) <= gap1 <= (p_pause.pause_max_s + EPS):
                    self._clap_buffer.append(clap)
                    return self._emit_trigger(GestureType.CLAP_PAUSE_CLAP, self._clap_buffer, [gap1], now)

                # B. Standard 2nd clap arrival (Double Clap or 1st leg of Triple Clap)
                if (self.min_double_gap_s - EPS) <= gap1 <= (self.max_double_gap_s + EPS):
                    self._clap_buffer.append(clap)

                    # Check if multi-clap patterns are active
                    has_triple = bool(
                        self._patterns.get(GestureType.TRIPLE_CLAP)
                        and self._patterns[GestureType.TRIPLE_CLAP].enabled
                    )
                    has_pause_3 = bool(
                        self._patterns.get(GestureType.CLAP_PAUSE_CLAP)
                        and self._patterns[GestureType.CLAP_PAUSE_CLAP].enabled
                    )

                    if not has_triple and not has_pause_3:
                        # Eager mode: only DOUBLE_CLAP is enabled
                        return self._emit_trigger(GestureType.DOUBLE_CLAP, self._clap_buffer, [gap1], now)
                    else:
                        # Ambiguity window: wait for potential 3rd clap
                        self._state = DetectorState.PENDING_DISAMBIGUATION
                        self._pending_deadline = now + self.disambiguation_timeout_s
                        logger.debug("State -> PENDING_DISAMBIGUATION: Clap 2 at %.3fs", now)
                        return None

                # C. Dead-Zone / Out-of-Window Reset:
                # Gap matched neither double clap nor syncopated pause.
                # Cleanly reset buffer with this clap as new Clap 1.
                logger.debug(
                    "Gap1 %.3fs matched neither double gap (<=%.3fs) nor pause (>=%.3fs). Resetting buffer with new clap at %.3fs",
                    gap1, self.max_double_gap_s, self.pause_min_s, now
                )
                self._clap_buffer = [clap]
                self._state = DetectorState.WAIT_CLAP_2
                self._pending_deadline = 0.0
                return None

            if len(self._clap_buffer) == 2:
                t1 = self._clap_buffer[0].timestamp
                t2 = self._clap_buffer[1].timestamp
                gap1 = t2 - t1
                gap2 = now - t2

                # A. Triple Clap Match
                p_triple = self._patterns.get(GestureType.TRIPLE_CLAP)
                if p_triple and p_triple.enabled:
                    if ((self.min_double_gap_s - EPS) <= gap2 <= (p_triple.max_gap_s + EPS)) and ((now - t1) <= 0.85 + EPS):
                        self._clap_buffer.append(clap)
                        return self._emit_trigger(GestureType.TRIPLE_CLAP, self._clap_buffer, [gap1, gap2], now)

                # B. 3-Clap Syncopated Pause Match
                p_pause = self._patterns.get(GestureType.CLAP_PAUSE_CLAP)
                if p_pause and p_pause.enabled:
                    if (p_pause.pause_min_s - EPS) <= gap2 <= (p_pause.pause_max_s + EPS):
                        self._clap_buffer.append(clap)
                        return self._emit_trigger(GestureType.CLAP_PAUSE_CLAP, self._clap_buffer, [gap1, gap2], now)

                # C. Mismatched 3rd clap: reset buffer and treat this clap as Clap 1
                logger.debug("3rd clap at %.3fs with gap2=%.3fs matched no 3-clap pattern. Resetting.", now, gap2)
                self._clap_buffer = [clap]
                self._state = DetectorState.WAIT_CLAP_2
                self._pending_deadline = 0.0
                return None

            return None

    def _is_pause_pattern_candidate(self, gap: float) -> bool:
        p = self._patterns.get(GestureType.CLAP_PAUSE_CLAP)
        return bool(p and p.enabled and (p.pause_min_s - EPS) <= gap <= (p.pause_max_s + EPS))

    def tick(self, now: Optional[float] = None) -> Optional[GestureResult]:
        """
        Periodic clock tick checking for disambiguation timeouts.
        """
        with self._lock:
            cur_time = now if now is not None else time.monotonic()

            if self._state == DetectorState.PENDING_DISAMBIGUATION and len(self._clap_buffer) == 2:
                if cur_time >= self._pending_deadline - EPS:
                    # Timeout reached without 3rd clap -> Disambiguate to DOUBLE_CLAP
                    t1, t2 = self._clap_buffer[0].timestamp, self._clap_buffer[1].timestamp
                    gap1 = t2 - t1
                    p_double = self._patterns.get(GestureType.DOUBLE_CLAP)
                    if p_double and p_double.enabled:
                        logger.debug("Disambiguation deadline reached. Triggering DOUBLE_CLAP.")
                        return self._emit_trigger(GestureType.DOUBLE_CLAP, self._clap_buffer, [gap1], cur_time)
                    else:
                        self.reset()

            # Evict stale claps from buffer
            if self._clap_buffer and (cur_time - self._clap_buffer[0].timestamp > self.pause_max_s + 0.5 + EPS):
                self.reset()

            return None

    def _emit_trigger(
        self,
        gesture_type: GestureType,
        claps: List[ClapEvent],
        intervals: List[float],
        timestamp: float,
    ) -> GestureResult:
        """Construct GestureResult, enter cooldown, notify dispatcher and subscribers."""
        pattern_cfg = self._patterns.get(gesture_type)
        actions = list(pattern_cfg.actions) if pattern_cfg else []

        result = GestureResult(
            gesture_type=gesture_type,
            timestamp=timestamp,
            confidence=1.0,
            claps=list(claps),
            intervals=list(intervals),
            actions_triggered=actions,
            metadata={"pattern_name": pattern_cfg.name if pattern_cfg else gesture_type.value},
        )

        # Set cooldown and reset state
        self._last_trigger_time = timestamp
        self._state = DetectorState.COOLDOWN
        self._clap_buffer.clear()
        self._pending_deadline = 0.0

        # Structured log
        try:
            log_trigger(
                trigger_type="gesture",
                pattern=gesture_type.value,
                details=f"intervals={[round(g, 3) for g in intervals]}, claps={len(claps)}",
            )
        except Exception:
            pass

        # Release lock before firing external dispatches & callbacks to eliminate deadlocks
        self._dispatch_result(result)
        return result

    def _dispatch_result(self, result: GestureResult) -> None:
        """Publish events and dispatch actions across threads."""
        g_name = result.gesture_type.value

        # 1. Direct on_gesture callback hook
        if self.on_gesture:
            try:
                self.on_gesture(g_name, result.confidence)
            except Exception as exc:
                logger.error("Error in on_gesture callback: %s", exc)

        # 2. EventBus Notification
        if self.event_bus:
            try:
                self.event_bus.publish("gesture.detected", gesture_type=g_name, result=result)
                self.event_bus.publish(f"gesture.{g_name}", result=result)
            except Exception as exc:
                logger.error("Error publishing gesture event: %s", exc)

        # 3. ActionDispatcher Execution
        if self.dispatcher and result.actions_triggered:
            context = RequesterContext.system()
            for action_name in result.actions_triggered:
                try:
                    logger.info("Executing gesture action: '%s' (trigger=%s)", action_name, g_name)
                    if hasattr(self.dispatcher, "dispatch_action"):
                        self.dispatcher.dispatch_action(
                            action_name=action_name,
                            payload={"gesture": result.to_dict()},
                            requester=context,
                        )
                except Exception as exc:
                    logger.error("Failed executing action '%s' for gesture '%s': %s", action_name, g_name, exc)

        # 4. Direct Listener Callbacks
        for cb in list(self._callbacks):
            try:
                cb(result)
            except Exception as exc:
                logger.error("Error in gesture callback: %s", exc)

    def process_stream(self, buffer: np.ndarray, block_size: int = 1764) -> List[GestureResult]:
        """
        Process an entire continuous PCM buffer (used in unit testing and offline stream evaluation).
        """
        # Collect transient spike times
        hit_times = []
        cur_time = 0.0
        dt = block_size / 44100.0
        last_raw_time = -100.0

        for i in range(0, len(buffer), block_size):
            chunk = buffer[i : i + block_size]
            if len(chunk) < block_size:
                pad = np.zeros(block_size - len(chunk), dtype=buffer.dtype)
                chunk = np.concatenate([chunk, pad])
            res = self.dsp.process_block(chunk)
            if res.get("is_transient"):
                # Chatter/echo filter: compare against last_raw_time
                if (cur_time - last_raw_time) >= (self.min_double_gap_s - EPS):
                    hit_times.append(cur_time)
                last_raw_time = cur_time
            cur_time += dt

        # Classify collected transient hit times
        events: List[GestureResult] = []
        i = 0
        while i < len(hit_times):
            # Check Triple Clap (3 hits)
            if i + 2 < len(hit_times):
                t1, t2, t3 = hit_times[i], hit_times[i+1], hit_times[i+2]
                g1, g2 = t2 - t1, t3 - t2
                if (self.min_double_gap_s - EPS <= g1 <= self.triple_clap_gap_s + EPS) and \
                   (self.min_double_gap_s - EPS <= g2 <= self.triple_clap_gap_s + EPS) and \
                   (t3 - t1 <= 0.85 + EPS):
                    events.append(
                        GestureResult(
                            gesture_type=GestureType.TRIPLE_CLAP,
                            timestamp=t3,
                            intervals=[g1, g2],
                            actions_triggered=list(self._patterns[GestureType.TRIPLE_CLAP].actions),
                        )
                    )
                    i += 3
                    continue

            # Check Clap-Pause-Clap (2 hits with pause)
            if i + 1 < len(hit_times):
                t1, t2 = hit_times[i], hit_times[i+1]
                gap = t2 - t1
                if (self.pause_min_s - EPS <= gap <= self.pause_max_s + EPS):
                    events.append(
                        GestureResult(
                            gesture_type=GestureType.CLAP_PAUSE_CLAP,
                            timestamp=t2,
                            intervals=[gap],
                            actions_triggered=list(self._patterns[GestureType.CLAP_PAUSE_CLAP].actions),
                        )
                    )
                    i += 2
                    continue

            # Check Double Clap (2 hits with standard gap)
            if i + 1 < len(hit_times):
                t1, t2 = hit_times[i], hit_times[i+1]
                gap = t2 - t1
                if (self.min_double_gap_s - EPS <= gap <= self.max_double_gap_s + EPS):
                    events.append(
                        GestureResult(
                            gesture_type=GestureType.DOUBLE_CLAP,
                            timestamp=t2,
                            intervals=[gap],
                            actions_triggered=list(self._patterns[GestureType.DOUBLE_CLAP].actions),
                        )
                    )
                    i += 2
                    continue

            # Single isolated clap or debounced
            i += 1

        # Apply cooldown filter between recognized events
        filtered: List[GestureResult] = []
        for ev in events:
            if not filtered or (ev.timestamp - filtered[-1].timestamp) >= (self.cooldown_s - EPS):
                filtered.append(ev)

        return filtered
