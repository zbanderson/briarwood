# ATTOM Backfill Investigation — 2026-04-30

Sister memo to `docs/MODEL_BACKTEST_2026-04-30.md`. Phase 1 scopes the ATTOM
surface area available for closing the three comp-store data-integrity findings:
(1) eligibility-gate densification, (2) sqft corruption cleanup, and
(3) non-arms-length sale filtering.

---

## 1. What `attom_enricher.py` does today

**File:** `briarwood/agents/comparable_sales/attom_enricher.py`

### Endpoints called

Single endpoint only: ATTOM **`/property/detail`** (line 117,
`_BASE_URL = "https://api.gateway.attomdata.com/propertyapi/v1.0.0"`,
hard-coded path `/property/detail`).

It does **NOT** hit `/saleshistory/detail`, `/saleshistory/snapshot`,
`/sale/detail`, `/assessment/detail`, or any other endpoint. The richer
`briarwood/data_sources/attom_client.py` (lines 22–40) exposes 16 endpoints
including `sale_history_detail` and `sale_history_snapshot`, but the comp
enricher does not use that client.

### Fields extracted

`ATTOMEnricher.extract_fields` (line 142) returns nine fields per row:
`beds`, `baths`, `sqft`, `year_built`, `lot_size`, `latitude`, `longitude`,
`stories`, `garage_spaces` (lines 208–218).

The mapping into ATTOM JSON (line 145–207):

| Output field    | ATTOM JSON path                                        |
|-----------------|--------------------------------------------------------|
| `beds`          | `building.rooms.beds`                                  |
| `baths`         | `building.rooms.bathstotal` then `bathsfull`           |
| `sqft`          | `building.size.universalsize` then `livingsize` then `bldgsize` |
| `year_built`    | `summary.yearbuilt`                                    |
| `lot_size`      | `lot.lotsize1` (acres)                                 |
| `latitude/lon`  | `location.latitude`/`longitude`                        |
| `stories`       | `building.summary.levels`                              |
| `garage_spaces` | `building.parking.prkgSpaces` (or 1 if `garagetype` set) |

It does **NOT** extract `property_type` (the `summary.proptype` field that
`attom_client._normalize_property_detail` does pull at line 356).

### Merge policy

`enrich_store` (lines 229–331) is **fill-only, never overwrite** — every assignment is
guarded by `if not sale.get(<field>) and fields[<field>] is not None:` (lines 281–311).
A row with corrupted `sqft=9000139` already has truthy sqft, so the existing
enricher will **skip** it. This is a key gap for the sqft cleanup work item.

The enricher's eligibility heuristic `_needs_enrichment` (line 79) is OR-of-missing
across beds, baths, sqft, year_built, lot_size, latitude, stories — so a row
missing any of those qualifies. A row with corrupted sqft that has all other
fields will **not** qualify. (In practice the sqft-corrupted rows are also
missing beds/baths/year_built, so they happen to qualify — but for a different
reason.)

### Quality / eligibility stamping

The enricher does **NOT** set `quality_status` and does **NOT** set
`source_provenance.comp_eligibility_gate` or `comp_eligibility_reasons`. Those
are stamped on-the-fly by `FileBackedComparableSalesProvider._load_rows`
(`briarwood/agents/comparable_sales/agent.py:61–73`) when the comp store is
loaded by the agent. The enricher only updates the structural fields and bumps
two metadata keys: `attom_enrichment_date` and `attom_records_enriched`
(lines 318–322).

### Rate limit / retry

Hard-coded `_REQUEST_DELAY_SECONDS = 0.5` between requests (line 36, used at
line 315, only after a successful call). 15-second per-request timeout
(line 121). **No retry on transient failures** — a `RequestException` or non-200
response is logged and the row is skipped (lines 138–140). No backoff. No
exponential retry. No 429-handling. The richer `AttomClient._fetch`
(`briarwood/data_sources/attom_client.py:170–215`) DOES have retry-with-backoff
and budget-tracking; the comp enricher predates that work.

---

## 2. What pushes a comp from `eligible` to `market_only`

**File:** `briarwood/data_quality/eligibility.py:18–56`

`classify_comp_eligibility` returns `market_only` when:

- `_identity_accepted` is True (address present + state == "NJ" + town not
  rejected/needs_review; lines 59–69), AND
- `_minimum_structural_profile` is False (line 35–43), AND
- No fatal conflicts.

`_minimum_structural_profile` (lines 72–81) requires **≥3 of the 4 fields**
`{beds, baths, sqft, property_type}` to be present (`chosen_value not in (None,
"", [], {})` and `chosen_status not in {"missing", "rejected"}`).

### Empirical confirmation

I re-ran `DataQualityPipeline.run` + `classify_comp_eligibility` on every row
of `data/comps/sales_comps.json` (3,919 rows). Result:

```
eligible:    833
market_only: 3084   (100% with reason "Structural core is incomplete.")
rejected:    2
```

By year (matches the backtest memo):

```
2022: market_only=467, eligible=0
2023: market_only=709, eligible=56
2024: market_only=738, eligible=94
2025: market_only=1043, eligible=576, rejected=2
2026: market_only=127, eligible=107
```

### What pushes the gate over

A `market_only` SR1A row has `sqft` + `property_type` only (2 of 4). Add either
**`beds` OR `baths` from ATTOM** and the row crosses the 3-of-4 threshold and
becomes `eligible`. ATTOM `/property/detail` returns both reliably for residential
parcels in our zip set (the existing 164 enriched rows were materially closed in
the 2026-04-10 run).

---

## 3. Sample inventory: 20 market_only + 20 corrupted-sqft rows

### 20 `market_only` rows (4 per year, random.seed(42))

Every sampled row has the same shape: source = `NJ SR1A`,
present = `[sqft, property_type]`, missing = `[beds, baths, year_built,
lot_size, latitude]`. ATTOM `/property/detail` plausibly fills beds, baths,
year_built, lot_size, lat/lon for all 20.

Selected indices: 1445, 1028, 942, 1526 (2022); 1544, 1452, 1425, 1176 (2023);
1798, 2729, 2595, 1765 (2024); 3614, 2809, 2804, 2939 (2025); 3804, 3806, 3848,
3865 (2026). All show identical missingness.

### 20 corrupted-sqft rows (random.seed(42), full pool of 2,264)

Pattern: source = `NJ SR1A`, sqft is a 7-digit value of shape `\d000\d{3}`
(e.g. `9000187`, `5000293`, `6000133`) — looks like SR1A bulk-ingest concatenated
two fields into one. Some are 5-digit values like `21408`, `52139`, `61864`
(also implausible for residential). Every one of these 20 has
`beds=None, baths=None, year_built=None, lot_size=None`. ATTOM can replace
all five fields, including sqft.

**Important caveat for the cleanup work:** the existing enricher's fill-only
merge policy will NOT overwrite `sqft` because the corrupted value is truthy.
The backfill script must override this for known-bad sqft values
(rule of thumb: residential `sqft > 10000` is implausible).

---

## 4. Deed-type signal (non-arms-length filter)

`/property/detail` does **NOT** return deed-type or sale-disclosure metadata.

`attom_client.py:481–513` (`_normalize_sales_history_rows`) does extract these
from the **`/saleshistory/detail`** and `/saleshistory/snapshot` endpoints:

- `transaction_type` (`saleTransType`) — e.g., `"REFINANCE"`, `"RESALE"`
- `deed_type` (`saleDocType`) — e.g., `"GRANT DEED"`, `"QUITCLAIM"`,
  `"INTRA-FAMILY TRANSFER"` etc.
- `disclosure_type` (`saleDisclosureType`) — captures non-disclosure jurisdictions
- `sale_code` (`saleCode`) — ATTOM's own arms-length / non-arms-length code

These map to ATTOM endpoint tier `"conditional"`
(`attom_client.py:48`), meaning higher cost. They are NOT covered by the
existing comp enricher.

For a non-arms-length filter, the script needs to add a NEW endpoint call
(`/saleshistory/snapshot` is the lighter surface) and extract `deed_type`,
`sale_code`, and `transaction_type` per row. Alternatively, defer this work
item — sqft cleanup + eligibility densification do not depend on it.

---

## Proposed Phase 2 design

### Script location

`scripts/data_quality/attom_comp_store_backfill.py` (new).

### Inputs / outputs

- Reads: `data/comps/sales_comps.json`
- Writes: `data/comps/sales_comps_attom_backfilled.json` (new file; original is
  not mutated — owner approves before promotion)
- Per-row log: `data/eval/attom_backfill_log_2026-04-30.jsonl` (streaming, one
  JSON line per processed row)

### Targeting (which rows to enrich)

A row qualifies if any of:

1. `sqft is None` OR `sqft > 10000` (corrupted-sqft cleanup) — **bypasses the
   enricher's fill-only merge for sqft only**
2. `_minimum_structural_profile` returns False (per the gate logic above) AND
   identity is accepted — i.e., the row is currently `market_only`. We try to
   close it to `eligible` by filling beds/baths/year_built.
3. (Optional, deferred) deed-type missing → call `/saleshistory/snapshot`. **My
   recommendation: defer this to a follow-up; the first two work items are
   cheaper and unblock the bulk of the backtest finding.**

### Per-row flow

1. Build address1 + address2 (reuse `_build_address2`, `attom_enricher.py:220`).
2. Call ATTOM property-detail via the existing `ATTOMEnricher.lookup_property` /
   `extract_fields` interface — no need to introduce a second client for Phase 2.
3. Apply ATTOM fields. For **sqft**, override the corrupted value when `sqft >
   10000` and ATTOM returned a plausible value (`100 ≤ sqft ≤ 20000`). For all
   other fields use the existing fill-only policy.
4. Re-run `DataQualityPipeline.run` + `classify_comp_eligibility` on the
   updated row to recompute `quality_status` and the gate. Stamp these onto the
   row inline (under `quality_status` and
   `source_provenance.comp_eligibility_gate`) so the agent's load-time pipeline
   pass at `agent.py:61–73` becomes a no-op for backfilled rows.
5. Append a log line with: `index`, `address`, `town`, `before` (sqft, beds,
   baths, year_built, gate, quality_status), `after` (same), `attom_fields_used`
   (which fields were filled), `attom_call_status` (`ok|404|error|skipped`).

### Throttling and resumability

- Use the existing `_REQUEST_DELAY_SECONDS = 0.5` (≈2 req/s; ATTOM's free-tier
  guidance per the comment at line 35).
- Streaming writes for both the JSONL log AND the output JSON. Output JSON is
  written after every N rows OR on Ctrl-C (signal handler).
- Idempotent re-runs: skip rows where the log already shows a recent
  successful enrichment.

### Sample size for Phase 2

50 rows split:
- 20 `market_only` 2024/2025 rows (10 each year)
- 20 corrupted-sqft rows
- 10 rows that are both (corrupted-sqft AND market_only — common per the
  inventory above)

Stop. Report success rates and wall-clock per row. Wait for owner approval
before running on the full 3,919.

### Out of scope for Phase 2

- Full-pool backfill.
- `/saleshistory/snapshot` deed-type integration. Recommend filing a separate
  follow-up handoff — the deed-type signal touches a different ATTOM endpoint
  with different cost/budget characteristics, and the non-arms-length filter
  also wants sale-price-vs-AVM cross-check logic that is its own design problem.
- In-place mutation of `data/comps/sales_comps.json`. Hard ground rule.

### Producer-math read-only constraint

Confirmed: no edits to `briarwood/modules/comparable_sales.py`,
`briarwood/modules/current_value.py`, `briarwood/agents/comparable_sales/agent.py`,
or any sibling module. The script lives under `scripts/data_quality/` and only
imports from `briarwood.data_quality.*` and
`briarwood.agents.comparable_sales.attom_enricher`.

---

## Open questions / blockers

1. **ATTOM rate ceiling under live keys.** Hard-coded 0.5s delay is from a
   comment, not a measured constraint. If the 50-row sample pushes that ceiling
   we will see 429s and report back.
2. **Property-detail address-match quality.** The existing enricher's match rate
   on the 2026-04-10 run isn't recorded per-row in the comp store metadata
   (only the `attom_records_enriched=164` aggregate). The 50-row sample will
   give us an empirical match rate for the kinds of rows we are now targeting
   (older SR1A rows that the previous run skipped, presumably for a reason).
3. **`property_type` enrichment is not currently in `extract_fields`.** Adding
   it is a small change; deferring for Phase 2 keeps the diff minimal but means
   property_type stays as the SR1A value. The gate doesn't depend on this if
   beds/baths land — sqft + property_type + beds = 3-of-4.
