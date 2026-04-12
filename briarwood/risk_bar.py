from __future__ import annotations

from dataclasses import dataclass

from briarwood.evidence import compute_confidence_breakdown, compute_critical_assumption_statuses
from briarwood.schemas import AnalysisReport


@dataclass(slots=True)
class RiskBarItem:
    name: str
    score: int
    level: str
    label: str

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "score": self.score,
            "level": self.level,
            "label": self.label,
        }


def build_risk_bar(report: AnalysisReport) -> list[RiskBarItem]:
    return [
        _price_risk(report),
        _carry_risk(report),
        _liquidity_risk(report),
        _execution_risk(report),
        _confidence_risk(report),
    ]


def _price_risk(report: AnalysisReport) -> RiskBarItem:
    current_value = report.module_results.get("current_value")
    metrics = current_value.metrics if current_value is not None else {}
    mispricing_pct = _as_float(metrics.get("mispricing_pct"))
    basis_gap_pct = _as_float(metrics.get("net_opportunity_delta_pct"))

    premium_gap = max(0.0, -(mispricing_pct or 0.0))
    basis_gap = max(0.0, -(basis_gap_pct if basis_gap_pct is not None else (mispricing_pct or 0.0)))
    discount_gap = max(0.0, mispricing_pct or 0.0)

    raw_score = max((premium_gap * 340.0), (basis_gap * 320.0)) - (discount_gap * 120.0)
    score = _clamp_score(raw_score)

    if score >= 67:
        label = "Premium to fair value"
    elif score >= 34:
        label = "Tight valuation cushion"
    elif discount_gap >= 0.08:
        label = "Discount to fair value"
    else:
        label = "Near fair value"

    return RiskBarItem(name="Price", score=score, level=_risk_level(score), label=label)


def _carry_risk(report: AnalysisReport) -> RiskBarItem:
    income_support = report.module_results.get("income_support")
    metrics = income_support.metrics if income_support is not None else {}
    carry_ratio = _as_float(metrics.get("income_support_ratio"))
    monthly_cash_flow = _as_float(metrics.get("monthly_cash_flow"))
    if monthly_cash_flow is None:
        monthly_cash_flow = _as_float(metrics.get("estimated_monthly_cash_flow"))

    ratio_score = _carry_ratio_risk_score(carry_ratio)
    shortfall_score = _monthly_shortfall_risk_score(monthly_cash_flow)
    score = _clamp_score((ratio_score * 0.65) + (shortfall_score * 0.35))

    if score >= 67:
        label = "Heavy monthly drag"
    elif score >= 34:
        label = "Carry needs support"
    else:
        label = "Carry is supported"

    return RiskBarItem(name="Carry", score=score, level=_risk_level(score), label=label)


def _liquidity_risk(report: AnalysisReport) -> RiskBarItem:
    liquidity = report.module_results.get("liquidity_signal")
    metrics = liquidity.metrics if liquidity is not None else {}
    liquidity_score = _as_float(metrics.get("liquidity_score"))
    comp_count = _as_float(metrics.get("comp_count")) or _comp_count(report)
    days_on_market = _days_on_market(report)

    score = 50.0 if liquidity_score is None else 100.0 - liquidity_score
    if comp_count == 0:
        score += 10.0
    elif comp_count < 3:
        score += 6.0
    if days_on_market is None:
        score += 5.0
    elif days_on_market >= 90:
        score += 10.0
    elif days_on_market >= 60:
        score += 6.0

    normalized_score = _clamp_score(score)
    if normalized_score >= 67:
        label = "Thin exit market"
    elif normalized_score >= 34:
        label = "Mixed exit depth"
    else:
        label = "Exit path looks workable"

    return RiskBarItem(name="Liquidity", score=normalized_score, level=_risk_level(normalized_score), label=label)


def _execution_risk(report: AnalysisReport) -> RiskBarItem:
    property_input = report.property_input
    current_value = report.module_results.get("current_value")
    current_metrics = current_value.metrics if current_value is not None else {}
    hybrid = report.module_results.get("hybrid_value")
    hybrid_metrics = hybrid.metrics if hybrid is not None else {}

    assumption_statuses = {item.key: item for item in compute_critical_assumption_statuses(report)}
    capex_status = assumption_statuses.get("capex")

    lane = str(getattr(property_input, "capex_lane", "") or "").strip().lower()
    condition_profile = str(getattr(property_input, "condition_profile", "") or "").strip().lower()
    base_score = {
        "light": 22.0,
        "low": 22.0,
        "moderate": 48.0,
        "heavy": 78.0,
    }.get(lane, 58.0)

    score = base_score
    if capex_status is not None:
        if capex_status.status == "estimated":
            score += 10.0
        elif capex_status.status == "missing":
            score += 18.0

    capex_basis_source = str(current_metrics.get("capex_basis_source") or "").lower()
    if capex_basis_source in {"inferred_lane", "inferred_condition", "unknown"}:
        score += 12.0

    if condition_profile in {"dated", "needs_work", "deferred", "rough"}:
        score += 12.0

    if bool(hybrid_metrics.get("is_hybrid")):
        score += 12.0

    renovation = report.module_results.get("renovation_scenario")
    teardown = report.module_results.get("teardown_scenario")
    if bool((renovation.metrics if renovation is not None else {}).get("enabled")):
        score += 15.0
    if bool((teardown.metrics if teardown is not None else {}).get("enabled")):
        score += 15.0

    normalized_score = _clamp_score(score)
    if normalized_score >= 67:
        label = "Execution heavy"
    elif normalized_score >= 34:
        label = "Some execution dependence"
    else:
        label = "Low execution burden"

    return RiskBarItem(name="Execution", score=normalized_score, level=_risk_level(normalized_score), label=label)


def _confidence_risk(report: AnalysisReport) -> RiskBarItem:
    confidence = compute_confidence_breakdown(report)
    assumption_statuses = compute_critical_assumption_statuses(report)
    current_value = report.module_results.get("current_value")
    comparable_sales = report.module_results.get("comparable_sales")

    score = 100.0 - (confidence.overall_confidence * 100.0)
    comp_count = _comp_count(report)
    if comp_count == 0:
        score += 20.0
    elif comp_count < 3:
        score += 12.0
    comp_confidence = float(comparable_sales.confidence) if comparable_sales is not None else 0.0
    if comp_confidence < 0.35:
        score += 8.0
    current_confidence = float(current_value.confidence) if current_value is not None else 0.0
    if current_confidence < 0.50:
        score += 10.0
    missing_count = sum(1 for item in assumption_statuses if item.status == "missing")
    estimated_count = sum(1 for item in assumption_statuses if item.status == "estimated")
    score += min(18.0, (missing_count * 4.0) + (estimated_count * 2.0))

    normalized_score = _clamp_score(score)
    if normalized_score >= 67:
        label = "Thin evidence base"
    elif normalized_score >= 34:
        label = "Some evidence gaps"
    else:
        label = "Well supported"

    return RiskBarItem(name="Confidence", score=normalized_score, level=_risk_level(normalized_score), label=label)


def _carry_ratio_risk_score(value: float | None) -> float:
    if value is None:
        return 55.0
    if value <= 0.40:
        return 96.0
    if value <= 0.60:
        return _lerp(value, 0.40, 0.60, 96.0, 78.0)
    if value <= 0.80:
        return _lerp(value, 0.60, 0.80, 78.0, 54.0)
    if value <= 1.00:
        return _lerp(value, 0.80, 1.00, 54.0, 24.0)
    if value <= 1.15:
        return _lerp(value, 1.00, 1.15, 24.0, 10.0)
    return 6.0


def _monthly_shortfall_risk_score(value: float | None) -> float:
    if value is None:
        return 55.0
    shortfall = max(0.0, -value)
    if shortfall <= 250.0:
        return 10.0
    if shortfall <= 1000.0:
        return _lerp(shortfall, 250.0, 1000.0, 10.0, 35.0)
    if shortfall <= 2500.0:
        return _lerp(shortfall, 1000.0, 2500.0, 35.0, 65.0)
    if shortfall <= 5000.0:
        return _lerp(shortfall, 2500.0, 5000.0, 65.0, 95.0)
    return 100.0


def _comp_count(report: AnalysisReport) -> int:
    comparable_sales = report.module_results.get("comparable_sales")
    if comparable_sales is None:
        return 0
    value = comparable_sales.metrics.get("comp_count")
    return int(value) if isinstance(value, (int, float)) else 0


def _days_on_market(report: AnalysisReport) -> int | None:
    property_input = report.property_input
    if property_input is not None and property_input.days_on_market is not None:
        return int(property_input.days_on_market)
    liquidity = report.module_results.get("liquidity_signal")
    if liquidity is None:
        return None
    value = liquidity.metrics.get("days_on_market")
    return int(value) if isinstance(value, (int, float)) else None


def _risk_level(score: int) -> str:
    if score >= 67:
        return "High"
    if score >= 34:
        return "Medium"
    return "Low"


def _clamp_score(value: float) -> int:
    return max(0, min(int(round(value)), 100))


def _lerp(value: float, lo: float, hi: float, out_lo: float, out_hi: float) -> float:
    if hi == lo:
        return out_lo
    position = (value - lo) / (hi - lo)
    return out_lo + (out_hi - out_lo) * position


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
