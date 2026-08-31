"""
tests/unit/test_subprocess_no_window_r2.py
===========================================
Acceptance & Regression Tests for R2: Suppress Admin CMD / PowerShell Flash Across Codebase.

Verifies:
1. Every subprocess.Popen, subprocess.run, subprocess.call, subprocess.check_output
   invocation across `jarvis/` and `scripts/` includes `CREATE_NO_WINDOW` or `startupinfo`
   within 5 lines of the call site.
2. No `os.system(` call exists across `jarvis/` and `scripts/`.
3. Runtime unit tests for patched components ensuring creationflags are passed on Windows.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def test_no_os_system_in_codebase():
    """Verify that os.system is not called anywhere in jarvis/ or scripts/."""
    violating_lines = []
    for search_dir in [ROOT_DIR / "jarvis", ROOT_DIR / "scripts"]:
        for root, _, files in os.walk(search_dir):
            for file in files:
                if file.endswith(".py"):
                    file_path = Path(root) / file
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                    lines = content.splitlines()
                    for idx, line in enumerate(lines, 1):
                        stripped = line.strip()
                        # Exclude comments / docstrings mentioning os.system
                        if stripped.startswith("#") or stripped.startswith("*"):
                            continue
                        if re.search(r"\bos\.system\s*\(", stripped):
                            violating_lines.append(f"{file_path}:{idx} -> {stripped}")

    assert not violating_lines, f"Found forbidden os.system calls:\n" + "\n".join(violating_lines)


def test_all_subprocess_calls_have_create_no_window():
    """
    Acceptance check matching specification:
    Select-String -Path "jarvis/**/*.py","scripts/**/*.py" -Pattern "subprocess.(Popen|run|call|check_output)"
    Every match must have CREATE_NO_WINDOW or startupinfo within 5 lines.
    """
    pattern = re.compile(r"subprocess\.(Popen|run|call|check_output)")
    target_pattern = re.compile(r"(CREATE_NO_WINDOW|startupinfo)")

    unprotected_calls = []
    total_calls = 0

    for search_dir in [ROOT_DIR / "jarvis", ROOT_DIR / "scripts"]:
        for root, _, files in os.walk(search_dir):
            for file in files:
                if file.endswith(".py"):
                    file_path = Path(root) / file
                    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    for idx, line in enumerate(lines):
                        if pattern.search(line):
                            # Skip comments or docstring usage instructions
                            stripped = line.strip()
                            if stripped.startswith("#") or stripped.startswith("*") or stripped.startswith('"""') or stripped.startswith("'''") or "Usage:" in line or "fall back to" in line:
                                continue

                            total_calls += 1
                            # Check window of 5 lines before and 5 lines after (including current line)
                            start_idx = max(0, idx - 5)
                            end_idx = min(len(lines), idx + 6)
                            surrounding = "\n".join(lines[start_idx:end_idx])

                            if not target_pattern.search(surrounding):
                                unprotected_calls.append(
                                    f"{file_path}:{idx + 1} -> {line.strip()}\nSurrounding snippet:\n{surrounding}\n"
                                )

    assert total_calls > 0, "No subprocess calls found in scan scope!"
    assert not unprotected_calls, (
        f"Found {len(unprotected_calls)} / {total_calls} unprotected subprocess calls:\n"
        + "\n".join(unprotected_calls)
    )


def test_hardware_monitor_nvidia_smi_uses_creationflags(monkeypatch):
    """Verify HardwareMonitor._probe_gpu passes creationflags to subprocess.run."""
    from jarvis.hardware.monitor import HardwareMonitor

    mock_run = MagicMock()
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "50, 65, 8192, 4096, 1200\n"

    monkeypatch.setattr(subprocess, "run", mock_run)

    mon = HardwareMonitor()
    mon._nvidia_smi_path = "nvidia-smi.exe"
    _ = mon._probe_gpu()

    assert mock_run.called
    kwargs = mock_run.call_args[1]
    assert "creationflags" in kwargs
    if sys.platform == "win32":
        assert kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW


def test_hardware_monitor_smart_probe_uses_creationflags(monkeypatch):
    """Verify HardwareMonitor._probe_disks passes creationflags to subprocess.run."""
    from jarvis.hardware.monitor import HardwareMonitor

    mock_run = MagicMock()
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = '[{"InstanceName": "Disk0", "Active": true, "PredictFailure": false}]'

    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr(sys, "platform", "win32")

    mon = HardwareMonitor()
    _ = mon._probe_disks()

    assert mock_run.called
    kwargs = mock_run.call_args[1]
    assert "creationflags" in kwargs
    assert kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW


def test_notification_hub_toast_uses_creationflags(monkeypatch):
    """Verify NotificationHub._send_toast passes creationflags."""
    from jarvis.workers.notification_hub import NotificationHub

    mock_run = MagicMock()
    mock_run.return_value.returncode = 0
    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr(sys, "platform", "win32")

    hub = NotificationHub(is_mock=True)
    hub._send_toast("Title", "Message")

    assert mock_run.called
    kwargs = mock_run.call_args[1]
    assert "creationflags" in kwargs
    assert kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW


def test_shell_plugin_exec_uses_creationflags(monkeypatch):
    """Verify ShellPlugin.exec_command passes creationflags."""
    from jarvis.plugins.shell import ShellPlugin

    mock_run = MagicMock()
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "OK"
    mock_run.return_value.stderr = ""
    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr(sys, "platform", "win32")

    plugin = ShellPlugin()
    plugin.exec_command("dir")

    assert mock_run.called
    kwargs = mock_run.call_args[1]
    assert "creationflags" in kwargs
    assert kwargs["creationflags"] == subprocess.CREATE_NO_WINDOW


def test_app_launcher_uses_combined_creationflags(monkeypatch):
    """Verify app_launcher skill passes combined CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP."""
    from jarvis.skills.app_launcher import execute

    mock_popen = MagicMock()
    monkeypatch.setattr(subprocess, "Popen", mock_popen)
    monkeypatch.setattr(sys, "platform", "win32")

    execute("notepad")

    assert mock_popen.called
    kwargs = mock_popen.call_args[1]
    assert "creationflags" in kwargs
    assert kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW
    assert kwargs["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
