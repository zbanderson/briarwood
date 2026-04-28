# AI-Native Foundation Stage 4 - Close The Model-Accuracy Loop

**Status:** Implementation substrate landed 2026-04-28. Outcome ingestion,
backfill, `model_alignment`, receiver hooks, and analyzer reporting are
implemented. Real outcome data still needs to be supplied and run through the
backfill before human tuning candidates can be reviewed against live rows.
**Size:** M-L (~1-2 handoffs; recommended 5 cycles + closeout).
**Sequence position:** Step 5 of [`ROADMAP.md`](ROADMAP.md) section 1. Phase 4b
Scout is complete as of 2026-04-28; Phase 4c BROWSE summary rebuild stays
after this stage.

**Principle.** "Closed feedback loops" - [`design_doc.md`](design_doc.md)
section 3.4 and Loop 1 (Model Accuracy) in section 7. A model-accuracy loop is closed
only when ground-truth outcomes are ingested, connected back to the module
calls that made a prediction, read by an analyzer/report, and used by a
human to decide prompt/weight changes.

**Why now.**
- Stage 1 persists `turn_traces`, `messages` metrics, and
  `data/llm_calls.jsonl`.
- Stage 2 persists response-quality feedback and mirrors analyzer records
  into `data/learning/intelligence_feedback.jsonl`.
- Stage 3 gives the owner a read-side admin surface.
- Phase 4b Scout is now shipped and will benefit from better module
  accuracy diagnostics, but Stage 4 must not pull in Phase 4c UI work.

**Preflight conclusion.** The Phase 4b Scout Cycle 5-7 code/docs batch was
committed first as `c8b6b0d` (`feat(scout): land Cycle 5-7 closeout`).
Stage 4 planning is now a separate change boundary.

**Cross-references.**
- [`ROADMAP.md`](ROADMAP.md) section 3.1 Stage 4, section 1 sequence step 5.
- [`DECISIONS.md`](DECISIONS.md) 2026-04-27 AI-Native Foundation sequencing
  entry and 2026-04-28 Stage 1-3 + Scout closeout entries.
- [`design_doc.md`](design_doc.md) section 3.4 and section 7.
- [`PERSISTENCE_HANDOFF_PLAN.md`](PERSISTENCE_HANDOFF_PLAN.md),
  [`FEEDBACK_LOOP_HANDOFF_PLAN.md`](FEEDBACK_LOOP_HANDOFF_PLAN.md),
  [`DASHBOARD_HANDOFF_PLAN.md`](DASHBOARD_HANDOFF_PLAN.md).

---

## Scope at a glance

Five additive pieces plus closeout:

1. **Ground-truth outcome ingestion.** Add an outcome source for actual
   sale/outcome data, starting with actual sale price for analyzed
   properties. Manual CSV/JSON is the v1 source; public-record automation
   can follow later.
2. **One-shot backfill.** Attach outcome data to historical
   `data/learning/intelligence_feedback.jsonl` rows and persisted
   `turn_traces` / feedback-linked rows where a property match is possible.
3. **Real module feedback receivers.** Implement `receive_feedback()` for
   `current_value`, `valuation`, and `comparable_sales` first.
4. **Persist module confidence-vs-outcome alignment.** Add a
   `model_alignment` table to `data/web/conversations.db` and write one row
   per scored module call.
5. **Analyzer report.** Surface high-confidence module calls that
   underperform actual outcomes and emit human-reviewed prompt/weight tuning
   candidates only.
6. **Closeout.** Focused tests, docs reconciliation, and an explicit pause
   before any recalibration changes.

All work is additive. No auto-tuning. No frontend redesign. No Phase 4c
BROWSE card rebuild. No broad semantic-audit implementation unless a narrow
Stage 4 field contract requires it.

---

## Current state - what exists today

### Outcome and feedback records

- [`data/learning/intelligence_feedback.jsonl`](data/learning/intelligence_feedback.jsonl)
  is the historical analyzer hopper. ROADMAP says it has 6,290 rows with
  `outcome=null`.
- [`briarwood/intelligence_capture.py`](briarwood/intelligence_capture.py)
  writes routed/user-feedback records. `build_routed_capture_record(...)`
  already accepts `session_id`, `contribution_map`, `model_confidences`,
  `explicit_signal`, and `outcome`; legacy callers leave most of these null.
- [`scripts/backfill_feedback_rows.py`](scripts/backfill_feedback_rows.py)
  already performs an idempotent JSONL rewrite for legacy feedback rows, but
  intentionally leaves `outcome` null. Stage 4 should extend the pattern, not
  overwrite it.

### Persisted turn substrate

- [`api/store.py`](api/store.py) persists `turn_traces`, `messages`, and
  `feedback`. `turn_traces.modules_run` stores per-module execution records
  as JSON; `messages.turn_trace_id` links assistant responses back to a turn;
  `feedback.turn_trace_id` links ratings back to the same turn.
- Stage 3 admin readers already deserialize turn-trace JSON columns through
  `ConversationStore.get_turn_trace(...)` and read feedback through
  `feedback_for_turn(...)`.

### Existing analyzers/harnesses

- [`briarwood/feedback/analyzer.py`](briarwood/feedback/analyzer.py) reports
  routing, confidence buckets, module frequency, and user-feedback
  confidence correlation. It does not yet compute outcome alignment.
- [`briarwood/eval/harness.py`](briarwood/eval/harness.py) already sketches
  deployed-model scorecards from `intelligence_feedback.jsonl`, including
  `confidence_calibration`, `rejection_rate`, and drift score. It currently
  keys mostly on `explicit_signal`, not actual sale outcomes.
- [`briarwood/eval/backtest_program.py`](briarwood/eval/backtest_program.py)
  computes valuation MAE/MAPE against `actual_sale_price` from saved-property
  facts when present. This is the closest current implementation of the
  Stage 4 outcome math.
- [`briarwood/pipeline/feedback_mixin.py`](briarwood/pipeline/feedback_mixin.py)
  defines `FeedbackReceiverMixin.receive_feedback(...)` as a no-op stub.

---

## Outcome contract

Stage 4 v1 should support one ground-truth outcome type:

```json
{
  "property_id": "string",
  "address": "string | null",
  "outcome_type": "sale_price",
  "outcome_value": 1234567,
  "outcome_date": "YYYY-MM-DD",
  "source": "manual_csv | manual_json | public_record",
  "source_ref": "string | null",
  "confidence": 0.0,
  "notes": "string | null"
}
```

Recommended file source for v1:
`data/outcomes/property_outcomes.jsonl` or
`data/outcomes/property_outcomes.csv`. A manual file is preferable for the
first pass because it keeps public-record scraping/API decisions out of the
model-accuracy loop.

Outcome matching order:
1. Exact `property_id`.
2. Normalized address + town/state where available.
3. Manual mapping file for ambiguous historical rows.

Rows with uncertain matches should be reported, not guessed.

---

## `model_alignment` table

Add a new table in [`api/store.py`](api/store.py):

```sql
CREATE TABLE IF NOT EXISTS model_alignment (
    id TEXT PRIMARY KEY,
    turn_trace_id TEXT REFERENCES turn_traces(turn_id) ON DELETE SET NULL,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    property_id TEXT,
    module_name TEXT NOT NULL,
    predicted_value REAL,
    predicted_label TEXT,
    confidence REAL,
    outcome_type TEXT NOT NULL,
    outcome_value REAL,
    outcome_date TEXT,
    absolute_error REAL,
    absolute_pct_error REAL,
    alignment_score REAL,
    high_confidence INTEGER NOT NULL DEFAULT 0,
    underperformed INTEGER NOT NULL DEFAULT 0,
    evidence TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS model_alignment_module_idx
    ON model_alignment(module_name, created_at);
CREATE INDEX IF NOT EXISTS model_alignment_turn_idx
    ON model_alignment(turn_trace_id);
CREATE INDEX IF NOT EXISTS model_alignment_property_idx
    ON model_alignment(property_id);
```

`evidence` is JSON with the source row, module payload subset, and matching
method. This keeps the table queryable while preserving audit detail.

Suggested v1 scoring:
- For sale-price outcomes, `absolute_pct_error = abs(predicted - outcome) /
  outcome`.
- `alignment_score = max(0.0, 1.0 - min(absolute_pct_error / 0.20, 1.0))`.
  A 0 percent error scores 1.0; a 20 percent or worse error scores 0.0.
- `high_confidence = confidence >= 0.75`.
- `underperformed = high_confidence and absolute_pct_error >= 0.10`.

The constants should live near the alignment code and be named so they can be
human-reviewed later. They should not silently change module weights.

---

## The pieces - cycle-by-cycle

### Cycle 1 - Ground-truth ingestion + loader

**Status:** Landed 2026-04-28.

**Scope.**
- Add a small outcome loader module, recommended:
  `briarwood/eval/outcomes.py`.
- Support CSV and JSONL manual files under `data/outcomes/`.
- Validate required fields, normalize prices/dates, and return structured
  records. Prefer a dataclass or Pydantic model; keep the shape simple.
- Add a report-only CLI:
  `python scripts/ingest_outcomes.py --path data/outcomes/property_outcomes.csv --dry-run`
  that prints valid rows, invalid rows, duplicate keys, and unmatched hints.

**Tests.**
- Valid JSONL and CSV rows load.
- Bad dates/prices are rejected with row-level errors.
- Duplicate property IDs are reported.
- Missing optional fields stay nullable.

**Pause gate.** Confirm the owner has an initial outcome file or wants a
sample template committed.

### Cycle 2 - One-shot backfill into JSONL and persisted turn rows

**Status:** Landed 2026-04-28 for JSONL backfill. Persisted turn rows are not
mutated; `model_alignment` rows are the durable store.

**Scope.**
- Add `scripts/backfill_outcomes.py` or extend the existing
  `scripts/backfill_feedback_rows.py` pattern with a separate command.
- Backfill historical `intelligence_feedback.jsonl` rows where a property can
  be matched. Preserve a `.bak` before rewriting, support `--dry-run`, and
  print counts for matched, ambiguous, unmatched, and skipped rows.
- Add read-only matching against `turn_traces` where possible. Because
  `turn_traces` does not have a first-class `property_id` column today, start
  by reading `modules_run` / `tool_calls` / `user_text` evidence. If matching
  is weak, emit an unmatched report rather than writing alignment.
- Do not mutate `turn_traces` in v1. Alignment rows in Cycle 3 are the durable
  store.

**Tests.**
- Dry-run does not write.
- Rewrite preserves unrelated JSONL fields and unknown/corrupt lines.
- Existing non-null outcomes are not overwritten unless
  `--overwrite-outcome` is explicitly passed.
- Ambiguous matches are reported, not guessed.

### Cycle 3 - `model_alignment` table + module feedback receivers

**Status:** Landed 2026-04-28.

**Scope.**
- Add `model_alignment` schema and a safe insert/query API on
  `ConversationStore`, following the Stage 1 failure-swallow convention only
  where alignment writes are observability. CLI backfills should fail loudly.
- Add a small alignment writer, recommended:
  `briarwood/eval/alignment.py`.
- Implement real `receive_feedback()` bodies for:
  - `current_value`
  - `valuation`
  - `comparable_sales`
- The bodies should extract module prediction, confidence, and evidence from
  the module payload and call the alignment writer. If a module lacks a usable
  prediction or confidence, it should return a structured skipped reason.
- Avoid hidden recalibration. `receive_feedback()` records alignment only.

**Module-specific v1 extraction.**
- `current_value`: predicted value from `briarwood_current_value` or
  `data.legacy_payload.briarwood_current_value`; confidence from module
  confidence and/or `pricing_view_confidence`.
- `valuation`: predicted value from `briarwood_current_value`; confidence
  from outer confidence; include macro-nudge evidence if present.
- `comparable_sales`: predicted value from `comparable_value` or
  `data.metrics.comparable_value`; confidence from `confidence` /
  `comp_confidence_score`.

**Tests.**
- Schema migration is idempotent.
- Each module receiver writes one alignment row for a clean sale outcome.
- Missing value/confidence produces a skipped reason, not a bogus row.
- High-confidence underperformance flags are computed from named constants.

### Cycle 4 - Analyzer report for underperforming high-confidence calls

**Status:** Landed 2026-04-28.

**Scope.**
- Extend `briarwood/feedback/analyzer.py` or add a sibling
  `briarwood/feedback/model_alignment_analyzer.py`.
- Report:
  - rows scored by module
  - mean absolute pct error by module
  - high-confidence call count by module
  - high-confidence underperformance count/rate
  - top example rows with turn/property/evidence pointers
  - human-reviewed tuning candidates
- Add a CLI:
  `python -m briarwood.feedback.model_alignment_analyzer`
  with optional `--json`.
- Candidate wording should be advisory, e.g. "Review comp weighting for
  comparable_sales on Belmar rows with high confidence and >10 percent miss."
  No automatic threshold or prompt change should occur.

**Tests.**
- Empty table reports cleanly.
- Mixed module rows aggregate correctly.
- Candidate list includes only high-confidence underperformance rows.
- JSON output is stable enough for future admin integration.

### Cycle 5 - Optional admin read surface, minimal only

**Status:** Deferred. CLI/JSON analyzer output closes the v1 read path; admin
alignment visibility is tracked as lower-priority follow-up work.

**Scope.**
- If the owner wants Stage 4 visible in `/admin`, add a small read-only
  section to the existing admin metrics route and page:
  - top underperforming modules
  - count of scored alignment rows
  - link/turn ID for example rows
- Keep it visually small. This is not Phase 4c and not a dashboard redesign.
- If time is tight, skip UI and keep CLI + JSON as the Stage 4 read-side
  proof. The loop closes when the analyzer reads alignment rows, not when a
  pretty card exists.

**Tests.**
- API compose function returns alignment summary.
- Admin page renders empty and non-empty summaries without crashing.

### Cycle 6 - Closeout docs + review pause

**Status:** Landed 2026-04-28.

**Scope.**
- Update [`ROADMAP.md`](ROADMAP.md) section 3.1 Stage 4 and section 1 only after the code
  lands and verification passes.
- Add a [`DECISIONS.md`](DECISIONS.md) entry only for actual owner/code
  decisions made during implementation, such as outcome file format,
  alignment thresholds, or whether admin UI shipped.
- Update [`ARCHITECTURE_CURRENT.md`](ARCHITECTURE_CURRENT.md) Persistence /
  eval sections if `model_alignment` lands.
- Update [`CURRENT_STATE.md`](CURRENT_STATE.md) only if Stage 4 closes and
  Phase 4c becomes the recommended next task.

**Pause gate.** Stop after closeout. The next step is a human-reviewed tuning
proposal for a specific module. Do not auto-apply model weights, prompts, or
threshold changes as part of Stage 4.

---

## Open design decisions for review

1. **Outcome source v1.** Recommended: manual CSV/JSONL under
   `data/outcomes/`. Public-record fetch can come later.
2. **Outcome matching strictness.** Recommended: exact `property_id` first;
   normalized address only when town/state also match; otherwise report
   ambiguous rows.
3. **Alignment thresholds.** Recommended: high confidence at `>=0.75`;
   underperformance at `>=10%` absolute pct error for sale-price outcomes.
4. **Admin UI in Stage 4.** Recommended: optional. CLI/JSON analyzer is enough
   to close the loop; admin can stay tiny if added.
5. **Whether to update historical JSONL in place.** Recommended: yes, with
   `.bak`, `--dry-run`, and no overwrite of existing non-null outcomes unless
   explicitly requested.

---

## Out of scope (deliberate)

- Auto-recalibration of weights or thresholds.
- Prompt changes, weight changes, or semantic-model fixes beyond recording
  candidates for human review.
- Phase 4c BROWSE summary card rebuild.
- Frontend redesign.
- Public-record scraping/API integration unless the owner rejects manual
  outcome files.
- Chasing unrelated full-suite baseline failures.
- Broad semantic audit implementation. Section 3.3.9 confidence-carrier consumer
  work can inform candidate wording, but it should not become part of Stage 4.

---

## Verification strategy

Focused checks should gate each cycle:

- `venv/bin/python -m pytest tests/test_api_turn_traces.py tests/test_api_feedback.py tests/test_api_admin.py`
  when touching persistence/admin read paths.
- New tests for `briarwood/eval/outcomes.py`,
  `briarwood/eval/alignment.py`, and the alignment analyzer.
- CLI dry-run against a tiny fixture outcome file.
- `venv/bin/python -m pytest tests/test_feedback_loop.py` if
  `feedback/analyzer.py` changes.
- `git diff --check`.

Do not use the full suite as the Stage 4 gate unless the owner asks for it.
The known pre-Cycle-5 clean-tree full-suite baseline differed from the
handoff count: 20 failures / 3 errors.

---

## Success criteria

- At least one actual sale-price outcome file can be loaded and validated.
- Historical feedback rows can be backfilled with non-null outcomes where a
  safe match exists.
- `current_value`, `valuation`, and `comparable_sales` can record alignment
  rows against actual sale outcomes.
- The analyzer reports high-confidence underperformance examples with
  enough evidence for a human to decide whether to tune a prompt/weight.
- No code path automatically changes module weights, thresholds, or prompts.
- The implementation pauses after the report, before any recalibration.
