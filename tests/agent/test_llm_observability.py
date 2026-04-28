from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from briarwood.agent.llm_observability import (
    LLMCallRecord,
    clear_llm_caches,
    complete_structured_observed,
    complete_text_observed,
    get_llm_ledger,
)
from briarwood.agent.turn_manifest import end_turn, start_turn
from briarwood.cost_guard import BudgetExceeded


class TinySchema(BaseModel):
    value: str


def setup_function() -> None:
    get_llm_ledger().clear()
    clear_llm_caches()


def test_structured_ledger_records_retry_success() -> None:
    calls = {"n": 0}

    def call() -> TinySchema | None:
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return TinySchema(value="ok")

    result = complete_structured_observed(
        surface="test.structured",
        schema=TinySchema,
        system="sys",
        user="user",
        call=call,
    )

    assert result == TinySchema(value="ok")
    assert calls["n"] == 2
    record = get_llm_ledger().records[-1]
    assert record.status == "success"
    assert record.attempts == 2
    assert record.schema_name == "TinySchema"


def test_structured_cache_hit_is_recorded() -> None:
    calls = {"n": 0}

    def call() -> TinySchema:
        calls["n"] += 1
        return TinySchema(value="cached")

    first = complete_structured_observed(
        surface="test.cache",
        schema=TinySchema,
        system="sys",
        user="user",
        call=call,
        cache_enabled=True,
    )
    second = complete_structured_observed(
        surface="test.cache",
        schema=TinySchema,
        system="sys",
        user="user",
        call=call,
        cache_enabled=True,
    )

    assert first == second
    assert calls["n"] == 1
    assert get_llm_ledger().records[-1].status == "cache_hit"


def test_budget_errors_are_not_retried() -> None:
    calls = {"n": 0}

    def call() -> TinySchema:
        calls["n"] += 1
        raise BudgetExceeded("stop")

    with pytest.raises(BudgetExceeded):
        complete_structured_observed(
            surface="test.budget",
            schema=TinySchema,
            system="sys",
            user="user",
            call=call,
        )

    assert calls["n"] == 1
    assert get_llm_ledger().records[-1].status == "budget_exceeded"


def test_text_ledger_records_response_hash() -> None:
    text = complete_text_observed(
        surface="test.text",
        system="sys",
        user="user",
        call=lambda: "hello",
    )

    assert text == "hello"
    record = get_llm_ledger().records[-1]
    assert record.status == "success"
    assert record.response_hash


def _record(**overrides) -> LLMCallRecord:
    base = dict(
        surface="test.surface",
        schema_name="TinySchema",
        provider="openai",
        model="gpt-4o-mini",
        prompt_hash="deadbeef",
        response_hash="cafebabe",
        status="success",
        attempts=1,
        duration_ms=42.5,
    )
    base.update(overrides)
    return LLMCallRecord(**base)


def test_append_writes_jsonl_line_when_path_configured(tmp_path, monkeypatch) -> None:
    target = tmp_path / "calls.jsonl"
    monkeypatch.setenv("BRIARWOOD_LLM_JSONL_PATH", str(target))
    monkeypatch.delenv("BRIARWOOD_LLM_DEBUG_PAYLOADS", raising=False)

    get_llm_ledger().append(_record())

    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["surface"] == "test.surface"
    assert payload["status"] == "success"
    assert payload["model"] == "gpt-4o-mini"
    assert payload["duration_ms"] == 42.5
    # recorded_at must be stamped at write time even though the dataclass
    # carries no absolute timestamp.
    assert "recorded_at" in payload
    assert payload["recorded_at"].endswith("+00:00")


def test_append_omits_debug_payload_when_flag_unset(tmp_path, monkeypatch) -> None:
    target = tmp_path / "calls.jsonl"
    monkeypatch.setenv("BRIARWOOD_LLM_JSONL_PATH", str(target))
    monkeypatch.delenv("BRIARWOOD_LLM_DEBUG_PAYLOADS", raising=False)

    get_llm_ledger().append(_record(debug_payload={"system": "S", "user": "U"}))

    payload = json.loads(target.read_text(encoding="utf-8").splitlines()[0])
    assert "debug_payload" not in payload


def test_append_includes_debug_payload_when_flag_set(tmp_path, monkeypatch) -> None:
    target = tmp_path / "calls.jsonl"
    monkeypatch.setenv("BRIARWOOD_LLM_JSONL_PATH", str(target))
    monkeypatch.setenv("BRIARWOOD_LLM_DEBUG_PAYLOADS", "1")

    get_llm_ledger().append(_record(debug_payload={"system": "S", "user": "U"}))

    payload = json.loads(target.read_text(encoding="utf-8").splitlines()[0])
    assert payload["debug_payload"] == {"system": "S", "user": "U"}


def test_append_swallows_write_error(tmp_path, monkeypatch, capfd) -> None:
    # Point the env var at a path that cannot be written: the parent is a
    # *file*, so mkdir(parents=True) raises FileExistsError / NotADirectoryError.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    bad_path = blocker / "calls.jsonl"
    monkeypatch.setenv("BRIARWOOD_LLM_JSONL_PATH", str(bad_path))
    monkeypatch.delenv("BRIARWOOD_LLM_DEBUG_PAYLOADS", raising=False)

    # Must not raise, even though the underlying write fails.
    get_llm_ledger().append(_record())

    captured = capfd.readouterr()
    assert "[llm_calls.jsonl]" in captured.out


def test_append_preserves_existing_manifest_mirror(tmp_path, monkeypatch) -> None:
    target = tmp_path / "calls.jsonl"
    monkeypatch.setenv("BRIARWOOD_LLM_JSONL_PATH", str(target))
    monkeypatch.delenv("BRIARWOOD_LLM_DEBUG_PAYLOADS", raising=False)

    start_turn(user_text="probe", conversation_id=None)
    try:
        get_llm_ledger().append(_record(surface="agent_router.classify"))
    finally:
        finalized = end_turn()

    assert finalized is not None
    assert any(c.surface == "agent_router.classify" for c in finalized.llm_calls)
    # And the JSONL mirror still happened.
    assert target.exists() and target.read_text(encoding="utf-8").strip()
