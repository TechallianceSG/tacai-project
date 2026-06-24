"""Future LLM integration seam.

Current MVP engines are local rules-based. This module defines a small interface so
future OpenAI/Claude/Azure providers can be added without changing CLI, Web UI, or
reporting flows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMRequest:
    task: str
    prompt: str
    system_prompt: str = ""
    temperature: float = 0.2


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str


class LLMClient(Protocol):
    """Provider-neutral text generation contract for later API integration."""

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Generate text for a recruitment intelligence task."""


class LocalRulesOnlyLLMClient:
    """Default placeholder that makes the no-API policy explicit."""

    provider = "local-rules"
    model = "deterministic-mvp"

    def generate(self, request: LLMRequest) -> LLMResponse:
        raise RuntimeError(
            "LLM API integration is not enabled for this MVP. Use local rules engines or add a provider implementing LLMClient."
        )
