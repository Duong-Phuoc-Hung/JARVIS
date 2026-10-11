"""
jarvis/skills/auto_updater/__init__.py
=========================================
Auto-Update skill — kiểm tra và áp dụng bản cập nhật JARVIS với xác thực tính toàn vẹn SHA-256.

Đặc tả an toàn (Task 4: UPDATER-SAFETY-DESIGN):
- Sử dụng JarvisUpdater chuẩn làm backend mặc định (SHA-256 integrity verification, atomic replace, health check rollback).
- Fail-Closed: nếu chưa cấu hình manifest URL an toàn (JARVIS_UPDATE_MANIFEST_URL), trả về NOT_CONFIGURED.
- Tuyệt đối không cho phép silent bypass hoặc cài đặt binary/code không kiểm tra checksum.

Lệnh thoại:
  "JARVIS, có bản cập nhật nào không?"
  "Cập nhật JARVIS đi"
  "Xem lịch sử cập nhật"
  "Rollback về bản trước"
"""
from __future__ import annotations

import logging
import os
from typing import Any

from jarvis.updater.updater import (
    CHANNEL_STABLE,
    HEALTH_CHECK_FAIL,
    INTEGRITY_FAIL,
    NOT_CONFIGURED,
    ROLLBACK_OK,
    UP_TO_DATE,
    UPDATE_OK,
    JarvisUpdater,
)

log = logging.getLogger("jarvis.skills.auto_updater")

_UPDATER: Any | None = None


def _get_updater() -> Any:
    global _UPDATER
    if _UPDATER is None:
        manifest_url = os.environ.get("JARVIS_UPDATE_MANIFEST_URL", "").strip()
        channel = os.environ.get("JARVIS_UPDATE_CHANNEL", CHANNEL_STABLE).strip()
        _UPDATER = JarvisUpdater(manifest_url=manifest_url, channel=channel)
    return _UPDATER


def _is_newer_semver(new_v: str, old_v: str, updater: Any = None) -> bool:
    """Return True if new_v is strictly newer than old_v."""
    if updater is not None and hasattr(updater, "_is_newer"):
        try:
            return bool(updater._is_newer(new_v, old_v))
        except Exception:
            pass
    def parse_semver(v: str) -> tuple[int, int, int, int, tuple[tuple[int, int | str], ...]]:
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
    try:
        return parse_semver(new_v) > parse_semver(old_v)
    except Exception:
        return False


def execute(
    action: str = "check",
    confirm: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Auto-Update skill with SHA-256 integrity verification.

    Actions:
      check    - Kiểm tra có bản mới không (yêu cầu manifest URL an toàn)
      update   - Tải và cài bản mới nhất có kiểm tra SHA-256 (cần confirm=True)
      rollback - Quay lại bản trước (cần confirm=True)
      history  - Lịch sử kiểm tra cập nhật
      status   - Trạng thái hiện tại (version, sha256 check status)
    """
    act = action.lower().strip()
    updater = _get_updater()

    if act == "check":
        if hasattr(updater, "fetch_manifest"):
            manifest_url = getattr(updater, "manifest_url", "")
            if not manifest_url:
                msg = "⚠️ Updater chưa được cấu hình manifest URL an toàn (NOT_CONFIGURED). Cần cấu hình JARVIS_UPDATE_MANIFEST_URL."
                return {
                    "data": {
                        "text": msg,
                        "status": NOT_CONFIGURED,
                        "success": False,
                        "current": getattr(updater, "current_version", "0.0.0"),
                    },
                    "output": msg,
                }
            manifest = updater.fetch_manifest()
            if manifest is None:
                msg = "⚠️ Không thể tải manifest cập nhật (NOT_CONFIGURED/mạng lỗi)."
                return {
                    "data": {
                        "text": msg,
                        "status": NOT_CONFIGURED,
                        "success": False,
                        "current": getattr(updater, "current_version", "0.0.0"),
                    },
                    "output": msg,
                }
            newer = _is_newer_semver(manifest.version, getattr(updater, "current_version", "0.0.0"), updater)
            if newer:
                msg = (
                    f"🆕 **Có bản mới: v{manifest.version}!**\n"
                    f"📌 Phiên bản hiện tại: v{updater.current_version}\n"
                    f"🔒 SHA-256: `{manifest.sha256[:16]}...`\n"
                    f"📋 Ghi chú:\n{manifest.release_notes[:300] if manifest.release_notes else 'N/A'}\n\n"
                    f"💬 Nói *'cập nhật JARVIS đi'* hoặc gọi với `confirm=True` để cài bản mới."
                )
            else:
                msg = f"✅ JARVIS đang dùng bản mới nhất: **v{updater.current_version}**"
            return {
                "data": {
                    "text": msg,
                    "current": updater.current_version,
                    "latest": manifest.version,
                    "available": newer,
                    "sha256": manifest.sha256,
                    "status": "UPDATE_AVAILABLE" if newer else UP_TO_DATE,
                    "success": True,
                },
                "output": msg,
            }
        elif hasattr(updater, "check_for_update"):
            status = updater.check_for_update()
            if status.error:
                msg = f"⚠️ {status.error}"
            elif status.update_available:
                rel = status.release
                msg = (
                    f"🆕 **Có bản mới: v{status.latest_version}!**\n"
                    f"📌 Phiên bản hiện tại: v{status.current_version}\n"
                    f"📋 Tính năng mới:\n{rel.body[:300] if rel else 'N/A'}\n\n"
                    f"💬 Nói *'cập nhật JARVIS đi'* để cài bản mới."
                )
            else:
                msg = (
                    f"✅ JARVIS đang dùng bản mới nhất: **v{status.current_version}**\n"
                    f"🕐 Kiểm tra lúc: {status.checked_at}"
                )
            return {
                "data": {
                    "text": msg,
                    "current": status.current_version,
                    "latest": status.latest_version,
                    "available": status.update_available,
                    "success": True,
                },
                "output": msg,
            }

    elif act == "update":
        if not confirm:
            if hasattr(updater, "fetch_manifest"):
                manifest_url = getattr(updater, "manifest_url", "")
                if not manifest_url:
                    msg = "⚠️ Updater chưa được cấu hình manifest URL an toàn (NOT_CONFIGURED)."
                    return {"data": {"text": msg, "status": NOT_CONFIGURED, "success": False}, "output": msg}
                manifest = updater.fetch_manifest()
                if not manifest or not _is_newer_semver(manifest.version, getattr(updater, "current_version", "0.0.0"), updater):
                    msg = f"✅ Đang dùng bản mới nhất: v{getattr(updater, 'current_version', '')}"
                    return {"data": {"text": msg, "success": True, "status": UP_TO_DATE}, "output": msg}
                msg = (
                    f"⚠️ Sắp cập nhật lên **v{manifest.version}** (SHA-256 verified).\n"
                    f"Nói *'đồng ý cập nhật'* hoặc gọi với `confirm=True` để tiến hành."
                )
                return {"data": {"text": msg, "pending": True, "success": True, "target_version": manifest.version}, "output": msg}
            elif hasattr(updater, "check_for_update"):
                status = updater.check_for_update()
                if not status.update_available:
                    msg = f"✅ Đang dùng bản mới nhất: v{status.current_version}"
                    return {"data": {"text": msg, "success": True}, "output": msg}
                rel = status.release
                msg = (
                    f"⚠️ Sắp cập nhật lên **v{status.latest_version}**\n"
                    f"Nói *'đồng ý cập nhật'* hoặc gọi với `confirm=True` để tiến hành."
                )
                return {"data": {"text": msg, "pending": True, "success": True}, "output": msg}

        # Confirmed update
        if hasattr(updater, "check_and_apply"):
            result = updater.check_and_apply()
            if result.status == UPDATE_OK:
                msg = f"✅ Đã cập nhật thành công lên v{result.to_version} (SHA-256 Verified)"
                return {
                    "data": {
                        "text": msg,
                        "status": result.status,
                        "success": True,
                        "new_version": result.to_version,
                    },
                    "output": msg,
                }
            elif result.status == UP_TO_DATE:
                msg = f"✅ Đã là bản mới nhất (v{result.from_version}), không cần cập nhật."
                return {"data": {"text": msg, "status": result.status, "success": True}, "output": msg}
            elif result.status == INTEGRITY_FAIL:
                msg = f"❌ Lỗi tính toàn vẹn (SHA-256 mismatch): {result.error}. Cập nhật bị hủy bỏ để bảo vệ an toàn."
                return {"data": {"text": msg, "status": result.status, "success": False, "error": result.error}, "output": msg}
            elif result.status == NOT_CONFIGURED:
                msg = f"⚠️ Cập nhật thất bại: {result.error or 'Chưa cấu hình URL manifest (NOT_CONFIGURED)'}."
                return {"data": {"text": msg, "status": result.status, "success": False, "error": result.error}, "output": msg}
            elif result.status == HEALTH_CHECK_FAIL:
                msg = f"❌ Bản cập nhật không vượt qua kiểm tra sức khỏe; đã rollback: {result.error}"
                return {"data": {"text": msg, "status": result.status, "success": False, "error": result.error}, "output": msg}
            else:
                msg = f"❌ Cập nhật thất bại ({result.status}): {result.error}"
                return {"data": {"text": msg, "status": result.status, "success": False, "error": result.error}, "output": msg}
        else:
            msg = "⚠️ Updater chưa được cấu hình cơ chế kiểm tra SHA-256 an toàn (NOT_CONFIGURED)."
            return {"data": {"text": msg, "status": NOT_CONFIGURED, "success": False}, "output": msg}

    elif act == "rollback":
        if not confirm:
            msg = "⚠️ Rollback sẽ hoàn tác bản cập nhật mới nhất.\nGọi với `confirm=True` để xác nhận."
            return {"data": {"text": msg, "success": True, "pending": True}, "output": msg}
        if hasattr(updater, "rollback") and hasattr(updater, "install_dir"):
            target = updater.install_dir / "JARVIS.exe"
            backup = updater.install_dir / f"JARVIS.exe{getattr(updater, 'BACKUP_SUFFIX', '.backup')}"
            if not backup.exists():
                msg = "❌ Không tìm thấy bản backup để rollback."
                return {"data": {"text": msg, "success": False, "status": "NO_BACKUP"}, "output": msg}
            res = updater.rollback(target, backup)
            if res == ROLLBACK_OK:
                msg = "✅ Đã rollback thành công về bản backup trước đó."
                return {"data": {"text": msg, "success": True, "status": ROLLBACK_OK}, "output": msg}
            msg = f"❌ Rollback thất bại: {res}"
            return {"data": {"text": msg, "success": False, "status": res}, "output": msg}
        elif hasattr(updater, "rollback"):
            result = updater.rollback()
            msg = result.get("message", "")
            return {"data": {**result, "text": msg}, "output": msg}

    elif act == "history":
        from jarvis.workers.auto_updater import AutoUpdater
        history = AutoUpdater(is_mock=True).get_update_history()
        if not history:
            msg = "📋 Chưa có lịch sử kiểm tra cập nhật nào."
        else:
            lines = ["📋 **Lịch sử cập nhật JARVIS:**\n"]
            for i, entry in enumerate(history[:5]):
                icon = "🆕" if entry.get("update_available") else "✅"
                applied = " (đã cài)" if entry.get("applied") else ""
                lines.append(f"{i+1}. {icon} {entry.get('checked_at', '')} — v{entry.get('current_version', '')} → v{entry.get('latest_version', '')}{applied}")
            msg = "\n".join(lines)
        return {"data": {"text": msg, "history": history, "success": True}, "output": msg}

    elif act == "status":
        current = getattr(updater, "current_version", "")
        if not current:
            try:
                import jarvis
                current = jarvis.__version__
            except Exception:
                current = "0.0.0"
        manifest_url = getattr(updater, "manifest_url", "")
        channel = getattr(updater, "channel", CHANNEL_STABLE)
        from jarvis.workers.auto_updater import AutoUpdater
        history = AutoUpdater(is_mock=True).get_update_history()
        last_check = history[0]["checked_at"] if history else "Chưa kiểm tra"
        configured = bool(manifest_url)
        msg = (
            f"🤖 **JARVIS Version Manager**\n"
            f"📌 Phiên bản hiện tại: **v{current}**\n"
            f"🛡️ Tính toàn vẹn SHA-256: {'ĐÃ CẤU HÌNH' if configured else 'CHƯA CẤU HÌNH (Fail-Closed)'}\n"
            f"📡 Kênh: {channel}\n"
            f"🕐 Lần kiểm tra cuối: {last_check}\n"
            f"📊 Số lần đã kiểm tra: {len(history)}"
        )
        return {
            "data": {
                "text": msg,
                "current": current,
                "configured": configured,
                "channel": channel,
                "checks": len(history),
                "success": True,
            },
            "output": msg,
        }

    else:
        msg = f"Hành động '{act}' không hỗ trợ. Thử: check, update, rollback, history, status."
        return {"data": {"text": msg, "success": False}, "output": msg}
