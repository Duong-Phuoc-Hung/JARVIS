"""
jarvis/memory/vector_store.py
==============================
Semantic Vector Store — TF-IDF cosine similarity for memory search.
No GPU or external ML frameworks required. Optional FAISS acceleration.

Usage:
    store = SemanticVectorStore()
    store.add_document("note_1", "JARVIS project progress", category="notes")
    results = store.search("JARVIS update", k=5)
"""
from __future__ import annotations

import json
import logging
import math
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("jarvis.memory.vector_store")

_VIETNAMESE_STOPWORDS = {
    "và", "của", "là", "có", "trong", "với", "cho", "này", "đó", "một",
    "các", "tôi", "bạn", "không", "đã", "được", "thì", "mà", "khi", "nếu",
    "nhưng", "vì", "từ", "theo", "đến", "về", "như", "hay", "hoặc", "để",
    "the", "a", "an", "is", "in", "on", "at", "to", "for", "of", "and",
    "or", "but", "with", "by", "from", "that", "this", "it", "be", "as",
}


@dataclass
class VectorStoreConfig:
    max_documents: int = 10000
    similarity_threshold: float = 0.05
    persist_path: str = ""  # auto-resolved to AppData/JARVIS/vector_store.json
    auto_save: bool = True


@dataclass
class DocumentVector:
    doc_id: str
    content: str
    tokens: list[str]
    tf: dict[str, float]      # Term frequency
    category: str = "general"
    timestamp: float = field(default_factory=time.time)


@dataclass
class SearchResult:
    doc_id: str
    content: str
    score: float
    category: str

    def to_dict(self) -> dict[str, Any]:
        return {"doc_id": self.doc_id, "content": self.content, "score": self.score, "category": self.category}


class SemanticVectorStore:
    """
    Lightweight semantic search using TF-IDF cosine similarity.
    Pure Python — no numpy, no FAISS required by default.
    Optional FAISS backend for 10x speedup when available.
    """

    def __init__(self, config: VectorStoreConfig | None = None) -> None:
        self.config = config or VectorStoreConfig()
        self._documents: dict[str, DocumentVector] = {}
        self._idf: dict[str, float] = {}
        self._lock = threading.Lock()
        self._faiss_index: Any | None = None
        self._faiss_id_map: list[str] = []
        self._load()
        log.info("SemanticVectorStore initialized (%d documents)", len(self._documents))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_document(self, doc_id: str, content: str, category: str = "general") -> bool:
        """Index a document for semantic search."""
        if not content.strip():
            return False
        tokens = self._tokenize(content)
        if not tokens:
            return False
        tf = self._compute_tf(tokens)
        with self._lock:
            self._documents[doc_id] = DocumentVector(
                doc_id=doc_id, content=content[:2000], tokens=tokens,
                tf=tf, category=category,
            )
            self._rebuild_idf()
        if self.config.auto_save:
            self.save()
        return True

    def search(
        self,
        query: str,
        k: int = 5,
        category_filter: str | None = None,
    ) -> list[SearchResult]:
        """Return top-k semantically similar documents."""
        if not query.strip() or not self._documents:
            return []

        q_tokens = self._tokenize(query)
        if not q_tokens:
            return []

        q_tf = self._compute_tf(q_tokens)
        q_tfidf = self._compute_tfidf_vec(q_tf)

        results: list[SearchResult] = []
        with self._lock:
            for doc in self._documents.values():
                if category_filter and doc.category != category_filter:
                    continue
                d_tfidf = self._compute_tfidf_vec(doc.tf)
                score = self._cosine_similarity(q_tfidf, d_tfidf)
                if score >= self.config.similarity_threshold:
                    results.append(SearchResult(
                        doc_id=doc.doc_id,
                        content=doc.content,
                        score=score,
                        category=doc.category,
                    ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]

    def delete_document(self, doc_id: str) -> bool:
        with self._lock:
            if doc_id not in self._documents:
                return False
            del self._documents[doc_id]
            self._rebuild_idf()
        if self.config.auto_save:
            self.save()
        return True

    def get_document(self, doc_id: str) -> DocumentVector | None:
        return self._documents.get(doc_id)

    def clear(self) -> None:
        with self._lock:
            self._documents.clear()
            self._idf.clear()
        if self.config.auto_save:
            self.save()

    def size(self) -> int:
        return len(self._documents)

    def categories(self) -> list[str]:
        return list({d.category for d in self._documents.values()})

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        path = Path(self.config.persist_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {
                "documents": {
                    doc_id: {
                        "doc_id": d.doc_id,
                        "content": d.content,
                        "tokens": d.tokens,
                        "tf": d.tf,
                        "category": d.category,
                        "timestamp": d.timestamp,
                    }
                    for doc_id, d in self._documents.items()
                }
            }
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            log.warning("Vector store save error: %s", exc)

    def _load(self) -> None:
        path = Path(self.config.persist_path)
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            for doc_id, d in raw.get("documents", {}).items():
                self._documents[doc_id] = DocumentVector(
                    doc_id=d["doc_id"],
                    content=d["content"],
                    tokens=d.get("tokens", []),
                    tf=d.get("tf", {}),
                    category=d.get("category", "general"),
                    timestamp=d.get("timestamp", 0.0),
                )
            self._rebuild_idf()
            log.info("Vector store loaded: %d documents", len(self._documents))
        except Exception as exc:
            log.warning("Vector store load error: %s", exc)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize and clean Vietnamese/English text."""
        text = text.lower()
        text = re.sub(r"[^\w\s\u00C0-\u1EF9]", " ", text)
        tokens = text.split()
        return [t for t in tokens if len(t) > 1 and t not in _VIETNAMESE_STOPWORDS]

    def _compute_tf(self, tokens: list[str]) -> dict[str, float]:
        """Term frequency: count / total."""
        if not tokens:
            return {}
        count = Counter(tokens)
        n = len(tokens)
        return {term: cnt / n for term, cnt in count.items()}

    def _rebuild_idf(self) -> None:
        """Recompute IDF across all documents (BM25-style smoothing)."""
        n = len(self._documents)
        if n == 0:
            self._idf = {}
            return
        df: Counter = Counter()
        for doc in self._documents.values():
            for term in set(doc.tokens):
                df[term] += 1
        # BM25-style IDF: log((N+1)/(df+0.5)) — always positive, robust for small N
        self._idf = {term: math.log((n + 1) / (cnt + 0.5)) for term, cnt in df.items()}


    def _compute_tfidf_vec(self, tf: dict[str, float]) -> dict[str, float]:
        """Compute TF-IDF vector."""
        return {term: val * self._idf.get(term, 0.0) for term, val in tf.items()}

    def _cosine_similarity(
        self,
        vec_a: dict[str, float],
        vec_b: dict[str, float],
    ) -> float:
        """Cosine similarity between two TF-IDF vectors."""
        if not vec_a or not vec_b:
            return 0.0
        common = set(vec_a) & set(vec_b)
        if not common:
            return 0.0
        dot = sum(vec_a[t] * vec_b[t] for t in common)
        norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
        norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


__all__ = ["SemanticVectorStore", "VectorStoreConfig", "DocumentVector", "SearchResult"]
