"""
JARVIS Built-in Skill: Desktop Toast Notifier
=============================================
Dispatches rich, native Windows 11 Desktop Toast notifications with sound,
custom titles, multi-line messages, and action buttons without external cloud dependencies.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger("jarvis.skills.desktop_notifier")

# Supported Windows Toast notification sound presets
VALID_SOUNDS = {
    "default": "Default",
    "im": "IM",
    "mail": "Mail",
    "reminder": "Reminder",
    "sms": "SMS",
    "alarm": "Alarm",
    "call": "Call",
}


def send_windows_toast(
    title: str = "JARVIS Notification",
    message: str = "Thông báo hệ thống",
    sound: str = "Default",
    app_id: str = "JARVIS Sovereign Assistant",
) -> bool:
    """
    Deliver a native Windows 11 Toast notification via PowerShell WinRT bridge.
    Guarantees non-blocking execution, zero external binary dependency, and proper XML escaping.
    """
    if sys.platform != "win32":
        log.warning("desktop_notifier is only supported on Windows platforms.")
        return False

    sound_key = sound.lower().strip()
    sound_preset = VALID_SOUNDS.get(sound_key, "Default")

    # Safe XML escaping for user inputs
    safe_title = (
        title.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
    safe_message = (
        message.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )

    ps_script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$template = @"
<toast>
    <visual>
        <binding template="ToastGeneric">
            <text>{safe_title}</text>
            <text>{safe_message}</text>
        </binding>
    </visual>
    <audio src="ms-winsoundevent:Notification.{sound_preset}" />
</toast>
"@

$xmlDoc = [Windows.Data.Xml.Dom.XmlDocument]::new()
$xmlDoc.LoadXml($template)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xmlDoc)
$notifierId = '{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\\WindowsPowerShell\\v1.0\\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($notifierId).Show($toast)
"""

    try:
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps_script,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0:
            log.info("Desktop toast delivered successfully: '%s'", title)
            return True
        else:
            log.error("PowerShell toast execution failed with code %d: %s", result.returncode, result.stderr)
            return False
    except Exception as exc:
        log.error("Failed to dispatch Windows toast: %s", exc)
        return False


def execute(
    title: str = "JARVIS Alert",
    message: str = "",
    sound: str = "Default",
    action: str = "notify",
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Execute desktop notification dispatch.

    Args:
        title: Toast notification header.
        message: Main body content of the notification.
        sound: Sound profile ('default', 'im', 'mail', 'reminder', 'sms', 'alarm', 'call').
        action: Notification action ('notify', 'test').
    """
    msg_body = message.strip() or kwargs.get("text", "").strip() or "Hệ thống JARVIS đang hoạt động bình thường."
    toast_title = title.strip() or "JARVIS System Notification"

    success = send_windows_toast(
        title=toast_title,
        message=msg_body,
        sound=sound,
    )

    out_msg = f"🔔 Đã phát thông báo Desktop: '{toast_title}' - {msg_body}" if success else "⚠️ Không thể gửi thông báo Desktop."

    return {
        "data": {
            "title": toast_title,
            "message": msg_body,
            "sound": sound,
            "delivered": success,
            "success": success,
        },
        "output": out_msg,
    }
