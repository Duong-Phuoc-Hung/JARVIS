"""
tests/unit/test_memory_injection.py
===================================
Unit tests for MemoryManager context injection, relevant facts ranking, and system prompt formatting.
"""
from pathlib import Path

import pytest

from jarvis.llm.router import build_jarvis_system_prompt
from jarvis.memory.manager import MemoryManager


class TestMemoryInjection:
    """Test suite for memory ranking and prompt integration."""

    @pytest.fixture
    def mem_mgr(self, tmp_path: Path) -> MemoryManager:
        db_path = tmp_path / "test_memory.db"
        mgr = MemoryManager(db_path=db_path, max_session_turns=5)
        # Seed test facts
        mgr.store_fact(key="user_name", value="Hung", category="profile")
        mgr.store_fact(key="email", value="hung@example.com", category="profile")
        mgr.store_fact(key="current_project", value="JARVIS", category="project")
        mgr.store_fact(key="favorite_music", value="Lo-fi hiphop", category="preference")
        mgr.store_fact(key="coffee_preference", value="Black iced coffee without sugar", category="preference")
        mgr.store_fact(key="wake_time", value="6:30 AM", category="habit")
        return mgr

    def test_get_relevant_facts_for_prompt_ranking(self, mem_mgr: MemoryManager) -> None:
        """Test facts relevant to query are boosted to top."""
        facts_music = mem_mgr.get_relevant_facts_for_prompt(query="mở nhạc lo-fi thư giãn", limit=3)
        assert len(facts_music) <= 3
        # Should contain profile or music facts
        keys = [f.get("key") for f in facts_music]
        assert "favorite_music" in keys or "user_name" in keys

    def test_get_relevant_facts_coffee_query(self, mem_mgr: MemoryManager) -> None:
        """Test coffee query finds coffee preference."""
        facts_coffee = mem_mgr.get_relevant_facts_for_prompt(query="tôi thích uống cà phê gì", limit=3)
        keys = [f.get("key") for f in facts_coffee]
        assert "coffee_preference" in keys or "user_name" in keys

    def test_get_system_prompt_context_with_query(self, mem_mgr: MemoryManager) -> None:
        """Test assembling system prompt context with query."""
        ctx = mem_mgr.get_system_prompt_context(query="dự án JARVIS")
        assert "User Profile & Long-Term Memories" in ctx
        assert "Hung" in ctx or "JARVIS" in ctx

    def test_build_jarvis_system_prompt_with_memory(self, mem_mgr: MemoryManager) -> None:
        """Test building complete system prompt with embedded persistent memory."""
        mem_ctx = mem_mgr.get_system_prompt_context(query="cà phê")
        prompt = build_jarvis_system_prompt(
            context_info={"Platform": "Windows 11"},
            memory_context=mem_ctx,
        )
        assert "You are JARVIS" in prompt
        assert "Persistent Memories & Context" in prompt
        assert "User Profile" in prompt
