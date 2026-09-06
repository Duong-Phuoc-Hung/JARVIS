"""
tests/unit/test_memory_concurrency_tier1.py
===========================================
TDD Unit test suite for P2-12: Memory Concurrency and Data Integrity Hardening (Tier 1).
Stress-tests SemanticVectorStore, SQLiteMemoryStore, and MemoryManager under 30+ concurrent threads.
Verifies zero dictionary iteration mutations, zero SQLite lockouts, zero lost writes, and atomic persistence.
"""
from __future__ import annotations

import concurrent.futures
import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from jarvis.memory.sqlite_store import SQLiteMemoryStore
from jarvis.memory.vector_store import SemanticVectorStore, VectorStoreConfig
from jarvis.memory.manager import MemoryManager


class TestSemanticVectorStoreConcurrency:
    """Stress tests for SemanticVectorStore thread safety and persistence integrity."""

    def test_concurrent_30_threads_add_document_no_lost_writes(self, tmp_path: Path) -> None:
        """
        Slice 1: 30 threads simultaneously index documents with auto_save=True.
        Must not raise RuntimeError: dictionary changed size during iteration.
        Must write exactly 30 documents to disk without file corruption.
        """
        persist_file = tmp_path / "vector_store.json"
        config = VectorStoreConfig(
            persist_path=str(persist_file),
            auto_save=True,
        )
        store = SemanticVectorStore(config=config)

        errors: list[Exception] = []

        def worker(idx: int) -> None:
            try:
                doc_id = f"doc_{idx:03d}"
                content = f"JARVIS tài liệu ghi chú số {idx} về kế hoạch tự động hóa và phát triển phần mềm"
                ok = store.add_document(doc_id, content, category="notes")
                if not ok:
                    raise ValueError(f"Failed to add document {doc_id}")
            except Exception as e:
                errors.append(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            futures = [executor.submit(worker, i) for i in range(30)]
            concurrent.futures.wait(futures)

        # No thread should raise an exception
        assert not errors, f"Encountered concurrency errors: {errors}"
        assert store.size() == 30

        # Verify disk persistence integrity
        assert persist_file.exists()
        raw_json = json.loads(persist_file.read_text(encoding="utf-8"))
        saved_docs = raw_json.get("documents", {})
        assert len(saved_docs) == 30, f"Expected 30 saved docs on disk, but found {len(saved_docs)} (lost write detected!)"

    def test_concurrent_interleaved_writes_and_searches_no_dict_mutation_error(self, tmp_path: Path) -> None:
        """
        Slice 2: Interleaved concurrent operations (writes, searches, deletes)
        across 30 threads without dictionary changed size during iteration.
        """
        persist_file = tmp_path / "vector_interleaved.json"
        config = VectorStoreConfig(persist_path=str(persist_file), auto_save=False)
        store = SemanticVectorStore(config=config)

        for i in range(10):
            store.add_document(f"seed_{i}", f"Tài liệu cơ bản số {i} hệ thống JARVIS")

        errors: list[Exception] = []
        stop_event = threading.Event()

        def writer(idx: int) -> None:
            try:
                for j in range(5):
                    store.add_document(f"dyn_{idx}_{j}", f"Dữ liệu động luồng {idx} bước {j} ghi chú tự trị")
                    time.sleep(0.002)
            except Exception as e:
                errors.append(e)

        def searcher() -> None:
            try:
                while not stop_event.is_set():
                    results = store.search("tự trị JARVIS", k=5)
                    assert isinstance(results, list)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def deleter() -> None:
            try:
                for i in range(5):
                    store.delete_document(f"seed_{i}")
                    time.sleep(0.003)
            except Exception as e:
                errors.append(e)

        threads: list[threading.Thread] = []
        for i in range(15):
            threads.append(threading.Thread(target=writer, args=(i,)))
        for _ in range(10):
            threads.append(threading.Thread(target=searcher))
        for _ in range(5):
            threads.append(threading.Thread(target=deleter))

        for t in threads:
            t.start()

        time.sleep(0.15)
        stop_event.set()

        for t in threads:
            t.join()

        assert not errors, f"Encountered errors during interleaved concurrent access: {errors}"

    def test_save_is_thread_safe_and_atomic(self, tmp_path: Path) -> None:
        """
        Slice 3: save() takes a thread-safe snapshot under lock and replaces file atomically.
        """
        persist_file = tmp_path / "vector_atomic.json"
        config = VectorStoreConfig(persist_path=str(persist_file), auto_save=False)
        store = SemanticVectorStore(config=config)

        # Seed with 100 documents
        for i in range(100):
            store.add_document(f"doc_{i}", f"Tài liệu số {i} kiểm tra atomic persistence")

        errors: list[Exception] = []

        def continuous_mutator() -> None:
            try:
                for i in range(50):
                    store.add_document(f"new_{i}", f"Nội dung mới {i}")
                    if i % 2 == 0:
                        store.delete_document(f"doc_{i}")
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        def continuous_saver() -> None:
            try:
                for _ in range(20):
                    store.save()
                    time.sleep(0.002)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=continuous_mutator)
        t2 = threading.Thread(target=continuous_saver)
        t3 = threading.Thread(target=continuous_saver)
        t1.start()
        t2.start()
        t3.start()
        t1.join()
        t2.join()
        t3.join()

        assert not errors, f"Errors during concurrent save: {errors}"
        assert persist_file.exists()
        raw = json.loads(persist_file.read_text(encoding="utf-8"))
        assert "documents" in raw


class TestSQLiteMemoryStoreConcurrencyTier1:
    """Slice 4: SQLiteMemoryStore 30 concurrent worker stress test."""

    def test_sqlite_30_concurrent_threads_read_write_integrity(self, tmp_path: Path) -> None:
        db_file = tmp_path / "sqlite_stress.db"
        store = SQLiteMemoryStore(db_path=db_file, timeout=15.0)

        errors: list[Exception] = []

        def worker_fact(idx: int) -> None:
            try:
                ok = store.store_fact(key=f"user_pref_{idx}", value=f"setting_{idx}", category="preferences")
                assert ok is True
                fact = store.get_fact(f"user_pref_{idx}", category="preferences")
                assert fact is not None
                assert fact["value"] == f"setting_{idx}"
            except Exception as e:
                errors.append(e)

        def worker_episode(idx: int) -> None:
            try:
                ep_id = store.log_episode(
                    command=f"lệnh người dùng {idx}",
                    intent="system_control",
                    outcome="Thành công",
                    success=True,
                )
                assert isinstance(ep_id, int) and ep_id > 0
            except Exception as e:
                errors.append(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            fact_futures = [executor.submit(worker_fact, i) for i in range(15)]
            episode_futures = [executor.submit(worker_episode, i) for i in range(15)]
            concurrent.futures.wait(fact_futures + episode_futures)

        assert not errors, f"SQLite concurrency errors: {errors}"

        facts = store.list_facts(category="preferences", limit=100)
        assert len(facts) == 15
        episodes = store.get_today_episodes()
        assert len(episodes) == 15


class TestMemoryManagerConcurrencyTier1:
    """Slice 5: High-level MemoryManager 30 concurrent worker stress test."""

    def test_memory_manager_concurrent_session_and_facts(self, tmp_path: Path) -> None:
        db_file = tmp_path / "mgr_stress.db"
        manager = MemoryManager(db_path=db_file, max_session_turns=10)

        errors: list[Exception] = []

        def worker(idx: int) -> None:
            try:
                # Store fact
                manager.store_fact(f"key_{idx}", f"val_{idx}", category="profile")
                # Add session turn
                manager.add_session_turn(role="user", content=f"Tin nhắn {idx}")
                # Query context
                ctx = manager.get_session_context()
                assert isinstance(ctx, str)
            except Exception as e:
                errors.append(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            futures = [executor.submit(worker, i) for i in range(30)]
            concurrent.futures.wait(futures)

        assert not errors, f"MemoryManager concurrency errors: {errors}"
        facts = manager.list_facts(category="profile", limit=50)
        assert len(facts) == 30
