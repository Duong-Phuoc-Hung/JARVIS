"""
jarvis/memory/manager.py
========================
Master Memory Manager orchestrating short-term conversation context,
persistent SQLite facts/habits/episodes, system prompt memory injection,
and direct Vietnamese memory commands ("nhớ rằng...", "hôm nay tôi đã làm gì?").
"""
from __future__ import annotations

import collections
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from jarvis.memory.session import ConversationTurn, SessionContextManager
from jarvis.memory.sqlite_store import SQLiteMemoryStore

logger = logging.getLogger("jarvis.memory.manager")


class MemoryManager:
    """
    Unified memory management subsystem orchestrating:
      1. Short-term 10-turn sliding FIFO conversation buffer.
      2. Long-term SQLite persistent store (facts, episodes, habits).
      3. Dynamic memory injection for LLM system prompts.
      4. Natural language memory command extractors and handlers.
    """

    def __init__(
        self,
        db_path: Union[str, Path] = "logs/memory.db",
        max_session_turns: int = 10,
    ) -> None:
        self.db_path = Path(db_path)
        self.max_session_turns = max_session_turns
        self.session = SessionContextManager(max_turns=max_session_turns)
        self.store = SQLiteMemoryStore(db_path=self.db_path)

        # Regex patterns for direct memory commands
        self._remember_regex = re.compile(
            r"^(?:jarvis\s*,?\s*)?(?:hãy\s*)?(?:nhớ\s*rằng|ghi\s*nhớ|nhớ\s*là|hãy\s*nhớ|remember\s*that|remember)\s*[:,\s]\s*(.+)",
            re.IGNORECASE,
        )
        self._today_summary_regex = re.compile(
            r"(?:hôm\s*nay\s*tôi\s*(?:đã\s*)?làm\s*gì|tóm\s*tắt\s*(?:hoạt\s*động\s*)?hôm\s*nay|tổng\s*kết\s*(?:hoạt\s*động\s*)?hôm\s*nay|lịch\s*sử\s*hôm\s*nay|what\s*(?:did\s*i\s*do\s*today|have\s*i\s*done\s*today))",
            re.IGNORECASE,
        )

    # ── Session Context Delegations ──────────────────────────────────────────

    def add_session_turn(
        self,
        role: str,
        content: str,
        action_name: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> ConversationTurn:
        """Adds a turn to the session FIFO sliding window."""
        return self.session.add_turn(
            role=role,
            content=content,
            action_name=action_name,
            parameters=parameters,
            metadata=metadata,
            **kwargs,
        )

    def get_session_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Returns conversation turns as a list of dicts."""
        lim = limit if limit is not None else self.max_session_turns
        return self.session.get_history(limit=lim)

    def get_session_turns(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Alias for get_session_history."""
        return self.get_session_history(limit=limit)

    def list_episodes(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Lists episodic interaction records."""
        return self.store.get_episodes(limit=limit)

    def get_session_context(self, limit: Optional[int] = None) -> str:
        """Returns formatted conversation history for prompt injection."""
        return self.session.get_formatted_context(limit=limit)

    def clear_session(self) -> None:
        """Clears current session history."""
        self.session.clear()

    # ── Facts & Preferences Delegations ──────────────────────────────────────

    def store_fact(
        self,
        key: str,
        value: str,
        category: str = "general",
        confidence: float = 1.0,
        source: str = "user_explicit",
    ) -> bool:
        """Stores or updates a persistent semantic fact."""
        return self.store.store_fact(
            key=key,
            value=value,
            category=category,
            confidence=confidence,
            source=source,
        )

    def get_fact(self, key: str, category: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieves a persistent fact."""
        return self.store.get_fact(key=key, category=category)

    def list_facts(
        self,
        category: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Lists stored facts."""
        return self.store.list_facts(category=category, limit=limit)

    def delete_fact(self, key: str, category: Optional[str] = None) -> bool:
        """Deletes a stored fact."""
        return self.store.delete_fact(key=key, category=category)

    # ── Episodic Interaction Delegations ─────────────────────────────────────

    def log_episode(
        self,
        command: str,
        intent: str,
        outcome: str,
        success: bool = True,
        session_id: Optional[str] = None,
        trigger_type: str = "VOICE",
        latency_ms: float = 0.0,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Logs an interaction episode into the SQLite store."""
        sess_id = session_id or self.session.session_id
        return self.store.log_episode(
            command=command,
            intent=intent,
            outcome=outcome,
            success=success,
            session_id=sess_id,
            trigger_type=trigger_type,
            latency_ms=latency_ms,
            error_message=error_message,
            metadata=metadata,
        )

    def get_today_episodes(self) -> List[Dict[str, Any]]:
        """Retrieves all episodes logged today."""
        return self.store.get_today_episodes()

    # ── System Prompt Memory Injection ───────────────────────────────────────

    def get_system_prompt_context(
        self,
        max_facts: int = 10,
        max_turns: int = 5,
    ) -> str:
        """
        Assembles persistent user profile / facts and recent conversational turns
        into a clean markdown block for LLM system prompt injection.
        """
        sections: List[str] = []

        # 1. Long-term Facts & User Profile
        facts = self.list_facts(limit=max_facts)
        if facts:
            fact_lines = ["### User Profile & Long-Term Memories:"]
            for f in facts:
                cat = f.get("category", "general")
                k = f.get("key", "")
                v = f.get("value", "")
                fact_lines.append(f"- [{cat}] {k}: {v}")
            sections.append("\n".join(fact_lines))

        # 2. Recent Session Conversation History
        session_ctx = self.get_session_context(limit=max_turns * 2)
        if session_ctx:
            sections.append("### Recent Session History:\n" + session_ctx)

        return "\n\n".join(sections).strip()

    # ── Direct Command Handlers & Heuristic Extractors ───────────────────────

    def is_remember_command(self, text: str) -> bool:
        """Checks if user input is an explicit fact memorization command."""
        return bool(self._remember_regex.search(text.strip()))

    def is_today_summary_command(self, text: str) -> bool:
        """Checks if user input asks for today's interaction summary."""
        return bool(self._today_summary_regex.search(text.strip()))

    def _extract_fact_entities(self, payload: str) -> Tuple[str, str, str]:
        """
        Extracts (category, key, value) from raw memory payload using semantic heuristics.
        """
        clean = payload.strip().rstrip(".").rstrip("!")

        # 1. User Email: "email của tôi là hung@example.com"
        m_email = re.search(r"(?:email(?:\s+của\s+tôi)?\s+là|my\s+email\s+is)\s+([^\s,;]+)", clean, re.IGNORECASE)
        if m_email:
            return ("profile", "email", m_email.group(1).strip())

        # 2. User Name: "tôi tên là Hưng", "tên tôi là Hưng", "tôi tên Hưng"
        m_name = re.search(r"(?:\btên\s+(?:của\s+)?tôi\s+là|\btôi\s+tên\s+là|\btôi\s+tên|\bmy\s+name\s+is|^(?:tôi\s+là))\s+([^\.,;]+)", clean, re.IGNORECASE)
        if m_name:
            name_val = m_name.group(1).strip()
            return ("profile", "user_name", name_val)

        # 3. Project: "dự án của tôi là JARVIS", "tôi đang làm dự án X"
        m_proj = re.search(r"(?:dự\s*án(?:\s+của\s+tôi|\s+hiện\s+tại)?\s+là|đang\s+làm\s+dự\s*án|my\s+project\s+is)\s+(.+)", clean, re.IGNORECASE)
        if m_proj:
            return ("project", "current_project", m_proj.group(1).strip())

        # 4. User Preferences: "tôi thích nghe nhạc lo-fi", "sở thích của tôi là..."
        m_pref = re.search(r"(?:tôi\s+thích|sở\s+thích\s+của\s+tôi\s+là|i\s+like|i\s+prefer)\s+(.+)", clean, re.IGNORECASE)
        if m_pref:
            pref_val = m_pref.group(1).strip()
            # Try to derive a meaningful subkey
            if "nhạc" in pref_val or "music" in pref_val:
                return ("preference", "favorite_music", pref_val)
            elif "ăn" in pref_val or "uống" in pref_val or "food" in pref_val:
                return ("preference", "food_drink", pref_val)
            return ("preference", "user_preference", pref_val)

        # 5. Habit: "tôi thường thức dậy lúc 7h", "thói quen của tôi là..."
        m_habit = re.search(r"(?:tôi\s+thường|thói\s+quen\s+của\s+tôi\s+là)\s+(.+)", clean, re.IGNORECASE)
        if m_habit:
            return ("habit", "user_habit", m_habit.group(1).strip())

        # 6. Key-Value statement: "<key> là <value>" (e.g. "mật khẩu wifi là 12345678")
        m_kv = re.search(r"^(.+?)\s+là\s+(.+)$", clean, re.IGNORECASE)
        if m_kv:
            raw_k = m_kv.group(1).strip()
            raw_v = m_kv.group(2).strip()
            # Normalize key
            k_slug = re.sub(r"\s+", "_", raw_k.lower())
            return ("general", k_slug, raw_v)

        # 7. Fallback General Fact
        slug = re.sub(r"[^\w\s]", "", clean[:30]).strip()
        k_slug = re.sub(r"\s+", "_", slug.lower()) or "custom_fact"
        return ("general", k_slug, clean)

    def handle_remember_command(self, text: str) -> MemoryCommandResult:
        """
        Handles commands like "JARVIS, nhớ rằng tôi tên Hưng".
        Extracts fact entities and stores them into persistent SQLite memory.
        """
        clean = text.strip()
        m = self._remember_regex.search(clean)
        payload = m.group(1).strip() if m else clean

        category, key, value = self._extract_fact_entities(payload)
        success = self.store_fact(key=key, value=value, category=category, source="user_explicit")

        if success:
            msg = f"Tôi đã ghi nhớ thông tin này, thưa Ngài: {key} = {value}."
            return MemoryCommandResult(
                msg,
                success=True,
                action="remember",
                category=category,
                key=key,
                value=value,
                message=msg,
                summary=msg,
            )
        else:
            msg = "Xin lỗi Ngài, tôi không thể lưu thông tin vào bộ nhớ."
            return MemoryCommandResult(
                msg,
                success=False,
                action="remember",
                error="Failed to write fact to persistent database.",
                message=msg,
                summary=msg,
            )

    def handle_today_summary(self, text: str = "") -> MemoryCommandResult:
        """
        Handles commands like "JARVIS, hôm nay tôi đã làm gì?".
        Fetches today's episodes and formats a natural Vietnamese executive summary.
        """
        episodes = self.get_today_episodes()
        if not episodes:
            msg = "Hôm nay Ngài chưa thực hiện tác vụ nào, thưa Ngài."
            return MemoryCommandResult(
                msg,
                success=True,
                action="today_summary",
                count=0,
                episodes=[],
                summary=msg,
                message=msg,
            )

        total_count = len(episodes)
        success_count = sum(1 for e in episodes if e.get("success"))

        # Aggregate intents / actions
        action_counts: Dict[str, int] = collections.Counter()
        for e in episodes:
            intent = e.get("intent") or "tác vụ"
            action_counts[intent] += 1

        breakdown_parts = []
        for intent, cnt in action_counts.most_common(4):
            breakdown_parts.append(f"{cnt} lần {intent}")
        breakdown_str = ", ".join(breakdown_parts) if breakdown_parts else f"{total_count} tác vụ"

        recent_cmds = [e.get("command", "").strip() for e in episodes if e.get("command")]
        cmds_sample = f" (ví dụ: {', '.join(recent_cmds[:2])})" if recent_cmds else ""
        summary_msg = f"Hôm nay Ngài đã thực hiện {total_count} tác vụ ({success_count} thành công), bao gồm: {breakdown_str}{cmds_sample}, thưa Ngài."

        return MemoryCommandResult(
            summary_msg,
            success=True,
            action="today_summary",
            count=total_count,
            success_count=success_count,
            episodes=episodes,
            summary=summary_msg,
            message=summary_msg,
        )


class MemoryCommandResult(str):
    """
    Subclass of str that transparently acts as both a formatted string
    and a dict with metadata for backwards-compatibility across all test suites.
    """
    def __new__(cls, content: str, **kwargs: Any):
        obj = super().__new__(cls, content)
        obj._data = kwargs
        return obj

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            return self._data.get(key, "")
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._data)

