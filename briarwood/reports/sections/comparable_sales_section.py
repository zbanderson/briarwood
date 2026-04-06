from __future__ import annotations

from briarwood.reports.section_helpers import get_comparable_sales
from briarwood.reports.schemas import ComparableCompCard, ComparableSalesSection, SectionAssessment
from briarwood.schemas import AnalysisReport


def build_comparable_sales_section(report: AnalysisReport) -> ComparableSalesSection:
    module = report.get_module("comparable_sales")
    comps = get_comparable_sales(report)

    if comps.comparable_value is None:
        return ComparableSalesSection(
            title="Comparable Sales",
            summary="No usable same-town sale comps were available for this property yet.",
            comparable_value_text="Unavailable",
            confidence_text=f"{round(module.confidence * 100):d}%",
            comp_count_text=f"0 kept | {comps.rejected_count} screened out",
            freshest_sale_text="Unavailable",
            median_sale_age_text="Unavailable",
            screening_summary=_screening_summary(comps.rejection_reasons),
            curation_summary=comps.curation_summary or "Unavailable",
            verification_summary=comps.verification_summary or "Unavailable",
            methodology_notes=comps.assumptions,
            warnings=comps.unsupported_claims + comps.warnings,
            comps=[],
            assessment=SectionAssessment(
                score=module.score,
                confidence=module.confidence,
                summary="Fair value is leaning more heavily on non-comp anchors because the comparable-sale set is thin.",
            ),
        )

    comp_cards = [
        ComparableCompCard(
            address=comp.address,
            sale_price_text=_currency(comp.sale_price),
            adjusted_price_text=_currency(comp.adjusted_price),
            sale_date_text=comp.sale_date,
            source_text=comp.source_summary or "Local comp record",
            fit_label=comp.fit_label.title(),
            micro_location_notes=comp.micro_location_notes[:2],
            why_comp=comp.why_comp[:3],
            cautions=comp.cautions[:2],
            adjustments=comp.adjustments_summary[:3],
        )
        for comp in comps.comps_used[:3]
    ]
    methodology_notes = list(comps.assumptions)
    methodology_notes.append(
        "Briarwood does not treat matching bed and bath counts alone as enough; comps are screened on same-town location, property-type family, size, lot profile, vintage, and sale recency."
    )
    methodology_notes.append(
        "Each kept comp includes a plain-English fit rationale so the comp set is reviewable rather than black-box."
    )

    return ComparableSalesSection(
        title="Comparable Sales",
        summary=comps.summary,
        comparable_value_text=_currency(comps.comparable_value),
        confidence_text=f"{round(module.confidence * 100):d}%",
        comp_count_text=f"{comps.comp_count} kept | {comps.rejected_count} screened out",
        freshest_sale_text=comps.freshest_sale_date or "Unavailable",
        median_sale_age_text=_days_text(comps.median_sale_age_days),
        screening_summary=_screening_summary(comps.rejection_reasons),
        curation_summary=comps.curation_summary or "Unavailable",
        verification_summary=comps.verification_summary or "Unavailable",
        methodology_notes=methodology_notes[:4],
        warnings=(comps.warnings + comps.unsupported_claims)[:5],
        comps=comp_cards,
        assessment=SectionAssessment(
            score=module.score,
            confidence=module.confidence,
            summary="Fair value now has a real property-level sale-comp anchor instead of relying only on town-level context.",
        ),
    )


def _currency(value: float) -> str:
    return f"${value:,.0f}"


def _days_text(value: int | None) -> str:
    if value is None:
        return "Unavailable"
    return f"{value} days"


def _screening_summary(reasons: dict[str, int]) -> str:
    if not reasons:
        return "The current comp set cleared Briarwood's relevance filters without obvious mismatches."
    ordered = sorted(reasons.items(), key=lambda item: (-item[1], item[0]))
    top_reasons = ", ".join(f"{count} {reason.replace('_', ' ')}" for reason, count in ordered[:3])
    return f"Most screened-out sales failed on: {top_reasons}."
