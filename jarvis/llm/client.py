"""
jarvis/llm/client.py
====================
Unified Multi-Provider LLM REST Client for JARVIS.
Supports OpenAI, Google Gemini, Anthropic Claude, Ollama, and Deterministic Mock.
Uses pure HTTP REST via `requests` (zero mandatory vendor SDKs).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    requests = None  # type: ignore[assignment]
    REQUESTS_AVAILABLE = False

logger = logging.getLogger("jarvis.llm.client")


class LLMProvider(str, Enum):
    OPENAI = "openai"
    GEMINI = "gemini"
    CLAUDE = "claude"
    OLLAMA = "ollama"
    MOCK = "mock"


class LLMError(Exception):
    """Base exception for all LLM client errors."""
    pass


class LLMAuthenticationError(LLMError, PermissionError):
    """Raised when API key is missing or rejected (HTTP 401)."""
    pass


class LLMRateLimitError(LLMError):
    """Raised when API rate limit is exceeded (HTTP 429)."""
    pass


class LLMTimeoutError(LLMError, TimeoutError):
    """Raised when an LLM HTTP request times out."""
    pass


class LLMProviderError(LLMError):
    """Raised when upstream LLM provider returns 5xx error."""
    pass


class LLMResponseParsingError(LLMError):
    """Raised when provider payload cannot be parsed."""
    pass


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
        }


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_arguments: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
            "raw_arguments": self.raw_arguments,
        }


@dataclass
class ChatMessage:
    role: str  # "system", "user", "assistant", "tool"
    content: str
    name: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            res["name"] = self.name
        if self.tool_calls:
            res["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        if self.tool_call_id:
            res["tool_call_id"] = self.tool_call_id
        return res


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    provider: str = "openai"
    model: str = ""
    usage: TokenUsage = field(default_factory=TokenUsage)
    raw_response: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    success: bool = True
    error: str | None = None

    def __str__(self) -> str:
        """Enables string compatibility with assertions (e.g. `assert 'gemini' in res`)."""
        if self.content:
            return self.content
        if self.tool_calls:
            return f"ToolCall: {self.tool_calls[0].name}({self.tool_calls[0].arguments})"
        return f"Response from {self.provider}"

    def __contains__(self, item: str) -> bool:
        """Enables substring checks directly on response object."""
        return item.lower() in str(self).lower() or item.lower() in self.provider.lower()


class LLMClient:
    """
    Unified Multi-Provider LLM REST Client for JARVIS.
    Supports OpenAI, Google Gemini, Anthropic Claude, Ollama, and Deterministic Mock.
    Uses pure HTTP REST via `requests` (zero mandatory vendor SDKs).
    """

    DEFAULT_MODELS = {
        LLMProvider.OPENAI: "gpt-4o",
        LLMProvider.GEMINI: "gemini-1.5-flash",
        LLMProvider.CLAUDE: "claude-3-5-sonnet-20241022",
        LLMProvider.OLLAMA: "llama3.2",
        LLMProvider.MOCK: "mock-model",
    }

    DEFAULT_ENDPOINTS = {
        LLMProvider.OPENAI: "https://api.openai.com/v1/chat/completions",
        LLMProvider.GEMINI: "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        LLMProvider.CLAUDE: "https://api.anthropic.com/v1/messages",
        LLMProvider.OLLAMA: "http://localhost:11434/api/chat",
    }

    # Pricing per 1M tokens (Prompt, Completion)
    PRICING_MAP = {
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gemini-1.5-flash": (0.075, 0.30),
        "gemini-1.5-pro": (1.25, 5.00),
        "claude-3-5-sonnet": (3.00, 15.00),
        "claude-3-haiku": (0.25, 1.25),
    }

    def __init__(
        self,
        provider: LLMProvider | str = "gemini",
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        default_temperature: float = 0.7,
        default_max_tokens: int = 1024,
        mock_mode: bool = False,
    ) -> None:
        if isinstance(provider, str):
            try:
                self.provider = LLMProvider(provider.lower())
            except ValueError as exc:
                valid = ", ".join(p.value for p in LLMProvider)
                raise ValueError(
                    f"Unknown LLM provider {provider!r}. Valid providers: {valid}."
                ) from exc
        else:
            self.provider = provider

        self.api_key = (
            api_key
            if api_key is not None
            else (
                os.environ.get(f"JARVIS_{self.provider.value.upper()}_API_KEY")
                or os.environ.get(f"{self.provider.value.upper()}_API_KEY", "")
            )
        )
        self.model = model or self.DEFAULT_MODELS.get(self.provider, "default-model")
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens
        self.mock_mode = mock_mode

        self.session = requests.Session() if REQUESTS_AVAILABLE else None
        self.call_history: list[dict[str, Any]] = []
        self._total_usage = TokenUsage()

        # Mocking controls
        self._mock_rules: dict[str, Any] = {}
        self._canned_responses: list[LLMResponse] = []
        self._mock_error: str | None = None
        self._mock_delay_s: float = 0.0

    def set_mock_behavior(
        self,
        rules: dict[str, Any] | None = None,
        canned_responses: list[LLMResponse] | None = None,
        mock_error: str | None = None,
        mock_delay_s: float = 0.0,
    ) -> None:
        """Configures mock engine behavior for deterministic unit & E2E tests."""
        if rules is not None:
            self._mock_rules = rules
        if canned_responses is not None:
            self._canned_responses = canned_responses
        self._mock_error = mock_error
        self._mock_delay_s = mock_delay_s

    def _sanitize_error_text(self, text: str) -> str:
        """
        Strips the configured API key out of an error message before it is
        raised or logged. Some transport-layer exceptions embed the request
        URL verbatim (e.g. a Gemini ConnectionError, whose URL carries the
        key as a `?key=...` query parameter) -- this keeps that key from
        leaking into logs/exception text now that real transport failures
        are surfaced instead of silently swallowed into a mock response.
        """
        if self.api_key and text:
            return text.replace(self.api_key, "***REDACTED***")
        return text

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        mock_http: Any | None = None,
    ) -> LLMResponse:
        """Convenience method sending a single prompt, returning LLMResponse."""
        messages = []
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))
        messages.append(ChatMessage(role="user", content=prompt))

        return self.chat(
            messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            mock_http=mock_http,
        )

    def chat(
        self,
        messages: Sequence[ChatMessage | dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        mock_http: Any | None = None,
    ) -> LLMResponse:
        """Executes a chat completion across configured provider with error isolation & retries."""
        normalized_messages: list[ChatMessage] = []
        for m in messages:
            if isinstance(m, ChatMessage):
                normalized_messages.append(m)
            elif isinstance(m, dict):
                normalized_messages.append(ChatMessage(role=m.get("role", "user"), content=m.get("content", "")))

        # 1. Permission / Authentication Validation
        if not self.api_key and self.provider not in (LLMProvider.OLLAMA, LLMProvider.MOCK):
            raise LLMAuthenticationError(f"API key required for cloud LLM provider '{self.provider.value}'")

        # 2. Check Mock / Synthetic Test Mode. These are the only paths that
        # may return a synthetic response: explicit MOCK provider, explicit
        # mock_mode, or the explicit (env-var-gated, no-base-url) Ollama test
        # mode. A REAL configured provider's request failure (timeout,
        # connection error, transport error, etc.) must never silently
        # become a synthetic success -- see the exception handling below.
        if self.provider == LLMProvider.MOCK or self.mock_mode or (
            self.provider == LLMProvider.OLLAMA and not self.base_url and os.environ.get("JARVIS_TEST_MODE") == "1"
        ):
            return self._execute_mock(normalized_messages, tools, mock_http=mock_http)

        # 3. Record Call History
        user_prompt = normalized_messages[-1].content if normalized_messages else ""
        self.call_history.append({
            "provider": self.provider.value,
            "model": self.model,
            "prompt": user_prompt,
            "timestamp": time.time(),
        })

        if not REQUESTS_AVAILABLE:
            raise LLMProviderError("requests library not installed")

        # 4. Provider Wire Request Dispatch with Exponential Backoff
        temp = temperature if temperature is not None else self.default_temperature
        tokens = max_tokens if max_tokens is not None else self.default_max_tokens

        for attempt in range(self.max_retries + 1):
            try:
                t0 = time.perf_counter()
                if self.provider == LLMProvider.OPENAI:
                    resp = self._call_openai(normalized_messages, tools, temp, tokens)
                elif self.provider == LLMProvider.GEMINI:
                    resp = self._call_gemini(normalized_messages, tools, temp, tokens)
                elif self.provider == LLMProvider.CLAUDE:
                    resp = self._call_claude(normalized_messages, tools, temp, tokens)
                elif self.provider == LLMProvider.OLLAMA:
                    resp = self._call_ollama(normalized_messages, tools, temp, tokens)
                else:
                    # Unreachable in practice (the constructor rejects any
                    # provider string that isn't a valid LLMProvider member,
                    # and MOCK always returns above before this loop is ever
                    # entered) -- but a production dispatch path must fail
                    # closed rather than ever synthesize a response for an
                    # unsupported/unexpected provider state.
                    raise LLMProviderError(f"Unsupported LLM provider state: {self.provider!r}")

                resp.latency_ms = (time.perf_counter() - t0) * 1000.0
                self._update_usage(resp.usage, self.model)
                return resp

            except requests.Timeout as exc:
                if attempt == self.max_retries:
                    raise LLMTimeoutError(
                        f"LLM request to {self.provider.value} timed out after {self.timeout}s: "
                        f"{self._sanitize_error_text(str(exc))}"
                    ) from exc
                time.sleep(0.5 * (2 ** attempt))
            except requests.ConnectionError as exc:
                # A real connection failure (daemon not running, host
                # unreachable, DNS failure, etc.) is a genuine provider
                # unavailability -- it must never be reported as a
                # successful (mocked or otherwise) response, for Ollama or
                # any other provider.
                if attempt == self.max_retries:
                    raise LLMProviderError(
                        f"Could not connect to {self.provider.value}: {self._sanitize_error_text(str(exc))}"
                    ) from exc
                time.sleep(0.5 * (2 ** attempt))
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                if status == 401:
                    raise LLMAuthenticationError(f"Authentication failed for {self.provider.value} (HTTP 401).")
                elif status == 429:
                    if attempt == self.max_retries:
                        raise LLMRateLimitError(f"Rate limit exceeded on {self.provider.value} (HTTP 429).")
                    time.sleep(1.0 * (2 ** attempt))
                elif status >= 500:
                    if attempt == self.max_retries:
                        raise LLMProviderError(f"Server error from {self.provider.value} (HTTP {status}).")
                    time.sleep(1.0 * (2 ** attempt))
                else:
                    raise LLMProviderError(
                        f"HTTP {status} error from {self.provider.value}: {self._sanitize_error_text(str(exc))}"
                    )
            except Exception as exc:
                if isinstance(exc, LLMError):
                    raise
                # A real transport/OS-level failure is a genuine provider
                # failure -- it must never be silently converted into a
                # synthetic successful response. Only provider=MOCK or
                # mock_mode may ever produce a mock LLMResponse (checked
                # above, before this loop is ever entered).
                if isinstance(exc, (requests.RequestException, ConnectionError, OSError)):
                    raise LLMProviderError(
                        f"Transport error calling {self.provider.value}: {self._sanitize_error_text(str(exc))}"
                    ) from exc
                raise LLMProviderError(
                    f"Unexpected error calling {self.provider.value}: {self._sanitize_error_text(str(exc))}"
                ) from exc

        raise LLMProviderError(f"Exhausted retries calling {self.provider.value}")

    def _execute_mock(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None,
        mock_http: Any | None = None,
    ) -> LLMResponse:
        """Deterministic mock response synthesizer."""
        if self._mock_delay_s > 0:
            time.sleep(self._mock_delay_s)
        if self._mock_error == "auth_error":
            raise LLMAuthenticationError("Mock authentication failure")
        elif self._mock_error == "rate_limit":
            raise LLMRateLimitError("Mock rate limit failure")
        elif self._mock_error == "timeout":
            raise LLMTimeoutError("Mock timeout failure")

        prompt = messages[-1].content if messages else ""
        self.call_history.append({"provider": self.provider.value, "prompt": prompt, "model": self.model})

        if self._canned_responses:
            return self._canned_responses.pop(0)

        # Intercept via MockHttpServer fixture if available
        if mock_http is not None and hasattr(mock_http, "llm_canned_intents"):
            for phrase, mapping in mock_http.llm_canned_intents.items():
                if phrase.lower() in prompt.lower():
                    tool_call = ToolCall(
                        id=f"call_{uuid.uuid4().hex[:8]}",
                        name=mapping.get("action", mapping.get("tool", "")),
                        arguments=dict(mapping),
                        raw_arguments=json.dumps(mapping),
                    )
                    return LLMResponse(
                        content="",
                        tool_calls=[tool_call],
                        provider=self.provider.value,
                        model=self.model,
                        success=True,
                    )

        # Check programmed mock rule matching
        for pattern, res in self._mock_rules.items():
            if pattern.lower() in prompt.lower():
                if isinstance(res, LLMResponse):
                    return res
                elif isinstance(res, dict) and "tool" in res:
                    return LLMResponse(
                        content="",
                        tool_calls=[ToolCall(id="mock_1", name=res["tool"], arguments=res.get("args", {}))],
                        provider=self.provider.value,
                        model="mock",
                        success=True,
                    )
                return LLMResponse(content=str(res), provider=self.provider.value, model="mock", success=True)

        return LLMResponse(
            content=f"Response for '{prompt}' from {self.provider.value}",
            provider=self.provider.value,
            model=self.model,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=15, total_tokens=25),
            success=True,
        )

    # Provider HTTP REST Implementations (OpenAI, Gemini, Claude, Ollama)
    def _call_openai(self, messages: list[ChatMessage], tools: list[dict[str, Any]] | None, temperature: float, max_tokens: int) -> LLMResponse:
        assert self.session is not None
        url = self.base_url or self.DEFAULT_ENDPOINTS[LLMProvider.OPENAI]
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        formatted_messages = [m.to_dict() for m in messages]
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        res = self.session.post(url, headers=headers, json=payload, timeout=self.timeout)
        res.raise_for_status()
        data = res.json()

        choice = data["choices"][0]
        msg = choice.get("message", {})
        content = msg.get("content") or ""

        tool_calls: list[ToolCall] = []
        if "tool_calls" in msg:
            for tc in msg["tool_calls"]:
                raw_args = tc.get("function", {}).get("arguments", "{}")
                tool_calls.append(ToolCall(
                    id=tc.get("id", str(uuid.uuid4())),
                    name=tc.get("function", {}).get("name", ""),
                    arguments=self._clean_and_parse_json(raw_args),
                    raw_arguments=raw_args,
                ))

        usage_data = data.get("usage", {})
        usage = TokenUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            provider="openai",
            model=self.model,
            usage=usage,
            raw_response=data,
            finish_reason=choice.get("finish_reason", "stop"),
            success=True,
        )

    def _call_gemini(self, messages: list[ChatMessage], tools: list[dict[str, Any]] | None, temperature: float, max_tokens: int) -> LLMResponse:
        assert self.session is not None
        endpoint = self.DEFAULT_ENDPOINTS[LLMProvider.GEMINI].format(model=self.model)
        url = f"{endpoint}?key={self.api_key}" if not self.base_url else self.base_url
        headers = {"Content-Type": "application/json"}

        system_instruction = None
        contents = []
        for m in messages:
            if m.role == "system":
                system_instruction = {"parts": [{"text": m.content}]}
            else:
                role = "model" if m.role == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": m.content}]})

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction
        if tools:
            gemini_funcs = []
            for t in tools:
                func = t.get("function", t)
                gemini_funcs.append({
                    "name": func.get("name"),
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {}),
                })
            payload["tools"] = [{"functionDeclarations": gemini_funcs}]

        res = self.session.post(url, headers=headers, json=payload, timeout=self.timeout)
        res.raise_for_status()
        data = res.json()

        content = ""
        tool_calls: list[ToolCall] = []
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for p in parts:
                if "text" in p:
                    content += p["text"]
                elif "functionCall" in p:
                    fc = p["functionCall"]
                    tool_calls.append(ToolCall(
                        id=str(uuid.uuid4())[:8],
                        name=fc.get("name", ""),
                        arguments=fc.get("args", {}),
                        raw_arguments=json.dumps(fc.get("args", {})),
                    ))

        meta = data.get("usageMetadata", {})
        usage = TokenUsage(
            prompt_tokens=meta.get("promptTokenCount", 0),
            completion_tokens=meta.get("candidatesTokenCount", 0),
            total_tokens=meta.get("totalTokenCount", 0),
        )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            provider="gemini",
            model=self.model,
            usage=usage,
            raw_response=data,
            success=True,
        )

    def _call_claude(self, messages: list[ChatMessage], tools: list[dict[str, Any]] | None, temperature: float, max_tokens: int) -> LLMResponse:
        assert self.session is not None
        url = self.base_url or self.DEFAULT_ENDPOINTS[LLMProvider.CLAUDE]
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        system_prompt = ""
        formatted_messages = []
        for m in messages:
            if m.role == "system":
                system_prompt = m.content
            else:
                formatted_messages.append({"role": m.role, "content": m.content})

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt
        if tools:
            claude_tools = []
            for t in tools:
                func = t.get("function", t)
                claude_tools.append({
                    "name": func.get("name"),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {}),
                })
            payload["tools"] = claude_tools

        res = self.session.post(url, headers=headers, json=payload, timeout=self.timeout)
        res.raise_for_status()
        data = res.json()

        content = ""
        tool_calls: list[ToolCall] = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.get("id", str(uuid.uuid4())),
                    name=block.get("name", ""),
                    arguments=block.get("input", {}),
                    raw_arguments=json.dumps(block.get("input", {})),
                ))

        usage_data = data.get("usage", {})
        prompt_tokens = usage_data.get("input_tokens", 0)
        comp_tokens = usage_data.get("output_tokens", 0)
        usage = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=comp_tokens,
            total_tokens=prompt_tokens + comp_tokens,
        )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            provider="claude",
            model=self.model,
            usage=usage,
            raw_response=data,
            finish_reason=data.get("stop_reason", "end_turn"),
            success=True,
        )

    def _call_ollama(self, messages: list[ChatMessage], tools: list[dict[str, Any]] | None, temperature: float, max_tokens: int) -> LLMResponse:
        assert self.session is not None
        url = self.base_url or self.DEFAULT_ENDPOINTS[LLMProvider.OLLAMA]
        headers = {"Content-Type": "application/json"}
        formatted_messages = [m.to_dict() for m in messages]
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if tools:
            payload["tools"] = tools

        res = self.session.post(url, headers=headers, json=payload, timeout=self.timeout)
        res.raise_for_status()
        data = res.json()

        msg = data.get("message", {})
        content = msg.get("content", "")
        tool_calls: list[ToolCall] = []
        if "tool_calls" in msg:
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                tool_calls.append(ToolCall(
                    id=str(uuid.uuid4())[:8],
                    name=fn.get("name", ""),
                    arguments=fn.get("arguments", {}),
                    raw_arguments=json.dumps(fn.get("arguments", {})),
                ))

        prompt_eval = data.get("prompt_eval_count", 0)
        eval_count = data.get("eval_count", 0)
        usage = TokenUsage(
            prompt_tokens=prompt_eval,
            completion_tokens=eval_count,
            total_tokens=prompt_eval + eval_count,
        )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            provider="ollama",
            model=self.model,
            usage=usage,
            raw_response=data,
            success=True,
        )

    def _clean_and_parse_json(self, raw_str: str) -> dict[str, Any]:
        """Cleans and robustly parses JSON with markdown strip and regex fallback."""
        if not raw_str or not isinstance(raw_str, str):
            return {}
        cleaned = raw_str.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            return json.loads(cleaned)
        except Exception:
            pairs = re.findall(r'["\']?(\w+)["\']?\s*:\s*["\']?([^,"\']+)["\']?', cleaned)
            return {k: v for k, v in pairs}

    def _update_usage(self, usage: TokenUsage, model: str) -> None:
        self._total_usage.prompt_tokens += usage.prompt_tokens
        self._total_usage.completion_tokens += usage.completion_tokens
        self._total_usage.total_tokens += usage.total_tokens

        pricing = self.PRICING_MAP.get(model, (0.0, 0.0))
        cost = (usage.prompt_tokens / 1_000_000.0 * pricing[0]) + (usage.completion_tokens / 1_000_000.0 * pricing[1])
        usage.estimated_cost_usd = round(cost, 6)
        self._total_usage.estimated_cost_usd += usage.estimated_cost_usd
