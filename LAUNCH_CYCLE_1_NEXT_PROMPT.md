May 2026 Launch — Cycle 1 (Sunday Scaffold) — execution handoff

START: follow CLAUDE.md startup orientation (run the readme-discipline drift check; read AGENTS.md, docs/current_docs_index.md, ARCHITECTURE_CURRENT.md, GAP_ANALYSIS.md, TOOL_REGISTRY.md, CURRENT_STATE.md; run `git log -10` and `git status` before any code work). Then read these specific entries before any sub-stream work — they hold the canonical alignment for this initiative and are NOT optional reading even if the orientation set already covers them at a high level:

- `CURRENT_STATE.md` — the new "May 2026 Launch (active)" section near the top.
- `ROADMAP.md` §3.8 May 2026 Launch Readiness — the full sequenced cycle plan; this cycle is **Cycle 1** of that plan (sub-streams 1a, 1b, 1c).
- `DECISIONS.md` 2026-04-30 entry "May 2026 launch readiness: alignment session" — the canonical "what is this app for?" reference. Do NOT re-litigate the alignment in this session; the decisions are locked. Execute against the plan.
- `docs/MODEL_BACKTEST_2026-04-30.md` — §3.7 Phase A Cycle 2A backtest baseline. The accuracy bar for the user demo is empirical against this baseline after Cycle 1 lands.
- `docs/HOSTING_COMPARISON_2026-04-30.md` and `docs/LAUNCH_CHECKLIST_2026-05-04.md` — Stream 2's hosting drafts. Sub-stream 1a executes against these.
- `docs/ATTOM_BACKFILL_INVESTIGATION_2026-04-30.md` — Stream 1's ATTOM investigation memo. Sub-stream 1b executes the full-pool run against the script that memo describes.

Locked alignment (do not re-question):

- Launch goal: Sunday 2026-05-04 EOD = scaffolding-complete; user demo with 5–10 trusted people = later.
- Two personas (small investors + realtors), same browse-and-drill flow.
- Headline UX is browse-first ("what's for sale in [town]") — NOT paste-URL-first. The 2026-04-26 Zillow URL parser regression is explicitly DEFERRED for this launch window.
- Geo scope: Monmouth coast 8 towns only (Belmar, Manasquan, Avon By The Sea / Avon-by-the-Sea, Spring Lake, Sea Girt, Bradley Beach, Asbury Park, Wall / Wall Township).
- Hosting: Fly.io (api/+briarwood/) + Vercel (web/). Default subdomains for Sunday (`briarwood.vercel.app` + `briarwood-api.fly.dev`). No custom domain in this cycle.
- No auth in Sunday scaffold. Vercel/Cloudflare Access SSO ships before the user demo, not in this cycle.
- Per-property page = existing Phase 4c three-section newspaper hierarchy (`BrowseRead` + `BrowseScout` + `BrowseDeeperRead`). Don't redesign the per-property layout in this cycle — that work lands in Cycles 3–4.

State of the world at handoff (2026-04-30 EOD):

- Stream 1 (ATTOM backfill) ran a 50-row sample. **Result:** 88% ATTOM match rate; 32/50 sqft corrections; 41/50 (82%) `market_only` → `eligible` promotions; ~0.54s/row. Output at `data/comps/sales_comps_attom_backfilled.json` (50 rows backfilled, 3,919 rows preserved unchanged side-by-side). Log at `data/eval/attom_backfill_log_2026-04-30.jsonl` (50 lines). Script at `scripts/data_quality/attom_comp_store_backfill.py`. **Owner approval to run the full pool was the explicit gate. Sub-stream 1b runs the full pool.**
- Stream 2 (hosting scaffold) drafted: `Dockerfile`, `.dockerignore`, `fly.toml` (Newark region, 1 GB volume, always-on, healthcheck on `/healthz`), `web/vercel.json` (Next.js framework, pnpm, `maxDuration: 300` on the SSE chat route), `docs/HOSTING_COMPARISON_2026-04-30.md`, `docs/LAUNCH_CHECKLIST_2026-05-04.md`. Existing `web/next.config.ts` already reads `BRIARWOOD_API_URL` env so no app-code changes needed. **Drafts are in the working tree, untracked.** `Dockerfile` was lint-verified but not built (Docker not installed in the agent's sandbox); the new session should run `docker build .` if Docker is available. Pre-deploy gate per the launch checklist: **rotate the live secrets in `.env`** (OpenAI / Anthropic / ATTOM / SearchApi / Mapbox / Google Maps / Tavily) before issuing them as Fly secrets — `.env` has been touched across multiple agent sessions and the keys may have leaked into transcripts.
- Sub-stream 1c (SearchApi active-listings refresh) is **not yet started.** This is fresh investigation + implementation. Current `data/comps/active_listings.json` has 59 listings dominated by Belmar (27), Avon-by-the-Sea variants (16 across two spellings), Spring Lake (9), Bradley Beach (5). **Manasquan = 0, Asbury Park = 0, Sea Girt = 0, Wall / Wall Township ≈ 1.** Without refreshed listings, the headline "what's for sale in [town]" flow returns nothing for half the supported towns.
- Pre-existing `__pycache__/*.pyc` modifications are unrelated to anything in scope and can be ignored.

Goal of Cycle 1:

By Sunday 2026-05-04 EOD, deliver a hosted Briarwood instance accessible from phone+laptop on default Vercel + Fly subdomains, running against an ATTOM-densified comp store and a refreshed active-listings file for all 8 supported towns. The instance is for the owner's own use first; user demo is later (Cycle 6).

This cycle's deliverables:

- **1a — Hosting deploy.** A live Fly.io app at `briarwood-api.fly.dev` (or whatever name the owner picks during `fly launch`) and a live Vercel deployment at `briarwood.vercel.app` (or owner's chosen project name). All env vars set; smoke tests pass against the deployed pair (canonical Belmar fixture renders end-to-end on the deployed web URL).
- **1b — ATTOM full-pool comp-store backfill.** `data/comps/sales_comps.json` updated in-place from the side-by-side `sales_comps_attom_backfilled.json` after owner reviews the diff. Backfill log at `data/eval/attom_backfill_log_2026-04-30.jsonl` extended to ~3,000 candidate rows. Two of the three §4 Cycle 2A follow-ups closed (sqft cleanup + eligibility-gate densification). The third (non-arms-length sale filter) stays open as a separate post-launch handoff.
- **1c — SearchApi active-listings refresh.** `data/comps/active_listings.json` updated to ~10–30 listings per supported town (≈100–300 total). Town spelling variants canonicalized (Avon By The Sea / Avon-by-the-Sea consolidated; Wall / Wall Township consolidated). New refresh script at `scripts/data_quality/refresh_active_listings.py` checked in for future re-runs.

Suggested execution shape (the new session can deviate):

The three sub-streams are independent and can be executed in parallel by spawning sub-agents (general-purpose) for 1b and 1c while the parent session walks through 1a interactively with the owner. 1a depends on the owner taking actions in their browser (account signup, payment method, `fly launch`); the agent helps with verification, pre-deploy key rotation, and post-deploy smoke tests but cannot execute the deploy itself.

---

## Sub-stream 1a — Hosting deploy

**Pre-deploy steps (agent-led, owner-paired):**

1. Walk the owner through `docs/LAUNCH_CHECKLIST_2026-05-04.md` from the top. Each phase has wall-clock estimates and `[EXTERNAL WAIT]` flags — surface those proactively.
2. **Rotate live secrets in `.env`.** This is the load-bearing pre-deploy gate. The keys to rotate (per Stream 2's blocker note): OpenAI, Anthropic, ATTOM, SearchApi, Mapbox, Google Maps, Tavily. After rotation, update local `.env`, ensure each app still works locally, then issue the new keys as Fly secrets (`flyctl secrets set ...`) and Vercel env vars.
3. Verify the drafts before launch:
   - `docker build .` if Docker is available locally — confirm the image builds.
   - Lint `fly.toml` (`flyctl config validate`).
   - Confirm `web/vercel.json` parses (`pnpm vercel build` if Vercel CLI is installed; otherwise just JSON-lint).
   - Read `Dockerfile`, `.dockerignore`, `fly.toml`, `web/vercel.json` end-to-end and flag anything that looks wrong against the actual repo state (e.g., paths, Python version, requirements).
4. Confirm the working tree state. `git status` must be in a known shape — if there are uncommitted application-code changes, decide with the owner whether to commit a deploy-prep snapshot first or deploy off `main` cleanly.

**Deploy steps (owner-executed; agent verifies):**

1. Owner signs up for Fly.io, attaches payment, runs `flyctl launch` from the repo root (no deploy yet — generates the volume + the app).
2. Owner runs `flyctl secrets set <KEY>=<VALUE>` for each rotated key.
3. Owner runs `flyctl deploy` to push the first deploy.
4. Owner signs up for Vercel, connects the repo, deploys the `web/` directory with the env var `BRIARWOOD_API_URL=https://<api-app>.fly.dev`.
5. Owner shares the two URLs back to the session.

**Post-deploy smoke tests (agent-led):**

Walk through the smoke-test phase of `docs/LAUNCH_CHECKLIST_2026-05-04.md`. At minimum verify:

- `https://<api-app>.fly.dev/healthz` returns 200.
- The web app loads at `https://<web-app>.vercel.app/` and the chat UI appears.
- A canonical query against the deployed pair completes end-to-end (try the Belmar saved property at slug `1008-14th-ave-belmar-nj-07719` if it survives the comp-store-mutation in 1b; else pick another saved property). Browse-tier should render with the three-section layout.
- An SSE-streaming chat turn completes without timeout (SSE max-duration is 300s on Vercel per the drafted `vercel.json`).

**Outcome:** append a "Cycle 1a outcome (YYYY-MM-DD — LANDED)" note to ROADMAP §3.8 with the live URLs, any deviations from the launch checklist, and any drafts that needed adjustment in flight.

---

## Sub-stream 1b — ATTOM full-pool comp-store backfill

**Prerequisite:** owner has approved the full-pool run after seeing the 50-row sample report. Treat that approval as granted by virtue of this prompt being executed.

**Steps:**

1. Read `scripts/data_quality/attom_comp_store_backfill.py` end-to-end. Confirm:
   - The script writes to `data/comps/sales_comps_attom_backfilled.json` (side-by-side), NOT in-place to `sales_comps.json`.
   - The streaming log at `data/eval/attom_backfill_log_2026-04-30.jsonl` is append-mode (so the existing 50 rows are preserved if the script supports resume; otherwise the run starts fresh).
   - Rate-limit handling and retry logic. If the script lacks backoff and ATTOM rate-limits during the run, the script needs minimal hardening (sleep-on-429) before the full run. Stream 1's investigation memo flagged "no retry/backoff" — fix that before the full pool.
2. Run the script on the full pool: `venv/bin/python3 -m scripts.data_quality.attom_comp_store_backfill`. Expected wall-clock: 35–60 minutes for ~3,000 candidate rows. If the script supports a `--limit` or progress mode, use it; if not, run unbounded with a streaming progress print every 250 rows.
3. After the run, produce a summary:
   - Total candidates processed.
   - ATTOM match rate (expected ~88% from sample).
   - Sqft corrections count.
   - `market_only` → `eligible` promotion count (expected ~82% from sample).
   - Rows still `market_only` after backfill (expected ~12% no-match + some that lacked promotable evidence even with ATTOM data).
   - Wall-clock and any rate-limit incidents.
4. **Promote the file.** After owner reviews the diff, copy `data/comps/sales_comps_attom_backfilled.json` over `data/comps/sales_comps.json` (using `git diff --stat data/comps/sales_comps.json` first to confirm the size of the change; the file is large enough that a full diff is unwieldy, so use a sampling diff: `jq '.sales | length' both files`, plus a 10-row random sample comparison).
5. **Re-run §3.7 Cycle 2A spot-check** (NOT the full backtest yet — that's Cycle 2 of §3.8). Just validate that the runner still works and that a sampled 50 targets show meaningfully better APE on the new data:
   ```
   venv/bin/python3 -m scripts.eval.backtest_comparable_sales 50
   venv/bin/python3 -m scripts.eval._backtest_analysis_filtered \
       data/eval/backtest_comparable_sales_<date>.jsonl
   ```
   Report median APE on the 50-row sample. If it's in the same range as the prior baseline (28%) or worse, flag immediately; something is wrong. If it's noticeably better, that's the leading indicator the densification worked.

**Outcome:** append a "Cycle 1b outcome (YYYY-MM-DD — LANDED)" note to ROADMAP §3.8 with the full-pool numbers + the spot-check median APE. Append the relevant per-row ATTOM-source citations to `data/eval/attom_backfill_log_2026-04-30.jsonl` (the script handles this).

---

## Sub-stream 1c — SearchApi active-listings refresh (NEW)

**Phase 1 — Investigation (read-only):**

1. Read `briarwood/data_sources/searchapi_zillow_client.py` end-to-end. Document the public interface — what call shape pulls listings for a town? Are there town-keyed list endpoints, or is it URL-keyed (one listing at a time)?
2. Read `data/comps/active_listings.json` to confirm its current schema. Listings carry `town`, `state`, `address`, `price`, `bedrooms`, `bathrooms`, `sqft`, `listing_url`, etc. — match the existing schema; do NOT introduce new fields.
3. Read the ingestion script that originally populated `active_listings.json` (likely under `scripts/` or `briarwood/agents/comparable_sales/`). If it exists, the new refresh script extends or wraps it. If it doesn't, design from scratch.
4. Cross-reference the 2026-04-28 ROADMAP entry "Comp store town-name canonicalization" — the spelling variants (Avon By The Sea / Avon-by-the-Sea, Wall / Wall Township) need to be canonicalized as part of this refresh so the browse-by-town flow doesn't fork.
5. Check SearchApi quota state — the owner mentioned upgrading. Confirm the current quota allows ~200–500 listing fetches without hitting limits, or document if a quota bump is needed before running.

**Phase 2 — Build the refresh script:**

1. New script at `scripts/data_quality/refresh_active_listings.py`. Should:
   - For each of the 8 supported towns, call SearchApi/Zillow's active-listings-by-town endpoint (or equivalent — could be a Zillow search URL constructed per town).
   - Pull at least 10 listings per town (more is better; aim for the natural Zillow page result, typically 25–40 per town).
   - Canonicalize town strings to a single spelling per town (the ROADMAP §4 town-name canonicalization decision).
   - Stamp each listing with provenance: `source_name=SearchApi`, `source_quality=...`, fetched-at timestamp.
   - Write to `data/comps/active_listings.json` in the existing schema.
   - Streaming write so a Ctrl-C leaves a partial-but-valid file.
   - Log to `data/eval/active_listings_refresh_<date>.jsonl` with per-town counts + any fetch failures.
2. Run the script. Verify:
   - All 8 supported towns have ≥ 10 active listings (preferably 20+).
   - Town spelling variants are consolidated (no more `Avon-by-the-Sea` AND `Avon By The Sea`).
   - The browse-style flow works against the new data — pick a property from each town and confirm it loads through the chat surface end-to-end.
3. **Spot-check the data.** Pick 5 random listings, manually visit the source URL (Zillow), confirm the data matches what was fetched. Catches schema drift or stale data.

**Outcome:** append a "Cycle 1c outcome (YYYY-MM-DD — LANDED)" note to ROADMAP §3.8 with: per-town listing counts, total count, any towns that came up short, the SearchApi quota usage, and the spot-check verification. The new script becomes the canonical refresh tool for future cycles.

---

## Hard constraints

- **READ-ONLY ON PRODUCER MATH.** No edits to `briarwood/modules/comparable_sales.py`, `briarwood/modules/current_value.py`, the agents under `briarwood/agents/comparable_sales/agent.py` (or any agent file), or any sibling module under `briarwood/modules/` or `briarwood/synthesis/`. Hosting work and data-substrate work do NOT touch model math.
- **ZILLOW URL PARSER REGRESSION IS DEFERRED.** Do NOT fix it in this cycle even if you encounter it during 1c (it affects URL-keyed paths; town-keyed listing fetches don't go through it). The 2026-04-26 ROADMAP entry stays open as a post-launch handoff.
- **BACKFILL OUTPUTS GO SIDE-BY-SIDE FIRST.** Sub-stream 1b writes to `sales_comps_attom_backfilled.json`; promotion to `sales_comps.json` happens after owner diff review. Sub-stream 1c writes to `active_listings.json` directly because the existing file is already side-by-side stale, but produce a backup copy at `active_listings_pre_refresh_<date>.json` before overwriting.
- **NO DESTRUCTIVE GIT OPERATIONS.** Do not `git reset --hard`, `git push --force`, or `git checkout --` on uncommitted changes. The working tree has uncommitted application-code changes from prior sessions; don't disturb them.
- **NO NEW LIVE API DEPENDENCIES.** Use existing ATTOM and SearchApi keys from `.env`. Don't add new vendor SDKs or accounts.
- **USE `venv/bin/python3`** per CLAUDE.md.
- **README discipline** per CLAUDE.md and `.claude/skills/readme-discipline/SKILL.md`. The hosting work doesn't touch any module README. The two new scripts (`refresh_active_listings.py` and the existing `attom_comp_store_backfill.py`) live under `scripts/data_quality/` which has no README — don't introduce one unless it would clearly help future sessions.
- **NO AUTH OR ANALYTICS WORK IN THIS CYCLE.** Auth is Cycle 6's gate; analytics beyond the existing turn-trace observability is post-launch.

## Verification

- Sub-stream 1a: deploy URLs return 200 on `/healthz`; canonical-fixture chat turn completes end-to-end on the deployed pair.
- Sub-stream 1b: full-pool match rate ≥ 80%; sqft corrections count ≥ 1500 (anything materially below the 50-row sample's 64% rate flags an issue); 50-row Cycle 2A spot-check shows median APE materially better than the 28.6% baseline.
- Sub-stream 1c: each of the 8 towns has ≥ 10 active listings; town spelling variants are consolidated; 5 random spot-checks against Zillow source URLs match.
- Pre-existing pytest baseline (16 failing tests as of 2026-04-30 Cycle 2A) unchanged. No code under `briarwood/` is modified, so this is automatic.
- ROADMAP §3.8 has three new "Cycle 1a/1b/1c outcome (YYYY-MM-DD — LANDED)" notes appended.
- DECISIONS.md gets ONE new entry: "YYYY-MM-DD — Launch Cycle 1 (Sunday Scaffold) landed (§3.8)" recording the live URLs, the new comp-store + listings counts, and any deviations from this prompt's plan.
- CURRENT_STATE.md "May 2026 Launch (active)" section updated: replace the "in flight / scaffolding-pending" framing with the actual landed-state framing once the cycle closes.

## Open Design Decisions to surface to owner if encountered

- **Custom domain.** This cycle uses default subdomains. If the owner decides during Cycle 1a that they want a custom domain, surface it as an extension (not a substitution) — the default subdomain still works while DNS propagates.
- **Postgres migration.** If Fly's SQLite-on-volume hits an unexpected snag during Cycle 1a, the fallback is porting `api/store.py` to Postgres. This is ~1–2 days of work and would slip Sunday. Surface immediately rather than hacking around.
- **SearchApi quota.** If the quota bump owner mentioned isn't yet in place when 1c runs, the script can either (a) fetch what fits in the current quota and document the gap, or (b) hold for the bump. Owner should pick.
- **Town canonicalization.** The 2026-04-28 ROADMAP entry says "consolidate spelling variants." The implementation choice (canonical-string lookup table vs. fuzzy match) lives in the new refresh script. Default to a canonical-string lookup table (`{"avon-by-the-sea": "Avon By The Sea", ...}`) and surface to owner if a row doesn't fit any known canonical form.

## Estimate

- Cycle 1a: 2–4 hours of pairing time. Owner-driven; bounded by external waits (account signup, payment hold, DNS if custom domain). On the default-subdomain path with no custom domain, zero external waits.
- Cycle 1b: 35–60 minutes wall-clock for the full pool, plus 30 minutes for diff review and promotion.
- Cycle 1c: 60–90 minutes for investigation + script + run + spot-check.
- Total LLM-development time across all three: 4–8 hours of agent work, parallelizable. Total wall-clock: half a day to a day if executed sequentially; less if 1b and 1c run in parallel sub-agents while 1a is paired interactively.

## Risk

- Cycle 1a external-wait risk: zero on default-subdomain path; high on custom-domain path. Default-subdomain is the locked decision.
- Cycle 1b: ATTOM rate-limit risk minimal per the 50-row sample; the script may need a sleep-on-429 hardening before the full run.
- Cycle 1c: SearchApi quota risk if the bump isn't in place; the script handles partial completion gracefully (streaming write).
- Across the cycle: risk of touching application code in a way that breaks the deploy. The hard constraints above mitigate this.

After Cycle 1 closes, Cycle 2 opens: re-run `scripts/eval/backtest_comparable_sales.py` and `scripts/eval/backtest_current_value.py` against the densified comp store, write `docs/MODEL_BACKTEST_<date>.md` (Cycle 2 version), and decide the launch-gate accuracy bar empirically. The Cycle 2 prompt for that work is preserved in conversation history and can be regenerated; this prompt closes when Cycle 1's three sub-streams all post their LANDED outcome notes.
