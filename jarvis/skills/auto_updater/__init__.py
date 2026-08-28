"""
jarvis/skills/auto_updater/__init__.py
=========================================
Auto-Update skill — kiểm tra và áp dụng bản cập nhật JARVIS mới.

Lệnh thoại:
  "JARVIS, có bản cập nhật nào không?"
  "Cập nhật JARVIS đi"
  "Xem lịch sử cập nhật"
  "Rollback về bản trước"
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

log = logging.getLogger("jarvis.skills.auto_updater")

_UPDATER: Optional[Any] = None


def _get_updater():
    global _UPDATER
    if _UPDATER is None:
        from jarvis.workers.auto_updater import AutoUpdater
        _UPDATER = AutoUpdater(is_mock=False)
    return _UPDATER


def execute(
    action: str = "check",
    confirm: bool = False,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Auto-Update skill.

    Actions:
      check    - Kiểm tra có bản mới không (không cập nhật)
      update   - Tải và cài bản mới nhất (cần confirm=True)
      rollback - Quay lại bản trước (cần confirm=True)
      history  - Lịch sử kiểm tra cập nhật
      status   - Trạng thái hiện tại (version, last check)
    """
    act = action.lower().strip()
    updater = _get_updater()

    if act == "check":
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
        status = updater.check_for_update()
        if not status.update_available:
            msg = "✅ Đã là bản mới nhất, không cần cập nhật."
            return {"data": {"text": msg, "success": True}, "output": msg}
        result = updater.apply_update(status.release)
        msg = result.get("message", "")
        return {"data": {**result, "text": msg}, "output": msg}

    elif act == "rollback":
        if not confirm:
            msg = "⚠️ Rollback sẽ hoàn tác bản cập nhật mới nhất.\nGọi với `confirm=True` để xác nhận."
            return {"data": {"text": msg, "success": True}, "output": msg}
        result = updater.rollback()
        msg = result.get("message", "")
        return {"data": {**result, "text": msg}, "output": msg}

    elif act == "history":
        history = updater.get_update_history()
        if not history:
            msg = "📋 Chưa có lịch sử kiểm tra cập nhật nào."
        else:
            lines = ["📋 **Lịch sử cập nhật JARVIS:**\n"]
            for i, entry in enumerate(history[:5]):
                icon = "🆕" if entry.get("update_available") else "✅"
                applied = " (đã cài)" if entry.get("applied") else ""
                lines.append(f"{i+1}. {icon} {entry['checked_at']} — v{entry['current_version']} → v{entry['latest_version']}{applied}")
            msg = "\n".join(lines)
        return {"data": {"text": msg, "history": history, "success": True}, "output": msg}

    elif act == "status":
        current = updater.get_current_version()
        last = updater.get_last_status()
        history = updater.get_update_history()
        last_check = history[0]["checked_at"] if history else "Chưa kiểm tra"
        msg = (
            f"🤖 **JARVIS Version Manager**\n"
            f"📌 Phiên bản hiện tại: **v{current}**\n"
            f"🕐 Lần kiểm tra cuối: {last_check}\n"
            f"📊 Số lần đã kiểm tra: {len(history)}"
        )
        return {
            "data": {"text": msg, "current": current, "checks": len(history), "success": True},
            "output": msg,
        }

    else:
        msg = f"Hành động '{act}' không hỗ trợ. Thử: check, update, rollback, history, status."
        return {"data": {"text": msg, "success": False}, "output": msg}
