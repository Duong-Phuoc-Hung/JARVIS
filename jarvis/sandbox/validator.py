"""
Static AST Code Security Validator for JARVIS Sandbox.
Parses code AST before execution to prevent dangerous syscalls, unauthorized
memory inspection, destructive filesystem modifications, and unsafe module imports.
"""
from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("jarvis.sandbox.validator")


@dataclass
class ValidationResult:
    """Outcome of static code validation."""
    is_safe: bool
    violations: list[str] = field(default_factory=list)
    error_message: str | None = None
    syntax_valid: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_safe": self.is_safe,
            "violations": self.violations,
            "error_message": self.error_message,
            "syntax_valid": self.syntax_valid,
        }


class _PythonASTSafetyVisitor(ast.NodeVisitor):
    """
    Traverses Python AST to identify unsafe constructs, forbidden modules,
    forbidden builtins, and dangerous OS/sys attributes.
    """

    def __init__(
        self,
        forbidden_modules: set[str],
        forbidden_calls: set[str],
        forbidden_os_attributes: set[str],
        forbidden_sys_attributes: set[str],
        forbidden_dunder_attributes: set[str],
    ) -> None:
        self.forbidden_modules = forbidden_modules
        self.forbidden_calls = forbidden_calls
        self.forbidden_os_attributes = forbidden_os_attributes
        self.forbidden_sys_attributes = forbidden_sys_attributes
        self.forbidden_dunder_attributes = forbidden_dunder_attributes
        self.violations: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root_mod = alias.name.split(".")[0]
            if root_mod in self.forbidden_modules:
                self.violations.append(
                    f"Forbidden import '{alias.name}' at line {node.lineno}"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            root_mod = node.module.split(".")[0]
            if root_mod in self.forbidden_modules:
                self.violations.append(
                    f"Forbidden from-import module '{node.module}' at line {node.lineno}"
                )
            if root_mod == "os":
                for alias in node.names:
                    if alias.name in self.forbidden_os_attributes:
                        self.violations.append(
                            f"Forbidden import 'os.{alias.name}' at line {node.lineno}"
                        )
            elif root_mod == "sys":
                for alias in node.names:
                    if alias.name in self.forbidden_sys_attributes:
                        self.violations.append(
                            f"Forbidden import 'sys.{alias.name}' at line {node.lineno}"
                        )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Check direct call by name (e.g. eval(...), exec(...))
        if isinstance(node.func, ast.Name):
            if node.func.id in self.forbidden_calls:
                self.violations.append(
                    f"Forbidden function call '{node.func.id}()' at line {node.lineno}"
                )
        # Check method/attribute calls (e.g. os.system(...), sys.modules.get(...))
        elif isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if attr_name in self.forbidden_os_attributes:
                self.violations.append(
                    f"Forbidden call on dangerous attribute '{attr_name}()' at line {node.lineno}"
                )
            if attr_name in self.forbidden_dunder_attributes:
                self.violations.append(
                    f"Forbidden reflection call '{attr_name}()' at line {node.lineno}"
                )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        attr_name = node.attr
        if attr_name in self.forbidden_dunder_attributes:
            self.violations.append(
                f"Forbidden dunder attribute access '{attr_name}' at line {node.lineno}"
            )
        if attr_name in self.forbidden_sys_attributes:
            self.violations.append(
                f"Forbidden sys attribute access '{attr_name}' at line {node.lineno}"
            )
        if isinstance(node.value, ast.Name):
            if node.value.id == "os" and attr_name in self.forbidden_os_attributes:
                self.violations.append(
                    f"Forbidden access 'os.{attr_name}' at line {node.lineno}"
                )
            elif node.value.id == "sys" and attr_name in self.forbidden_sys_attributes:
                self.violations.append(
                    f"Forbidden access 'sys.{attr_name}' at line {node.lineno}"
                )
        self.generic_visit(node)


class ASTCodeValidator:
    """
    Static Code Security Validator for Python and PowerShell scripts.
    Validates code against safety rules before executing in sandbox.
    """

    # Forbidden Python modules (low-level OS tampering, ctypes, win32, raw sockets)
    DEFAULT_FORBIDDEN_MODULES: set[str] = {
        "ctypes",
        "_ctypes",
        "win32api",
        "win32con",
        "win32gui",
        "win32process",
        "win32service",
        "win32file",
        "_winapi",
        "subprocess",
        "multiprocessing",
        "pty",
        "socket",  # Direct socket tampering
        "posix",
        "resource",
        "signal",
    }

    # Forbidden Python built-in functions
    DEFAULT_FORBIDDEN_CALLS: set[str] = {
        "eval",
        "exec",
        "compile",
        "__import__",
        "globals",
        "locals",
        "vars",
        "breakpoint",
    }

    # Forbidden OS attributes / dangerous process spawners
    DEFAULT_FORBIDDEN_OS_ATTRIBUTES: set[str] = {
        "system",
        "popen",
        "popen2",
        "popen3",
        "popen4",
        "spawn",
        "spawne",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
        "fork",
        "forkpty",
        "kill",
        "killpg",
        "plock",
        "abort",
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "execv",
        "execve",
        "execvp",
        "execvpe",
    }

    # Forbidden Sys attributes
    DEFAULT_FORBIDDEN_SYS_ATTRIBUTES: set[str] = {
        "_getframe",
        "settrace",
        "setprofile",
        "call_tracing",
    }

    # Forbidden Dunder attributes (prevents sandbox escaping via class hierarchy reflection)
    DEFAULT_FORBIDDEN_DUNDER_ATTRIBUTES: set[str] = {
        "__subclasses__",
        "__bases__",
        "__base__",
        "__mro__",
        "__globals__",
        "__code__",
        "__builtins__",
    }

    # PowerShell dangerous command regex patterns
    POWERSHELL_DANGEROUS_PATTERNS: list[re.Pattern] = [
        re.compile(r"\b(Format-Volume|Format-Disk|Clear-Disk|Initialize-Disk)\b", re.IGNORECASE),
        re.compile(r"\b(Stop-Computer|Restart-Computer)\b", re.IGNORECASE),
        re.compile(r"\bSet-ExecutionPolicy\b", re.IGNORECASE),
        re.compile(r"\b(Invoke-Expression|\biex\b)\s+", re.IGNORECASE),
        re.compile(r"Remove-Item\b.*(-[rR]ecurse|[cC]:\\Windows|[cC]:\\Program)", re.IGNORECASE),
        re.compile(r"\b(Add-MpPreference|Set-MpPreference)\b.*-Exclusion", re.IGNORECASE),
        re.compile(r"Set-ItemProperty\s+.*HKLM", re.IGNORECASE),
        re.compile(r"\bnet\s+(user|localgroup)\b", re.IGNORECASE),
        re.compile(r"DownloadString\s*\(", re.IGNORECASE),
        re.compile(r"DownloadFile\s*\(", re.IGNORECASE),
    ]

    def __init__(
        self,
        forbidden_modules: set[str] | None = None,
        forbidden_calls: set[str] | None = None,
        forbidden_os_attributes: set[str] | None = None,
        forbidden_sys_attributes: set[str] | None = None,
        forbidden_dunder_attributes: set[str] | None = None,
    ) -> None:
        self.forbidden_modules = forbidden_modules or set(self.DEFAULT_FORBIDDEN_MODULES)
        self.forbidden_calls = forbidden_calls or set(self.DEFAULT_FORBIDDEN_CALLS)
        self.forbidden_os_attributes = forbidden_os_attributes or set(self.DEFAULT_FORBIDDEN_OS_ATTRIBUTES)
        self.forbidden_sys_attributes = forbidden_sys_attributes or set(self.DEFAULT_FORBIDDEN_SYS_ATTRIBUTES)
        self.forbidden_dunder_attributes = forbidden_dunder_attributes or set(self.DEFAULT_FORBIDDEN_DUNDER_ATTRIBUTES)

    def validate_python(self, code: str) -> ValidationResult:
        """
        Statically validate Python code using AST parsing and visitor analysis.
        
        Args:
            code: Source code string to validate.
            
        Returns:
            ValidationResult with safety flag, violation list, and error details.
        """
        if not code or not code.strip():
            return ValidationResult(is_safe=True, violations=[])

        try:
            tree = ast.parse(code)
        except SyntaxError as syn_err:
            logger.warning("Python syntax error during validation: %s", syn_err)
            return ValidationResult(
                is_safe=False,
                violations=[f"SyntaxError: {syn_err.msg} at line {syn_err.lineno}"],
                error_message=f"SyntaxError: {syn_err.msg}",
                syntax_valid=False,
            )
        except Exception as exc:
            logger.error("Unexpected error parsing Python AST: %s", exc)
            return ValidationResult(
                is_safe=False,
                violations=[f"AST Parse Exception: {str(exc)}"],
                error_message=str(exc),
                syntax_valid=False,
            )

        visitor = _PythonASTSafetyVisitor(
            forbidden_modules=self.forbidden_modules,
            forbidden_calls=self.forbidden_calls,
            forbidden_os_attributes=self.forbidden_os_attributes,
            forbidden_sys_attributes=self.forbidden_sys_attributes,
            forbidden_dunder_attributes=self.forbidden_dunder_attributes,
        )
        visitor.visit(tree)

        is_safe = len(visitor.violations) == 0
        error_msg = None if is_safe else "; ".join(visitor.violations)
        return ValidationResult(
            is_safe=is_safe,
            violations=visitor.violations,
            error_message=error_msg,
            syntax_valid=True,
        )

    def validate_powershell(self, script: str) -> ValidationResult:
        """
        Statically validate PowerShell script against dangerous command patterns.
        
        Args:
            script: PowerShell script string.
            
        Returns:
            ValidationResult with safety flag and violation list.
        """
        if not script or not script.strip():
            return ValidationResult(is_safe=True, violations=[])

        violations: list[str] = []
        for pattern in self.POWERSHELL_DANGEROUS_PATTERNS:
            match = pattern.search(script)
            if match:
                violations.append(f"Forbidden PowerShell pattern detected: '{match.group(0)}'")

        is_safe = len(violations) == 0
        error_msg = None if is_safe else "; ".join(violations)
        return ValidationResult(
            is_safe=is_safe,
            violations=violations,
            error_message=error_msg,
            syntax_valid=True,
        )
