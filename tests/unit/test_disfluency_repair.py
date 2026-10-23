"""
tests/unit/test_disfluency_repair.py
====================================
Comprehensive Unit & Latency Verification for Spoken Disfluency Repair Engine.
Validates:
  - Numeric parameter corrections ('50 à nhầm 80 phần trăm').
  - Target application & entity repairs ('mở chrome à thôi mở edge', 'mở chrome à thôi edge').
  - Media & song title replacements ('bật bài hát nắng à không bài chúng ta của hiện tại').
  - Query entity corrections ('mở video độ mixi à nhầm độ tộc 2').
  - Mid-speech cancellation and abort signals ('mở visual studio code à thôi đừng mở').
  - Stuttering / false-start command verb deduplication ('mở mở chrome' -> 'mở chrome').
  - Preservation of valid queries containing negative words ('tìm kiếm bài hát không phải em').
  - Sub-0.5ms CPU latency budget (Argon Sovereign Telemetry).
  - Integration with LLMIntentRouter.parse_intent.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock
import pytest

from jarvis.nlp.disfluency_repair import (
    DisfluencyRepairResult,
    DisfluencySpan,
    SpokenDisfluencyRepairEngine,
    repair_spoken_disfluency,
)


@pytest.fixture
def repair_engine() -> SpokenDisfluencyRepairEngine:
    return SpokenDisfluencyRepairEngine()


class TestSpokenDisfluencyRepairEngine:
    """Direct unit tests for SpokenDisfluencyRepairEngine."""

    def test_numeric_parameter_repair(self, repair_engine: SpokenDisfluencyRepairEngine) -> None:
        """User corrects a numeric volume or brightness parameter mid-speech."""
        res = repair_engine.repair("tăng âm lượng lên 50 à nhầm 80 phần trăm")
        assert res.has_disfluency is True
        assert res.is_aborted is False
        assert res.repaired_text == "tăng âm lượng lên 80 phần trăm"
        assert len(res.spans) == 1
        assert res.spans[0].reparandum == "50"
        assert res.spans[0].repair == "80 phần trăm"

    def test_brightness_down_repair(self, repair_engine: SpokenDisfluencyRepairEngine) -> None:
        """User corrects brightness level with different interregnum."""
        res = repair_engine.repair("giảm độ sáng xuống 30 à lộn 20")
        assert res.has_disfluency is True
        assert res.repaired_text == "giảm độ sáng xuống 20"
        assert res.spans[0].reparandum == "30"
        assert res.spans[0].repair == "20"

    def test_timer_parameter_repair(self, repair_engine: SpokenDisfluencyRepairEngine) -> None:
        """User corrects timer duration with unit."""
        res = repair_engine.repair("đặt hẹn giờ 5 phút à không 10 phút")
        assert res.has_disfluency is True
        assert res.repaired_text == "đặt hẹn giờ 10 phút"

    def test_application_replacement_full_verb(self, repair_engine: SpokenDisfluencyRepairEngine) -> None:
        """User replaces application with full action verb repeated."""
        res = repair_engine.repair("mở chrome à thôi mở edge")
        assert res.has_disfluency is True
        assert res.repaired_text == "mở edge"

    def test_application_replacement_entity_only(self, repair_engine: SpokenDisfluencyRepairEngine) -> None:
        """User replaces application entity without repeating the action verb."""
        res = repair_engine.repair("mở chrome à thôi edge")
        assert res.has_disfluency is True
        assert res.repaired_text == "mở edge"

    def test_close_app_repair(self, repair_engine: SpokenDisfluencyRepairEngine) -> None:
        """User corrects target application to close."""
        res = repair_engine.repair("tắt word à nhầm excel")
        assert res.has_disfluency is True
        assert res.repaired_text == "tắt excel"

    def test_media_song_title_repair(self, repair_engine: SpokenDisfluencyRepairEngine) -> None:
        """User corrects song title containing category noun 'bài hát'."""
        res = repair_engine.repair("bật bài hát nắng à không bài chúng ta của hiện tại")
        assert res.has_disfluency is True
        assert res.repaired_text == "bật bài chúng ta của hiện tại"

    def test_video_query_repair(self, repair_engine: SpokenDisfluencyRepairEngine) -> None:
        """User corrects video search query on YouTube."""
        res = repair_engine.repair("mở video độ mixi à nhầm độ tộc 2")
        assert res.has_disfluency is True
        assert res.repaired_text == "mở video độ tộc 2"

    def test_compound_verb_replacement(self, repair_engine: SpokenDisfluencyRepairEngine) -> None:
        """User corrects action from restart to shutdown."""
        res = repair_engine.repair("khởi động lại máy à thôi tắt máy")
        assert res.has_disfluency is True
        assert res.repaired_text == "tắt máy"

    def test_action_replacement_different_verb(self, repair_engine: SpokenDisfluencyRepairEngine) -> None:
        """User changes action completely from screenshot to settings."""
        res = repair_engine.repair("chụp màn hình à nhầm mở cài đặt")
        assert res.has_disfluency is True
        assert res.repaired_text == "mở cài đặt"

    def test_multiple_chained_disfluencies(self, repair_engine: SpokenDisfluencyRepairEngine) -> None:
        """User corrects themselves multiple times in a single sentence."""
        res = repair_engine.repair("mở chrome à thôi edge à nhầm firefox")
        assert res.has_disfluency is True
        assert res.repaired_text == "mở firefox"
        assert len(res.spans) == 2

    def test_stuttering_command_verb(self, repair_engine: SpokenDisfluencyRepairEngine) -> None:
        """User stutters on initial command verb."""
        res = repair_engine.repair("mở mở chrome")
        assert res.has_disfluency is True
        assert res.repaired_text == "mở chrome"

    def test_full_command_abort_dont_open(self, repair_engine: SpokenDisfluencyRepairEngine) -> None:
        """User explicitly aborts command with 'à thôi đừng mở'."""
        res = repair_engine.repair("mở visual studio code à thôi đừng mở")
        assert res.has_disfluency is True
        assert res.is_aborted is True
        assert res.repaired_text == ""

    def test_full_command_abort_drop_it(self, repair_engine: SpokenDisfluencyRepairEngine) -> None:
        """User aborts system shutdown with 'à thôi bỏ đi'."""
        res = repair_engine.repair("tắt máy tính đi à thôi bỏ đi")
        assert res.has_disfluency is True
        assert res.is_aborted is True
        assert res.repaired_text == ""

    def test_empty_and_whitespace_input(self, repair_engine: SpokenDisfluencyRepairEngine) -> None:
        """Guards against null or empty strings."""
        res1 = repair_engine.repair("")
        assert res1.has_disfluency is False
        assert res1.repaired_text == ""

        res2 = repair_engine.repair(None)
        assert res2.has_disfluency is False
        assert res2.repaired_text == ""

    def test_clean_speech_passthrough(self, repair_engine: SpokenDisfluencyRepairEngine) -> None:
        """Clean speech passes through completely unaltered."""
        clean_text = "tăng âm lượng lên 80 phần trăm"
        res = repair_engine.repair(clean_text)
        assert res.has_disfluency is False
        assert res.is_aborted is False
        assert res.repaired_text == clean_text

    def test_negative_words_in_song_title_not_repaired(
        self, repair_engine: SpokenDisfluencyRepairEngine
    ) -> None:
        """Song titles containing negative phrase 'không phải' are protected when reparandum is empty."""
        title = "tìm kiếm bài hát không phải em"
        res = repair_engine.repair(title)
        assert res.has_disfluency is False
        assert res.repaired_text == title

    def test_cpu_latency_budget_under_half_millisecond(
        self, repair_engine: SpokenDisfluencyRepairEngine
    ) -> None:
        """Ensures p50 execution latency is strictly <= 0.5ms on CPU (Argon budget)."""
        latencies: list[float] = []
        sample_query = "tăng âm lượng lên 50 à nhầm 80 phần trăm"

        for _ in range(500):
            t0 = time.perf_counter()
            repair_engine.repair(sample_query)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000)

        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)]

        # Must execute comfortably under 0.50ms on CPU
        assert p50 < 0.50, f"p50 latency {p50:.4f}ms exceeds 0.50ms budget"
        assert p95 < 1.50, f"p95 latency {p95:.4f}ms exceeds 1.50ms budget"


class TestRouterDisfluencyIntegration:
    """Tests end-to-end integration of disfluency repair inside LLMIntentRouter.parse_intent."""

    def test_router_numeric_disfluency_repair(self) -> None:
        """Router correctly parses volume level 80 despite user initially saying 50."""
        from jarvis.llm.router import LLMIntentRouter

        router = LLMIntentRouter(llm_client=MagicMock(), fast_path_enabled=True)
        result = router.parse_intent("tăng âm lượng lên 50 à nhầm 80 phần trăm")
        assert result.action_name == "system_volume"
        assert result.parameters.get("delta") == 80 or result.parameters.get("level") == 80

    def test_router_app_replacement_repair(self) -> None:
        """Router opens edge when user says 'mở chrome à thôi mở edge'."""
        from jarvis.llm.router import LLMIntentRouter

        router = LLMIntentRouter(llm_client=MagicMock(), fast_path_enabled=True)
        result = router.parse_intent("mở chrome à thôi mở edge")
        assert result.action_name == "app_open"
        assert "edge" in result.parameters.get("app_name", "").lower()

    def test_router_abort_mid_speech_cancels_action(self) -> None:
        """Router intercepts mid-speech abort and refuses to execute destructive command."""
        from jarvis.llm.router import LLMIntentRouter

        router = LLMIntentRouter(llm_client=MagicMock(), fast_path_enabled=True)
        result = router.parse_intent("tắt máy tính đi à thôi đừng tắt")
        # Must fail-closed or report abort, never return system_power
        assert result.action_name != "system_power"
        assert "hủy" in result.response_text.lower() or result.action_name == "unknown_intent"
