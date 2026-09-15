"""
jarvis/plugins/shell.py
=======================
CLI shell execution plugin with ADMIN privilege enforcement and timeout protection.
"""
from __future__ import annotations

import subprocess
import sys
from typing import Any

import psutil

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
        """
        Runs shell command with a genuinely wall-clock-bounded timeout.

        Deliberately avoids subprocess's run(..., timeout=...) convenience
        wrapper: on Windows, its own internal TimeoutExpired handling calls
        process.kill() (which only terminates the immediate shell wrapper,
        e.g. cmd.exe) and then performs a SECOND, UNBOUNDED communicate() call
        to collect output for the exception. If the shelled-out command
        spawned a grandchild process (e.g. `curl`) that survives the
        wrapper's termination and keeps the inherited stdout/stderr pipes
        open, that second call can block far past `timeout` -- observed in
        CI as an effectively indefinite hang on a weather lookup
        (`curl -s wttr.in`) via shell_exec. Using Popen directly keeps full
        control: on timeout, the entire process tree is terminated first,
        and every step afterward stays bounded.
        """
        _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace',
            creationflags=_cflags,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            return {
                "exit_code": proc.returncode,
                "stdout": (stdout or "").strip(),
                "stderr": (stderr or "").strip(),
            }
        except subprocess.TimeoutExpired:
            self._terminate_process_tree(proc)
            # Bounded cleanup only, never an unbounded wait: even if the tree
            # kill missed something, a caller must get a timely, truthful
            # timeout result rather than blocking again on a lingering handle.
            try:
                proc.communicate(timeout=2.0)
            except Exception:
                pass
            # Fail closed unconditionally: a timeout is always reported as a
            # timeout, regardless of whether cleanup above fully succeeded.
            raise TimeoutError(f"Command timed out after {timeout}s")

    def _terminate_process_tree(self, proc: Any) -> None:
        """
        Best-effort termination of the ENTIRE process tree rooted at `proc`.

        On Windows, shell=True launches the command via a cmd.exe wrapper that
        may itself spawn a grandchild (e.g. curl.exe/python.exe); killing only
        the wrapper leaves the grandchild running and holding the output pipes
        open indefinitely -- this is the actual defect being fixed here.
        Kill the descendants through psutil before killing the wrapper.  A
        single ``taskkill /T`` call is not reliable in restricted Windows
        sessions: it can return ``Access denied`` for one console helper and
        leave the executable grandchild alive.  Capturing the tree first and
        terminating each process independently avoids that all-or-nothing
        failure mode.  Never raises: termination failure must still leave the
        caller free to report a truthful timeout, never a fabricated success.
        """
        if sys.platform == "win32":
            try:
                root = psutil.Process(proc.pid)
                descendants = root.children(recursive=True)
                for child in reversed(descendants):
                    try:
                        child.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                try:
                    root.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                _, survivors = psutil.wait_procs([*descendants, root], timeout=0.5)
                for survivor in survivors:
                    try:
                        survivor.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                if survivors:
                    psutil.wait_procs(survivors, timeout=0.5)
            except Exception:
                # The wrapper may have exited between communicate() timing
                # out and this snapshot, or OS policy may deny inspection.
                # Cleanup errors must not replace the truthful TimeoutError;
                # the Popen handle is still killed below as a final fallback.
                pass
        try:
            proc.kill()
        except Exception:
            pass
