from __future__ import annotations

from html import escape
from pathlib import Path

from briarwood.reports.schemas import ScenarioCase, ScenarioPoint, TearSheet


def render_tear_sheet_html(tear_sheet: TearSheet) -> str:
    template = _load_text("templates/tear_sheet.html")
    css = _load_text("assets/tear_sheet.css")
    chart = tear_sheet.scenario_chart
    max_value = max((point.value for point in chart.points), default=1.0)

    replacements = {
        "__CSS__": css,
        "$property_name": escape(tear_sheet.header.property_name),
        "$subtitle": escape(tear_sheet.header.subtitle),
        "$investment_stance": escape(tear_sheet.header.investment_stance),
        "$ask_price": _currency(tear_sheet.conclusion.ask_price),
        "$base_value": _currency(tear_sheet.conclusion.base_value),
        "$bull_value": _currency(tear_sheet.conclusion.bull_value),
        "$bear_value": _currency(tear_sheet.conclusion.bear_value),
        "$valuation_method_summary": escape(tear_sheet.conclusion.explanation),
        "$thesis_title": escape(tear_sheet.thesis.title),
        "$thesis_summary": escape(tear_sheet.thesis.assessment.summary),
        "$thesis_bullets": _render_list_items(tear_sheet.thesis.bullets),
        "$chart_title": escape(tear_sheet.scenario_chart.chart_title),
        "$scenario_rows": _render_chart_rows(chart.points, max_value),
        "$distribution_summary": escape(tear_sheet.scenario_chart.caption),
        "$case_columns": _render_case_columns(tear_sheet.bull_base_bear),
    }
    html = template
    for key, value in replacements.items():
        html = html.replace(key, str(value))
    return html


def write_tear_sheet_html(tear_sheet: TearSheet, output_path: str | Path) -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_tear_sheet_html(tear_sheet))
    return destination


def _load_text(relative_path: str) -> str:
    base_path = Path(__file__).parent
    return (base_path / relative_path).read_text()


def _currency(value: float) -> str:
    return f"${value:,.0f}"


def _bar_width(value: float, max_value: float) -> str:
    return f"{(value / max_value) * 100:.1f}"


def _render_list_items(items: list[str]) -> str:
    return "\n".join(f"          <li>{escape(item)}</li>" for item in items)


def _render_chart_rows(points: list[ScenarioPoint], max_value: float) -> str:
    class_map = {
        "Ask": "ask",
        "Bear": "bear",
        "Base": "base",
        "Bull": "bull",
    }
    rows: list[str] = []
    for point in points:
        css_class = class_map.get(point.label, "base")
        rows.append(
            '<div class="chart-row">'
            f"<span>{escape(point.label)}</span>"
            f'<div class="bar-track"><div class="bar {css_class}" style="width: {_bar_width(point.value, max_value)}%;"></div></div>'
            f"<strong>{_currency(point.value)}</strong>"
            "</div>"
        )
    return "\n".join(rows)


def _render_case_columns(section: object) -> str:
    cases = [
        section.bull_case,
        section.base_case,
        section.bear_case,
    ]
    return "\n".join(_render_case_card(case) for case in cases)


def _render_case_card(case: ScenarioCase) -> str:
    assumptions = _render_case_list(case.assumptions)
    drivers = _render_case_list(case.key_drivers)
    risks = _render_case_list(case.risk_factors)
    return (
        '<section class="card case-card">'
        f"<div class=\"section-label\">{escape(case.name)}</div>"
        f"<h3>{escape(case.name)}</h3>"
        f"<div class=\"case-value\">{_currency(case.scenario_value)}</div>"
        f"<p class=\"body-copy\">{escape(case.assessment.summary)}</p>"
        '<div class="case-block-label">Assumptions</div>'
        f"{assumptions}"
        '<div class="case-block-label">Key Drivers</div>'
        f"{drivers}"
        '<div class="case-block-label">Risk Factors</div>'
        f"{risks}"
        "</section>"
    )


def _render_case_list(items: list[str]) -> str:
    rendered_items = "".join(f"<li>{escape(item)}</li>" for item in items)
    return f'<ul class="case-list">{rendered_items}</ul>'
