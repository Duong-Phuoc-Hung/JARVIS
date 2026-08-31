"""
jarvis/skills/telemetry.py
============================
Runtime skill-invocation telemetry, stored separately from packaged skill
manifests (jarvis/skills/<skill>/metadata.json).

Packaged metadata.json files describe a skill's static definition and must
never be rewritten just to record that it was invoked. This module is the
one place invocation counters/latency get persisted: a single JSON file
outside the source package tree (default location resolved via
jarvis.core.paths.data_path(), which is not modified by this change),
independently injectable so tests can point it at a temporary path.

No network/database dependency. Writes are atomic (write-to-temp +
os.replace) and every operation degrades gracefully (logs a warning,
never raises) if the store is missing, corrupt, or the data directory is
unavailable/read-only.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.skills.telemetry")

DEFAULT_TELEMETRY_FILENAME = "skills_telemetry.json"


def _default_telemetry_path() -> Path:
    """Resolve the unscoped default telemetry store path under JARVIS's writable data dir."""
    from jarvis.core.paths import data_path

    return data_path("skills", DEFAULT_TELEMETRY_FILENAME)


def default_telemetry_path_for(skills_dir: str | Path) -> Path:
    """
    Resolve a telemetry store path scoped to a specific skills_dir.

    Different skill trees -- in particular, a fresh temporary directory
    created by each test run -- must never share, and therefore never
    cross-pollute, runtime telemetry counters. The real packaged
    jarvis/skills/ tree resolves to the same scoped file across process
    restarts (same input path -> same hash), so persistence for the real
    app is unaffected; a brand-new temp directory always gets a fresh file.
    """
    from jarvis.core.paths import data_path

    resolved = str(Path(skills_dir).resolve())
    digest = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:16]
    return data_path("skills", f"telemetry_{digest}.json")


class SkillTelemetryStore:
    """
    Thread-safe, file-backed runtime telemetry store for skill invocations.
    Deliberately independent of the packaged skill manifest tree.
    """

    def __init__(self, store_path: str | Path | None = None) -> None:
        self.store_path = Path(store_path) if store_path is not None else _default_telemetry_path()
        self._lock = threading.Lock()

    def _load_all_locked(self) -> dict[str, dict[str, Any]]:
        """Load the full telemetry map. Caller must hold self._lock. Never raises."""
        if not self.store_path.exists():
            return {}
        try:
            raw = self.store_path.read_text(encoding="utf-8")
            if not raw.strip():
                return {}
            data = json.loads(raw)
            if not isinstance(data, dict):
                logger.warning("Telemetry store %s did not contain a JSON object; ignoring.", self.store_path)
                return {}
            return data
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.warning(
                "Telemetry store %s is corrupt or unreadable (%s); treating as empty.", self.store_path, exc
            )
            return {}

    def _write_all_locked(self, data: dict[str, dict[str, Any]]) -> bool:
        """
        Atomically write the full telemetry map. Caller must hold self._lock.
        Never raises -- returns False on failure so record_invocation() can
        still hand back the updated in-memory counters even when disk
        persistence is unavailable (e.g. a read-only data directory).
        """
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
            tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp_path, self.store_path)
            return True
        except (OSError, TypeError, ValueError) as exc:
            # OSError: disk/permission failure (tmp write or the same-directory
            # atomic replace never touches self.store_path until the write
            # already fully succeeded, so a failure here can never destroy a
            # previously-valid store). TypeError/ValueError: guards json.dumps()
            # itself in case a non-JSON-serializable value ever ends up in
            # `data` -- this must degrade gracefully too, never propagate out
            # of a telemetry write and interrupt skill execution.
            logger.warning("Failed to persist skill telemetry to %s: %s", self.store_path, exc)
            return False

    def load_all(self) -> dict[str, dict[str, Any]]:
        """Return the full telemetry map for all skills. Never raises."""
        with self._lock:
            return self._load_all_locked()

    def get(self, skill_name: str) -> dict[str, Any] | None:
        """Return the stored telemetry dict for one skill, or None if absent/unavailable."""
        with self._lock:
            return self._load_all_locked().get(skill_name)

    def record_invocation(
        self,
        skill_name: str,
        success: bool,
        latency_ms: float,
        seed: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Atomically increment and persist telemetry counters for one skill
        invocation. The read-modify-write cycle is guarded by an in-process
        lock, so concurrent invocations of the same or different skills
        against one SkillTelemetryStore instance cannot lose updates.
        Returns the updated counters for this skill regardless of whether
        the disk write itself succeeded.

        `seed` is used only the first time this store has no existing entry
        for `skill_name` -- it bootstraps the counters from there (e.g. a
        skill's pre-existing counters already baked into an old-style
        packaged metadata.json) instead of starting at zero, so migrating a
        skill onto this store never looks like its history was deleted.
        """
        with self._lock:
            data = self._load_all_locked()
            if skill_name in data:
                stats = data[skill_name]
            elif seed is not None:
                stats = {
                    "invocation_count": int(seed.get("invocation_count", 0)),
                    "success_count": int(seed.get("success_count", 0)),
                    "failure_count": int(seed.get("failure_count", 0)),
                    "total_latency_ms": float(seed.get("total_latency_ms", 0.0)),
                }
            else:
                stats = {
                    "invocation_count": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "total_latency_ms": 0.0,
                }
            stats["invocation_count"] = int(stats.get("invocation_count", 0)) + 1
            if success:
                stats["success_count"] = int(stats.get("success_count", 0)) + 1
            else:
                stats["failure_count"] = int(stats.get("failure_count", 0)) + 1
            stats["total_latency_ms"] = float(stats.get("total_latency_ms", 0.0)) + latency_ms
            stats["updated_at"] = time.time()

            data[skill_name] = stats
            self._write_all_locked(data)
            return dict(stats)
