# Hosting Comparison — API side (Briarwood)

**Date:** 2026-04-30
**Author:** Claude (deploy-scaffolding session)
**Scope:** Where to run the FastAPI `api/` + Python `briarwood/` package for the EOD Sunday 2026-05-04 launch. Vercel for `web/` is already locked.
**Recommendation up-front:** **Fly.io.**

---

## TL;DR

| Dimension                    | Railway                                | Fly.io                              | Render                              |
|------------------------------|----------------------------------------|-------------------------------------|-------------------------------------|
| SQLite + persistent volume   | Volumes exist, awkward                 | **First-class, well-documented**    | Disks exist, Postgres-biased        |
| JSONL/JSON read+write        | Volume                                 | **Volume**                          | Disk                                |
| SSE / long-lived requests    | OK (no hard cap)                       | **OK (no hard cap on Machines)**    | OK on paid; free tier idles 15 min  |
| Cold-start                   | Always-on                              | **Always-on**                       | Free tier sleeps; paid is always-on |
| Python 3.13/3.14 build       | Auto (Nixpacks) or Dockerfile          | **Dockerfile (clean, deterministic)** | Auto or Dockerfile                |
| Pricing for MVP (1-100 DAU)  | $5 Hobby + ~$5-10 usage = **~$10-15/mo** | **~$5-10/mo (one shared-cpu-1x VM + 1 GB volume)** | $7/mo Starter web service          |
| Custom domain + SSL          | ~5-15 min                              | ~5-15 min                           | ~5-15 min                           |
| Secrets management           | Dashboard env-var UI                   | `fly secrets set` + dashboard       | Dashboard env-var UI                |
| Time-to-first-deploy         | ~10-20 min                             | **~10-20 min**                      | ~10-20 min                          |
| Volume durability            | Backed disks, no automatic snapshots   | Backed disks, **daily snapshots**   | Backed disks                        |

**Recommendation:** **Fly.io.** It is the only host of the three where SQLite-on-a-persistent-volume is the documented happy path, not the workaround. That matters because all of `data/web/conversations.db`, `data/saved_properties/`, `data/learning/intelligence_feedback.jsonl`, `data/outcomes/property_outcomes.jsonl`, and the comp ground-truth JSONs live on the local filesystem today and are read-and-written by request handlers. Switching to managed Postgres in 4 days is not a launch-shaped problem.

---

## Section 1 — SQLite vs Postgres: the decision driver

The app uses SQLite at `data/web/conversations.db` via `api/store.py` (line 19: `Path(__file__).resolve().parents[1] / "data" / "web" / "conversations.db"`). The schema covers:

- `conversations`, `messages` (chat persistence)
- `turn_traces` (router/dispatch audit)
- `feedback` (Stage 2 thumbs up/down)
- (and several model-alignment / intelligence tables — see `api/store.py`)

The path is overridable via `BRIARWOOD_WEB_DB`, but the DB is a single file. It is opened with a thread `Lock` and a per-request connection. There is no Postgres adapter, no SQLAlchemy abstraction, and no migration tool. Porting to Postgres before launch would mean:

- Rewriting `api/store.py` to use `asyncpg` or `sqlalchemy[asyncio]`
- Writing a one-time migration of the existing SQLite contents (the local DB has been collecting traces since Stage 1)
- Re-testing every endpoint that reads the store (`/api/conversations`, `/api/feedback`, `/api/admin/*`, the chat route's `attach_turn_metrics` path)

That is a 1-2-day project on top of the deploy itself, and it touches application code — explicitly out of scope for this handoff.

**Fly.io's persistent volume model is the right shape for this app.** A `fly volume` mounts at a path on the VM filesystem, survives deploys, and is backed by NVMe storage in the same region as the Machine. SQLite's single-writer model is fine for one-VM deployments — and Briarwood is a single-VM app. Railway and Render both *technically* support volumes, but the docs, defaults, and ecosystem all assume Postgres for app state. The friction is real: on Railway, volumes don't auto-attach in some templates; on Render, the disk add-on is gated behind specific service types.

**Tradeoff to flag:** SQLite on a single Fly Machine means **no horizontal scaling** of the API beyond one instance. That is the right tradeoff for a launch with 1-100 DAU. When traffic justifies a second VM, the path forward is LiteFS (Fly's SQLite replication layer) or migrating to Postgres on Fly. Neither needs to happen before Sunday.

## Section 2 — JSONL ground-truth files and saved-property writes

These are the runtime read+write paths the API needs:

| Path                                                  | Read at runtime | Written at runtime | Size today |
|-------------------------------------------------------|-----------------|--------------------|------------|
| `data/comps/sales_comps.json`                         | Yes             | Curation scripts only (offline) | ~3.6 MB |
| `data/comps/active_listings.json`                     | Yes             | Curation scripts only (offline) | small |
| `data/saved_properties/<slug>/inputs.json` + others   | Yes             | **Yes** — every "save listing" + intake run | ~1.4 MB |
| `data/local_intelligence/signals/*.json`              | Yes             | **Yes** — auto-research updates | ~2 MB |
| `data/learning/intelligence_feedback.jsonl`           | Yes             | **Yes** — every feedback action | ~5.4 MB |
| `data/outcomes/property_outcomes.jsonl`               | Yes             | Yes (Stage 4 backfill) | small |
| `data/llm_calls.jsonl`                                | No (gitignored sink) | **Yes** — every LLM call | small, append-only |
| `data/eval/*.jsonl`                                   | Read-only, dev surface | Backfill scripts only | ~9 MB |
| `data/agent_artifacts/<session>/`                     | Yes (mounted as `/artifacts`) | **Yes** — chart HTML per turn | ~6.4 MB |
| `data/cache/searchapi_zillow/*.json`                  | Yes             | **Yes** — cache fills on miss | ~6.7 MB |
| `data/public_records/`                                | No (offline curation only) | No | 412 MB — **gitignored, do not ship** |

**Conclusion:** the API needs a single persistent volume mounted at `/app/data` that survives deploys. Object storage (S3/R2) is not necessary for launch — these files are small, accessed frequently, and the codebase reads them as plain `Path("data/...")` opens. Migrating them to S3 would mean code changes; migrating them to a volume is zero code changes.

**Fly volume sizing:** start at 1 GB (current `data/` minus `public_records/` is ~37 MB, with 10x headroom for cache + artifact growth over the launch window). $0.15/GB/month on Fly.

## Section 3 — Background tasks and SSE

Confirmed by reading `api/main.py` and `api/pipeline_adapter.py`:

- All work is request-scoped. `_event_source` is an async generator that yields SSE chunks for the duration of one chat turn. No `BackgroundTask`, no `apscheduler`, no Celery, no separate worker process.
- The longest a single SSE stream stays open is bounded by the dispatch flow (decision/browse/scout) — order of tens of seconds for a full decision cascade with comps + research, occasionally more.
- **All three hosts handle this fine** (no provider caps SSE under 60 seconds at the proxy layer for paid tiers). This is not a host-pick driver.

**Fly note:** Fly Machines run the process directly; the proxy layer (Anycast → Fly Proxy → VM) does not buffer. The existing `Cache-Control: no-cache, no-transform` and `X-Accel-Buffering: no` headers in `api/main.py` are sufficient.

## Section 4 — Cold-start vs always-on

- **Render free tier:** sleeps after 15 min of inactivity; first cold request takes ~30-60s. **Disqualifying for launch demo.** Render *paid* Starter ($7/mo) is always-on — comparable to the other two.
- **Railway:** always-on on Hobby. No cold starts.
- **Fly.io:** always-on by default; can opt into auto-stop/auto-start to save money, but for launch leave on.

## Section 5 — Pricing for 1-100 DAU launch

Concrete monthly cost for a single API instance + a small volume + outbound traffic:

- **Fly.io:** 1 × `shared-cpu-1x` Machine (1 GB RAM, always-on) ≈ $1.94/mo + 1 GB volume ≈ $0.15/mo + ~$0-2 outbound = **$2-5/mo**. With a slight bump to `shared-cpu-2x` (2 GB RAM, safer for the LLM-call burstiness): **~$5-10/mo**.
- **Railway:** Hobby plan $5/mo + usage (1 GB RAM service ≈ $5-7/mo metered) = **$10-15/mo**.
- **Render:** Starter web service $7/mo + 1 GB disk $1/mo = **$8/mo**.

All three are under $20/mo. Pricing is not a meaningful tiebreaker.

## Section 6 — Custom domain + SSL

All three providers issue Let's Encrypt certs automatically once a CNAME or A record points at them. Mechanics:

- **Vercel (web):** add domain in dashboard → Vercel emits a CNAME target → DNS propagation 1-30 min → cert provisions in ~1-2 min after propagation.
- **Fly.io (api):** `fly certs add api.example.com` → emits CNAME or A/AAAA targets → DNS prop → cert auto-provisions in ~30s after prop.
- **Railway:** identical flow.
- **Render:** identical flow.

**The Sunday-deadline risk is DNS propagation, not the host.** Whatever provider is picked, the owner should configure DNS Friday or earlier. A registrar with low TTLs (Cloudflare, Namecheap) propagates in minutes; some legacy registrars take 4-24 hours. **The owner has not stated whether a custom domain is even in scope** — see launch checklist for the branch.

## Section 7 — Secrets management

All three offer dashboard env-var UI plus a CLI. No meaningful difference for the seven keys this app needs (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `ATTOM_API_KEY`, `GOOGLE_MAPS_API_KEY`, `TAVILY_API_KEY`, `SEARCHAPI_API_KEY`, `BRIARWOOD_WEB_DB`).

**Critical hygiene flag:** the local `.env` at the repo root **contains live production-grade secrets** for OpenAI, Anthropic, ATTOM, Google Maps, Mapbox, Tavily, and SearchAPI. The `.env` file is correctly gitignored and is not in git history (verified). However, the secrets exist in the working tree and have been visible to multiple agent sessions. **The owner should rotate at minimum the OpenAI and Anthropic keys before launch**, since those are the highest-cost-of-compromise. The launch checklist includes this step.

---

## Recommendation

**Use Fly.io for the API side.**

Reasons in priority order:
1. SQLite-on-volume is the documented happy path, not a workaround. Zero application-code changes. (Section 1 — load-bearing.)
2. Pricing is the lowest of the three for the launch traffic profile.
3. The Dockerfile-based deploy is deterministic; what builds locally builds on Fly.
4. Daily volume snapshots come for free — useful insurance for `conversations.db` during the launch window.

**When you would override this choice:**
- If the owner already has deep Railway or Render familiarity, the time-savings of "use the host I know" can outweigh the 10% cost delta.
- If the owner wants to migrate to Postgres before launch anyway, all three are equivalent and the choice collapses to "which dashboard do you like."

**What this comparison does NOT recommend:**
- Render free tier — disqualified by cold starts.
- Heroku, AWS Elastic Beanstalk, Google Cloud Run — out of scope per the prompt and not faster to deploy than Fly.
- Vercel for the API (FastAPI on Vercel serverless) — Vercel's Python runtime tops out at ~10s execution time and does not support persistent SQLite. Disqualified by SSE + state shape.

---

## Open question for the owner before deploy

**Is a custom domain in scope for Sunday?** If yes, what is the registrar and what is the desired hostname? The default flow uses `<app>.vercel.app` and `<app>.fly.dev`, both of which work at launch with no DNS. Adding a custom domain adds 30-60 minutes plus DNS propagation wait. Decide before Friday so DNS has time to propagate.
