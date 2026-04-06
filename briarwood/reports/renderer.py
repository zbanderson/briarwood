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
        "$verdict": escape(tear_sheet.conclusion.verdict),
        "$verdict_key_line": escape(tear_sheet.conclusion.key_line),
        "$ask_price": _currency(tear_sheet.conclusion.ask_price),
        "$briarwood_current_value": _currency(tear_sheet.conclusion.briarwood_current_value),
        "$pricing_gap": _percent_text(tear_sheet.conclusion.premium_discount_to_ask),
        "$cash_flow_text": escape(tear_sheet.conclusion.cash_flow_text),
        "$top_risk": escape(tear_sheet.conclusion.top_risk),
        "$scenario_range": (
            f"{_currency(tear_sheet.conclusion.bear_value)} to "
            f"{_currency(tear_sheet.conclusion.bull_value)}"
        ),
        "$bcv_range": (
            f"{_currency(tear_sheet.conclusion.value_range_low)} - "
            f"{_currency(tear_sheet.conclusion.value_range_high)}"
        ),
        "$pricing_view": escape(tear_sheet.conclusion.pricing_view.title()),
        "$bull_value": _currency(tear_sheet.conclusion.bull_value),
        "$bear_value": _currency(tear_sheet.conclusion.bear_value),
        "$valuation_method_summary": escape(tear_sheet.conclusion.explanation),
        "$why_it_matters": _render_list_items(tear_sheet.conclusion.why_it_matters),
        "$decision_fit": _render_list_items(tear_sheet.conclusion.decision_fit),
        "$what_changes_call": _render_list_items(tear_sheet.conclusion.what_changes_call),
        "$thesis_title": escape(tear_sheet.thesis.title),
        "$thesis_deal_type": escape(tear_sheet.thesis.deal_type),
        "$thesis_must_go_right": _render_list_items(tear_sheet.thesis.must_go_right),
        "$thesis_what_breaks": _render_list_items(tear_sheet.thesis.what_breaks),
        "$thesis_so_what": _render_list_items(tear_sheet.thesis.so_what),
        "$chart_title": escape(tear_sheet.scenario_chart.chart_title),
        "$secondary_chart_title": escape(tear_sheet.scenario_chart.secondary_chart_title),
        "$scenario_chart": _render_scenario_chart(chart),
        "$scenario_zoom_chart": _render_secondary_scenario_chart(chart),
        "$distribution_summary": escape(tear_sheet.scenario_chart.caption),
        "$durability_title": escape(tear_sheet.market_durability.title),
        "$durability_assessment": escape(tear_sheet.market_durability.assessment.summary),
        "$durability_supporting_points": _render_list_items(tear_sheet.market_durability.supporting_points),
        "$durability_caveats": _render_list_items(tear_sheet.market_durability.caveats),
        "$durability_confidence_line": escape(tear_sheet.market_durability.confidence_line),
        "$durability_confidence_notes": _render_case_list_items(tear_sheet.market_durability.confidence_notes),
        "$carry_title": escape(tear_sheet.carry_support.title),
        "$carry_market_absorption_label": escape(tear_sheet.carry_support.market_absorption_label),
        "$carry_market_absorption_summary": escape(tear_sheet.carry_support.market_absorption_summary),
        "$carry_market_absorption_confidence": _confidence(tear_sheet.carry_support.market_absorption_confidence),
        "$carry_rental_viability_label": escape(tear_sheet.carry_support.rental_viability_label),
        "$carry_rental_viability_summary": escape(tear_sheet.carry_support.rental_viability_summary),
        "$carry_rental_viability_confidence": _confidence(tear_sheet.carry_support.rental_viability_confidence),
        "$carry_rental_ease_score": escape(tear_sheet.carry_support.rental_ease_score_text),
        "$carry_ratio": escape(tear_sheet.carry_support.income_support_ratio_text),
        "$carry_days_to_rent": escape(tear_sheet.carry_support.estimated_days_to_rent_text),
        "$carry_days_to_rent_context": escape(tear_sheet.carry_support.estimated_days_to_rent_context),
        "$carry_cash_flow": escape(tear_sheet.carry_support.estimated_cash_flow_text),
        "$carry_assessment": escape(tear_sheet.carry_support.assessment.summary),
        "$carry_market_warnings": _render_case_list_items(tear_sheet.carry_support.market_absorption_warnings),
        "$carry_viability_warnings": _render_case_list_items(tear_sheet.carry_support.rental_viability_warnings),
        "$carry_assumptions": _render_case_list_items(tear_sheet.carry_support.assumptions),
        "$carry_unsupported_claims": _render_case_list_items(tear_sheet.carry_support.unsupported_claims),
        "$comp_title": escape(tear_sheet.comparable_sales.title),
        "$comp_summary": escape(tear_sheet.comparable_sales.summary),
        "$comp_value": escape(tear_sheet.comparable_sales.comparable_value_text),
        "$comp_confidence": escape(tear_sheet.comparable_sales.confidence_text),
        "$comp_count": escape(tear_sheet.comparable_sales.comp_count_text),
        "$comp_freshest_sale": escape(tear_sheet.comparable_sales.freshest_sale_text),
        "$comp_median_sale_age": escape(tear_sheet.comparable_sales.median_sale_age_text),
        "$comp_screening_summary": escape(tear_sheet.comparable_sales.screening_summary),
        "$comp_curation_summary": escape(tear_sheet.comparable_sales.curation_summary),
        "$comp_verification_summary": escape(tear_sheet.comparable_sales.verification_summary),
        "$comp_assessment": escape(tear_sheet.comparable_sales.assessment.summary),
        "$comp_methodology_notes": _render_case_list_items(tear_sheet.comparable_sales.methodology_notes),
        "$comp_warnings": _render_case_list_items(tear_sheet.comparable_sales.warnings),
        "$comp_cards": _render_comp_cards(tear_sheet.comparable_sales.comps),
        "$case_columns": _render_case_columns(tear_sheet.bull_base_bear),
        "$evidence_title": escape(tear_sheet.evidence_strip.title),
        "$evidence_mode": escape(tear_sheet.evidence_strip.evidence_mode_text),
        "$evidence_overall_confidence": escape(tear_sheet.evidence_strip.overall_report_confidence_text),
        "$evidence_rent_component_confidence": escape(tear_sheet.evidence_strip.rent_component_confidence_text),
        "$evidence_capex_component_confidence": escape(tear_sheet.evidence_strip.capex_component_confidence_text),
        "$evidence_market_component_confidence": escape(tear_sheet.evidence_strip.market_component_confidence_text),
        "$evidence_liquidity_component_confidence": escape(tear_sheet.evidence_strip.liquidity_component_confidence_text),
        "$evidence_value_confidence": escape(tear_sheet.evidence_strip.value_confidence_text),
        "$evidence_location_confidence": escape(tear_sheet.evidence_strip.location_confidence_text),
        "$evidence_rental_confidence": escape(tear_sheet.evidence_strip.rental_confidence_text),
        "$evidence_scenario_confidence": escape(tear_sheet.evidence_strip.scenario_confidence_text),
        "$evidence_confidence_reasons": _render_case_list_items(tear_sheet.evidence_strip.confidence_reason_lines),
        "$evidence_coverage": _render_case_list_items(tear_sheet.evidence_strip.source_coverage_highlights),
        "$evidence_missing": _render_case_list_items(tear_sheet.evidence_strip.major_missing_inputs),
        "$evidence_estimated": _render_case_list_items(tear_sheet.evidence_strip.estimated_inputs),
        "$evidence_modeled_fields": _render_case_list_items(tear_sheet.evidence_strip.modeled_fields),
        "$evidence_non_modeled_fields": _render_case_list_items(tear_sheet.evidence_strip.non_modeled_fields),
        "$evidence_strongest": _render_case_list_items(tear_sheet.evidence_strip.strongest_evidence),
        "$evidence_weaker": _render_case_list_items(tear_sheet.evidence_strip.weaker_evidence),
        "$evidence_heuristic": _render_case_list_items(tear_sheet.evidence_strip.heuristic_flags),
        "$signal_metrics": _render_signal_metrics(tear_sheet.signal_metrics),
    }
    html = template
    for key in sorted(replacements, key=len, reverse=True):
        value = replacements[key]
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


def _confidence(value: float) -> str:
    return f"{round(value * 100):d}%"


def _percent_text(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1%}"


def _render_list_items(items: list[str]) -> str:
    return "\n".join(f"          <li>{escape(item)}</li>" for item in items)


def _render_scenario_chart(chart: ScenarioChartSection) -> str:
    if chart.plot_html:
        return chart.plot_html

    all_values = [chart.current_ask, chart.current_value, chart.market_reference_value, chart.forward_base_value]
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
    bcv_y = y_for(chart.current_value)
    marker_y = y_for(chart.market_reference_value)
    base_y = y_for(chart.forward_base_value)
    band_map = {band.label: band.value for band in chart.fan_bands}
    bull_y = y_for(band_map.get("Upside", chart.forward_base_value))
    bear_y = y_for(band_map.get("Downside", chart.forward_base_value))

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
        f'<circle class="scenario-dot bcv-dot" cx="{x_left}" cy="{bcv_y:.1f}" r="6"></circle>'
        f'<circle class="scenario-dot base-dot" cx="{x_right}" cy="{base_y:.1f}" r="6"></circle>'
        f'<circle class="scenario-dot bull-dot" cx="{x_right}" cy="{bull_y:.1f}" r="6"></circle>'
        f'<circle class="scenario-dot bear-dot" cx="{x_right}" cy="{bear_y:.1f}" r="6"></circle>'
        f'<text class="chart-label" x="{x_left}" y="252" text-anchor="middle">Today</text>'
        f'<text class="chart-label" x="{x_right}" y="252" text-anchor="middle">{escape(chart.forward_year_label)}</text>'
        f'<text class="chart-annotation" x="{x_left - 12}" y="{marker_y - 12:.1f}" text-anchor="end">{escape(chart.market_reference_label)} {_currency(chart.market_reference_value)}</text>'
        f'<text class="chart-annotation" x="{x_left - 12}" y="{ask_y + 22:.1f}" text-anchor="end">Ask {_currency(chart.current_ask)}</text>'
        f'<text class="chart-annotation" x="{x_left - 12}" y="{bcv_y + 4:.1f}" text-anchor="end">{escape(chart.current_value_label)} {_currency(chart.current_value)}</text>'
        f'<text class="chart-annotation base-text" x="{x_right + 14}" y="{base_y + 4:.1f}">Base {_currency(chart.forward_base_value)}</text>'
        f'<text class="chart-annotation bull-text" x="{x_right + 14}" y="{bull_y + 4:.1f}">Upside {_currency(band_map.get("Upside", chart.forward_base_value))}</text>'
        f'<text class="chart-annotation bear-text" x="{x_right + 14}" y="{bear_y + 4:.1f}">Downside {_currency(band_map.get("Downside", chart.forward_base_value))}</text>'
        "</svg>"
        "</div>"
    )


def _render_secondary_scenario_chart(chart: ScenarioChartSection) -> str:
    if chart.secondary_plot_html:
        return chart.secondary_plot_html
    return _render_scenario_chart(chart)


def _render_case_columns(section: object) -> str:
    cases = [
        section.bull_case,
        section.base_case,
        section.bear_case,
    ]
    html = "\n".join(_render_case_card(case) for case in cases)
    if getattr(section, "stress_case", None) is not None:
        html += "\n" + _render_stress_case_card(section.stress_case)
    return html


def _render_case_card(case: ScenarioCase) -> str:
    assumptions = _render_case_list(case.assumptions)
    drivers = _render_case_list(case.key_drivers)
    risks = _render_case_list(case.risk_factors)
    return (
        '<section class="card case-card">'
        f"<div class=\"section-label\">{escape(case.name)}</div>"
        f"<h3>{escape(case.name)}</h3>"
        f"<div class=\"case-value\">{_currency(case.scenario_value)}</div>"
        f"<p class=\"case-move\">{escape(case.implied_move_text)}</p>"
        f"<p class=\"body-copy\">{escape(case.assessment.summary)}</p>"
        '<div class="case-block-label">Works If</div>'
        f"{assumptions}"
        '<div class="case-block-label">Drivers</div>'
        f"{drivers}"
        '<div class="case-block-label">Risk</div>'
        f"{risks}"
        "</section>"
    )


def _render_signal_metrics(section: object) -> str:
    metrics = [
        section.price_to_rent,
        section.net_opportunity_delta,
        section.scarcity,
        section.forward_gap,
        section.liquidity,
        section.optionality,
    ]
    cards = "".join(_render_signal_metric_card(m) for m in metrics if m is not None)
    return f'<div class="signal-metrics-strip">{cards}</div>'


def _render_signal_metric_card(metric: object) -> str:
    return (
        '<div class="signal-metric-card">'
        f'<div class="signal-metric-label">{escape(metric.label)}</div>'
        f'<div class="signal-metric-value">{escape(metric.value_text)}</div>'
        f'<div class="signal-metric-class {_signal_class_css(metric.classification)}">{escape(metric.classification)}</div>'
        f'<div class="signal-metric-context">{escape(metric.context)}</div>'
        "</div>"
    )


def _signal_class_css(classification: str) -> str:
    mapping = {
        "positive": "sig-positive",
        "fast": "sig-positive",
        "strong value": "sig-positive",
        "meaningful": "sig-moderate",
        "moderate": "sig-moderate",
        "normal": "sig-moderate",
        "fair": "sig-moderate",
        "limited": "sig-caution",
        "slow": "sig-caution",
        "fully valued": "sig-caution",
        "negative": "sig-negative",
        "stale": "sig-negative",
        "weak": "sig-negative",
        "expensive": "sig-negative",
        "overpriced": "sig-negative",
        "unavailable": "sig-muted",
    }
    return mapping.get(classification.strip().lower(), "sig-muted")


def _render_stress_case_card(case: ScenarioCase) -> str:
    assumptions = _render_case_list(case.assumptions)
    risks = _render_case_list(case.risk_factors)
    return (
        '<section class="card case-card stress-case-card">'
        '<div class="section-label stress-label">⚠ Tail Risk</div>'
        f"<h3>{escape(case.name)}</h3>"
        f"<div class=\"case-value stress-value\">{_currency(case.scenario_value)}</div>"
        f"<p class=\"case-move\">{escape(case.implied_move_text)}</p>"
        f"<p class=\"body-copy stress-disclaimer\">{escape(case.assessment.summary)}</p>"
        '<div class="case-block-label">Shock Scenario</div>'
        f"{assumptions}"
        '<div class="case-block-label">Capital Risk</div>'
        f"{risks}"
        "</section>"
    )


def _render_case_list(items: list[str]) -> str:
    rendered_items = "".join(f"<li>{escape(item)}</li>" for item in items)
    return f'<ul class="case-list">{rendered_items}</ul>'


def _render_case_list_items(items: list[str]) -> str:
    return "\n".join(f"<li>{escape(item)}</li>" for item in items)


def _render_comp_cards(cards: list[object]) -> str:
    return "\n".join(_render_comp_card(card) for card in cards)


def _render_comp_card(card: object) -> str:
    why_comp = _render_case_list(card.why_comp)
    cautions = _render_case_list(card.cautions or ["No major fit issue beyond normal adjustment risk."])
    adjustments = _render_case_list(card.adjustments)
    micro_location = _render_case_list(card.micro_location_notes or ["No micro-location notes were added to this comp record yet."])
    return (
        '<section class="comp-card">'
        f'<div class="comp-card-top"><div class="comp-address">{escape(card.address)}</div><div class="comp-fit">{escape(card.fit_label)}</div></div>'
        f'<div class="comp-source">{escape(card.source_text)}</div>'
        '<div class="metric-grid compact-metrics comp-metrics">'
        f'<div><span>Sale Price</span><strong>{escape(card.sale_price_text)}</strong></div>'
        f'<div><span>Adj. Value</span><strong>{escape(card.adjusted_price_text)}</strong></div>'
        f'<div><span>Sale Date</span><strong>{escape(card.sale_date_text)}</strong></div>'
        '</div>'
        '<div class="case-block-label">Why This Is A Comp</div>'
        f'{why_comp}'
        '<div class="case-block-label">Adjustments</div>'
        f'{adjustments}'
        '<div class="case-block-label">Micro-Location</div>'
        f'{micro_location}'
        '<div class="case-block-label">Cautions</div>'
        f'{cautions}'
        '</section>'
    )
