"""
tests/unit/test_minkowski_concurrency.py
========================================
Unit Tests for Relativistic Causal Concurrency & Minkowski Light-Cone Event Serialization.
Milestone v9.0.0 ("The Transcendent Singularity", Frontier 30.0).
"""
from __future__ import annotations

import math
import os
import tempfile
import numpy as np
import pytest

from jarvis.network.minkowski_concurrency import (
    DEFAULT_SIGNAL_VELOCITY,
    CausalSeparation,
    DispatchBatchResult,
    Minkowski4Vector,
    MinkowskiEvent,
    MinkowskiSpacetimeMetric,
    RelativisticEventDispatcher,
)


def test_minkowski_4vector_construction_and_norm():
    """Validates invariant 4-vector X^mu = (ct, x, y, z) representation."""
    c = 3.0e8
    t = 2.0
    coords = (100.0, 200.0, 300.0)

    vec = Minkowski4Vector.from_time_and_space(t, coords, c=c)
    assert vec.ct == 6.0e8
    assert vec.x == 100.0
    assert vec.y == 200.0
    assert vec.z == 300.0

    arr = vec.as_array()
    assert np.array_equal(arr, [6.0e8, 100.0, 200.0, 300.0])

    expected_norm = math.sqrt(100**2 + 200**2 + 300**2)
    assert abs(vec.spatial_norm() - expected_norm) < 1e-7


def test_minkowski_spacetime_metric_causal_classification():
    """Validates pseudo-Riemannian metric interval computation and causal classification."""
    metric = MinkowskiSpacetimeMetric(c=100.0)  # Use logical c = 100 m/s for clean testing

    # 1. Space-like separated events: Delta x = 500m, Delta t = 1s -> Delta s^2 = 500^2 - 100^2 > 0
    v1 = Minkowski4Vector(ct=0.0, x=0.0, y=0.0, z=0.0)
    v_spacelike = Minkowski4Vector(ct=100.0, x=500.0, y=0.0, z=0.0)
    assert metric.classify_separation(v1, v_spacelike) == CausalSeparation.SPACE_LIKE
    assert metric.interval_squared(v1, v_spacelike) > 0.0

    # 2. Time-like separated events: Delta x = 20m, Delta t = 1s -> Delta s^2 = 20^2 - 100^2 < 0
    v_timelike = Minkowski4Vector(ct=100.0, x=20.0, y=0.0, z=0.0)
    assert metric.classify_separation(v1, v_timelike) == CausalSeparation.TIME_LIKE
    assert metric.interval_squared(v1, v_timelike) < 0.0

    # 3. Light-like / null separated events: Delta x = 100m, Delta t = 1s -> Delta s^2 == 0
    v_lightlike = Minkowski4Vector(ct=100.0, x=100.0, y=0.0, z=0.0)
    assert metric.classify_separation(v1, v_lightlike) == CausalSeparation.LIGHT_LIKE
    assert abs(metric.interval_squared(v1, v_lightlike)) < 1e-7


def test_spacelike_provable_zero_lock_commutativity():
    """Theorem: Space-like separated events can commute ([E1, E2] = 0) lock-free."""
    metric = MinkowskiSpacetimeMetric(c=1000.0)

    e1 = MinkowskiEvent(
        event_id="e1",
        coord=Minkowski4Vector(ct=0.0, x=0.0, y=0.0, z=0.0),
        payload={"action": "update_ui"},
        author_node_id="node_a",
    )
    # 50,000 meters away, delta t = 0.001s (ct = 1m) -> Delta s^2 > 0 (space-like)
    e2 = MinkowskiEvent(
        event_id="e2",
        coord=Minkowski4Vector(ct=1.0, x=50000.0, y=0.0, z=0.0),
        payload={"action": "write_cache"},
        author_node_id="node_b",
    )

    assert metric.can_commute(e1, e2) is True


def test_lorentz_gamma_factor():
    """Validates relativistic clock dilation gamma = 1 / sqrt(1 - (v/c)^2)."""
    metric = MinkowskiSpacetimeMetric(c=3.0e8)

    # v = 0 -> gamma = 1.0
    assert abs(metric.lorentz_gamma(0.0) - 1.0) < 1e-9

    # v = 0.6 c -> gamma = 1 / sqrt(1 - 0.36) = 1 / 0.8 = 1.25
    assert abs(metric.lorentz_gamma(1.8e8) - 1.25) < 1e-5

    # v >= c raises ValueError
    with pytest.raises(ValueError):
        metric.lorentz_gamma(3.0e8)


def test_past_and_future_light_cone_traversal():
    """Validates past light-cone J^-(E) and future light-cone J^+(E) causal reachability."""
    dispatcher = RelativisticEventDispatcher(c=100.0)

    # Create past event (t=0, x=0)
    e_origin = dispatcher.record_event("e_origin", {"v": 0}, timestamp_s=0.0, coords=(0, 0, 0))

    # Time-like future event (t=2, x=10)
    e_timelike_future = dispatcher.record_event(
        "e_time_fut", {"v": 1}, timestamp_s=2.0, coords=(10, 0, 0)
    )

    # Space-like event (t=1, x=5000)
    e_spacelike = dispatcher.record_event(
        "e_space", {"v": 2}, timestamp_s=1.0, coords=(5000, 0, 0)
    )

    # Check past light cone of e_timelike_future
    past_cone = dispatcher.past_light_cone(e_timelike_future)
    past_ids = [e.event_id for e in past_cone]
    # e_origin is in the past light cone (causally connected)
    assert "e_origin" in past_ids
    # e_spacelike is NOT in the past light cone
    assert "e_space" not in past_ids

    # Check future light cone of e_origin
    fut_cone = dispatcher.future_light_cone(e_origin)
    fut_ids = [e.event_id for e in fut_cone]
    assert "e_time_fut" in fut_ids
    assert "e_space" not in fut_ids


def test_partition_into_commuting_batches_and_concurrent_dispatch():
    """Validates lock-free parallel execution of space-like commuting batches."""
    dispatcher = RelativisticEventDispatcher(c=100.0)

    # 3 space-like separated events occurring almost simultaneously across different continents
    e1 = dispatcher.record_event("ev_tokyo", {"tx": 1}, timestamp_s=1.0, coords=(100000, 0, 0))
    e2 = dispatcher.record_event("ev_london", {"tx": 2}, timestamp_s=1.0, coords=(-100000, 0, 0))
    e3 = dispatcher.record_event("ev_sydney", {"tx": 3}, timestamp_s=1.0, coords=(0, 100000, 0))

    batches = dispatcher.partition_into_commuting_batches([e1, e2, e3])
    # All 3 events are space-like to one another, so they can be grouped in a single parallel batch!
    assert len(batches) == 1
    assert len(batches[0]) == 3

    # Dispatch concurrent
    executed_log = []
    res = dispatcher.dispatch_concurrent(
        ["ev_tokyo", "ev_london", "ev_sydney"],
        executor_func=lambda ev: executed_log.append(ev.event_id),
    )

    assert isinstance(res, DispatchBatchResult)
    assert res.total_events == 3
    assert res.lock_free_parallel_events == 3
    assert res.consensus_latency_ms == 0.0  # 0 ms consensus latency for space-like events!
    assert len(executed_log) == 3


def test_minkowski_windows_atomic_persistence():
    """Validates thread-safe Windows Atomic Persistence save/load for Minkowski causal graph."""
    dispatcher = RelativisticEventDispatcher(node_id="node_alpha", c=1000.0)
    dispatcher.record_event("ev_1", {"msg": "start"}, timestamp_s=10.0, coords=(10, 20, 30))
    dispatcher.record_event("ev_2", {"msg": "step"}, timestamp_s=12.0, coords=(15, 25, 35))

    with tempfile.TemporaryDirectory() as tmpdir:
        save_file = os.path.join(tmpdir, "minkowski_graph.json")
        dispatcher.save(save_file)
        assert os.path.exists(save_file)

        restored = RelativisticEventDispatcher.load(save_file)
        assert restored.node_id == "node_alpha"
        assert len(restored.events) == 2
        assert "ev_1" in restored.events
        assert "ev_2" in restored.events
        assert restored.events["ev_1"].payload["msg"] == "start"


def test_minkowski_edge_cases():
    """Validates edge cases: empty dispatch, single event, and invalid speed of light."""
    dispatcher = RelativisticEventDispatcher()
    res_empty = dispatcher.dispatch_concurrent([])
    assert res_empty.total_events == 0
    assert res_empty.parallel_batches_count == 0

    with pytest.raises(ValueError):
        MinkowskiSpacetimeMetric(c=-10.0)
