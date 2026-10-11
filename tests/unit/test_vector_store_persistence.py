"""
tests/unit/test_vector_store_persistence.py
============================================
Seam tests for Task 6: VECTOR-PERSISTENCE-FIX1.
Verifies that:
1. SemanticVectorStore() resolves default persist_path to %LOCALAPPDATA%/JARVIS/vector_store.json (or data_path).
2. persist() method is available as standard contract and performs atomic write.
3. Windows atomic-write contract with retry and cleanup is upheld under concurrent writes.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from jarvis.core.paths import data_path
from jarvis.memory.vector_store import (
    SemanticVectorStore,
    VectorStoreConfig,
)


class TestVectorStorePersistenceSeam:
    def test_default_persist_path_resolves_to_data_path(self, monkeypatch, tmp_path):
        """Default SemanticVectorStore() must resolve persist_path to standard data_path."""
        test_dir = tmp_path / "jarvis_data"
        monkeypatch.setenv("JARVIS_DATA_DIR", str(test_dir))

        store = SemanticVectorStore()
        assert store.config.persist_path != ""
        assert Path(store.config.persist_path).name == "vector_store.json"
        assert str(test_dir) in store.config.persist_path

    def test_persist_method_saves_data_atomically(self, tmp_path):
        """persist() method must exist, save documents, and produce valid JSON without temp files left."""
        target_path = tmp_path / "store.json"
        cfg = VectorStoreConfig(persist_path=str(target_path), auto_save=False)
        store = SemanticVectorStore(config=cfg)

        store.add_document("doc100", "Lưu trữ vector an toàn trên Windows")
        # Call persist()
        store.persist()

        assert target_path.exists()
        raw = json.loads(target_path.read_text(encoding="utf-8"))
        assert "doc100" in raw["documents"]
        assert raw["documents"]["doc100"]["content"] == "Lưu trữ vector an toàn trên Windows"

        # Ensure no dangling .tmp files in directory
        tmp_files = list(tmp_path.glob("*.tmp*"))
        assert len(tmp_files) == 0

    def test_concurrent_persist_thread_safety(self, tmp_path):
        """Concurrent add_document and persist operations must not corrupt file or leave tmp files."""
        target_path = tmp_path / "concurrent_store.json"
        cfg = VectorStoreConfig(persist_path=str(target_path), auto_save=False)
        store = SemanticVectorStore(config=cfg)

        def worker(w_id: int):
            for i in range(20):
                store.add_document(f"doc_{w_id}_{i}", f"Worker {w_id} sample content iteration {i}")
                if i % 5 == 0:
                    store.persist()

        threads = [threading.Thread(target=worker, args=(w,)) for w in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        store.persist()
        assert target_path.exists()
        raw = json.loads(target_path.read_text(encoding="utf-8"))
        assert len(raw["documents"]) == 100

        # No temporary files left behind
        tmp_files = list(tmp_path.glob("*.tmp*"))
        assert len(tmp_files) == 0

    def test_default_persist_path_no_appdata_fallback(self, monkeypatch):
        """When AppData variables are absent, default persist path must resolve cleanly to fallback location."""
        monkeypatch.delenv("JARVIS_DATA_DIR", raising=False)
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        monkeypatch.delenv("APPDATA", raising=False)

        store = SemanticVectorStore()
        assert store.config.persist_path != ""
        assert Path(store.config.persist_path).name == "vector_store.json"

    def test_persist_replace_retry_and_cleanup_on_failure(self, tmp_path, monkeypatch):
        """Atomic replace must retry up to 5 times on OSError and clean up temp files on failure."""
        target_path = tmp_path / "store_retry.json"
        cfg = VectorStoreConfig(persist_path=str(target_path), auto_save=False)
        store = SemanticVectorStore(config=cfg)
        store.add_document("doc1", "Retry test content")

        attempts = 0
        real_replace = Path.replace

        def mock_replace(self_path, target):
            nonlocal attempts
            attempts += 1
            if attempts <= 2:
                raise OSError("WinError 5: Access is denied")
            return real_replace(self_path, target)

        monkeypatch.setattr(Path, "replace", mock_replace)

        # First test: transient failure for 2 attempts succeeds on 3rd
        assert store.save() is True
        assert target_path.exists()
        assert len(list(tmp_path.glob("*.tmp*"))) == 0

        # Second test: permanent failure after 5 attempts
        attempts = 0

        def mock_always_fail(self_path, target):
            nonlocal attempts
            attempts += 1
            raise OSError("WinError 5: Lock timeout")

        monkeypatch.setattr(Path, "replace", mock_always_fail)
        assert store.save() is False
        assert attempts == 5
        # Verify temp file was cleaned up in finally block
        assert len(list(tmp_path.glob("*.tmp*"))) == 0

