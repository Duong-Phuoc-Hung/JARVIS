"""
tests/unit/test_speculative_prerouting.py
=========================================
Unit tests for Speculative Intent Pre-Routing and Streaming STT Integration.
Tests:
  - PreWarmCache caching, TTL expiration, and resource resolution.
  - Partial hypothesis anticipation and speculative candidate generation.
  - Speculative pre-route HIT upon matching final hypothesis.
  - Immediate cancellation / cache purge on mid-sentence correction ("à thôi", "hủy").
  - StreamingSTTSession end-to-end integration with SpeculativePreRouter.
"""
from __future__ import annotations

import time
import numpy as np
import pytest

from jarvis.llm.client import LLMClient
from jarvis.llm.router import LLMIntentRouter
from jarvis.stt.speculative_router import (
    PreWarmCache,
    SpeculativeIntentCandidate,
    SpeculativePreRouter,
)
from jarvis.stt.streaming import StreamingConfig, StreamingSTTSession


def test_prewarm_cache_lifecycle():
    """Verify pre-warming app executables and cache expiration."""
    cache = PreWarmCache(ttl_seconds=0.2)

    # Prewarm app_launch
    data = cache.prewarm("app_launch", {"app_name": "vscode"})
    assert data["status"] == "ready"
    assert data["app_resolved"] is True
    assert "executable_path" in data

    # Cache hit
    cached = cache.get("app_launch", {"app_name": "vscode"})
    assert cached is not None
    assert cached["app_resolved"] is True
    assert cache.metrics["hits"] == 1

    # Wait for TTL expiration
    time.sleep(0.25)
    expired = cache.get("app_launch", {"app_name": "vscode"})
    assert expired is None
    assert cache.metrics["misses"] >= 1


def test_speculative_prerouting_partial_and_hit():
    """Verify speculative pre-route trigger on partial and confirmed HIT on final utterance."""
    mock_llm = LLMClient.__new__(LLMClient)
    router = LLMIntentRouter(llm_client=mock_llm, fast_path_enabled=True)
    spec_router = SpeculativePreRouter(router=router, min_speculative_confidence=0.5)

    # Step 1: Partial hypothesis as user is still speaking
    cand = spec_router.on_partial_hypothesis("mở ứng dụng visual studio code")
    assert cand is not None
    assert cand.action_name in ("app_launch", "app_open", "workspace_prepare")
    assert spec_router.current_candidate is not None

    # Step 2: Final turn completes with matching utterance
    t0 = time.perf_counter()
    final_res, is_hit = spec_router.on_final_hypothesis("mở visual studio code")
    dispatch_prep_latency = (time.perf_counter() - t0) * 1000.0

    assert is_hit is True
    assert final_res.parameters.get("_speculative_hit") is True
    assert "_prewarmed_payload" in final_res.parameters
    assert dispatch_prep_latency < 10.0, f"Dispatch prep latency {dispatch_prep_latency:.2f}ms exceeds 10ms"
    assert spec_router.speculative_hits == 1


def test_speculative_cancellation_on_negation():
    """Verify that user mid-sentence correction ('à thôi đừng mở') purges speculation fail-closed."""
    mock_llm = LLMClient.__new__(LLMClient)
    router = LLMIntentRouter(llm_client=mock_llm, fast_path_enabled=True)
    spec_router = SpeculativePreRouter(router=router, min_speculative_confidence=0.5)

    # Candidate triggered
    cand = spec_router.on_partial_hypothesis("mở trình duyệt chrome")
    assert cand is not None

    # User cancels mid-sentence
    final_res, is_hit = spec_router.on_final_hypothesis("mở trình duyệt chrome à thôi đừng mở nữa")
    assert is_hit is False
    assert spec_router.current_candidate is None
    assert spec_router.prewarm_cache.metrics["size"] == 0
    assert spec_router.speculative_cancellations == 1


def test_streaming_stt_session_with_speculative_router():
    """Verify StreamingSTTSession drives SpeculativePreRouter on partial and final audio events."""
    mock_llm = LLMClient.__new__(LLMClient)
    router = LLMIntentRouter(llm_client=mock_llm, fast_path_enabled=True)
    spec_router = SpeculativePreRouter(router=router, min_speculative_confidence=0.5)

    # Custom mock transcriber simulating partial then final speech
    turn_counter = [0]

    def mock_transcribe(audio_samples: np.ndarray, lang: str = "vi") -> str:
        turn_counter[0] += 1
        if turn_counter[0] == 1:
            return "tăng âm lượng lên"
        return "tăng âm lượng lên 80%"

    partials_received = []
    finals_received = []

    session = StreamingSTTSession(
        transcriber_fn=mock_transcribe,
        config=StreamingConfig(min_speech_s=0.1, step_interval_s=0.01, silence_cutoff_s=0.1),
        on_partial=lambda t: partials_received.append(t),
        on_final=lambda t: finals_received.append(t),
        speculative_router=spec_router,
    )

    # Feed speech chunk (300Hz sine wave within speech bandpass)
    t_speech = np.linspace(0, 0.5, 8000, endpoint=False)
    speech_pcm = (0.5 * np.sin(2 * np.pi * 300 * t_speech)).astype(np.float32)
    # First chunk to activate speech
    session.feed(speech_pcm[:4000])
    time.sleep(0.02)
    # Second chunk to trigger partial hypothesis
    hyp_partial = session.feed(speech_pcm[4000:])

    time.sleep(0.02)
    # Feed silence chunk to trigger finalization (silence cutoff is 1600 samples)
    silence_pcm = np.zeros(2000, dtype=np.float32)
    hyp_final = session.feed(silence_pcm)

    assert hyp_final is not None
    assert hyp_final.is_final is True
    assert hyp_final.speculative_hit is True
    assert hyp_final.speculative_candidate is not None
