"""
JARVIS Built-in Skill: Smart USB Auto-Backup
============================================
Detects connected removable drives (USB flash drives / external disks)
and creates automated, timestamped, compressed ZIP backups of designated project folders.
"""
from __future__ import annotations

import datetime
import logging
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

log = logging.getLogger("jarvis.skills.usb_backup")


def find_removable_drives() -> list[dict[str, str]]:
    """Detect all currently mounted removable drives or external disks."""
    removable: list[dict[str, str]] = []
    if HAS_PSUTIL:
        for part in psutil.disk_partitions(all=False):
            # Check for removable drive flags or non-C/D drives with writable storage
            opts = part.opts.lower()
            if "removable" in opts or part.fstype.lower() in {"fat32", "exfat"}:
                removable.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                })
    # Windows fallback: scan drive letters E: through Z:
    if not removable and os.name == "nt":
        for letter in "EFGHIJKLMNOPQRSTUVWXYZ":
            drive_path = Path(f"{letter}:\\")
            if drive_path.exists():
                removable.append({
                    "device": f"{letter}:",
                    "mountpoint": str(drive_path),
                    "fstype": "unknown",
                })
    return removable


def create_zip_backup(source_dir: Path, destination_zip: Path, max_files: int = 10000) -> dict[str, Any]:
    """Compress source folder into a timestamped zip archive."""
    file_count = 0
    total_bytes = 0
    destination_zip.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(destination_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_dir):
            # Skip hidden folders, virtual environments and caches
            dirs[:] = [d for d in dirs if not d.startswith((".", "__")) and d not in {"node_modules", "venv", ".venv"}]
            for file in files:
                if file.startswith((".", "~$")):
                    continue
                file_path = Path(root) / file
                try:
                    arcname = file_path.relative_to(source_dir)
                    zf.write(file_path, arcname)
                    file_count += 1
                    total_bytes += file_path.stat().st_size
                    if file_count >= max_files:
                        break
                except Exception as exc:
                    log.warning("Skipping file '%s': %s", file, exc)
            if file_count >= max_files:
                break

    archive_size = destination_zip.stat().st_size if destination_zip.exists() else 0
    return {
        "file_count": file_count,
        "uncompressed_bytes": total_bytes,
        "compressed_bytes": archive_size,
        "archive_path": str(destination_zip),
    }


def execute(
    source: str = "",
    target_drive: str = "",
    action: str = "backup",
    notify: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Execute USB backup discovery or backup creation.
    """
    removable = find_removable_drives()
    act = action.lower().strip()

    if act == "detect" or not source.strip():
        if not removable:
            msg = "🔌 Không tìm thấy ổ đĩa ngoài hoặc USB nào đang cắm vào máy tính."
        else:
            drives_str = ", ".join([f"{r['device']} ({r['mountpoint']})" for r in removable])
            msg = f"💾 Phát hiện {len(removable)} ổ đĩa ngoài sẵn sàng: {drives_str}"
        return {
            "data": {
                "removable_drives": removable,
                "total_drives": len(removable),
                "success": True,
            },
            "output": msg,
        }

    src_path = Path(source).resolve()
    if not src_path.exists():
        msg = f"Thư mục nguồn không tồn tại: `{source}`"
        return {"data": {"success": False, "error": msg}, "output": msg}

    # Resolve target drive
    dest_root: Path | None = None
    if target_drive.strip():
        dest_root = Path(target_drive).resolve()
    elif removable:
        dest_root = Path(removable[0]["mountpoint"])
    else:
        # Fallback to local backup folder if no USB attached
        dest_root = Path("D:/JARVIS_Backups")

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_filename = f"Backup_{src_path.name}_{timestamp}.zip"
    dest_zip = dest_root / "JARVIS_Backups" / backup_filename

    stats = create_zip_backup(src_path, dest_zip)
    size_mb = stats["compressed_bytes"] / (1024 * 1024)

    msg = (
        f"✅ **Sao lưu hoàn tất!**\n"
        f"  • Thư mục nguồn: `{src_path}`\n"
        f"  • Tệp sao lưu: `{dest_zip}`\n"
        f"  • Số lượng tệp: {stats['file_count']:,} tệp\n"
        f"  • Dung lượng nén: **{size_mb:.2f} MB**"
    )

    if notify:
        try:
            from jarvis.skills.desktop_notifier import send_windows_toast
            send_windows_toast(
                title="JARVIS Smart USB Backup",
                message=f"Đã sao lưu thành công {stats['file_count']} tệp ({size_mb:.1f} MB) sang ổ đĩa {dest_root}.",
                sound="Reminder"
            )
        except Exception:
            pass

    return {
        "data": {
            "source": str(src_path),
            "archive_path": str(dest_zip),
            "file_count": stats["file_count"],
            "size_mb": round(size_mb, 2),
            "success": True,
        },
        "output": msg,
    }
