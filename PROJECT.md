# Project: Tối ưu Hóa Chuỗi Phản Xạ Voice-to-Action & Dynamic Tiered ASR

## Architecture
Hệ thống Voice-to-Action Reflex Arc của JARVIS được thiết kế theo luồng phản xạ cận-zero latency (< 1.0s E2E):
```
[Microphone Audio (16kHz PCM)]
       │
       ▼
[SileroVADStreamingDetector (CPU ONNX, 576 samples ~36ms, <0.25ms)]
  └── Speech detected → Audio Frame Buffer
  └── Post-TTS Settling Guard (150ms mutex lock) prevents loopback
       │
       ▼
[DynamicTieredASR Engine (CTranslate2 CUDA)]
  ├── Default Tier: Faster-Whisper Small (int8_float16, ~552ms, VRAM ~786MB)
  │     or Tiny for ultra-short commands (<1s, ~198ms)
  └── Uncertainty Escalation: Faster-Whisper Large-v3
        Condition: avg_logprob < -0.65 or no_speech_prob > 0.50
        Lifecycle: On-demand load → Transcribe → del & gc.collect() (VRAM <= 2.0GB)
       │
       ▼
[Phonetic & Multi-intent Normalizer (~0.42ms)]
       │
       ▼
[VietnameseNLPClassifier (ONNX C-API, ~0.04ms, 15 Domains + OOD)]
       │
       ├── If P >= 0.35 and Intent != "unknown":
       │     Extract Typed Slots (volume %, brightness level, app name, action...)
       │     Direct Bypass to ActionDispatcher (Win32 Endpoint / WMI / Process APIs, ~1.15ms)
       │     (Zero Cloud LLM latency for device control)
       │
       └── If P < 0.35 or Intent == "unknown":
             ├── Hook UnrecognizedTurnCollector:
             │     PII Scrubber (Redacts Passwords, Phone, Card, CCCD, Email, Tokens)
             │     Thread-safe append to data/feedback/unrecognized_turns.jsonl
             └── Fallback to Cloud LLM / Clarification
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---|---|---|---|
| 1 | DynamicTieredASR Router | Chuyển đổi linh hoạt giữa Whisper Small, Tiny và Large-v3 theo độ tin cậy âm học | M1 | R1 |
| 2 | Whisper Acoustic Metrics | Trích xuất `avg_logprob` và `no_speech_prob` từ Faster-Whisper segments | M1 | R1 |
| 3 | VRAM Lifecycle Guard | Giữ VRAM <= 2.0GB, giải phóng bộ đệm CUDA ngay sau khi large-v3 suy luận, không OOM trên GTX 1650 | M1 | R1 |
| 4 | Silero VAD v6 Streaming | Stream khung 576 mẫu (~36ms), độ trễ CPU <= 0.25ms, duy trì LSTM state (h, c) | M2 | R2 |
| 5 | Post-TTS Settling Guard | Đồng bộ khóa âm thanh 150ms sau TTS ngăn vòng lặp phản hồi micro | M2 | R2 |
| 6 | ONNX Direct Fast-Path Wiring | Kích hoạt `ml_fast_path_enabled` và ngưỡng P >= 0.35 từ VietnameseNLPClassifier sang ActionDispatcher | M3 | R3 |
| 7 | ActionDispatcher Domain Alignment | Đăng ký và chuẩn hóa 6 domain thiếu (`window_control`, `app_close`, `clipboard_action`, `media_control`, `file_management`, `network_diagnostics`) | M3 | R3 |
| 8 | Typed Slots Extraction & Direct Execution | Trích xuất tham số có kiểu (target_level, action, delta, app_name...) và dispatch trực tiếp Windows APIs | M3 | R3 |
| 9 | PII Scrubber Fix & Hardening | Sửa lỗi rò rỉ mật khẩu trong regex substitution, bổ sung CCCD/CMND, IP, Bearer token | M4 | R4 |
| 10 | UnrecognizedTurn Voice Hook | Tự động ghi nhận câu nói P < 0.35 hoặc unknown vào feedback dataset | M4 | R4 |
| 11 | Argon Latency Timing Breakdown | Đo đạc chính xác tau_total = tau_VAD + tau_STT + tau_Norm + tau_NLU + tau_Dispatch | M5 | R5 |
| 12 | RAM & VRAM Telemetry Harness | Thu thập số liệu bộ nhớ thực tế, xác nhận VRAM <= 2.0GB và 50 runs 0 OOM | M5 | R5 |
| 13 | Fail-Closed Verification | Xác thực toàn bộ phản xạ trả mã lỗi chuẩn, không ghost success | M5 | R5 |
| 14 | E2E Regression & Release Sync | 100% tests pass, cập nhật CHANGELOG, README, ROADMAP và git push main | M6 | Acceptance |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| M1 | Dynamic Tiered ASR Engine & Adaptive Routing | `jarvis/stt/dynamic_tiered.py`, `jarvis/stt/engine.py`, segment metrics, VRAM lifecycle | none | PLANNED |
| M2 | Real-time Streaming Silero VAD & Settling Guard | `jarvis/audio/silero_vad.py`, `jarvis/audio/vad.py`, 576-sample frames, 150ms settling guard | none | PLANNED |
| M3 | Zero-Latency NLU-to-Dispatcher Direct Wiring | `jarvis/llm/local_classifier.py`, `jarvis/llm/router.py`, `jarvis/core/dispatcher.py`, `jarvis/core/app.py` | none | PLANNED |
| M4 | Continuous Learning Feedback & PII Scrubber | `jarvis/nlp/automation/unrecognized_collector.py`, hook in voice/NLU pipeline | M3 | PLANNED |
| M5 | Argon Benchmark Suite & Telemetry Verification | `tests/benchmarks/test_voice_reflex_benchmark.py`, latency breakdown, 50-run 0 OOM | M1, M2, M3, M4 | PLANNED |
| M6 | Final Integration & Release Packaging | Full test suite regression (100% pass), documentation sync, git commit & push | M5 | PLANNED |

## Interface Contracts

### 1. `DynamicTieredASR` ↔ ASR Consumers
- **Class**: `jarvis.stt.dynamic_tiered.DynamicTieredASREngine`
- **Method**: `transcribe(audio: np.ndarray | str | Path, language: str = "vi") -> TranscriptionResult`
- **Return Type**:
  ```python
  @dataclass(frozen=True)
  class TranscriptionResult:
      text: str
      avg_logprob: float
      no_speech_prob: float
      model_tier: str  # "tiny", "small", "large-v3"
      escalated: bool
      duration_ms: float
  ```
- **Error Handling**: Fail-closed; on missing model or CUDA exception, falls back to CPU small or returns empty result with error status.

### 2. `SileroVADStreamingDetector` ↔ Audio Pipeline
- **Class**: `jarvis.audio.silero_vad.SileroVADStreamingDetector`
- **Method**: `process_frame(frame_pcm16: np.ndarray | bytes) -> float` (returns speech probability $p \in [0.0, 1.0]$)
- **Method**: `reset_states() -> None` (clears LSTM `(h, c)` states)
- **Frame Spec**: Exactly 576 samples (512 chunk + 64 context) @ 16kHz float32.

### 3. `VietnameseNLPClassifier` ↔ `ActionDispatcher`
- **Method**: `classify_and_dispatch(text: str) -> DispatchResult`
- **Threshold**: $P \ge 0.35$ routes directly to `dispatcher.dispatch(action_name, **slots)`
- **Return Type**:
  ```python
  @dataclass
  class DirectDispatchResult:
      intent: str
      confidence: float
      slots: dict[str, Any]
      dispatched: bool
      action_result: dict[str, Any] | None
      execution_latency_ms: float
  ```

### 4. `UnrecognizedTurnCollector` ↔ Voice/NLU Pipeline
- **Method**: `record_unrecognized(raw_text: str, confidence: float, source: str = "voice") -> bool`
- **Privacy Contract**: All strings scrubbed by hardened `scrub_pii(text)` prior to JSONL write.

## Code Layout
- `jarvis/stt/dynamic_tiered.py`: DynamicTieredASR implementation
- `jarvis/stt/engine.py`: FasterWhisperSTT acoustic metrics exposure
- `jarvis/audio/silero_vad.py`: Silero VAD v6 576-sample streaming detector
- `jarvis/audio/vad.py`: VoiceActivityDetector integration
- `jarvis/llm/local_classifier.py`: VietnameseNLPClassifier slot extraction alignment
- `jarvis/llm/router.py`: LLMIntentRouter fast-path activation and P >= 0.35 threshold
- `jarvis/core/dispatcher.py`: ActionDispatcher handler alignment and direct dispatch
- `jarvis/core/app.py`: JarvisApp fast-path wiring
- `jarvis/nlp/automation/unrecognized_collector.py`: Hardened PII scrubber and collection hook
- `tests/benchmarks/test_voice_reflex_benchmark.py`: Argon benchmark test harness
- `tests/unit/test_dynamic_tiered_asr.py`: Unit tests for DynamicTieredASR
- `tests/unit/test_silero_vad_streaming.py`: Unit tests for Silero VAD
- `tests/unit/test_direct_nlu_dispatch.py`: Unit tests for direct NLU-to-Dispatcher
- `tests/unit/test_unrecognized_collector_hardened.py`: Unit tests for PII scrubber & collector
