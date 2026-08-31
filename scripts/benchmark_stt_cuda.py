"""
scripts/benchmark_stt_cuda.py
==============================
Empirical STT Benchmark for Faster-Whisper large-v3 on CUDA (NVIDIA GeForce GTX 1650 4GB).
Measures real inference latencies (p50, p95, min, max) and calculates Real-Time Factor (RTF)
across 1.0s, 3.0s, 5.0s, and 10.0s synthetic audio buffers.
"""
from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel


def run_cuda_stt_benchmark() -> dict:
    print("=" * 70)
    print("  JARVIS FASTER-WHISPER LARGE-V3 CUDA BENCHMARK (GTX 1650 4GB)")
    print("=" * 70)

    # 1. Model Loading
    print("[*] Loading Faster-Whisper 'large-v3' with device='cuda', compute_type='float16'...")
    t0 = time.perf_counter()
    model = WhisperModel("large-v3", device="cuda", compute_type="float16")
    load_time_s = time.perf_counter() - t0
    print(f"[*] Model loaded successfully in {load_time_s:.2f} seconds.")

    # 2. Warmup
    sr = 16000
    print("[*] Running GPU warmup pass...")
    warmup_audio = np.sin(2 * np.pi * 440 * np.linspace(0, 1, sr, dtype=np.float32))
    segments, _ = model.transcribe(warmup_audio, beam_size=1, language="vi")
    _ = list(segments)
    print("[*] Warmup completed.")

    # 3. Audio Benchmark Runs
    durations = [1.0, 3.0, 5.0, 10.0]
    iterations = 5
    benchmark_data = {
        "model": "large-v3",
        "device": "cuda",
        "compute_type": "float16",
        "gpu": "NVIDIA GeForce GTX 1650 with Max-Q Design (4GB VRAM)",
        "cuda_driver": "13.4",
        "model_load_time_s": round(load_time_s, 2),
        "results": {},
    }

    for dur in durations:
        t_arr = np.linspace(0, dur, int(sr * dur), dtype=np.float32)
        # Synthetic speech-like harmonic signal
        audio = (
            0.3 * np.sin(2 * np.pi * 220 * t_arr)
            + 0.2 * np.sin(2 * np.pi * 440 * t_arr)
            + 0.1 * np.random.normal(0, 0.05, len(t_arr)).astype(np.float32)
        )

        latencies = []
        print(f"\n[*] Benchmarking {dur:.1f}s synthetic audio buffer ({iterations} iterations)...")
        for i in range(iterations):
            t_start = time.perf_counter()
            segs, info = model.transcribe(audio, beam_size=1, language="vi")
            _ = list(segs)
            lat_ms = (time.perf_counter() - t_start) * 1000.0
            latencies.append(lat_ms)
            print(f"    - Iteration {i+1}: {lat_ms:.2f} ms")

        latencies.sort()
        p50 = statistics.median(latencies)
        p95 = latencies[int(len(latencies) * 0.95)]
        min_lat = min(latencies)
        max_lat = max(latencies)
        rtf = (p50 / 1000.0) / dur

        key = f"audio_{int(dur)}s"
        benchmark_data["results"][key] = {
            "duration_s": dur,
            "iterations": iterations,
            "p50_ms": round(p50, 2),
            "p95_ms": round(p95, 2),
            "min_ms": round(min_lat, 2),
            "max_ms": round(max_lat, 2),
            "real_time_factor_rtf": round(rtf, 4),
            "status": "REAL CUDA (large-v3 FP16)",
        }
        print(f"[+] Result for {dur:.1f}s: p50={p50:.2f}ms | p95={p95:.2f}ms | RTF={rtf:.4f}")

    print("\n" + "=" * 70)
    print("  CONSOLIDATED CUDA REAL HARDWARE BENCHMARK RESULTS")
    print("=" * 70)
    for k, v in benchmark_data["results"].items():
        dur_s = v["duration_s"]
        p50_ms = v["p50_ms"]
        p95_ms = v["p95_ms"]
        rtf = v["real_time_factor_rtf"]
        print(f"  {dur_s:>4.1f}s audio: p50={p50_ms:>7.2f} ms | p95={p95_ms:>7.2f} ms | RTF={rtf:>6.4f}")
    print("=" * 70)

    return benchmark_data


if __name__ == "__main__":
    res = run_cuda_stt_benchmark()
    out_path = Path(__file__).resolve().parent.parent / "cuda_stt_benchmark_temp.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
    print(f"Benchmark written to {out_path}")
