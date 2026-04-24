# synthesis — Deterministic Structured Synthesizer (Legacy Path)

**Last Updated:** 2026-04-24
**Layer:** Unified Intelligence (Layer 3 — deterministic legacy path; runs whenever the claim-object wedge is off or falls through)
**Status:** STABLE (production default until `BRIARWOOD_CLAIMS_ENABLED` flips)

## Purpose

The `synthesis/` package is the deterministic, reproducible decision-builder that turns module results plus the Phase 4 interaction trace into a fully-populated `UnifiedIntelligenceOutput`. It runs whenever the routed pipeline produces a turn — every DECISION-tier turn either ends here (claim wedge off, or wedge fell back) or runs in parallel before the wedge takes over for rendering. The synthesizer is intentionally **LLM-free**: every field on the output is derivable from a module metric or a bridge record. The "trust gate" lives here too — when aggregate confidence is below `TRUST_FLOOR_ANY (0.40)`, the stance collapses to `CONDITIONAL` and the recommendation explicitly explains why no stronger stance is possible. Stronger stances (`STRONG_BUY`) require `TRUST_FLOOR_STRONG (0.70)`. The package's docstring at [briarwood/synthesis/__init__.py:1-6](__init__.py#L1-L6) frames the intent: "Replaces the LLM-pass-through synthesizer with a deterministic, reproducible decision-building pipeline. The LLM may translate the structured output into narrative (later), but it does not make the decision."

## Location

- **Package root:** [briarwood/synthesis/](.) — re-exports from [briarwood/synthesis/__init__.py](__init__.py).
- **Entry point:** [briarwood/synthesis/structured.py:34](structured.py#L34) — `build_unified_output(*, property_summary, parser_output, module_results, interaction_trace) -> dict[str, Any]`.
- **Stance classifier:** [briarwood/synthesis/structured.py:123](structured.py#L123) — `classify_decision_stance(*, value_position, trust_flags, bridges, aggregate_confidence)`.
- **Helpers also exported:** `compute_value_position` at [structured.py:235](structured.py#L235); `collect_trust_flags` at [structured.py:276](structured.py#L276).
- **Schemas (consumed):** `UnifiedIntelligenceOutput`, `ParserOutput`, `DecisionStance`, `DecisionType`, `AnalysisDepth` at [briarwood/routing_schema.py](../routing_schema.py).
- **Caller:** [briarwood/runner_routed.py:104-122](../runner_routed.py#L104-L122) — `_scoped_synthesizer` wraps `build_unified_output` and is passed as the `synthesizer` argument to `run_briarwood_analysis_with_artifacts`.
- **Tests:** [tests/synthesis/test_structured_synthesizer.py](../../tests/synthesis/test_structured_synthesizer.py).

## Role in the Six-Layer Architecture

- **This layer:** Unified Intelligence (Layer 3) — the deterministic counterpart to the claim-object pipeline. Per [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) Layer 3, the target-state Unified Intelligence is an LLM that asks "did we answer the intent?" — this synthesizer does NOT do that; it mechanically assembles the output. Both pipelines coexist behind the `BRIARWOOD_CLAIMS_ENABLED` feature flag.
- **Called by:** `_scoped_synthesizer` at [briarwood/runner_routed.py:104](../runner_routed.py#L104), which is passed into `run_briarwood_analysis_with_artifacts` at [briarwood/orchestrator.py](../orchestrator.py). The orchestrator invokes the synthesizer once per analysis after the executor has run all scoped modules.
- **Calls:** Internal helpers only. Reads `module_results` and `interaction_trace` dicts.
- **Returns to:** `run_briarwood_analysis_with_artifacts`, which surfaces the output to dispatch handlers as `artifacts["unified_output"]`.
- **Emits events:** None directly. The output is consumed downstream by `api/pipeline_adapter.py` to construct the `verdict` SSE event and other structured cards.

## LLM Usage

None. The synthesizer is entirely deterministic — pure Python, no LLM calls, no randomness. The package docstring at [__init__.py:1-6](__init__.py#L1-L6) makes the constraint explicit. Note that the **prose composer** that takes this output and renders text (`briarwood/agent/composer.py`) does call LLMs — but that is a separate layer.

## Inputs

| Input | Type | Source | Notes |
|-------|------|--------|-------|
| `property_summary` | `dict[str, Any]` | Orchestrator | Property facts surfaced for downstream cards. |
| `parser_output` | `dict[str, Any]` | Router | Validated against `ParserOutput` Pydantic model at [structured.py:48](structured.py#L48). |
| `module_results` | `dict[str, Any]` | Executor | Wraps each scoped module's output under `outputs[module_name]`. Unwrapped at [structured.py:737-744](structured.py#L737-L744). |
| `interaction_trace` | `dict[str, Any]` | Phase-4 bridges (e.g., `valuation_x_risk`, `valuation_x_town`, `scenario_x_risk`, `conflict_detector`) | Indexed at [structured.py:746-749](structured.py#L746-L749). |

## Outputs

`build_unified_output` returns a `dict[str, Any]` immediately validatable against `UnifiedIntelligenceOutput` at [briarwood/routing_schema.py](../routing_schema.py). The return type is a dict (not a model) so the orchestrator's normalization path keeps working — see docstring at [structured.py:43-46](structured.py#L43-L46).

Salient fields the synthesizer populates:

| Field | Built by | Notes |
|-------|----------|-------|
| `decision_stance` | `classify_decision_stance` at [structured.py:123](structured.py#L123) | One of `STRONG_BUY`, `PASS_UNLESS_CHANGES`, `EXECUTION_DEPENDENT`, `INTERESTING_BUT_FRAGILE`, `BUY_IF_PRICE_IMPROVES`, `CONDITIONAL`. |
| `decision_type` | Same | One of `DecisionType.BUY`, `PASS`, `MIXED`. |
| `recommendation` | Same | Single sentence stance summary. |
| `best_path` | Same | Single sentence next-action line. |
| `value_position` | `compute_value_position` at [structured.py:235](structured.py#L235) | `ask_price`, `all_in_basis`, `premium_discount_pct`, `basis_premium_pct`, etc. See "Hardcoded Values" for the contract distinction this function fixed. |
| `trust_flags` | `collect_trust_flags` at [structured.py:276](structured.py#L276) | Trust gaps surfaced for the trust gate. |
| `aggregate_confidence` | `_aggregate_confidence` at [structured.py:587](structured.py#L587) | Drives the trust gate. |
| `confidence_band` | `_confidence_band` at [structured.py:717](structured.py#L717) | String label. |
| `primary_value_source` | `_primary_value_source` at [structured.py:351](structured.py#L351) | See Known Rough Edges — falls through to `"unknown"` when none of the four signal paths fire. |
| `optionality_signal` | `_optionality_signal` at [structured.py:357](structured.py#L357) | Hidden-upside surface (multi-unit / ADU / repositioning). |
| `key_value_drivers` | `_key_value_drivers` at [structured.py:526](structured.py#L526) | Top reasons the value read landed where it did. |
| `key_risks` | `_key_risks` at [structured.py:557](structured.py#L557) | Risk flags consolidated for the verdict. |
| `what_must_be_true` | `_what_must_be_true` at [structured.py:468](structured.py#L468) | Conditions the thesis depends on (used by `EXECUTION_DEPENDENT`). |
| `next_checks` | `_next_checks` at [structured.py:484](structured.py#L484) | Specific verifications the user could run. |
| `trust_summary` | `_trust_summary` at [structured.py:637](structured.py#L637) | Surfaces aggregate confidence + flag count. |
| `why_this_stance` | `_why_this_stance` at [structured.py:655](structured.py#L655) | Per-stance reason narrative. |
| `what_changes_my_view` | `_what_changes_my_view` at [structured.py:694](structured.py#L694) | What evidence would shift the recommendation. |
| `recommended_next_run` | `_recommended_next_run` at [structured.py:727](structured.py#L727) | Optional follow-up suggestion. |

## Decision Stance Rule Order

From `classify_decision_stance` ([structured.py:131-227](structured.py#L131-L227)) — applied top to bottom; first match wins:

1. **Trust gate.** `aggregate_confidence < TRUST_FLOOR_ANY (0.40)` → `CONDITIONAL` + `MIXED`.
2. **Strong buy.** `price_gap <= -0.05` AND `aggregate_confidence >= TRUST_FLOOR_STRONG (0.70)` AND `fragility < 0.5` AND no conflicts.
3. **Price-too-high.** `price_gap > 0.05` → `PASS_UNLESS_CHANGES` + `PASS`.
4. **Execution-dependent.** `fragility >= 0.6` → `EXECUTION_DEPENDENT` + `MIXED`.
5. **Interesting but fragile.** `conflicts` exist OR `fragility >= 0.4` → `INTERESTING_BUT_FRAGILE` + `MIXED`.
6. **Buy if price improves.** `price_gap > -0.02` → `BUY_IF_PRICE_IMPROVES` + `MIXED`.
7. **Fallback.** `PASS_UNLESS_CHANGES` + `MIXED`.

`price_gap = premium_discount_pct - (band_upper - extra_discount_demanded_pct)`. `band_upper` defaults to `0.07` ([structured.py:147-149](structured.py#L147-L149)) when the `valuation_x_town` bridge does not provide it.

## Dependencies on Other Modules

- **Schema dependency on:** `briarwood/routing_schema.py` (`UnifiedIntelligenceOutput`, `ParserOutput`, `DecisionStance`, `DecisionType`, `AnalysisDepth`). Any change to those models is a breaking change here.
- **Bridge contract:** Reads bridge dicts under specific keys: `valuation_x_risk`, `valuation_x_town`, `scenario_x_risk`, `conflict_detector` (and others). Bridges live in `briarwood/interactions/` — schema changes there are silent breakages here.
- **Imports:** Only `briarwood.routing_schema`. No LLM client, no network.
- **Coupled to:** `briarwood/runner_routed.py:_scoped_synthesizer` (caller), `api/pipeline_adapter.py` (consumer of the output dict).

## Invariants

- Never raises on a valid `parser_output`. `ParserOutput.model_validate` propagates Pydantic `ValidationError` if the dict is malformed.
- Returns a `dict`, not a Pydantic model — explicit choice (see `build_unified_output` docstring).
- Every output field traces back to either a module metric or a bridge record (the package-level invariant; not enforced by tests but stated in the package docstring at [structured.py:1-11](structured.py#L1-L11)).
- The trust-gate thresholds (`TRUST_FLOOR_STRONG = 0.70`, `TRUST_FLOOR_ANY = 0.40`) are module-level constants at [structured.py:27-28](structured.py#L27-L28).
- `decision_stance` is always set; `_unwrap_outputs` and `_index_bridges` always return dicts (possibly empty).
- Deterministic per input — no LLM, no randomness, no system clock.
- Never mutates its inputs.

## State & Side Effects

- **Stateless package:** all functions are pure (modulo Pydantic validation side effects).
- **Writes to disk:** no.
- **Modifies session:** no.
- **Safe to call concurrently:** yes.

## Example Call

```python
from briarwood.synthesis import build_unified_output

unified = build_unified_output(
    property_summary={"address": "...", "town": "Montclair", "state": "NJ", ...},
    parser_output={"intent": "decision", "depth": "full", ...},
    module_results={"outputs": {"valuation": {...}, "carry_cost": {...}, "risk_model": {...}, ...}},
    interaction_trace={"bridges": {"valuation_x_risk": {...}, "scenario_x_risk": {...}, ...}},
)
# unified["decision_stance"]      ∈ {"STRONG_BUY","PASS_UNLESS_CHANGES","EXECUTION_DEPENDENT",
#                                    "INTERESTING_BUT_FRAGILE","BUY_IF_PRICE_IMPROVES","CONDITIONAL"}
# unified["aggregate_confidence"] ∈ [0, 1]
# unified["primary_value_source"] ∈ {strategy/...} or "unknown" — see Known Rough Edges
```

## Known Rough Edges

- **`primary_value_source` returns `"unknown"` on typical fixtures.** [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) Known Rough Edges (`NEW-V-005`) — `_primary_value_source` at [structured.py:351-355](structured.py#L351-L355) checks four signal paths (strategy, mispricing, carry offset, scenario); when none fire it falls through to `"unknown"`. Downstream cards in the web layer gate on `!== "unknown"`. Whether the bridge fires is fixture-dependent.
- **`all_in_basis` is computed but the UI does not render it.** [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) Known Rough Edges (`AUDIT_REPORT.md` F-003). The synthesizer at [structured.py:252-265](structured.py#L252-L265) computes `all_in_basis`; it is declared on the verdict event at `api/pipeline_adapter.py:615` and projected at `:658`; it appears in the TypeScript event type at `web/src/lib/chat/events.ts:152`. No card in `web/src/components/chat/` reads it.
- **`compute_value_position` carries a contract-distinction docstring** at [structured.py:241-249](structured.py#L241-L249). The old contract aliased `ask_price = all_in_basis`; today they are distinct: `ask_price = listing ask`, `all_in_basis = purchase_price + capex`, `ask_premium_pct` is a legacy alias for `premium_discount_pct`, and `basis_premium_pct` is the all-in-basis vs fair-value framing. Callers reading any of these names should consult the docstring.
- **No fallback on scoped-registry failure (cross-cutting).** [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) Known Rough Edges (`AUDIT_REPORT.md` F-004) — the orchestrator raises `RoutingError` rather than falling back; the synthesizer never sees that failure mode.
- **Trust-gate constants are module-level**, not config. Adjusting `TRUST_FLOOR_STRONG` or `TRUST_FLOOR_ANY` is a code change.

## Open Product Decisions

(Pulled from [GAP_ANALYSIS.md](../../GAP_ANALYSIS.md) Layer 3 and adjacent; no synthesis-specific decisions invented here.)

- **Promote to LLM-driven Layer 3 ("did we answer the intent?")?** The current synthesizer is mechanical — the gap analysis describes a target where an LLM judges intent satisfaction and either re-orchestrates or surfaces a "I can't answer this well because X" response. Whether the LLM step replaces this synthesizer or sits in front of it is undecided.
- **Sunset path for the legacy synthesizer.** Once `BRIARWOOD_CLAIMS_ENABLED` is default-on for all archetypes, this path becomes a fallback only. When (and how) to remove it is open.

## Changelog

### 2026-04-24
- Initial README created.
