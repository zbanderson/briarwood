"""Unit tests for the chart registry."""

from __future__ import annotations

from briarwood.representation import charts
from briarwood.representation.charts import ChartSpec


def test_registry_has_all_registered_charts() -> None:
    ids = {spec.id for spec in charts.all_specs()}
    assert ids == {
        "scenario_fan",
        "value_opportunity",
        "cma_positioning",
        "risk_bar",
        "rent_burn",
        "rent_ramp",
        "hidden_upside_band",
        "horizontal_bar_with_ranges",
        "market_trend",  # Phase 3 Cycle B (2026-04-26)
    }


def test_render_market_trend_produces_event_payload() -> None:
    """Cycle B: market_trend chart projects the ZHVI series + change percentages."""
    inputs = {
        "geography_name": "Belmar",
        "geography_type": "town",
        "current_value": 850_000,
        "one_year_change_pct": 0.04,
        "three_year_change_pct": 0.12,
        "history_points": [
            {"date": "2020-01-31", "value": 600_000},
            {"date": "2021-01-31", "value": 680_000},
            {"date": "2022-01-31", "value": 760_000},
            {"date": "2023-01-31", "value": 820_000},
            {"date": "2024-01-31", "value": 850_000},
        ],
    }
    event = charts.render("market_trend", inputs)
    assert event is not None
    assert event["kind"] == "market_trend"
    spec = event["spec"]
    assert spec["geography_name"] == "Belmar"
    assert spec["geography_type"] == "town"
    assert spec["current_value"] == 850_000
    assert len(spec["points"]) == 5
    # Cycle A presentation metadata also lands.
    assert event["value_format"] == "currency"
    assert event["x_axis_label"] == "Year"
    assert event["y_axis_label"] == "Home value index"
    legend_labels = {item["label"] for item in event["legend"]}
    assert "Belmar (town)" in legend_labels


def test_render_market_trend_returns_none_without_points() -> None:
    """Cycle B: market_trend without history points must not produce an event."""
    assert charts.render("market_trend", {"geography_name": "Belmar"}) is None
    assert charts.render("market_trend", {"history_points": []}) is None


def test_horizontal_bar_with_ranges_is_a_marker_spec() -> None:
    # Wedge chart: registry entry exists for discoverability + id validation,
    # but rendering happens in the claim-object representation layer, so the
    # registry renderer must return None like `hidden_upside_band`.
    spec = charts.get_spec("horizontal_bar_with_ranges")
    assert spec is not None
    assert spec.claim_types == ["scenario_comparison"]
    assert charts.render("horizontal_bar_with_ranges", {"scenarios": []}) is None


def test_registry_exposes_broader_representation_claim_intents() -> None:
    claim_map = {
        claim_type
        for spec in charts.all_specs()
        for claim_type in spec.claim_types
    }
    assert "affordability_carry_cost" in claim_map
    assert "rent_vs_own" in claim_map
    assert "renovation_impact" in claim_map
    assert "sensitivity" in claim_map


def test_every_spec_declares_claim_types_and_required_inputs() -> None:
    marker_specs = {"hidden_upside_band", "horizontal_bar_with_ranges"}
    for spec in charts.all_specs():
        assert spec.claim_types, f"{spec.id} must declare at least one claim_type"
        if spec.id in marker_specs:
            continue
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
    # Cycle A: presentation metadata is always carried alongside the spec.
    assert event["subtitle"]
    assert event["x_axis_label"] == "Years from today"
    assert event["y_axis_label"] == "Home value"
    assert event["value_format"] == "currency"
    legend_labels = [item["label"] for item in event["legend"]]
    assert "Bull case" in legend_labels
    assert "Stress floor" in legend_labels  # included when stress_case_value is present


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
    assert event["subtitle"]
    assert event["value_format"] == "currency"
    assert {item["label"] for item in event["legend"]} == {"Fair value", "Ask"}


def test_render_risk_bar_carries_presentation_metadata() -> None:
    """Cycle A: risk_bar should declare percent formatting and a two-tone legend."""
    event = charts.render(
        "risk_bar",
        {
            "risk_flags": ["flood_zone"],
            "trust_flags": ["incomplete_carry_inputs"],
            "total_penalty": 0.2,
            "ask_price": 900_000,
        },
    )
    assert event is not None
    assert event["value_format"] == "percent"
    assert event["x_axis_label"] == "Penalty share"
    legend_labels = {item["label"] for item in event["legend"]}
    assert legend_labels == {"Risk flag", "Trust gap"}


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
