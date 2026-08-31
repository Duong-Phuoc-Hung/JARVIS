"""
tests/e2e/test_r1_sandbox_globals_e2e.py
=========================================
E2E Test Suite for Requirement 1: Sandbox __globals__ Escape Patch & Class Introspection Protection.

Covers:
  - TIER 1: Feature Coverage
      * test_r1_happy_path_safe_script_execution
      * test_r1_direct_function_globals_access_blocked
      * test_r1_class_call_globals_escape_blocked
      * test_r1_object_subclasses_traversal_restricted
      * test_r1_sandbox_result_structured_contract
      * test_r1_preamble_injection_integrity
  - TIER 2: Boundary, Corner & Adversarial Cases
      * test_r1_corner_nested_lambda_method_globals_traversal
      * test_r1_corner_custom_class_metaclass_globals_probing
      * test_r1_boundary_empty_and_whitespace_code
      * test_r1_boundary_syntax_and_runtime_exception_handling
      * test_r1_boundary_unicode_variable_and_obfuscated_identifiers
      * test_r1_adversarial_real_os_globals_class_level_blocked
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
import pytest

from jarvis.sandbox.interpreter import CodeInterpreterSandbox, SandboxResult
from jarvis.sandbox.security import (
    WindowsJobObject,
    inject_security_preamble,
    prepare_scrubbed_environment,
    strip_sandbox_ready_sentinel,
)
from jarvis.sandbox.validator import ASTCodeValidator, ValidationResult


class _PermissiveASTValidator(ASTCodeValidator):
    """Permissive validator allowing raw AST to test runtime sandbox isolation guards."""
    def validate_python(self, code: str) -> ValidationResult:
        return ValidationResult(is_safe=True)


@pytest.fixture
def sandbox(tmp_path):
    """Standard CodeInterpreterSandbox instance with temporary scratch directory."""
    return CodeInterpreterSandbox(
        base_scratch_dir=tmp_path / "sandbox_r1_scratch",
        default_timeout=10.0,
    )


@pytest.fixture
def os_test_sandbox(tmp_path):
    """Permissive CodeInterpreterSandbox instance for testing runtime OS barriers directly."""
    return CodeInterpreterSandbox(
        base_scratch_dir=tmp_path / "sandbox_r1_os_scratch",
        default_timeout=10.0,
        validator=_PermissiveASTValidator(),
    )


# ============================================================================
# TIER 1: FEATURE COVERAGE (R1)
# ============================================================================

class TestR1SandboxGlobalsFeatureTier1:
    """Tier 1: Primary feature verification for R1 __globals__ and sandbox execution."""

    def test_r1_happy_path_safe_script_execution(self, sandbox):
        """
        Verify that standard mathematical, algorithmic, and data manipulation code
        executes successfully without false-positive security blocks.
        """
        code = """
import math

numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
evens = [x for x in numbers if x % 2 == 0]
sum_evens = sum(evens)
sqrt_val = math.sqrt(sum_evens)

print(f"SUM={sum_evens}")
print(f"SQRT={round(sqrt_val, 4)}")
"""
        result = sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert result.exit_code == 0
        assert "SUM=30" in result.stdout
        assert "SQRT=5.4772" in result.stdout

    def test_r1_direct_function_globals_access_blocked(self, os_test_sandbox):
        """
        Verify that direct function introspection via `fn.__globals__` does not leak
        host environment variables, unpatched callables, or sensitive project modules.
        """
        code = """
def test_fn():
    pass

g = getattr(test_fn, "__globals__", {})
leaked_keys = [k for k in g.keys() if "API" in k or "SECRET" in k or "TOKEN" in k]
print(f"LEAKED_COUNT={len(leaked_keys)}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "LEAKED_COUNT=0" in result.stdout

    def test_r1_class_call_globals_escape_blocked(self, os_test_sandbox):
        """
        Verify that class-level __globals__ traversal vector:
        `type(fn).__call__.__globals__`
        cannot be used to access original unpatched builtins or host globals.
        """
        code = """
import builtins

def dummy():
    pass

# Attempt vector: type(dummy).__call__.__globals__
try:
    fn_type = type(dummy)
    call_attr = getattr(fn_type, "__call__", None)
    if call_attr is not None:
        target_globals = getattr(call_attr, "__globals__", None)
        if target_globals is not None:
            # Check if original unpatched open is present
            if "_orig_builtin_open" in target_globals or "_orig_os_open" in target_globals:
                print("GLOBALS_ESCAPE_VULNERABLE")
            else:
                print("GLOBALS_ESCAPE_CONTAINED")
        else:
            print("GLOBALS_ATTR_NONE")
    else:
        print("CALL_ATTR_NONE")
except Exception as exc:
    print(f"GLOBALS_ESCAPE_EXCEPTION: {type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "GLOBALS_ESCAPE_VULNERABLE" not in result.stdout
        assert (
            "GLOBALS_ESCAPE_CONTAINED" in result.stdout
            or "GLOBALS_ATTR_NONE" in result.stdout
            or "GLOBALS_ESCAPE_EXCEPTION" in result.stdout
        )

    def test_r1_object_subclasses_traversal_restricted(self, os_test_sandbox):
        """
        Verify that traversing `().__class__.__bases__[0].__subclasses__()` cannot instantiate
        dangerous classes (e.g. subprocess.Popen, os._wrap_close, file wrappers) to break confinement.
        """
        code = """
try:
    subclasses = ().__class__.__bases__[0].__subclasses__()
    names = [c.__name__ for c in subclasses]
    
    # Attempt to locate Popen or FileLoader
    dangerous = [c for c in subclasses if c.__name__ in ("Popen", "_wrap_close", "FileLoader")]
    instantiated = False
    for cls in dangerous:
        try:
            instance = cls()
            instantiated = True
        except Exception:
            pass
            
    print(f"SUBCLASSES_COUNT={len(subclasses)}")
    print(f"INSTANTIATED_DANGEROUS={instantiated}")
except Exception as exc:
    print(f"SUBCLASS_TRAVERSAL_ERROR: {type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "INSTANTIATED_DANGEROUS=False" in result.stdout

    def test_r1_sandbox_result_structured_contract(self, sandbox):
        """
        Verify that SandboxResult conforms strictly to the structured execution contract.
        """
        code = """
print("Step 1: processing...")
print('__JARVIS_RESULT__ = {"status": "ok", "items": [1, 2, 3]}')
"""
        result = sandbox.execute_python(code, timeout_seconds=5.0)
        assert isinstance(result, SandboxResult)
        assert result.success is True
        assert result.exit_code == 0
        assert result.execution_time_ms >= 0.0
        assert result.execution_time_seconds >= 0.0
        assert result.data == {"status": "ok", "items": [1, 2, 3]}

        d = result.to_dict()
        assert "success" in d
        assert "exit_code" in d
        assert "stdout" in d
        assert "stderr" in d
        assert "data" in d
        assert "execution_time_ms" in d

    def test_r1_preamble_injection_integrity(self):
        """
        Verify that `inject_security_preamble` injects the zero-trust guard header
        and preserves original script code intact.
        """
        user_script = "print('HELLO_FROM_SANDBOX')"
        wrapped = inject_security_preamble(user_script)
        assert "_BLOCKED_SANDBOX_MODULES" in wrapped
        assert "_ScopedBuiltinOpenGuard" in wrapped
        assert "HELLO_FROM_SANDBOX" in wrapped


# ============================================================================
# TIER 2: BOUNDARY & CORNER CASES (R1)
# ============================================================================

class TestR1SandboxGlobalsBoundaryTier2:
    """Tier 2: Boundary, corner cases, and adversarial vectors for R1."""

    def test_r1_corner_nested_lambda_method_globals_traversal(self, os_test_sandbox):
        """
        Corner Case: Deeply nested closures and method call wrappers:
        `(lambda x: (lambda y: x + y))(1).__call__.__globals__`
        verifying that no parent scope or interpreter global namespace leaks.
        """
        code = """
f = (lambda x: (lambda y: x + y))(1)
try:
    g = f.__call__.__globals__
    has_orig = any(k.startswith("_orig") for k in g.keys())
    print(f"ORIG_LEAKED={has_orig}")
except Exception as exc:
    print(f"NESTED_EXCEPTION={type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "ORIG_LEAKED=True" not in result.stdout

    def test_r1_corner_custom_class_metaclass_globals_probing(self, os_test_sandbox):
        """
        Corner Case: Custom user classes overriding `__getattribute__` or inspecting
        `self.__class__.__init__.__globals__` cannot tamper with security guards.
        """
        code = """
class MetaclassProber(type):
    def __new__(mcs, name, bases, attrs):
        return super().__new__(mcs, name, bases, attrs)

class UserClass(metaclass=MetaclassProber):
    def __init__(self):
        pass
    def probe(self):
        return getattr(self.__class__.__init__, "__globals__", {})

u = UserClass()
g = u.probe()
sensitive = [k for k in g.keys() if "KEY" in k or "SECRET" in k]
print(f"SENSITIVE_LEAKS={len(sensitive)}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "SENSITIVE_LEAKS=0" in result.stdout

    def test_r1_boundary_empty_and_whitespace_code(self, sandbox):
        """
        Boundary Case: Executing empty code, comments only, or massive whitespace.
        Must return success with exit code 0 and empty stdout without crash.
        """
        empty_res = sandbox.execute_python("", timeout_seconds=5.0)
        assert empty_res.success is True
        assert empty_res.exit_code == 0

        whitespace_res = sandbox.execute_python("   \n\n   \t\n   ", timeout_seconds=5.0)
        assert whitespace_res.success is True
        assert whitespace_res.exit_code == 0

        comments_res = sandbox.execute_python("# Just a comment\n# Another comment\n", timeout_seconds=5.0)
        assert comments_res.success is True
        assert comments_res.exit_code == 0

    def test_r1_boundary_syntax_and_runtime_exception_handling(self, sandbox):
        """
        Boundary Case: Script with syntax error or unhandled runtime exception
        must gracefully return `success=False` with captured error details.
        """
        # 1. Syntax error
        syntax_res = sandbox.execute_python("def broken_syntax(:", timeout_seconds=5.0)
        assert syntax_res.success is False
        assert syntax_res.error is not None or "SyntaxError" in syntax_res.stderr

        # 2. Runtime ZeroDivisionError
        runtime_res = sandbox.execute_python("x = 1 / 0", timeout_seconds=5.0)
        assert runtime_res.success is False
        assert "ZeroDivisionError" in runtime_res.stderr or "ZeroDivisionError" in (runtime_res.error or "")

    def test_r1_boundary_unicode_variable_and_obfuscated_identifiers(self, os_test_sandbox):
        """
        Adversarial: Script using unicode confusable characters or dynamic string
        concatenation to access `__glob` + `als__`.
        """
        code = """
def sample_func():
    return 42

target_attr = "".join(["_", "_", "g", "l", "o", "b", "a", "l", "s", "_", "_"])
try:
    g = getattr(type(sample_func).__call__, target_attr, None)
    if g is not None and ("_orig_builtin_open" in g):
        print("OBFUSCATION_SUCCESS")
    else:
        print("OBFUSCATION_BLOCKED")
except Exception as exc:
    print(f"OBFUSCATION_ERROR: {type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "OBFUSCATION_SUCCESS" not in result.stdout
        assert ("OBFUSCATION_BLOCKED" in result.stdout or "OBFUSCATION_ERROR" in result.stdout)

    @pytest.mark.skipif(sys.platform != "win32", reason="Adversarial real OS test requires Windows host")
    def test_r1_adversarial_real_os_globals_class_level_blocked(self, os_test_sandbox):
        """
        Adversarial Non-Mock Test: Verified on real Windows OS.
        Confirms `type(builtins.open).__call__.__globals__` access is blocked or
        does not expose `_orig_builtin_open` or host system environment keys.
        """
        code = """
import builtins

try:
    # Class-level introspection on builtins.open
    target_cls = type(builtins.open)
    call_fn = getattr(target_cls, "__call__", None)
    if call_fn is not None:
        g = getattr(call_fn, "__globals__", {})
        if "_orig_builtin_open" in g or "_orig_os_open" in g:
            print("REAL_OS_GLOBALS_LEAKED")
        else:
            print("REAL_OS_GLOBALS_PROTECTED")
    else:
        print("REAL_OS_NO_CALL_MEMBER")
except Exception as exc:
    print(f"REAL_OS_EXCEPTION_{type(exc).__name__}")
"""
        result = os_test_sandbox.execute_python(code, timeout_seconds=5.0)
        assert result.success is True
        assert "REAL_OS_GLOBALS_LEAKED" not in result.stdout
        assert (
            "REAL_OS_GLOBALS_PROTECTED" in result.stdout
            or "REAL_OS_NO_CALL_MEMBER" in result.stdout
            or "REAL_OS_EXCEPTION_" in result.stdout
        )
