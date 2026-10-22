"""
scripts/argon_boundary_analysis.py
==================================
Argon Boundary Probability & Tail Latency Analysis across 15 Intent Domains.
Examines:
  1. Multiclass probability margins on ambiguous/borderline utterances.
  2. High-resolution latency tail percentiles (p50, p90, p95, p99, p99.9) on CPU.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from jarvis.llm.local_classifier import VietnameseNLPClassifier


def analyze_boundary_probabilities():
    print("=" * 68)
    print("🔬 REA x ARGON DEEP-DIVE: 15-DOMAIN BOUNDARY PROBABILITIES & LATENCY TAIL")
    print("=" * 68)

    clf = VietnameseNLPClassifier()

    boundary_cases = [
        # Volume vs Brightness border
        ("cho to lên một chút", "system_volume"),
        ("tối quá không thấy gì", "system_brightness"),
        ("sáng quá chói mắt", "system_brightness"),
        ("cho lớn hết cỡ", "system_volume"),

        # App vs Smart Home border
        ("bật quạt", "smart_home"),
        ("mở quạt trần", "smart_home"),
        ("chạy máy tính", "app_launch"),
        ("mở ứng dụng đèn", "app_launch"),

        # Window vs App Close border
        ("thu nhỏ cửa sổ này", "window_management"),
        ("đóng cửa sổ này đi", "app_close"),
        ("chia đôi màn hình sang trái", "window_management"),

        # File vs App Launch border
        ("mở thư mục tải về", "file_management"),
        ("mở file explorer", "app_launch"),
        ("dọn dẹp thùng rác", "file_management"),

        # Clipboard vs System border
        ("sao chép đoạn này", "clipboard_action"),
        ("dán vào đây", "clipboard_action"),
        ("xóa clipboard", "clipboard_action"),

        # Network vs System Status border
        ("kiểm tra kết nối mạng wifi", "network_control"),
        ("đo tốc độ internet", "network_control"),
        ("kiểm tra tình trạng máy tính", "system_status"),

        # Power vs App Close border
        ("khóa màn hình máy tính", "system_power"),
        ("cho máy tính đi ngủ", "system_power"),
        ("hẹn giờ tắt máy tính sau 30 phút", "system_power"),

        # Web Search vs Greeting vs Unknown
        ("hôm nay trời thế nào bạn ơi", "web_search"),
        ("bạn là ai thế", "greeting_chat"),
        ("nghĩ gì về cuộc sống", "unknown"),
        ("qwertyuiop123456", "unknown"),
    ]

    print("\n[1] 15-DOMAIN BORDER CLASS PROBABILITY DISTRIBUTIONS:")
    correct_count = 0
    for text, expected in boundary_cases:
        res = clf.predict(text)
        sorted_scores = sorted(res.all_scores.items(), key=lambda x: x[1], reverse=True)[:3]
        top3_str = ", ".join([f"{k}: {v*100:.1f}%" for k, v in sorted_scores])
        is_match = (res.intent == expected) or (expected == "unknown" and res.confidence < 0.45)
        if is_match:
            correct_count += 1
        match_symbol = "✅" if is_match else "⚠️"
        print(f"  {match_symbol} Utterance: '{text}'")
        print(f"     Expected: {expected} | Actual: {res.intent} (conf: {res.confidence:.3f})")
        print(f"     Top-3: [{top3_str}]")

    print(f"\n  Boundary Accuracy: {correct_count}/{len(boundary_cases)} ({correct_count / len(boundary_cases) * 100:.1f}%)")

    # High-resolution Latency Tail Analysis (2,500 iterations)
    print("\n[2] HIGH-RESOLUTION LATENCY TAIL PROFILE (N=2,500 RUNS ON PHYSICAL CPU):")
    sample_queries = [
        "tăng âm lượng lên 20%",
        "bat den phong khach",
        "mở google chrome",
        "thời tiết hôm nay",
        "chia đôi màn hình sang trái",
    ]

    # Warmup
    for q in sample_queries:
        _ = clf.predict(q)

    all_latencies: list[float] = []
    N_ROUNDS = 500  # 500 * 5 = 2,500 queries
    for _ in range(N_ROUNDS):
        for q in sample_queries:
            t0 = time.perf_counter()
            _ = clf.predict(q)
            all_latencies.append((time.perf_counter() - t0) * 1000.0)

    arr = np.array(all_latencies)
    print(f"  - Total Real Runs:   {len(arr):,}")
    print(f"  - Mean Latency:      {np.mean(arr):.2f} ms")
    print(f"  - p50 (Median):      {np.percentile(arr, 50):.2f} ms")
    print(f"  - p90:               {np.percentile(arr, 90):.2f} ms")
    print(f"  - p95:               {np.percentile(arr, 95):.2f} ms")
    print(f"  - p99:               {np.percentile(arr, 99):.2f} ms")
    print(f"  - p99.9:             {np.percentile(arr, 99.9):.2f} ms")
    print(f"  - Max Jitter:        {np.max(arr):.2f} ms")
    print("\n✅ ARGON BOUNDARY & LATENCY TAIL ANALYSIS COMPLETE!")


if __name__ == "__main__":
    analyze_boundary_probabilities()
