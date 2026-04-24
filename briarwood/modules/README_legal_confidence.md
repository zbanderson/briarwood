# legal_confidence — Scoped Registry Model

**Last Updated:** 2026-04-24
**Status:** READY
**Registry:** scoped

## Purpose

`legal_confidence` surfaces how much structured evidence Briarwood has around zoning, additional-unit signals, and local-document coverage, so synthesis and the risk model can calibrate their confidence when an extra-unit or use-permission question is in play. It is **not** a legal classifier — the module's docstring at [legal_confidence.py:13-15](legal_confidence.py#L13-L15) states explicitly "This wrapper does not perform legal classification." Call this tool whenever the user's intent touches accessory dwelling units, multi-unit feasibility, zoning overrides, or any use-permission question that could be undercut by thin local-document evidence.

## Location

- **Entry point:** [briarwood/modules/legal_confidence.py:10](legal_confidence.py#L10) — `run_legal_confidence(context: ExecutionContext) -> dict[str, object]`.
- **Registry entry:** [briarwood/execution/registry.py:151-158](../execution/registry.py#L151-L158) — `ModuleSpec(name="legal_confidence", depends_on=[], required_context_keys=["property_data"], runner=run_legal_confidence)`.
- **Schema definitions:** outer `ModulePayload` at [briarwood/routing_schema.py:316](../routing_schema.py#L316); this module does not use the legacy-result helper — it constructs the payload directly at [legal_confidence.py:28-73](legal_confidence.py#L28-L73).

## Intent Fit

Per `AnswerType` values at [briarwood/agent/router.py:40-54](../agent/router.py#L40-L54):

- `RISK` — called when the user's question centers on use-permission risk.
- `DECISION` — called as a confidence anchor for `risk_model` ([registry.py:72-78](../execution/registry.py#L72-L78) shows `risk_model` depends on `valuation`; `legal_confidence` is consumed at [risk_model.py](risk_model.py) as an input reference even though the registry does not list it as a direct `depends_on`).
- `STRATEGY` — called for investor paths that depend on extra-unit or redevelopment rights.
- `EDGE` — called for edge questions about teardown, subdivision, or non-conforming use.
- Not called for: `SEARCH`, `BROWSE`, `CHITCHAT`, pure `VISUALIZE`.

## Inputs

Inputs arrive via `ExecutionContext` ([briarwood/execution/context.py:8](../execution/context.py#L8)) and are normalized to a `PropertyInput` by `build_property_input_from_context` at [briarwood/modules/scoped_common.py:26](scoped_common.py#L26).

| Field | Type | Required | Source | Notes |
|-------|------|----------|--------|-------|
| `context.property_data.zone_flags` | `dict` | optional | listing / town data | Keys like `multi_unit_allowed`, etc.; absence drops confidence. |
| `context.property_data.has_back_house` | `bool` | optional | listing facts | Signals accessory structure presence. |
| `context.property_data.adu_type` | `str \| None` | optional | listing facts | E.g., `"attached_adu"`, `"detached_adu"`. |
| `context.property_data.additional_units` | `list` | optional | listing facts | Each entry represents a countable unit. |
| `context.property_data.local_documents` | `list[dict]` | optional | town/local-intelligence intake | Planning, zoning, HOA documents. Gate for running `LocalIntelligenceModule` (see [legal_confidence.py:20-24](legal_confidence.py#L20-L24)). |
| `context.property_data` (other facts) | `dict` | required | — | Needed by `PropertyDataQualityModule` to produce a completeness score. |
| `context.market_context` | `dict` | optional | router / session | Accepted via `optional_context_keys`. |
| `context.prior_outputs` | `dict` | optional | executor | Accepted via `optional_context_keys`. |

## Outputs

`run_legal_confidence` returns `ModulePayload.model_dump()`. Salient fields in the payload's `data` dict (all constructed inline at [legal_confidence.py:28-73](legal_confidence.py#L28-L73)):

| Field | Type | Range / Units | Notes |
|-------|------|---------------|-------|
| `module_name` | `str` | — | `"legal_confidence"`. |
| `summary` | `str` | prose | One of four branches in `_build_summary` at [legal_confidence.py:77-92](legal_confidence.py#L77-L92) based on accessory / zone / local-document signal combos. |
| `legality_evidence.has_accessory_signal` | `bool` | — | True when `has_back_house`, `adu_type`, or any `additional_units` is present. |
| `legality_evidence.adu_type` | `str \| None` | — | Passthrough. |
| `legality_evidence.has_back_house` | `bool \| None` | — | Passthrough. |
| `legality_evidence.additional_unit_count` | `int` | — | `len(additional_units or [])`. |
| `legality_evidence.zone_flags` | `dict` | — | Passthrough of `property_input.zone_flags`. |
| `legality_evidence.local_document_count` | `int` | — | `len(local_documents or [])`. |
| `legality_evidence.multi_unit_allowed` | `bool \| None` | — | `zone_flags.get("multi_unit_allowed")`. |
| `data_quality.summary` | `str` | prose | From `PropertyDataQualityModule`. |
| `data_quality.metrics` | `dict` | mixed | From `PropertyDataQualityModule`. |
| `data_quality.confidence` | `float` | 0-1 | From `PropertyDataQualityModule`. |
| `local_intelligence` | `dict \| None` | — | Present only when `property_input.local_documents` is non-empty (gate at [legal_confidence.py:20-24](legal_confidence.py#L20-L24)). Contains `summary`, `metrics`, `confidence`. |
| `confidence` | `float` | 0-1 | Outer `ModulePayload.confidence`; computed by `_legal_evidence_confidence` at [legal_confidence.py:95-110](legal_confidence.py#L95-L110). |
| `warnings` | `list[str]` | — | From `_legal_warnings` at [legal_confidence.py:113-123](legal_confidence.py#L113-L123); populated when accessory signals exist without zone flags or without local documents. |
| `assumptions_used.legacy_module` | `str` | — | `"PropertyDataQualityModule"`. |
| `assumptions_used.supporting_module` | `str \| None` | — | `"LocalIntelligenceModule"` when available, else `None`. |

**Note on output shape:** [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) and [TOOL_REGISTRY.md](../../TOOL_REGISTRY.md) describe this module as producing `permission_flags: list[str]` and `restriction_flags: list[str]`. Those fields do NOT exist in the current output. See [DECISIONS.md](../../DECISIONS.md) entry "legal_confidence output schema mismatch in audit docs" (2026-04-24).

## Dependencies

- **Requires (inputs):** none among scoped modules — `depends_on=[]` at [registry.py:153](../execution/registry.py#L153). Only `property_data` is required.
- **Benefits from (optional):** `market_context`, `prior_outputs`.
- **Calls internally:** `PropertyDataQualityModule` at [briarwood/modules/property_data_quality.py](property_data_quality.py) (always); `LocalIntelligenceModule` at [briarwood/modules/local_intelligence.py](local_intelligence.py) (only when `local_documents` are present).
- **Must not run concurrently with:** none.
- **Downstream scoped consumers:** consumed by `risk_model` for legal-confidence gating (per [ARCHITECTURE_CURRENT.md](../../ARCHITECTURE_CURRENT.md) → `risk_model` row: "Adjusts confidence for overpricing and legal uncertainty"). The registry does not list `legal_confidence` in `risk_model.depends_on` — risk_model reads it via `prior_outputs` at runtime.

## Invariants

- **Never raises on valid input.** The body is wrapped in a single `try/except` that catches any internal exception (e.g., from `PropertyDataQualityModule` or `LocalIntelligenceModule`) and returns a canonical fallback payload via `module_payload_from_error` at [briarwood/modules/scoped_common.py:114](scoped_common.py#L114) — `mode="fallback"`, `confidence=0.08`, `warnings=["Legal-confidence fallback: {ExceptionClass}: {message}"]`. See the 2026-04-24 "Scoped wrapper error contract" entry in [DECISIONS.md](../../DECISIONS.md).
- `confidence` is always rounded to 4 decimals at [legal_confidence.py:110](legal_confidence.py#L110).
- `confidence` is floored at 0.55 when `has_zone_flags` is true, and capped at 0.65 when `has_accessory_signal` is false — see [legal_confidence.py:106-109](legal_confidence.py#L106-L109). The floor precedes the cap in evaluation order; when both conditions apply, the floor wins first then the cap clamps down.
- `confidence` = `min(data_quality_confidence, local_confidence)` before the floor/cap (at [legal_confidence.py:102-105](legal_confidence.py#L102-L105)).
- `local_intelligence` is `None` when `property_input.local_documents` is empty or missing — not present with null sub-fields.
- Deterministic for a fixed input — the module does not call an LLM. (`LocalIntelligenceModule` may internally call an LLM-backed extractor; see its own README once written.)
- Never mutates its inputs.

## Example Call

```python
from briarwood.execution.context import ExecutionContext
from briarwood.modules.legal_confidence import run_legal_confidence

context = ExecutionContext(
    property_id="NJ-0000001",
    property_data={
        "sqft": 2_100,
        "beds": 4,
        "baths": 2.5,
        "town": "Montclair",
        "state": "NJ",
        "has_back_house": True,
        "adu_type": "detached_adu",
        "zone_flags": {"multi_unit_allowed": True},
        "local_documents": [],
    },
)

payload = run_legal_confidence(context)
# payload["data"]["legality_evidence"]["has_accessory_signal"] == True
# payload["data"]["legality_evidence"]["multi_unit_allowed"]   == True
# payload["data"]["local_intelligence"]                        is None
# payload["confidence"]                                        >= 0.55   (floor)
# payload["warnings"] includes "No local planning or zoning documents were provided..."
```

## Hardcoded Values & TODOs

- Confidence floor `0.55` when `has_zone_flags` is true, at [legal_confidence.py:107](legal_confidence.py#L107).
- Confidence cap `0.65` when `has_accessory_signal` is false, at [legal_confidence.py:109](legal_confidence.py#L109).
- Four-branch prose template in `_build_summary` at [legal_confidence.py:77-92](legal_confidence.py#L77-L92) — no localization or geography-specific variant.
- Warnings are emitted only for two specific accessory-signal-minus-evidence conditions at [legal_confidence.py:119-122](legal_confidence.py#L119-L122). Any other legal edge case is silent.

## Blockers for Tool Use

- None for normal invocation. Internal exceptions degrade to a canonical fallback payload (see Invariants) rather than propagating.

## Notes

- **Output schema contradicts the audit docs.** See [DECISIONS.md](../../DECISIONS.md) 2026-04-24 entry. The audit describes a classifier (`permission_flags`, `restriction_flags`); the code is an evidence-coverage signal. When the audit docs are reconciled, this module should be re-described as "Zoning / ADU evidence coverage, not a legal classifier."
- Tests exercising `run_legal_confidence` include [tests/modules/test_legal_confidence_isolated.py](../../tests/modules/test_legal_confidence_isolated.py).
- `LocalIntelligenceModule` is the only code path reached from this module that can incur LLM cost. It is gated on `property_input.local_documents` — when documents are absent, no LLM call is made from this module.

## Changelog

### 2026-04-24
- Initial README created.
- Contract change: wrapped body in `try/except` and migrated to the canonical error contract. Internal exceptions now return a `module_payload_from_error` fallback (`mode="fallback"`, `confidence=0.08`) rather than propagating. See [DECISIONS.md](../../DECISIONS.md) 2026-04-24 "Scoped wrapper error contract."
