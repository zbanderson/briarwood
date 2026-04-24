# carry_cost — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`carry_cost` computes the ownership-carry economics of holding a property: monthly mortgage principal + interest, pro-rated taxes and insurance, HOA, a maintenance reserve, gross and effective monthly rent, and the derived underwriting ratios (cap rate, DSCR, cash-on-cash return, monthly cash flow). Call this tool whenever the user's intent involves any form of "what does it cost to own?" or when downstream modules need a monthly-cost anchor to stress-test resale, margin, hold-to-rent, or income-offset paths. It is the single entry every financing-aware module depends on.

## Location

- **Entry point:** [briarwood/modules/carry_cost.py:12](carry_cost.py#L12) — `run_carry_cost(context: ExecutionContext) -> dict[str, object]`
- **Registry entry:** [briarwood/execution/registry.py:63-70](../execution/registry.py#L63-L70) — `ModuleSpec(name="carry_cost", depends_on=[], required_context_keys=["property_data", "assumptions"], runner=run_carry_cost)`
- **Schema definitions:** `ModulePayload` at [briarwood/routing_schema.py](../routing_schema.py); internal `ValuationOutput` at [briarwood/schemas.py](../schemas.py); shared payload helpers at [briarwood/modules/scoped_common.py:48-99](scoped_common.py#L48-L99)

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `DECISION` — called whenever ownership economics matter to the verdict.
- `RENT_LOOKUP` — called to derive rent-vs-carry ratios.
- `STRATEGY` — called for hold-to-rent, flip, and owner-occupancy paths.
- `PROJECTION` — called as a dependency of `resale_scenario` and `opportunity_cost` for forward cost projection.
- Not called for: `SEARCH`, `BROWSE`, `CHITCHAT`, `VISUALIZE` (no cost computation required).

## Inputs

Inputs arrive through [briarwood/execution/context.py](../execution/context.py)'s `ExecutionContext`. The runner normalizes them into a `PropertyInput` via `build_property_input_from_context` at [briarwood/modules/scoped_common.py](scoped_common.py).

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.property_data.purchase_price` | `float` | yes | user / listing facts | Falls back to `0.0` if absent; triggers fallback payload. |
| `context.property_data.taxes` | `float` (annual) | yes | user / listing facts | Required field per error branch at [carry_cost.py:26](carry_cost.py#L26). |
| `context.property_data.insurance` | `float` (annual) | yes | user / listing facts | Required field per error branch at [carry_cost.py:26](carry_cost.py#L26). |
| `context.property_data.down_payment_percent` | `float` (0-1) | recommended | `assumptions` | Defaults via `_normalize_percent`; missing value degrades `financing_complete` to false. |
| `context.property_data.interest_rate` | `float` (0-1) | recommended | `assumptions` | Same as above. |
| `context.property_data.loan_term_years` | `int` | optional | `assumptions` | Falls back to `DEFAULT_COST_VALUATION_SETTINGS.loan_term_years`. |
| `context.property_data.monthly_hoa` | `float` | optional | listing facts | Treated as 0.0 when absent. |
| `context.property_data.sqft`, `town`, `state` | mixed | optional | listing facts | Used for rent estimation + vacancy/maintenance heuristics. |
| `context.property_data.estimated_monthly_rent` | `float` | optional | user / listing facts | If absent, `RentContextAgent` estimates rent. |
| `context.assumptions` | `dict` | yes (may be empty) | router / session | Registry requires the key to exist; contents are consumed through `property_data` by the legacy module. |

## Outputs

The runner returns `ModulePayload.model_dump()`. The salient fields sit under the payload's `output` section (from the wrapped `ValuationOutput`):

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `monthly_mortgage_payment` | `float` | USD / month | Principal + interest; null when financing facts missing. |
| `monthly_taxes` | `float` | USD / month | Annual taxes ÷ 12. |
| `monthly_insurance` | `float` | USD / month | Annual insurance ÷ 12. |
| `monthly_hoa` | `float` | USD / month | Zero when absent. |
| `monthly_maintenance_reserve` | `float` | USD / month | Age/condition-adjusted per `_resolve_maintenance_reserve` in [ownership_economics.py](ownership_economics.py). |
| `monthly_total_cost` | `float` | USD / month | PITI + HOA + maintenance reserve. |
| `monthly_cash_flow` | `float` | USD / month | Effective monthly rent − `monthly_total_cost`. |
| `annual_noi` | `float \| None` | USD / year | Effective annual rent − operating expenses (excludes debt service). |
| `cap_rate` | `float \| None` | fraction | `annual_noi / purchase_price`. |
| `gross_yield` | `float \| None` | fraction | `annual_gross_rent / purchase_price`. |
| `dscr` | `float \| None` | ratio | `annual_noi / annual_debt_service`. |
| `cash_on_cash_return` | `float \| None` | fraction | `annual_cash_flow / down_payment_amount`. |
| `effective_monthly_rent` | `float \| None` | USD / month | After vacancy adjustment. |
| `rent_source_type` | `str` | enum | `"actual" \| "estimated" \| "fallback" \| "unavailable"`. |
| `carrying_cost_complete` | `bool` | — | True when taxes/insurance/HOA are all present. |
| `financing_complete` | `bool` | — | True when down payment, interest rate, and loan term are all present. |
| `loan_amount`, `down_payment_amount` | `float \| None` | USD | Null when `purchase_price` missing. |
| `confidence` | `float` | 0.0-1.0 | From `ModulePayload`; reflects input completeness and rent-source strength. |
| `summary` | `str` | prose | One- to two-sentence human-readable summary built inside `OwnershipEconomicsModule._build_summary`. |
| `warnings` | `list[str]` | — | Populated by fallback path when `purchase_price` / `taxes` / `insurance` are missing. |

## Dependencies

- **Requires (inputs):** none among scoped modules — `depends_on=[]` at [registry.py:65](../execution/registry.py#L65). The only hard inputs are `property_data` (user-supplied facts) and an `assumptions` dict.
- **Benefits from (optional):** `property_summary` (accepted via `optional_context_keys`).
- **Calls internally:** `OwnershipEconomicsModule` at [briarwood/modules/ownership_economics.py:13](ownership_economics.py#L13). That module in turn calls `IncomeAgent` at [briarwood/agents/income/](../agents/income/) and `RentContextAgent` at [briarwood/agents/rent_context/](../agents/rent_context/).
- **Must not run concurrently with:** none.
- **Downstream scoped consumers:** `resale_scenario` ([registry.py:88-94](../execution/registry.py#L88-L94)), `hold_to_rent` ([registry.py:111-118](../execution/registry.py#L111-L118)), `margin_sensitivity` ([registry.py:135-142](../execution/registry.py#L135-L142)), `unit_income_offset` ([registry.py:143-150](../execution/registry.py#L143-L150)).

## Invariants

- Never raises. All exceptions are caught at [carry_cost.py:28-36](carry_cost.py#L28-L36) and replaced with a fallback `ModulePayload` whose `warnings` carry the exception type + message.
- When `purchase_price`, `taxes`, or `insurance` are missing, the returned payload marks those fields in `required_fields` and lowers `confidence` accordingly; the caller gets a structured degraded response, not an error.
- `rent_source_type` is never null; missing rent produces `"unavailable"`.
- `confidence` is in `[0.0, 1.0]`.
- The runner is deterministic for fixed inputs — no LLM calls, no randomness.
- `carrying_cost_complete` and `financing_complete` are the honest completeness flags; do not compute separate heuristics from partial outputs.

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.carry_cost import run_carry_cost

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={
        "purchase_price": 850_000,
        "taxes": 14_400,
        "insurance": 2_100,
        "monthly_hoa": 0,
        "down_payment_percent": 0.20,
        "interest_rate": 0.0675,
        "loan_term_years": 30,
        "sqft": 2_100,
        "town": "Montclair",
        "state": "NJ",
    },
    assumptions={},
)

payload = run_carry_cost(context)
# payload["output"]["monthly_mortgage_payment"] ≈ 4_410
# payload["output"]["monthly_total_cost"]     ≈ 5_800
# payload["output"]["dscr"]                   ≈ ...
# payload["confidence"]                       ∈ [0, 1]
# payload["warnings"]                         == []  # when all required fields present
```

## Hardcoded Values & TODOs

- Default `loan_term_years`, vacancy floor, and maintenance percent are set in [briarwood/settings.py](../settings.py) `DEFAULT_COST_VALUATION_SETTINGS`. Individual overrides (coastal/seasonal vacancy; age/condition maintenance) are resolved inline in [ownership_economics.py:43-50](ownership_economics.py#L43-L50) with comments labelled "Bug 7" and "Bug 8".
- Rent fallbacks come from `RentContextAgent`; no explicit per-geography table in this module.
- No `$400/sqft` replacement-cost constant is used in the scoped carry path — despite the wrapped class being named `OwnershipEconomicsModule`. See Notes.

## Blockers for Tool Use

- None. This module is callable in isolation via `run_carry_cost(context)` with a populated `ExecutionContext`.

## Notes

- **Historic naming mismatch (resolved).** The legacy module was originally named `CostValuationModule` in `briarwood/modules/cost_valuation.py`, and its config dataclass remains `CostValuationSettings` in [briarwood/settings.py](../settings.py). The class and file were renamed to `OwnershipEconomicsModule` / `ownership_economics.py` in Handoff 2a Piece 5A (2026-04-24). The settings dataclass was left unrenamed to minimize diff; a future sweep may align it. The `run()` implementation at [ownership_economics.py:27-140](ownership_economics.py#L27-L140) computes ownership-carry economics (PITI + HOA + maintenance + NOI + DSCR + cap rate) through `IncomeAgent` and `RentContextAgent` — no replacement-cost or land-value fields are produced, matching the new name.
- Historical audit finding (`ARCHITECTURE_CURRENT.md` Known Rough Edges → Hardcoded values): the `$400/sqft` replacement-cost default cited in `decision_model/scoring_config.py` is NOT consumed by `carry_cost` — this module does not call into the scoring config.
- Tests exercising carry_cost outputs live in [tests/test_execution_v2.py](../../tests/test_execution_v2.py), [tests/test_runner_routed.py](../../tests/test_runner_routed.py), [tests/test_modules.py](../../tests/test_modules.py), and [tests/modules/_phase2_fixtures.py](../../tests/modules/_phase2_fixtures.py).
- This module is latency-cheap: `IncomeAgent` and `RentContextAgent` are file-backed / deterministic under production fixtures.
- No LLM calls; no cost.

## Changelog

### 2026-04-24
- Initial README created.
- Rename: the wrapped legacy class `CostValuationModule` in `briarwood/modules/cost_valuation.py` was renamed to `OwnershipEconomicsModule` in `briarwood/modules/ownership_economics.py` via `git mv` (Handoff 2a Piece 5A). `carry_cost.py` import path and `assumptions_used["legacy_module"]` string updated to match. Contract unchanged. See [DECISIONS.md](../../DECISIONS.md) 2026-04-24 "CostValuationModule is misnamed."
