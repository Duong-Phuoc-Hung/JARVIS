"""
jarvis/updater/updater.py
==========================
D-13: Updater with Integrity Check + Rollback

Provides:
- Channel-based update manifest fetching (stable / beta)
- SHA-256 integrity verification before applying
- Atomic file replacement (Windows-safe rename)
- Automatic rollback on health-check failure
- Fail-Closed: any verification failure aborts update

Per AGENTS.md: no silent fallback; missing/invalid manifest → NOT_CONFIGURED.
Per AGENTS.md Atomic Persistence: write to .tmp file, replace atomically.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("jarvis.updater")

# ── Public constants ─────────────────────────────────────────────────────────
CHANNEL_STABLE = "stable"
CHANNEL_BETA   = "beta"

UPDATE_OK          = "UPDATE_OK"
UP_TO_DATE         = "UP_TO_DATE"
ROLLBACK_OK        = "ROLLBACK_OK"
ROLLBACK_FAILED    = "ROLLBACK_FAILED"
INTEGRITY_FAIL     = "INTEGRITY_FAIL"
DOWNLOAD_FAIL      = "DOWNLOAD_FAIL"
MANIFEST_NOT_FOUND = "MANIFEST_NOT_FOUND"
HEALTH_CHECK_FAIL  = "HEALTH_CHECK_FAIL"
NOT_CONFIGURED     = "NOT_CONFIGURED"


@dataclass
class UpdateManifest:
    version: str
    channel: str
    download_url: str
    sha256: str
    release_notes: str = ""
    min_required_version: str = ""
    published_at: str = ""


@dataclass
class UpdateResult:
    status: str
    from_version: str = ""
    to_version: str = ""
    error: str = ""
    backup_path: str = ""
    manifest: UpdateManifest | None = None

    @property
    def ok(self) -> bool:
        return self.status in (UPDATE_OK, UP_TO_DATE, ROLLBACK_OK)


class JarvisUpdater:
    """
    Atomic updater for JARVIS binary with SHA-256 integrity verification and rollback.

    Usage::

        updater = JarvisUpdater(
            manifest_url="https://releases.example.com/jarvis/manifest.json",
            install_dir=Path("C:/Program Files/JARVIS"),
            channel="stable",
        )
        result = updater.check_and_apply()
        if result.status == UPDATE_OK:
            print(f"Updated to {result.to_version}")
    """

    BACKUP_SUFFIX = ".backup"
    MAX_ROLLBACK_RETRIES = 5

    def __init__(
        self,
        manifest_url: str = "",
        install_dir: Path | None = None,
        channel: str = CHANNEL_STABLE,
        current_version: str = "",
        http_client: Any | None = None,
        health_check_fn: Any | None = None,
    ) -> None:
        self.manifest_url = manifest_url
        self.install_dir = install_dir or Path(".")
        self.channel = channel
        self.http_client = http_client
        self._lock = threading.Lock()

        # Current version from jarvis package or caller
        if current_version:
            self.current_version = current_version
        else:
            try:
                import jarvis
                self.current_version = jarvis.__version__
            except Exception:
                self.current_version = "0.0.0"

        # Optional health-check callable: () -> bool
        self.health_check_fn = health_check_fn

    # ── Manifest ─────────────────────────────────────────────────────────────

    def fetch_manifest(self) -> UpdateManifest | None:
        """
        Fetch update manifest from manifest_url.
        Returns None (Fail-Closed) if URL empty, network fails, or JSON invalid.
        """
        if not self.manifest_url:
            log.warning("Updater: manifest_url not configured → NOT_CONFIGURED")
            return None

        try:
            if self.http_client is not None:
                resp = self.http_client.get(self.manifest_url, timeout=15)
            else:
                import urllib.request
                with urllib.request.urlopen(self.manifest_url, timeout=15) as r:
                    resp = type("R", (), {"text": r.read().decode("utf-8"), "status_code": r.status})()

            if hasattr(resp, "status_code") and resp.status_code != 200:
                log.error("Updater: manifest fetch HTTP %s", resp.status_code)
                return None

            data: dict = json.loads(resp.text if hasattr(resp, "text") else resp.read())

            # Support both flat manifest and channel-keyed manifest
            if self.channel in data:
                data = data[self.channel]

            required = {"version", "download_url", "sha256"}
            missing = required - data.keys()
            if missing:
                log.error("Updater: manifest missing fields: %s", missing)
                return None

            return UpdateManifest(
                version=data["version"],
                channel=self.channel,
                download_url=data["download_url"],
                sha256=data["sha256"],
                release_notes=data.get("release_notes", ""),
                min_required_version=data.get("min_required_version", ""),
                published_at=data.get("published_at", ""),
            )
        except Exception as exc:
            log.error("Updater: manifest fetch error: %s", exc)
            return None

    # ── Integrity ─────────────────────────────────────────────────────────────

    @staticmethod
    def verify_sha256(file_path: Path, expected_sha256: str) -> bool:
        """Verify file SHA-256. Returns False (Fail-Closed) on mismatch or error."""
        try:
            h = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            actual = h.hexdigest().lower()
            expected = expected_sha256.lower()
            if actual != expected:
                log.error(
                    "Updater: SHA-256 mismatch. expected=%s actual=%s", expected, actual
                )
                return False
            return True
        except Exception as exc:
            log.error("Updater: integrity check error: %s", exc)
            return False

    # ── Download ──────────────────────────────────────────────────────────────

    def _download_to_tmp(self, url: str, dest_dir: Path) -> Path | None:
        """Download file to a temp path inside dest_dir. Returns None on failure."""
        tmp_name = f".tmp.update.{threading.get_ident()}.{time.time_ns()}"
        tmp_path = dest_dir / tmp_name
        try:
            if self.http_client is not None:
                resp = self.http_client.get(url, stream=True, timeout=120)
                with open(tmp_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
            else:
                import urllib.request
                urllib.request.urlretrieve(url, tmp_path)
            return tmp_path
        except Exception as exc:
            log.error("Updater: download error: %s", exc)
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            return None

    # ── Backup & Rollback ─────────────────────────────────────────────────────

    def _backup_current(self, target: Path) -> Path | None:
        """Backup current binary to .backup path. Returns backup path or None."""
        if not target.exists():
            return None
        backup = target.with_suffix(self.BACKUP_SUFFIX)
        try:
            shutil.copy2(target, backup)
            log.info("Updater: backed up %s → %s", target.name, backup.name)
            return backup
        except Exception as exc:
            log.error("Updater: backup failed: %s", exc)
            return None

    def rollback(self, target: Path, backup: Path) -> str:
        """
        Restore backup to target. Returns ROLLBACK_OK or ROLLBACK_FAILED.
        Uses retry loop for Windows file locking (WinError 5).
        """
        for attempt in range(1, self.MAX_ROLLBACK_RETRIES + 1):
            try:
                backup.replace(target)
                log.info("Updater: rollback OK on attempt %d", attempt)
                return ROLLBACK_OK
            except OSError as e:
                log.warning("Updater: rollback attempt %d failed: %s", attempt, e)
                time.sleep(0.02 * attempt)

        log.error("Updater: rollback failed after %d attempts", self.MAX_ROLLBACK_RETRIES)
        return ROLLBACK_FAILED

    # ── Atomic Apply ──────────────────────────────────────────────────────────

    def _atomic_replace(self, src: Path, dest: Path) -> bool:
        """Atomically replace dest with src. Retry on Windows file locking."""
        for attempt in range(1, 6):
            try:
                src.replace(dest)
                return True
            except OSError as e:
                log.warning("Updater: replace attempt %d: %s", attempt, e)
                time.sleep(0.02 * attempt)
        return False

    # ── Main Update Flow ──────────────────────────────────────────────────────

    def check_and_apply(self, target_filename: str = "JARVIS.exe") -> UpdateResult:
        """
        Full update cycle:
          1. Fetch manifest (Fail-Closed if unavailable)
          2. Compare versions (skip if up-to-date)
          3. Download to temp file
          4. SHA-256 integrity verify
          5. Backup current binary
          6. Atomic replace
          7. Health check (rollback on failure)

        Returns UpdateResult with status field.
        """
        with self._lock:
            return self._run_update(target_filename)

    def _run_update(self, target_filename: str) -> UpdateResult:
        manifest = self.fetch_manifest()
        if manifest is None:
            return UpdateResult(status=NOT_CONFIGURED, error="Manifest unavailable")

        if self._versions_equal(self.current_version, manifest.version):
            log.info("Updater: already up-to-date (%s)", self.current_version)
            return UpdateResult(
                status=UP_TO_DATE,
                from_version=self.current_version,
                to_version=manifest.version,
                manifest=manifest,
            )

        log.info(
            "Updater: update available %s → %s", self.current_version, manifest.version
        )

        target = self.install_dir / target_filename
        tmp = self._download_to_tmp(manifest.download_url, self.install_dir)
        if tmp is None:
            return UpdateResult(
                status=DOWNLOAD_FAIL,
                from_version=self.current_version,
                to_version=manifest.version,
                error="Download failed",
                manifest=manifest,
            )

        try:
            if not self.verify_sha256(tmp, manifest.sha256):
                tmp.unlink(missing_ok=True)
                return UpdateResult(
                    status=INTEGRITY_FAIL,
                    from_version=self.current_version,
                    to_version=manifest.version,
                    error="SHA-256 mismatch — update aborted",
                    manifest=manifest,
                )

            backup = self._backup_current(target)
            backup_path = str(backup) if backup else ""

            if not self._atomic_replace(tmp, target):
                tmp.unlink(missing_ok=True)
                return UpdateResult(
                    status=DOWNLOAD_FAIL,
                    from_version=self.current_version,
                    to_version=manifest.version,
                    error="Atomic replace failed",
                    manifest=manifest,
                )

            # Health check with rollback
            if self.health_check_fn is not None:
                try:
                    healthy = self.health_check_fn()
                except Exception:
                    healthy = False

                if not healthy:
                    log.error("Updater: health check failed — rolling back")
                    rollback_status = ROLLBACK_FAILED
                    if backup:
                        rollback_status = self.rollback(target, backup)
                    return UpdateResult(
                        status=HEALTH_CHECK_FAIL,
                        from_version=self.current_version,
                        to_version=manifest.version,
                        error="Health check failed; rollback: " + rollback_status,
                        backup_path=backup_path,
                        manifest=manifest,
                    )

            log.info("Updater: update applied successfully → %s", manifest.version)
            return UpdateResult(
                status=UPDATE_OK,
                from_version=self.current_version,
                to_version=manifest.version,
                backup_path=backup_path,
                manifest=manifest,
            )

        finally:
            try:
                if tmp and tmp.exists():
                    tmp.unlink(missing_ok=True)
            except Exception:
                pass

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _versions_equal(v1: str, v2: str) -> bool:
        """Normalise and compare version strings."""
        def norm(v: str) -> tuple:
            return tuple(int(x) for x in v.strip().lstrip("v").split(".")[:3] if x.isdigit())
        try:
            return norm(v1) == norm(v2)
        except Exception:
            return v1.strip() == v2.strip()
