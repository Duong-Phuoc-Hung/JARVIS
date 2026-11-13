"""
tests/unit/test_ollama_client.py
================================
Unit tests for OllamaClient: model discovery, chat completions, streaming,
embeddings, and fail-closed error handling.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from jarvis.llm.ollama_client import (
    OllamaChatResponse,
    OllamaClient,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaResponseError,
)


def test_health_check() -> None:
    """Verify health_check pinging /api/version."""
    mock_session = MagicMock()

    # Online
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_session.get.return_value = mock_resp

    client = OllamaClient(session=mock_session)
    assert client.health_check() is True

    # Offline / Connection exception
    mock_session.get.side_effect = ConnectionRefusedError("Offline")
    assert client.health_check() is False


def test_list_models_and_has_model() -> None:
    """Verify listing models and checking model existence."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [
            {"name": "llama3:8b", "size": 4661224676},
            {"name": "qwen2.5:7b", "size": 4434250368},
            {"name": "nomic-embed-text:latest", "size": 274302450},
        ]
    }
    mock_session.get.return_value = mock_resp

    client = OllamaClient(session=mock_session)
    models = client.list_models()
    assert "llama3:8b" in models
    assert "qwen2.5:7b" in models

    assert client.has_model("llama3:8b") is True
    assert client.has_model("llama3") is True
    assert client.has_model("deepseek-r1") is False


def test_chat_completion_success() -> None:
    """Verify successful chat completion and response data structure."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "model": "llama3",
        "message": {
            "role": "assistant",
            "content": "Tôi là JARVIS, trợ lý AI của Ngài.",
            "tool_calls": [],
        },
        "total_duration": 450000000,  # 450ms
        "prompt_eval_count": 12,
        "eval_count": 18,
        "done": True,
    }
    mock_session.post.return_value = mock_resp

    client = OllamaClient(session=mock_session)
    resp = client.chat(
        messages=[{"role": "user", "content": "Bạn là ai?"}],
        model="llama3",
        temperature=0.7,
    )

    assert isinstance(resp, OllamaChatResponse)
    assert resp.content == "Tôi là JARVIS, trợ lý AI của Ngài."
    assert resp.model == "llama3"
    assert resp.total_duration_ms == 450.0
    assert resp.prompt_eval_count == 12
    assert resp.eval_count == 18
    d = resp.to_dict()
    assert d["content"] == resp.content


def test_chat_model_not_found() -> None:
    """Verify HTTP 404 raises OllamaModelNotFoundError."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = "model 'non-existent' not found"
    mock_session.post.return_value = mock_resp

    client = OllamaClient(session=mock_session)
    with pytest.raises(OllamaModelNotFoundError, match="not found in local Ollama repository"):
        client.chat(messages=[{"role": "user", "content": "hi"}], model="non-existent")


def test_chat_connection_error_fail_closed() -> None:
    """Verify fail-closed exception when daemon is unreachable."""
    mock_session = MagicMock()
    mock_session.post.side_effect = ConnectionRefusedError("Connection refused: 11434")

    client = OllamaClient(session=mock_session)
    with pytest.raises(OllamaConnectionError, match="Failed to communicate with Ollama"):
        client.chat(messages=[{"role": "user", "content": "hi"}])


def test_generate_stream() -> None:
    """Verify generator streaming token chunks."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_lines.return_value = [
        json.dumps({"response": "Xin "}).encode("utf-8"),
        json.dumps({"response": "chào "}).encode("utf-8"),
        json.dumps({"response": "Ngài.", "done": True}).encode("utf-8"),
    ]
    mock_session.post.return_value = mock_resp

    client = OllamaClient(session=mock_session)
    tokens = list(client.generate_stream(prompt="Xin chào"))
    assert tokens == ["Xin ", "chào ", "Ngài."]


def test_embeddings() -> None:
    """Verify embeddings vector extraction."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "embedding": [0.12, -0.45, 0.78, 0.01]
    }
    mock_session.post.return_value = mock_resp

    client = OllamaClient(session=mock_session)
    vec = client.embeddings(prompt="Vector test", model="nomic-embed-text")
    assert vec == [0.12, -0.45, 0.78, 0.01]
