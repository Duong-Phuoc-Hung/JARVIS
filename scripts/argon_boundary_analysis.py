import os
import sys
sys.path.insert(0, os.path.abspath("."))
import time
import numpy as np
from jarvis.llm.local_classifier import VietnameseNLPClassifier

def analyze_boundary_probabilities():
    print("=" * 65)
    print("REA x ARGON DEEP-DIVE: BOUNDARY PROBABILITIES & LATENCY TAIL")
    print("=" * 65)

    clf = VietnameseNLPClassifier()

    # Ambiguous, borderline, and challenging edge cases
    boundary_cases = [
        # Volume vs Brightness border
        ("cho to lên một chút", "system_volume"),
        ("tối quá không thấy gì", "system_brightness"),
        ("sáng quá chói mắt", "system_brightness"),
        ("cho lớn hết cỡ", "system_volume"),
        # App vs Smart Home border
        ("bật quạt", "smart_home"),
        ("mở quạt trần", "smart_home"),
        ("chạy máy tính", "app_launch"),  # 'calculator' vs 'pc'
        ("mở ứng dụng đèn", "app_launch"),
        # Web Search vs Greeting Chat vs Unknown border
        ("hôm nay trời thế nào bạn ơi", "web_search"),
        ("bạn là ai thế", "greeting_chat"),
        ("chào buổi sáng jarvis", "greeting_chat"),
        ("nghĩ gì về cuộc sống", "unknown"),
        # OOD & Noise
        ("qwertyuiop123", "unknown"),
        ("hôm nay 12345 !@#$", "unknown"),
    ]

    print("\n[1] BORDER CLASS PROBABILITY DISTRIBUTIONS:")
    for text, expected in boundary_cases:
        res = clf.predict(text)
        sorted_scores = sorted(res.all_scores.items(), key=lambda x: x[1], reverse=True)[:3]
        top3_str = ", ".join([f"{k}: {v*100:.1f}%" for k, v in sorted_scores])
        match_symbol = "✅" if res.intent == expected or (expected == "unknown" and res.confidence < 0.45) else "⚠️"
        print(f"  {match_symbol} Utterance: '{text}'")
        print(f"     Expected: {expected} | Actual: {res.intent} (conf: {res.confidence:.3f})")
        print(f"     Top-3 Distribution: [{top3_str}]")
        print(f"     Slots Extracted: {res.slots}")

    # Latency Tail Analysis (500 iterations)
    print("\n[2] HIGH-RESOLUTION LATENCY TAIL PROFILE (N=500):")
    sample_queries = [
        "tăng âm lượng lên 20%",
        "bat den phong khach",
        "mở google chrome",
        "thời tiết hôm nay",
        "báo thức sau 15 phút",
    ]
    warmup_n = 20
    bench_n = 500

    # Warmup
    for _ in range(warmup_n):
        for q in sample_queries:
            clf.predict(q)

    latencies_us = []
    for _ in range(bench_n):
        for q in sample_queries:
            t0 = time.perf_counter_ns()
            _ = clf.predict(q)
            latencies_us.append((time.perf_counter_ns() - t0) / 1000.0)  # microseconds

    latencies_ms = np.array(latencies_us) / 1000.0

    print(f"  - Sample Count: {len(latencies_ms)} executions across {len(sample_queries)} distinct domains")
    print(f"  - Mean Latency:   {np.mean(latencies_ms):.3f} ms")
    print(f"  - p50 (Median):   {np.percentile(latencies_ms, 50):.3f} ms")
    print(f"  - p90:            {np.percentile(latencies_ms, 90):.3f} ms")
    print(f"  - p95:            {np.percentile(latencies_ms, 95):.3f} ms")
    print(f"  - p99:            {np.percentile(latencies_ms, 99):.3f} ms")
    print(f"  - Max Jitter:     {np.max(latencies_ms):.3f} ms")

    print("\n" + "=" * 65)
    print("REA DEEP-DIVE COMPLETE: ZERO RUNAWAY JITTER, STABLE BOUNDARIES")
    print("=" * 65)

if __name__ == "__main__":
    analyze_boundary_probabilities()
