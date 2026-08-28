"""
Artifact Management and Indexing for JARVIS Code Interpreter Sandbox.
Detects, classifies, and indexes generated files (.xlsx, .csv, .png, .pdf, etc.)
after sandbox script execution.
"""
from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.sandbox.artifacts")


@dataclass
class ArtifactInfo:
    """Metadata representing a generated output file from sandbox execution."""
    filename: str
    file_path: str
    file_type: str        # e.g. "image", "spreadsheet", "csv", "document", "json", "archive", "binary"
    size_bytes: int
    mime_type: str
    created_at: float = field(default_factory=time.time)
    checksum_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "size_bytes": self.size_bytes,
            "mime_type": self.mime_type,
            "created_at": self.created_at,
            "checksum_sha256": self.checksum_sha256,
        }


class ArtifactManager:
    """
    Manages snapshotting, discovery, classification, and export of files
    produced inside the sandbox execution environment.
    """

    EXTENSION_MAP: dict[str, tuple[str, str]] = {
        ".png": ("image", "image/png"),
        ".jpg": ("image", "image/jpeg"),
        ".jpeg": ("image", "image/jpeg"),
        ".gif": ("image", "image/gif"),
        ".svg": ("image", "image/svg+xml"),
        ".webp": ("image", "image/webp"),
        ".xlsx": ("spreadsheet", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ".xls": ("spreadsheet", "application/vnd.ms-excel"),
        ".csv": ("csv", "text/csv"),
        ".tsv": ("csv", "text/tab-separated-values"),
        ".pdf": ("document", "application/pdf"),
        ".docx": ("document", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ".doc": ("document", "application/msword"),
        ".txt": ("document", "text/plain"),
        ".md": ("document", "text/markdown"),
        ".json": ("json", "application/json"),
        ".xml": ("data", "application/xml"),
        ".html": ("document", "text/html"),
        ".zip": ("archive", "application/zip"),
        ".tar": ("archive", "application/x-tar"),
        ".gz": ("archive", "application/gzip"),
    }

    IGNORED_FILENAMES: set[str] = {
        "script.py",
        "script.ps1",
        "__main__.py",
        ".gitkeep",
    }

    IGNORED_EXTENSIONS: set[str] = {
        ".pyc",
        ".pyo",
        ".pyd",
    }

    def __init__(self, scratch_dir: str | Path) -> None:
        self.scratch_dir = Path(scratch_dir).resolve()
        mimetypes.init()

    def snapshot_directory(self) -> set[Path]:
        """
        Take a snapshot of all files currently existing in the scratch directory.
        
        Returns:
            Set of resolved Path objects.
        """
        if not self.scratch_dir.exists():
            return set()

        files: set[Path] = set()
        for root, dirs, filenames in os.walk(self.scratch_dir):
            # Skip __pycache__ directories
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")
            for fname in filenames:
                file_path = Path(root) / fname
                files.add(file_path.resolve())
        return files

    def detect_new_artifacts(self, pre_snapshot: set[Path]) -> list[ArtifactInfo]:
        """
        Detect all new or updated files generated since the pre_snapshot.
        
        Args:
            pre_snapshot: Set of Path objects from before script execution.
            
        Returns:
            List of ArtifactInfo records for newly created files.
        """
        if not self.scratch_dir.exists():
            return []

        artifacts: list[ArtifactInfo] = []
        current_snapshot = self.snapshot_directory()
        new_files = current_snapshot - pre_snapshot

        for file_path in sorted(new_files):
            # Check ignored filenames and extensions
            if file_path.name in self.IGNORED_FILENAMES:
                continue
            if file_path.suffix.lower() in self.IGNORED_EXTENSIONS:
                continue
            if "__pycache__" in str(file_path):
                continue
            if not file_path.is_file():
                continue

            try:
                size_bytes = file_path.stat().st_size
                checksum = self.compute_sha256(file_path)
                file_type, mime_type = self.classify_file(file_path)

                artifact = ArtifactInfo(
                    filename=file_path.name,
                    file_path=str(file_path),
                    file_type=file_type,
                    size_bytes=size_bytes,
                    mime_type=mime_type,
                    created_at=file_path.stat().st_mtime,
                    checksum_sha256=checksum,
                )
                artifacts.append(artifact)
                logger.debug("Discovered artifact: %s (%s, %d bytes)", artifact.filename, artifact.file_type, artifact.size_bytes)
            except Exception as exc:
                logger.warning("Failed to index artifact '%s': %s", file_path, exc)

        return artifacts

    def classify_file(self, file_path: str | Path) -> tuple[str, str]:
        """
        Determine high-level file type and MIME type based on extension.
        
        Returns:
            Tuple of (file_type, mime_type).
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext in self.EXTENSION_MAP:
            return self.EXTENSION_MAP[ext]

        guessed_mime, _ = mimetypes.guess_type(str(path))
        mime = guessed_mime or "application/octet-stream"

        if mime.startswith("image/"):
            return "image", mime
        elif mime.startswith("text/"):
            return "document", mime
        elif mime.startswith("audio/"):
            return "audio", mime
        elif mime.startswith("video/"):
            return "video", mime

        return "binary", mime

    @staticmethod
    def compute_sha256(file_path: str | Path) -> str:
        """Calculate SHA256 hex digest for a file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def export_artifacts(
        self,
        artifacts: list[ArtifactInfo],
        destination_dir: str | Path
    ) -> list[Path]:
        """
        Copy generated artifacts from scratch directory to persistent storage directory.
        
        Args:
            artifacts: List of ArtifactInfo to export.
            destination_dir: Directory where files should be copied.
            
        Returns:
            List of new destination Path objects.
        """
        dest_path = Path(destination_dir).resolve()
        dest_path.mkdir(parents=True, exist_ok=True)
        exported: list[Path] = []

        for artifact in artifacts:
            src = Path(artifact.file_path)
            if src.exists():
                target = dest_path / artifact.filename
                shutil.copy2(src, target)
                exported.append(target)
                logger.info("Exported artifact '%s' to '%s'", artifact.filename, target)

        return exported
