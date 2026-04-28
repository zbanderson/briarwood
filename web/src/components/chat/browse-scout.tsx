"use client";

import type { ScoutInsightItem } from "@/lib/chat/events";

// Phase 4c Cycle 1 — Section B ("WHAT YOU'D MISS") stub.
//
// Cycle 1 returns null for every input. Cycle 2 fills this in: when
// `insights` is non-empty, render a peer section with the existing
// `ScoutFinds` 0/1/2 cards; when empty, return null so the entire
// section disappears (no placeholder, no rule, no header).
//
// The stub still receives `insights` and `onPrompt` so messages.tsx can
// wire the prop shape now and Cycle 2 only touches this file.

type Props = {
  insights: ScoutInsightItem[];
  onPrompt?: (prompt: string) => void;
};

export function BrowseScout({ insights, onPrompt }: Props) {
  // Cycle 1 stub: returns null for every input. The Cycle 2
  // conditional-null contract (return null when `insights` is empty;
  // render a peer section with the existing `ScoutFinds` body when
  // non-empty) lives in this file once content lands. The `insights`
  // length check below is the same guard Cycle 2 will keep at the top
  // of the function — wiring it now means messages.tsx already passes
  // the right shape end-to-end.
  if (!insights || insights.length === 0) return null;
  // Suppressed Cycle-1 only: `onPrompt` will be threaded into the
  // ScoutFinds child in Cycle 2.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _onPrompt = onPrompt;
  return null;
}
