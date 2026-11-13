"""
jarvis/llm/ollama_client.py
===========================
High-Performance Local LLM Client for Ollama and vLLM.

Provides:
  - Local model auto-discovery via `/api/tags`.
  - Non-streaming & streaming chat completions via `/api/chat`.
  - Single-prompt text generation via `/api/generate`.
  - Text embeddings via `/api/embeddings`.
  - Native tool/function-calling payload adaptation.
  - Fail-closed error handling: never fabricates responses if local daemon is unreachable.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("jarvis.llm.ollama_client")


class OllamaError(Exception):
    """Base exception for all Ollama client errors."""
    pass


class OllamaConnectionError(OllamaError):
    """Raised when the local Ollama daemon cannot be reached."""
    pass


class OllamaModelNotFoundError(OllamaError):
    """Raised when requested model is not downloaded or found locally."""
    pass


class OllamaResponseError(OllamaError):
    """Raised when Ollama returns an HTTP error or malformed JSON."""
    pass


@dataclass
class OllamaChatResponse:
    content: str
    role: str = "assistant"
    model: str = ""
    total_duration_ms: float = 0.0
    prompt_eval_count: int = 0
    eval_count: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    done: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "role": self.role,
            "model": self.model,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "prompt_eval_count": self.prompt_eval_count,
            "eval_count": self.eval_count,
            "tool_calls": self.tool_calls,
            "done": self.done,
        }


class OllamaClient:
    """
    Client for interacting with local Ollama inference service (default http://127.0.0.1:11434).
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        default_model: str = "llama3",
        timeout_seconds: float = 60.0,
        session: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout_seconds = float(timeout_seconds)
        self._session = session

    def _get_session(self) -> Any:
        if self._session is not None:
            return self._session
        import requests
        return requests

    def health_check(self) -> bool:
        """
        Pings Ollama daemon via `/api/version`.
        Fail-closed: Returns False if offline or unreachable.
        """
        try:
            sess = self._get_session()
            resp = sess.get(f"{self.base_url}/api/version", timeout=3.0)
            return resp.status_code == 200
        except Exception as exc:
            logger.debug("Ollama health_check failed: %s", exc)
            return False

    def list_models(self) -> list[str]:
        """
        Lists all locally pulled models from `/api/tags`.
        Fail-closed: Raises OllamaConnectionError if daemon is unreachable.
        """
        try:
            sess = self._get_session()
            resp = sess.get(f"{self.base_url}/api/tags", timeout=5.0)
            if resp.status_code != 200:
                raise OllamaResponseError(f"HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            models = data.get("models", [])
            return [m.get("name", "") for m in models if m.get("name")]
        except OllamaError:
            raise
        except Exception as exc:
            raise OllamaConnectionError(f"Cannot connect to Ollama at {self.base_url}: {exc}") from exc

    def has_model(self, model_name: str) -> bool:
        """Checks if specified model is present locally."""
        try:
            pulled = self.list_models()
            target = model_name.lower()
            return any(target == m.lower() or target in m.lower().split(":") for m in pulled)
        except OllamaConnectionError:
            return False

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        format: str | None = None,
    ) -> OllamaChatResponse:
        """
        Executes chat completion against `/api/chat`.
        Fail-closed: Raises descriptive OllamaError on connection or execution failure.
        """
        target_model = model or self.default_model
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens
        if tools:
            payload["tools"] = tools
        if format:
            payload["format"] = format

        try:
            sess = self._get_session()
            resp = sess.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout_seconds,
            )
            if resp.status_code == 404:
                raise OllamaModelNotFoundError(f"Model '{target_model}' not found in local Ollama repository.")
            if resp.status_code != 200:
                raise OllamaResponseError(f"Ollama chat error (HTTP {resp.status_code}): {resp.text}")

            data = resp.json()
            msg = data.get("message", {})
            content = msg.get("content", "")
            role = msg.get("role", "assistant")
            tool_calls = msg.get("tool_calls", [])

            dur_ns = data.get("total_duration", 0)
            dur_ms = dur_ns / 1_000_000.0 if dur_ns else 0.0

            return OllamaChatResponse(
                content=content,
                role=role,
                model=data.get("model", target_model),
                total_duration_ms=dur_ms,
                prompt_eval_count=data.get("prompt_eval_count", 0),
                eval_count=data.get("eval_count", 0),
                tool_calls=tool_calls,
                done=data.get("done", True),
            )
        except OllamaError:
            raise
        except Exception as exc:
            raise OllamaConnectionError(f"Failed to communicate with Ollama: {exc}") from exc

    def generate_stream(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> Generator[str, None, None]:
        """
        Streams generated text tokens from `/api/generate`.
        Yields token strings as they arrive.
        """
        target_model = model or self.default_model
        payload: dict[str, Any] = {
            "model": target_model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
            },
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        try:
            sess = self._get_session()
            resp = sess.post(
                f"{self.base_url}/api/generate",
                json=payload,
                stream=True,
                timeout=self.timeout_seconds,
            )
            if resp.status_code != 200:
                raise OllamaResponseError(f"HTTP {resp.status_code}: {resp.text}")

            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line.decode("utf-8") if isinstance(line, bytes) else line)
                    token = chunk.get("response", "")
                    if token:
                        yield token
                    if chunk.get("done", False):
                        break
                except Exception:
                    continue
        except OllamaError:
            raise
        except Exception as exc:
            raise OllamaConnectionError(f"Ollama streaming connection broke: {exc}") from exc

    def embeddings(self, prompt: str, model: str | None = None) -> list[float]:
        """
        Generates text embedding vector via `/api/embeddings`.
        """
        target_model = model or self.default_model
        payload = {
            "model": target_model,
            "prompt": prompt,
        }
        try:
            sess = self._get_session()
            resp = sess.post(
                f"{self.base_url}/api/embeddings",
                json=payload,
                timeout=self.timeout_seconds,
            )
            if resp.status_code != 200:
                raise OllamaResponseError(f"HTTP {resp.status_code}: {resp.text}")
            data = resp.json()
            return list(data.get("embedding", []))
        except OllamaError:
            raise
        except Exception as exc:
            raise OllamaConnectionError(f"Ollama embeddings call failed: {exc}") from exc
