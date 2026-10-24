"""
tests/unit/test_speculative_cloud.py
====================================
Unit test suite for Speculative Cloud Pre-Warming & Draft Verification (SCPDV).
Validates 60-75% latency reduction, mid-sentence cancellation handling,
and Draft AST verification in Argon Frontier 10.0 (JARVIS v6.0.0).
"""
import time
import pytest

from jarvis.llm.speculative_cloud import (
    DraftASTSkeleton,
    SCPDVConfig,
    SCPDVExecutionResult,
    SpeculativeCloudHandoff,
)


class TestSpeculativeCloudHandoff:
    """Comprehensive test harness for SpeculativeCloudHandoff."""

    def test_scpdv_mid_speech_partial_prewarming(self) -> None:
        """Verifies partial speech triggers pre-warming for complex comparative queries."""
        coordinator = SpeculativeCloudHandoff()

        partial = "so sánh kiến trúc microservices với monolith đang mở"
        draft = coordinator.analyze_partial_speech(partial, context_window={"app": "chrome"})

        assert draft is not None
        assert isinstance(draft, DraftASTSkeleton)
        assert draft.intent == "comparative_analysis"
        assert draft.domain == "knowledge"
        assert draft.is_prewarmed is True
        assert "web_search" in draft.suggested_tools

    def test_scpdv_draft_verification_latency_reduction(self) -> None:
        """Verifies draft verification achieves 60-75% latency reduction over cold generation."""
        coordinator = SpeculativeCloudHandoff()

        partial = "soạn email gửi anh Hưng tổng hợp các báo cáo"
        draft = coordinator.analyze_partial_speech(partial)
        assert draft is not None

        # When user finishes speech:
        final_prompt = "soạn email gửi anh Hưng tổng hợp các báo cáo quý 3 và đính kèm số liệu"
        res = coordinator.dispatch_final_verification(
            final_prompt=final_prompt,
            draft=draft,
            base_cloud_latency_ms=3000.0,
        )

        assert isinstance(res, SCPDVExecutionResult)
        assert res.was_prewarmed is True
        assert res.was_cancelled is False
        # Baseline: 3000ms -> Accelerated: ~1050ms (65% reduction)
        assert res.actual_latency_ms <= 1200.0
        assert res.latency_reduction_pct >= 60.0
        assert res.payload["verification_mode"] == "DRAFT_VERIFY_PATCH"

    def test_scpdv_instant_cancellation_on_hesitation(self) -> None:
        """Verifies mid-sentence cancellation aborts active drafts to prevent cloud token cost."""
        coordinator = SpeculativeCloudHandoff()

        partial_1 = "hãy phân tích thuật toán đồ thị này"
        draft = coordinator.analyze_partial_speech(partial_1)
        assert draft is not None
        assert draft.is_prewarmed is True

        # User hesitates and cancels:
        partial_2 = "hãy phân tích thuật toán đồ thị này à thôi không cần"
        cancelled_draft = coordinator.analyze_partial_speech(partial_2)
        assert cancelled_draft is None
        assert draft.is_cancelled is True

    def test_scpdv_cold_fallback_without_draft(self) -> None:
        """Verifies clean fallback to unaccelerated baseline when no draft was pre-warmed."""
        coordinator = SpeculativeCloudHandoff()

        res = coordinator.dispatch_final_verification(
            final_prompt="một câu hỏi rất ngắn",
            draft=None,
            base_cloud_latency_ms=1500.0,
        )

        assert res.was_prewarmed is False
        assert res.actual_latency_ms == 1500.0
        assert res.latency_reduction_pct == 0.0
        assert res.payload["verification_mode"] == "COLD_FULL_GENERATION"

    def test_scpdv_draft_ttl_expiration(self) -> None:
        """Verifies stale speculative drafts auto-expire beyond TTL."""
        config = SCPDVConfig(draft_ttl_s=0.05)
        coordinator = SpeculativeCloudHandoff(config=config)

        draft1 = coordinator.analyze_partial_speech("phân tích kiến trúc hệ thống phân tán")
        assert draft1 is not None

        time.sleep(0.08)

        # Trigger second analysis -> draft1 should be purged
        draft2 = coordinator.analyze_partial_speech("viết code thuật toán lru cache đa luồng")
        assert draft2 is not None
        assert draft1.draft_id not in coordinator._active_drafts
