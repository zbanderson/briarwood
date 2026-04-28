// AI-Native Foundation Stage 3 — per-turn drill-down.
//
// Server component. Renders the full TurnManifest for one turn plus
// any feedback rows that joined to its messages. Highlights the
// `feedback:recent-thumbs-down-influenced-synthesis` notes tag — that's
// the closure-loop audit affordance from Stage 2 made visible.
//
// Reached via deep-link from /admin (slowest / costliest tables) or by
// pasting a turn_id directly. Same env-gate as the parent route.

import Link from "next/link";
import {
  AdminDisabledError,
  type AdminTurnDetail,
  type ModuleRunRow,
  type LlmCallSummaryRow,
  type ToolCallRow,
  type TurnFeedbackRow,
  getAdminTurnDetail,
} from "@/lib/admin-api";

export const dynamic = "force-dynamic";

const SYNTHESIS_HINT_TAG = "feedback:recent-thumbs-down-influenced-synthesis";

export default async function AdminTurnPage({
  params,
}: {
  params: Promise<{ turn_id: string }>;
}) {
  const { turn_id } = await params;
  let detail: AdminTurnDetail | null = null;
  let disabled = false;
  let errorMessage: string | null = null;

  try {
    detail = await getAdminTurnDetail(turn_id);
  } catch (err) {
    if (err instanceof AdminDisabledError) {
      disabled = true;
    } else {
      errorMessage = (err as Error).message;
    }
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-10 text-[var(--color-text)]">
      <nav className="mb-6 text-xs text-[var(--color-text-muted)]">
        <Link href="/admin" className="hover:text-[var(--color-text)]">
          ← admin
        </Link>
      </nav>

      {disabled && (
        <div
          role="alert"
          className="rounded-lg border border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)] p-6 text-sm text-[var(--color-text-muted)]"
        >
          <p className="font-medium text-[var(--color-text)]">
            Admin surface disabled.
          </p>
          <p className="mt-2">
            Set <code className="font-mono">BRIARWOOD_ADMIN_ENABLED=1</code> on
            the FastAPI process and restart, then refresh this page.
          </p>
        </div>
      )}

      {errorMessage && !disabled && (
        <div
          role="alert"
          className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-6 text-sm text-rose-100"
        >
          <p className="font-medium">Couldn&rsquo;t load turn detail.</p>
          <p className="mt-2 font-mono text-xs opacity-80">{errorMessage}</p>
          <p className="mt-2 font-mono text-xs opacity-60">turn_id: {turn_id}</p>
        </div>
      )}

      {detail && <TurnDetailBody detail={detail} />}
    </main>
  );
}

function TurnDetailBody({ detail }: { detail: AdminTurnDetail }) {
  const { trace, feedback } = detail;
  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-mono text-lg">{trace.turn_id}</h1>
        <p className="mt-1 text-sm text-[var(--color-text-muted)]">
          {trace.answer_type ?? "—"}
          {" · "}
          {trace.dispatch ?? "—"}
          {" · "}
          {formatMs(trace.duration_ms_total)}
          {" · "}
          conf {trace.confidence === null ? "—" : trace.confidence.toFixed(2)}
        </p>
        <p className="mt-1 text-xs text-[var(--color-text-faint)]">
          started {formatTimestamp(trace.started_at)}
          {trace.conversation_id && (
            <>
              {" · "}
              <Link
                href={`/c/${trace.conversation_id}`}
                className="underline-offset-4 hover:underline"
              >
                conversation {trace.conversation_id.slice(0, 10)}
              </Link>
            </>
          )}
        </p>
      </header>

      <Section title="User text">
        <pre className="whitespace-pre-wrap rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)] p-3 text-sm">
          {trace.user_text}
        </pre>
      </Section>

      {trace.classification_reason && (
        <Section title="Classification reason">
          <p className="text-sm text-[var(--color-text-muted)]">
            {trace.classification_reason}
          </p>
        </Section>
      )}

      {feedback.length > 0 && <FeedbackBlock rows={feedback} />}
      <NotesBlock notes={trace.notes ?? []} />
      <ModulesBlock rows={trace.modules_run ?? []} />
      <LlmCallsBlock rows={trace.llm_calls_summary ?? []} />
      {(trace.tool_calls ?? []).length > 0 && (
        <ToolCallsBlock rows={trace.tool_calls} />
      )}

      <details className="group rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)] p-3 text-sm">
        <summary className="cursor-pointer select-none font-mono text-xs text-[var(--color-text-muted)]">
          Raw manifest JSON
        </summary>
        <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-xs">
          {JSON.stringify(trace, null, 2)}
        </pre>
      </details>
    </div>
  );
}

function FeedbackBlock({ rows }: { rows: TurnFeedbackRow[] }) {
  return (
    <Section title="Feedback">
      <ul className="space-y-2 text-sm">
        {rows.map((r) => (
          <li
            key={r.message_id}
            className="rounded-md border border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)] p-3"
          >
            <div className="flex items-baseline justify-between">
              <span
                className={
                  "font-mono text-xs uppercase " +
                  (r.rating === "down"
                    ? "text-rose-300"
                    : "text-emerald-300")
                }
              >
                {r.rating}
              </span>
              <span className="text-xs text-[var(--color-text-faint)]">
                {formatTimestampMs(r.updated_at)}
              </span>
            </div>
            {r.comment && (
              <p className="mt-1 text-sm text-[var(--color-text)]">
                {r.comment}
              </p>
            )}
            <p className="mt-1 font-mono text-xs text-[var(--color-text-faint)]">
              {r.message_id}
            </p>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function NotesBlock({ notes }: { notes: string[] }) {
  if (notes.length === 0) {
    return null;
  }
  return (
    <Section
      title="Notes"
      subtitle="Free-text breadcrumbs from the turn manifest. Synthesis-hint markers are highlighted."
    >
      <ul className="space-y-1 text-xs font-mono">
        {notes.map((note, i) => {
          const isHint = note.includes(SYNTHESIS_HINT_TAG);
          return (
            <li
              key={i}
              className={
                "rounded-sm px-2 py-1 " +
                (isHint
                  ? "border border-amber-500/30 bg-amber-500/10 text-amber-100"
                  : "text-[var(--color-text-muted)]")
              }
            >
              {note}
              {isHint && (
                <span className="ml-2 text-[10px] uppercase tracking-wider text-amber-200">
                  feedback loop
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

function ModulesBlock({ rows }: { rows: ModuleRunRow[] }) {
  if (rows.length === 0) {
    return null;
  }
  return (
    <Section title="Modules run">
      <table className="w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-[var(--color-text-faint)]">
          <tr>
            <th className="py-1 pr-3">name</th>
            <th className="py-1 pr-3">source</th>
            <th className="py-1 pr-3">mode</th>
            <th className="py-1 pr-3">conf</th>
            <th className="py-1 pr-3">ms</th>
            <th className="py-1 pr-3">warnings</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={i}
              className="border-t border-[var(--color-border-subtle)]"
            >
              <td className="py-1 pr-3 font-mono text-xs">{r.name}</td>
              <td className="py-1 pr-3 text-[var(--color-text-muted)]">
                {r.source ?? "—"}
              </td>
              <td className="py-1 pr-3 text-[var(--color-text-muted)]">
                {r.mode ?? "—"}
              </td>
              <td className="py-1 pr-3 tabular-nums">
                {r.confidence === null || r.confidence === undefined
                  ? "—"
                  : r.confidence.toFixed(2)}
              </td>
              <td className="py-1 pr-3 tabular-nums">
                {formatMs(r.duration_ms ?? null)}
              </td>
              <td className="py-1 pr-3 tabular-nums">
                {r.warnings_count ?? 0}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  );
}

function LlmCallsBlock({ rows }: { rows: LlmCallSummaryRow[] }) {
  if (rows.length === 0) {
    return null;
  }
  const totalDuration = rows.reduce(
    (acc, r) => acc + (r.duration_ms ?? 0),
    0,
  );
  return (
    <Section
      title="LLM calls"
      subtitle="Per-call cost lives in data/llm_calls.jsonl (joined separately by turn_id). Summary here is duration + status only."
    >
      <table className="w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-[var(--color-text-faint)]">
          <tr>
            <th className="py-1 pr-3">surface</th>
            <th className="py-1 pr-3">provider</th>
            <th className="py-1 pr-3">model</th>
            <th className="py-1 pr-3">status</th>
            <th className="py-1 pr-3">attempts</th>
            <th className="py-1 pr-3">ms</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={i}
              className="border-t border-[var(--color-border-subtle)]"
            >
              <td className="py-1 pr-3 font-mono text-xs">{r.surface}</td>
              <td className="py-1 pr-3 text-[var(--color-text-muted)]">
                {r.provider ?? "—"}
              </td>
              <td className="py-1 pr-3 text-[var(--color-text-muted)]">
                {r.model ?? "—"}
              </td>
              <td className="py-1 pr-3 text-[var(--color-text-muted)]">
                {r.status ?? "—"}
              </td>
              <td className="py-1 pr-3 tabular-nums">{r.attempts ?? 0}</td>
              <td className="py-1 pr-3 tabular-nums">
                {formatMs(r.duration_ms ?? null)}
              </td>
            </tr>
          ))}
          <tr className="border-t border-[var(--color-border-subtle)] text-xs uppercase tracking-wide text-[var(--color-text-faint)]">
            <td className="py-1 pr-3">total</td>
            <td className="py-1 pr-3" />
            <td className="py-1 pr-3" />
            <td className="py-1 pr-3" />
            <td className="py-1 pr-3 tabular-nums">{rows.length}</td>
            <td className="py-1 pr-3 tabular-nums">
              {formatMs(totalDuration)}
            </td>
          </tr>
        </tbody>
      </table>
    </Section>
  );
}

function ToolCallsBlock({ rows }: { rows: ToolCallRow[] }) {
  return (
    <Section title="Tool calls">
      <table className="w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-[var(--color-text-faint)]">
          <tr>
            <th className="py-1 pr-3">name</th>
            <th className="py-1 pr-3">status</th>
            <th className="py-1 pr-3">ms</th>
            <th className="py-1 pr-3">error</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={i}
              className="border-t border-[var(--color-border-subtle)]"
            >
              <td className="py-1 pr-3 font-mono text-xs">{r.name}</td>
              <td className="py-1 pr-3 text-[var(--color-text-muted)]">
                {r.status ?? "—"}
              </td>
              <td className="py-1 pr-3 tabular-nums">
                {formatMs(r.duration_ms ?? null)}
              </td>
              <td className="py-1 pr-3 text-[var(--color-text-muted)]">
                {r.error_type ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  );
}

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <header className="mb-2">
        <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
        {subtitle && (
          <p className="text-xs text-[var(--color-text-muted)]">{subtitle}</p>
        )}
      </header>
      {children}
    </section>
  );
}

function formatMs(ms: number | null): string {
  if (ms === null || !Number.isFinite(ms)) return "—";
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${Math.round(ms)}ms`;
}

function formatTimestamp(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toISOString();
}

function formatTimestampMs(epochMs: number): string {
  return new Date(epochMs).toISOString();
}
