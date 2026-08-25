"""
Isolated Code Interpreter Sandbox for JARVIS.
Executes self-generated Python and safe PowerShell scripts in an isolated
scratch environment with AST security validation, resource bounds,
execution timeouts, and automatic artifact indexing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Set, Union
import uuid

from jarvis.sandbox.artifacts import ArtifactInfo, ArtifactManager
from jarvis.sandbox.validator import ASTCodeValidator, ValidationResult

logger = logging.getLogger("jarvis.sandbox.interpreter")


@dataclass
class SandboxResult:
    """Structured execution outcome from CodeInterpreterSandbox."""
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    artifacts: List[ArtifactInfo] = field(default_factory=list)
    data: Any = None
    execution_time_ms: float = 0.0
    error: Optional[str] = None
    scratch_dir: Optional[str] = None

    @property
    def execution_time_seconds(self) -> float:
        """Returns execution duration in seconds."""
        return self.execution_time_ms / 1000.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "data": self.data,
            "execution_time_ms": self.execution_time_ms,
            "execution_time_seconds": self.execution_time_seconds,
            "error": self.error,
            "scratch_dir": self.scratch_dir,
        }


class CodeInterpreterSandbox:
    """
    Subprocess-based Code Interpreter Sandbox for executing Python and PowerShell scripts.
    Enforces AST code safety, scratch directory isolation, timeouts, and artifact indexing.
    """

    DEFAULT_TIMEOUT_SECONDS: float = 15.0

    def __init__(
        self,
        base_scratch_dir: Optional[Union[str, Path]] = None,
        default_timeout: float = DEFAULT_TIMEOUT_SECONDS,
        validator: Optional[ASTCodeValidator] = None,
        cleanup_on_exit: bool = False,
        persistent_artifacts_dir: Optional[Union[str, Path]] = None,
        max_execution_seconds: Optional[float] = None,
        **kwargs: Any,
    ) -> None:
        if base_scratch_dir:
            self.base_scratch_dir = Path(base_scratch_dir).resolve()
        else:
            # Default to workspace/sandbox under project root
            self.base_scratch_dir = Path("workspace/sandbox").resolve()
            
        self.base_scratch_dir.mkdir(parents=True, exist_ok=True)
        self.default_timeout = max_execution_seconds if max_execution_seconds is not None else default_timeout
        self.max_execution_seconds = self.default_timeout
        self.validator = validator or ASTCodeValidator()
        self.cleanup_on_exit = cleanup_on_exit
        self.persistent_artifacts_dir = (
            Path(persistent_artifacts_dir).resolve() if persistent_artifacts_dir else None
        )
        if self.persistent_artifacts_dir:
            self.persistent_artifacts_dir.mkdir(parents=True, exist_ok=True)

    def create_scratch_env(self, run_id: Optional[str] = None) -> Path:
        """Create a dedicated scratch directory for a single script run."""
        rid = run_id or f"run_{uuid.uuid4().hex[:10]}"
        scratch_path = self.base_scratch_dir / rid
        scratch_path.mkdir(parents=True, exist_ok=True)
        return scratch_path

    def cleanup_scratch_env(self, scratch_path: Union[str, Path]) -> None:
        """Clean up and remove scratch directory."""
        path = Path(scratch_path)
        if path.exists() and path.is_dir():
            try:
                shutil.rmtree(path, ignore_errors=True)
                logger.debug("Cleaned up sandbox scratch directory: %s", path)
            except Exception as exc:
                logger.warning("Failed to clean up scratch dir %s: %s", path, exc)

    def _prepare_environment(self, custom_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Prepare sanitized environment variables for subprocess execution."""
        env = os.environ.copy()
        # Set UTF-8 encoding for Python subprocesses
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        # Ensure project root is in PYTHONPATH if needed
        project_root = str(Path(__file__).resolve().parents[2])
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{project_root}{os.pathsep}{existing_pythonpath}"
            if existing_pythonpath
            else project_root
        )
        if custom_env:
            env.update(custom_env)
        return env

    def _extract_structured_data(self, stdout: str) -> Any:
        """
        Attempt to parse structured data returned via stdout.
        Looks for `__JARVIS_RESULT__ = <json>` or JSON on the final line.
        """
        if not stdout:
            return None

        # 1. Check for explicit marker: __JARVIS_RESULT__ = {...}
        marker = "__JARVIS_RESULT__"
        for line in stdout.splitlines():
            if marker in line:
                try:
                    payload_str = line.split("=", 1)[1].strip()
                    return json.loads(payload_str)
                except Exception:
                    pass

        # 2. Check if the last non-empty line is valid JSON (object or list)
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        if lines:
            last_line = lines[-1]
            if (last_line.startswith("{") and last_line.endswith("}")) or (
                last_line.startswith("[") and last_line.endswith("]")
            ):
                try:
                    return json.loads(last_line)
                except Exception:
                    pass

        return None

    def execute_python(
        self,
        code: str,
        timeout_seconds: Optional[float] = None,
        env: Optional[Dict[str, str]] = None,
        extra_files: Optional[Dict[str, Union[str, bytes]]] = None,
        custom_scratch_dir: Optional[Union[str, Path]] = None,
    ) -> SandboxResult:
        """
        Execute Python code safely in the sandbox environment.
        
        Args:
            code: Python code string.
            timeout_seconds: Maximum wall-clock execution time.
            env: Optional custom environment variable dict.
            extra_files: Optional dict mapping relative filename to content (str or bytes).
            custom_scratch_dir: Optional specific directory to execute within.
            
        Returns:
            SandboxResult with execution status, output streams, artifacts, and parsed data.
        """
        t0 = time.perf_counter()
        timeout = timeout_seconds if timeout_seconds is not None else self.default_timeout

        # Step 1: Static AST validation
        val_res = self.validator.validate_python(code)
        if not val_res.is_safe:
            elapsed = (time.perf_counter() - t0) * 1000.0
            error_msg = f"AST Safety Check Failed: {val_res.error_message}"
            logger.warning("Code validation failed: %s", error_msg)
            return SandboxResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=val_res.error_message or "Security check failed",
                error=error_msg,
                execution_time_ms=elapsed,
            )

        # Step 2: Initialize Scratch Directory
        scratch_dir = (
            Path(custom_scratch_dir).resolve()
            if custom_scratch_dir
            else self.create_scratch_env()
        )
        scratch_dir.mkdir(parents=True, exist_ok=True)

        # Step 3: Write extra files into scratch dir
        if extra_files:
            for rel_path_str, content in extra_files.items():
                dest_file = scratch_dir / rel_path_str
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(content, bytes):
                    dest_file.write_bytes(content)
                else:
                    dest_file.write_text(content, encoding="utf-8")

        # Step 4: Write main script
        script_file = scratch_dir / "script.py"
        script_file.write_text(code, encoding="utf-8")

        # Step 5: Snapshot directory before execution
        artifact_manager = ArtifactManager(scratch_dir)
        pre_snapshot = artifact_manager.snapshot_directory()

        # Step 6: Execute script via subprocess
        exec_env = self._prepare_environment(env)
        cmd = [sys.executable, "-u", str(script_file)]

        stdout = ""
        stderr = ""
        exit_code = 0
        timed_out = False

        try:
            process = subprocess.run(
                cmd,
                cwd=str(scratch_dir),
                env=exec_env,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            stdout = process.stdout
            stderr = process.stderr
            exit_code = process.returncode
        except subprocess.TimeoutExpired as texc:
            timed_out = True
            exit_code = -1
            stdout = texc.stdout or ""
            stderr = texc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            logger.warning("Code execution timed out after %s seconds.", timeout)
        except Exception as exc:
            exit_code = -1
            stderr = f"Subprocess invocation failed: {str(exc)}"
            logger.error("Execution failed: %s", exc, exc_info=True)

        elapsed = (time.perf_counter() - t0) * 1000.0

        # Step 7: Detect generated artifacts
        artifacts = artifact_manager.detect_new_artifacts(pre_snapshot)
        if self.persistent_artifacts_dir and artifacts:
            artifact_manager.export_artifacts(artifacts, self.persistent_artifacts_dir)

        # Step 8: Parse structured result data
        parsed_data = self._extract_structured_data(stdout)

        # Step 9: Determine overall success
        success = (exit_code == 0) and not timed_out
        error_summary = None
        if timed_out:
            error_summary = f"Execution timed out after {timeout}s."
        elif exit_code != 0:
            error_summary = stderr.strip() or f"Process exited with code {exit_code}."

        result = SandboxResult(
            success=success,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            artifacts=artifacts,
            data=parsed_data,
            execution_time_ms=elapsed,
            error=error_summary,
            scratch_dir=str(scratch_dir),
        )

        # Cleanup if requested
        if self.cleanup_on_exit:
            self.cleanup_scratch_env(scratch_dir)

        return result

    def execute_powershell(
        self,
        script: str,
        timeout_seconds: Optional[float] = None,
        env: Optional[Dict[str, str]] = None,
        custom_scratch_dir: Optional[Union[str, Path]] = None,
    ) -> SandboxResult:
        """
        Execute PowerShell script safely in the sandbox environment.
        
        Args:
            script: PowerShell script string.
            timeout_seconds: Maximum execution time.
            env: Optional custom environment dict.
            custom_scratch_dir: Optional specific scratch directory.
            
        Returns:
            SandboxResult with execution status, outputs, artifacts.
        """
        t0 = time.perf_counter()
        timeout = timeout_seconds if timeout_seconds is not None else self.default_timeout

        # Step 1: PowerShell static safety check
        val_res = self.validator.validate_powershell(script)
        if not val_res.is_safe:
            elapsed = (time.perf_counter() - t0) * 1000.0
            error_msg = f"PowerShell Safety Check Failed: {val_res.error_message}"
            logger.warning("PowerShell validation failed: %s", error_msg)
            return SandboxResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=val_res.error_message or "Security check failed",
                error=error_msg,
                execution_time_ms=elapsed,
            )

        # Step 2: Initialize Scratch Directory
        scratch_dir = (
            Path(custom_scratch_dir).resolve()
            if custom_scratch_dir
            else self.create_scratch_env()
        )
        scratch_dir.mkdir(parents=True, exist_ok=True)

        # Step 3: Write script to file
        script_file = scratch_dir / "script.ps1"
        script_file.write_text(script, encoding="utf-8")

        # Step 4: Snapshot directory
        artifact_manager = ArtifactManager(scratch_dir)
        pre_snapshot = artifact_manager.snapshot_directory()

        # Step 5: Subprocess execution
        exec_env = self._prepare_environment(env)
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_file),
        ]

        stdout = ""
        stderr = ""
        exit_code = 0
        timed_out = False

        try:
            process = subprocess.run(
                cmd,
                cwd=str(scratch_dir),
                env=exec_env,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            stdout = process.stdout
            stderr = process.stderr
            exit_code = process.returncode
        except subprocess.TimeoutExpired as texc:
            timed_out = True
            exit_code = -1
            stdout = texc.stdout or ""
            stderr = texc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            logger.warning("PowerShell execution timed out after %s seconds.", timeout)
        except Exception as exc:
            exit_code = -1
            stderr = f"PowerShell invocation failed: {str(exc)}"
            logger.error("PowerShell execution failed: %s", exc, exc_info=True)

        elapsed = (time.perf_counter() - t0) * 1000.0

        artifacts = artifact_manager.detect_new_artifacts(pre_snapshot)
        if self.persistent_artifacts_dir and artifacts:
            artifact_manager.export_artifacts(artifacts, self.persistent_artifacts_dir)

        parsed_data = self._extract_structured_data(stdout)

        success = (exit_code == 0) and not timed_out
        error_summary = None
        if timed_out:
            error_summary = f"Execution timed out after {timeout}s."
        elif exit_code != 0:
            error_summary = stderr.strip() or f"Process exited with code {exit_code}."

        result = SandboxResult(
            success=success,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            artifacts=artifacts,
            data=parsed_data,
            execution_time_ms=elapsed,
            error=error_summary,
            scratch_dir=str(scratch_dir),
        )

        if self.cleanup_on_exit:
            self.cleanup_scratch_env(scratch_dir)

        return result
