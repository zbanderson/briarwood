"""Shared helpers for deterministic chat-tier Scout patterns."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from briarwood.routing_schema import UnifiedIntelligenceOutput


def unified_dict(unified: UnifiedIntelligenceOutput) -> dict[str, Any]:
    """Return a JSON-like dict for path lookups."""

    return unified.model_dump(mode="json")


def get_path(data: Mapping[str, Any], path: str) -> Any:
    """Read a dotted path from nested dicts."""

    current: Any = data
    for part in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def first_path(data: Mapping[str, Any], paths: tuple[str, ...]) -> tuple[Any, str | None]:
    """Return the first non-None value and the path that produced it."""

    for path in paths:
        value = get_path(data, path)
        if value is not None:
            return value, path
    return None, None


def as_float(value: Any) -> float | None:
    """Coerce numeric-looking values without treating booleans as numbers."""

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def as_bool(value: Any) -> bool:
    """Coerce common bool-like values from structured payloads."""

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    if isinstance(value, (int, float)):
        return value != 0
    return False
