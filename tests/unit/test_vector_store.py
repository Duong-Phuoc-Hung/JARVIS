"""
tests/unit/test_vector_store.py
=================================
Unit tests for the Semantic Vector Store (TF-IDF cosine similarity).
"""
from __future__ import annotations

import time
import json
from pathlib import Path

import pytest

from jarvis.memory.vector_store import (
    SemanticVectorStore,
    VectorStoreConfig,
    DocumentVector,
    SearchResult,
)


@pytest.fixture
def store(tmp_path):
    cfg = VectorStoreConfig(
        persist_path=str(tmp_path / "test_vectors.json"),
        auto_save=False,
    )
    return SemanticVectorStore(config=cfg)


class TestAddAndRetrieve:
    def test_add_document_returns_true(self, store):
        ok = store.add_document("doc1", "xin chào JARVIS trợ lý AI")
        assert ok is True

    def test_get_document_after_add(self, store):
        store.add_document("doc2", "JARVIS is an AI assistant")
        doc = store.get_document("doc2")
        assert doc is not None
        assert doc.doc_id == "doc2"
        assert "JARVIS" in doc.content

    def test_add_empty_content_returns_false(self, store):
        ok = store.add_document("empty", "   ")
        assert ok is False

    def test_size_increases_on_add(self, store):
        initial = store.size()
        store.add_document("sz1", "content one")
        store.add_document("sz2", "content two")
        assert store.size() == initial + 2


class TestSearch:
    def test_search_returns_list(self, store):
        store.add_document("s1", "machine learning artificial intelligence")
        results = store.search("machine learning")
        assert isinstance(results, list)

    def test_search_finds_relevant_document(self, store):
        store.add_document("jarvis_ai", "JARVIS là trợ lý AI thông minh cá nhân")
        store.add_document("cooking", "công thức nấu phở bò Hà Nội")
        results = store.search("trợ lý AI JARVIS", k=3)
        assert len(results) > 0
        doc_ids = [r.doc_id for r in results]
        assert "jarvis_ai" in doc_ids

    def test_search_top_k_limiting(self, store):
        for i in range(10):
            store.add_document(f"doc_{i}", f"python programming language concept {i}")
        results = store.search("python programming", k=3)
        assert len(results) <= 3

    def test_search_result_has_score(self, store):
        store.add_document("scored", "neural network deep learning model")
        results = store.search("deep learning", k=5)
        for r in results:
            assert 0.0 <= r.score <= 1.0


class TestCosimeSimilarity:
    def test_exact_match_high_score(self, store):
        """Same content should produce very high similarity."""
        store.add_document("exact", "JARVIS voice assistant command control")
        results = store.search("JARVIS voice assistant command control", k=1)
        if results:
            assert results[0].score > 0.7

    def test_unrelated_query_low_score(self, store):
        """Completely unrelated query should have low/zero results."""
        store.add_document("food", "pizza pasta spaghetti Italian cuisine recipe")
        results = store.search("quantum physics nuclear reactor", k=5)
        # Either empty or very low score
        high_scores = [r for r in results if r.score > 0.5]
        assert len(high_scores) == 0


class TestCategoryFilter:
    def test_category_filter_excludes_other_categories(self, store):
        store.add_document("note1", "ghi chú dự án A quan trọng", category="notes")
        store.add_document("ep1", "người dùng hỏi về dự án A", category="episodes")
        results = store.search("dự án A", k=10, category_filter="notes")
        for r in results:
            assert r.category == "notes"

    def test_categories_method_returns_list(self, store):
        store.add_document("c1", "content one", category="cat_a")
        store.add_document("c2", "content two", category="cat_b")
        cats = store.categories()
        assert "cat_a" in cats
        assert "cat_b" in cats


class TestPersistence:
    def test_save_and_load(self, tmp_path):
        path = str(tmp_path / "persist.json")
        cfg = VectorStoreConfig(persist_path=path, auto_save=True)
        store1 = SemanticVectorStore(config=cfg)
        store1.add_document("persist_doc", "content to persist across restarts")

        # Load in a new instance
        store2 = SemanticVectorStore(config=cfg)
        doc = store2.get_document("persist_doc")
        assert doc is not None
        assert "content to persist" in doc.content

    def test_explicit_save_creates_file(self, tmp_path):
        path = str(tmp_path / "explicit.json")
        cfg = VectorStoreConfig(persist_path=path, auto_save=False)
        store = SemanticVectorStore(config=cfg)
        store.add_document("d1", "saved content")
        store.save()
        assert Path(path).exists()


class TestDeleteDocument:
    def test_delete_removes_document(self, store):
        store.add_document("del1", "document to be deleted")
        assert store.get_document("del1") is not None
        ok = store.delete_document("del1")
        assert ok is True
        assert store.get_document("del1") is None

    def test_delete_nonexistent_returns_false(self, store):
        ok = store.delete_document("nonexistent_id")
        assert ok is False

    def test_deleted_document_not_in_search(self, store):
        store.add_document("del_search", "unique content JARVIS AI assistant")
        store.delete_document("del_search")
        results = store.search("unique content JARVIS", k=5)
        doc_ids = [r.doc_id for r in results]
        assert "del_search" not in doc_ids
