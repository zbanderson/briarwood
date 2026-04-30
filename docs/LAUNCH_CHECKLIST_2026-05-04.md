# Launch Checklist — Briarwood EOD 2026-05-04 (Sunday)

**Target stack:** Vercel (web/) + Fly.io (api/) — see `docs/HOSTING_COMPARISON_2026-04-30.md`.
**Owner runs all commands.** Claude Code does not have access to user accounts, payment methods, or DNS providers.

Each step is annotated with **{wall-clock estimate}** and **[EXTERNAL WAIT]** when the step has a propagation/verification window outside the owner's control.

> Symbol key: `→` = action; `?` = decision required from owner; `!` = risk to flag.

---

## Pre-flight (run on Friday/Saturday — do NOT save for Sunday)

### P-1. Decide on a custom domain {5 min}
- ? Does the launch require a custom domain (e.g. `briarwood.app`, `app.briarwood.com`), or is `briarwood.vercel.app` + `briarwood-api.fly.dev` acceptable?
- ! If yes, which registrar holds the domain today, and what is the TTL on existing records?
- → If yes, complete steps D-1 through D-4 below before Sunday morning. If no, skip the D-* section entirely.

### P-2. Rotate exposed API keys {10-30 min} [EXTERNAL WAIT — dashboards]
- ! The local `.env` contains live keys for OpenAI, Anthropic, ATTOM, Google Maps, Mapbox, Tavily, and SearchAPI. The `.env` file is correctly gitignored, but the secrets exist in the working tree of multiple agent sessions.
- → At minimum, rotate **OPENAI_API_KEY** and **ANTHROPIC_API_KEY** (highest cost-of-compromise) before issuing them as Fly secrets.
- → Rotate the others if any agent session has been shared screen-recorded or pushed transcripts externally.
- [EXTERNAL WAIT] Some providers take 30s-2min to invalidate the old key.

### P-3. Verify the `.env.example` is current {5 min}
- → Confirm `.env.example` lists every key the app actually reads. The current file is missing `GOOGLE_MAPS_API_KEY`, `SEARCHAPI_API_KEY`, and `BRIARWOOD_WEB_DB`. This is not a blocker for deploy (Fly secrets are set explicitly), but flag for post-launch cleanup in `ROADMAP.md`.

### P-4. Confirm `data/` snapshot for first deploy {5 min}
- → The Dockerfile ships `data/comps`, `data/local_intelligence`, `data/eval`, `data/town_county` as seed datasets. On first deploy these populate the empty Fly volume.
- → `data/saved_properties/`, `data/learning/`, `data/web/conversations.db`, `data/llm_calls.jsonl`, `data/agent_artifacts/`, `data/cache/` are intentionally **excluded** from the image (see `.dockerignore`) and start empty on the volume.
- ? Is that the intended launch state? If the owner wants the dev `conversations.db` and `data/saved_properties/*` content on the prod volume for the demo, that's a separate one-time `fly ssh sftp` upload after first deploy. Decide before launch day.

---

## Phase A — Account creation {15-25 min total} [EXTERNAL WAIT — email verification, payment-method holds]

### A-1. Vercel account {5-10 min} [EXTERNAL WAIT]
- → Sign up at https://vercel.com using GitHub auth (faster than email).
- [EXTERNAL WAIT] First-time accounts may face a 1-2 min anti-fraud hold.
- → Free Hobby plan is sufficient for launch traffic.

### A-2. Fly.io account {5-10 min} [EXTERNAL WAIT — payment method]
- → Sign up at https://fly.io.
- → Install CLI locally: `curl -L https://fly.io/install.sh | sh`
- → `fly auth login`
- [EXTERNAL WAIT] Fly requires a credit card on file even for free-tier launches. Card pre-auth holds typically clear in seconds, occasionally minutes.
- ! If the card auth fails (international cards, prepaid cards), there's no easy fallback — switch to Railway as Plan B (see hosting comparison memo).

### A-3. (Optional) Domain registrar access {5 min}
- → Skip if step P-1 = "no custom domain."
- → Confirm dashboard access for the registrar (Cloudflare / Namecheap / Google Domains / etc.).

---

## Phase B — Repo connection {5-10 min}

### B-1. Push current `main` to GitHub if not already {2-5 min}
- → `git status` to confirm working tree state.
- ! There are uncommitted changes in the working tree per the start-of-session `git status`. Decide: commit a deploy-prep snapshot, or stash and deploy off a clean `main`.
- → `git push origin main`

### B-2. Connect Vercel to the repo {3-5 min}
- → Vercel dashboard → "Add New" → "Project" → Import the GitHub repo.
- → **Root Directory:** set to `web` (CRITICAL — Vercel must build from `web/`, not the repo root).
- → **Framework Preset:** Next.js (auto-detected from `web/next.config.ts`).
- → **Install command:** auto-detected from `web/vercel.json` (`pnpm install --frozen-lockfile`).
- → **Build command:** auto-detected (`pnpm build`).
- → Do NOT click "Deploy" yet — env vars come first (Phase C).

### B-3. Connect Fly to the repo (optional, manual deploy is fine) {2 min}
- → For launch, manual `fly deploy` from the owner's laptop is simplest.
- → Skip GitHub Actions / Fly auto-deploy until post-launch.

---

## Phase C — Env var configuration {15-20 min}

### C-1. Vercel env vars (web side) {5-10 min}
Add the following to Vercel project settings → Environment Variables (Production scope):

| Key                              | Value                                | Source                             |
|----------------------------------|--------------------------------------|------------------------------------|
| `BRIARWOOD_API_URL`              | `https://briarwood-api.fly.dev` (or custom domain) | Set after Fly deploy gives you the hostname |
| `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`| (rotated value from P-2)             | `.env` line 10                     |
| `NEXT_PUBLIC_MAPBOX_TOKEN`       | (rotated value from P-2)             | `.env` line 11                     |

! Note the `NEXT_PUBLIC_` prefix on the two map keys — those are intentionally browser-exposed (per `web/src/components/chat/inline-map.tsx`). Restrict the keys at the Google/Mapbox dashboard level (referrer allowlist for the Vercel domain) before going live.

### C-2. Fly secrets (api side) {5-10 min}
Run from the repo root on the owner's laptop:

```bash
fly secrets set \
  OPENAI_API_KEY="sk-proj-..." \
  ANTHROPIC_API_KEY="sk-ant-..." \
  ATTOM_API_KEY="..." \
  GOOGLE_MAPS_API_KEY="..." \
  TAVILY_API_KEY="..." \
  SEARCHAPI_API_KEY="..." \
  --app briarwood-api
```

! Use the rotated values from step P-2, NOT the values still in `.env`.
! `BRIARWOOD_WEB_DB`, `BRIARWOOD_ADMIN_ENABLED`, and the budget caps are set in `fly.toml` `[env]` and do NOT need to be set as secrets.

---

## Phase D — DNS + custom domain (skip entire section if no custom domain) {30-90 min} [EXTERNAL WAIT — DNS propagation]

### D-1. Add the API domain to Fly {5 min}
- → `fly certs add api.<your-domain> --app briarwood-api`
- → Fly prints the required CNAME or A/AAAA records.

### D-2. Add DNS records at the registrar {5-10 min}
- → Add the records Fly emitted.
- → Add a CNAME for `<your-domain>` pointing at `cname.vercel-dns.com.` (Vercel apex/www handling — verify in Vercel dashboard).

### D-3. Wait for DNS propagation [EXTERNAL WAIT — 5 min to 24 hours]
- ! **This is the highest-risk timing variable on the Sunday timeline.** Cloudflare/Namecheap/Google Domains typically propagate in 5-30 min. Some legacy registrars take 4-24 hours.
- → Verify with `dig api.<your-domain>` or `nslookup`. Don't proceed until both names resolve to the right targets.

### D-4. Verify SSL [EXTERNAL WAIT — 30s to 5 min after propagation]
- → `fly certs check api.<your-domain>` until status is "Issued".
- → Vercel auto-provisions the cert as soon as DNS resolves; check the dashboard.
- → Update `BRIARWOOD_API_URL` env var on Vercel to use the custom API domain. Redeploy web (Vercel → "Redeploy" without clearing build cache).

---

## Phase E — First deploys {15-25 min total}

### E-1. Deploy the API to Fly {10-15 min} [EXTERNAL WAIT — image build]
From the repo root on the owner's laptop:

```bash
fly apps create briarwood-api          # one-time, name must be globally unique
fly volumes create briarwood_data --region ewr --size 1 --app briarwood-api
fly deploy --app briarwood-api
```

[EXTERNAL WAIT] First build pulls Python 3.13 base image, installs deps, and pushes to Fly registry. Expect 5-10 min.
- ! If the unique app name `briarwood-api` is taken, edit `fly.toml` line 1 (`app = "..."`) before running these commands.

Verify:
```bash
fly status --app briarwood-api
curl https://briarwood-api.fly.dev/healthz   # should return {"status":"ok"}
```

### E-2. Deploy the web frontend to Vercel {5-10 min} [EXTERNAL WAIT — first build]
- → After the Fly URL is live and `BRIARWOOD_API_URL` is set on Vercel (Phase C-1), click "Deploy" in the Vercel dashboard.
- [EXTERNAL WAIT] First Vercel build typically 2-4 min for this app.
- → Verify `https://briarwood.vercel.app` (or custom domain) loads.

---

## Phase F — Smoke tests {10-15 min}

Run from the owner's browser and from `curl`. Each test is a quick pass/fail; if any fails, see Phase G rollback.

### F-1. API health endpoints
- → `curl https://briarwood-api.fly.dev/healthz` → expect `{"status":"ok"}`. {30s}
- → `curl https://briarwood-api.fly.dev/api/conversations` → expect `[]` (or existing list if dev DB was uploaded). {30s}

### F-2. Web app loads
- → Open the Vercel URL in a browser. {1 min}
- → Confirm the chat surface renders (no white-screen, no console errors about `BRIARWOOD_API_URL`).

### F-3. End-to-end chat turn (echo / SEARCH / BROWSE)
- → Type "Find me a starter home in Belmar" in the chat input. {1-2 min}
- → Expect: SSE stream begins within 1-2s, listings render, map renders, suggestions render.
- → Confirm in Vercel logs and Fly logs that no errors fired.

### F-4. End-to-end DECISION turn (the load-bearing path)
- → Click into a listing → click "Run analysis" (or paste a Zillow URL). {2-4 min}
- → Expect: SSE stream stays open for 20-90s, decision summary renders, comps render, scenarios render, a chart artifact iframes via `/artifacts/...`.
- ! This is the longest-running surface and the most likely to surface a deploy-shaped bug. Watch `fly logs --app briarwood-api` in parallel.

### F-5. Persistence
- → Reload the browser → confirm the conversation appears in the sidebar (= write hit `/data/web/conversations.db` on the volume). {1 min}
- → `fly ssh console -C "ls -la /app/data/web/"` → confirm `conversations.db` exists and has nonzero size.

### F-6. Feedback path
- → Click thumbs-up or thumbs-down on an assistant message. {1 min}
- → No error toast in browser; the row should appear in the volume:
  ```bash
  fly ssh console -C "sqlite3 /app/data/web/conversations.db 'SELECT * FROM feedback ORDER BY created_at DESC LIMIT 1;'"
  ```

---

## Phase G — Rollback procedure {2-5 min per layer}

### G-1. Vercel rollback
- → Vercel dashboard → Deployments → previous successful deploy → "Promote to Production". {2 min}
- → Vercel keeps deployments forever; this is the safest rollback in the stack.

### G-2. Fly rollback
- → `fly releases --app briarwood-api` to list versions. {30s}
- → `fly deploy --image registry.fly.io/briarwood-api:deployment-<previous-id> --app briarwood-api` to redeploy a prior image. {2-3 min}
- ! **Volume data is NOT rolled back.** SQLite migrations or schema changes that ran on the new release will persist on the volume even after image rollback. For launch this is fine (no migrations are running on first deploy), but flag it for post-launch.

### G-3. Full take-down (emergency)
- → Vercel: pause the production deployment in dashboard. {1 min}
- → Fly: `fly scale count 0 --app briarwood-api` to stop the API. {30s}
- → To bring back: `fly scale count 1 --app briarwood-api` and re-enable Vercel.

---

## Open-question summary for the owner

Before Sunday, the owner needs answers to:

1. **Custom domain in scope?** (drives whether Phase D runs at all)
2. **Pre-populate the prod Fly volume with the dev `conversations.db` and `data/saved_properties/`?** (drives a one-time `fly ssh sftp` step after E-1)
3. **Which API keys get rotated before launch, and which get rotated post-launch?** (P-2 — recommend OpenAI + Anthropic at minimum)
4. **Is the uncommitted working-tree state intended for production, or should it be stashed first?** (B-1)

---

## Critical-path summary

If the owner has all four answers above and zero blockers, the realistic path-to-live is:

- **Friday:** P-1, P-2, P-3, P-4, A-1, A-2 (~45 min). DNS records added if D-* in scope. **DNS starts propagating overnight.**
- **Saturday:** B-* and C-* (~30 min). Verify env-var wiring with a Fly preview deploy if you want a dry run.
- **Sunday morning:** E-1, E-2, F-1 through F-6 (~60 min). Buffer the rest of the day for issue resolution.

**Total active work: ~2.5 hours. External wait windows: up to 24h for DNS.**
The Sunday-deadline risk is **DNS propagation on a custom domain**, full stop. If the owner skips the custom domain, the launch is a 2.5-hour straight shot with no external timing gates.
