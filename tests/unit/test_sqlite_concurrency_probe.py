"""
tests/unit/test_sqlite_concurrency_probe.py
===========================================
Empirical Stress Probe for Task 9: SQLITE-CONCURRENCY-PROBE.
Tests multi-connection concurrent reads and writes on Windows SQLite without
relying on speculative deductions.

Verifies:
1. Multiple distinct SQLiteMemoryStore instances (independent Python locks, separate connections)
   concurrently writing and reading from the same SQLite DB file on Windows.
2. Cross-subsystem concurrency: BrowserSessionManager and SQLiteMemoryStore concurrently
   accessing the same SQLite file.
3. Raw multi-connection transaction contention under SQLite WAL mode with busy timeout.
4. Continuous heavy reader queries during rapid concurrent write bursts.
"""
from __future__ import annotations

import concurrent.futures
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from jarvis.browser.session import BrowserSessionManager
from jarvis.memory.sqlite_store import SQLiteMemoryStore


class TestSQLiteWindowsConcurrencyProbe:
    """
    Stress-probe test suite evaluating SQLite multi-connection concurrency
    specifically under Windows filesystem semantics.
    """

    def test_multiple_distinct_store_instances_concurrent_writes(self, tmp_path: Path) -> None:
        """
        Probe 1: 10 independent SQLiteMemoryStore instances pointing to the same file.
        Because each instance has its own private self._lock, Python threading.RLock
        does NOT protect against cross-instance concurrency.
        All concurrency serialization must be handled correctly by SQLite WAL mode and busy handler.
        """
        db_path = tmp_path / "cross_instance_stress.db"

        # Initialize schema with primary instance
        primary_store = SQLiteMemoryStore(db_path=db_path, timeout=10.0)
        assert primary_store.get_journal_mode() == "wal"

        num_instances = 10
        stores = [SQLiteMemoryStore(db_path=db_path, timeout=10.0) for _ in range(num_instances)]

        errors: list[Exception] = []
        operations_per_worker = 30
        total_workers = 20

        def worker(worker_id: int) -> None:
            # Distribute workers across the 10 distinct store instances
            store = stores[worker_id % num_instances]
            try:
                for op_idx in range(operations_per_worker):
                    key = f"key_w{worker_id}_op{op_idx}"
                    val = f"val_{worker_id}_{op_idx}"

                    # Write fact
                    ok = store.store_fact(key=key, value=val, category="probe_test")
                    if not ok:
                        raise RuntimeError(f"store_fact returned False for {key}")

                    # Write episode
                    ep_id = store.log_episode(
                        command=f"cmd {worker_id} {op_idx}",
                        intent="probe_intent",
                        outcome="success",
                        success=True,
                    )
                    if ep_id <= 0:
                        raise RuntimeError(f"log_episode failed for worker {worker_id}")

                    # Read fact back
                    fact = store.get_fact(key=key, category="probe_test")
                    if fact is None or fact["value"] != val:
                        raise ValueError(f"Fact read mismatch for {key}: got {fact}")

                    # Micro sleep to interleave transactions
                    time.sleep(0.001)
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=total_workers) as executor:
            futures = [executor.submit(worker, w_id) for w_id in range(total_workers)]
            concurrent.futures.wait(futures)

        assert not errors, f"Cross-instance SQLite concurrency errors encountered: {errors}"

        # Verify final record counts
        all_facts = primary_store.list_facts(category="probe_test", limit=total_workers * operations_per_worker + 100)
        assert len(all_facts) == total_workers * operations_per_worker

    def test_concurrent_browser_session_and_memory_store(self, tmp_path: Path) -> None:
        """
        Probe 2: Concurrent access between BrowserSessionManager and SQLiteMemoryStore
        on the exact same SQLite database file.
        """
        db_path = tmp_path / "shared_browser_memory.db"

        # Prime memory store
        mem_store = SQLiteMemoryStore(db_path=db_path, timeout=10.0)
        browser_mgr = BrowserSessionManager(
            storage_dir=tmp_path / "browser_sessions",
            db_path=str(db_path),
        )

        errors: list[Exception] = []
        stop_event = threading.Event()

        def memory_writer() -> None:
            try:
                for i in range(40):
                    mem_store.store_fact(f"m_key_{i}", f"m_val_{i}", category="shared_test")
                    mem_store.log_episode(
                        command=f"mem cmd {i}",
                        intent="intent",
                        outcome="done",
                        success=True,
                    )
                    time.sleep(0.002)
            except Exception as e:
                errors.append(e)

        def browser_writer() -> None:
            try:
                for i in range(40):
                    domain = f"example{i % 5}.com"
                    browser_mgr.save_session(
                        domain=domain,
                        cookies=[{"name": f"c_{i}", "value": f"v_{i}", "domain": domain}],
                        local_storage={f"k_{i}": f"v_{i}"},
                        local_storage_origin=f"https://{domain}",
                        user_agent=f"JARVIS-Agent/{i}",
                    )
                    time.sleep(0.002)
            except Exception as e:
                errors.append(e)

        def continuous_reader() -> None:
            try:
                while not stop_event.is_set():
                    facts = mem_store.list_facts(category="shared_test", limit=10)
                    assert isinstance(facts, list)
                    sess = browser_mgr.load_session("example0.com")
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        t_mem = threading.Thread(target=memory_writer)
        t_brow = threading.Thread(target=browser_writer)
        t_read = threading.Thread(target=continuous_reader)

        t_mem.start()
        t_brow.start()
        t_read.start()

        t_mem.join()
        t_brow.join()
        stop_event.set()
        t_read.join()

        assert not errors, f"Errors in concurrent BrowserSession + MemoryStore: {errors}"

    def test_raw_multi_connection_contention_and_busy_handler(self, tmp_path: Path) -> None:
        """
        Probe 3: Stress test raw sqlite3 connections executing concurrent transactions
        under WAL mode to evaluate if Windows filesystem locking causes 'database is locked'.
        """
        db_path = str(tmp_path / "raw_concurrency.db")

        # Setup schema and WAL mode
        init_conn = sqlite3.connect(db_path)
        init_conn.execute("PRAGMA journal_mode = WAL;")
        init_conn.execute("PRAGMA synchronous = NORMAL;")
        init_conn.execute("CREATE TABLE test_counter (id INTEGER PRIMARY KEY, counter INTEGER);")
        init_conn.execute("INSERT INTO test_counter VALUES (1, 0);")
        init_conn.commit()
        init_conn.close()

        num_threads = 16
        increments_per_thread = 25
        errors: list[Exception] = []

        def worker() -> None:
            try:
                conn = sqlite3.connect(db_path, timeout=10.0, isolation_level=None)
                try:
                    for _ in range(increments_per_thread):
                        conn.execute("BEGIN IMMEDIATE;")
                        cursor = conn.cursor()
                        cursor.execute("SELECT counter FROM test_counter WHERE id = 1;")
                        val = cursor.fetchone()[0]
                        cursor.execute("UPDATE test_counter SET counter = ? WHERE id = 1;", (val + 1,))
                        conn.execute("COMMIT;")
                        time.sleep(0.001)
                finally:
                    conn.close()
            except Exception as exc:
                errors.append(exc)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker) for _ in range(num_threads)]
            concurrent.futures.wait(futures)

        assert not errors, f"Raw multi-connection contention failed with errors: {errors}"

        # Verify final counter equals total increments
        check_conn = sqlite3.connect(db_path)
        cursor = check_conn.cursor()
        cursor.execute("SELECT counter FROM test_counter WHERE id = 1;")
        final_val = cursor.fetchone()[0]
        check_conn.close()

        assert final_val == num_threads * increments_per_thread
