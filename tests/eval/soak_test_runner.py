"""
tests/eval/soak_test_runner.py
==============================
H-09: Soak Test & Runaway Leak Detection Framework for JARVIS Beta v1.

Monitors memory (WorkingSet / PrivateBytes), Windows kernel handles,
and thread counts over extended execution periods (e.g. 60s smoke, 30m, 2h, 8h).
Calculates linear regression trends to detect creeping leaks before production release.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psutil

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


@dataclass
class SoakDataPoint:
    timestamp: float
    elapsed_s: float
    cpu_percent: float
    working_set_mb: float
    private_bytes_mb: float
    handle_count: int
    thread_count: int


@dataclass
class SoakSummary:
    duration_s: float
    samples_count: int
    avg_cpu_percent: float
    initial_working_set_mb: float
    final_working_set_mb: float
    peak_working_set_mb: float
    working_set_slope_mb_per_hr: float
    initial_handles: int
    final_handles: int
    peak_handles: int
    handle_slope_per_hr: float
    peak_threads: int
    passed: bool
    status_notes: list[str]


def compute_linear_slope(x: list[float], y: list[float]) -> float:
    """Computes ordinary least-squares slope (dy/dx)."""
    n = len(x)
    if n < 2:
        return 0.0
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    denom = sum((xi - mean_x) ** 2 for xi in x)
    if abs(denom) < 1e-9:
        return 0.0
    numer = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    return numer / denom


def run_synthetic_traffic_tick() -> None:
    """Executes representative internal operations to exercise garbage collector and resource handles."""
    from jarvis.core.dispatcher import ActionDispatcher
    from jarvis.comms.rate_limiter import TokenBucketRateLimiter, RateLimitConfig

    # 1. Exercise dispatcher & action lookup
    dispatcher = ActionDispatcher()
    dispatcher.register_action("ping", lambda: {"status": "pong"})
    _ = dispatcher.dispatch_action("ping")

    # 2. Exercise rate limiter
    limiter = TokenBucketRateLimiter(RateLimitConfig(requests_per_minute=60, burst_limit=10))
    _ = limiter.acquire("soak_test_client")


def run_soak_test(
    target_pid: int | None = None,
    duration_s: float = 30.0,
    interval_s: float = 1.0,
    out_json: Path | None = None,
    max_memory_slope_mb_per_hr: float = 50.0,
    max_handle_slope_per_hr: float = 20.0,
) -> SoakSummary:
    """
    Runs the soak test monitoring loop and evaluates pass/fail gates.
    """
    proc = psutil.Process(target_pid) if target_pid else psutil.Process()
    # Prime cpu_percent
    proc.cpu_percent(interval=None)

    data_points: list[SoakDataPoint] = []
    t_start = time.monotonic()
    t_end = t_start + duration_s

    print(f"Starting JARVIS Soak Test (PID {proc.pid}) for {duration_s:.1f}s (sampling every {interval_s:.1f}s)...")

    while time.monotonic() < t_end:
        now = time.monotonic()
        elapsed = now - t_start

        # Run synthetic workload if monitoring self
        if target_pid is None or target_pid == os.getpid():
            run_synthetic_traffic_tick()

        cpu = proc.cpu_percent(interval=None)
        mem_info = proc.memory_info()
        ws_mb = mem_info.rss / (1024 * 1024)
        pb_mb = getattr(mem_info, "private", mem_info.rss) / (1024 * 1024)

        handles = proc.num_handles() if hasattr(proc, "num_handles") else 0
        threads = proc.num_threads() if hasattr(proc, "num_threads") else 0

        point = SoakDataPoint(
            timestamp=time.time(),
            elapsed_s=round(elapsed, 2),
            cpu_percent=round(cpu, 1),
            working_set_mb=round(ws_mb, 2),
            private_bytes_mb=round(pb_mb, 2),
            handle_count=handles,
            thread_count=threads,
        )
        data_points.append(point)

        print(
            f"  [{elapsed:>5.1f}s] CPU: {cpu:>4.1f}% | RAM: {ws_mb:>6.2f} MB | "
            f"Handles: {handles:>4d} | Threads: {threads:>3d}"
        )

        sleep_time = min(interval_s, max(0.0, t_end - time.monotonic()))
        if sleep_time > 0:
            time.sleep(sleep_time)

    # Evaluation
    dur = time.monotonic() - t_start
    n = len(data_points)
    times = [p.elapsed_s for p in data_points]
    rams = [p.working_set_mb for p in data_points]
    handles_list = [float(p.handle_count) for p in data_points]

    # Calculate trends per hour (slope * 3600)
    ram_slope_per_hr = compute_linear_slope(times, rams) * 3600.0
    handle_slope_per_hr = compute_linear_slope(times, handles_list) * 3600.0

    avg_cpu = sum(p.cpu_percent for p in data_points) / n if n else 0.0
    init_ram = rams[0] if rams else 0.0
    final_ram = rams[-1] if rams else 0.0
    peak_ram = max(rams) if rams else 0.0

    init_h = int(handles_list[0]) if handles_list else 0
    final_h = int(handles_list[-1]) if handles_list else 0
    peak_h = int(max(handles_list)) if handles_list else 0
    peak_threads = max(p.thread_count for p in data_points) if data_points else 0

    notes: list[str] = []
    passed = True

    if ram_slope_per_hr > max_memory_slope_mb_per_hr:
        passed = False
        notes.append(
            f"FAIL: Memory slope {ram_slope_per_hr:.2f} MB/hr exceeds threshold {max_memory_slope_mb_per_hr:.2f} MB/hr"
        )
    else:
        notes.append(f"PASS: Memory slope {ram_slope_per_hr:.2f} MB/hr within healthy bound")

    if handle_slope_per_hr > max_handle_slope_per_hr:
        passed = False
        notes.append(
            f"FAIL: Handle slope {handle_slope_per_hr:.2f}/hr exceeds threshold {max_handle_slope_per_hr:.2f}/hr"
        )
    else:
        notes.append(f"PASS: Handle slope {handle_slope_per_hr:.2f}/hr within healthy bound")

    summary = SoakSummary(
        duration_s=round(dur, 2),
        samples_count=n,
        avg_cpu_percent=round(avg_cpu, 1),
        initial_working_set_mb=round(init_ram, 2),
        final_working_set_mb=round(final_ram, 2),
        peak_working_set_mb=round(peak_ram, 2),
        working_set_slope_mb_per_hr=round(ram_slope_per_hr, 2),
        initial_handles=init_h,
        final_handles=final_h,
        peak_handles=peak_h,
        handle_slope_per_hr=round(handle_slope_per_hr, 2),
        peak_threads=peak_threads,
        passed=passed,
        status_notes=notes,
    )

    print("\n" + "=" * 70)
    print("SOAK TEST SUMMARY REPORT (H-09)")
    print("=" * 70)
    print(f"Status:             {'GREEN (PASS)' if passed else 'RED (FAIL)'}")
    print(f"Duration:           {dur:.1f}s ({n} samples)")
    print(f"Working Set:        {init_ram:.2f} MB -> {final_ram:.2f} MB (Peak: {peak_ram:.2f} MB)")
    print(f"Memory Trend:       {ram_slope_per_hr:+.2f} MB/hour (Limit: <= {max_memory_slope_mb_per_hr:.2f})")
    print(f"Windows Handles:    {init_h} -> {final_h} (Peak: {peak_h}, Trend: {handle_slope_per_hr:+.2f}/hour)")
    print(f"Peak Threads:       {peak_threads}")
    for note in notes:
        print(f"  * {note}")

    if out_json:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        report_payload = {
            "summary": asdict(summary),
            "data_points": [asdict(p) for p in data_points],
        }
        out_json.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nDetailed time-series telemetry saved to: {out_json}")

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="JARVIS H-09 Soak Test Runner")
    parser.add_argument("--pid", type=int, default=None, help="Target process PID to monitor (default: current process)")
    parser.add_argument("--duration", type=float, default=30.0, help="Test duration in seconds (default: 30)")
    parser.add_argument("--interval", type=float, default=1.0, help="Sampling interval in seconds (default: 1.0)")
    parser.add_argument("--out-json", type=Path, default=ROOT / "tests" / "eval" / "results_soak_test.json")
    args = parser.parse_args()

    summary = run_soak_test(
        target_pid=args.pid,
        duration_s=args.duration,
        interval_s=args.interval,
        out_json=args.out_json,
    )
    return 0 if summary.passed else 1


if __name__ == "__main__":
    sys.exit(main())
