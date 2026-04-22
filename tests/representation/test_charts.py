"""Unit tests for the chart registry."""

from __future__ import annotations

from briarwood.representation import charts
from briarwood.representation.charts import ChartSpec


def test_registry_has_all_six_native_charts() -> None:
    ids = {spec.id for spec in charts.all_specs()}
    assert ids == {
        "scenario_fan",
        "value_opportunity",
        "cma_positioning",
        "risk_bar",
        "rent_burn",
        "rent_ramp",
    }


def test_every_spec_declares_claim_types_and_required_inputs() -> None:
    for spec in charts.all_specs():
        assert spec.claim_types, f"{spec.id} must declare at least one claim_type"
        assert spec.required_inputs, f"{spec.id} must declare required_inputs"


def test_get_spec_returns_none_for_unknown_id() -> None:
    assert charts.get_spec("no_such_chart") is None


def test_render_unknown_chart_returns_none() -> None:
    assert charts.render("not_in_registry", {"ask_price": 1}) is None


def test_render_scenario_fan_produces_event_payload() -> None:
    inputs = {
        "ask_price": 950_000,
        "basis_label": "all-in basis",
        "bull_case_value": 1_200_000,
        "base_case_value": 1_050_000,
        "bear_case_value": 900_000,
        "stress_case_value": 820_000,
    }
    event = charts.render("scenario_fan", inputs)
    assert event is not None
    assert event["type"] == "chart"
    assert event["kind"] == "scenario_fan"
    spec = event["spec"]
    assert spec["bull_case_value"] == 1_200_000
    assert spec["bear_case_value"] == 900_000


def test_render_scenario_fan_rejects_empty_inputs() -> None:
    # Matches the underlying _native_scenario_chart contract.
    assert charts.render("scenario_fan", {}) is None


def test_render_value_opportunity_produces_event_payload() -> None:
    inputs = {
        "ask_price": 950_000,
        "fair_value_base": 870_000,
        "premium_discount_pct": 0.092,
        "key_value_drivers": ["Strong town demand", "Coastal proximity"],
    }
    event = charts.render("value_opportunity", inputs)
    assert event is not None
    assert event["kind"] == "value_opportunity"
    assert event["spec"]["value_drivers"][:2] == [
        "Strong town demand",
        "Coastal proximity",
    ]


def test_render_risk_bar_uses_trust_fallback() -> None:
    inputs = {
        "risk_flags": ["flood_zone"],
        "trust_flags": ["incomplete_carry_inputs"],
        "total_penalty": 0.2,
        "ask_price": 900_000,
    }
    event = charts.render("risk_bar", inputs)
    assert event is not None
    assert event["kind"] == "risk_bar"
    items = event["spec"]["items"]
    assert any(i["tone"] == "risk" for i in items)
    assert any(i["tone"] == "trust" for i in items)


def test_render_renderer_exception_returns_none(monkeypatch) -> None:
    """Renderers that blow up must degrade to None, not crash the stream."""

    def boom(_: dict) -> dict | None:
        raise RuntimeError("kaboom")

    charts.register(
        ChartSpec(
            id="_bad_chart",
            name="Bad",
            description="Bad",
            required_inputs=["x"],
            claim_types=["price_position"],
        ),
        boom,
    )
    try:
        assert charts.render("_bad_chart", {"x": 1}) is None
    finally:
        charts._REGISTRY.pop("_bad_chart", None)
