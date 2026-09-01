"""
tests/unit/test_stt_intent_eval_threshold_curve.py
====================================================
CPU-only, deterministic unit tests for
tests/eval/stt_intent_eval.py::compute_threshold_curve().

Locks in the renamed "end_to_end_abstention" curve key (replacing the
ambiguous historical "silent" key) so a future edit cannot silently
reintroduce ambiguous terminology into NEW evaluator outputs. Historical
committed evidence (docs/eval/stt_eval_summaries.json) intentionally still
uses "silent" and is untouched — this test only covers the new code path.

No CUDA, no faster-whisper model, no microphone, no network required.
"""
from __future__ import annotations

from tests.eval.stt_intent_eval import compute_threshold_curve


def _row(confidence, outcome):
    return {"confidence": confidence, "outcome": outcome}


class TestComputeThresholdCurveKeyNaming:
    def test_curve_entries_use_end_to_end_abstention_key(self):
        rows = [_row(0.9, "CORRECT"), _row(0.2, "ROUTER_ABSTAIN")]
        curve = compute_threshold_curve(rows, thresholds=[0.5])
        entry = curve["0.5"]
        assert "end_to_end_abstention" in entry
        assert "silent" not in entry

    def test_curve_has_exactly_three_keys(self):
        rows = [_row(0.9, "CORRECT")]
        curve = compute_threshold_curve(rows, thresholds=[0.5])
        assert set(curve["0.5"].keys()) == {"correct", "misrouting", "end_to_end_abstention"}


class TestComputeThresholdCurveBehavior:
    def test_below_threshold_counts_as_abstention(self):
        rows = [_row(0.1, "CORRECT")]  # below threshold despite CORRECT outcome
        curve = compute_threshold_curve(rows, thresholds=[0.5])
        assert curve["0.5"]["end_to_end_abstention"] == 1.0
        assert curve["0.5"]["correct"] == 0.0

    def test_above_threshold_correct_outcome_counts_as_correct(self):
        rows = [_row(0.9, "CORRECT")]
        curve = compute_threshold_curve(rows, thresholds=[0.5])
        assert curve["0.5"]["correct"] == 1.0
        assert curve["0.5"]["end_to_end_abstention"] == 0.0

    def test_above_threshold_misrouted_outcome_counts_as_misrouting(self):
        rows = [_row(0.9, "MISROUTED")]
        curve = compute_threshold_curve(rows, thresholds=[0.5])
        assert curve["0.5"]["misrouting"] == 1.0

    def test_above_threshold_stt_empty_or_router_abstain_counts_as_abstention(self):
        rows = [_row(0.9, "STT_EMPTY"), _row(0.9, "ROUTER_ABSTAIN")]
        curve = compute_threshold_curve(rows, thresholds=[0.5])
        assert curve["0.5"]["end_to_end_abstention"] == 1.0

    def test_rows_without_confidence_are_excluded_not_counted_as_zero(self):
        # Production-backend rows have confidence=None and must not skew the curve.
        rows = [_row(None, "CORRECT"), _row(0.9, "CORRECT")]
        curve = compute_threshold_curve(rows, thresholds=[0.5])
        assert curve["0.5"]["correct"] == 1.0  # denominator is 1 (scored rows only), not 2

    def test_empty_when_no_rows_have_confidence(self):
        rows = [_row(None, "CORRECT")]
        curve = compute_threshold_curve(rows)
        assert curve == {}

    def test_empty_results_returns_empty_curve(self):
        assert compute_threshold_curve([]) == {}

    def test_multiple_thresholds_each_produce_an_entry(self):
        rows = [_row(0.6, "CORRECT")]
        curve = compute_threshold_curve(rows, thresholds=[0.3, 0.5, 0.7])
        assert set(curve.keys()) == {"0.3", "0.5", "0.7"}
        assert curve["0.3"]["correct"] == 1.0  # 0.6 >= 0.3
        assert curve["0.7"]["end_to_end_abstention"] == 1.0  # 0.6 < 0.7
