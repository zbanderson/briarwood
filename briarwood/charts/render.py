"""Render a Layer 05 chart kind to a ``ChartArtifact``.

Reuses the figure builders in ``briarwood.agent.rendering._build_figure``.
"""

from __future__ import annotations

from typing import Any

from briarwood.agent.rendering import ChartUnavailable, _build_figure
from briarwood.charts.artifact import ChartArtifact
from briarwood.pipeline.session import PipelineSession


CHART_KINDS: tuple[str, ...] = ("line_area", "bar_compare", "geo_map", "radar_score")


def render(spec: dict[str, Any]) -> ChartArtifact:
    """Render a chart spec to an HTML string (and PNG bytes if available)."""

    if not isinstance(spec, dict):
        raise ChartUnavailable("spec must be a dict with a 'kind' key.")
    kind = spec.get("kind")
    if kind not in CHART_KINDS:
        raise ChartUnavailable(
            f"Unsupported chart kind '{kind}'. Supported: {list(CHART_KINDS)}"
        )

    fig = _build_figure(kind, spec)
    html = fig.to_html(include_plotlyjs="cdn", full_html=True)
    png_bytes: bytes | None
    try:
        image = fig.to_image(format="png")
        png_bytes = image if isinstance(image, bytes) else None
    except Exception:
        png_bytes = None

    return ChartArtifact(
        kind=kind,
        html=html,
        png_bytes=png_bytes,
        source_data=dict(spec),
    )


def render_from_route(
    route: dict[str, Any],
    session: PipelineSession,
) -> ChartArtifact:
    """Build a spec from a unified chart route + session state, then render."""

    if not isinstance(route, dict) or "kind" not in route:
        raise ChartUnavailable("route must be a dict with a 'kind' key.")
    spec = _spec_from_route(route, session)
    return render(spec)


def _spec_from_route(
    route: dict[str, Any],
    session: PipelineSession,
) -> dict[str, Any]:
    kind = route["kind"]
    source = route.get("source")
    purpose = route.get("purpose")

    spec: dict[str, Any] = {"kind": kind, "title": purpose}

    if kind == "bar_compare":
        items = {
            name: float(result.confidence)
            for name, result in session.model_outputs.items()
            if isinstance(result.confidence, (int, float))
        }
        if items:
            spec["items"] = items
    elif kind == "radar_score":
        factors = {
            name: float(result.confidence) * 100
            for name, result in session.model_outputs.items()
            if isinstance(result.confidence, (int, float))
        }
        if factors:
            spec["factors"] = factors
    elif kind == "line_area":
        # Prefer the named source model's data; else the synthesis payload.
        if isinstance(source, str) and source in session.model_outputs:
            spec.update(_coerce_to_series_spec(session.model_outputs[source].data))
        # scenario_model carries bull/base/bear but not ask_price; backfill
        # from session.property_data when available so the fan chart renders.
        if "ask_price" not in spec:
            ask = session.property_data.get("purchase_price")
            if isinstance(ask, (int, float)):
                spec["ask_price"] = ask
    elif kind == "geo_map":
        if isinstance(source, str) and source in session.model_outputs:
            data = session.model_outputs[source].data
            points = data.get("points")
            if isinstance(points, list):
                spec["points"] = points

    # Let the caller-specific payload from the source model override defaults.
    if isinstance(source, str) and source in session.model_outputs:
        for key, value in session.model_outputs[source].data.items():
            spec.setdefault(key, value)

    return spec


def _coerce_to_series_spec(data: dict[str, Any]) -> dict[str, Any]:
    """Project a model data dict onto the keys _line_area expects."""

    projected: dict[str, Any] = {}
    for key in ("series", "ask_price", "bull_case_value", "bear_case_value"):
        if key in data:
            projected[key] = data[key]
    return projected


__all__ = ["CHART_KINDS", "render", "render_from_route"]
