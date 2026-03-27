from __future__ import annotations

from html import escape
from pathlib import Path

from briarwood.reports.schemas import ScenarioCase, ScenarioChartSection, TearSheet


def render_tear_sheet_html(tear_sheet: TearSheet) -> str:
    template = _load_text("templates/tear_sheet.html")
    css = _load_text("assets/tear_sheet.css")
    chart = tear_sheet.scenario_chart

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
        "$scenario_chart": _render_scenario_chart(chart),
        "$distribution_summary": escape(tear_sheet.scenario_chart.caption),
        "$durability_title": escape(tear_sheet.market_durability.title),
        "$durability_summary": escape(tear_sheet.market_durability.summary),
        "$durability_assessment": escape(tear_sheet.market_durability.assessment.summary),
        "$durability_takeaway": escape(tear_sheet.market_durability.buyer_takeaway),
        "$durability_supporting_points": _render_list_items(tear_sheet.market_durability.supporting_points),
        "$durability_caveats": _render_list_items(tear_sheet.market_durability.caveats),
        "$durability_confidence_notes": _render_case_list_items(tear_sheet.market_durability.confidence_notes),
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


def _render_list_items(items: list[str]) -> str:
    return "\n".join(f"          <li>{escape(item)}</li>" for item in items)


def _render_scenario_chart(chart: ScenarioChartSection) -> str:
    if chart.plot_html:
        return chart.plot_html

    all_values = [chart.current_ask, chart.market_reference_value, chart.forward_base_value]
    all_values.extend(band.value for band in chart.fan_bands)
    min_value = min(all_values)
    max_value = max(all_values)
    padding = max((max_value - min_value) * 0.15, 1.0)
    chart_min = min_value - padding
    chart_max = max_value + padding

    def y_for(value: float) -> float:
        if chart_max == chart_min:
            return 110.0
        normalized = (value - chart_min) / (chart_max - chart_min)
        return 220.0 - (normalized * 180.0)

    x_left = 90.0
    x_mid = 260.0
    x_right = 520.0

    ask_y = y_for(chart.current_ask)
    marker_y = y_for(chart.market_reference_value)
    base_y = y_for(chart.forward_base_value)
    band_map = {band.label: band.value for band in chart.fan_bands}
    bull_y = y_for(band_map.get("Bull", chart.forward_base_value))
    bear_y = y_for(band_map.get("Bear", chart.forward_base_value))

    return (
        '<div class="scenario-chart-wrap">'
        '<svg class="scenario-chart" viewBox="0 0 640 280" role="img" '
        f'aria-label="{escape(chart.chart_title)}">'
        '<line class="scenario-grid" x1="90" y1="32" x2="90" y2="235"></line>'
        '<line class="scenario-grid" x1="520" y1="32" x2="520" y2="235"></line>'
        f'<line class="scenario-line market-line" x1="{x_left}" y1="{marker_y:.1f}" x2="{x_right}" y2="{base_y:.1f}"></line>'
        f'<line class="scenario-line ask-line" x1="{x_left}" y1="{ask_y:.1f}" x2="{x_mid}" y2="{ask_y:.1f}"></line>'
        f'<line class="scenario-line base-line" x1="{x_mid}" y1="{base_y:.1f}" x2="{x_right}" y2="{base_y:.1f}"></line>'
        f'<line class="scenario-line bull-line" x1="{x_mid}" y1="{base_y:.1f}" x2="{x_right}" y2="{bull_y:.1f}"></line>'
        f'<line class="scenario-line bear-line" x1="{x_mid}" y1="{base_y:.1f}" x2="{x_right}" y2="{bear_y:.1f}"></line>'
        f'<circle class="scenario-dot market-dot" cx="{x_left}" cy="{marker_y:.1f}" r="6"></circle>'
        f'<circle class="scenario-dot ask-dot" cx="{x_left}" cy="{ask_y:.1f}" r="6"></circle>'
        f'<circle class="scenario-dot base-dot" cx="{x_right}" cy="{base_y:.1f}" r="6"></circle>'
        f'<circle class="scenario-dot bull-dot" cx="{x_right}" cy="{bull_y:.1f}" r="6"></circle>'
        f'<circle class="scenario-dot bear-dot" cx="{x_right}" cy="{bear_y:.1f}" r="6"></circle>'
        f'<text class="chart-label" x="{x_left}" y="252" text-anchor="middle">Today</text>'
        f'<text class="chart-label" x="{x_right}" y="252" text-anchor="middle">{escape(chart.forward_year_label)}</text>'
        f'<text class="chart-annotation" x="{x_left - 12}" y="{marker_y - 12:.1f}" text-anchor="end">{escape(chart.market_reference_label)} {_currency(chart.market_reference_value)}</text>'
        f'<text class="chart-annotation" x="{x_left - 12}" y="{ask_y + 22:.1f}" text-anchor="end">Ask {_currency(chart.current_ask)}</text>'
        f'<text class="chart-annotation base-text" x="{x_right + 14}" y="{base_y + 4:.1f}">Base {_currency(chart.forward_base_value)}</text>'
        f'<text class="chart-annotation bull-text" x="{x_right + 14}" y="{bull_y + 4:.1f}">Bull {_currency(band_map.get("Bull", chart.forward_base_value))}</text>'
        f'<text class="chart-annotation bear-text" x="{x_right + 14}" y="{bear_y + 4:.1f}">Bear {_currency(band_map.get("Bear", chart.forward_base_value))}</text>'
        "</svg>"
        "</div>"
    )


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


def _render_case_list_items(items: list[str]) -> str:
    return "\n".join(f"<li>{escape(item)}</li>" for item in items)
