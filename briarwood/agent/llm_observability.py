"""Shared LLM observability, retry, and in-process caching helpers.

The agent layer has several small structured-output LLM calls. This module
keeps their operational behavior consistent without changing the semantic
owner of any decision logic.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, TypeVar

from pydantic import BaseModel

from briarwood.cost_guard import BudgetExceeded

_logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalized_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(slots=True)
class LLMCallRecord:
    surface: str
    schema_name: str | None
    provider: str | None
    model: str | None
    prompt_hash: str
    response_hash: str | None = None
    status: str = "started"
    attempts: int = 0
    duration_ms: float = 0.0
    cache_hit: bool = False
    error_type: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    debug_payload: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMCallLedger:
    """Process-local call ledger.

    Full prompt/response bodies are excluded by default. Set
    ``BRIARWOOD_LLM_DEBUG_PAYLOADS=1`` to attach them to records in-process.
    """

    def __init__(self) -> None:
        self.records: list[LLMCallRecord] = []

    @property
    def debug_payloads_enabled(self) -> bool:
        return os.environ.get("BRIARWOOD_LLM_DEBUG_PAYLOADS", "").strip() in {
            "1",
            "true",
            "yes",
        }

    def append(self, record: LLMCallRecord) -> None:
        self.records.append(record)
        _logger.info("llm_call %s", asdict(record))
        # Mirror into the per-turn manifest when a turn is active. Lazy
        # import to avoid a hard cycle (turn_manifest is in the same agent
        # package but conceptually downstream).
        try:
            from briarwood.agent.turn_manifest import record_llm_call_summary

            record_llm_call_summary(
                surface=record.surface,
                provider=record.provider,
                model=record.model,
                status=record.status,
                duration_ms=record.duration_ms,
                attempts=record.attempts,
            )
        except Exception:  # observability must never break a turn
            pass

    def clear(self) -> None:
        self.records.clear()


_LEDGER = LLMCallLedger()
_STRUCTURED_CACHE: dict[str, BaseModel] = {}


def get_llm_ledger() -> LLMCallLedger:
    return _LEDGER


def clear_llm_caches() -> None:
    _STRUCTURED_CACHE.clear()


def structured_cache_key(
    *,
    provider: str | None,
    model: str | None,
    schema: type[BaseModel],
    system: str,
    user: str,
    context_version: str = "v1",
    feature_flags: dict[str, Any] | None = None,
) -> str:
    payload = {
        "provider": provider,
        "model": model,
        "schema": schema.__name__,
        "system_hash": _sha256_text(system),
        "user_hash": _sha256_text(user),
        "context_version": context_version,
        "feature_flags": feature_flags or {},
    }
    return _sha256_text(_normalized_json(payload))


def complete_structured_observed(
    *,
    surface: str,
    call: Callable[[], T | None],
    schema: type[T],
    system: str,
    user: str,
    provider: str | None = None,
    model: str | None = None,
    max_attempts: int = 2,
    cache_enabled: bool | None = None,
    context_version: str = "v1",
    feature_flags: dict[str, Any] | None = None,
) -> T | None:
    """Run one structured-output LLM call with shared retry/cache telemetry.

    ``BudgetExceeded`` is intentionally non-retryable and is re-raised so
    callers keep their existing budget-fallback semantics.
    """

    if cache_enabled is None:
        cache_enabled = os.environ.get("BRIARWOOD_LLM_RESPONSE_CACHE", "").strip() in {
            "1",
            "true",
            "yes",
        }
    cache_key = structured_cache_key(
        provider=provider,
        model=model,
        schema=schema,
        system=system,
        user=user,
        context_version=context_version,
        feature_flags=feature_flags,
    )
    prompt_hash = _sha256_text(_normalized_json({"system": system, "user": user}))
    if cache_enabled and cache_key in _STRUCTURED_CACHE:
        cached = _STRUCTURED_CACHE[cache_key]
        record = LLMCallRecord(
            surface=surface,
            schema_name=schema.__name__,
            provider=provider,
            model=model,
            prompt_hash=prompt_hash,
            response_hash=_sha256_text(cached.model_dump_json()),
            status="cache_hit",
            attempts=0,
            cache_hit=True,
        )
        if _LEDGER.debug_payloads_enabled:
            record.debug_payload = {"system": system, "user": user, "response": cached.model_dump(mode="json")}
        _LEDGER.append(record)
        return cached  # type: ignore[return-value]

    started = time.perf_counter()
    record = LLMCallRecord(
        surface=surface,
        schema_name=schema.__name__,
        provider=provider,
        model=model,
        prompt_hash=prompt_hash,
    )
    if _LEDGER.debug_payloads_enabled:
        record.debug_payload = {"system": system, "user": user}

    for attempt in range(1, max_attempts + 1):
        record.attempts = attempt
        try:
            response = call()
        except BudgetExceeded:
            record.status = "budget_exceeded"
            record.error_type = "BudgetExceeded"
            record.duration_ms = (time.perf_counter() - started) * 1000
            _LEDGER.append(record)
            raise
        except Exception as exc:
            record.status = "exception"
            record.error_type = type(exc).__name__
            if attempt >= max_attempts:
                record.duration_ms = (time.perf_counter() - started) * 1000
                _LEDGER.append(record)
                return None
            continue

        if response is not None:
            record.status = "success"
            record.response_hash = _sha256_text(response.model_dump_json())
            record.duration_ms = (time.perf_counter() - started) * 1000
            if record.debug_payload is not None:
                record.debug_payload["response"] = response.model_dump(mode="json")
            if cache_enabled:
                _STRUCTURED_CACHE[cache_key] = response
            _LEDGER.append(record)
            return response

        record.status = "none"

    record.duration_ms = (time.perf_counter() - started) * 1000
    _LEDGER.append(record)
    return None


def complete_text_observed(
    *,
    surface: str,
    call: Callable[[], str],
    system: str,
    user: str,
    provider: str | None = None,
    model: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Run a free-text LLM call and record metadata in the shared ledger."""

    started = time.perf_counter()
    record = LLMCallRecord(
        surface=surface,
        schema_name=None,
        provider=provider,
        model=model,
        prompt_hash=_sha256_text(_normalized_json({"system": system, "user": user})),
        metadata=metadata or {},
    )
    if _LEDGER.debug_payloads_enabled:
        record.debug_payload = {"system": system, "user": user}
    try:
        response = call()
    except BudgetExceeded:
        record.status = "budget_exceeded"
        record.error_type = "BudgetExceeded"
        record.attempts = 1
        record.duration_ms = (time.perf_counter() - started) * 1000
        _LEDGER.append(record)
        raise
    except Exception as exc:
        record.status = "exception"
        record.error_type = type(exc).__name__
        record.attempts = 1
        record.duration_ms = (time.perf_counter() - started) * 1000
        _LEDGER.append(record)
        raise
    record.status = "success"
    record.attempts = 1
    record.response_hash = _sha256_text(response)
    record.duration_ms = (time.perf_counter() - started) * 1000
    if record.debug_payload is not None:
        record.debug_payload["response"] = response
    _LEDGER.append(record)
    return response
