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
_UPDATE_LOG: Path | None = None  # resolved at runtime or overridden in tests
_SAVE_LOCK = threading.Lock()


def _get_update_log_path() -> Path:
    global _UPDATE_LOG
    if _UPDATE_LOG is None:
        from jarvis.core.paths import data_path
        _UPDATE_LOG = data_path("logs", "update_history.json")
    return _UPDATE_LOG


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
        if auto_apply:
            log.warning("AutoUpdater: legacy auto_apply is disabled for security (lacks SHA-256 integrity check; use JarvisUpdater).")
        self.auto_apply = False  # Disabled for security: unverified background git pull is prohibited
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

    @staticmethod
    def _parse_semver(v: str) -> tuple[int, int, int, int, tuple[tuple[int, int | str], ...]]:
        clean = v.strip().lstrip("vV").split("+", 1)[0]
        core, separator, prerelease = clean.partition("-")
        parts = core.split(".")
        nums = []
        for p in parts[:3]:
            digits = ""
            for char in p:
                if char.isdigit():
                    digits += char
                else:
                    break
            nums.append(int(digits) if digits else 0)
        while len(nums) < 3:
            nums.append(0)
        if not separator:
            return (nums[0], nums[1], nums[2], 1, ())
        prerelease_key: list[tuple[int, int | str]] = []
        for identifier in prerelease.split("."):
            if identifier.isdigit():
                prerelease_key.append((0, int(identifier)))
            else:
                prerelease_key.append((1, identifier.lower()))
        return (nums[0], nums[1], nums[2], 0, tuple(prerelease_key))

    def _version_newer(self, new: str, old: str) -> bool:
        """Return True if new > old using semver comparison."""
        try:
            return self._parse_semver(new) > self._parse_semver(old)
        except Exception:
            return False

    def apply_update(self, release: ReleaseInfo) -> dict[str, Any]:
        """Download and apply update (git pull in dev mode)."""
        if self.is_mock:
            return {"success": True, "message": f"Mock: đã cập nhật lên {release.tag}", "new_version": release.tag}

        log.info("Applying update to %s...", release.tag)
        if self._last_status is None:
            import datetime
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            current = self.get_current_version()
            self._last_status = UpdateStatus(
                current_version=current,
                latest_version=release.tag.lstrip("v"),
                update_available=True,
                release=release,
                checked_at=ts,
            )
        try:
            # Backup current version first
            self._backup_current()
            # In development mode: git pull
            _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            result = subprocess.run(
                ["git", "pull", "origin", "main"],
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60,
                creationflags=_cflags,
            )
            if result.returncode == 0:
                # Install new deps
                _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                pip_res = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=120,
                    creationflags=_cflags,
                )
                if pip_res.returncode != 0:
                    err_msg = f"❌ Cài đặt dependencies thất bại (exit {pip_res.returncode}): {pip_res.stderr[:200]}"
                    log.error(err_msg)
                    self._save_update_log(self._last_status, applied=False, error_override=err_msg)
                    return {"success": False, "message": err_msg, "error": err_msg}
                self._save_update_log(self._last_status, applied=True)
                return {"success": True, "message": f"✅ Đã cập nhật lên {release.tag}", "new_version": release.tag, "git_output": result.stdout[:200]}
            else:
                err_msg = f"❌ Git pull thất bại: {result.stderr[:200]}"
                self._save_update_log(self._last_status, applied=False, error_override=err_msg)
                return {"success": False, "message": err_msg, "error": err_msg}
        except subprocess.TimeoutExpired:
            err_msg = "Timeout khi cập nhật."
            self._save_update_log(self._last_status, applied=False, error_override=err_msg)
            return {"success": False, "message": err_msg, "error": err_msg}
        except Exception as exc:
            err_msg = str(exc)
            log.error("Apply update error: %s", exc)
            self._save_update_log(self._last_status, applied=False, error_override=err_msg)
            return {"success": False, "message": err_msg, "error": err_msg}

    def rollback(self) -> dict[str, Any]:
        """Rollback to the previous backup version."""
        if self.is_mock:
            return {"success": True, "message": "Mock: rollback thành công"}

        backups = sorted(_BACKUP_DIR.glob("backup_*.txt"), reverse=True)
        if not backups:
            return {"success": False, "message": "Không có backup nào để rollback."}

        try:
            latest_backup = backups[0]
            backup_tag = ""
            try:
                lines = latest_backup.read_text(encoding="utf-8").splitlines()
                for line in lines:
                    if line.startswith("version="):
                        backup_tag = line.split("=", 1)[1].strip()
                        break
            except Exception:
                pass
            if not backup_tag:
                backup_tag = latest_backup.stem.replace("backup_", "")

            _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            result = subprocess.run(
                ["git", "checkout", backup_tag],
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30,
                creationflags=_cflags,
            )
            if result.returncode == 0:
                return {"success": True, "message": f"✅ Đã rollback về {backup_tag}"}
            err_msg = f"Rollback thất bại: {result.stderr[:100]}"
            return {"success": False, "message": err_msg, "error": err_msg}
        except Exception as exc:
            err_msg = str(exc)
            return {"success": False, "message": err_msg, "error": err_msg}

    def _backup_current(self) -> None:
        """Record current version tag as backup marker."""
        current = self.get_current_version()
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup_file = _BACKUP_DIR / f"backup_v{current}_{ts}.txt"
        backup_file.write_text(f"version={current}\nbackup_time={ts}\n")
        log.info("Backup marker: %s", backup_file)

    def _save_update_log(self, status: UpdateStatus | None, applied: bool = False, error_override: str = "") -> None:
        """Append update check to history log atomically."""
        if status is None:
            return
        log_path = _get_update_log_path()
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with _SAVE_LOCK:
                history = []
                if log_path.exists():
                    try:
                        history = json.loads(log_path.read_text(encoding="utf-8"))
                        if not isinstance(history, list):
                            history = []
                    except Exception:
                        history = []
                entry = {
                    "checked_at": status.checked_at,
                    "current_version": status.current_version,
                    "latest_version": status.latest_version,
                    "update_available": status.update_available,
                    "applied": applied,
                    "error": error_override or status.error,
                }
                history.insert(0, entry)
                data_str = json.dumps(history[:30], indent=2, ensure_ascii=False)

                # Windows atomic persistence: temp file + retry replace + cleanup
                tmp_name = f".tmp.{threading.get_ident()}.{time.time_ns()}"
                tmp_path = log_path.parent / tmp_name
                try:
                    tmp_path.write_text(data_str, encoding="utf-8")
                    for attempt in range(1, 6):
                        try:
                            tmp_path.replace(log_path)
                            break
                        except OSError as err:
                            if attempt == 5:
                                raise err
                            time.sleep(0.02 * attempt)
                finally:
                    if tmp_path.exists():
                        try:
                            tmp_path.unlink(missing_ok=True)
                        except Exception:
                            pass
        except Exception as exc:
            log.debug("Save update log error: %s", exc)

    def get_update_history(self) -> list[dict]:
        """Return last N update check records."""
        try:
            log_path = _get_update_log_path()
            if log_path.exists():
                data = json.loads(log_path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
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
                    log.warning("Legacy auto_apply is permanently disabled for security. Skipping automatic unverified update.")
            except Exception as exc:
                log.error("Auto-updater loop error: %s", exc)
            time.sleep(self.check_interval_s)


__all__ = ["AutoUpdater", "ReleaseInfo", "UpdateStatus"]
