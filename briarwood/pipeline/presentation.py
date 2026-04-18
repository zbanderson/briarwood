from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from briarwood.agent.tools import CMAResult, InvestmentScreenResult, PropertyBrief, RentOutlook, TownMarketRead


@dataclass(frozen=True)
class PresentationCard:
    key: str
    title: str
    body: list[str]
    tone: str = "neutral"


@dataclass(frozen=True)
class PresentationTable:
    key: str
    title: str
    columns: list[str]
    rows: list[dict[str, Any]]


@dataclass(frozen=True)
class PresentationChart:
    key: str
    kind: str
    title: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class PropertyPresentationPayload:
    property_id: str
    address: str | None
    contract_type: str = "property_brief"
    analysis_mode: str = "browse"
    cards: list[PresentationCard] = field(default_factory=list)
    tables: list[PresentationTable] = field(default_factory=list)
    charts: list[PresentationChart] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


def build_property_presentation(
    property_id: str,
    *,
    brief: "PropertyBrief",
    enrichment: dict[str, Any] | None = None,
    risk: dict[str, Any] | None = None,
    cma: "CMAResult | None" = None,
    rent_outlook: "RentOutlook | None" = None,
    town_read: "TownMarketRead | None" = None,
    investment_screen: "InvestmentScreenResult | None" = None,
    contract_type: str = "property_brief",
    analysis_mode: str = "browse",
) -> PropertyPresentationPayload:
    """Build a renderer-ready payload from pre-computed backend outputs.

    Callers own the routed-pipeline invocation and pass the derived ``brief``,
    ``enrichment``, and (optionally) ``risk`` in — this module never runs the
    pipeline itself. Pass ``risk=None`` to omit the risk bar chart (browse).
    """
    enrichment = enrichment or {}

    cards = [
        PresentationCard(
            key="property_header",
            title="Property",
            body=[
                _join_non_empty(
                    [
                        brief.address or property_id,
                        f"{brief.beds}bd/{brief.baths}ba" if brief.beds is not None and brief.baths is not None else None,
                        _money(brief.ask_price, prefix="ask "),
                    ]
                ),
            ],
        ),
        PresentationCard(
            key="purchase_brief",
            title="Purchase Brief",
            body=[
                _setup_line(brief),
                _support_line(brief),
                _risk_line(brief),
                _next_line(brief),
            ],
            tone="decision",
        ),
        PresentationCard(
            key="data_coverage",
            title="Source Coverage",
            body=_coverage_lines(enrichment),
            tone="supporting",
        ),
    ]

    google = dict(enrichment.get("google") or {})
    nearby = dict(google.get("nearby_places") or {})
    type_counts = dict(nearby.get("type_counts") or {})
    town_intelligence = enrichment.get("town_intelligence") or {}
    town_summary = dict(town_intelligence.get("summary") or {})
    if type_counts or town_summary:
        cards.append(
            PresentationCard(
                key="location_pulse",
                title="Location Pulse",
                body=_location_lines(type_counts, town_summary),
                tone="supporting",
            )
        )

    attom = dict(enrichment.get("attom") or {})
    tables: list[PresentationTable] = []
    sale_history = list((attom.get("sale_history_snapshot") or {}).get("sale_history") or [])
    if sale_history:
        tables.append(
            PresentationTable(
                key="sale_history",
                title="Sale History",
                columns=["date", "price", "event", "document_number"],
                rows=[
                    {
                        "date": row.get("sale_date"),
                        "price": row.get("sale_price"),
                        "event": row.get("sale_type") or row.get("event"),
                        "document_number": row.get("document_number"),
                    }
                    for row in sale_history[:6]
                ],
            )
        )
    coverage_rows = [
        {"category": key, "status": value}
        for key, value in sorted((enrichment.get("source_coverage") or {}).items())
    ]
    if coverage_rows:
        tables.append(
            PresentationTable(
                key="source_coverage",
                title="Source Coverage",
                columns=["category", "status"],
                rows=coverage_rows,
            )
        )
    if cma and cma.comps:
        tables.append(
            PresentationTable(
                key="cma_comps",
                title="CMA Comps",
                columns=["address", "beds", "baths", "ask_price", "blocks_to_beach", "selection_rationale"],
                rows=[
                    {
                        "address": comp.address,
                        "beds": comp.beds,
                        "baths": comp.baths,
                        "ask_price": comp.ask_price,
                        "blocks_to_beach": comp.blocks_to_beach,
                        "selection_rationale": comp.selection_rationale,
                    }
                    for comp in cma.comps
                ],
            )
        )
        cards.append(
            PresentationCard(
                key="cma",
                title="CMA",
                body=[
                    f"Fair value anchor: {_money(cma.fair_value_base) or 'n/a'}",
                    f"Range: {_money(cma.value_low) or 'n/a'} to {_money(cma.value_high) or 'n/a'}",
                    cma.comp_selection_summary or "Comps selected from nearby saved properties.",
                ],
                tone="decision",
            )
        )
    charts = [
        PresentationChart(
            key="verdict_gauge",
            kind="verdict_gauge",
            title="Decision Stance",
            payload={"property_id": property_id},
        ),
        PresentationChart(
            key="value_opportunity",
            kind="value_opportunity",
            title="Ask vs Value",
            payload={"property_id": property_id},
        ),
    ]

    if rent_outlook:
        body = [
            _join_non_empty(
                [
                    f"Current rent {_money(rent_outlook.current_monthly_rent)}" if rent_outlook.current_monthly_rent is not None else None,
                    f"effective {_money(rent_outlook.effective_monthly_rent)}" if rent_outlook.effective_monthly_rent is not None else None,
                ],
                separator="; ",
            ) or "Current rent picture is still thin.",
        ]
        if rent_outlook.zillow_market_rent is not None:
            body.append(
                f"SearchAPI Zillow market rent anchor: {_money(rent_outlook.zillow_market_rent)}"
                + (
                    f" from {rent_outlook.zillow_rental_comp_count} rental listing(s)"
                    if rent_outlook.zillow_rental_comp_count
                    else ""
                )
            )
        if rent_outlook.horizon_years is not None:
            body.append(
                f"{rent_outlook.horizon_years}-year working range: {_money(rent_outlook.future_rent_low) or 'n/a'} to {_money(rent_outlook.future_rent_high) or 'n/a'}"
            )
        if rent_outlook.basis_to_rent_framing:
            body.append(rent_outlook.basis_to_rent_framing)
        if rent_outlook.owner_occupy_then_rent:
            body.append(rent_outlook.owner_occupy_then_rent)
        cards.append(PresentationCard(key="rent_outlook", title="Rent Outlook", body=body, tone="supporting"))
        charts.append(
            PresentationChart(
                key="rent_burn",
                kind="rent_burn",
                title="Rent Burn",
                payload=dict(rent_outlook.burn_chart_payload or {}),
            )
        )
    if town_read:
        cards.append(
            PresentationCard(
                key="town_pulse",
                title="Town Pulse",
                body=[
                    town_read.narrative_summary or f"No clear town pulse yet for {town_read.town}, {town_read.state}.",
                    "Constructive: " + "; ".join(town_read.bullish_signals[:2]) if town_read.bullish_signals else "Constructive: none yet.",
                    "Risks/watchlist: " + "; ".join((town_read.bearish_signals or town_read.watch_items)[:2]) if (town_read.bearish_signals or town_read.watch_items) else "Risks/watchlist: none yet.",
                ],
                tone="supporting",
            )
        )
    if investment_screen and investment_screen.candidates:
        tables.append(
            PresentationTable(
                key="investment_screen",
                title="Investment Screen",
                columns=["address", "ask_price", "annual_noi", "cap_rate", "monthly_rent"],
                rows=[
                    {
                        "address": row.address,
                        "ask_price": row.ask_price,
                        "annual_noi": row.annual_noi,
                        "cap_rate": row.cap_rate,
                        "monthly_rent": row.monthly_rent,
                    }
                    for row in investment_screen.candidates
                ],
            )
        )

    if risk:
        charts.append(
            PresentationChart(
                key="risk_bar",
                kind="risk_bar",
                title="Risk Profile",
                payload={"property_id": property_id},
            )
        )

    evidence = {
        "enrichment": enrichment,
        "risk": risk,
        "contract_type": contract_type,
    }
    return PropertyPresentationPayload(
        property_id=property_id,
        address=brief.address,
        contract_type=contract_type,
        analysis_mode=analysis_mode,
        cards=cards,
        tables=tables,
        charts=charts,
        next_actions=[_next_line(brief).replace("Next best question: ", "")],
        evidence=evidence,
    )


def _money(value: float | None, *, prefix: str = "") -> str | None:
    if isinstance(value, (int, float)):
        return f"{prefix}${value:,.0f}"
    return None


def _join_non_empty(parts: list[str | None], separator: str = " — ") -> str:
    return separator.join(part for part in parts if isinstance(part, str) and part.strip())


def _setup_line(brief: Any) -> str:
    stance = (brief.decision_stance or "unknown").replace("_", " ")
    if isinstance(brief.ask_premium_pct, (int, float)):
        delta = f"{abs(brief.ask_premium_pct):.1%}"
        direction = "below" if brief.ask_premium_pct < 0 else "above"
        return f"Immediate setup: {stance}. Ask is {delta} {direction} the fair value anchor."
    return f"Immediate setup: {stance}."


def _support_line(brief: Any) -> str:
    if brief.best_path:
        return f"What supports it: {brief.best_path}"
    if brief.key_value_drivers:
        return "What supports it: " + "; ".join(brief.key_value_drivers[:2]) + "."
    return "What supports it: the snapshot run surfaced an actionable purchase read."


def _risk_line(brief: Any) -> str:
    if brief.trust_flags:
        return "What could weaken confidence: " + ", ".join(brief.trust_flags[:3]) + "."
    if brief.key_risks:
        return "What could weaken confidence: " + "; ".join(brief.key_risks[:2]) + "."
    return "What could weaken confidence: no major trust flags were surfaced in the snapshot read."


def _next_line(brief: Any) -> str:
    if brief.next_questions:
        return f"Next best question: {brief.next_questions[0]}"
    if brief.recommended_next_run:
        return f"Next best question: {brief.recommended_next_run}"
    return "Next best question: should I buy this at the current ask?"


def _coverage_lines(enrichment: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    listing = dict(enrichment.get("listing_source") or {})
    if listing.get("source_url"):
        lines.append("SearchAPI/Zillow hydrated the live listing context.")
    if (enrichment.get("attom") or {}).get("sale_history_snapshot"):
        lines.append("ATTOM added structured sale history and ownership timing context.")
    if (enrichment.get("google") or {}).get("geocode"):
        lines.append("Google Maps added geocode and nearby-place context.")
    warnings = list(enrichment.get("warnings") or [])
    if warnings:
        lines.append("Still missing: " + "; ".join(warnings[:2]))
    return lines or ["Coverage is still thin; no post-promotion enrichment has been captured yet."]


def _location_lines(type_counts: dict[str, Any], town_summary: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if type_counts:
        fragments = [f"{count} {kind.replace('_', ' ')}" for kind, count in sorted(type_counts.items())[:3]]
        lines.append("Nearby place scan: " + ", ".join(fragments) + ".")
    if town_summary.get("narrative_summary"):
        lines.append(str(town_summary["narrative_summary"]))
    elif town_summary.get("market_direction"):
        lines.append(f"Town read: {town_summary['market_direction']}.")
    return lines


__all__ = [
    "PresentationCard",
    "PresentationChart",
    "PresentationTable",
    "PropertyPresentationPayload",
    "build_property_presentation",
]
