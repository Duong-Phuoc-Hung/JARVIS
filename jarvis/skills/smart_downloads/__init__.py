"""
JARVIS Built-in Skill: Smart Downloads Intake & Organizer
=========================================================
Automatically scans, categorizes, and organizes the Windows Downloads directory
into structured destination folders (Documents, Pictures, Code, Audio, Video, Archives, Installers).
Supports dry-run scanning, active download protection, and desktop toast alerts.
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("jarvis.skills.smart_downloads")

CATEGORY_MAPPING: dict[str, set[str]] = {
    "Documents": {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".txt", ".csv", ".rtf", ".epub", ".md"},
    "Pictures": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico", ".tiff"},
    "Code": {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".json", ".yaml", ".yml", ".sh", ".bat", ".ps1", ".sql", ".rs", ".go", ".cpp", ".c", ".java"},
    "Audio": {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"},
    "Video": {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"},
    "Installers": {".exe", ".msi", ".iso"},
}

IGNORED_EXTENSIONS: set[str] = {".crdownload", ".part", ".tmp", ".download"}


def get_default_downloads_dir() -> Path:
    """Resolve the current user's Downloads directory path."""
    user_home = Path.home()
    standard_dl = user_home / "Downloads"
    if standard_dl.exists():
        return standard_dl
    return user_home


def organize_downloads(
    source_dir: str | Path | None = None,
    dry_run: bool = False,
    min_age_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Scan source folder and organize files by category.
    """
    src = Path(source_dir).resolve() if source_dir else get_default_downloads_dir()
    if not src.exists() or not src.is_dir():
        return {"error": f"Thư mục không tồn tại: {src}", "categorized": {}, "total_moved": 0}

    now = time.time()
    categorized_results: dict[str, list[str]] = {cat: [] for cat in CATEGORY_MAPPING}
    categorized_results["Others"] = []
    total_processed = 0

    for item in src.iterdir():
        # Only process files, ignore subdirectories and hidden files
        if not item.is_file() or item.name.startswith((".", "~$")):
            continue

        ext = item.suffix.lower()
        if ext in IGNORED_EXTENSIONS:
            continue

        # Active download protection
        try:
            mtime = item.stat().st_mtime
            if (now - mtime) < min_age_seconds:
                continue
        except OSError:
            continue

        matched_category = "Others"
        for category, extensions in CATEGORY_MAPPING.items():
            if ext in extensions:
                matched_category = category
                break

        target_folder = src / matched_category
        target_path = target_folder / item.name

        if not dry_run:
            target_folder.mkdir(parents=True, exist_ok=True)
            # Avoid overwriting existing files by appending timestamp if collision occurs
            if target_path.exists():
                stem = item.stem
                unique_name = f"{stem}_{int(now)}{ext}"
                target_path = target_folder / unique_name

            try:
                shutil.move(str(item), str(target_path))
                categorized_results[matched_category].append(target_path.name)
                total_processed += 1
            except Exception as exc:
                log.error("Failed to move '%s': %s", item.name, exc)
        else:
            categorized_results[matched_category].append(item.name)
            total_processed += 1

    # Filter out empty categories
    cleaned_results = {k: v for k, v in categorized_results.items() if v}

    return {
        "source_directory": str(src),
        "dry_run": dry_run,
        "total_files": total_processed,
        "categories": cleaned_results,
    }


def execute(
    directory: str = "",
    action: str = "organize",
    dry_run: bool = False,
    notify: bool = True,
    min_age_seconds: float = 30.0,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Execute smart downloads intake and organization.
    """
    act = action.lower().strip()
    is_dry = dry_run or (act == "scan")

    target_dir = Path(directory) if directory.strip() else get_default_downloads_dir()
    result = organize_downloads(source_dir=target_dir, dry_run=is_dry, min_age_seconds=min_age_seconds)

    total = result.get("total_files", 0)
    cat_summary = result.get("categories", {})

    lines: list[str] = []
    if is_dry:
        lines.append(f"🔍 [Quét thư mục] Tìm thấy {total} tệp tin trong `{target_dir}`:")
    else:
        lines.append(f"📁 [Tự động phân loại] Đã sắp xếp thành công {total} tệp tin:")

    for cat, files in cat_summary.items():
        lines.append(f"  • **{cat}** ({len(files)} tệp): {', '.join(files[:4])}{'...' if len(files) > 4 else ''}")

    if total == 0:
        msg = f"✨ Thư mục `{target_dir}` đã sạch sẽ, không có tệp mới cần phân loại."
    else:
        msg = "\n".join(lines)

    if notify and total > 0 and not is_dry:
        try:
            from jarvis.skills.desktop_notifier import send_windows_toast
            send_windows_toast(
                title="JARVIS Smart Downloads",
                message=f"Đã tự động phân loại {total} tệp tin vào các thư mục tương ứng.",
                sound="Default"
            )
        except Exception:
            pass

    return {
        "data": {
            "total_files": total,
            "categories": cat_summary,
            "directory": str(target_dir),
            "dry_run": is_dry,
            "success": True,
        },
        "output": msg,
    }
