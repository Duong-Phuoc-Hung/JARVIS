"""
run_challenger2_tests.py
Custom Empirical Test Runner for Challenger 2
"""
import sys
import unittest
import pytest

def main():
    print("=" * 60)
    print("CHALLENGER 2: EMPIRICAL STRESS TEST SUITE")
    print("=" * 60)

    # 1. Run Challenger 2 specific stress suite
    print("\n--- Running tests/test_challenger2_stress.py ---")
    ret_stress = pytest.main(["-v", "tests/test_challenger2_stress.py"])

    # 2. Run E2E Test Suite
    print("\n--- Running tests/e2e/test_tiers_1_to_4.py ---")
    ret_e2e = pytest.main(["-v", "tests/e2e/test_tiers_1_to_4.py"])

    # 3. Run R5-R8 Unit Tests
    print("\n--- Running R5-R8 Unit Tests ---")
    ret_unit = pytest.main([
        "-v",
        "tests/unit/test_web_intelligence.py",
        "tests/unit/test_proactive_engine.py",
        "tests/unit/test_shell_assistant.py",
        "tests/unit/test_always_on_overlay.py",
    ])

    print("\n" + "=" * 60)
    print(f"Results Summary: Stress={ret_stress}, E2E={ret_e2e}, Unit={ret_unit}")
    print("=" * 60)

if __name__ == "__main__":
    main()
