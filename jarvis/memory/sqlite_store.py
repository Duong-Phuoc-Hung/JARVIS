"""
jarvis/memory/sqlite_store.py
=============================
Thread-safe persistent SQLite storage for JARVIS memory layer.
Manages:
  - User facts, profile, habits, and preferences (`facts` table).
  - Episodic interaction telemetry and outcome history (`episodes` table).
  - Observed behavioral patterns (`user_habits` table).
  - Multi-step Task DAG execution history (`task_history` table).
  - Browser cookie/session/local-storage persistence (`browser_sessions` table).
  - Reusable learned autonomous workflows (`learned_workflows` table).
Enforces SQLite WAL mode (Write-Ahead Logging) and concurrent connection safety.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

logger = logging.getLogger("jarvis.memory.sqlite_store")


class SQLiteMemoryStore:
    """
    Persistent SQLite Memory Engine with WAL journaling and thread-safe operations.
    """

    def __init__(
        self,
        db_path: Union[str, Path] = "logs/memory.db",
        timeout: float = 10.0,
    ) -> None:
        self.db_path = Path(db_path)
        # Ensure parent directory exists (e.g. logs/)
        if self.db_path.parent and not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.timeout = timeout
        self._lock = threading.RLock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Creates a configured connection to the SQLite database."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=self.timeout,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self) -> None:
        """Initializes database schema with WAL mode and necessary tables/indexes."""
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    # 1. Facts Table: Semantic facts, user preferences, habits, projects
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS facts (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            category TEXT NOT NULL CHECK(category IN ('profile', 'preference', 'habit', 'project', 'system', 'general')),
                            key TEXT NOT NULL,
                            value TEXT NOT NULL,
                            confidence REAL NOT NULL DEFAULT 1.0,
                            source TEXT NOT NULL DEFAULT 'user_explicit',
                            created_at DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime')),
                            updated_at DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime')),
                            access_count INTEGER NOT NULL DEFAULT 0,
                            last_accessed_at DATETIME,
                            UNIQUE(category, key)
                        );
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_facts_key ON facts(key);")

                    # 2. Episodes Table: Full history of commands, intents, and outcomes
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS episodes (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            session_id TEXT NOT NULL DEFAULT '',
                            timestamp DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime')),
                            trigger_type TEXT NOT NULL DEFAULT 'VOICE',
                            command TEXT NOT NULL,
                            intent TEXT NOT NULL DEFAULT 'none',
                            outcome TEXT NOT NULL DEFAULT '',
                            success BOOLEAN NOT NULL DEFAULT 1,
                            latency_ms REAL NOT NULL DEFAULT 0.0,
                            error_message TEXT,
                            metadata TEXT
                        );
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_episodes_timestamp ON episodes(timestamp);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_episodes_session ON episodes(session_id);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_episodes_intent ON episodes(intent);")

                    # 3. User Habits Table: Usage frequencies and aggregated observations
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS user_habits (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            habit_key TEXT NOT NULL UNIQUE,
                            frequency INTEGER NOT NULL DEFAULT 1,
                            last_observed DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime')),
                            habit_type TEXT NOT NULL DEFAULT 'general',
                            typical_hour INTEGER,
                            metadata TEXT
                        );
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_habits_key ON user_habits(habit_key);")

                    # 4. Task History Table: Autonomous ReAct Planner execution records
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS task_history (
                            task_id TEXT PRIMARY KEY,
                            goal TEXT NOT NULL,
                            plan_dag_json TEXT NOT NULL,
                            execution_trace_json TEXT NOT NULL DEFAULT '[]',
                            status TEXT NOT NULL DEFAULT 'completed',
                            duration_seconds REAL NOT NULL DEFAULT 0.0,
                            created_at DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime')),
                            completed_at DATETIME
                        );
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_history_status ON task_history(status);")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_history_created ON task_history(created_at);")

                    # 5. Browser Sessions Table: Persistent cookie/storage per domain
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS browser_sessions (
                            domain TEXT PRIMARY KEY,
                            cookies_json TEXT NOT NULL,
                            local_storage_json TEXT NOT NULL DEFAULT '{}',
                            user_agent TEXT NOT NULL DEFAULT '',
                            updated_at DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime'))
                        );
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_browser_sessions_domain ON browser_sessions(domain);")

                    # 6. Learned Workflows Table: Dynamically synthesized or recorded workflows
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS learned_workflows (
                            workflow_id TEXT PRIMARY KEY,
                            name TEXT NOT NULL,
                            description TEXT NOT NULL DEFAULT '',
                            trigger_pattern TEXT NOT NULL DEFAULT '',
                            steps_template_json TEXT NOT NULL DEFAULT '[]',
                            usage_count INTEGER NOT NULL DEFAULT 1,
                            last_used_at DATETIME NOT NULL DEFAULT (DATETIME('now', 'localtime'))
                        );
                    """)
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_learned_workflows_pattern ON learned_workflows(trigger_pattern);")
            finally:
                conn.close()

    def get_journal_mode(self) -> str:
        """Returns the current SQLite journal mode (should be 'wal')."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute("PRAGMA journal_mode;")
                row = cursor.fetchone()
                return str(row[0]).lower() if row else ""
            finally:
                conn.close()

    # ── Facts & Preferences API ──────────────────────────────────────────────

    def store_fact(
        self,
        key: str,
        value: str,
        category: str = "general",
        confidence: float = 1.0,
        source: str = "user_explicit",
    ) -> bool:
        """
        Stores or updates a semantic fact using SQLite UPSERT.
        Categories: 'profile', 'preference', 'habit', 'project', 'system', 'general'
        """
        if not key or not str(key).strip() or not value or not str(value).strip():
            return False

        cat = category.lower().strip()
        if cat not in ('profile', 'preference', 'habit', 'project', 'system', 'general'):
            cat = "general"

        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute("""
                        INSERT INTO facts (category, key, value, confidence, source, created_at, updated_at, access_count)
                        VALUES (?, ?, ?, ?, ?, DATETIME('now', 'localtime'), DATETIME('now', 'localtime'), 0)
                        ON CONFLICT(category, key) DO UPDATE SET
                            value = excluded.value,
                            confidence = excluded.confidence,
                            source = excluded.source,
                            updated_at = DATETIME('now', 'localtime'),
                            access_count = facts.access_count + 1;
                    """, (cat, key.strip(), value.strip(), confidence, source))
                return True
            except Exception as e:
                logger.error("Failed to store fact %s:%s: %s", cat, key, e)
                return False
            finally:
                conn.close()

    def get_fact(self, key: str, category: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieves a fact by key (and optional category).
        Updates access count and last_accessed_at timestamp.
        """
        clean_key = key.strip()
        with self._lock:
            conn = self._get_connection()
            try:
                if category:
                    cursor = conn.execute(
                        "SELECT * FROM facts WHERE category = ? AND key = ?",
                        (category.lower().strip(), clean_key),
                    )
                else:
                    cursor = conn.execute(
                        "SELECT * FROM facts WHERE key = ? ORDER BY updated_at DESC LIMIT 1",
                        (clean_key,),
                    )
                row = cursor.fetchone()
                if not row:
                    return None

                result = dict(row)
                # Update access count
                with conn:
                    conn.execute(
                        "UPDATE facts SET access_count = access_count + 1, last_accessed_at = DATETIME('now', 'localtime') WHERE id = ?",
                        (result["id"],),
                    )
                result["access_count"] += 1
                return result
            finally:
                conn.close()

    def list_facts(
        self,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Lists stored facts filtered by category, ordered by updated_at descending."""
        with self._lock:
            conn = self._get_connection()
            try:
                if category:
                    cursor = conn.execute(
                        "SELECT * FROM facts WHERE category = ? ORDER BY updated_at DESC LIMIT ?",
                        (category.lower().strip(), limit),
                    )
                else:
                    cursor = conn.execute(
                        "SELECT * FROM facts ORDER BY updated_at DESC LIMIT ?",
                        (limit,),
                    )
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

    def delete_fact(self, key: str, category: Optional[str] = None) -> bool:
        """Deletes a fact by key and optional category."""
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    if category:
                        cursor = conn.execute(
                            "DELETE FROM facts WHERE category = ? AND key = ?",
                            (category.lower().strip(), key.strip()),
                        )
                    else:
                        cursor = conn.execute(
                            "DELETE FROM facts WHERE key = ?",
                            (key.strip(),),
                        )
                    return cursor.rowcount > 0
            finally:
                conn.close()

    # ── Episodic Interaction Log API ─────────────────────────────────────────

    def log_episode(
        self,
        command: str,
        intent: str,
        outcome: str,
        success: bool = True,
        session_id: str = "",
        trigger_type: str = "VOICE",
        latency_ms: float = 0.0,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Logs an interaction episode to the SQLite database.
        Returns the generated episode ID.
        """
        meta_str = json.dumps(metadata or {}, ensure_ascii=False)
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    cursor = conn.execute("""
                        INSERT INTO episodes (
                            session_id, trigger_type, command, intent, outcome,
                            success, latency_ms, error_message, metadata, timestamp
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, DATETIME('now', 'localtime'))
                    """, (
                        session_id,
                        trigger_type,
                        command.strip(),
                        intent.strip(),
                        outcome.strip(),
                        1 if success else 0,
                        latency_ms,
                        error_message,
                        meta_str,
                    ))
                    return cursor.lastrowid
            except Exception as e:
                logger.error("Failed to log episode: %s", e)
                return -1
            finally:
                conn.close()

    def get_episodes(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Queries episodes within optional date ranges."""
        with self._lock:
            conn = self._get_connection()
            try:
                query = "SELECT * FROM episodes"
                params: List[Any] = []
                conditions = []

                if start_date:
                    conditions.append("date(timestamp) >= date(?)")
                    params.append(start_date)
                if end_date:
                    conditions.append("date(timestamp) <= date(?)")
                    params.append(end_date)

                if conditions:
                    query += " WHERE " + " AND ".join(conditions)

                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)

                cursor = conn.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

    def get_today_episodes(self) -> List[Dict[str, Any]]:
        """Retrieves all episodes logged today (local time)."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute("""
                    SELECT * FROM episodes
                    WHERE date(timestamp) = date('now', 'localtime')
                    ORDER BY timestamp ASC
                """)
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

    # Alias for API compatibility
    list_episodes = get_episodes

    # ── User Habits & Behavioral Aggregates API ──────────────────────────────

    def record_habit(
        self,
        habit_key: str,
        habit_type: str = "general",
        typical_hour: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Records or updates user habit observation frequency."""
        meta_str = json.dumps(metadata or {}, ensure_ascii=False)
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute("""
                        INSERT INTO user_habits (habit_key, frequency, last_observed, habit_type, typical_hour, metadata)
                        VALUES (?, 1, DATETIME('now', 'localtime'), ?, ?, ?)
                        ON CONFLICT(habit_key) DO UPDATE SET
                            frequency = user_habits.frequency + 1,
                            last_observed = DATETIME('now', 'localtime'),
                            typical_hour = COALESCE(excluded.typical_hour, user_habits.typical_hour),
                            metadata = excluded.metadata;
                    """, (habit_key.strip(), habit_type, typical_hour, meta_str))
            except Exception as e:
                logger.error("Failed to record habit %s: %s", habit_key, e)
            finally:
                conn.close()

    def get_habits(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns user habits ordered by frequency descending."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    "SELECT * FROM user_habits ORDER BY frequency DESC LIMIT ?",
                    (limit,),
                )
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

    # ── Autonomous Task History API ──────────────────────────────────────────

    def record_task_execution(
        self,
        task_id: str,
        goal: str,
        dag_json: Optional[Union[str, Dict[str, Any]]] = None,
        status: str = "completed",
        duration: float = 0.0,
        duration_seconds: Optional[float] = None,
        plan_dag_json: Optional[Union[str, Dict[str, Any]]] = None,
        execution_trace: Optional[Union[str, List[Any], Dict[str, Any]]] = None,
        execution_trace_json: Optional[Union[str, List[Any], Dict[str, Any]]] = None,
        created_at: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> bool:
        """
        Records or updates a task execution record in the `task_history` table.
        Supports flexible argument naming for compatibility.
        """
        actual_dag = plan_dag_json if plan_dag_json is not None else (dag_json or "{}")
        if isinstance(actual_dag, (dict, list)):
            dag_str = json.dumps(actual_dag, ensure_ascii=False)
        else:
            dag_str = str(actual_dag)

        actual_trace = execution_trace_json if execution_trace_json is not None else (execution_trace or "[]")
        if isinstance(actual_trace, (dict, list)):
            trace_str = json.dumps(actual_trace, ensure_ascii=False)
        else:
            trace_str = str(actual_trace)

        actual_dur = float(duration_seconds if duration_seconds is not None else duration)

        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute("""
                        INSERT INTO task_history (
                            task_id, goal, plan_dag_json, execution_trace_json,
                            status, duration_seconds, created_at, completed_at
                        ) VALUES (
                            ?, ?, ?, ?, ?, ?,
                            COALESCE(?, DATETIME('now', 'localtime')),
                            COALESCE(?, DATETIME('now', 'localtime'))
                        )
                        ON CONFLICT(task_id) DO UPDATE SET
                            goal = excluded.goal,
                            plan_dag_json = excluded.plan_dag_json,
                            execution_trace_json = excluded.execution_trace_json,
                            status = excluded.status,
                            duration_seconds = excluded.duration_seconds,
                            completed_at = excluded.completed_at;
                    """, (
                        str(task_id).strip(),
                        str(goal).strip(),
                        dag_str,
                        trace_str,
                        str(status).strip(),
                        actual_dur,
                        created_at,
                        completed_at,
                    ))
                return True
            except Exception as e:
                logger.error("Failed to record task execution %s: %s", task_id, e)
                return False
            finally:
                conn.close()

    def get_task_history(
        self,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieves task execution history ordered by created_at descending."""
        with self._lock:
            conn = self._get_connection()
            try:
                if status:
                    cursor = conn.execute(
                        "SELECT * FROM task_history WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                        (status.strip(), limit),
                    )
                else:
                    cursor = conn.execute(
                        "SELECT * FROM task_history ORDER BY created_at DESC LIMIT ?",
                        (limit,),
                    )
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a specific task execution by task_id."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    "SELECT * FROM task_history WHERE task_id = ?",
                    (str(task_id).strip(),),
                )
                row = cursor.fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    # ── Browser Session Persistence API ──────────────────────────────────────

    @staticmethod
    def _normalize_domain(domain_or_url: str) -> str:
        """Normalizes URL or domain string into a clean hostname key."""
        d = domain_or_url.strip().lower()
        if "://" in d:
            d = urlparse(d).netloc
        d = d.split(":")[0]
        return d or "default"

    def save_browser_session(
        self,
        domain: str,
        cookies: Union[str, List[Dict[str, Any]]],
        storage: Optional[Union[str, Dict[str, Any]]] = None,
        local_storage: Optional[Union[str, Dict[str, Any]]] = None,
        user_agent: str = "",
    ) -> bool:
        """Saves browser cookies, local storage, and user agent per domain."""
        norm_domain = self._normalize_domain(domain)
        if isinstance(cookies, (list, dict)):
            cookies_str = json.dumps(cookies, ensure_ascii=False)
        else:
            cookies_str = str(cookies or "[]")

        actual_storage = local_storage if local_storage is not None else (storage or "{}")
        if isinstance(actual_storage, (dict, list)):
            storage_str = json.dumps(actual_storage, ensure_ascii=False)
        else:
            storage_str = str(actual_storage)

        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute("""
                        INSERT INTO browser_sessions (domain, cookies_json, local_storage_json, user_agent, updated_at)
                        VALUES (?, ?, ?, ?, DATETIME('now', 'localtime'))
                        ON CONFLICT(domain) DO UPDATE SET
                            cookies_json = excluded.cookies_json,
                            local_storage_json = excluded.local_storage_json,
                            user_agent = excluded.user_agent,
                            updated_at = DATETIME('now', 'localtime');
                    """, (norm_domain, cookies_str, storage_str, user_agent))
                return True
            except Exception as e:
                logger.error("Failed to save browser session for %s: %s", norm_domain, e)
                return False
            finally:
                conn.close()

    def get_browser_session(self, domain: str) -> Optional[Dict[str, Any]]:
        """Loads stored browser session for a domain."""
        norm_domain = self._normalize_domain(domain)
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    "SELECT cookies_json, local_storage_json, user_agent, updated_at FROM browser_sessions WHERE domain = ?",
                    (norm_domain,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                try:
                    c_data = json.loads(row["cookies_json"])
                except Exception:
                    c_data = row["cookies_json"]
                try:
                    s_data = json.loads(row["local_storage_json"])
                except Exception:
                    s_data = row["local_storage_json"]
                return {
                    "domain": norm_domain,
                    "cookies": c_data,
                    "local_storage": s_data,
                    "user_agent": row["user_agent"],
                    "updated_at": row["updated_at"],
                }
            finally:
                conn.close()

    def delete_browser_session(self, domain: str) -> bool:
        """Removes stored browser session for a domain."""
        norm_domain = self._normalize_domain(domain)
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    cursor = conn.execute(
                        "DELETE FROM browser_sessions WHERE domain = ?",
                        (norm_domain,),
                    )
                    return cursor.rowcount > 0
            finally:
                conn.close()

    def list_browser_sessions(self) -> List[str]:
        """Lists all domains with saved browser sessions."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute("SELECT domain FROM browser_sessions ORDER BY domain ASC")
                return [str(row[0]) for row in cursor.fetchall()]
            finally:
                conn.close()

    # ── Learned Workflows API ────────────────────────────────────────────────

    def save_learned_workflow(
        self,
        workflow_id: str,
        name: str,
        description: str = "",
        trigger_pattern: str = "",
        steps_template: Optional[Union[str, Dict[str, Any], List[Any]]] = None,
        steps_template_json: Optional[Union[str, Dict[str, Any], List[Any]]] = None,
    ) -> bool:
        """Stores or updates a learned reusable workflow."""
        actual_template = steps_template_json if steps_template_json is not None else (steps_template or "[]")
        if isinstance(actual_template, (dict, list)):
            template_str = json.dumps(actual_template, ensure_ascii=False)
        else:
            template_str = str(actual_template)

        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute("""
                        INSERT INTO learned_workflows (
                            workflow_id, name, description, trigger_pattern,
                            steps_template_json, usage_count, last_used_at
                        ) VALUES (?, ?, ?, ?, ?, 1, DATETIME('now', 'localtime'))
                        ON CONFLICT(workflow_id) DO UPDATE SET
                            name = excluded.name,
                            description = excluded.description,
                            trigger_pattern = excluded.trigger_pattern,
                            steps_template_json = excluded.steps_template_json,
                            usage_count = learned_workflows.usage_count + 1,
                            last_used_at = DATETIME('now', 'localtime');
                    """, (
                        str(workflow_id).strip(),
                        str(name).strip(),
                        str(description).strip(),
                        str(trigger_pattern).strip(),
                        template_str,
                    ))
                return True
            except Exception as e:
                logger.error("Failed to save learned workflow %s: %s", workflow_id, e)
                return False
            finally:
                conn.close()

    def get_learned_workflows(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves learned workflows ordered by usage_count descending."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    "SELECT * FROM learned_workflows ORDER BY usage_count DESC, last_used_at DESC LIMIT ?",
                    (limit,),
                )
                results = []
                for row in cursor.fetchall():
                    item = dict(row)
                    try:
                        item["steps_template"] = json.loads(item["steps_template_json"])
                    except Exception:
                        item["steps_template"] = item["steps_template_json"]
                    results.append(item)
                return results
            finally:
                conn.close()

    def get_learned_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single learned workflow by workflow_id."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    "SELECT * FROM learned_workflows WHERE workflow_id = ?",
                    (str(workflow_id).strip(),),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                item = dict(row)
                try:
                    item["steps_template"] = json.loads(item["steps_template_json"])
                except Exception:
                    item["steps_template"] = item["steps_template_json"]
                return item
            finally:
                conn.close()

    def increment_workflow_usage(self, workflow_id: str) -> bool:
        """Increments usage counter and updates last_used_at timestamp."""
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    cursor = conn.execute("""
                        UPDATE learned_workflows
                        SET usage_count = usage_count + 1,
                            last_used_at = DATETIME('now', 'localtime')
                        WHERE workflow_id = ?
                    """, (str(workflow_id).strip(),))
                    return cursor.rowcount > 0
            except Exception as e:
                logger.error("Failed to increment workflow usage for %s: %s", workflow_id, e)
                return False
            finally:
                conn.close()

    def close(self) -> None:
        """No-op for connection-per-call architecture, provided for lifecycle symmetry."""
        pass
