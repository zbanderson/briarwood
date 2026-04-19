"use client";

import { useMemo } from "react";
import type { GroundingAnchor } from "@/lib/chat/events";

type Segment =
  | { kind: "text"; text: string }
  | { kind: "anchor"; text: string; anchor: GroundingAnchor };

/**
 * Candidate display forms for an anchor value. The backend sends the raw value
 * (e.g. "820000" or "0.06"); the LLM typically renders the same value as
 * "$820,000" or "6%". We enumerate plausible formats and match the first one
 * that appears in the prose so the tooltip can wrap the actual cited span.
 */
function displayForms(value: string): string[] {
  const out = new Set<string>();
  const raw = value.trim();
  out.add(raw);
  const cleaned = raw.replace(/[,$%]/g, "").trim();
  const num = Number(cleaned);
  if (!Number.isFinite(num)) return [...out];

  // Currency forms for integers >= 1000.
  if (Math.abs(num) >= 1000 && Number.isInteger(num)) {
    const commafied = num.toLocaleString("en-US");
    out.add(`$${commafied}`);
    out.add(commafied);
    out.add(String(num));
    if (num % 1000 === 0 && Math.abs(num) < 1_000_000) {
      const k = Math.round(num / 1000);
      out.add(`$${k}k`);
      out.add(`$${k}K`);
      out.add(`${k}k`);
      out.add(`${k}K`);
    }
    if (Math.abs(num) >= 1_000_000) {
      const m = num / 1_000_000;
      const m1 = m.toFixed(1).replace(/\.0$/, "");
      out.add(`$${m1}M`);
      out.add(`$${m1}m`);
      out.add(`${m1}M`);
    }
  }

  // Fractional → percent (0.06 → 6%). Treat anything |x| < 1 as a fraction.
  if (Math.abs(num) < 1 && num !== 0) {
    const pct = num * 100;
    const pct1 = pct.toFixed(1).replace(/\.0$/, "");
    out.add(`${pct1}%`);
    out.add(`+${pct1}%`);
    out.add(`${pct.toFixed(2)}%`);
  }

  // Already-percent forms.
  if (Math.abs(num) >= 1) {
    out.add(`${num}%`);
    out.add(`+${num}%`);
    out.add(`${num.toFixed(1)}%`);
  }

  return [...out];
}

/**
 * Segment content into text/anchor chunks. For each anchor, find the first
 * unmatched occurrence of any display form in the remaining text and wrap it.
 * Anchors that match nothing simply don't get highlighted — the tooltip data
 * is still emitted in the grounding_annotations event for consumers that want
 * to list sources separately.
 */
function segmentContent(content: string, anchors: GroundingAnchor[]): Segment[] {
  if (!content || anchors.length === 0) return [{ kind: "text", text: content }];

  type Hit = { start: number; end: number; anchor: GroundingAnchor };
  const hits: Hit[] = [];
  const claimedRanges: Array<[number, number]> = [];

  for (const anchor of anchors) {
    for (const form of displayForms(anchor.value)) {
      if (!form) continue;
      let from = 0;
      while (from <= content.length - form.length) {
        const idx = content.indexOf(form, from);
        if (idx < 0) break;
        const end = idx + form.length;
        const overlaps = claimedRanges.some(
          ([s, e]) => !(end <= s || idx >= e),
        );
        if (!overlaps) {
          hits.push({ start: idx, end, anchor });
          claimedRanges.push([idx, end]);
          break;
        }
        from = idx + 1;
      }
      if (claimedRanges.some(([s, e]) => s <= content.length && e === content.length)) break;
      if (hits.some((h) => h.anchor === anchor)) break;
    }
  }

  if (hits.length === 0) return [{ kind: "text", text: content }];

  hits.sort((a, b) => a.start - b.start);

  const out: Segment[] = [];
  let cursor = 0;
  for (const hit of hits) {
    if (hit.start > cursor) {
      out.push({ kind: "text", text: content.slice(cursor, hit.start) });
    }
    out.push({
      kind: "anchor",
      text: content.slice(hit.start, hit.end),
      anchor: hit.anchor,
    });
    cursor = hit.end;
  }
  if (cursor < content.length) {
    out.push({ kind: "text", text: content.slice(cursor) });
  }
  return out;
}

type GroundedTextProps = {
  content: string;
  anchors: GroundingAnchor[];
  muted?: boolean;
};

export function GroundedText({ content, anchors, muted = false }: GroundedTextProps) {
  const segments = useMemo(
    () => segmentContent(content, anchors),
    [content, anchors],
  );

  if (!content) return null;

  const baseClass = muted
    ? "whitespace-pre-wrap break-words rounded-xl border border-[var(--color-border-subtle)] bg-[var(--color-bg-sunken)] px-3 py-2 text-[var(--color-text-muted)]"
    : "whitespace-pre-wrap break-words";

  return (
    <div className={baseClass}>
      {muted && (
        <span
          className="mr-2 inline-flex items-center rounded-full border border-[var(--color-border-subtle)] bg-[var(--color-surface)] px-2 py-0.5 text-[10px] uppercase tracking-wider text-[var(--color-text-faint)]"
          aria-label="no model output"
        >
          no model output
        </span>
      )}
      {segments.map((seg, i) =>
        seg.kind === "text" ? (
          <span key={i}>{seg.text}</span>
        ) : (
          <span
            key={i}
            title={`Source: ${seg.anchor.module} · ${seg.anchor.field} = ${seg.anchor.value}`}
            className="cursor-help underline decoration-dotted decoration-[var(--color-text-faint)] underline-offset-2 text-[var(--color-text)]"
          >
            {seg.text}
          </span>
        ),
      )}
    </div>
  );
}
