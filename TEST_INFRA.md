# E2E Test Infra: Voice-to-Action & Dynamic Tiered ASR

## Test Philosophy
- Opaque-box & Requirement-driven: Evaluates real audio inputs, confidence thresholds, dispatch execution, and telemetry.
- Methodology: Category-Partition + Boundary Value Analysis + Pairwise Combinatorial + Real-World Workload Testing.
- Rigorous Hardware Telemetry: Live RAM & VRAM measurements on GTX 1650 Max-Q.

## Feature Inventory & Test Coverage Matrix
| # | Feature | Requirement | Tier 1 (Unit/Feature) | Tier 2 (Boundary) | Tier 3 (Cross-Feature) | Tier 4 (Workload/E2E) |
|---|---|---|:---:|:---:|:---:|:---:|
| 1 | DynamicTieredASR | R1 | >= 5 | >= 5 | ✓ | ✓ |
| 2 | Whisper Acoustic Metrics | R1 | >= 5 | >= 5 | ✓ | ✓ |
| 3 | VRAM Lifecycle Guard | R1 | >= 5 | >= 5 | ✓ | ✓ (50 runs 0 OOM) |
| 4 | Silero VAD v6 Streaming | R2 | >= 5 | >= 5 | ✓ | ✓ |
| 5 | Post-TTS Settling Guard | R2 | >= 5 | >= 5 | ✓ | ✓ |
| 6 | ONNX Direct Fast-Path Wiring | R3 | >= 5 | >= 5 | ✓ | ✓ |
| 7 | ActionDispatcher Alignment | R3 | >= 5 | >= 5 | ✓ | ✓ |
| 8 | Typed Slots Direct Execution | R3 | >= 5 | >= 5 | ✓ | ✓ |
| 9 | PII Scrubber Fix & Hardening | R4 | >= 5 | >= 5 | ✓ | ✓ |
| 10 | UnrecognizedTurn Collector | R4 | >= 5 | >= 5 | ✓ | ✓ |
| 11 | Latency Breakdown (tau_total) | R5 | >= 5 | >= 5 | ✓ | ✓ (p50 <= 1100ms) |
| 12 | RAM & VRAM Telemetry | R5 | >= 5 | >= 5 | ✓ | ✓ (VRAM <= 2.0GB) |
| 13 | Fail-Closed Error Handling | R5 | >= 5 | >= 5 | ✓ | ✓ |

## Test Architecture
- **E2E Benchmark Runner**: `tests/benchmarks/test_voice_reflex_benchmark.py`
- **Unit Test Suites**:
  - `tests/unit/test_dynamic_tiered_asr.py`
  - `tests/unit/test_silero_vad_streaming.py`
  - `tests/unit/test_direct_nlu_dispatch.py`
  - `tests/unit/test_unrecognized_collector_hardened.py`
- **Execution Command**: `python -m pytest tests/unit/test_dynamic_tiered_asr.py tests/unit/test_silero_vad_streaming.py tests/unit/test_direct_nlu_dispatch.py tests/unit/test_unrecognized_collector_hardened.py tests/benchmarks/test_voice_reflex_benchmark.py -v`

## Coverage Thresholds
- Tier 1: >= 5 test cases per feature (happy path isolation)
- Tier 2: >= 5 test cases per feature (boundaries: empty audio, noise, clipping, extreme confidence, password variations, CCCD)
- Tier 3: Pairwise combinations (e.g. VAD speech cut + Whisper escalation + NLU slot extract + Dispatch)
- Tier 4: Real-world workload (50 consecutive commands with active VRAM/RAM telemetry, 0 OOM)
- Total tests planned: > 70 tests across suites with 100% pass rate.
