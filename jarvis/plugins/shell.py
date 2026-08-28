"""
jarvis/plugins/shell.py
=======================
CLI shell execution plugin with ADMIN privilege enforcement and timeout protection.
"""
from __future__ import annotations

import subprocess
from typing import Any

from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import PluginMetadata, PrivilegeLevel
from jarvis.core.plugin import BasePlugin


class ShellPlugin(BasePlugin):
    """Executes CLI commands with timeout guard and privilege boundary."""

    def _define_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="shell",
            version="1.0.0",
            description="CLI shell executor",
            required_permissions=["ADMIN"],
        )

    def initialize(self, config: dict[str, Any], dispatcher: ActionDispatcher) -> None:
        self.config = config or {}
        self.dispatcher = dispatcher
        self.register_action(
            name="shell_exec",
            handler=self.exec_command,
            required_privilege=PrivilegeLevel.ADMIN,
            description="Execute shell command",
        )

    def exec_command(self, command: str, timeout: float = 5.0, **kwargs) -> dict[str, Any]:
        """Runs shell command with timeout limit."""
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
            }
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Command '{command}' timed out after {timeout}s")
