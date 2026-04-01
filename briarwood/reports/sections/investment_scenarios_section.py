from __future__ import annotations

from briarwood.reports.schemas import (
    InvestmentScenariosSection,
    RenovationScenarioSummary,
    TeardownPhase1Summary,
    TeardownPhase2Summary,
    TeardownProjectTotals,
    TeardownScenarioSummary,
)
from briarwood.schemas import AnalysisReport


def build_investment_scenarios_section(report: AnalysisReport) -> InvestmentScenariosSection | None:
    """Build the investment scenarios section from module results. Returns None if no scenarios are enabled."""
    renovation = _build_renovation(report)
    teardown = _build_teardown(report)
    if renovation is None and teardown is None:
        return None
    return InvestmentScenariosSection(renovation=renovation, teardown=teardown)


def _build_renovation(report: AnalysisReport) -> RenovationScenarioSummary | None:
    result = report.module_results.get("renovation_scenario")
    if result is None:
        return None
    payload = result.payload
    if not isinstance(payload, dict) or not payload.get("enabled"):
        return None
    return RenovationScenarioSummary(
        renovation_budget=float(payload.get("renovation_budget") or 0),
        current_bcv=float(payload.get("current_bcv") or 0),
        renovated_bcv=float(payload.get("renovated_bcv") or 0),
        gross_value_creation=float(payload.get("gross_value_creation") or 0),
        net_value_creation=float(payload.get("net_value_creation") or 0),
        roi_pct=float(payload.get("roi_pct") or 0),
        cost_per_dollar_of_value=payload.get("cost_per_dollar_of_value"),
        condition_change=str(payload.get("condition_change") or ""),
        sqft_change=payload.get("sqft_change"),
        summary=str(payload.get("summary") or ""),
        confidence=float(payload.get("confidence") or 0),
        warnings=list(payload.get("warnings") or []),
    )


def _build_teardown(report: AnalysisReport) -> TeardownScenarioSummary | None:
    result = report.module_results.get("teardown_scenario")
    if result is None:
        return None
    payload = result.payload
    if not isinstance(payload, dict) or not payload.get("enabled"):
        return None
    p1 = payload.get("phase1") or {}
    p2 = payload.get("phase2") or {}
    pt = payload.get("project_totals") or {}
    return TeardownScenarioSummary(
        hold_years=int(payload.get("hold_years") or 0),
        phase1=TeardownPhase1Summary(
            hold_years=int(payload.get("hold_years") or 0),
            total_gross_rent=float(p1.get("total_gross_rent") or 0),
            total_net_cash_flow=float(p1.get("total_net_cash_flow") or 0),
            burn_down_pct=float(p1.get("burn_down_pct") or 0),
            effective_cost_basis=float(p1.get("effective_cost_basis") or 0),
            equity_at_teardown=float(p1.get("equity_at_teardown") or 0),
            mortgage_balance_at_teardown=float(p1.get("mortgage_balance_at_teardown") or 0),
            estimated_property_value_at_teardown=float(p1.get("estimated_property_value_at_teardown") or 0),
            narrative=str(payload.get("phase1_narrative") or ""),
            year_by_year=list(p1.get("year_by_year") or []),
        ),
        phase2=TeardownPhase2Summary(
            demolition_cost=float(p2.get("demolition_cost") or 0),
            construction_cost=float(p2.get("construction_cost") or 0),
            lost_rent_during_construction=float(p2.get("lost_rent_during_construction") or 0),
            total_phase2_cost=float(p2.get("total_phase2_cost") or 0),
            estimated_new_construction_value=float(p2.get("estimated_new_construction_value") or 0),
            comp_basis=str(p2.get("comp_basis") or ""),
            narrative=str(payload.get("phase2_narrative") or ""),
        ),
        project_totals=TeardownProjectTotals(
            total_cash_invested=float(pt.get("total_cash_invested") or 0),
            total_rental_income=float(pt.get("total_rental_income") or 0),
            final_property_value=float(pt.get("final_property_value") or 0),
            final_mortgage_balance=float(pt.get("final_mortgage_balance") or 0),
            net_equity_position=float(pt.get("net_equity_position") or 0),
            total_profit=float(pt.get("total_profit") or 0),
            total_roi_pct=float(pt.get("total_roi_pct") or 0),
            annualized_roi_pct=float(pt.get("annualized_roi_pct") or 0),
            total_timeline_years=float(payload.get("total_project_timeline_years") or 0),
            narrative=str(payload.get("project_narrative") or ""),
        ),
        confidence=float(payload.get("confidence") or 0),
        warnings=list(payload.get("warnings") or []),
    )
