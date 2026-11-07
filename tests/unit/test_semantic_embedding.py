"""
tests/unit/test_semantic_embedding.py
=====================================
Unit test suite for Local Semantic Embedding Engine and Hybrid Vector Store.
Verifies Johnson-Lindenstrauss dense projection, caching, and hybrid retrieval.
"""
from __future__ import annotations

import numpy as np
import pytest

from jarvis.memory.embeddings import (
    DenseSemanticHashEmbeddingBackend,
    SemanticEmbeddingEngine,
    get_embedding_engine,
)
from jarvis.memory.vector_store import (
    SemanticVectorStore,
    VectorStoreConfig,
)


def test_dense_semantic_backend_properties():
    backend = DenseSemanticHashEmbeddingBackend(dim=128, seed=42)

    # Empty text
    empty_vec = backend.embed("")
    assert empty_vec.shape == (128,)
    assert np.allclose(empty_vec, 0.0)

    # Valid text
    vec1 = backend.embed("Dự án JARVIS trí tuệ nhân tạo")
    assert vec1.shape == (128,)
    norm = np.linalg.norm(vec1)
    assert abs(norm - 1.0) < 1e-4

    # Determinism
    vec2 = backend.embed("Dự án JARVIS trí tuệ nhân tạo")
    assert np.allclose(vec1, vec2)


def test_semantic_proximity():
    engine = SemanticEmbeddingEngine()

    v_code1 = engine.embed("Lập trình phần mềm Python cho hệ thống tự động")
    v_code2 = engine.embed("Phát triển mã nguồn Python cho ứng dụng tự động hóa")
    v_food = engine.embed("Công thức nấu phở bò gia truyền thơm ngon đậm đà")

    sim_related = engine.cosine_similarity(v_code1, v_code2)
    sim_unrelated = engine.cosine_similarity(v_code1, v_food)

    assert sim_related > sim_unrelated
    assert sim_related > 0.30


def test_hybrid_vector_store_indexing_and_search(tmp_path):
    store_file = tmp_path / "test_vector_store.json"
    cfg = VectorStoreConfig(persist_path=str(store_file), auto_save=True)
    store = SemanticVectorStore(config=cfg)

    store.add_document("doc1", "Báo cáo tiến độ dự án JARVIS v9.1", category="work")
    store.add_document("doc2", "Kiến trúc hệ thống Mamba-2 SSD và phản xạ nhanh", category="tech")
    store.add_document("doc3", "Lịch trình tập luyện thể dục thể thao buổi chiều", category="health")

    assert store.size() == 3

    # Exact and semantic search
    results = store.search("tiến độ dự án JARVIS", k=2)
    assert len(results) > 0
    assert results[0].doc_id == "doc1"
    assert results[0].score > 0.1

    # Reload from disk and verify embeddings preserved
    store2 = SemanticVectorStore(config=cfg)
    assert store2.size() == 3
    doc1 = store2.get_document("doc1")
    assert doc1 is not None
    assert doc1.embedding is not None
    assert len(doc1.embedding) == 128
