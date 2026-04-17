"""Tests for the briarwood.charts package (wrapper over rendering builders)."""

from __future__ import annotations

import pytest

from briarwood.charts import CHART_KINDS, ChartArtifact, render, render_from_route
from briarwood.pipeline.session import PipelineSession


def test_exposes_canonical_chart_kinds() -> None:
    assert CHART_KINDS == ("line_area", "bar_compare", "geo_map", "radar_score")


def test_render_bar_compare_returns_html_artifact() -> None:
    artifact = render(
        {
            "kind": "bar_compare",
            "items": {"income_model": 0.72, "risk_model": 0.65, "location_model": 0.8},
            "title": "Per-model confidence",
        }
    )

    assert isinstance(artifact, ChartArtifact)
    assert artifact.kind == "bar_compare"
    assert artifact.html.lstrip().lower().startswith("<!doctype html") or artifact.html.lstrip().startswith("<html")
    assert artifact.source_data["kind"] == "bar_compare"


def test_render_radar_score_populates_factors() -> None:
    artifact = render(
        {
            "kind": "radar_score",
            "factors": {"Income": 72, "Risk": 65, "Location": 80},
        }
    )
    assert isinstance(artifact, ChartArtifact)
    assert artifact.html


def test_render_line_area_requires_series_or_projection() -> None:
    artifact = render(
        {
            "kind": "line_area",
            "ask_price": 500_000,
            "bull_case_value": 620_000,
            "bear_case_value": 460_000,
        }
    )
    assert artifact.html


def test_render_geo_map_handles_empty_points() -> None:
    artifact = render({"kind": "geo_map", "points": []})
    assert artifact.kind == "geo_map"
    assert artifact.html


def test_render_rejects_unsupported_kind() -> None:
    from briarwood.agent.rendering import ChartUnavailable

    with pytest.raises(ChartUnavailable):
        render({"kind": "verdict_gauge"})


def test_render_from_route_uses_session_confidences_for_bar_compare() -> None:
    session = PipelineSession(raw_intent="q")
    session.record_model_output("income_model", {"cap_rate": 0.05}, confidence=0.72)
    session.record_model_output("risk_model", {"score": 80}, confidence=0.65)

    artifact = render_from_route(
        {"kind": "bar_compare", "source": "specialist_models", "purpose": "Confidences"},
        session,
    )

    assert artifact.source_data["items"] == {"income_model": 0.72, "risk_model": 0.65}
    assert artifact.kind == "bar_compare"


def test_render_from_route_builds_radar_factors() -> None:
    session = PipelineSession(raw_intent="q")
    session.record_model_output("income_model", {}, confidence=0.7)
    session.record_model_output("risk_model", {}, confidence=0.6)
    session.record_model_output("location_model", {}, confidence=0.8)

    artifact = render_from_route(
        {"kind": "radar_score", "source": "all_models", "purpose": "fit"},
        session,
    )

    factors = artifact.source_data["factors"]
    assert set(factors) == {"income_model", "risk_model", "location_model"}
    # Values get scaled to 0–100.
    assert all(0 <= v <= 100 for v in factors.values())
