"""
tests/test_adversarial_m3_stt_llm.py
======================================
Empirical Adversarial Stress Test Suite for Milestone 3 (Voice AI & LLM Intent Router).
Tests target:
  1. STT Audio Pipeline:
     - NaN / Inf float32 arrays, zero-length arrays, 100MB bursts, rapid 50-chunk continuous feeds,
       corrupt RIFF WAV headers, mono/stereo multi-channel downmixing, sample rate mismatch (8k, 44.1k, 48k -> 16k).
  2. VAD State Machine:
     - Extreme rapid oscillations around vad_threshold, chatter burst pulses, leading/trailing silence edge boundaries.
  3. LLM Client & Router:
     - Concurrent multi-threaded requests, malformed JSON with markdown blocks, missing fields,
       token limit edge cases, HTTP 429 backoff simulation, and sub-5ms rule fallback performance.
  4. Dynamic Schema Generator:
     - Actions with complex parameter annotations (Union, Optional, List, Dict, custom objects, untyped *args/**kwargs).
  5. Module Interface & Contract Compliance:
     - Verifying exports and contracts across `jarvis.stt` and `jarvis.llm`.
"""
from __future__ import annotations

import concurrent.futures
import io
import json
import math
import os
import re
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from unittest.mock import MagicMock, patch
import wave

import numpy as np
import pytest
import requests

# Target imports
from jarvis.audio.dsp import calculate_rms
from jarvis.core.dispatcher import ActionDispatcher
from jarvis.core.models import ActionResult, RequesterContext
from jarvis.stt.engine import (
    BaseSTTEngine,
    FasterWhisperSTT,
    MockSTTEngine,
    OpenAIWhisperSTT,
    STTError,
    STTEngine,
    VADSegmenter,
    WindowsSpeechSTT,
    audio_to_float32,
    float32_to_pcm16_wav_bytes,
    resample_audio,
)
from jarvis.llm.client import (
    ChatMessage,
    LLMAuthenticationError,
    LLMClient,
    LLMError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponse,
    LLMResponseParsingError,
    LLMTimeoutError,
    TokenUsage,
    ToolCall,
)
from jarvis.llm.router import (
    IntentResult,
    LLMIntentRouter,
    build_jarvis_system_prompt,
    generate_tool_schema_from_dispatcher,
)


# ============================================================================
# 1. STT AUDIO PIPELINE ADVERSARIAL STRESS TESTS
# ============================================================================

def test_adversarial_stt_nan_inf_float32():
    """Pass NaN, +Inf, -Inf float32 arrays into STT pipeline components."""
    dirty_array = np.array([np.nan, np.inf, -np.inf, 0.5, -0.5, np.nan], dtype=np.float32)
    
    # 1. audio_to_float32
    sanitized = audio_to_float32(dirty_array)
    assert isinstance(sanitized, np.ndarray)
    assert sanitized.dtype == np.float32
    assert not np.isnan(sanitized).any(), "NaN values found in sanitized audio"
    assert not np.isinf(sanitized).any(), "Inf values found in sanitized audio"
    assert (sanitized >= -1.0).all() and (sanitized <= 1.0).all()

    # 2. All-NaN array
    all_nan = np.full(1000, np.nan, dtype=np.float32)
    sanitized_all_nan = audio_to_float32(all_nan)
    assert not np.isnan(sanitized_all_nan).any()
    assert np.all(sanitized_all_nan == 0.0)

    # 3. All-Inf array
    all_inf = np.full(1000, np.inf, dtype=np.float32)
    sanitized_all_inf = audio_to_float32(all_inf)
    assert not np.isinf(sanitized_all_inf).any()
    assert np.all(sanitized_all_inf == 0.0)

    # 4. float32_to_pcm16_wav_bytes with dirty array
    wav_buf = float32_to_pcm16_wav_bytes(dirty_array, sample_rate=16000)
    assert isinstance(wav_buf, io.BytesIO)
    wav_bytes = wav_buf.getvalue()
    assert wav_bytes.startswith(b"RIFF")
    assert len(wav_bytes) > 44  # Valid WAV header size

    # Verify parsed WAV frames
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        frames = wf.readframes(wf.getnframes())
        pcm_arr = np.frombuffer(frames, dtype=np.int16)
        assert len(pcm_arr) == len(dirty_array)

    # 5. calculate_rms on dirty arrays
    rms = calculate_rms(dirty_array)
    assert isinstance(rms, float)
    assert not math.isnan(rms)
    assert not math.isinf(rms)
    assert rms >= 0.0

    # 6. STTEngine transcribe on NaN array
    engine = STTEngine(provider="mock")
    res_nan = engine.transcribe(all_nan)
    assert res_nan == ""

    # Dirty array with real audio content [0.5, -0.5]
    res_dirty = engine.transcribe(dirty_array)
    assert isinstance(res_dirty, str)


def test_adversarial_stt_zero_length_and_empty_inputs():
    """Pass zero-length arrays, empty bytes, None, and nonexistent paths."""
    empty_1d = np.empty(0, dtype=np.float32)
    empty_2d = np.empty((0, 2), dtype=np.float32)

    # audio_to_float32
    assert len(audio_to_float32(empty_1d)) == 0
    assert len(audio_to_float32(empty_2d)) == 0
    assert len(audio_to_float32(b"")) == 0
    assert len(audio_to_float32(None)) == 0
    assert len(audio_to_float32(io.BytesIO(b""))) == 0
    assert len(audio_to_float32("non_existent_audio_file_9999.wav")) == 0

    # float32_to_pcm16_wav_bytes
    wav_empty = float32_to_pcm16_wav_bytes(empty_1d)
    assert isinstance(wav_empty, io.BytesIO)
    with wave.open(wav_empty, "rb") as wf:
        assert wf.getnframes() == 0

    # resample_audio
    assert len(resample_audio(empty_1d, 16000, 8000)) == 0
    assert len(resample_audio(empty_1d, 8000, 16000)) == 0

    # STTEngine transcribe
    engine = STTEngine(provider="mock")
    assert engine.transcribe(empty_1d) == ""
    assert engine.transcribe(b"") == ""
    assert engine.transcribe(None) == ""

    # VADSegmenter
    vad = VADSegmenter()
    assert vad.feed_block(empty_1d) is None
    assert vad.feed_block(None) is None
    assert vad.is_speech(empty_1d) is False
    assert vad.is_speech(None) is False


def test_adversarial_stt_100mb_burst_and_memory_safety():
    """Process 100MB audio array (26.2 million float32 samples = ~27 mins of audio)."""
    num_samples = 25 * 1024 * 1024  # 26,214,400 floats = ~100MB
    tone = np.sin(2.0 * np.pi * 440.0 * np.arange(16000, dtype=np.float32) / 16000.0) * 0.5
    repeats = (num_samples // 16000) + 1
    large_audio = np.tile(tone, repeats)[:num_samples]
    assert large_audio.nbytes >= 100 * 1024 * 1024

    # 1. audio_to_float32
    t0 = time.perf_counter()
    normalized = audio_to_float32(large_audio)
    dt = time.perf_counter() - t0
    assert len(normalized) == num_samples
    assert dt < 3.0, f"Normalization of 100MB burst took too long: {dt:.2f}s"

    # 2. VAD Segmenter Max Speech Hard Cutoff
    vad = VADSegmenter(vad_threshold=0.01, max_speech_s=2.0, sample_rate=16000)
    # Feed first block to trigger active state
    first_block = large_audio[:16000]  # 1s
    vad.feed_block(first_block)
    assert vad._is_speech_active is True

    # Feed second block exceeding max_speech_s (total = 2.5s >= 2.0s)
    second_block = large_audio[16000:40000]  # 1.5s
    segment = vad.feed_block(second_block)
    assert segment is not None, "VAD should trigger max_speech hard cutoff on second block"
    assert len(segment) >= int(2.0 * 16000)
    assert vad._is_speech_active is False
    assert len(vad._active_buffer) == 0


def test_adversarial_stt_50_chunk_continuous_feed():
    """Simulate real-time streaming of 50 continuous chunks (512 samples each = 32ms frames)."""
    sr = 16000
    chunk_size = 512
    vad = VADSegmenter(
        vad_threshold=0.02,
        sample_rate=sr,
        silence_trailing_s=0.3,  # 300ms trailing silence
        pre_speech_s=0.2,       # 200ms pre-speech buffer
        min_speech_s=0.2,       # 200ms min speech
    )

    silence_chunk = np.zeros(chunk_size, dtype=np.float32)
    t = np.arange(chunk_size, dtype=np.float32) / float(sr)
    voice_chunk = (np.sin(2.0 * np.pi * 440.0 * t) * 0.5).astype(np.float32)
    assert calculate_rms(voice_chunk) > 0.05

    segments_received = []

    # Phase 1: 10 chunks silence (320ms) -> accumulating pre-buffer
    for i in range(10):
        res = vad.feed_block(silence_chunk)
        assert res is None

    assert vad._is_speech_active is False
    assert len(vad._pre_buffer) <= int(0.2 * sr)

    # Phase 2: 15 chunks voice (480ms) -> speech active
    for i in range(15):
        res = vad.feed_block(voice_chunk)
        assert res is None  # Still active, not complete yet
        assert vad._is_speech_active is True

    # Phase 3: 25 chunks silence (800ms) -> trailing silence exceeds 300ms, should complete
    for i in range(25):
        res = vad.feed_block(silence_chunk)
        if res is not None:
            segments_received.append(res)

    assert len(segments_received) == 1, f"Expected exactly 1 segment, got {len(segments_received)}"
    seg = segments_received[0]
    min_expected_samples = int((0.2 + 0.48 + 0.3) * sr * 0.8)
    assert len(seg) >= min_expected_samples
    assert vad._is_speech_active is False


def test_adversarial_stt_corrupt_riff_wav_headers():
    """Feed broken, truncated, and random byte streams to audio converter and STT engine."""
    corrupt_samples = [
        b"RIFF",  # 4 bytes truncated
        b"RIFF\x00\x00\x00\x00",  # Truncated header
        b"RIFF\x24\x00\x00\x00WAVEfmt ",  # Incomplete fmt chunk
        b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x00\x00",  # Zero channels/samplerate
        b"RIFX\x00\x00\x00\x24WAVEfmt ",  # Non-standard magic
        b"\x00" * 1024,  # Null bytes
        os.urandom(4096),  # Random fuzzed bytes
    ]

    engine = STTEngine(provider="mock")

    for idx, payload in enumerate(corrupt_samples):
        # 1. audio_to_float32 must never raise unhandled exception
        try:
            arr = audio_to_float32(payload)
            assert isinstance(arr, np.ndarray)
        except Exception as exc:
            pytest.fail(f"audio_to_float32 crashed on corrupt payload #{idx}: {exc}")

        # 2. float32_to_pcm16_wav_bytes must handle it
        try:
            wav_io = float32_to_pcm16_wav_bytes(arr)
            assert isinstance(wav_io, io.BytesIO)
        except Exception as exc:
            pytest.fail(f"float32_to_pcm16_wav_bytes crashed on payload #{idx}: {exc}")

        # 3. STTEngine transcribe must gracefully return empty string or valid text
        try:
            res = engine.transcribe(payload)
            assert isinstance(res, str)
        except Exception as exc:
            pytest.fail(f"STTEngine.transcribe crashed on corrupt payload #{idx}: {exc}")


def test_adversarial_stt_multichannel_downmixing():
    """Downmix multi-channel 2D arrays (Stereo 2ch, Surround 5.1 6ch, Surround 7.1 8ch)."""
    n_samples = 1000

    # Stereo float32: left = 0.8, right = 0.2 -> mean = 0.5
    stereo = np.zeros((n_samples, 2), dtype=np.float32)
    stereo[:, 0] = 0.8
    stereo[:, 1] = 0.2
    downmixed_stereo = audio_to_float32(stereo)
    assert downmixed_stereo.ndim == 1
    assert len(downmixed_stereo) == n_samples
    np.testing.assert_allclose(downmixed_stereo, 0.5, atol=1e-5)

    # 6-channel float32 (5.1 surround)
    surround_51 = np.ones((n_samples, 6), dtype=np.float32) * 0.6
    downmixed_51 = audio_to_float32(surround_51)
    assert downmixed_51.ndim == 1
    assert len(downmixed_51) == n_samples
    np.testing.assert_allclose(downmixed_51, 0.6, atol=1e-5)

    # 8-channel float32 (7.1 surround)
    surround_71 = np.ones((n_samples, 8), dtype=np.float32) * -0.4
    downmixed_71 = audio_to_float32(surround_71)
    assert downmixed_71.ndim == 1
    np.testing.assert_allclose(downmixed_71, -0.4, atol=1e-5)

    # 1D int16 array (normalized correctly)
    int16_mono = np.ones(n_samples, dtype=np.int16) * 16384  # ~0.5
    downmixed_mono_int = audio_to_float32(int16_mono)
    assert downmixed_mono_int.ndim == 1
    np.testing.assert_allclose(downmixed_mono_int, 0.5, atol=1e-3)

    # Note on 2D int16 array:
    # Under current implementation, 2D int16 array mean() converts to float64, bypassing int conversion
    # and clipping to 1.0 (finding documented in handoff).


def test_adversarial_stt_sample_rate_mismatch_resampling():
    """Test linear interpolation resampling across standard mismatched sample rates."""
    rates = [8000, 22050, 44100, 48000, 96000, 192000]
    target_sr = 16000

    for sr in rates:
        duration = 0.5  # 0.5 second
        t = np.arange(int(sr * duration), dtype=np.float32) / float(sr)
        sine = (np.sin(2.0 * np.pi * 440.0 * t) * 0.8).astype(np.float32)

        resampled = resample_audio(sine, orig_sr=sr, target_sr=target_sr)
        expected_samples = int(duration * target_sr)
        assert abs(len(resampled) - expected_samples) <= 1, (
            f"Resampling from {sr} to {target_sr}: got {len(resampled)}, expected {expected_samples}"
        )
        assert resampled.dtype == np.float32
        assert np.max(resampled) <= 0.85
        assert np.min(resampled) >= -0.85

    # Identity resampling (same rate)
    arr = np.linspace(-0.5, 0.5, 1000, dtype=np.float32)
    same = resample_audio(arr, 16000, 16000)
    assert np.array_equal(arr, same)


# ============================================================================
# 2. VAD STATE MACHINE ADVERSARIAL STRESS TESTS
# ============================================================================

def test_adversarial_vad_rapid_threshold_oscillations():
    """Rapidly oscillate RMS around vad_threshold across 200 consecutive frames."""
    th = 0.02
    vad = VADSegmenter(vad_threshold=th, sample_rate=16000)

    chunk_len = 160  # 10ms frame
    sub_chunk = np.full(chunk_len, th - 0.005, dtype=np.float32)
    super_chunk = np.full(chunk_len, th + 0.005, dtype=np.float32)

    for i in range(200):
        block = super_chunk if (i % 2 == 0) else sub_chunk
        segment = vad.feed_block(block)
        assert segment is None or isinstance(segment, np.ndarray)


def test_adversarial_vad_chatter_burst_pulses():
    """Loud transient chatter bursts shorter than min_speech_s should be discarded."""
    sr = 16000
    vad = VADSegmenter(
        vad_threshold=0.015,
        sample_rate=sr,
        min_speech_s=0.25,  # 250ms minimum speech
        silence_trailing_s=0.5,  # 500ms trailing silence
    )

    burst_samples = int(0.05 * sr)
    burst = np.full(burst_samples, 0.5, dtype=np.float32)
    silence_samples = int(0.6 * sr)
    silence = np.zeros(silence_samples, dtype=np.float32)

    vad.feed_block(burst)
    assert vad._is_speech_active is True

    vad.feed_block(silence)
    assert vad._is_speech_active is False
    assert len(vad._active_buffer) == 0


def test_adversarial_vad_leading_trailing_silence_edge_boundaries():
    """Verify pre-speech ring buffer preservation and exact trailing silence cutoff."""
    sr = 16000
    pre_s = 0.3  # 300ms
    silence_trailing_s = 0.8  # 800ms
    vad = VADSegmenter(
        vad_threshold=0.02,
        sample_rate=sr,
        pre_speech_s=pre_s,
        silence_trailing_s=silence_trailing_s,
        min_speech_s=0.2,
    )

    # 1. Feed 1000ms of silence in 100ms blocks
    block_100ms = np.zeros(int(0.1 * sr), dtype=np.float32)
    for _ in range(10):
        vad.feed_block(block_100ms)

    assert len(vad._pre_buffer) == int(pre_s * sr)

    # 2. Feed 500ms of voice
    voice_500ms = np.full(int(0.5 * sr), 0.1, dtype=np.float32)
    vad.feed_block(voice_500ms)
    assert vad._is_speech_active is True
    assert len(vad._pre_buffer) == 0

    # 3. Feed 700ms silence (under 800ms trailing) -> should NOT complete yet
    block_700ms = np.zeros(int(0.7 * sr), dtype=np.float32)
    res1 = vad.feed_block(block_700ms)
    assert res1 is None
    assert vad._is_speech_active is True

    # 4. Feed additional 200ms silence (total silence = 900ms >= 800ms) -> MUST complete!
    block_200ms = np.zeros(int(0.2 * sr), dtype=np.float32)
    res2 = vad.feed_block(block_200ms)
    assert res2 is not None, "Utterance should be completed on reaching trailing silence"
    assert len(res2) == int((0.3 + 0.5 + 0.7 + 0.2) * sr)
    assert vad._is_speech_active is False


# ============================================================================
# 3. LLM CLIENT & ROUTER ADVERSARIAL STRESS TESTS
# ============================================================================

def test_adversarial_llm_concurrent_multithreaded_requests():
    """Execute 40 concurrent threads calling LLMClient and LLMIntentRouter."""
    client = LLMClient(provider="mock")
    dispatcher = ActionDispatcher()
    dispatcher.register_action(
        name="test_action",
        handler=lambda x=1: {"status": "ok", "x": x},
        description="Test action handler",
    )
    router = LLMIntentRouter(llm_client=client, dispatcher=dispatcher)

    def worker_task(thread_id: int) -> Tuple[bool, str]:
        try:
            resp = client.generate(f"Thread test prompt {thread_id}")
            if not resp.success:
                return False, "generate failed"

            chat_resp = client.chat([
                ChatMessage(role="system", content="System"),
                ChatMessage(role="user", content=f"Hello from {thread_id}")
            ])
            if not chat_resp.success:
                return False, "chat failed"

            intent = router.parse_intent(f"bật đèn phòng khách {thread_id}")
            if not intent.action_name:
                return False, "intent parse failed"

            action_res = router.execute_intent(intent)
            if not isinstance(action_res, ActionResult):
                return False, "execute intent failed"

            return True, "ok"
        except Exception as e:
            return False, str(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(worker_task, i) for i in range(40)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    for success, msg in results:
        assert success is True, f"Thread failed with error: {msg}"

    assert len(client.call_history) >= 80


def test_adversarial_llm_malformed_json_markdown_blocks():
    """Test _clean_and_parse_json against markdown blocks and verify parsed content."""
    client = LLMClient(provider="mock")

    test_cases = [
        ('```json\n{"action": "turn_on", "target": "lamp"}\n```', {"action": "turn_on", "target": "lamp"}),
        ('```\n{"temperature": 24.5, "mode": "cool"}\n```', {"temperature": 24.5, "mode": "cool"}),
        ('\n\n  ```json\n{"status": "active"}\n``` \n ', {"status": "active"}),
        ('{"key": "value", "count": 42}', {"key": "value", "count": 42}),
        ('', {}),
        ('   ', {}),
        (None, {}),
    ]

    for raw_input, expected in test_cases:
        parsed = client._clean_and_parse_json(raw_input)
        assert isinstance(parsed, dict)
        for k, v in expected.items():
            assert k in parsed
            assert str(parsed[k]) == str(v)


def test_adversarial_llm_missing_fields_and_malformed_payloads():
    """Pass malformed ChatMessages, ToolCalls, and IntentResults."""
    # 1. ChatMessage with None / missing fields
    msg = ChatMessage(role="user", content="", name=None, tool_calls=None, tool_call_id=None)
    msg_dict = msg.to_dict()
    assert msg_dict["role"] == "user"
    assert msg_dict["content"] == ""
    assert "name" not in msg_dict

    # 2. ToolCall with empty args
    tc = ToolCall(id="", name="")
    tc_dict = tc.to_dict()
    assert tc_dict["id"] == ""
    assert tc_dict["arguments"] == {}

    # 3. IntentResult execution with unknown intent
    router = LLMIntentRouter(llm_client=LLMClient(provider="mock"), dispatcher=ActionDispatcher())
    unknown_intent = IntentResult(action_name="unknown_intent", raw_text="gibberish 12345")
    res = router.execute_intent(unknown_intent)
    assert res.success is False
    assert res.error_code == "UNKNOWN_INTENT"

    # 4. IntentResult execution without dispatcher
    orphan_router = LLMIntentRouter(llm_client=LLMClient(provider="mock"), dispatcher=None)
    res_no_disp = orphan_router.execute_intent(IntentResult(action_name="test"))
    assert res_no_disp.success is False
    assert res_no_disp.error_code == "DISPATCHER_UNAVAILABLE"


def test_adversarial_llm_token_limit_and_massive_prompts():
    """Pass 50,000 character prompt string and verify token usage accumulation."""
    client = LLMClient(provider="mock")
    massive_prompt = "A" * 50000

    resp = client.generate(massive_prompt)
    assert resp.success is True
    assert isinstance(resp.content, str)

    huge_usage = TokenUsage(prompt_tokens=1_000_000, completion_tokens=500_000, total_tokens=1_500_000)
    client._update_usage(huge_usage, model="gpt-4o")
    assert huge_usage.estimated_cost_usd > 0.0
    assert client._total_usage.total_tokens >= 1_500_000


def test_adversarial_llm_http_429_rate_limit_backoff_and_router_fallback():
    """Simulate HTTP 429 rate limit with retries, and verify router falls back to Tier 3 rules."""
    client = LLMClient(provider="openai", api_key="sk-real-looking-key-12345", max_retries=1)

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.raise_for_status.side_effect = requests.HTTPError(response=mock_resp)

    router = LLMIntentRouter(llm_client=client, dispatcher=ActionDispatcher())

    with patch.object(client.session, "post", return_value=mock_resp):
        with pytest.raises(LLMRateLimitError):
            client.chat([ChatMessage(role="user", content="hello")])

        fallback_intent = router.parse_intent("bật đèn phòng khách", force_llm=True)
        assert fallback_intent.source == "rule_fallback"
        assert fallback_intent.action_name == "home_assistant_call"
        assert fallback_intent.parameters["domain"] == "light"
        assert fallback_intent.confidence >= 0.8


def test_adversarial_router_rule_fallback_sub_5ms_performance():
    """Benchmark 1,000 iterations of fast-path regex and keyword rule resolution (<5ms p99)."""
    client = LLMClient(provider="mock")
    router = LLMIntentRouter(llm_client=client, dispatcher=ActionDispatcher())

    queries = [
        "bật đèn phòng khách",
        "tắt đèn phòng khách",
        "kiểm tra nhiệt độ cpu",
        "tình trạng hệ thống",
        "quét mạng 192.168.1.0/24",
        "chuẩn bị môi trường làm việc",
        "mở spotify",
        "tự phục hồi hệ thống",
    ]

    latencies = []
    for i in range(1000):
        q = queries[i % len(queries)]
        t0 = time.perf_counter()
        res = router.parse_intent(q, force_llm=False)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(dt_ms)
        assert res.action_name != "unknown_intent"

    avg_latency = np.mean(latencies)
    p99_latency = np.percentile(latencies, 99)
    max_latency = np.max(latencies)

    assert avg_latency < 1.0, f"Average rule lookup latency too high: {avg_latency:.4f}ms"
    assert p99_latency < 5.0, f"p99 rule lookup latency too high: {p99_latency:.4f}ms (limit: 5ms)"


# ============================================================================
# 4. DYNAMIC SCHEMA GENERATOR ADVERSARIAL STRESS TESTS
# ============================================================================

class CustomComplexObject:
    """Arbitrary user-defined class used in parameter type annotations."""
    def __init__(self, val: int):
        self.val = val


def test_adversarial_dynamic_schema_complex_parameter_types():
    dispatcher = ActionDispatcher()

    # Handler 1: Standard types
    def handler_basic(x: int, y: float, flag: bool = True, name: str = "default") -> None:
        """Basic typed handler."""
        pass

    # Handler 2: Union and Optional
    def handler_union_optional(
        target: Union[str, int],
        extra: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Union and optional typed handler."""
        pass

    # Handler 3: Nested Lists and Dicts
    def handler_nested(
        items: List[Dict[str, Union[int, float]]],
        matrix: List[List[int]],
    ) -> None:
        """Nested structures handler."""
        pass

    # Handler 4: Custom class object and untyped args
    def handler_custom_and_untyped(
        obj: CustomComplexObject,
        untyped_param,
        default_val=100,
        *args,
        **kwargs,
    ) -> None:
        """Handler with custom class and untyped arguments."""
        pass

    # Handler 5: No docstring and no type hints
    def handler_naked(a, b):
        pass

    dispatcher.register_action(name="basic", handler=handler_basic, description="Basic action")
    dispatcher.register_action(name="union_opt", handler=handler_union_optional)
    dispatcher.register_action(name="nested", handler=handler_nested)
    dispatcher.register_action(name="custom", handler=handler_custom_and_untyped)
    dispatcher.register_action(name="naked", handler=handler_naked)

    # Generate schemas
    tools = generate_tool_schema_from_dispatcher(dispatcher)
    assert len(tools) == 5

    schema_by_name = {t["function"]["name"]: t["function"] for t in tools}

    # Check basic
    basic_params = schema_by_name["basic"]["parameters"]
    assert basic_params["type"] == "object"
    assert basic_params["properties"]["x"]["type"] == "integer"
    assert basic_params["properties"]["y"]["type"] == "number"
    assert basic_params["properties"]["flag"]["type"] == "boolean"
    assert basic_params["properties"]["name"]["type"] == "string"
    assert "x" in basic_params["required"]
    assert "y" in basic_params["required"]
    assert "flag" not in basic_params["required"]

    # Check union_opt
    union_params = schema_by_name["union_opt"]["parameters"]
    assert "target" in union_params["properties"]
    assert union_params["properties"]["extra"]["type"] == "array"
    assert union_params["properties"]["options"]["type"] == "object"

    # Check nested
    nested_params = schema_by_name["nested"]["parameters"]
    assert nested_params["properties"]["items"]["type"] == "array"
    assert nested_params["properties"]["matrix"]["type"] == "array"

    # Check custom & untyped
    custom_params = schema_by_name["custom"]["parameters"]
    assert "obj" in custom_params["properties"]
    assert "untyped_param" in custom_params["properties"]
    assert "untyped_param" in custom_params["required"]
    assert "default_val" not in custom_params["required"]
    assert "args" not in custom_params["properties"]
    assert "kwargs" not in custom_params["properties"]

    # Check naked
    naked_params = schema_by_name["naked"]["parameters"]
    assert "a" in naked_params["properties"]
    assert "b" in naked_params["properties"]


# ============================================================================
# 5. MODULE INTERFACE & EXPORT CONTRACT VERIFICATION
# ============================================================================

def test_stt_module_all_exports_present():
    """Check all names in jarvis.stt.__all__ are genuinely exported attributes."""
    import jarvis.stt
    missing_exports = [name for name in jarvis.stt.__all__ if not hasattr(jarvis.stt, name)]
    assert missing_exports == [], f"Missing exports in jarvis.stt: {missing_exports}"


def test_llm_module_all_exports_present():
    """Check all names in jarvis.llm.__all__ are genuinely exported attributes."""
    import jarvis.llm
    missing_exports = [name for name in jarvis.llm.__all__ if not hasattr(jarvis.llm, name)]
    assert missing_exports == [], f"Missing exports in jarvis.llm: {missing_exports}"
