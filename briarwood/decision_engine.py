"""DEPRECATED — scheduled for deletion 2026-04-22 (Wednesday).

This module is the legacy verdict path. All remaining callers
(`dash_app/quick_decision.py`, `dash_app/view_models.py`,
`reports/sections/thesis_section.py`, `reports/sections/conclusion_section.py`)
will migrate to `briarwood/projections/legacy_verdict.py` via the
`AnalysisReport -> routed` adapter that lands Wednesday AM.

DO NOT add new callers. DO NOT extend.
The canonical verdict is `briarwood/synthesis/structured.py::build_unified_output()`.
Display-layer projections live in `briarwood/projections/`.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from briarwood.schemas import AnalysisReport


DECISION_RECOMMENDATIONS: tuple[str, ...] = (
    "BUY",
    "LEAN BUY",
    "NEUTRAL",
    "LEAN PASS",
    "AVOID",
)


@dataclass(slots=True)
class DecisionOutput:
    recommendation: str
    conviction: float
    primary_reason: str
    secondary_reason: str
    required_beliefs: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_decision(report: AnalysisReport) -> DecisionOutput:
    current_value = report.module_results.get("current_value")
    income_support = report.module_results.get("income_support")
    comparable_sales = report.module_results.get("comparable_sales")
    property_data_quality = report.module_results.get("property_data_quality")
    town_outlook = report.module_results.get("town_county_outlook")

    current_metrics = current_value.metrics if current_value is not None else {}
    income_metrics = income_support.metrics if income_support is not None else {}
    comp_metrics = comparable_sales.metrics if comparable_sales is not None else {}

    fair_value_gap = _as_float(current_metrics.get("mispricing_pct"))
    monthly_carry = _as_float(income_metrics.get("monthly_cash_flow"))
    if monthly_carry is None:
        monthly_carry = _as_float(income_metrics.get("estimated_monthly_cash_flow"))
    income_support_ratio = _as_float(income_metrics.get("income_support_ratio"))
    comp_count = _as_int(comp_metrics.get("comp_count")) or 0

    evidence_quality = _evidence_quality(
        current_confidence=_as_float(getattr(current_value, "confidence", None)) or 0.0,
        income_confidence=_as_float(getattr(income_support, "confidence", None)) or 0.0,
        comp_confidence=_as_float(comp_metrics.get("comp_confidence"))
        or _as_float(getattr(comparable_sales, "confidence", None))
        or 0.0,
        property_quality_confidence=_as_float(getattr(property_data_quality, "confidence", None)) or 0.0,
        town_confidence=_as_float(getattr(town_outlook, "confidence", None)) or 0.0,
    )

    valuation_band = _valuation_band(fair_value_gap)
    carry_band = _carry_band(monthly_carry, income_support_ratio)
    recommendation = _recommendation_from_bands(
        valuation_band=valuation_band,
        carry_band=carry_band,
        fair_value_gap=fair_value_gap,
        monthly_carry=monthly_carry,
        income_support_ratio=income_support_ratio,
    )

    primary_reason = _primary_reason(
        recommendation=recommendation,
        fair_value_gap=fair_value_gap,
        monthly_carry=monthly_carry,
        income_support_ratio=income_support_ratio,
    )
    secondary_reason = _secondary_reason(
        recommendation=recommendation,
        fair_value_gap=fair_value_gap,
        monthly_carry=monthly_carry,
        income_support_ratio=income_support_ratio,
        comp_count=comp_count,
        evidence_quality=evidence_quality,
    )
    required_beliefs = _required_beliefs(
        fair_value_gap=fair_value_gap,
        monthly_carry=monthly_carry,
        income_support_ratio=income_support_ratio,
        evidence_quality=evidence_quality,
        comp_count=comp_count,
    )
    conviction = _conviction(
        recommendation=recommendation,
        valuation_band=valuation_band,
        carry_band=carry_band,
        evidence_quality=evidence_quality,
    )

    return DecisionOutput(
        recommendation=recommendation,
        conviction=round(conviction, 2),
        primary_reason=primary_reason,
        secondary_reason=secondary_reason,
        required_beliefs=required_beliefs[:3],
    )


def _evidence_quality(
    *,
    current_confidence: float,
    income_confidence: float,
    comp_confidence: float,
    property_quality_confidence: float,
    town_confidence: float,
) -> float:
    return _clamp(
        current_confidence * 0.32
        + income_confidence * 0.23
        + comp_confidence * 0.23
        + property_quality_confidence * 0.12
        + town_confidence * 0.10
    )


def _valuation_band(fair_value_gap: float | None) -> str:
    if fair_value_gap is None:
        return "unknown"
    if fair_value_gap >= 0.12:
        return "strong"
    if fair_value_gap >= 0.05:
        return "good"
    if fair_value_gap > -0.08:
        return "neutral"
    if fair_value_gap > -0.15:
        return "weak"
    return "bad"


def _carry_band(monthly_carry: float | None, income_support_ratio: float | None) -> str:
    if monthly_carry is None and income_support_ratio is None:
        return "unknown"
    if (
        monthly_carry is not None
        and monthly_carry >= 250
    ) or (
        income_support_ratio is not None and income_support_ratio >= 1.0
    ):
        return "strong"
    if (
        monthly_carry is not None
        and monthly_carry >= -500
    ) or (
        income_support_ratio is not None and income_support_ratio >= 0.8
    ):
        return "ok"
    if (
        monthly_carry is not None
        and monthly_carry <= -3000
    ) or (
        income_support_ratio is not None and income_support_ratio < 0.45
    ):
        return "bad"
    if (
        monthly_carry is not None
        and monthly_carry <= -1500
    ) or (
        income_support_ratio is not None and income_support_ratio < 0.55
    ):
        return "weak"
    return "mixed"


def _recommendation_from_bands(
    *,
    valuation_band: str,
    carry_band: str,
    fair_value_gap: float | None,
    monthly_carry: float | None,
    income_support_ratio: float | None,
) -> str:
    if valuation_band in {"bad", "weak"} and carry_band in {"bad", "weak"}:
        return "AVOID" if valuation_band == "bad" or carry_band == "bad" else "LEAN PASS"
    if carry_band == "bad" and (fair_value_gap is None or fair_value_gap <= 0.05):
        return "AVOID"
    if valuation_band == "bad":
        return "LEAN PASS"
    if valuation_band == "strong" and carry_band in {"strong", "ok", "mixed"}:
        return "BUY"
    if valuation_band == "good" and carry_band in {"strong", "ok", "mixed"}:
        return "LEAN BUY"
    if valuation_band in {"strong", "good"} and carry_band in {"weak", "bad"}:
        return "NEUTRAL"
    if valuation_band == "neutral" and carry_band in {"strong", "ok"}:
        return "NEUTRAL"
    if valuation_band == "weak" and carry_band in {"strong", "ok"}:
        return "NEUTRAL"
    if (fair_value_gap is not None and fair_value_gap <= 0.0) and (
        (monthly_carry is not None and monthly_carry < 0)
        or (income_support_ratio is not None and income_support_ratio < 0.7)
    ):
        return "LEAN PASS"
    return "NEUTRAL"


def _primary_reason(
    *,
    recommendation: str,
    fair_value_gap: float | None,
    monthly_carry: float | None,
    income_support_ratio: float | None,
) -> str:
    if recommendation in {"BUY", "LEAN BUY"} and fair_value_gap is not None and fair_value_gap > 0:
        return f"Fair value sits about {fair_value_gap:.0%} above the ask."
    if recommendation in {"AVOID", "LEAN PASS"} and fair_value_gap is not None and fair_value_gap < 0:
        return f"Ask is about {abs(fair_value_gap):.0%} above fair value."
    if monthly_carry is not None:
        return f"Monthly carry runs about {_format_signed_currency(monthly_carry)}."
    if income_support_ratio is not None:
        return f"Rent covers about {income_support_ratio:.0%} of carrying cost."
    return "The current valuation and carry signals are mixed."


def _secondary_reason(
    *,
    recommendation: str,
    fair_value_gap: float | None,
    monthly_carry: float | None,
    income_support_ratio: float | None,
    comp_count: int,
    evidence_quality: float,
) -> str:
    if monthly_carry is not None and income_support_ratio is not None:
        if monthly_carry < 0:
            return f"Rent covers only about {income_support_ratio:.0%} of carrying cost."
        return f"Carry is roughly supported, with rent covering about {income_support_ratio:.0%} of cost."
    if evidence_quality < 0.45:
        return "Evidence quality is still thin, so this call should be held with lower conviction."
    if comp_count < 3:
        return "Comparable-sale depth is still thin."
    if fair_value_gap is not None:
        return "The pricing gap is modest, so execution matters more than headline upside."
    return "The current evidence stack does not fully resolve the case."


def _required_beliefs(
    *,
    fair_value_gap: float | None,
    monthly_carry: float | None,
    income_support_ratio: float | None,
    evidence_quality: float,
    comp_count: int,
) -> list[str]:
    beliefs: list[str] = []
    if fair_value_gap is None:
        beliefs.append("Comparable sales need to confirm fair value with a usable local anchor.")
    elif fair_value_gap < 0:
        beliefs.append("You need to buy materially closer to fair value than the current ask.")
    else:
        beliefs.append("Fair value needs to hold near the current estimate through diligence.")

    if monthly_carry is None or income_support_ratio is None:
        beliefs.append("Rent and financing assumptions need to be verified with real numbers.")
    elif monthly_carry < 0 or income_support_ratio < 0.8:
        beliefs.append("Carry needs to improve enough to cut the monthly shortfall materially.")

    if comp_count < 3:
        beliefs.append("Comparable-sales support needs to deepen beyond a thin comp set.")
    elif evidence_quality < 0.45:
        beliefs.append("The current conclusion needs stronger evidence before treating it as high conviction.")
    else:
        beliefs.append("Key underwriting assumptions need to hold close to the current base case.")

    return beliefs


def _conviction(
    *,
    recommendation: str,
    valuation_band: str,
    carry_band: str,
    evidence_quality: float,
) -> float:
    anchor = {
        "BUY": 0.82,
        "LEAN BUY": 0.68,
        "NEUTRAL": 0.50,
        "LEAN PASS": 0.36,
        "AVOID": 0.24,
    }[recommendation]
    strength = (
        _band_strength(valuation_band) * 0.55
        + _band_strength(carry_band) * 0.45
    )
    conviction = anchor * 0.65 + evidence_quality * 0.25 + abs(strength - 0.5) * 0.10
    if evidence_quality < 0.35:
        conviction = min(conviction, 0.58)
    return _clamp(conviction)


def _band_strength(band: str) -> float:
    return {
        "strong": 0.95,
        "good": 0.78,
        "neutral": 0.50,
        "ok": 0.62,
        "mixed": 0.42,
        "weak": 0.24,
        "bad": 0.08,
        "unknown": 0.35,
    }.get(band, 0.35)


def _format_signed_currency(value: float) -> str:
    prefix = "+" if value >= 0 else "-"
    return f"{prefix}${abs(value):,.0f}/mo"


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))
