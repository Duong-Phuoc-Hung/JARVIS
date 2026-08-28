"""
tests/unit/test_memory_system.py
================================
Comprehensive unit test suite for Milestone 2: Context & Persistent Memory Layer (R2).
Covers:
  - SQLite initialization, WAL mode, persistence across reconnects, concurrent thread safety.
  - 10-turn sliding FIFO session context eviction, formatting, and clearing.
  - Semantic fact storage, UPSERT, listing, deletion, and "nhớ rằng..." command heuristics.
  - Episodic interaction logging, querying, habit tracking, and today's activity summary.
  - System prompt memory injection into LLMIntentRouter.
"""
from __future__ import annotations

import concurrent.futures
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from jarvis.llm.client import ChatMessage, LLMClient, LLMResponse
from jarvis.llm.router import LLMIntentRouter, build_jarvis_system_prompt
from jarvis.memory.manager import MemoryManager
from jarvis.memory.session import ConversationTurn, SessionContextManager
from jarvis.memory.sqlite_store import SQLiteMemoryStore

# ============================================================================
# 1. SQLite Store & WAL Mode Tests
# ============================================================================

def test_sqlite_store_initialization(tmp_path: Path):
    """Verifies SQLite tables and parent directories are automatically created."""
    db_file = tmp_path / "sub_dir" / "test_memory.db"
    assert not db_file.parent.exists()

    store = SQLiteMemoryStore(db_path=db_file)
    assert db_file.exists()

    # Verify tables exist
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    conn.close()

    assert "facts" in tables
    assert "episodes" in tables
    assert "user_habits" in tables


def test_sqlite_wal_mode_enabled(tmp_path: Path):
    """Verifies that WAL (Write-Ahead Logging) mode is activated."""
    db_file = tmp_path / "wal_test.db"
    store = SQLiteMemoryStore(db_path=db_file)
    journal_mode = store.get_journal_mode()
    assert journal_mode == "wal"


def test_sqlite_persistence_across_reconnects(tmp_path: Path):
    """Verifies stored facts and episodes persist across separate store instances."""
    db_file = tmp_path / "persist.db"

    # Instance 1: Store data
    store1 = SQLiteMemoryStore(db_path=db_file)
    store1.store_fact(key="user_name", value="Hưng", category="profile")
    store1.log_episode(command="bật đèn", intent="smart_home", outcome="Đèn bật", success=True)
    store1.record_habit(habit_key="morning_briefing", habit_type="routine")

    # Instance 2: Connect and verify data persists
    store2 = SQLiteMemoryStore(db_path=db_file)
    fact = store2.get_fact(key="user_name", category="profile")
    assert fact is not None
    assert fact["value"] == "Hưng"

    episodes = store2.get_today_episodes()
    assert len(episodes) == 1
    assert episodes[0]["command"] == "bật đèn"
    assert episodes[0]["intent"] == "smart_home"

    habits = store2.get_habits()
    assert len(habits) == 1
    assert habits[0]["habit_key"] == "morning_briefing"


def test_sqlite_store_concurrent_thread_safety(tmp_path: Path):
    """Verifies thread-safe concurrent writes and reads without lock errors."""
    db_file = tmp_path / "concurrent.db"
    store = SQLiteMemoryStore(db_path=db_file)

    def worker_write_fact(i: int):
        store.store_fact(key=f"key_{i}", value=f"value_{i}", category="general")
        store.log_episode(command=f"cmd_{i}", intent="test", outcome="ok", success=True)

    threads = []
    for i in range(25):
        t = threading.Thread(target=worker_write_fact, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    facts = store.list_facts(limit=100)
    assert len(facts) == 25
    episodes = store.get_today_episodes()
    assert len(episodes) == 25


# ============================================================================
# 2. Session Context Manager & 10-Turn FIFO Eviction Tests
# ============================================================================

def test_session_manager_turn_addition():
    """Verifies adding user and assistant turns."""
    session = SessionContextManager(max_turns=10)
    assert len(session) == 0

    turn1 = session.add_user_turn("Xin chào JARVIS")
    assert turn1.role == "user"
    assert turn1.content == "Xin chào JARVIS"
    assert len(session) == 1

    turn2 = session.add_assistant_turn("Chào Ngài, tôi có thể giúp gì?", action_name="greet")
    assert turn2.role == "assistant"
    assert turn2.action_name == "greet"
    assert len(session) == 2

    history = session.get_history()
    assert len(history) == 2
    assert history[0]["content"] == "Xin chào JARVIS"
    assert history[1]["content"] == "Chào Ngài, tôi có thể giúp gì?"


def test_session_manager_sliding_fifo_eviction():
    """Verifies that exceeding max_turns automatically evicts the oldest turns in FIFO order."""
    max_turns = 3  # Max 3 pairs = 6 messages
    session = SessionContextManager(max_turns=max_turns)

    # Add 5 dialogue pairs (10 messages)
    for i in range(1, 6):
        session.add_user_turn(f"User message {i}")
        session.add_assistant_turn(f"Assistant response {i}")

    # Total buffer length should be capped at max_turns * 2 = 6
    assert len(session) == 6

    history = session.get_history()
    assert len(history) == 6

    # The oldest turns (messages 1 and 2) must have been evicted
    assert history[0]["content"] == "User message 3"
    assert history[1]["content"] == "Assistant response 3"
    assert history[-2]["content"] == "User message 5"
    assert history[-1]["content"] == "Assistant response 5"


def test_session_manager_formatted_context():
    """Verifies get_formatted_context formats conversation turns accurately."""
    session = SessionContextManager(max_turns=10)
    session.add_user_turn("Bật đèn phòng khách")
    session.add_assistant_turn("Đang bật đèn phòng khách cho Ngài.")

    formatted = session.get_formatted_context()
    assert "- User: Bật đèn phòng khách" in formatted
    assert "- JARVIS: Đang bật đèn phòng khách cho Ngài." in formatted


def test_session_manager_clear():
    """Verifies clearing session history and rotating session ID."""
    session = SessionContextManager(max_turns=10)
    old_id = session.session_id
    session.add_user_turn("Test")
    assert len(session) == 1

    session.clear()
    assert len(session) == 0
    assert session.session_id != old_id
    assert session.get_formatted_context() == ""


def test_session_manager_get_context_turns():
    """Verifies conversion to ChatMessage list for LLM consumption."""
    session = SessionContextManager(max_turns=10)
    session.add_user_turn("Thời tiết hôm nay")
    session.add_assistant_turn("Thời tiết 28 độ C")

    chat_messages = session.get_context_turns()
    assert len(chat_messages) == 2
    assert isinstance(chat_messages[0], ChatMessage)
    assert chat_messages[0].role == "user"
    assert chat_messages[0].content == "Thời tiết hôm nay"


# ============================================================================
# 3. Fact Storage, UPSERT, and Direct "Nhớ rằng..." Commands
# ============================================================================

def test_fact_crud_and_upsert(tmp_path: Path):
    """Verifies fact CRUD operations and UPSERT overwrite."""
    manager = MemoryManager(db_path=tmp_path / "facts.db")

    # 1. Create
    assert manager.store_fact(key="editor", value="VS Code", category="preference")
    fact = manager.get_fact(key="editor", category="preference")
    assert fact is not None
    assert fact["value"] == "VS Code"
    assert fact["access_count"] >= 1

    # 2. Update (UPSERT)
    assert manager.store_fact(key="editor", value="Cursor AI", category="preference")
    fact_updated = manager.get_fact(key="editor", category="preference")
    assert fact_updated["value"] == "Cursor AI"

    # 3. List
    facts = manager.list_facts(category="preference")
    assert len(facts) == 1
    assert facts[0]["key"] == "editor"

    # 4. Delete
    assert manager.delete_fact(key="editor", category="preference")
    assert manager.get_fact(key="editor", category="preference") is None


def test_handle_remember_commands(tmp_path: Path):
    """Verifies natural language fact extraction from Vietnamese 'nhớ rằng...' commands."""
    manager = MemoryManager(db_path=tmp_path / "remember.db")

    # 1. User Name
    cmd1 = "JARVIS, nhớ rằng tôi tên là Hưng"
    assert manager.is_remember_command(cmd1)
    res1 = manager.handle_remember_command(cmd1)
    assert res1["success"] is True
    assert res1["category"] == "profile"
    assert res1["key"] == "user_name"
    assert res1["value"] == "Hưng"
    assert "ghi nhớ" in res1["message"]

    # 2. User Email
    cmd2 = "nhớ rằng email của tôi là hung@jarvis.ai"
    res2 = manager.handle_remember_command(cmd2)
    assert res2["success"] is True
    assert res2["category"] == "profile"
    assert res2["key"] == "email"
    assert res2["value"] == "hung@jarvis.ai"

    # 3. User Music Preference
    cmd3 = "hãy nhớ rằng tôi thích nghe nhạc lo-fi khi làm việc"
    res3 = manager.handle_remember_command(cmd3)
    assert res3["success"] is True
    assert res3["category"] == "preference"
    assert res3["key"] == "favorite_music"
    assert "lo-fi" in res3["value"]

    # 4. Active Project
    cmd4 = "nhớ là dự án của tôi là JARVIS Assistant"
    res4 = manager.handle_remember_command(cmd4)
    assert res4["success"] is True
    assert res4["category"] == "project"
    assert res4["key"] == "current_project"
    assert "JARVIS Assistant" in res4["value"]

    # 5. Key-value statement
    cmd5 = "nhớ rằng wifi văn phòng là JARVIS_5G_VIP"
    res5 = manager.handle_remember_command(cmd5)
    assert res5["success"] is True
    assert "wifi" in res5["key"]
    assert res5["value"] == "JARVIS_5G_VIP"

    # Verify all 5 facts stored in SQLite
    all_facts = manager.list_facts(limit=10)
    assert len(all_facts) == 5


# ============================================================================
# 4. Episodic Logging & Today's Summary Tests
# ============================================================================

def test_episodic_logging_and_summary(tmp_path: Path):
    """Verifies episodic interaction recording and today's activity summary."""
    manager = MemoryManager(db_path=tmp_path / "episodes.db")

    # Initially no episodes
    summary_empty = manager.handle_today_summary("hôm nay tôi đã làm gì?")
    assert summary_empty["count"] == 0
    assert "chưa thực hiện tác vụ nào" in summary_empty["summary"]

    # Log 3 episodes
    manager.log_episode(command="bật đèn phòng khách", intent="smart_home", outcome="Đèn bật", success=True)
    manager.log_episode(command="thời tiết hà nội", intent="weather", outcome="28 độ C", success=True)
    manager.log_episode(command="mở spotify bài lofi", intent="spotify", outcome="Đang phát", success=True)

    today_eps = manager.get_today_episodes()
    assert len(today_eps) == 3

    # Test summary command
    summary_full = manager.handle_today_summary("JARVIS, tóm tắt hoạt động hôm nay")
    assert summary_full["count"] == 3
    assert summary_full["success_count"] == 3
    assert "3 tác vụ" in summary_full["summary"]
    assert "smart_home" in summary_full["summary"] or "tác vụ" in summary_full["summary"]


def test_user_habit_tracking(tmp_path: Path):
    """Verifies habit frequency incrementing."""
    manager = MemoryManager(db_path=tmp_path / "habits.db")

    manager.store.record_habit(habit_key="briefing_morning", habit_type="routine", typical_hour=8)
    manager.store.record_habit(habit_key="briefing_morning", habit_type="routine", typical_hour=8)
    manager.store.record_habit(habit_key="spotify_lofi", habit_type="music", typical_hour=9)

    habits = manager.store.get_habits()
    assert len(habits) == 2
    assert habits[0]["habit_key"] == "briefing_morning"
    assert habits[0]["frequency"] == 2
    assert habits[1]["habit_key"] == "spotify_lofi"
    assert habits[1]["frequency"] == 1


# ============================================================================
# 5. System Prompt Injection & Router Integration Tests
# ============================================================================

def test_system_prompt_memory_injection(tmp_path: Path):
    """Verifies prompt generator properly embeds facts and session context."""
    manager = MemoryManager(db_path=tmp_path / "prompt.db")

    manager.store_fact(key="user_name", value="Hưng", category="profile")
    manager.store_fact(key="favorite_music", value="Lo-Fi Chill", category="preference")
    manager.add_session_turn("user", "Bật quạt phòng khách")
    manager.add_session_turn("assistant", "Đang bật quạt cho Ngài.")

    mem_ctx = manager.get_system_prompt_context()
    assert "### User Profile & Long-Term Memories:" in mem_ctx
    assert "[profile] user_name: Hưng" in mem_ctx
    assert "[preference] favorite_music: Lo-Fi Chill" in mem_ctx
    assert "### Recent Session History:" in mem_ctx
    assert "- User: Bật quạt phòng khách" in mem_ctx

    system_prompt = build_jarvis_system_prompt(
        context_info={"OS": "Windows 11"},
        memory_context=mem_ctx,
    )
    assert "### Persistent Memories & Context:" in system_prompt
    assert "user_name: Hưng" in system_prompt
    assert "- OS: Windows 11" in system_prompt


def test_router_with_memory_manager_fast_path(tmp_path: Path):
    """Verifies LLMIntentRouter routes direct memory commands via fast path."""
    manager = MemoryManager(db_path=tmp_path / "router_mem.db")
    mock_llm = MagicMock(spec=LLMClient)

    router = LLMIntentRouter(
        llm_client=mock_llm,
        dispatcher=None,
        fast_path_enabled=True,
        memory_manager=manager,
    )

    # 1. Test "nhớ rằng..." command
    res1 = router.parse_intent("JARVIS, nhớ rằng tôi tên là Hưng")
    assert res1.action_name == "memory_save_fact"
    assert res1.source == "rule_fast_path"
    assert "Hưng" in res1.response_text
    # Verify fact stored
    assert manager.get_fact("user_name", "profile")["value"] == "Hưng"
    # Ensure LLM was not called (fast-path handled)
    mock_llm.generate.assert_not_called()

    # 2. Test "hôm nay tôi đã làm gì?" command
    manager.log_episode(command="bật đèn", intent="smart_home", outcome="Đèn bật", success=True)
    res2 = router.parse_intent("JARVIS, hôm nay tôi đã làm gì?")
    assert res2.action_name == "memory_summarize_daily"
    assert res2.source == "rule_fast_path"
    assert "1 tác vụ" in res2.response_text
    mock_llm.generate.assert_not_called()


def test_router_injects_memory_context_to_llm(tmp_path: Path):
    """Verifies that non-rule queries trigger LLM with injected memory context."""
    manager = MemoryManager(db_path=tmp_path / "llm_mem.db")
    manager.store_fact(key="user_name", value="Hưng", category="profile")
    manager.add_session_turn("user", "Hello")
    manager.add_session_turn("assistant", "Hi")

    mock_llm = MagicMock(spec=LLMClient)
    mock_llm.generate.return_value = LLMResponse(content="Chào anh Hưng, tôi có thể giúp gì?")

    router = LLMIntentRouter(
        llm_client=mock_llm,
        dispatcher=None,
        fast_path_enabled=True,
        memory_manager=manager,
    )

    res = router.parse_intent("Bạn có biết tôi là ai không?", force_llm=True)
    assert res.source == "llm"
    assert res.action_name == "generic_llm_response"

    # Verify LLM was called with system_prompt containing memory context
    mock_llm.generate.assert_called_once()
    called_kwargs = mock_llm.generate.call_args.kwargs
    system_prompt_used = called_kwargs.get("system_prompt", "")
    assert "### Persistent Memories & Context:" in system_prompt_used
    assert "user_name: Hưng" in system_prompt_used
    assert "- User: Hello" in system_prompt_used


# ============================================================================
# 6. Additional Edge Cases & Robustness Tests
# ============================================================================

def test_session_manager_concurrent_thread_safety():
    """Verifies that SessionContextManager handles high concurrent turn additions."""
    session = SessionContextManager(max_turns=50)

    def worker_add(idx: int):
        session.add_user_turn(f"User {idx}")
        session.add_assistant_turn(f"Assistant {idx}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker_add, i) for i in range(50)]
        concurrent.futures.wait(futures)

    # Max length is 50 * 2 = 100
    assert len(session) == 100
    turns = session.get_turns()
    assert len(turns) == 100


def test_memory_manager_custom_prompt_limits(tmp_path: Path):
    """Verifies limit parameter behavior in get_system_prompt_context."""
    manager = MemoryManager(db_path=tmp_path / "limits.db")

    for i in range(15):
        manager.store_fact(key=f"fact_{i}", value=f"val_{i}", category="general")
        manager.add_session_turn("user", f"query {i}")
        manager.add_session_turn("assistant", f"reply {i}")

    prompt_ctx = manager.get_system_prompt_context(max_facts=3, max_turns=2)
    # Only 3 facts should be included
    assert prompt_ctx.count("- [general]") == 3
    # Only 2 pairs = 4 messages should be included
    assert prompt_ctx.count("- User:") == 2
    assert prompt_ctx.count("- JARVIS:") == 2


def test_memory_manager_mixed_episode_summary(tmp_path: Path):
    """Verifies summary generation with mixed success and failed episodes."""
    manager = MemoryManager(db_path=tmp_path / "mixed.db")

    manager.log_episode(command="cmd1", intent="intent_a", outcome="ok", success=True)
    manager.log_episode(command="cmd2", intent="intent_a", outcome="ok", success=True)
    manager.log_episode(command="cmd3", intent="intent_b", outcome="err", success=False, error_message="timeout")

    summary = manager.handle_today_summary()
    assert summary["count"] == 3
    assert summary["success_count"] == 2
    assert "3 tác vụ" in summary["summary"]
    assert "2 thành công" in summary["summary"]
    assert "intent_a" in summary["summary"]


def test_sqlite_store_date_range_queries(tmp_path: Path):
    """Verifies querying episodes by date filters."""
    store = SQLiteMemoryStore(db_path=tmp_path / "dates.db")

    store.log_episode(command="c1", intent="i1", outcome="o1")
    store.log_episode(command="c2", intent="i2", outcome="o2")

    all_eps = store.get_episodes(limit=10)
    assert len(all_eps) == 2

    # Query with date string
    today_str = time.strftime("%Y-%m-%d")
    today_eps = store.get_episodes(start_date=today_str, end_date=today_str)
    assert len(today_eps) == 2

    # Future date should return empty
    future_eps = store.get_episodes(start_date="2099-01-01")
    assert len(future_eps) == 0


def test_fact_not_found_and_delete_not_found(tmp_path: Path):
    """Verifies non-existent fact retrieval and deletion handling."""
    store = SQLiteMemoryStore(db_path=tmp_path / "nf.db")
    assert store.get_fact("non_existent_key") is None
    assert store.delete_fact("non_existent_key") is False


def test_generic_remember_command_fallback(tmp_path: Path):
    """Verifies fallback fact storage for unstructured remember requests."""
    manager = MemoryManager(db_path=tmp_path / "gen_remember.db")

    cmd = "JARVIS, hãy nhớ là chìa khóa dự phòng nằm trong ngăn kéo bàn làm việc"
    res = manager.handle_remember_command(cmd)
    assert res["success"] is True
    assert res["category"] == "general"
    assert "chìa_khóa" in res["key"] or "chìa khóa" in res["key"] or len(res["key"]) > 0
    assert "ngăn kéo" in res["value"]

