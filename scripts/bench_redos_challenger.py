"""
Empirical ReDoS and Massive Input Parsing Latency Benchmark Harness
Milestone 1 Remediation Verification (v4.8.1)
Challenger M1 R2-1
"""
import sys
import time
import json
from jarvis.llm.router import LLMIntentRouter
from jarvis.llm.client import LLMClient


def run_benchmark():
    client = LLMClient(provider="mock")
    router = LLMIntentRouter(client)

    # Warmup
    for _ in range(5):
        router.parse_intent("bật đèn phòng khách", force_llm=False)
        router.parse_intent("bat den phong khach", force_llm=False)
        router.parse_intent("nhạc", force_llm=False)

    test_cases = [
        # 10KB cases
        ("10KB_matching_vietnamese_accented", ("lệnh kiểm tra hệ thống " * 450)), # ~10KB
        ("10KB_matching_embedded_rule", ("a" * 1000 + " bật đèn " + "b" * 1000) * 5), # ~10KB
        ("10KB_non_matching_adversarial_ascii", "a" * 10240), # 10KB
        ("10KB_non_matching_adversarial_vietnamese", "hệ thống không khớp lệnh " * 400), # ~10KB

        # 50KB cases
        ("50KB_matching_embedded_rule", ("a" * 1000 + " bật đèn " + "b" * 1000) * 25), # ~50KB
        ("50KB_matching_vietnamese_accented", ("lệnh kiểm tra hệ thống " * 2200)), # ~50KB
        ("50KB_non_matching_adversarial_ascii", "a" * 51200), # 50KB
        ("50KB_non_matching_adversarial_vietnamese", "hệ thống không khớp lệnh " * 2000), # ~50KB

        # 100KB cases
        ("100KB_matching_embedded_rule", ("a" * 1000 + " bật đèn " + "b" * 1000) * 50), # ~100KB
        ("100KB_matching_vietnamese_accented", ("lệnh kiểm tra hệ thống " * 4400)), # ~100KB
        ("100KB_non_matching_adversarial_ascii", "a" * 102400), # 100KB
        ("100KB_non_matching_adversarial_vietnamese", "hệ thống không khớp lệnh " * 4000), # ~100KB

        # Boundary around 2048 chars
        ("2047B_unaccented_multiword", "bat den phong khach " + "x" * (2047 - len("bat den phong khach "))),
        ("2048B_unaccented_multiword", "bat den phong khach " + "x" * (2048 - len("bat den phong khach "))),
        ("2049B_unaccented_multiword", "bat den phong khach " + "x" * (2049 - len("bat den phong khach "))),
        ("2047B_non_matching", "x" * 2047),
        ("2048B_non_matching", "x" * 2048),
        ("2049B_non_matching", "x" * 2049),
    ]

    results = []

    for name, payload in test_cases:
        length = len(payload)
        timings = []
        # Run 5 iterations per case
        for _ in range(5):
            t0 = time.perf_counter()
            res = router.parse_intent(payload, force_llm=False)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            timings.append(dt_ms)

        avg_ms = sum(timings) / len(timings)
        min_ms = min(timings)
        max_ms = max(timings)

        results.append({
            "test_case": name,
            "length_chars": length,
            "avg_ms": round(avg_ms, 4),
            "min_ms": round(min_ms, 4),
            "max_ms": round(max_ms, 4),
            "action_name": res.action_name,
            "source": res.source,
        })

    # Standard query regression checks
    standard_cases = [
        ("bật đèn phòng khách", "home_assistant_call", True),
        ("bat den phong khach", "home_assistant_call", True),
        ("nhạc", "media_control", True),
        ("nhắc", "reminder_set", True),
        ("dừng", "media_control", True),
        ("dụng", "unknown_intent", False),
        ("kiểm tra cpu", "hardware_status_query", True),
        ("thời tiết hôm nay", "weather_query", True),
    ]

    standard_results = []
    for q, expected_action, expected_success in standard_cases:
        t0 = time.perf_counter()
        res = router.parse_intent(q, force_llm=False)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        match = (res.action_name == expected_action)
        standard_results.append({
            "query": q,
            "expected": expected_action,
            "actual": res.action_name,
            "match": match,
            "latency_ms": round(dt_ms, 4)
        })

    report = {
        "benchmarks": results,
        "standard_validation": standard_results
    }

    print("=== BENCHMARK REPORT ===")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return report


def test_bench_redos_10kb_50kb_100kb():
    """Verify that 10KB, 50KB, and 100KB queries parse well within ReDoS SLA."""
    client = LLMClient(provider="mock")
    router = LLMIntentRouter(client)

    # 10KB
    ten_kb = ("a" * 1000 + " bật đèn " + "b" * 1000) * 5
    t0 = time.perf_counter()
    res_10k = router.parse_intent(ten_kb, force_llm=False)
    dt_10k = (time.perf_counter() - t0) * 1000.0
    assert dt_10k < 10.0, f"10KB took {dt_10k:.2f}ms"
    assert res_10k.action_name == "home_assistant_call"

    # 50KB
    fifty_kb = ("a" * 1000 + " bật đèn " + "b" * 1000) * 25
    t1 = time.perf_counter()
    res_50k = router.parse_intent(fifty_kb, force_llm=False)
    dt_50k = (time.perf_counter() - t1) * 1000.0
    assert dt_50k < 10.0, f"50KB took {dt_50k:.2f}ms (> 10.0ms target)"
    assert res_50k.action_name == "home_assistant_call"

    # 100KB
    hundred_kb = ("a" * 1000 + " bật đèn " + "b" * 1000) * 50
    t2 = time.perf_counter()
    res_100k = router.parse_intent(hundred_kb, force_llm=False)
    dt_100k = (time.perf_counter() - t2) * 1000.0
    assert dt_100k < 20.0, f"100KB took {dt_100k:.2f}ms (> 20.0ms)"
    assert res_100k.action_name == "home_assistant_call"


def test_bench_boundary_2048_chars():
    """Verify boundary conditions around 2048 chars threshold."""
    client = LLMClient(provider="mock")
    router = LLMIntentRouter(client)

    # 2047 chars with unaccented multi-word matching
    pad_2047 = "bat den phong khach " + "x" * (2047 - len("bat den phong khach "))
    t0 = time.perf_counter()
    res_2047 = router.parse_intent(pad_2047, force_llm=False)
    dt_2047 = (time.perf_counter() - t0) * 1000.0
    assert dt_2047 < 10.0
    assert res_2047.action_name == "home_assistant_call"

    # 2048 chars
    pad_2048 = "bat den phong khach " + "x" * (2048 - len("bat den phong khach "))
    t1 = time.perf_counter()
    res_2048 = router.parse_intent(pad_2048, force_llm=False)
    dt_2048 = (time.perf_counter() - t1) * 1000.0
    assert dt_2048 < 10.0
    assert res_2048.action_name == "home_assistant_call"

    # 2049 chars: length guard triggers, skipping diacritic folding
    pad_2049_unaccented = "bat den phong khach " + "x" * (2049 - len("bat den phong khach "))
    t2 = time.perf_counter()
    res_2049_unaccented = router.parse_intent(pad_2049_unaccented, force_llm=False)
    dt_2049 = (time.perf_counter() - t2) * 1000.0
    assert dt_2049 < 10.0
    # Accented exact match still works > 2048
    pad_2049_accented = "bật đèn phòng khách " + "x" * (2049 - len("bật đèn phòng khách "))
    res_2049_accented = router.parse_intent(pad_2049_accented, force_llm=False)
    assert res_2049_accented.action_name == "home_assistant_call"


def test_bench_standard_and_homophones():
    """Verify standard single-word and multi-word queries with homophone isolation."""
    client = LLMClient(provider="mock")
    router = LLMIntentRouter(client)

    assert router.parse_intent("bật đèn phòng khách", force_llm=False).action_name == "home_assistant_call"
    assert router.parse_intent("bat den phong khach", force_llm=False).action_name == "home_assistant_call"
    assert router.parse_intent("nhạc", force_llm=False).action_name == "media_control"
    assert router.parse_intent("nhắc", force_llm=False).action_name == "reminder_set"
    assert router.parse_intent("dừng", force_llm=False).action_name == "media_control"
    assert router.parse_intent("dụng", force_llm=False).action_name != "media_control"


if __name__ == "__main__":
    run_benchmark()

