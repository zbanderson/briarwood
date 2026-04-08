from __future__ import annotations

import dataclasses
import math

from briarwood.modules.comparable_sales import ComparableSalesModule
from briarwood.modules.current_value import CurrentValueModule, get_current_value_payload
from briarwood.modules.income_support import IncomeSupportModule, get_income_support_payload
from briarwood.schemas import ModuleResult, PropertyInput
from briarwood.settings import DEFAULT_TEARDOWN_SCENARIO_SETTINGS, TeardownScenarioSettings


class TeardownScenarioModule:
    """
    Models a rent-to-teardown investment strategy.

    Phase 1: Buy the property, rent it for N years, accumulate cash flow and equity.
    Phase 2: Demolish and build new construction, estimate final value.

    No-op if teardown_scenario is absent or disabled.
    """

    name = "teardown_scenario"

    def __init__(
        self,
        settings: TeardownScenarioSettings | None = None,
        *,
        comparable_sales_module: ComparableSalesModule | None = None,
        current_value_module: CurrentValueModule | None = None,
        income_support_module: IncomeSupportModule | None = None,
    ) -> None:
        self.settings = settings or DEFAULT_TEARDOWN_SCENARIO_SETTINGS
        self.comparable_sales_module = comparable_sales_module or ComparableSalesModule()
        self.current_value_module = current_value_module or CurrentValueModule()
        self.income_support_module = income_support_module or IncomeSupportModule()

    def run(
        self,
        property_input: PropertyInput,
        prior_results: dict[str, ModuleResult] | None = None,
    ) -> ModuleResult:
        scenario = property_input.teardown_scenario
        if not scenario or not scenario.get("enabled"):
            return _blocked_result(
                module_name=self.name,
                status="not_enabled",
                summary="Knockdown / new-build scenario is not configured for this property.",
            )

        s = self.settings

        # --- Extract scenario parameters ---
        purchase_price = float(scenario.get("purchase_price") or property_input.purchase_price or 0.0)
        if purchase_price <= 0:
            return _blocked_result(
                module_name=self.name,
                status="missing_inputs",
                summary="Knockdown / new-build scenario requires a purchase price.",
                missing_inputs=["purchase_price"],
            )

        closing_costs_pct = float(scenario.get("closing_costs_pct") or s.default_closing_costs_pct)
        down_payment_pct = float(scenario.get("down_payment_pct") or s.default_down_payment_pct)
        mortgage_rate = float(scenario.get("mortgage_rate_pct") or 0.065)
        mortgage_term_years = int(scenario.get("mortgage_term_years") or 30)
        hold_years = int(scenario.get("hold_years") or 7)
        hold_years = max(s.min_hold_years, min(s.max_hold_years, hold_years))
        annual_rent_growth = float(scenario.get("annual_rent_growth_pct") or s.default_annual_rent_growth_pct)
        vacancy_rate = float(scenario.get("vacancy_rate_pct") or s.default_vacancy_rate_pct)
        annual_maintenance_pct = float(scenario.get("annual_maintenance_pct") or s.default_annual_maintenance_pct)
        annual_tax = float(scenario.get("annual_property_tax") or property_input.taxes or 0.0)
        annual_insurance = float(scenario.get("annual_insurance") or property_input.insurance or 0.0)
        light_reno_budget = float(scenario.get("light_renovation_budget") or 0.0)
        demolition_cost = float(scenario.get("demolition_cost") or 30_000.0)
        new_construction_cost = float(scenario.get("new_construction_cost") or 0.0)
        raw_new_construction_sqft = scenario.get("new_construction_sqft")
        new_construction_sqft = int(raw_new_construction_sqft or 0)
        new_construction_beds = int(scenario.get("new_construction_beds") or property_input.beds or 3)
        new_construction_baths = float(scenario.get("new_construction_baths") or property_input.baths or 2.0)
        construction_months = int(scenario.get("construction_duration_months") or s.default_construction_duration_months)
        missing_inputs: list[str] = []
        if new_construction_cost <= 0:
            missing_inputs.append("new_construction_cost")
        if new_construction_sqft <= 0:
            missing_inputs.append("new_construction_sqft")
        if missing_inputs:
            return _blocked_result(
                module_name=self.name,
                status="missing_inputs",
                summary="Knockdown / new-build scenario needs both a construction budget and a target new-build size before Briarwood can model project economics.",
                missing_inputs=missing_inputs,
            )

        # --- Pull BCV and drift from prior_results ---
        if prior_results and "current_value" in prior_results:
            current_cv = get_current_value_payload(prior_results["current_value"])
        else:
            current_cv = get_current_value_payload(self.current_value_module.run(property_input))
        current_bcv = float(current_cv.briarwood_current_value or purchase_price or 0.0)
        if current_bcv <= 0:
            return _blocked_result(
                module_name=self.name,
                status="missing_anchor",
                summary="Knockdown / new-build scenario could not run because Briarwood could not establish a current value anchor.",
                missing_inputs=["purchase_price"],
            )

        # BBB base drift for appreciation
        base_drift = 0.03  # fallback
        if prior_results and "bull_base_bear" in prior_results:
            base_drift_raw = prior_results["bull_base_bear"].metrics.get("base_market_drift_pct")
            if isinstance(base_drift_raw, (int, float)):
                base_drift = float(base_drift_raw)
        # Clamp drift to reasonable range
        base_drift = max(-0.05, min(0.10, base_drift))

        # --- Monthly rent ---
        scenario_rent = scenario.get("monthly_rent")
        if scenario_rent:
            monthly_rent = float(scenario_rent)
        elif prior_results and "income_support" in prior_results:
            income = get_income_support_payload(prior_results["income_support"])
            monthly_rent = income.effective_monthly_rent or 0.0
        else:
            income_result = self.income_support_module.run(property_input)
            income = get_income_support_payload(income_result)
            monthly_rent = income.effective_monthly_rent or 0.0

        # --- Mortgage setup ---
        down_payment = purchase_price * down_payment_pct
        closing_costs = purchase_price * closing_costs_pct
        loan_amount = purchase_price - down_payment
        monthly_rate = mortgage_rate / 12.0
        n_payments = mortgage_term_years * 12
        if monthly_rate > 0:
            monthly_mortgage = loan_amount * monthly_rate * (1 + monthly_rate) ** n_payments / ((1 + monthly_rate) ** n_payments - 1)
        else:
            monthly_mortgage = loan_amount / n_payments
        annual_mortgage = monthly_mortgage * 12

        # --- Phase 1: Year-by-year cash flow ---
        year_by_year = []
        cumulative_cash_flow = 0.0
        mortgage_balance = loan_amount
        total_invested_upfront = down_payment + closing_costs + light_reno_budget

        for year in range(1, hold_years + 1):
            # Revenue
            gross_rent = monthly_rent * 12 * (1 + annual_rent_growth) ** (year - 1)
            effective_rent = gross_rent * (1 - vacancy_rate)

            # Expenses
            tax_this_year = annual_tax * (1 + s.default_tax_escalation_pct) ** (year - 1)
            insurance_this_year = annual_insurance * (1 + s.default_insurance_escalation_pct) ** (year - 1)
            prop_value_this_year = current_bcv * (1 + base_drift) ** year
            maintenance_this_year = prop_value_this_year * annual_maintenance_pct

            total_expenses = annual_mortgage + tax_this_year + insurance_this_year + maintenance_this_year
            net_cash_flow = effective_rent - total_expenses
            cumulative_cash_flow += net_cash_flow

            # Mortgage balance (amortization)
            # Track balance precisely via amortization
            yr_start_balance = mortgage_balance
            for _ in range(12):
                interest = mortgage_balance * monthly_rate
                principal = monthly_mortgage - interest
                mortgage_balance = max(0.0, mortgage_balance - principal)

            equity = prop_value_this_year - mortgage_balance
            burn_down_pct = (cumulative_cash_flow / total_invested_upfront * 100) if total_invested_upfront > 0 else 0.0

            year_by_year.append({
                "year": year,
                "gross_rent": round(gross_rent, 2),
                "effective_rent": round(effective_rent, 2),
                "annual_mortgage": round(annual_mortgage, 2),
                "tax": round(tax_this_year, 2),
                "insurance": round(insurance_this_year, 2),
                "maintenance": round(maintenance_this_year, 2),
                "total_expenses": round(total_expenses, 2),
                "net_cash_flow": round(net_cash_flow, 2),
                "cumulative_cash_flow": round(cumulative_cash_flow, 2),
                "property_value": round(prop_value_this_year, 2),
                "mortgage_balance": round(mortgage_balance, 2),
                "equity": round(equity, 2),
                "burn_down_pct": round(burn_down_pct, 1),
            })

        # Phase 1 summary
        total_gross_rent = sum(y["gross_rent"] for y in year_by_year)
        total_net_cash_flow = cumulative_cash_flow
        final_year = year_by_year[-1]
        mortgage_balance_at_teardown = final_year["mortgage_balance"]
        prop_value_at_teardown = final_year["property_value"]
        equity_at_teardown = final_year["equity"]
        burn_down_pct_final = final_year["burn_down_pct"]

        # Effective cost basis after rent offsets
        positive_rent_offset = max(0.0, total_net_cash_flow)
        effective_cost_basis = total_invested_upfront - positive_rent_offset

        # --- Phase 2: New construction value ---
        warnings: list[str] = []
        new_build_bcv = 0.0
        comp_basis_text = "No new construction comp data available."
        if new_construction_sqft > 0:
            new_build_input = dataclasses.replace(
                property_input,
                sqft=new_construction_sqft,
                beds=new_construction_beds,
                baths=new_construction_baths,
                condition_profile="renovated",  # "new" typically not in comps, use "renovated"
                capex_lane=None,
                repair_capex_budget=None,
                purchase_price=current_bcv,  # use current BCV as anchor for comp engine
                year_built=None,  # brand new
            )
            new_build_comp_result = self.comparable_sales_module.run(new_build_input)
            new_build_cv_result = self.current_value_module.run(new_build_input)
            new_build_cv = get_current_value_payload(new_build_cv_result)
            new_build_bcv = new_build_cv.briarwood_current_value

            # Extract comp basis text
            new_comps = getattr(new_build_comp_result.payload, "comps", None)
            if new_comps:
                prices = [c.adjusted_price for c in new_comps if getattr(c, "adjusted_price", None)]
                if prices:
                    ppsf_vals = [p / new_construction_sqft for p in prices]
                    avg_ppsf = sum(ppsf_vals) / len(ppsf_vals)
                    comp_basis_text = f"Based on {len(prices)} comparable(s) in {property_input.town} averaging ${avg_ppsf:,.0f}/sqft"
                    if new_build_cv_result.confidence < 0.50:
                        warnings.append("New construction comp data is thin — estimated new build value has wide uncertainty.")
            else:
                warnings.append("No comps found for new construction profile — new build value is estimated from market history only.")
        else:
            warnings.append("No new construction sqft specified — Phase 2 value estimate unavailable.")

        if new_build_bcv <= 0:
            return _blocked_result(
                module_name=self.name,
                status="insufficient_support",
                summary="Knockdown / new-build scenario could not estimate a credible completed-home value from the available comp support.",
                warnings=warnings or ["Add more new-construction or renovated comp support for this town and product type."],
            )

        # Apply market appreciation for hold period + construction
        total_appreciation_years = hold_years + construction_months / 12.0
        appreciation_factor = (1.0 + base_drift) ** total_appreciation_years
        future_new_construction_value = new_build_bcv * appreciation_factor

        # Phase 2 costs
        total_phase2_cost = demolition_cost + new_construction_cost

        # Lost rent during construction
        final_monthly_rent_at_teardown = monthly_rent * (1 + annual_rent_growth) ** hold_years
        lost_rent = final_monthly_rent_at_teardown * construction_months * (1 - vacancy_rate)

        # --- Full project economics ---
        total_cash_invested = (
            total_invested_upfront
            + total_phase2_cost
            + max(0.0, -total_net_cash_flow)  # any out-of-pocket carry shortfall
            + lost_rent
        )
        total_rental_income = total_gross_rent * (1 - vacancy_rate)
        net_equity_position = future_new_construction_value - mortgage_balance_at_teardown
        total_profit = net_equity_position - total_cash_invested
        base_cash_invested_for_roi = down_payment + closing_costs + light_reno_budget + total_phase2_cost
        total_roi_pct = (total_profit / base_cash_invested_for_roi * 100) if base_cash_invested_for_roi > 0 else 0.0
        total_years = hold_years + construction_months / 12.0
        annualized_roi_pct = total_roi_pct / total_years if total_years > 0 else 0.0

        # Confidence
        confidence = 0.65
        if monthly_rent <= 0:
            confidence -= 0.10
            warnings.append("No rent estimate available — Phase 1 cash flows are uncertain.")
        if new_build_bcv <= 0:
            confidence -= 0.15
            warnings.append("New construction value could not be estimated.")
        if new_construction_cost <= 0:
            confidence -= 0.10
            warnings.append("No construction cost provided — Phase 2 economics are incomplete.")
        confidence = max(confidence, self.settings.confidence_floor)

        # --- Narratives ---
        phase1_narrative = _phase1_narrative(
            hold_years=hold_years,
            total_gross_rent=total_gross_rent,
            total_net_cash_flow=total_net_cash_flow,
            burn_down_pct=burn_down_pct_final,
            total_invested_upfront=total_invested_upfront,
            prop_value_at_teardown=prop_value_at_teardown,
            mortgage_balance_at_teardown=mortgage_balance_at_teardown,
            equity_at_teardown=equity_at_teardown,
        )
        phase2_narrative = _phase2_narrative(
            demolition_cost=demolition_cost,
            new_construction_cost=new_construction_cost,
            new_construction_sqft=new_construction_sqft,
            new_construction_beds=new_construction_beds,
            new_construction_baths=new_construction_baths,
            construction_months=construction_months,
            town=property_input.town,
            future_new_construction_value=future_new_construction_value,
            comp_basis_text=comp_basis_text,
        )
        project_narrative = _project_narrative(
            purchase_price=purchase_price,
            hold_years=hold_years,
            total_years=total_years,
            future_new_construction_value=future_new_construction_value,
            total_cash_invested=total_cash_invested,
            total_profit=total_profit,
            annualized_roi_pct=annualized_roi_pct,
            total_net_cash_flow=total_net_cash_flow,
            equity_at_teardown=equity_at_teardown,
        )

        payload = {
            "enabled": True,
            "hold_years": hold_years,
            "total_project_timeline_years": round(total_years, 1),
            "base_drift_used": round(base_drift, 4),
            "phase1": {
                "total_gross_rent": round(total_gross_rent, 2),
                "total_net_cash_flow": round(total_net_cash_flow, 2),
                "burn_down_pct": round(burn_down_pct_final, 1),
                "effective_cost_basis": round(effective_cost_basis, 2),
                "equity_at_teardown": round(equity_at_teardown, 2),
                "mortgage_balance_at_teardown": round(mortgage_balance_at_teardown, 2),
                "estimated_property_value_at_teardown": round(prop_value_at_teardown, 2),
                "year_by_year": year_by_year,
            },
            "phase2": {
                "demolition_cost": round(demolition_cost, 2),
                "construction_cost": round(new_construction_cost, 2),
                "lost_rent_during_construction": round(lost_rent, 2),
                "total_phase2_cost": round(total_phase2_cost, 2),
                "estimated_new_construction_value": round(future_new_construction_value, 2),
                "comp_basis": comp_basis_text,
            },
            "project_totals": {
                "total_cash_invested": round(total_cash_invested, 2),
                "total_rental_income": round(total_rental_income, 2),
                "final_property_value": round(future_new_construction_value, 2),
                "final_mortgage_balance": round(mortgage_balance_at_teardown, 2),
                "net_equity_position": round(net_equity_position, 2),
                "total_profit": round(total_profit, 2),
                "total_roi_pct": round(total_roi_pct, 1),
                "annualized_roi_pct": round(annualized_roi_pct, 1),
            },
            "confidence": round(confidence, 2),
            "warnings": warnings,
            "phase1_narrative": phase1_narrative,
            "phase2_narrative": phase2_narrative,
            "project_narrative": project_narrative,
        }

        return ModuleResult(
            module_name=self.name,
            metrics={
                "enabled": True,
                "hold_years": hold_years,
                "burn_down_pct": round(burn_down_pct_final, 1),
                "total_net_cash_flow": round(total_net_cash_flow, 2),
                "equity_at_teardown": round(equity_at_teardown, 2),
                "future_new_construction_value": round(future_new_construction_value, 2),
                "total_profit": round(total_profit, 2),
                "annualized_roi_pct": round(annualized_roi_pct, 1),
                "total_cash_invested": round(total_cash_invested, 2),
            },
            score=min(100.0, max(0.0, 50.0 + annualized_roi_pct * 3)),
            confidence=round(confidence, 2),
            summary=project_narrative,
            payload=payload,
        )


def _blocked_result(
    *,
    module_name: str,
    status: str,
    summary: str,
    missing_inputs: list[str] | None = None,
    warnings: list[str] | None = None,
) -> ModuleResult:
    payload = {
        "enabled": False,
        "status": status,
        "summary": summary,
        "missing_inputs": list(missing_inputs or []),
        "warnings": list(warnings or []),
    }
    return ModuleResult(
        module_name=module_name,
        metrics={"enabled": False, "status": status},
        summary=summary,
        payload=payload,
    )


def _phase1_narrative(
    *,
    hold_years: int,
    total_gross_rent: float,
    total_net_cash_flow: float,
    burn_down_pct: float,
    total_invested_upfront: float,
    prop_value_at_teardown: float,
    mortgage_balance_at_teardown: float,
    equity_at_teardown: float,
) -> str:
    cash_flow_sign = "positive" if total_net_cash_flow >= 0 else "negative"
    return (
        f"Over a {hold_years}-year hold period, the property generates an estimated ${total_gross_rent:,.0f} in gross rental income. "
        f"After carrying costs (mortgage, taxes, insurance, maintenance), net cash flow totals approximately ${total_net_cash_flow:,.0f} — "
        f"{'burning down' if total_net_cash_flow >= 0 else 'representing a shortfall against'} "
        f"{abs(burn_down_pct):.0f}% of your initial ${total_invested_upfront:,.0f} cash investment. "
        f"By year {hold_years}, the property has appreciated to an estimated ${prop_value_at_teardown:,.0f} against a remaining mortgage of "
        f"${mortgage_balance_at_teardown:,.0f}, putting your equity position at approximately ${equity_at_teardown:,.0f}."
    )


def _phase2_narrative(
    *,
    demolition_cost: float,
    new_construction_cost: float,
    new_construction_sqft: int,
    new_construction_beds: int,
    new_construction_baths: float,
    construction_months: int,
    town: str,
    future_new_construction_value: float,
    comp_basis_text: str,
) -> str:
    total_build = demolition_cost + new_construction_cost
    return (
        f"Demolition and new construction of a {new_construction_sqft:,} sqft "
        f"{new_construction_beds}BR/{new_construction_baths:.0f}BA home is estimated at ${total_build:,.0f} total "
        f"(${demolition_cost:,.0f} demo + ${new_construction_cost:,.0f} build). "
        f"During the {construction_months}-month construction period, rental income is paused. "
        f"{comp_basis_text}. "
        f"Applying market appreciation to the completion date yields an estimated value of ${future_new_construction_value:,.0f}."
    )


def _project_narrative(
    *,
    purchase_price: float,
    hold_years: int,
    total_years: float,
    future_new_construction_value: float,
    total_cash_invested: float,
    total_profit: float,
    annualized_roi_pct: float,
    total_net_cash_flow: float,
    equity_at_teardown: float,
) -> str:
    economics_tone = "favorable" if annualized_roi_pct >= 5.0 else "thin" if annualized_roi_pct >= 2.0 else "unfavorable"
    if economics_tone == "unfavorable":
        return (
            f"The project economics are unfavorable. Buy at ${purchase_price:,.0f}, rent for {hold_years} years, tear down and build new — "
            f"yields an estimated final value of ${future_new_construction_value:,.0f} against total cash invested of "
            f"${total_cash_invested:,.0f} over {total_years:.1f} years. "
            f"Net profit: ${total_profit:,.0f}. Annualized ROI of {annualized_roi_pct:.1f}% does not adequately compensate for "
            f"execution risk and illiquidity over {total_years:.1f} years."
        )
    if economics_tone == "thin":
        return (
            f"The project economics are marginal. The full project — buy at ${purchase_price:,.0f}, rent for {hold_years} years, "
            f"tear down and build new — yields an estimated final value of ${future_new_construction_value:,.0f} against "
            f"total cash invested of ${total_cash_invested:,.0f} over {total_years:.1f} years. "
            f"Net profit: ${total_profit:,.0f} at an annualized ROI of {annualized_roi_pct:.1f}%."
        )
    return (
        f"The full project — buy at ${purchase_price:,.0f}, rent for {hold_years} years, tear down and build new — "
        f"yields an estimated final value of ${future_new_construction_value:,.0f} against total cash invested of "
        f"${total_cash_invested:,.0f} over {total_years:.1f} years. "
        f"That's a net profit of approximately ${total_profit:,.0f} and an annualized ROI of {annualized_roi_pct:.1f}%. "
        f"The rental phase offsets ${max(0,total_net_cash_flow):,.0f} in carrying costs and builds "
        f"${equity_at_teardown:,.0f} in equity before the construction phase begins."
    )
