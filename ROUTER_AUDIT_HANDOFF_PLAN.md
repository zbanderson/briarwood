# Router Classification Audit Handoff

**Status:** ✅ RESOLVED 2026-04-28 — Cycles 1-4 landed. See
[`DECISIONS.md`](DECISIONS.md) 2026-04-28 entry "Router classification
audit Cycle 1-4 landed" for the corpus, the prompt edits, the regex
widening, and the Guardrail Review section.
[`briarwood/agent/README_router.md`](briarwood/agent/README_router.md)
Changelog 2026-04-28 carries the contract-change notes.
[`ROADMAP.md`](ROADMAP.md) §4 Medium "Audit router classification
boundaries" + §10 Resolved Index row 9 mark closure.

**Size:** S–M (~half a day; ~3 cycles plus closeout).
**Source:** [`ROADMAP.md`](ROADMAP.md) §4 Medium *"2026-04-25 — Audit router
classification boundaries with real traffic"* — entry already lists 5+ known
misses; this is the corpus-driven prompt fix it was waiting on.

**Why now.**
- AI-Native Foundation Stage 1 just landed — `turn_traces` now writes one row
  per chat turn with `user_text` + `answer_type` + `confidence` + `reason`.
  The corpus is writing itself.
- 2026-04-28 live UI smoke surfaced two new misses (1 STRATEGY, 1 EDGE) that
  are pure prompt gaps — small, surgical, high signal.
- Cheap ROADMAP win between Stage 1 closeout and Stages 2–3 (which need a
  separate plan-mode pass and design decisions).

**Cross-references.**
- [`ROADMAP.md`](ROADMAP.md) §4 Medium "Audit router classification boundaries"
  (canonical scope; this handoff's body is the audit-against-corpus work the
  entry queued).
- [`briarwood/agent/router.py`](briarwood/agent/router.py) `_LLM_SYSTEM` at
  lines 169-226 — the source-of-truth prompt.
- [`briarwood/agent/README_router.md`](briarwood/agent/README_router.md) —
  module contract; updated in Cycle 4.
- [`tests/agent/test_router.py`](tests/agent/test_router.py) —
  `PromptContentRegressionTests` and `LLMClassifyTests` are the regression
  surfaces.

---

## Scope at a glance

Three sequenceable pieces:

1. **Corpus aggregation** (read-only) — collect every known miss into one
   structured table: text, current classification, expected classification,
   notes / source.
2. **`_LLM_SYSTEM` prompt updates** — close the gaps the corpus exposes.
   STRATEGY missing escalation phrasings, EDGE missing
   sensitivity/counterfactual phrasings, SEARCH missing "show me listings"
   phrasings.
3. **`_COMP_SET_RE` regex widening** in `briarwood/agent/dispatch.py` — per
   the existing ROADMAP entry's item 1.

Plus a closeout cycle: README changelog, ROADMAP closure, DECISIONS entry.

---

## Out of scope (deliberate)

- **No new `AnswerType` values.** All 14 buckets already exist; the gaps are
  about which phrasings map into each bucket.
- **No router-architecture changes.** LLM-first with two cache rules + price
  override — the design from 2026-04-24 is intentional and stays.
- **No user-type / persona work.** That's a separate Layer-1 product
  decision tracked under README_router.md "Open Product Decisions."
- **No retroactive re-classification of `turn_traces` rows.** The
  audit-against-corpus is forward-only — we update the prompt and verify
  with new traffic + LLM_CANNED tests.
- **No automated drift-detection job.** That's a Stage 3 dashboard item.

---

## Current state — what exists today

Read-only inventory before any changes.

### The prompt

[briarwood/agent/router.py:169-226](briarwood/agent/router.py#L169-L226) —
`_LLM_SYSTEM`. Defines 14 AnswerType buckets + IMPORTANT MAPPINGS +
counter-examples. Last updated 2026-04-25 (LOOKUP/DECISION price-analysis
fix per README changelog).

### The cache + override paths (out of scope, here for context)

- `_CACHE_RULES` at lines 114-139: greeting → CHITCHAT, compare/vs →
  COMPARISON. These are deliberate; not touched.
- What-if-price override at lines 371-400 (DECISION / RENT_LOOKUP /
  PROJECTION sub-routing). Deterministic; not touched.

### The contextualize-followup regex (Cycle 3 target)

`_COMP_SET_RE` lives in `briarwood/agent/dispatch.py` (per ROADMAP entry,
around lines 4536-4551). Today catches "comp set", "cma", "comps" with
specific context but NOT "show me the comps", "list the comps", "what are
the comps", "explain your comp choice", "Why were these comps chosen".

### The corpus

Sources, in order of authority:

1. **`turn_traces` table** (Stage 1 substrate, 2026-04-28 onward) —
   `SELECT user_text, answer_type, confidence, classification_reason FROM
   turn_traces` is the source of real traffic.
2. **ROADMAP §4 entry** — already lists 5 known misses with file paths and
   expected classifications.
3. **`tests/agent/test_router.py::LLM_CANNED`** — the canned-response test
   cases pin the current behavior for boundary phrasings.

---

## The cycles

### Cycle 1 — Corpus aggregation (read-only, ~30 min)

**Status:** Not started.

**Scope.** Produce a single in-PR-comment / in-DECISIONS table of every
known miss:

| # | Text | Current classification | Expected | Source |
|---|------|------------------------|----------|--------|
| 1 | "Why were these comps chosen?" (pinned property) | RESEARCH | EDGE | ROADMAP 2026-04-25 |
| 2 | "show me the comps" (pinned) | BROWSE | EDGE | ROADMAP 2026-04-26 |
| 3 | "Show me listings here" | BROWSE | SEARCH | ROADMAP 2026-04-25 |
| 4 | "Walk me through the recommended path" (pinned) | BROWSE | STRATEGY | turn_traces 2026-04-28 |
| 5 | "What would change your value view?" (pinned) | RISK | EDGE | turn_traces 2026-04-28 |

Plus 1-2 synthetic boundary cases per gap to harden tests:
- STRATEGY escalation: "what should I do here", "next move on this", "what's
  the play"
- EDGE sensitivity: "what assumption matters most", "how sensitive is your
  number", "what would shift this"
- SEARCH list-style: "list the comps", "what are the comps"

**Deliverable.** Inline table in this plan (above) + a paragraph in the
DECISIONS entry. No code change.

**Estimate:** 30 min. **Risk:** None — read-only.

---

### Cycle 2 — `_LLM_SYSTEM` prompt updates (~1 hour)

**Status:** Not started.

**Scope.** Targeted edits to [briarwood/agent/router.py:169-226](briarwood/agent/router.py#L169-L226):

1. **STRATEGY definition expansion** — add escalation phrasings to the
   bucket sentence ("recommended path", "walk me through the path", "what
   should I do here", "next move", "the play"). Today reads "best way to
   play, flip vs rent vs hold, primary or rental, what strategy."
2. **EDGE definition expansion** — add sensitivity/counterfactual
   phrasings. Today reads "where's the value, what's the edge, why is this
   a deal, value thesis, angle, catch." Add: "what would change your view",
   "what would shift the number", "how sensitive is X", "what assumption is
   load-bearing".
3. **SEARCH definition expansion** — add "show me listings here", "list the
   X" phrasings. Today reads "find other properties matching criteria
   (beds/price/distance/similar)." Add: list/show-imperative + plural
   artifact phrasings ("show me the listings", "list the properties").
4. **New IMPORTANT MAPPINGS lines:**
   - "'recommended path' / 'walk me through the path' / 'what should I do
     here' / 'next move' -> strategy (escalation from browse)"
   - "'what would change your view' / 'what would shift X' / 'how sensitive
     is X' / 'what assumption is load-bearing' -> edge (counterfactual /
     sensitivity)"
   - "'show me the listings' / 'list the X' (with X = listings/properties)
     -> search; with X = comps -> edge with comp_set follow-up"
5. **New counter-example pairs:**
   - "'what do you think of X' is BROWSE; 'walk me through the recommended
     path for X' is STRATEGY (escalation from first-read)"
   - "'what could go wrong with X' is RISK; 'what would change your view of
     X' is EDGE (sensitivity vs downside enumeration)"

**Tests** (extend `tests/agent/test_router.py`):

- `LLM_CANNED` additions covering each new mapping with structured-output
  responses pinning the new classifications.
- `PromptContentRegressionTests` — new tests pinning that the STRATEGY,
  EDGE, SEARCH bucket sentences contain the new phrasings (so a future
  prompt edit can't silently regress them).
- `PromptContentRegressionTests` — new tests pinning the new IMPORTANT
  MAPPINGS lines and counter-example pairs.

**Verification.**
- Unit: `pytest tests/agent/test_router.py` green, including new cases.
- Live (deferred to user, auto-mode): re-run today's three turns
  ("recommended path", "what would change your view"); each should now
  classify into STRATEGY / EDGE.

**Estimate:** 1 hour. **Risk:** Low. Prompt-only; no schema, no code path
change. Regression net is the existing 14+ router tests + new ones.

---

### Cycle 3 — `_COMP_SET_RE` regex widening (~30 min)

**Status:** Not started.

**Scope.** Extend the regex in
[`briarwood/agent/dispatch.py`](briarwood/agent/dispatch.py) (per ROADMAP
entry, around lines 4536-4551) to catch:

- "show me the comps" / "show me your comps"
- "list the comps" / "list your comps"
- "what are the comps"
- "explain your comp choice" / "explain the comp choice"
- "Why were these comps" / "why were the comps"

**Tests.** Extend `tests/agent/test_dispatch.py` — pin each new phrasing
rewrites to EDGE with `comp_set` follow-up. Add a synthetic boundary case
("the comparable sales market in Belmar" → still RESEARCH, NOT EDGE — the
"comparable sales market" is market context, not a comp-set followup).

**Verification.**
- Unit: `pytest tests/agent/test_dispatch.py` green.
- Live (deferred): "show me the comps" with a pinned property routes to
  EDGE comp_set follow-up.

**Estimate:** 30 min. **Risk:** Low. Regex is isolated; the fallback path
when it doesn't match is unchanged.

---

### Cycle 4 — Closeout (~30 min)

**Status:** Not started.

**Scope.**

- Update [`briarwood/agent/README_router.md`](briarwood/agent/README_router.md)
  Changelog with a 2026-04-28 entry: prompt expansion (STRATEGY / EDGE /
  SEARCH bucket sentences + 3 new IMPORTANT MAPPINGS + 2 new counter-example
  pairs). Note: contract change — STRATEGY now absorbs escalation
  phrasings that previously fell to BROWSE; EDGE now absorbs sensitivity
  phrasings that previously fell to RISK.
- Update [`ROADMAP.md`](ROADMAP.md) §4 *Audit router classification
  boundaries* — mark `✅` on heading and add `**Status:** RESOLVED
  2026-04-28` line per the convention adopted 2026-04-28. Add Resolved
  Index row 9.
- Update [`DECISIONS.md`](DECISIONS.md) with a 2026-04-28 entry: the
  corpus, the 5 prompt edits, the regex widening, the deferred items
  (any unaddressed boundary cases observed during Cycle 1 that we
  consciously didn't fix this pass).
- **No** ARCHITECTURE_CURRENT.md / TOOL_REGISTRY.md updates needed —
  router shape unchanged.

**Tests.** Existing 14 router tests + ~10 new from Cycles 2-3.

**Estimate:** 30 min. **Risk:** Low.

---

## Open design decisions

(Resolve at the start of the named cycle.)

1. **Corpus source — Stage 1 traces only, or include synthetic boundary
   cases?** Cycle 1. Recommendation: **both**. Today's `turn_traces` has 3
   rows; synthetic boundary cases harden tests against future regressions.
2. **Cycle 3 (regex widening) in or out of this handoff?** Recommendation:
   **in**. Same audit, same files, low risk, named in the existing ROADMAP
   entry as item 1.
3. **Update `data/agent_feedback/untracked.jsonl` consumer to surface
   misses?** Today the file accumulates low-confidence turns but no
   consumer queries it. Recommendation: **defer**. Out of scope; folds
   naturally into Stages 2-3 (feedback loop + dashboard).

---

## Failure semantics

- Tests must stay green at every cycle boundary. The pre-existing 16
  failures in the broader suite are unchanged baseline (verified
  2026-04-28).
- Prompt edits are reversible — each edit is a small string diff to
  `_LLM_SYSTEM`.
- The regex widening is additive — broader match, no narrower; risk is
  false-positive routing of NEW phrasings to EDGE that weren't intended.
  Mitigated by the synthetic boundary case ("the comparable sales market").

---

## ROADMAP closures (anticipated)

- §4 Medium *"2026-04-25 — Audit router classification boundaries with real
  traffic"* — RESOLVED on landing.
- The 4 sub-points listed in the entry's "When the audit-against-corpus
  work happens" section close together.
- The 6 sub-points (5 + 6) added 2026-04-28 close on Cycle 2's prompt
  expansion.
