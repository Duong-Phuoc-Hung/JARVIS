"""
jarvis/memory
=============
JARVIS Context & Persistent Memory Layer (Milestone 2 - R2).
Exports:
  - SessionContextManager, ConversationTurn (10-turn sliding FIFO conversation buffer)
  - SQLiteMemoryStore (Thread-safe WAL SQLite database for facts, episodes, habits)
  - MemoryManager (Master memory orchestrator with prompt injection & command helpers)
"""
from __future__ import annotations

from jarvis.memory.manager import MemoryManager
from jarvis.memory.session import ConversationTurn, SessionContextManager
from jarvis.memory.sqlite_store import SQLiteMemoryStore

__all__ = [
    "ConversationTurn",
    "SessionContextManager",
    "SQLiteMemoryStore",
    "MemoryManager",
]
