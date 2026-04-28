// Server-side admin API client for the FastAPI bridge.
// Used from the admin Server Components (web/src/app/admin/...).
//
// Mirrors the api.ts pattern, but each call needs the
// BRIARWOOD_ADMIN_ENABLED env var to be set on the FastAPI side.
// When the gate is closed FastAPI returns 404 — the admin pages
// surface a clean "admin disabled" notice instead of crashing.

import { apiBaseUrl } from "@/lib/api";

export type LatencyRow = {
  answer_type: string;
  count: number;
  avg_ms: number;
  p50_ms: number | null;
  p95_ms: number | null;
};

export type CostRow = {
  surface: string;
  count: number;
  total_cost_usd: number;
  avg_duration_ms: number | null;
  errors: number;
};

export type ThumbsSummary = {
  up: number;
  down: number;
  total: number;
  ratio: number | null;
};

export type AdminMetrics = {
  days: number;
  since_iso: string;
  latency_by_answer_type: LatencyRow[];
  cost_by_surface: CostRow[];
  thumbs: ThumbsSummary;
};

export type SlowTurnRow = {
  turn_id: string;
  conversation_id: string | null;
  started_at: number;
  duration_ms_total: number;
  answer_type: string | null;
  confidence: number | null;
  dispatch: string | null;
  user_text: string;
};

export type CostlyTurnRow = {
  turn_id: string;
  total_cost_usd: number;
  call_count: number;
};

export type AdminRecentTurns = {
  days: number;
  limit: number;
  slowest: SlowTurnRow[];
  costliest: CostlyTurnRow[];
};

export type ModuleRunRow = {
  name: string;
  source?: string | null;
  mode?: string | null;
  confidence?: number | null;
  duration_ms?: number | null;
  warnings_count?: number | null;
};

export type LlmCallSummaryRow = {
  surface: string;
  provider?: string | null;
  model?: string | null;
  status?: string | null;
  duration_ms?: number | null;
  attempts?: number | null;
};

export type ToolCallRow = {
  name: string;
  duration_ms?: number | null;
  status?: string | null;
  error_type?: string | null;
};

export type TurnTrace = {
  turn_id: string;
  conversation_id: string | null;
  started_at: number;
  duration_ms_total: number;
  answer_type: string | null;
  confidence: number | null;
  classification_reason: string | null;
  dispatch: string | null;
  user_text: string;
  wedge: Record<string, unknown> | null;
  modules_run: ModuleRunRow[];
  modules_skipped: Array<Record<string, unknown>>;
  llm_calls_summary: LlmCallSummaryRow[];
  tool_calls: ToolCallRow[];
  notes: string[];
};

export type TurnFeedbackRow = {
  message_id: string;
  rating: "up" | "down";
  comment: string | null;
  created_at: number;
  updated_at: number;
};

export type AdminTurnDetail = {
  trace: TurnTrace;
  feedback: TurnFeedbackRow[];
};

export class AdminDisabledError extends Error {
  constructor() {
    super("admin disabled");
    this.name = "AdminDisabledError";
  }
}

async function adminFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${apiBaseUrl}${path}`, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (res.status === 404) {
    // Treat 404 as the "admin disabled" signal. The endpoint also
    // returns 404 for genuinely-missing turn ids; callers that need to
    // distinguish should check first via the metrics endpoint.
    throw new AdminDisabledError();
  }
  if (!res.ok) {
    throw new Error(`Admin ${path} failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

export function getAdminMetrics(days = 7) {
  return adminFetch<AdminMetrics>(`/api/admin/metrics?days=${days}`);
}

export function getAdminRecentTurns(days = 7, limit = 10) {
  return adminFetch<AdminRecentTurns>(
    `/api/admin/turns/recent?days=${days}&limit=${limit}`,
  );
}

export function getAdminTurnDetail(turnId: string) {
  return adminFetch<AdminTurnDetail>(
    `/api/admin/turns/${encodeURIComponent(turnId)}`,
  );
}
