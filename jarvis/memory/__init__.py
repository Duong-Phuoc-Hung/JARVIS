"""
jarvis/memory
=============
JARVIS Context & Persistent Memory Layer (Milestone 2 - R2 & Sprint 31).
Exports:
  - SessionContextManager, ConversationTurn (10-turn sliding FIFO conversation buffer)
  - SQLiteMemoryStore (Thread-safe WAL SQLite database for facts, episodes, habits)
  - MemoryManager (Master memory orchestrator with prompt injection & command helpers)
  - SemanticVectorStore (Hybrid lexical-semantic vector store with dense embedding)
  - SemanticEmbeddingEngine, get_embedding_engine (128-d zero-VRAM dense embedding engine)
"""
from __future__ import annotations

from jarvis.memory.embeddings import (
    DenseSemanticHashEmbeddingBackend,
    ONNXEmbeddingBackend,
    SemanticEmbeddingEngine,
    get_embedding_engine,
)
from jarvis.memory.manager import MemoryManager
from jarvis.memory.session import ConversationTurn, SessionContextManager
from jarvis.memory.sqlite_store import SQLiteMemoryStore
from jarvis.memory.vector_store import (
    DocumentVector,
    SearchResult,
    SemanticVectorStore,
    VectorStoreConfig,
)

__all__ = [
    "ConversationTurn",
    "SessionContextManager",
    "SQLiteMemoryStore",
    "MemoryManager",
    "SemanticVectorStore",
    "VectorStoreConfig",
    "DocumentVector",
    "SearchResult",
    "DenseSemanticHashEmbeddingBackend",
    "ONNXEmbeddingBackend",
    "SemanticEmbeddingEngine",
    "get_embedding_engine",
]
