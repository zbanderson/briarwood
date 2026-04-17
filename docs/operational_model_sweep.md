# Briarwood Operational Model Sweep

This document defines the repo-native review surface for the current
intelligence-first, routed/scoped architecture.

## Scope

- Audit the current routed/scoped system, not the archived Dash-era UI.
- Measure both model behavior and operational readiness.
- Distinguish three states for each evaluation surface:
  - runnable and passing
  - runnable but failing
  - blocked by environment/setup drift

## Primary Tool

Run:

```bash
python3 -m briarwood.eval.operational_sweep
python3 -m briarwood.eval.operational_sweep --json outputs/operational_sweep.json
```

The sweep produces a structured artifact with:

- environment dependency readiness
- scoped module inventory from the V2 registry
- currently documented fully scoped vs partial/fallback paths
- targeted evaluation surface status
- prioritized findings
- Tavily and ATTOM integration recommendations

## What The Sweep Should Validate

### Routed / Scoped Core

- `buy_decision` at `snapshot` and `decision` remain the baseline must-work paths.
- Scoped execution tests and orchestrator tests are the first operational checks.
- Model-quality harness status should be recorded separately from model correctness when the environment is missing dependencies.

### Tavily

- Tavily is Briarwood's discovery/extraction layer for local intelligence.
- Preferred runtime pattern:
  - Search for freshness-sensitive discovery
  - Extract for normalized municipal/local text
- Crawl should be reserved for stable municipal or ordinance sites.
- Research should stay out of the core routed hot path.

### ATTOM

- ATTOM sales history is the preferred structured source for subject and comp history evidence.
- `sale/detail` is last-sale only and should not be treated as full history.
- `saleshistory/detail` and `saleshistory/snapshot` should feed:
  - repeat-sale chains
  - hold-period context
  - price-per-sqft history anchors
  - disclosure / history-quality caveats

### Confidence

- Confidence should remain Briarwood-native and deterministic.
- Sales-history quality should surface as explicit history confidence rather than hidden narrative text.
- History confidence should adjust trust and curation, not replace valuation math.

## Notes

- Existing docs that remain authoritative for this sweep:
  - `AGENTS.md`
  - `docs/current_docs_index.md`
  - `docs/scoped_execution_support.md`
  - `docs/model_inventory.md`
  - `docs/model_audits/*`
- Historical UI/dashboard docs are context only unless a current doc points back to them.
