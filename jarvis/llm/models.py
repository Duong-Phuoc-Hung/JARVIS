"""
jarvis/llm/models.py
====================
Data models and type definitions for LLM routing and intent resolution in JARVIS.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis.llm.client import LLMResponse


@dataclass
class IntentResult:
    """
    Structured outcome of an intent resolution attempt across fast regex,
    LLM semantic tool calling, or deterministic Vietnamese keyword fallback.
    """
    action_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source: str = "llm"  # "llm", "rule_fallback", "rule_fast_path"
    reasoning: str | None = None
    raw_text: str = ""
    llm_response: LLMResponse | None = None
    response_text: str | None = None
    requires_confirmation: bool = False
    confirmation_prompt: str | None = None
    danger_level: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializes the IntentResult to a plain dictionary."""
        return {
            "action_name": self.action_name,
            "parameters": self.parameters,
            "confidence": self.confidence,
            "source": self.source,
            "reasoning": self.reasoning,
            "raw_text": self.raw_text,
            "response_text": self.response_text,
            "requires_confirmation": self.requires_confirmation,
            "confirmation_prompt": self.confirmation_prompt,
            "danger_level": self.danger_level,
        }

