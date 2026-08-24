"""
jarvis/llm
==========
LLM Semantic Intent Engine and Multi-Provider Client Package for JARVIS.
"""
from __future__ import annotations

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

__all__ = [
    "ChatMessage",
    "IntentResult",
    "LLMAuthenticationError",
    "LLMClient",
    "LLMError",
    "LLMIntentRouter",
    "LLMProvider",
    "LLMProviderError",
    "LLMRateLimitError",
    "LLMResponse",
    "LLMResponseParsingError",
    "LLMTimeoutError",
    "TokenUsage",
    "ToolCall",
    "build_jarvis_system_prompt",
    "generate_tool_schema_from_dispatcher",
]
