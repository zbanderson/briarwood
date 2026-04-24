# Briarwood — Follow-Ups

Actionable code-level items surfaced during Handoff 1 README writing that were left untouched per Handoff 1's "no application code changes" rule. Each entry should be triagable: state the issue, the affected file paths, the impact, and a suggested approach. Resolve in subsequent handoffs.

Distinct from [DECISIONS.md](DECISIONS.md) (which captures product/architectural decisions and audit-doc drift) and [GAP_ANALYSIS.md](GAP_ANALYSIS.md) (which captures architectural gaps relative to the six-layer target). This file is for "go fix this" items that are smaller in scope than either of those.

---

## 2026-04-24 — Editor / synthesis threshold duplication has no mechanical guard

**Severity:** Medium — silent drift hazard for every claim-object-pipeline run.

**Files:**
- [briarwood/editor/checks.py:14-20](briarwood/editor/checks.py#L14-L20) — `VALUE_FIND_THRESHOLD_PCT`, `OVERPRICED_THRESHOLD_PCT`, `SMALL_SAMPLE_THRESHOLD`.
- [briarwood/claims/synthesis/verdict_with_comparison.py](briarwood/claims/synthesis/verdict_with_comparison.py) — synthesizer counterparts.

**Issue:** The editor's check thresholds must agree with the synthesizer's; the editor explicitly does not import from synthesis to avoid a layering violation. If either side drifts, the editor either rejects valid claims or passes invalid ones — silently. The hazard is named in the comment at [checks.py:18-20](briarwood/editor/checks.py#L18-L20) but unenforced.

**Suggested fix:** Two options:
1. Move all three constants into a neutral module (e.g., `briarwood/claims/thresholds.py`) and import from both sides.
2. Add a test in `tests/editor/` that imports both modules and asserts equality of the three constants. Cheap, catches drift on every CI run.

---

## 2026-04-24 — Add a shared LLM call ledger

**Severity:** Medium — hard to improve prompts or model routing without comparable telemetry across call sites.

**Files:**
- [briarwood/agent/llm.py](briarwood/agent/llm.py)
- [briarwood/agent/composer.py](briarwood/agent/composer.py)
- [briarwood/agent/router.py](briarwood/agent/router.py)
- [briarwood/representation/agent.py](briarwood/representation/agent.py)
- [briarwood/claims/representation/verdict_with_comparison.py](briarwood/claims/representation/verdict_with_comparison.py)
- [briarwood/local_intelligence/adapters.py](briarwood/local_intelligence/adapters.py)

**Issue:** Router fallback turns, composer verifier reports, representation planning, claim prose, and local-intelligence extraction all expose different levels of LLM observability. There is no single inspectable record of prompt tier, provider/model, structured-vs-prose mode, latency, token/cost estimate, fallback reason, verifier outcome, or whether the user saw LLM prose versus deterministic fallback.

**Suggested fix:** Add a lightweight append-only LLM ledger, likely under `data/agent_feedback/` or `data/learning/`, with one JSONL event per LLM attempt. Record metadata only by default; gate full prompt/response capture behind an explicit debug env var to avoid leaking sensitive payloads. Thread it through the shared `LLMClient` boundary first, then add call-site context (`router`, `decision_summary`, `representation_plan`, etc.).

---

## 2026-04-24 — Extend router classification with telemetry-first `user_type`

**Severity:** Medium — blocks user-type-conditioned orchestration, Value Scout triggering, and tone adaptation.

**Files:**
- [briarwood/agent/router.py](briarwood/agent/router.py)
- [briarwood/agent/session.py](briarwood/agent/session.py)
- [briarwood/interactions/](briarwood/interactions/)
- [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py)
- [tests/agent/test_router.py](tests/agent/test_router.py)

**Issue:** `GAP_ANALYSIS.md` Layer 1 calls for intent plus user-type classification, but `RouterDecision` only carries `answer_type`. Existing interaction/persona hints accumulate separately and do not feed routing or dispatch. A cold-start misclassification could shape the session incorrectly if treated as authoritative too early.

**Suggested fix:** Add a conservative `user_type` field with values chosen by product decision before implementation. Recommended first pass: `unknown`/`pending` as the default plus low-confidence telemetry, not hard routing behavior. Plumb the field through `RouterDecision` and `Session`, collect examples, and only later let dispatch or Value Scout branch on it.

---

## 2026-04-24 — Prototype Layer 3 intent-satisfaction LLM in shadow mode

**Severity:** Medium — current synthesis can produce grounded prose while still failing to answer the user's actual intent.

**Files:**
- [briarwood/synthesis/structured.py](briarwood/synthesis/structured.py)
- [briarwood/claims/synthesis/verdict_with_comparison.py](briarwood/claims/synthesis/verdict_with_comparison.py)
- [briarwood/agent/composer.py](briarwood/agent/composer.py)
- [briarwood/routing_schema.py](briarwood/routing_schema.py)

**Issue:** The deterministic synthesizers assemble valid outputs, and the composer verifies numbers, but nothing asks whether the module set actually satisfied the routed intent. `GAP_ANALYSIS.md` Layer 3 names the missing LLM step: read the intent contract plus module outputs, then declare intent satisfied or identify missing facts/tools.

**Suggested fix:** Add a structured-output shadow evaluator that returns `{intent_satisfied, missing_facts, suggested_tools, explanation}` without changing user-visible behavior. Log results to the LLM ledger. Do not let it trigger re-orchestration until the evaluator has golden tests and retry bounds.

---

## 2026-04-24 — Route local-intelligence extraction through shared LLM boundary

**Severity:** Medium — the only LLM-backed extraction path sits outside shared provider, budget, retry, and telemetry conventions.

**Files:**
- [briarwood/local_intelligence/adapters.py](briarwood/local_intelligence/adapters.py)
- [briarwood/local_intelligence/config.py](briarwood/local_intelligence/config.py)
- [briarwood/agent/llm.py](briarwood/agent/llm.py)
- [briarwood/cost_guard.py](briarwood/cost_guard.py)
- [TOOL_REGISTRY.md](TOOL_REGISTRY.md)

**Issue:** `OpenAILocalIntelligenceExtractor` uses a direct OpenAI client and schema call. That gives it strong extraction structure, but it bypasses the central `LLMClient` abstraction and does not share the same provider routing, budget accounting, retry behavior, or call ledger that router/composer/representation should use.

**Suggested fix:** Either adapt `OpenAILocalIntelligenceExtractor` to accept/use the shared structured `LLMClient`, or explicitly create a local-intelligence-specific LLM adapter that still records cost/telemetry through the shared surfaces. Keep the existing validation pipeline intact.

---

## 2026-04-24 — Broaden Representation Agent triggering beyond the claims flag

**Severity:** Low — Layer 4 mostly exists, but only part of the app benefits from it.

**Files:**
- [briarwood/representation/agent.py](briarwood/representation/agent.py)
- [api/pipeline_adapter.py](api/pipeline_adapter.py)
- [briarwood/agent/dispatch.py](briarwood/agent/dispatch.py)
- [briarwood/feature_flags.py](briarwood/feature_flags.py)

**Issue:** `GAP_ANALYSIS.md` Layer 4 says the Representation Agent substantially exists, but its use is still gated around the claim-object path while legacy synthesis emits charts directly from handlers. That means chart selection quality and LLM-vs-deterministic fallback behavior differ by execution path.

**Suggested fix:** Add a feature-flagged path that runs the Representation Agent for ordinary decision-tier turns after `UnifiedIntelligenceOutput` and module views are available. Start in shadow mode: compare selected charts to the currently emitted events, log mismatches, and only switch rendering once chart coverage is stable.
