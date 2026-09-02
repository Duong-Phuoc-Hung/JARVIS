"""
tests/eval/run_m5_pytest_suite.py
=================================
Programmatic test runner for Worker M5 verification suite.
Runs pytest on:
- tests/unit/test_router_hardware.py
- tests/test_hardware_monitor.py
- tests/test_adversarial_*.py
"""
import sys
import pytest

if __name__ == "__main__":
    args = [
        "tests/unit/test_router_hardware.py",
        "tests/test_hardware_monitor.py",
        "tests/test_adversarial_challenger_1.py",
        "tests/test_adversarial_harness.py",
        "tests/test_adversarial_m1.py",
        "tests/test_adversarial_m1_intent_router.py",
        "tests/test_adversarial_m2_audio_gesture.py",
        "tests/test_adversarial_m2_llm_router.py",
        "tests/test_adversarial_m3_challenger1.py",
        "tests/test_adversarial_m3_stt_llm.py",
        "tests/test_adversarial_m3_ui_app.py",
        "tests/test_adversarial_m4_challenger1.py",
        "tests/test_adversarial_m5_2.py",
        "tests/test_adversarial_m5_challenger1.py",
        "-v",
    ]
    ret = pytest.main(args)
    sys.exit(ret)
