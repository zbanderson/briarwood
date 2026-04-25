from __future__ import annotations

import pytest
from pydantic import BaseModel

from briarwood.agent.llm_observability import (
    clear_llm_caches,
    complete_structured_observed,
    complete_text_observed,
    get_llm_ledger,
)
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
