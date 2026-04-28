# Router Quality Round 2 Handoff

**Status:** ✅ RESOLVED 2026-04-28 — Cycles 1-3 landed. See
[`DECISIONS.md`](DECISIONS.md) 2026-04-28 entry "Router Quality
Round 2 landed" and
[`briarwood/agent/README_router.md`](briarwood/agent/README_router.md)
Changelog 2026-04-28 (Round 2). [`ROADMAP.md`](ROADMAP.md) §4 Medium
both entries marked ✅; §10 Resolved Index rows 10 and 11.
**Size:** M (~30-45 min LLM time; ~3 cycles + closeout).
**Source:** Two §4 Medium ROADMAP entries filed 2026-04-28 during the
2026-04-28 router-audit smoke:
- "Router LLM `confidence=0.6` cap collapses classifier signal"
- "`parse_overrides` bare-renovation false-positive shoehorns scenario
  requests into DECISION"

Both are guardrail-blocks-quality findings per
`project_llm_guardrails.md`. Both are surgical and live in the same
neighborhood (`briarwood/agent/router.py` + `briarwood/agent/overrides.py`).
Pairing them as one handoff keeps the closeout convention and amortizes
the test-update cost.

**Why now.** Stage 3 dashboard plans depend on a real `confidence`
signal in `turn_traces.confidence` (today every LLM-classified row is
0.6). Override-parser miss is small but produced a user-visible bad
turn (DECISION verdict-with-comparison response for "Run renovation
scenarios"). Both fixes unblock downstream and are fast.

**Cross-references.**
- [`ROADMAP.md`](ROADMAP.md) §4 Medium "Router LLM `confidence=0.6` cap..."
- [`ROADMAP.md`](ROADMAP.md) §4 Medium "`parse_overrides` bare-renovation..."
- [`DECISIONS.md`](DECISIONS.md) 2026-04-28 entry "Router classification
  audit Cycle 1-4 landed" — Guardrail Review section that flagged #1.
- [`ROUTER_AUDIT_HANDOFF_PLAN.md`](ROUTER_AUDIT_HANDOFF_PLAN.md) — the
  closed Round 1 audit; this is its operational follow-on.

---

## Scope at a glance

Two sequenceable fixes:

1. **Plumb LLM-emitted confidence into `RouterDecision.confidence`.**
   Add a `confidence: float` field to `RouterClassification`, update
   `_LLM_SYSTEM` to ask for a 0-1 score, replace the hardcoded
   `confidence=0.6` at `router.py:407` with the LLM's value.
2. **Tighten `parse_overrides` so bare-renovation isn't an override +
   widen `_PROJECTION_OVERRIDE_HINT_RE`.** Layer A in `overrides.py`,
   Layer B in `router.py`. Both layers ship together for defense in
   depth.

Plus a closeout cycle.

---

## Out of scope (deliberate)

- **No new `AnswerType` values.**
- **No router-architecture changes** beyond schema + plumbing.
- **No retroactive backfill of `turn_traces.confidence`.** New rows
  carry the LLM's value forward; old rows stay at 0.6 (they're wrong
  but unfixable without re-classification, which we deliberately don't
  do).
- **No changes to the cache-rule or what-if-price-override branches'
  confidence values.** The `0.9 / 0.75 / 0.7` constants for cache
  hits / rent-override / projection-override / DECISION-default stay
  — those paths are deterministic and don't have an LLM signal.

---

## Cycles

### Cycle 1 — Plumb LLM confidence (~10-15 min)

**Status:** Not started.

**Scope.**
1. Add `confidence: float` to `RouterClassification` Pydantic schema at
   [briarwood/agent/router.py:245-258](briarwood/agent/router.py#L245-L258).
   Constrain via Pydantic `Field(ge=0.0, le=1.0)`.
2. Update `_LLM_SYSTEM` to ask for the score: append a sentence like
   *"Also include `confidence`: a float in [0, 1] reflecting how
   certain you are about the classification (1.0 = unambiguous, 0.5 =
   could be one of 2-3 buckets, <0.4 = genuinely don't know)."*
3. In `classify` at
   [router.py:402-412](briarwood/agent/router.py#L402-L412), replace
   `confidence=0.6` with `confidence=max(llm_result.confidence, 0.4)`.
   Floor at 0.4 prevents the LLM's noise from flipping into the 0.3
   default-fallback bucket; document the floor as a deliberate
   guardrail.

**Tests** in `tests/agent/test_router.py`:
- New `LLMClassifyTests::test_llm_confidence_flows_through_to_decision`
  — `ScriptedLLM` returns `confidence=0.92`, assert
  `decision.confidence == 0.92`.
- New `test_llm_confidence_floor_at_0_4` — `ScriptedLLM` returns
  `confidence=0.1`, assert `decision.confidence == 0.4`.
- New `PromptContentRegressionTests::test_prompt_asks_for_confidence`
  — pin the new prompt sentence so a future edit can't silently
  remove it.
- Update `ScriptedLLM.complete_structured` to emit `confidence=0.7`
  by default (or whatever the existing `LLM_CANNED` cases need to
  pass) so the existing test corpus keeps working.

**Risk.** Low. Schema is additive; fallback to `max(..., 0.4)` floor
covers LLM emission outliers.

---

### Cycle 2 — Tighten overrides + widen projection hint (~10-15 min)

**Status:** Not started.

**Scope (Layer A, `overrides.py`).** In `parse_overrides` at
[briarwood/agent/overrides.py:111-147](briarwood/agent/overrides.py#L111-L147),
make `mode = "renovated"` conditional on at least one of:
- a price was extracted (`overrides.get("ask_price") is not None`)
- a capex was extracted (`overrides.get("repair_capex_budget") is
  not None`)
- the text carries a value/worth/price question token
  (regex sketch: `\b(value|worth|priced?|cost|sell for|fair price|
  underwrite|good deal)\b`)

If none of those: `_RENO_RE` matched but it's narrative-only, not an
override. Drop the `mode` set.

**Scope (Layer B, `router.py`).** Widen `_PROJECTION_OVERRIDE_HINT_RE`
at [router.py:239-242](briarwood/agent/router.py#L239-L242) to also
match scenario / renovation imperatives:
```python
_PROJECTION_OVERRIDE_HINT_RE = re.compile(
    r"\b(arv|after repair value|sell it for|resale|"
    r"turn around and sell|flip|"
    r"renovation scenarios?|run scenarios?|scenario)\b",
    re.IGNORECASE,
)
```
Defense in depth: even if Layer A misses, the override path now
correctly routes to PROJECTION instead of falling through to DECISION.

**Tests:**
- New `tests/test_overrides.py` (or extend the existing overrides
  test file — find via grep) cases:
  - `parse_overrides("Run renovation scenarios")` → `{}` (no override).
  - `parse_overrides("renovate me")` → `{}` (mode-only, no price /
    capex / value question).
  - `parse_overrides("what's the value if renovated")` → `{"mode":
    "renovated"}` (paired with value question).
  - `parse_overrides("buy it at 1.3M and renovate")` → contains both
    `ask_price` and `mode` (paired with price).
- Extend `tests/agent/test_router.py`:
  - New `LLM_CANNED` entry: `("Run renovation scenarios",
    AnswerType.PROJECTION)` — pinning the LLM-classify path now
    works end-to-end (no spurious override short-circuit).
  - New `PrecedenceTests::test_bare_renovation_is_not_a_what_if_override`
    — assert `classify("Run renovation scenarios", client=None)`
    does NOT return `reason="what-if price override"`.
  - New `PrecedenceTests::test_renovation_scenarios_with_override_routes_to_projection`
    — `classify("if I bought at 1.3M and ran renovation scenarios",
    client=None)` → PROJECTION (Layer B sub-routes correctly).

**Risk.** Medium-low. `parse_overrides` has downstream consumers
(`inputs_with_overrides`, the various callers in dispatch). Tightening
at parse-time means callers that relied on `mode="renovated"` from
bare "renovation" will lose it. Mitigation: grep for callers and
verify each handles `mode` being absent gracefully (Cycle 2 step 0).

---

### Cycle 3 — Closeout (~5-10 min)

**Status:** Not started.

**Scope.**
- Update [`briarwood/agent/README_router.md`](briarwood/agent/README_router.md)
  Changelog with a 2026-04-28 entry: confidence plumbing + override
  tightening. Note contract change — `RouterDecision.confidence` now
  carries the LLM's signal instead of a hardcoded 0.6 for
  LLM-classified turns.
- Mark both ROADMAP entries `✅ RESOLVED 2026-04-28` with
  `**Status:**` line. Add §10 Resolved Index rows 10 and 11.
- Add `DECISIONS.md` entry summarizing the two fixes + a brief
  Guardrail Review note (per the standing
  `project_llm_guardrails.md` directive — the two fixes themselves
  are the guardrail loosening, so the section is shorter this round).
- No `ARCHITECTURE_CURRENT.md` updates needed; router shape unchanged
  at the documented level.

**Tests.** Existing 23 router tests + new ones from Cycles 1-2.

**Risk.** None — docs only.

---

## Open design decisions

(Resolve at start of named cycle.)

1. **Confidence floor value.** Cycle 1. Recommendation:
   `max(llm.confidence, 0.4)` — keeps every LLM-classified row above
   the 0.3 default-fallback threshold while preserving signal above
   that. Alternative: no floor (raw LLM value flows through). Floor
   safer.
2. **`parse_overrides` Layer A approach.** Cycle 2. Recommendation:
   tighten in-place (gate the `mode` set on price/capex/value-question
   presence). Alternative: split into `overrides` vs `narrative_hints`
   channels — bigger contract change, defer.
3. **Layer A grep pass for downstream `mode`-only consumers.** Cycle 2
   prerequisite. Recommendation: grep for `\.get\("mode"\)` and
   `overrides\["mode"\]` across the codebase before tightening; verify
   each consumer handles `mode` being absent gracefully. If any
   callers rely on bare-renovation setting mode, surface as a
   secondary finding, don't auto-fix.

---

## Verification

- Unit: new tests + existing 23 router tests + existing dispatch
  comp-set tests stay green.
- Live (deferred to user, auto-mode): re-run "Run renovation
  scenarios" — should now classify as PROJECTION.
  `turn_traces.confidence` for new chats should vary (no longer
  every row at 0.6).

---

## ROADMAP closures (anticipated)

- §4 Medium "Router LLM `confidence=0.6` cap collapses classifier
  signal" → ✅ RESOLVED.
- §4 Medium "`parse_overrides` bare-renovation false-positive
  shoehorns scenario requests into DECISION" → ✅ RESOLVED.
- §10 Resolved Index rows 10 and 11.
