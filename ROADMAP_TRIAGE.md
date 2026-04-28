# Briarwood Roadmap Triage — No-Drop Index

Created 2026-04-28 as a scan-friendly companion to `ROADMAP.md`. `ROADMAP.md` remains the canonical source of truth; this file is an index for planning, sizing, and impact-label assignment.

## No-Drop Rules

- No roadmap item is deleted, silently merged, or dropped.
- Every entry below points back to its canonical `ROADMAP.md` section.
- Resolved items stay visible under **Resolved / Closed Items**.
- Ambiguous items go to **Unclassified / Needs Owner Decision** instead of being forced into a bucket.
- If `ROADMAP.md` changes, update this file in the same handoff.

## Impact Labels

- `LLM & Synthesis` — prompts, LLM boundaries, structured/prose synthesis, verifier behavior, LLM telemetry surfaces.
- `Output & Presentation` — response shape, cards, representation selection, presentation quality, user-facing answer format.
- `Property Analysis` — valuation, comps, rent, CMA, scoring, geospatial/property data, semantic model correctness.
- `Routing & Orchestration` — intent routing, dispatch, execution planning, module sets, cache/concurrency behavior.
- `Data, Persistence & Feedback` — storage, ledgers, feedback capture/read-back, admin analytics, model-accuracy loops.
- `Scout` — Value Scout / Phase 4b apex insight work.
- `UI & Charts` — web chat rendering, chart specs/components, SSE chart behavior, chart-library migration.
- `Docs, Process & Repo Health` — documentation drift, tests known broken, repo process, audit hygiene.
- `Unclassified / Needs Owner Decision` — parked items requiring owner classification.

## High-Level Buckets

### LLM & Synthesis

| Roadmap ref | Item | Size | Status |
|---|---|---:|---|
| §3.3 | Semantic-model audit umbrella | L | Open |
| §3.3.2 | Synthesis confidence floors are invisible to the LLM prompts | ? | Open |
| §3.3.6 | Numeric-grounding rule in synthesizer is informal | ? | Open |
| §4 High | Layer 3 LLM synthesizer: prose from full `UnifiedIntelligenceOutput` | M | Open |
| §4 Medium | Prototype Layer 3 intent-satisfaction LLM in shadow mode | M | Open |
| §4 Medium | Route local-intelligence extraction through shared LLM boundary | S | Open |

### Output & Presentation

| Roadmap ref | Item | Size | Status |
|---|---|---:|---|
| §2 | Phase 2 — Output Quality | S | Tail cleanup open |
| §2 | Phase 3 — Presentation | ? | Awaiting design decision |
| §3.5 | Phase 4c — BROWSE summary card rebuild | XL | Parked |
| §4 Low | Broaden Representation Agent triggering beyond the claims flag | M | Open |

### Property Analysis

| Roadmap ref | Item | Size | Status |
|---|---|---:|---|
| §2 | Phase 4a — CMA Quality | ? | Resolved |
| §3.3.1 | Pricing-view bands disagree with verdict-label thresholds | ? | Open |
| §3.3.3 | Orphan signature metrics: Forward Value Gap & Optionality Score | ? | Open |
| §3.3.4 | BCV component-count drift in prompts and prior docs | ? | Open |
| §3.3.5 | Rent has three sources with no reconciliation carrier | ? | Open |
| §3.3.7 | `scarcity_score` naming collision across two modules | ? | Open |
| §3.3.8 | Comp-scoring weights duplicated across two layers | ? | Open |
| §3.3.9 | `pricing_view` is a user-facing categorical output with no confidence | ? | Open |
| §3.3.10 | `valuation` vs `current_value` module naming collision | ? | Open |
| §3.3.11 | `decision_model/scoring.py` looks legacy — verify before delete | ? | Open |
| §4 Medium | Zillow URL-intake address normalization regression | S | Open |
| §4 Medium | Renovation premium pass-through to live comps | M | Open |
| §4 Medium | Plumb subject lat/lon through `summary` for per-row CMA distance filtering | M | Open |
| §4 Medium | `get_cma` Step 2 still open (cache-miss audit) | S | Open |

### Routing & Orchestration

| Roadmap ref | Item | Size | Status |
|---|---|---:|---|
| §4 High | Consolidate chat-tier execution: one plan per turn, intent-keyed module set | L | Open |
| §4 Medium | Property resolver matches wrong slug | S | Open |
| §4 Medium | Module-result caching at the per-tool boundary is leaky | S | Open |
| §4 Medium | `in_active_context` is not safe under concurrent thread-pool callers | S | Open |
| §4 Medium | Extend router classification with telemetry-first `user_type` | M | Open |
| §4 Low | Strip unreachable defensive fallback in `_classification_user_type` | S | Open |

### Data, Persistence & Feedback

| Roadmap ref | Item | Size | Status |
|---|---|---:|---|
| §3.1 | AI-Native Foundation umbrella | XL | In progress by stage |
| §3.1 Stage 1 | Persist Every Action | M | Resolved |
| §3.1 Stage 2 | Close The User-Feedback Loop | M | Open |
| §3.1 Stage 3 | Business-Facing Dashboard | M-L | Open |
| §3.1 Stage 4 | Close The Model-Accuracy Loop | M-L | Open |
| §4 Medium | `data/llm_calls.jsonl` rotation/compaction policy | S | Open |
| §4 Medium | Stage 3 dashboard analytic-query sketches | S | Open |

### Scout

| Roadmap ref | Item | Size | Status |
|---|---|---:|---|
| §3.2 | Phase 4b — Scout buildout | XL | Open |

### UI & Charts

| Roadmap ref | Item | Size | Status |
|---|---|---:|---|
| §3.4 | Chart visual quality push | L | Open |
| §3.4.1 | `cma_positioning` chip + `feeds_fair_value` dead architecture | ? | Open |
| §3.4.2 | `value_opportunity` y-axis label renders as a vertical stack | ? | Open |
| §3.4.3 | `cma_positioning` chart-prose alignment | ? | Open |
| §3.4.4 | Live SSE rendering requires a page reload | ? | Open |
| §3.4.5 | `cma_positioning` source-view drift in non-BROWSE handlers | ? | Partial defensive fix; follow-on open |
| §3.4.6 | Other chart umbrella items | ? | Open |
| §3.4.7 | Evaluate React-native charting library to replace Plotly-iframe | L | Open |

### Docs, Process & Repo Health

| Roadmap ref | Item | Size | Status |
|---|---|---:|---|
| §4 Medium | `docs/current_docs_index.md` does not list authoritative orientation docs | S | Open |
| §4 Low | Pre-existing failure: `StructuredSynthesizerTests::test_interaction_trace_attached` | S | Open |
| §4 Low | Pre-existing failure: browse stream ordering test | S | Open |
| §5 | `ARCHITECTURE_CURRENT.md` / `TOOL_REGISTRY.md` keep drifting | ? | Open process question |
| §5 | Decision sessions should grep-verify caller claims in real time | ? | Open |
| §7 | Resolve sizing gaps | ? | Open |
| §7 | Phase 2 status discrepancy | ? | Open |
| §9 | Phase 3 Open Design Decision #7 sizing gap | ? | Open |

## Closing Out / Sequence / Parking Lot Coverage

| Roadmap ref | Item | Impact | Size | Status |
|---|---|---|---:|---|
| §1 Step 1 | Phase 4a Cycle 6 — close the CMA handoff | Property Analysis | ? | Resolved |
| §1 Step 2 | AI-Native Foundation Stage 1 — persistence | Data, Persistence & Feedback | M | Resolved |
| §1 Step 3 | AI-Native Foundation Stages 2-3 | Data, Persistence & Feedback | M / M-L | Open |
| §1 Step 4 | Phase 4b — Scout buildout | Scout | XL | Open |
| §1 Step 5 | AI-Native Foundation Stage 4 | Data, Persistence & Feedback | M-L | Open |
| §1 Step 6 | Phase 4c — BROWSE summary card rebuild | Output & Presentation | XL | Parked |
| §6 | Parking Lot | Unclassified / Needs Owner Decision | ? | No entries currently listed under the heading |

## Resolved / Closed Items

Resolved items remain in their original roadmap sections and in §10 Resolved Index. They are included here so closed work does not disappear during triage.

| Roadmap ref | Item | Impact | Size | Closed in |
|---|---|---|---:|---|
| §3.1 Stage 1 | Persist Every Action | Data, Persistence & Feedback | M | PERSISTENCE_HANDOFF_PLAN.md Cycles 1-4 |
| §4 Medium | Audit router classification boundaries with real traffic | Routing & Orchestration | M | ROUTER_AUDIT_HANDOFF_PLAN.md Cycles 1-4 |
| §4 Medium | Router LLM `confidence=0.6` cap collapses classifier signal | Routing & Orchestration | S | ROUTER_QUALITY_ROUND2_HANDOFF_PLAN.md Cycle 1 |
| §4 Medium | `parse_overrides` bare-renovation false-positive | Routing & Orchestration | S | ROUTER_QUALITY_ROUND2_HANDOFF_PLAN.md Cycle 2 |
| §4 Low | `presentation_advisor` bypasses shared LLM observability ledger | LLM & Synthesis | ? | Phase 2 Cycle 6 cleanup item 1 |
| §4 Low | Retire the ad-hoc `ComparableSalesModule()` graft | Property Analysis | S | CMA Phase 4a Cycle 6 |
| §5 | `base_comp_selector.py` / 15% sqft tolerance drift in audit docs | Docs, Process & Repo Health | ? | CMA Phase 4a Cycle 6 |

## Absorbed / Dedup Coverage

These entries are not separate implementation work because `ROADMAP.md` §8 records them as absorbed into canonical locations. They are listed here to preserve traceability.

| Dedup # | Absorbed phrasing | Surviving location |
|---:|---|---|
| 1 | Add a shared LLM call ledger | §3.1 AI-Native Stage 1 |
| 2 | Editor / synthesis threshold duplication has no mechanical guard | §3.3.1 Semantic Audit pricing-view item |
| 3 | Two comp engines with divergent quality | §2 Phase 4a Cycle 6 |
| 4 | Live SSE rendering requires page reload | §3.4.4 Chart umbrella |
| 5 | `cma_positioning` chart-prose alignment | §3.4.3 Chart umbrella |
| 6 | `cma_positioning` context-only chip + `feeds_fair_value` | §3.4.1 Chart umbrella |
| 7 | `value_opportunity` y-axis vertical stack | §3.4.2 Chart umbrella |
| 8 | `cma_positioning` source-view drift | §3.4.5 Chart umbrella |

## Unclassified / Needs Owner Decision

No currently listed roadmap item required parking during this pass. If a future entry cannot be classified confidently, put it here with the exact original heading and the owner question before assigning a subsystem label.
