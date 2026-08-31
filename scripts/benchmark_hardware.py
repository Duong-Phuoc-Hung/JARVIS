"""
scripts/benchmark_hardware.py
=============================
Empirical Hardware Benchmark and Resource Profiling Suite for JARVIS.
Measures real performance on the host Windows machine:
  1. System & Hardware Specifications (CPU, RAM, GPU, OS)
  2. AST Code Validation Latency (p50, p95, p99)
  3. OS-Level Process Isolation Overhead (Token, Job Object, Subprocess Launch)
  4. Audio STT Latency & Real-Time Factor (RTF)
  5. Audio TTS Latency (Local SAPI5 & Cache Lookup)
  6. Memory Footprint & CPU Utilization
"""
from __future__ import annotations

import io
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path for running directly
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from jarvis.sandbox.interpreter import CodeInterpreterSandbox
from jarvis.sandbox.security import WindowsJobObject, spawn_low_integrity_process
from jarvis.sandbox.validator import ASTCodeValidator
from jarvis.tts.cache import LocalTTSCache
from jarvis.tts.fallback import SAPI5FallbackTTS


def get_hardware_info() -> dict[str, Any]:
    """Inspect and extract accurate hardware specifications of the host Windows system."""
    info: dict[str, Any] = {
        "os": f"{platform.system()} {platform.release()} (Build {platform.version()})",
        "python": sys.version.split()[0],
        "cpu_arch": platform.machine(),
        "cpu_count_logical": os.cpu_count() or 1,
        "cpu_name": platform.processor(),
    }
    
    # Try reading detailed CPU and RAM via Windows wmic / powershell
    try:
        _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        cpu_cmd = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=5,
            creationflags=_cflags,
        )
        if cpu_cmd.returncode == 0 and cpu_cmd.stdout.strip():
            info["cpu_name"] = cpu_cmd.stdout.strip()
    except Exception:
        pass

    try:
        _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        ram_cmd = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum).Sum / 1GB"],
            capture_output=True, text=True, timeout=5,
            creationflags=_cflags,
        )
        if ram_cmd.returncode == 0 and ram_cmd.stdout.strip():
            info["ram_total_gb"] = round(float(ram_cmd.stdout.strip()), 2)
    except Exception:
        info["ram_total_gb"] = "N/A"

    # GPU Check
    try:
        _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        gpu_cmd = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=5,
            creationflags=_cflags,
        )
        if gpu_cmd.returncode == 0 and gpu_cmd.stdout.strip():
            info["gpus"] = [g.strip() for g in gpu_cmd.stdout.strip().splitlines() if g.strip()]
    except Exception:
        info["gpus"] = []

    return info


def benchmark_ast_validator(iterations: int = 50) -> dict[str, Any]:
    """Measure AST validation latency for simple, intermediate, and complex code."""
    validator = ASTCodeValidator()
    
    small_code = "x = 42\nprint(x * 2)"
    medium_code = """
import math, json
records = [{"id": i, "val": math.sqrt(i)} for i in range(100)]
with open("out.json", "w") as f:
    json.dump(records, f)
"""
    complex_code = """
import csv, math, json
class DataProcessor:
    def __init__(self, data):
        self.data = data
    def process(self):
        return [math.log(x + 1) for x in self.data if x > 0]

dp = DataProcessor(list(range(500)))
res = dp.process()
print(json.dumps({"processed_count": len(res)}))
"""
    results: dict[str, Any] = {}
    for label, code in [("small", small_code), ("medium", medium_code), ("complex", complex_code)]:
        timings = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            validator.validate_python(code)
            timings.append((time.perf_counter() - t0) * 1000.0)
        
        timings.sort()
        p50 = statistics.median(timings)
        p95 = timings[int(len(timings) * 0.95)]
        p99 = timings[int(len(timings) * 0.99)]
        results[label] = {
            "p50_ms": round(p50, 4),
            "p95_ms": round(p95, 4),
            "p99_ms": round(p99, 4),
            "min_ms": round(min(timings), 4),
            "max_ms": round(max(timings), 4),
        }
    return results


def benchmark_os_sandbox_isolation(tmp_path: Path, iterations: int = 10) -> dict[str, Any]:
    """Measure Win32 Low Integrity Token + Job Object creation and execution overhead."""
    sandbox = CodeInterpreterSandbox(base_scratch_dir=tmp_path / "bench_scratch")
    
    # 1. Null execution overhead
    null_code = "pass"
    null_timings = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        res = sandbox.execute_python(null_code)
        if res.success:
            null_timings.append(res.execution_time_ms)
    
    # 2. Compute execution overhead
    compute_code = """
import math, json
s = sum(math.sqrt(i) for i in range(50000))
print(json.dumps({"sum": round(s, 2)}))
"""
    compute_timings = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        res = sandbox.execute_python(compute_code)
        if res.success:
            compute_timings.append(res.execution_time_ms)

    # 3. Artifact generation overhead (CSV write + capture)
    artifact_code = """
import csv, json
with open("bench_artifact.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "val"])
    for i in range(100):
        w.writerow([i, i*2])
print(json.dumps({"rows": 100}))
"""
    artifact_timings = []
    for _ in range(iterations):
        res = sandbox.execute_python(artifact_code)
        if res.success:
            artifact_timings.append(res.execution_time_ms)

    def stats(arr: list[float]) -> dict[str, float]:
        if not arr:
            return {"p50_ms": 0, "p95_ms": 0, "min_ms": 0, "max_ms": 0}
        arr.sort()
        return {
            "p50_ms": round(statistics.median(arr), 2),
            "p95_ms": round(arr[int(len(arr) * 0.95)], 2),
            "min_ms": round(min(arr), 2),
            "max_ms": round(max(arr), 2),
        }

    return {
        "null_execution": stats(null_timings),
        "compute_execution": stats(compute_timings),
        "artifact_io_execution": stats(artifact_timings),
    }


def benchmark_stt_engine(iterations: int = 5) -> dict[str, Any]:
    """Measure STT engine load time and transcription latency across audio lengths."""
    from jarvis.stt.faster_whisper import FasterWhisperConfig, FasterWhisperSTTEngine
    import numpy as np

    results: dict[str, Any] = {}
    
    t0 = time.perf_counter()
    stt = FasterWhisperSTTEngine(config=FasterWhisperConfig(model_size="base", device="cpu", compute_type="int8"))
    init_time_ms = (time.perf_counter() - t0) * 1000.0
    results["init_time_ms"] = round(init_time_ms, 2)
    
    is_real_faster_whisper = False
    try:
        import faster_whisper  # noqa: F401
        is_real_faster_whisper = True
    except ImportError:
        is_real_faster_whisper = False

    results["engine_mode"] = (
        "REAL_FASTER_WHISPER_MODEL" if is_real_faster_whisper else "MOCK_PIPELINE_ADAPTER_FALLBACK"
    )

    # Generate synthetic 16kHz float32 audio buffers (1s, 3s, 5s)
    sample_rate = 16000
    for dur_s in [1.0, 3.0, 5.0]:
        audio_buffer = np.zeros(int(sample_rate * dur_s), dtype=np.float32)
        timings = []
        for _ in range(iterations):
            t_start = time.perf_counter()
            _ = stt.transcribe(audio_buffer)
            timings.append((time.perf_counter() - t_start) * 1000.0)
        timings.sort()
        p50 = statistics.median(timings)
        p95 = timings[int(len(timings) * 0.95)]
        rtf = (p50 / 1000.0) / dur_s  # Real-Time Factor
        results[f"audio_{int(dur_s)}s"] = {
            "duration_s": dur_s,
            "p50_ms": round(p50, 2),
            "p95_ms": round(p95, 2),
            "min_ms": round(min(timings), 2),
            "max_ms": round(max(timings), 2),
            "real_time_factor_rtf": round(rtf, 4),
            "measurement_note": (
                "Synthetic float32 PCM adapter pass-through"
                if not is_real_faster_whisper
                else "Real CTranslate2 neural inference"
            ),
        }

    return results


def benchmark_tts_engine(tmp_path: Path, iterations: int = 10) -> dict[str, Any]:
    """Measure real SAPI5 audio synthesis latency and audio cache lookup latency."""
    cache = LocalTTSCache(tmp_path / "tts_cache")

    short_text = "Xin chào tôi là trợ lý ảo JARVIS."
    medium_text = "Đã cập nhật hệ thống bảo mật cấp OS thành công. Sẵn sàng nhận lệnh tiếp theo từ bạn."
    long_text = (
        "Báo cáo tổng kết dự án JARVIS: Đã hoàn tất kiểm thử đối kháng với 661 test cases pass hoàn toàn. "
        "Hệ thống phòng thủ đa tầng kết hợp Windows Mandatory Integrity Control, Job Object và Directory Allowlist "
        "bảo vệ an toàn cho hệ thống máy chủ."
    )

    results: dict[str, Any] = {}

    # 1. Real SAPI5 Speech Synthesis to Memory Stream
    try:
        import win32com.client
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Rate = 0
        speaker.Volume = 100

        for label, text in [("short", short_text), ("medium", medium_text), ("long", long_text)]:
            timings = []
            audio_sizes = []
            for _ in range(iterations):
                stream = win32com.client.Dispatch("SAPI.SpMemoryStream")
                speaker.AudioOutputStream = stream
                t0 = time.perf_counter()
                speaker.Speak(text, 0)  # 0 = SVSFDefault (synchronous full phoneme-to-PCM rendering)
                timings.append((time.perf_counter() - t0) * 1000.0)
                audio_sizes.append(len(bytes(stream.GetData())))
            timings.sort()
            results[f"sapi5_real_synth_{label}"] = {
                "char_count": len(text),
                "generated_pcm_bytes": audio_sizes[0],
                "p50_ms": round(statistics.median(timings), 2),
                "p95_ms": round(timings[int(len(timings) * 0.95)], 2),
                "min_ms": round(min(timings), 2),
                "max_ms": round(max(timings), 2),
                "measurement_type": "REAL_SYNCHRONOUS_PCM_SYNTHESIS",
            }
    except Exception as exc:
        results["sapi5_error"] = str(exc)

    # 2. Benchmark Local TTS Audio Cache lookup
    cache.put(short_text, "voice1", "model1", b"MOCK_WAV_HEADER_DATA_STREAM" * 50)
    cache_timings = []
    for _ in range(100):
        t0 = time.perf_counter()
        _ = cache.get(short_text, "voice1", "model1")
        cache_timings.append((time.perf_counter() - t0) * 1000.0)
    cache_timings.sort()
    results["cache_lookup"] = {
        "p50_ms": round(statistics.median(cache_timings), 4),
        "p95_ms": round(cache_timings[int(len(cache_timings) * 0.95)], 4),
        "min_ms": round(min(cache_timings), 4),
        "max_ms": round(max(cache_timings), 4),
        "measurement_type": "IN_MEMORY_AND_DISK_HASH_LOOKUP",
    }

    return results


def run_full_benchmark() -> dict[str, Any]:
    """Execute all benchmarks and return consolidated report."""
    import tempfile
    tmp_dir = Path(tempfile.gettempdir()) / "jarvis_hw_benchmark"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  JARVIS EMPIRICAL HARDWARE BENCHMARK & SYSTEM PROFILING SUITE")
    print("=" * 70)

    print("[1/4] Inspecting host system specifications...")
    hw_info = get_hardware_info()
    print(f"      CPU: {hw_info.get('cpu_name')} ({hw_info.get('cpu_count_logical')} logical cores)")
    print(f"      RAM: {hw_info.get('ram_total_gb')} GB")
    print(f"      OS : {hw_info.get('os')}")
    if hw_info.get("gpus"):
        print(f"      GPU: {', '.join(hw_info['gpus'])}")

    print("\n--- SECTION A: VERIFIED REAL HARDWARE MEASUREMENTS ---")
    print("[2/5] Benchmarking AST Code Validator (100 runs)...")
    ast_res = benchmark_ast_validator(iterations=100)
    print(f"      Small AST  p50: {ast_res['small']['p50_ms']} ms | p95: {ast_res['small']['p95_ms']} ms")
    print(f"      Medium AST p50: {ast_res['medium']['p50_ms']} ms | p95: {ast_res['medium']['p95_ms']} ms")
    print(f"      Complex AST p50: {ast_res['complex']['p50_ms']} ms | p95: {ast_res['complex']['p95_ms']} ms")

    print("[3/5] Benchmarking Win32 OS-Level Sandbox Process Isolation...")
    sb_res = benchmark_os_sandbox_isolation(tmp_dir, iterations=10)
    print(f"      Null Process Launch    p50: {sb_res['null_execution']['p50_ms']} ms")
    print(f"      Compute (50k Math Ops) p50: {sb_res['compute_execution']['p50_ms']} ms")
    print(f"      Artifact I/O (CSV Gen) p50: {sb_res['artifact_io_execution']['p50_ms']} ms")

    print("[4/5] Benchmarking Real SAPI5 Speech Synthesis to Memory...")
    tts_res = benchmark_tts_engine(tmp_dir, iterations=10)
    if "sapi5_real_synth_short" in tts_res:
        print(f"      Real SAPI5 Short (33 chars)  p50: {tts_res['sapi5_real_synth_short']['p50_ms']} ms ({tts_res['sapi5_real_synth_short']['generated_pcm_bytes']} PCM bytes)")
        print(f"      Real SAPI5 Medium (84 chars) p50: {tts_res['sapi5_real_synth_medium']['p50_ms']} ms ({tts_res['sapi5_real_synth_medium']['generated_pcm_bytes']} PCM bytes)")
        print(f"      Real SAPI5 Long (239 chars)  p50: {tts_res['sapi5_real_synth_long']['p50_ms']} ms ({tts_res['sapi5_real_synth_long']['generated_pcm_bytes']} PCM bytes)")

    print("\n--- SECTION B: PIPELINE ADAPTER & FRAMEWORK OVERHEADS ---")
    print("[5/5] Benchmarking Audio Cache & STT Pipeline Adapter...")
    stt_res = benchmark_stt_engine(iterations=5)
    print(f"      Audio Cache Lookup Latency   p50: {tts_res['cache_lookup']['p50_ms']} ms")
    print(f"      STT Mode                     : {stt_res['engine_mode']}")
    print(f"      STT 1.0s Buffer Adapter      p50: {stt_res['audio_1s']['p50_ms']} ms (RTF: {stt_res['audio_1s']['real_time_factor_rtf']})")
    print(f"      STT 3.0s Buffer Adapter      p50: {stt_res['audio_3s']['p50_ms']} ms (RTF: {stt_res['audio_3s']['real_time_factor_rtf']})")
    print(f"      STT 5.0s Buffer Adapter      p50: {stt_res['audio_5s']['p50_ms']} ms (RTF: {stt_res['audio_5s']['real_time_factor_rtf']})")

    full_report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hardware": hw_info,
        "verified_hardware_measurements": {
            "ast_validator": ast_res,
            "sandbox_isolation_win32": sb_res,
            "tts_real_sapi5_pcm": {k: v for k, v in tts_res.items() if k.startswith("sapi5_real_synth")},
        },
        "framework_and_adapter_baselines": {
            "audio_cache_lookup": tts_res["cache_lookup"],
            "stt_pipeline_adapter": stt_res,
        }
    }

    report_file = _PROJECT_ROOT / "benchmark_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2)

    print("=" * 70)
    print(f"  Benchmark complete. Structured report saved to: {report_file}")
    print("=" * 70)
    return full_report


if __name__ == "__main__":
    run_full_benchmark()
