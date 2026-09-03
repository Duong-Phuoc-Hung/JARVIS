"""
jarvis/ui/terminal/report.py
==============================
Diagnostic report persistence for the Terminal Control Center.

Uses jarvis.core.paths.data_path() -- the existing canonical writable
per-user data location (%LOCALAPPDATA%/JARVIS on Windows) -- never a
hard-coded source-tree path. Reports live under <jarvis-data>/reports/cli/.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from jarvis import __version__ as JARVIS_VERSION
from jarvis.core.paths import data_path
from jarvis.ui.terminal.models import ActionOutcome, BatchResult, SessionRecord
from jarvis.ui.terminal.session import redact_structured


def _safe_filename_component(text: str) -> str:
    keep = "".join(c if (c.isalnum() or c in ("-", "_")) else "_" for c in text.strip())
    return keep or "report"


def _timestamp_component(ts: float | None = None) -> str:
    return time.strftime("%Y-%m-%d_%H%M%S", time.localtime(ts))


def _unique_report_path(module: str, kind: str, ts: float | None = None) -> Path:
    """Never silently overwrites: appends -2, -3, ... if the timestamped
    filename somehow already exists (two saves within the same second)."""
    reports_dir = data_path("reports", "cli")
    reports_dir.mkdir(parents=True, exist_ok=True)
    stem = f"jarvis_{_safe_filename_component(module)}_{_safe_filename_component(kind)}_{_timestamp_component(ts)}"
    candidate = reports_dir / f"{stem}.txt"
    n = 2
    while candidate.exists():
        candidate = reports_dir / f"{stem}-{n}.txt"
        n += 1
    return candidate


def _header(title: str, module: str, operation: str, duration_s: float) -> list[str]:
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    return [
        "=" * 60,
        "J.A.R.V.I.S. // INFOSEC EDITION",
        title,
        "=" * 60,
        "",
        f"Timestamp       : {now}",
        f"JARVIS Version  : {JARVIS_VERSION}",
        "Platform        : Windows",
        f"Module          : {module}",
        f"Operation       : {operation}",
        f"Duration        : {duration_s:.2f}s",
        "",
    ]


def _footer() -> list[str]:
    return ["", "=" * 60, "END OF JARVIS REPORT", "=" * 60, ""]


def _outcome_section(action_label: str, outcome: ActionOutcome) -> list[str]:
    lines = [
        "-" * 60,
        action_label,
        "-" * 60,
        "",
        f"Status          : {outcome.status.value}",
    ]
    for key, value in redact_fields_safe(outcome.fields):
        lines.append(f"{key:<16}: {value}")
    if outcome.error_reason:
        lines.append("")
        lines.append(f"Reason          : {outcome.error_reason}")
    for detail in outcome.detail_lines:
        lines.append(detail)
    lines.append("")
    return lines


def redact_fields_safe(fields: list[tuple[str, str]]) -> list[tuple[str, str]]:
    from jarvis.ui.terminal.session import redact_fields
    return redact_fields(fields)


class ReportWriteResult:
    def __init__(self, path: Path | None, saved: bool, error: str | None = None) -> None:
        self.path = path
        self.saved = saved
        self.error = error


class ReportWriter:
    """Writes human-readable TXT diagnostic reports. Every write is verified
    (the file is re-checked to actually exist and be non-empty) before
    reporting success -- a save is never claimed without proof."""

    def save_single_result(self, module: str, action_label: str, outcome: ActionOutcome) -> ReportWriteResult:
        lines = _header(f"{action_label} Report", module, action_label, outcome.duration_s)
        lines.extend(_outcome_section(action_label, outcome))
        lines.extend(_footer())
        return self._write(module, "result", lines)

    def save_batch_result(self, batch: BatchResult) -> ReportWriteResult:
        total_duration = batch.duration_s
        lines = _header(f"{batch.module} Diagnostic Report", batch.module, batch.operation, total_duration)
        for item in batch.items:
            lines.extend(_outcome_section(item.action.label, item.outcome))
        counts = batch.counts()
        lines.append("-" * 60)
        lines.append("SUMMARY")
        lines.append("-" * 60)
        lines.append("")
        for status_name, count in sorted(counts.items()):
            lines.append(f"{status_name:<16}: {count}")
        lines.extend(_footer())
        return self._write(batch.module, "batch", lines)

    def save_module_session(self, module: str, records: list[SessionRecord]) -> ReportWriteResult:
        lines = _header(f"{module} Session Report", module, "session_export", 0.0)
        lines.extend(self._session_lines(records))
        lines.extend(_footer())
        return self._write(module, "session", lines)

    def save_full_session(self, records: list[SessionRecord]) -> ReportWriteResult:
        lines = _header("Full CLI Session Report", "session", "full_session_export", 0.0)
        lines.extend(self._session_lines(records))
        lines.extend(_footer())
        return self._write("session", "full", lines)

    def _session_lines(self, records: list[SessionRecord]) -> list[str]:
        lines: list[str] = []
        for rec in records:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(rec.timestamp))
            lines.append("-" * 60)
            lines.append(f"{ts}  [{rec.module}] {rec.action}")
            lines.append("-" * 60)
            lines.append(f"Status          : {rec.status}")
            lines.append(f"Duration        : {rec.duration_s:.2f}s")
            lines.append(f"Summary         : {rec.summary}")
            safe_data = redact_structured(rec.structured_data)
            if safe_data:
                for k, v in safe_data.items():
                    lines.append(f"  {k}: {v}")
            lines.append("")
        if not records:
            lines.append("(no records in this session)")
            lines.append("")
        return lines

    def _write(self, module: str, kind: str, lines: list[str]) -> ReportWriteResult:
        try:
            path = _unique_report_path(module, kind)
            content = "\n".join(lines)
            path.write_text(content, encoding="utf-8")
        except OSError as e:
            return ReportWriteResult(path=None, saved=False, error=str(e))

        # Verify before claiming success -- never trust the write call alone.
        try:
            exists = path.exists() and path.stat().st_size > 0
        except OSError as e:
            return ReportWriteResult(path=path, saved=False, error=f"post-write verification failed: {e}")

        if not exists:
            return ReportWriteResult(path=path, saved=False, error="file not found after write")
        return ReportWriteResult(path=path, saved=True)
