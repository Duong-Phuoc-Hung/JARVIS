"""
tests/eval/run_victory_audit_tests.py
======================================
Independent Victory Audit Test Runner for Sprint 2 (v4.7.0).
Executes:
1. Pytest on tests/unit/
2. Pytest on tests/test_adversarial_*.py
3. Routing eval tests/eval/routing_eval_n150.py
4. Package version verification
"""
import sys
import os
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

def main():
    print("=" * 70)
    print("VICTORY AUDITOR INDEPENDENT TEST EXECUTION")
    print("=" * 70)
    
    # 1. Verify package version
    import jarvis
    version = getattr(jarvis, "__version__", None)
    print(f"\n[1] Package Version Check: jarvis.__version__ = {version!r}")
    assert version == "4.7.0", f"Version mismatch: expected '4.7.0', got {version!r}"
    print("  --> Version check: PASS")

    # 2. Run pytest on tests/unit/
    print("\n[2] Executing pytest on tests/unit/ ...")
    unit_args = ["tests/unit/", "-q", "--tb=short"]
    ret_unit = pytest.main(unit_args)
    print(f"  --> tests/unit/ pytest exit code: {ret_unit}")
    
    # 3. Run pytest on adversarial test suites
    print("\n[3] Executing pytest on adversarial test suites ...")
    adv_files = [
        str(p) for p in (ROOT / "tests").glob("test_adversarial_*.py")
    ]
    adv_args = adv_files + ["-q", "--tb=short"]
    ret_adv = pytest.main(adv_args)
    print(f"  --> tests/test_adversarial_*.py pytest exit code: {ret_adv}")

    # 4. Run routing eval
    print("\n[4] Executing routing_eval_n150.py ...")
    from tests.eval.routing_eval_n150 import run_eval
    run_eval(verbose=False)

    print("\n" + "=" * 70)
    print("INDEPENDENT AUDIT SUMMARY:")
    print(f"  Version 4.7.0: PASS")
    print(f"  Unit tests exit code: {ret_unit} ({'PASS' if ret_unit == 0 else 'FAIL'})")
    print(f"  Adversarial tests exit code: {ret_adv} ({'PASS' if ret_adv == 0 else 'FAIL'})")
    print("=" * 70)

    if ret_unit != 0 or ret_adv != 0:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
