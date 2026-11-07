"""
JARVIS Built-in Skill: Smart File Renamer
=========================================
Inspects documents with ambiguous or messy filenames (e.g. 'download (1).pdf', 'scan_002.txt')
and generates clean, descriptive, context-aware filenames based on document headers and content.
"""
from __future__ import annotations

import datetime
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("jarvis.skills.smart_renamer")

AMBIGUOUS_PATTERNS = [
    re.compile(r"^download(?:\s*\(\d+\))?$", re.IGNORECASE),
    re.compile(r"^document(?:\s*\(\d+\))?$", re.IGNORECASE),
    re.compile(r"^scan(?:_\d+)?$", re.IGNORECASE),
    re.compile(r"^untitled(?:\s*\(\d+\))?$", re.IGNORECASE),
    re.compile(r"^file(?:\s*\(\d+\))?$", re.IGNORECASE),
    re.compile(r"^unnamed(?:\s*\(\d+\))?$", re.IGNORECASE),
    re.compile(r"^\d{8,14}$"),  # Timestamp only names
]


def is_ambiguous_name(stem: str) -> bool:
    """Check if a filename stem matches common ambiguous naming patterns."""
    for pattern in AMBIGUOUS_PATTERNS:
        if pattern.match(stem.strip()):
            return True
    return False


def sanitize_filename(name: str, max_length: int = 60) -> str:
    """Sanitize string into an OS-safe filename."""
    # Replace invalid Windows filename characters: \ / : * ? " < > |
    cleaned = re.sub(r'[\\/*?:"<>|\n\r\t]+', '_', name)
    cleaned = re.sub(r'\s+', '_', cleaned).strip('._ ')
    if not cleaned:
        cleaned = "TaiLieu"
    return cleaned[:max_length]


def extract_title_from_text_file(path: Path) -> str | None:
    """Extract a meaningful title from text or markdown files."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for _ in range(20):
                line = f.readline()
                if not line:
                    break
                line_str = line.strip()
                # Check for markdown header
                if line_str.startswith("#"):
                    header = line_str.lstrip("#").strip()
                    if len(header) >= 3:
                        return header
                # Check for key: value or title keyword
                if line_str.lower().startswith("title:") or line_str.lower().startswith("tiêu đề:"):
                    parts = line_str.split(":", 1)
                    if len(parts) > 1 and len(parts[1].strip()) >= 3:
                        return parts[1].strip()
                # Use first non-empty substantial line
                if len(line_str) >= 6 and not line_str.startswith(("---", "===", "***")):
                    return line_str
    except Exception as exc:
        log.warning("Could not extract title from '%s': %s", path.name, exc)
    return None


def extract_title_from_pdf(path: Path) -> str | None:
    """Extract title from the first page of a PDF file."""
    try:
        import pypdf
        reader = pypdf.PdfReader(str(path))
        if reader.metadata and reader.metadata.title:
            title_meta = str(reader.metadata.title).strip()
            if len(title_meta) >= 3:
                return title_meta
        if len(reader.pages) > 0:
            first_page_text = reader.pages[0].extract_text() or ""
            for line in first_page_text.splitlines():
                line_clean = line.strip()
                if len(line_clean) >= 6 and not line_clean.isdigit():
                    return line_clean[:80]
    except ImportError:
        pass
    except Exception as exc:
        log.warning("PDF extraction failed for '%s': %s", path.name, exc)
    return None


def suggest_new_filename(path: Path) -> str | None:
    """Generate a clean new filename based on extracted title and file creation date."""
    ext = path.suffix.lower()
    title: str | None = None

    if ext in {".txt", ".md", ".json", ".csv"}:
        title = extract_title_from_text_file(path)
    elif ext == ".pdf":
        title = extract_title_from_pdf(path)

    if not title:
        return None

    safe_title = sanitize_filename(title)
    try:
        mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime)
        date_prefix = mtime.strftime("%Y-%m-%d")
    except Exception:
        date_prefix = datetime.datetime.now().strftime("%Y-%m-%d")

    return f"{date_prefix}_{safe_title}{ext}"


def execute(
    path: str = "",
    directory: str = "",
    action: str = "suggest",
    auto_rename: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Execute smart file renaming analysis or operation.
    """
    suggestions: list[dict[str, str]] = []
    renamed: list[dict[str, str]] = []

    files_to_check: list[Path] = []
    if path.strip():
        p = Path(path).resolve()
        if p.is_file():
            files_to_check.append(p)
    elif directory.strip():
        d = Path(directory).resolve()
        if d.is_dir():
            files_to_check = [f for f in d.iterdir() if f.is_file()]

    for f in files_to_check:
        new_name = suggest_new_filename(f)
        if new_name and new_name.lower() != f.name.lower():
            target_path = f.parent / new_name
            suggestions.append({
                "original": f.name,
                "suggested": new_name,
                "path": str(f),
            })
            if auto_rename or action == "rename":
                try:
                    f.rename(target_path)
                    renamed.append({
                        "original": f.name,
                        "new": new_name,
                    })
                except Exception as exc:
                    log.error("Failed to rename '%s' to '%s': %s", f.name, new_name, exc)

    if not files_to_check:
        msg = "Vui lòng cung cấp đường dẫn tệp (`path`) hoặc thư mục (`directory`) cần đổi tên."
        return {"data": {"success": False, "suggestions": []}, "output": msg}

    lines: list[str] = []
    if renamed:
        lines.append(f"✅ Đã đổi tên thành công {len(renamed)} tệp tin:")
        for r in renamed:
            lines.append(f"  • `{r['original']}` ➔ `{r['new']}`")
    elif suggestions:
        lines.append(f"💡 Đề xuất đổi tên cho {len(suggestions)} tệp tin:")
        for s in suggestions:
            lines.append(f"  • `{s['original']}` ➔ `{s['suggested']}`")
    else:
        lines.append("✨ Tên tệp tin đã rõ ràng hoặc không trích xuất được tiêu đề nội dung.")

    msg = "\n".join(lines)
    return {
        "data": {
            "suggestions": suggestions,
            "renamed": renamed,
            "total_suggestions": len(suggestions),
            "total_renamed": len(renamed),
            "success": True,
        },
        "output": msg,
    }
