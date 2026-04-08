from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class OpenAILocalIntelligenceConfig:
    """Centralized provider configuration for OpenAI-backed extraction."""

    model: str = "gpt-5-mini"
    reasoning_effort: str = "low"
    max_output_tokens: int = 1800
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "OpenAILocalIntelligenceConfig":
        return cls(
            model=os.environ.get("BRIARWOOD_LOCAL_INTELLIGENCE_MODEL", "gpt-5-mini"),
            reasoning_effort=os.environ.get("BRIARWOOD_LOCAL_INTELLIGENCE_REASONING", "low"),
            max_output_tokens=_int_env("BRIARWOOD_LOCAL_INTELLIGENCE_MAX_OUTPUT_TOKENS", 1800),
            timeout_seconds=_float_env("BRIARWOOD_LOCAL_INTELLIGENCE_TIMEOUT_SECONDS", 30.0),
        )


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        return float(raw)
    except ValueError:
        return default
