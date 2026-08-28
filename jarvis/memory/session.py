"""
jarvis/memory/session.py
========================
Short-Term Session Context Manager managing a sliding FIFO conversation window.
Tracks ongoing conversational turns (user utterances & assistant responses)
for multi-turn dialogue reasoning and system prompt injection.
"""
from __future__ import annotations

import collections
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from jarvis.llm.client import ChatMessage


@dataclass
class ConversationTurn:
    """Represents a single conversational turn in the session buffer."""
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    timestamp: float = field(default_factory=time.time)
    turn_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    action_name: str | None = None
    parameters: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Converts turn to dictionary format."""
        return {
            "turn_id": self.turn_id,
            "timestamp": self.timestamp,
            "role": self.role,
            "content": self.content,
            "action_name": self.action_name,
            "parameters": self.parameters,
            "metadata": self.metadata,
        }


class SessionContextManager:
    """
    Thread-safe FIFO sliding-window conversation history buffer.
    Maintains up to `max_turns` conversation dialogue turns (user + assistant pairs).
    """

    def __init__(self, max_turns: int = 10, session_id: str | None = None) -> None:
        self.max_turns = max_turns
        self.session_id = session_id or str(uuid.uuid4())
        # A conversation turn usually consists of (user, assistant).
        # We store up to max_turns * 2 messages.
        self._history: collections.deque[ConversationTurn] = collections.deque(maxlen=max_turns * 2)
        self._lock = threading.RLock()

    def add_turn(
        self,
        role: str,
        content: str,
        action_name: str | None = None,
        parameters: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ConversationTurn:
        """
        Adds a conversation turn to the sliding FIFO queue.
        Oldest turns are automatically evicted when capacity is reached.
        """
        meta = dict(metadata or {})
        meta.update(kwargs)
        turn = ConversationTurn(
            role=role,
            content=content,
            action_name=action_name,
            parameters=parameters,
            metadata=meta,
        )
        with self._lock:
            self._history.append(turn)
        return turn

    def add_user_turn(self, content: str, **kwargs: Any) -> ConversationTurn:
        """Convenience method for user utterance."""
        return self.add_turn("user", content, **kwargs)

    def add_assistant_turn(
        self,
        content: str,
        action_name: str | None = None,
        parameters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ConversationTurn:
        """Convenience method for assistant response."""
        return self.add_turn("assistant", content, action_name=action_name, parameters=parameters, **kwargs)

    def get_history(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Returns turns as a list of dictionaries."""
        with self._lock:
            items = list(self._history)
            if limit is not None:
                items = items[-limit:]
            return [t.to_dict() for t in items]

    def get_turns(self, limit: int | None = None) -> list[ConversationTurn]:
        """Returns raw ConversationTurn objects."""
        with self._lock:
            items = list(self._history)
            if limit is not None:
                items = items[-limit:]
            return list(items)

    def get_context_turns(self, limit: int | None = None) -> list[ChatMessage]:
        """Converts recent turns to LLM ChatMessage objects."""
        with self._lock:
            items = list(self._history)
            if limit is not None:
                items = items[-limit:]
            return [ChatMessage(role=t.role, content=t.content) for t in items]

    def get_formatted_context(self, limit: int | None = None) -> str:
        """
        Formats recent turns into a structured string suitable for system prompt injection.
        """
        with self._lock:
            items = list(self._history)
            if limit is not None:
                items = items[-limit:]
            if not items:
                return ""
            lines = []
            for t in items:
                role_label = "User" if t.role.lower() == "user" else ("JARVIS" if t.role.lower() in ("assistant", "model", "bot") else t.role.capitalize())
                lines.append(f"- {role_label}: {t.content}")
            return "\n".join(lines)

    def clear(self) -> None:
        """Clears all session conversation history and resets session ID."""
        with self._lock:
            self._history.clear()
            self.session_id = str(uuid.uuid4())

    def __len__(self) -> int:
        with self._lock:
            return len(self._history)
