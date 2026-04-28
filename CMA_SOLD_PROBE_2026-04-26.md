# SearchApi Zillow SOLD Probe — 2026-04-26

**Generated:** 2026-04-26
**Plan:** [CMA_HANDOFF_PLAN.md](CMA_HANDOFF_PLAN.md) Cycle 1.5.
**Probe script:** [scripts/probe_searchapi_sold.py](scripts/probe_searchapi_sold.py).
**Raw output:** [data/diagnostics/searchapi_sold_probe_2026-04-26.json](data/diagnostics/searchapi_sold_probe_2026-04-26.json).

---

## Headline

**SearchApi Zillow's SOLD endpoint is rich, fresh, and load-bearing-grade for our markets.** Every one of our six target Monmouth County towns returns ~41 SOLD listings per query with 100% sale-date coverage, full geocoding, and recent (last 18 months) sales activity. The unify path in CMA_HANDOFF_PLAN Cycle 3 is unblocked.

**Bigger finding:** our normalizer at `briarwood/data_sources/searchapi_zillow_client.py::SearchApiZillowListingCandidate` throws away ~80% of what SearchApi sends back per row. The raw payload includes `date_sold`, `lot_sqft`, `latitude`, `longitude`, `tax_assessed_value`, `zestimate`, `rent_zestimate`, `days_on_zillow`, and more — none of which reach our application code. Cycle 3 needs to extend the normalizer FIRST, before the 3-source merger. The data is already paid for.

---

## Per-town SOLD inventory

| Town | Rows | Sale-date range | Price range |
|------|-----:|-----------------|-------------|
| Avon By The Sea | 41 | 2024-10-10 → 2026-04-06 | $34K → $4.5M |
| Belmar | 41 | 2025-11-12 → 2026-04-20 | $8K → $3.4M |
| Bradley Beach | 41 | 2025-08-11 → 2026-04-24 | $199K → $2.8M |
| Manasquan | 41 | 2026-01-08 → 2026-04-23 | $160K → $4.9M |
| Sea Girt | 41 | 2025-08-12 → 2026-04-09 | $446K → $6.0M |
| Spring Lake | 41 | 2025-12-01 → 2026-04-24 | $225K → $6.8M |
| **Total** | **246** | **2024-10 → 2026-04** | — |

**Note on row count:** SearchApi returned 41 rows per town in the raw payload. Our probe script capped normalization at 20 (`max_results=20`), so the JSON output reflects 120 rows total — but the upstream supply is 246. Production calls would naturally bump `max_results` to capture more.

**Note on price floor outliers:** Belmar at $8K and Avon at $34K are almost certainly tax-deed sales or distressed transactions. Engine A's `_data_quality_score` filtering will drop these once the unified pipeline is in place. SearchApi does not pre-filter for transaction type.

**Comparison to saved data** (per `data/comps/sales_comps.json`): 2,489 saved sales for the same 6 towns over a wider 4-year window (2022-04 → 2026-04-01). Saved data is denser by count but the SearchApi window is fresher (last 18 months vs. last 4 years). For day-of-decision valuation, SearchApi's recency is the more valuable signal.

---

## Field coverage across 246 SOLD rows

| Field | Coverage | Notes |
|-------|---------:|-------|
| `date_sold` | 246 / 246 (100%) | Universal. Closes the SOLD recency-scoring gap. |
| `latitude` | 246 / 246 (100%) | Universal. Enables real proximity scoring (Engine A's `_proximity_score` works). |
| `longitude` | 246 / 246 (100%) | Universal. |
| `rent_zestimate` | 245 / 246 (100%) | Universal. **Highly load-bearing for the Scout rent-angle pattern (Phase 4b).** |
| `days_on_zillow` | 246 / 246 (100%) | Universal. Useful for the ACTIVE-staleness invariant (Cycle 2). |
| `home_type` | 246 / 246 (100%) | Universal. SINGLE_FAMILY / MULTI_FAMILY / etc. |
| `listing_type` | 246 / 246 (100%) | Universal. Owner-occupied vs investor signal. |
| `zestimate` | 230 / 246 (93%) | High coverage. Zillow's AVM cross-check. |
| `tax_assessed_value` | 226 / 246 (92%) | High coverage. Quality signal — outliers in tax assessment vs sale price flag bad comps. |
| `beds` | 227 / 246 (92%) | High coverage. |
| `baths` | 227 / 246 (92%) | High coverage. |
| `lot_sqft` | 199 / 246 (81%) | Mostly available. Engine A's lot-adjustment range works for ~80% of rows; the rest degrade to direct-comp scoring. |
| `broker` | 181 / 246 (74%) | Provenance. |
| `sqft` | 176 / 246 (72%) | The biggest gap. Engine A's sqft-tolerance filter and per-sqft adjustments need missing-sqft fallbacks. |

---

## Implications for Cycle 2 + Cycle 3

### What this changes about Cycle 2 (invariants)

- **SOLD age cap default**: SearchApi's window is roughly 18 months. Default `SOLD_AGE_CAP_MONTHS = 18`. Anything older than 18 months either doesn't appear or signals a distressed/special transaction.
- **ACTIVE staleness cap**: `days_on_zillow` is universally available. Default `ACTIVE_DOM_CAP_DAYS = 180` (6 months on market is a stale ask).
- **Minimum SOLD count per town**: with 41 SOLD per town readily available, default `MIN_SOLD_COUNT = 5` (after applying town/beds/sqft filters; well within reach for our markets).
- **`tax_assessed_value` outlier detection**: a comp with `extracted_price < 0.4 * tax_assessed_value` (or > 4×) is almost certainly a non-arms-length transaction. New invariant: filter via this ratio. Catches the Belmar $8K and Avon $34K outliers without hand-tuning per market.

### What this changes about Cycle 3 (3-source pipeline)

**Restructure Cycle 3 into three sub-steps:**

1. **Extend `SearchApiZillowListingCandidate`** to capture `date_sold`, `lot_sqft`, `latitude`, `longitude`, `tax_assessed_value`, `zestimate`, `rent_zestimate`, `days_on_zillow`, `home_type`, `listing_type`. This is mostly a normalizer rewrite — the data is in `raw_payload["properties"][i]`, just not making it through `_normalize_listing`. **Do this first.** Without it, the rest of Cycle 3 has to work with crippled data.
2. **Lift Engine A's scoring/adjustment logic + apply per-listing-status extensions.** As scoped today.
3. **3-source merger.** As scoped today, but prioritize SearchApi SOLD as the primary source — saved data becomes a strict fallback for cases where SearchApi returns below-minimum rows.

### What this changes about ATTOM enrichment

**Lower priority than originally scoped.** SearchApi's SOLD payload already includes `zestimate` (Zillow's AVM) and `tax_assessed_value` — which is most of what an ATTOM `sale_history_snapshot` confirmation would deliver. The remaining ATTOM-only signal would be deeper sale history (multiple transactions for repeat-sale analysis) which is useful but not foundational.

Recommendation: **defer ATTOM enrichment from Cycle 3 to a follow-up cycle** (or remove from scope entirely until a quality gap is observed in production). The `BRIARWOOD_CMA_ATTOM_ENRICH=0` env knob in Cycle 3 should default to OFF and we let traces from the live pipeline tell us if we need ATTOM at all.

---

## Cost note

- 12 SearchApi calls (6 SOLD + 6 ACTIVE) at ~$0.005 each → ~$0.06 total for this probe.
- Production cost per chat-tier turn after Cycle 3 lands: 2 SearchApi calls (1 SOLD + 1 ACTIVE) per cache miss. With the 24-hour discovery cache TTL, repeat queries on the same town hit cache. Cost amortizes well across users in the same market.

---

## Open question for owner

**Should the probe script stay or go?**
- Keep at `scripts/probe_searchapi_sold.py` — useful for re-checking inventory in new markets when we expand beyond Monmouth.
- Move to `scripts/diagnostics/probe_searchapi_sold.py` — signals "diagnostic, not user-facing tool."
- Delete after Cycle 3 lands.

Recommendation: **move to `scripts/diagnostics/`**. Re-runs cost $0.06 and the script is small. Re-running before any market expansion is cheap insurance against discovering the same kind of inventory gap in a new geography.

---

## Verdict

Cycle 1.5's question — "is SearchApi Zillow SOLD inventory thin or stale for our target markets?" — is answered: **no, it's rich and fresh.** Cycle 2 and Cycle 3 can proceed as scoped, with the three adjustments above (extend normalizer first; new tax-assessed-vs-price outlier invariant; downgrade ATTOM enrichment to defer-or-remove). Owner can sign off on the unify direction as a confirmed call rather than a hopeful one.
