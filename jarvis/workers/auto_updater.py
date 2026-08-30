"""
jarvis/workers/auto_updater.py
================================
Auto-Update Daemon: tự động kiểm tra và cài bản JARVIS mới từ GitHub Releases.

Chu kỳ: kiểm tra mỗi 6 giờ.
Hỗ trợ: rollback về bản trước nếu bản mới lỗi.

Lệnh thoại:
  "JARVIS, kiểm tra bản cập nhật"
  "Cập nhật JARVIS đi"
  "Rollback về bản trước"
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

log = logging.getLogger("jarvis.workers.auto_updater")

_REPO = "Duong-Phuoc-Hung/JARVIS"
_GITHUB_API = f"https://api.github.com/repos/{_REPO}/releases/latest"
_CHECK_INTERVAL_S = 6 * 3600   # 6 giờ
_VERSION_FILE = Path("jarvis/__init__.py")
_BACKUP_DIR = Path("backups/versions")
_UPDATE_LOG: Path | None = None  # resolved at runtime


@dataclass
class ReleaseInfo:
    tag: str
    name: str
    body: str
    published_at: str
    assets: list[dict[str, Any]] = field(default_factory=list)
    download_url: str = ""
    is_prerelease: bool = False


@dataclass
class UpdateStatus:
    current_version: str
    latest_version: str
    update_available: bool
    release: ReleaseInfo | None = None
    checked_at: str = ""
    error: str = ""


class AutoUpdater:
    """
    Auto-Update Daemon for JARVIS.
    Checks GitHub Releases API, downloads and applies updates.
    """

    def __init__(
        self,
        repo: str = _REPO,
        check_interval_s: int = _CHECK_INTERVAL_S,
        auto_apply: bool = False,
        is_mock: bool = False,
    ) -> None:
        self.repo = repo
        self.check_interval_s = check_interval_s
        self.auto_apply = auto_apply
        self.is_mock = is_mock
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_status: UpdateStatus | None = None
        _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        Path("logs").mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # Version detection
    # ------------------------------------------------------------------

    def get_current_version(self) -> str:
        """Read __version__ from jarvis/__init__.py."""
        try:
            text = _VERSION_FILE.read_text(encoding="utf-8")
            for line in text.splitlines():
                if "__version__" in line and "=" in line:
                    return line.split("=")[-1].strip().strip('"').strip("'")
        except Exception:
            pass
        return "0.0.0"

    # ------------------------------------------------------------------
    # GitHub API
    # ------------------------------------------------------------------

    def fetch_latest_release(self) -> ReleaseInfo | None:
        """Fetch latest release info from GitHub API."""
        if self.is_mock:
            return ReleaseInfo(
                tag="v3.1.0",
                name="JARVIS v3.1.0 - Browser Control",
                body="- Added Browser CDP Controller\n- Auto-Update Daemon\n- +30 new tests",
                published_at="2026-08-29T00:00:00Z",
                download_url="https://github.com/mock/releases/JARVIS_v3.1.0.zip",
            )
        try:
            req = Request(
                f"https://api.github.com/repos/{self.repo}/releases/latest",
                headers={"Accept": "application/vnd.github+json", "User-Agent": "JARVIS-AutoUpdater"},
            )
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            assets = data.get("assets", [])
            download_url = ""
            for a in assets:
                if a["name"].endswith(".zip") or a["name"].endswith(".exe"):
                    download_url = a["browser_download_url"]
                    break
            return ReleaseInfo(
                tag=data.get("tag_name", ""),
                name=data.get("name", ""),
                body=data.get("body", "")[:500],
                published_at=data.get("published_at", ""),
                assets=assets,
                download_url=download_url,
                is_prerelease=data.get("prerelease", False),
            )
        except URLError as exc:
            log.warning("GitHub API unavailable: %s", exc)
            return None
        except Exception as exc:
            log.error("Fetch release error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Check & Apply
    # ------------------------------------------------------------------

    def check_for_update(self) -> UpdateStatus:
        """Check if a newer version is available. Returns UpdateStatus."""
        import datetime
        current = self.get_current_version()
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        release = self.fetch_latest_release()

        if not release:
            status = UpdateStatus(
                current_version=current,
                latest_version=current,
                update_available=False,
                checked_at=ts,
                error="Không thể kết nối GitHub API.",
            )
        else:
            latest_clean = release.tag.lstrip("v")
            update_available = self._version_newer(latest_clean, current)
            status = UpdateStatus(
                current_version=current,
                latest_version=latest_clean,
                update_available=update_available,
                release=release,
                checked_at=ts,
            )

        self._last_status = status
        self._save_update_log(status)
        log.info("Update check: current=%s, latest=%s, available=%s", current, status.latest_version, status.update_available)
        return status

    def _version_newer(self, new: str, old: str) -> bool:
        """Return True if new > old using semver comparison."""
        try:
            def to_tuple(v: str):
                return tuple(int(x) for x in v.split(".")[:3])
            return to_tuple(new) > to_tuple(old)
        except ValueError:
            return new != old

    def apply_update(self, release: ReleaseInfo) -> dict[str, Any]:
        """Download and apply update (git pull in dev mode)."""
        if self.is_mock:
            return {"success": True, "message": f"Mock: đã cập nhật lên {release.tag}", "new_version": release.tag}

        log.info("Applying update to %s...", release.tag)
        try:
            # Backup current version first
            self._backup_current()
            # In development mode: git pull
            result = subprocess.run(
                ["git", "pull", "origin", "main"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                # Install new deps
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"],
                    timeout=120
                )
                self._save_update_log(self._last_status, applied=True)
                return {"success": True, "message": f"✅ Đã cập nhật lên {release.tag}", "new_version": release.tag, "git_output": result.stdout[:200]}
            else:
                return {"success": False, "message": f"❌ Git pull thất bại: {result.stderr[:200]}"}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Timeout khi cập nhật."}
        except Exception as exc:
            log.error("Apply update error: %s", exc)
            return {"success": False, "message": str(exc)}

    def rollback(self) -> dict[str, Any]:
        """Rollback to the previous backup version."""
        if self.is_mock:
            return {"success": True, "message": "Mock: rollback thành công"}

        backups = sorted(_BACKUP_DIR.glob("backup_*.txt"), reverse=True)
        if not backups:
            return {"success": False, "message": "Không có backup nào để rollback."}

        try:
            latest_backup = backups[0]
            backup_tag = latest_backup.stem.replace("backup_", "")
            result = subprocess.run(
                ["git", "checkout", backup_tag],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return {"success": True, "message": f"✅ Đã rollback về {backup_tag}"}
            return {"success": False, "message": f"Rollback thất bại: {result.stderr[:100]}"}
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    def _backup_current(self) -> None:
        """Record current version tag as backup marker."""
        current = self.get_current_version()
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup_file = _BACKUP_DIR / f"backup_v{current}_{ts}.txt"
        backup_file.write_text(f"version={current}\nbackup_time={ts}\n")
        log.info("Backup marker: %s", backup_file)

    def _save_update_log(self, status: UpdateStatus | None, applied: bool = False) -> None:
        """Append update check to history log."""
        if status is None:
            return
        try:
            history = []
            if _UPDATE_LOG.exists():
                history = json.loads(_UPDATE_LOG.read_text(encoding="utf-8"))
            entry = {
                "checked_at": status.checked_at,
                "current_version": status.current_version,
                "latest_version": status.latest_version,
                "update_available": status.update_available,
                "applied": applied,
                "error": status.error,
            }
            history.insert(0, entry)
            _UPDATE_LOG.write_text(json.dumps(history[:30], indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            log.debug("Save update log error: %s", exc)

    def get_update_history(self) -> list[dict]:
        """Return last N update check records."""
        try:
            if _UPDATE_LOG.exists():
                return json.loads(_UPDATE_LOG.read_text(encoding="utf-8"))
        except Exception:
            pass
        return []

    def get_last_status(self) -> UpdateStatus | None:
        return self._last_status

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    def start_background_checker(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._check_loop, daemon=True, name="AutoUpdater")
        self._thread.start()
        log.info("Auto-updater background checker started (interval=%ds)", self.check_interval_s)

    def stop(self) -> None:
        self._running = False

    def _check_loop(self) -> None:
        while self._running:
            try:
                status = self.check_for_update()
                if status.update_available and self.auto_apply and status.release:
                    log.info("Auto-applying update %s...", status.latest_version)
                    self.apply_update(status.release)
            except Exception as exc:
                log.error("Auto-updater loop error: %s", exc)
            time.sleep(self.check_interval_s)


__all__ = ["AutoUpdater", "ReleaseInfo", "UpdateStatus"]
