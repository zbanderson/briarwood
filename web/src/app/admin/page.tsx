// AI-Native Foundation Stage 3 — top-line admin dashboard.
//
// Server component. Reads `/api/admin/metrics` + `/api/admin/turns/recent`
// at request time and renders a single-page summary of the last N days.
// Plain HTML/CSS bars (no chart library — owner-locked 2026-04-28; the
// chart-lib evaluation belongs with the UI reconstruction handoff per
// ROADMAP §3.4.7 sequencing note).
//
// The page is unlinked from the main UI by design (single-user local
// product); discoverable only via direct URL. Access additionally
// gated by BRIARWOOD_ADMIN_ENABLED on the FastAPI side; when the gate
// is closed the API returns 404 and we surface a clean disabled
// notice rather than a broken page.

import Link from "next/link";
import {
  AdminDisabledError,
  type AdminMetrics,
  type AdminRecentTurns,
  type CostRow,
  type CostlyTurnRow,
  type LatencyRow,
  type SlowTurnRow,
  type ThumbsSummary,
  getAdminMetrics,
  getAdminRecentTurns,
} from "@/lib/admin-api";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{ days?: string }>;

export default async function AdminPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const params = await searchParams;
  const days = clampDays(params.days);

  let metrics: AdminMetrics | null = null;
  let recent: AdminRecentTurns | null = null;
  let disabled = false;
  let errorMessage: string | null = null;

  try {
    [metrics, recent] = await Promise.all([
      getAdminMetrics(days),
      getAdminRecentTurns(days, 10),
    ]);
  } catch (err) {
    if (err instanceof AdminDisabledError) {
      disabled = true;
    } else {
      errorMessage = (err as Error).message;
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-10 text-[var(--color-text)]">
      <header className="mb-8 flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Briarwood admin
          </h1>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">
            Last {days} day{days === 1 ? "" : "s"} of chat-tier activity.
          </p>
        </div>
        <DaysSwitch active={days} />
      </header>

      {disabled && <DisabledNotice />}
      {errorMessage && <ErrorNotice message={errorMessage} />}

      {metrics && recent && (
        <div className="space-y-10">
          <ThumbsSection thumbs={metrics.thumbs} />
          <LatencySection rows={metrics.latency_by_answer_type} />
          <CostSection rows={metrics.cost_by_surface} />
          <SlowestTable rows={recent.slowest} />
          <CostliestTable rows={recent.costliest} />
        </div>
      )}
    </main>
  );
}

function clampDays(raw: string | undefined): number {
  const parsed = Number.parseInt(raw ?? "", 10);
  if (!Number.isFinite(parsed)) return 7;
  return Math.min(Math.max(parsed, 1), 90);
}

function DaysSwitch({ active }: { active: number }) {
  const choices = [1, 7, 30];
  return (
    <nav
      aria-label="Time window"
      className="inline-flex rounded-md border border-[var(--color-border-subtle)] text-xs"
    >
      {choices.map((d) => {
        const selected = active === d;
        return (
          <Link
            key={d}
            href={`/admin?days=${d}`}
            aria-current={selected ? "page" : undefined}
            className={
              "px-3 py-1.5 " +
              (selected
                ? "bg-[var(--color-surface)] text-[var(--color-text)]"
                : "text-[var(--color-text-muted)] hover:text-[var(--color-text)]")
            }
          >
            {d}d
          </Link>
        );
      })}
    </nav>
  );
}

function DisabledNotice() {
  return (
    <div
      role="alert"
      className="rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)] p-6 text-sm text-[var(--color-text-muted)]"
    >
      <p className="font-medium text-[var(--color-text)]">Admin surface disabled.</p>
      <p className="mt-2">
        Set <code className="font-mono">BRIARWOOD_ADMIN_ENABLED=1</code> on the
        FastAPI process and restart, then refresh this page.
      </p>
    </div>
  );
}

function ErrorNotice({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-6 text-sm text-rose-100"
    >
      <p className="font-medium">Couldn&rsquo;t load admin data.</p>
      <p className="mt-2 font-mono text-xs opacity-80">{message}</p>
    </div>
  );
}

function ThumbsSection({ thumbs }: { thumbs: ThumbsSummary }) {
  const ratioPct =
    thumbs.ratio === null ? null : Math.round(thumbs.ratio * 1000) / 10;
  return (
    <section>
      <SectionHeader title="Feedback" subtitle="Thumbs up / down on assistant turns." />
      <div className="grid grid-cols-3 gap-4">
        <StatCard label="Up" value={String(thumbs.up)} accent="up" />
        <StatCard label="Down" value={String(thumbs.down)} accent="down" />
        <StatCard
          label="Up ratio"
          value={ratioPct === null ? "—" : `${ratioPct}%`}
          subtext={
            thumbs.total === 0
              ? "Not enough data yet"
              : `${thumbs.total} rated turn${thumbs.total === 1 ? "" : "s"}`
          }
        />
      </div>
    </section>
  );
}

function StatCard({
  label,
  value,
  accent,
  subtext,
}: {
  label: string;
  value: string;
  accent?: "up" | "down";
  subtext?: string;
}) {
  const tone =
    accent === "up"
      ? "border-emerald-500/30"
      : accent === "down"
        ? "border-rose-500/30"
        : "border-[var(--color-border-subtle)]";
  return (
    <div
      className={
        "rounded-lg border bg-[var(--color-bg-sunken)] p-4 " + tone
      }
    >
      <div className="text-xs uppercase tracking-wide text-[var(--color-text-faint)]">
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {subtext && (
        <div className="mt-2 text-xs text-[var(--color-text-muted)]">{subtext}</div>
      )}
    </div>
  );
}

function LatencySection({ rows }: { rows: LatencyRow[] }) {
  if (rows.length === 0) {
    return <EmptySection title="Latency by answer_type" />;
  }
  const max = Math.max(...rows.map((r) => r.p95_ms ?? r.avg_ms));
  return (
    <section>
      <SectionHeader
        title="Latency by answer_type"
        subtitle="Wall-clock duration of each turn, grouped by classifier output."
      />
      <Table
        headers={["answer_type", "count", "avg", "p50", "p95"]}
        rows={rows.map((r) => ({
          key: r.answer_type,
          cells: [
            r.answer_type,
            String(r.count),
            formatMs(r.avg_ms),
            formatMs(r.p50_ms),
            formatMs(r.p95_ms),
          ],
          bar: r.p95_ms ?? r.avg_ms,
          barMax: max,
        }))}
      />
    </section>
  );
}

function CostSection({ rows }: { rows: CostRow[] }) {
  if (rows.length === 0) {
    return <EmptySection title="LLM cost by surface" />;
  }
  const max = Math.max(...rows.map((r) => r.total_cost_usd));
  return (
    <section>
      <SectionHeader
        title="LLM cost by surface"
        subtitle="Sum of per-call cost_usd from data/llm_calls.jsonl."
      />
      <Table
        headers={["surface", "calls", "total $", "avg ms", "errors"]}
        rows={rows.map((r) => ({
          key: r.surface,
          cells: [
            r.surface,
            String(r.count),
            formatUsd(r.total_cost_usd),
            r.avg_duration_ms === null ? "—" : formatMs(r.avg_duration_ms),
            String(r.errors),
          ],
          bar: r.total_cost_usd,
          barMax: max,
        }))}
      />
    </section>
  );
}

function SlowestTable({ rows }: { rows: SlowTurnRow[] }) {
  if (rows.length === 0) {
    return <EmptySection title="Slowest turns" />;
  }
  const max = Math.max(...rows.map((r) => r.duration_ms_total));
  return (
    <section>
      <SectionHeader
        title="Slowest turns"
        subtitle="Top 10 by duration_ms_total. Click into a row for the full manifest."
      />
      <Table
        headers={["turn", "answer_type", "duration", "user text"]}
        rows={rows.map((r) => ({
          key: r.turn_id,
          cells: [
            <Link
              key="link"
              href={`/admin/turn/${r.turn_id}`}
              className="font-mono text-xs underline-offset-4 hover:underline"
            >
              {r.turn_id.slice(0, 10)}
            </Link>,
            r.answer_type ?? "—",
            formatMs(r.duration_ms_total),
            <span key="t" className="line-clamp-1">
              {r.user_text}
            </span>,
          ],
          bar: r.duration_ms_total,
          barMax: max,
        }))}
      />
    </section>
  );
}

function CostliestTable({ rows }: { rows: CostlyTurnRow[] }) {
  if (rows.length === 0) {
    return (
      <EmptySection
        title="Highest-cost turns"
        note="Requires turn_id linkage on JSONL records (added 2026-04-28). New turns will appear here as they accumulate."
      />
    );
  }
  const max = Math.max(...rows.map((r) => r.total_cost_usd));
  return (
    <section>
      <SectionHeader
        title="Highest-cost turns"
        subtitle="Top 10 by summed per-call cost_usd. Joined to turn_traces via the JSONL turn_id field."
      />
      <Table
        headers={["turn", "calls", "total $"]}
        rows={rows.map((r) => ({
          key: r.turn_id,
          cells: [
            <Link
              key="link"
              href={`/admin/turn/${r.turn_id}`}
              className="font-mono text-xs underline-offset-4 hover:underline"
            >
              {r.turn_id.slice(0, 10)}
            </Link>,
            String(r.call_count),
            formatUsd(r.total_cost_usd),
          ],
          bar: r.total_cost_usd,
          barMax: max,
        }))}
      />
    </section>
  );
}

function SectionHeader({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: string;
}) {
  return (
    <header className="mb-3">
      <h2 className="text-base font-semibold tracking-tight">{title}</h2>
      {subtitle && (
        <p className="text-xs text-[var(--color-text-muted)]">{subtitle}</p>
      )}
    </header>
  );
}

function EmptySection({ title, note }: { title: string; note?: string }) {
  return (
    <section>
      <SectionHeader title={title} />
      <div className="rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)] px-4 py-6 text-sm text-[var(--color-text-muted)]">
        Not enough data yet — keep chatting.
        {note && <div className="mt-2 text-xs">{note}</div>}
      </div>
    </section>
  );
}

type TableRow = {
  key: string;
  cells: Array<React.ReactNode>;
  bar: number;
  barMax: number;
};

function Table({
  headers,
  rows,
}: {
  headers: string[];
  rows: TableRow[];
}) {
  return (
    <div className="overflow-hidden rounded-md border border-[var(--color-border-subtle)]">
      <table className="w-full text-sm">
        <thead className="bg-[var(--color-bg-sunken)] text-left text-xs uppercase tracking-wide text-[var(--color-text-faint)]">
          <tr>
            {headers.map((h) => (
              <th key={h} className="px-3 py-2 font-medium">
                {h}
              </th>
            ))}
            <th aria-hidden className="w-32 px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const pct = row.barMax > 0 ? (row.bar / row.barMax) * 100 : 0;
            return (
              <tr
                key={row.key}
                className="border-t border-[var(--color-border-subtle)]"
              >
                {row.cells.map((cell, i) => (
                  <td key={i} className="px-3 py-2 align-middle">
                    {cell}
                  </td>
                ))}
                <td className="px-3 py-2 align-middle">
                  <div
                    aria-hidden
                    className="h-1.5 rounded-full bg-[var(--color-surface)]"
                  >
                    <div
                      className="h-1.5 rounded-full bg-[var(--color-text-faint)]"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function formatMs(ms: number | null): string {
  if (ms === null || !Number.isFinite(ms)) return "—";
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${Math.round(ms)}ms`;
}

function formatUsd(value: number): string {
  if (value < 0.01) return `$${value.toFixed(4)}`;
  return `$${value.toFixed(2)}`;
}
