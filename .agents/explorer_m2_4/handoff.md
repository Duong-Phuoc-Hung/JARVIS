# Milestone 2 Audio & Gesture Hardening Remediation Blueprint

**Agent**: Explorer 4 (`explorer_m2_4`)  
**Milestone**: Milestone 2 Iteration 2 (Audio & Gesture Hardening)  
**Deliverable**: Comprehensive Remediation Architecture and Exact Code Blueprint for Challenger 1 Findings  
**Target Files**:
- `jarvis/gesture/detector.py`
- `jarvis/audio/engine.py`
- `tests/test_adversarial_m2_audio_gesture.py`

---

## 1. Observation

Empirical analysis and code audit of `jarvis/gesture/detector.py`, `jarvis/audio/engine.py`, and `tests/test_adversarial_m2_audio_gesture.py` confirmed four specific defect vectors identified by Challenger 1:

### 1.1 Echo Rejection & Chatter Suppression Vulnerability
- **Location**: `jarvis/gesture/detector.py:184-191`, `jarvis/gesture/detector.py:397-400`
- **Existing Code**:
  ```python
  # In feed_clap():
  if self._clap_buffer:
      prev_clap = self._clap_buffer[-1]
      gap = now - prev_clap.timestamp
      if gap < self.min_double_gap_s:
          logger.debug("Clap at %.3fs ignored as acoustic echo (gap=%.3fs)", now, gap)
          return None
  ```
- **Observed Failure Mechanism**:
  When a continuous pulse train or chatter arrives (e.g. 20ms intervals: $t = 1.00, 1.02, 1.04, 1.06, 1.08, 1.10, 1.12\dots$):
  1. At $t=1.00\text{s}$, transient 1 is accepted into `_clap_buffer` ($T_1 = 1.00\text{s}$).
  2. At $t=1.02\text{s}$, gap $1.02 - 1.00 = 0.02\text{s} < 0.05\text{s}$ is rejected. But no `_last_raw_clap_time` is updated.
  3. At $t=1.04\text{s}$, gap $1.04 - 1.00 = 0.04\text{s} < 0.05\text{s}$ is rejected.
  4. At $t=1.06\text{s}$, gap $1.06 - 1.00 = 0.06\text{s} \ge 0.05\text{s}$. Because comparison is made against `_clap_buffer[-1]` ($1.00\text{s}$) rather than the immediate predecessor transient ($1.04\text{s}$), the 4th pulse is incorrectly accepted as Clap 2!
  5. At $t=1.12\text{s}$, the 7th pulse is accepted as Clap 3, falsely firing a `TRIPLE_CLAP` gesture from rapid 20ms background chatter.

### 1.2 Dead-Zone Interval Stalling `(0.35s, 0.50s)`
- **Location**: `jarvis/gesture/detector.py:204-210`, `jarvis/gesture/detector.py:270-272`
- **Existing Code**:
  ```python
  if gap1 > self.max_double_gap_s and not self._is_pause_pattern_candidate(gap1):
      # Gap too long for double/triple: start new sequence
      self._clap_buffer = [clap]
      self._state = DetectorState.WAIT_CLAP_2
      return None

  def _is_pause_pattern_candidate(self, gap: float) -> bool:
      p = self._patterns.get(GestureType.CLAP_PAUSE_CLAP)
      return bool(p and p.enabled and gap <= p.pause_max_s)
  ```
- **Observed Failure Mechanism**:
  When a 2nd clap arrives with $g_1 = 0.42\text{s}$ (between `max_double_gap_s = 0.35s` and `pause_min_s = 0.50s`):
  1. `_is_pause_pattern_candidate(0.42)` returns `True` because $0.42 \le 1.20\text{s}$.
  2. `not self._is_pause_pattern_candidate(gap1)` evaluates to `False`, so the buffer reset branch is bypassed.
  3. The clap fails the syncopation check ($0.50 \le 0.42 \le 1.20$ is `False`) and fails the double clap check ($0.05 \le 0.42 \le 0.35$ is `False`).
  4. The 2nd clap at $0.42\text{s}$ is silently discarded/swallowed while `self._clap_buffer` remains stuck holding the stale first clap ($T_1$).
  5. If a 3rd clap arrives at $T_1 + 0.75\text{s}$, the detector computes $g = 0.75\text{s}$ against stale $T_1$ and falsely triggers a `CLAP_PAUSE_CLAP` instead of treating $(0.42\text{s}, 0.75\text{s})$ or $(0.75\text{s})$ as the active sequence.

### 1.3 Floating-Point Quantization Residuals at Nominal Boundaries
- **Location**: `jarvis/gesture/detector.py:180, 188, 213, 218, 250, 257, 282, 410, 428, 444, 462`
- **Observed Failure Mechanism**:
  In standard Python IEEE 754 float arithmetic:
  ```python
  1.350 - 1.000 == 0.3500000000000001  # > 0.350
  2.200 - 1.000 == 1.2000000000000002  # > 1.200
  1.050 - 1.000 == 0.04999999999999993 # < 0.050
  ```
  Strict inequality checks (`gap <= max_gap`, `gap >= min_gap`) cause valid transient pairs at exact boundaries ($0.050\text{s}, 0.350\text{s}, 0.500\text{s}, 1.200\text{s}$) to be rejected due to float quantization noise.

### 1.4 Missing `feed_virtual_audio` Method Alias
- **Location**: `jarvis/audio/engine.py:421-436`
- **Observed Failure Mechanism**:
  `AudioEngine` implemented `feed_audio(self, buffer, virtual_time=True)` but omitted `feed_virtual_audio`, which is referenced across certain virtualized test harnesses and mocks expecting `AudioEngine.feed_virtual_audio(...)`.

---

## 2. Logic Chain

1. **Acoustic Transient Ingestion Flow**:
   - Transients originate either from `feed_audio_block` via `AudioDSPProcessor` or from direct test feeds via `feed_clap`.
   - To guarantee immunity against high-frequency chatter ($< 50\text{ms}$ bursts, clicks, or acoustic echoes), every raw transient must update a monotonic tracker `self._last_raw_clap_time`.
   - If an incoming transient arrives with `now - self._last_raw_clap_time < min_double_gap_s - EPS`, it is classified as continuous chatter / acoustic echo, updates `self._last_raw_clap_time = now`, and is dropped immediately before affecting any state machine buffers.
   - Similarly, in `process_stream()`, maintaining `last_raw_time` prevents chunk-by-chunk pulse aliasing.

2. **State Machine Partitioning & Dead-Zone Elimination**:
   - For a sequence with 1 buffered clap ($T_1$) upon arrival of a 2nd transient at `now` ($g_1 = \text{now} - T_1$):
     * **Region 1: Double / Multi-Clap Range**: $g_1 \in [\text{min\_double\_gap\_s} - \text{EPS}, \text{max\_double\_gap\_s} + \text{EPS}]$. Append clap and enter disambiguation (or emit if eager).
     * **Region 2: Syncopated Pause Range**: $g_1 \in [\text{pause\_min\_s} - \text{EPS}, \text{pause\_max\_s} + \text{EPS}]$ with `CLAP_PAUSE_CLAP` enabled. Append clap and trigger `CLAP_PAUSE_CLAP`.
     * **Region 3: Invalid / Dead-Zone Gap**: $g_1 \in (\text{max\_double\_gap\_s} + \text{EPS}, \text{pause\_min\_s} - \text{EPS})$ OR $g_1 > \text{pause\_max\_s} + \text{EPS}$ OR pause pattern disabled. $T_1$ is invalidated; buffer is cleanly reset to `[clap]` with state `WAIT_CLAP_2`.
   - This ensures no transient is ever silently discarded while leaving stale claps in the buffer.

3. **Epsilon Boundary Protection**:
   - Introducing `EPS = 1e-4` ($0.1\text{ms}$) across all timing boundary comparisons absorbs IEEE 754 quantization noise while remaining two orders of magnitude smaller than the minimum physical debounce window ($50\text{ms}$).

4. **Engine Interface Alignment**:
   - Providing `feed_virtual_audio` as an explicit method and alias on `AudioEngine` ensures polymorphic interface compliance.

---

## 3. Caveats

1. **Chatter Burst Extinction**:
   - When continuous rapid chatter (e.g. 20ms clicks) ceases, the initial clap ($T_1$) remains in `_clap_buffer` until evicted by the stale eviction timeout in `tick()` ($T_{\text{evict}} = \text{pause\_max\_s} + 0.5\text{s}$). If a single clean clap arrives after the chatter stops but before eviction, it will be evaluated against $T_1$. However, since the elapsed time from $T_1$ will exceed $\text{max\_double\_gap\_s}$, it will reset the buffer cleanly as a new Clap 1.
2. **Sub-millisecond Precision**:
   - An `EPS` value of `1e-4` ($0.1\text{ms}$) is strictly optimal for 44.1kHz audio (where 1 sample is $\approx 0.0226\text{ms}$ and 1 block of 1764 samples is $40.0\text{ms}$). It does not allow false aliasing across nominal gesture windows.

---

## 4. Conclusion & Remediation Blueprint

### 4.1 Target File 1: `jarvis/gesture/detector.py`

#### Change 1: Add Epsilon Constant & State Initialization
```python
# ============================================================================
# jarvis/gesture/detector.py (Top Level & __init__)
# ============================================================================

# Module-level epsilon tolerance for IEEE 754 float comparisons
EPS = 1e-4

class GestureDetector:
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

    def reset(self) -> None:
        """Reset internal buffers and state to IDLE."""
        with self._lock:
            self._state = DetectorState.IDLE
            self._clap_buffer.clear()
            self._pending_deadline = 0.0
            self._last_raw_clap_time = -100.0
            if hasattr(self.dsp, "reset"):
                self.dsp.reset()
```

#### Change 2: Hardened `feed_clap()` State Machine
```python
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
```

#### Change 3: Epsilon Tolerance in `tick()` and `process_stream()`
```python
    def tick(self, now: Optional[float] = None) -> Optional[GestureResult]:
        """Periodic clock tick checking for disambiguation timeouts."""
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

    def process_stream(self, buffer: np.ndarray, block_size: int = 1764) -> List[GestureResult]:
        """
        Process an entire continuous PCM buffer (offline evaluation and testing).
        """
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
```

---

### 4.2 Target File 2: `jarvis/audio/engine.py`

#### Method and Alias Additions in `AudioEngine`
```python
    def feed_virtual_audio(self, buffer: np.ndarray, virtual_time: bool = True) -> None:
        """
        Alias for feed_audio.
        Pushes synthetic audio buffer directly into stream processing for test harnesses.
        """
        self.feed_audio(buffer, virtual_time=virtual_time)
```

---

### 4.3 Target File 3: `tests/test_adversarial_m2_audio_gesture.py`

#### Hardened & New Verification Test Cases
```python
def test_rapid_multi_clap_chatter_suppression_hardened():
    """
    Hardened verification: Rapid 20ms chatter transients (<50ms apart)
    must NOT alias into false gestures because every raw pulse updates _last_raw_clap_time.
    """
    det = GestureDetector(min_double_gap_s=0.05)
    t = 1.0
    triggers = []
    for i in range(20):
        res = det.feed_clap(ClapEvent(timestamp=t, amplitude=0.8))
        if res is not None:
            triggers.append(res)
        t += 0.02  # 20ms continuous chatter

    # After chatter stops, tick past timeout
    res_tick = det.tick(now=t + 1.0)
    if res_tick is not None:
        triggers.append(res_tick)

    assert len(triggers) == 0, f"Expected 0 triggers from chatter spam, got {len(triggers)}: {triggers}"


def test_dead_zone_interval_resets_buffer_cleanly():
    """
    Verify dead-zone gap (e.g. 0.420s between max_double 0.35s and pause_min 0.50s)
    cleanly resets the gesture buffer and treats Clap 2 as Clap 1 of a new sequence.
    """
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35, pause_min_s=0.50, pause_max_s=1.20)
    
    # Clap 1 at 1.000s
    c1 = ClapEvent(timestamp=1.000, amplitude=0.8)
    assert det.feed_clap(c1) is None
    assert len(det._clap_buffer) == 1

    # Clap 2 at 1.420s (gap = 0.420s: dead-zone)
    c2 = ClapEvent(timestamp=1.420, amplitude=0.8)
    assert det.feed_clap(c2) is None
    # Buffer MUST now hold only Clap 2 (not Clap 1, and not empty)
    assert len(det._clap_buffer) == 1
    assert det._clap_buffer[0].timestamp == 1.420

    # Clap 3 at 1.570s (gap = 0.150s from Clap 2)
    c3 = ClapEvent(timestamp=1.570, amplitude=0.8)
    assert det.feed_clap(c3) is None
    assert len(det._clap_buffer) == 2

    # Disambiguation timeout at 1.950s
    res = det.tick(now=1.950)
    assert res is not None
    assert res.gesture_type == GestureType.DOUBLE_CLAP
    assert res.claps[0].timestamp == 1.420
    assert res.claps[1].timestamp == 1.570


def test_float_epsilon_tolerance_exact_boundaries():
    """
    Verify exact timing boundaries withstand IEEE 754 float subtraction residuals.
    """
    det = GestureDetector(min_double_gap_s=0.05, max_double_gap_s=0.35, pause_min_s=0.50, pause_max_s=1.20)

    # 1. Exact Double Clap max boundary: 1.000 + 0.350 = 1.350
    t1 = 1.000
    t2 = t1 + 0.350
    det.reset()
    det.feed_clap(ClapEvent(timestamp=t1, amplitude=0.8))
    det.feed_clap(ClapEvent(timestamp=t2, amplitude=0.8))
    res = det.tick(now=t2 + 0.40)
    assert res is not None
    assert res.gesture_type == GestureType.DOUBLE_CLAP

    # 2. Exact Syncopated Pause max boundary: 1.000 + 1.200 = 2.200
    t3 = 1.000
    t4 = t3 + 1.200
    det.reset()
    det.feed_clap(ClapEvent(timestamp=t3, amplitude=0.8))
    res_pause_max = det.feed_clap(ClapEvent(timestamp=t4, amplitude=0.8))
    assert res_pause_max is not None
    assert res_pause_max.gesture_type == GestureType.CLAP_PAUSE_CLAP

    # 3. Exact Syncopated Pause min boundary: 1.000 + 0.500 = 1.500
    t5 = 1.000
    t6 = t5 + 0.500
    det.reset()
    det.feed_clap(ClapEvent(timestamp=t5, amplitude=0.8))
    res_pause_min = det.feed_clap(ClapEvent(timestamp=t6, amplitude=0.8))
    assert res_pause_min is not None
    assert res_pause_min.gesture_type == GestureType.CLAP_PAUSE_CLAP

    # 4. Exact Double Clap min boundary: 1.000 + 0.050 = 1.050
    t7 = 1.000
    t8 = t7 + 0.050
    det.reset()
    det.feed_clap(ClapEvent(timestamp=t7, amplitude=0.8))
    det.feed_clap(ClapEvent(timestamp=t8, amplitude=0.8))
    res_double_min = det.tick(now=t8 + 0.40)
    assert res_double_min is not None
    assert res_double_min.gesture_type == GestureType.DOUBLE_CLAP


def test_audio_engine_feed_virtual_audio_alias():
    """
    Verify AudioEngine.feed_virtual_audio exists and dispatches audio blocks.
    """
    bus_blocks = []
    engine = AudioEngine(
        sample_rate=44100,
        block_ms=40,
        mode=AudioEngineMode.MOCK,
        on_audio_block=lambda blk: bus_blocks.append(blk),
    )
    engine.start_stream()

    test_audio = np.full(3528, 0.42, dtype=np.float32)
    assert hasattr(engine, "feed_virtual_audio")
    engine.feed_virtual_audio(test_audio)

    engine.stop_stream()
    assert len(bus_blocks) == 2
    assert np.allclose(bus_blocks[0], 0.42)
```

---

## 5. Verification Method

### Test Execution Command
To verify the entire suite with all hardened adversarial stress tests:

```powershell
& "d:\Software GitCode\JARVIS\.venv\Scripts\python.exe" -m pytest tests/test_adversarial_m2_audio_gesture.py tests/test_empirical_challenger_m2.py tests/unit/ -v
```

### Invalidation Conditions
- Any trigger emitted when 20ms chatter transients are fed into `GestureDetector`.
- Any failure to trigger `DOUBLE_CLAP` or `CLAP_PAUSE_CLAP` at exact float boundaries ($0.050\text{s}, 0.350\text{s}, 0.500\text{s}, 1.200\text{s}$).
- Any failure when calling `AudioEngine.feed_virtual_audio(...)`.
- Any stale clap retaining in `_clap_buffer` after a dead-zone ($0.42\text{s}$) arrival.
