# Local Intelligence Signal Classification

This document defines how Briarwood turns validated `TownSignal` records into the compact Town Pulse buckets shown in the app.

The goal is trust and scanability, not maximum recall.

## Why the app uses `Catalysts`, `Risks`, and `Watch`

Town Pulse is meant to answer:

`What is changing in this town that comps and listing data may not yet fully reflect?`

To keep that useful in a fast decision flow, Briarwood groups signals into three user-facing buckets:

- `Catalysts`
  Confirmed or well-supported positive local signals that could improve value, demand, liquidity, infrastructure quality, amenities, or town perception.
- `Risks`
  Confirmed or well-supported negative local signals that could hurt value, rents, liquidity, resilience, or execution.
- `Watch`
  Early-stage, mixed, neutral, or lower-confidence signals that matter, but should not yet be treated as a firm catalyst or risk.

For backward compatibility in the data model, these still map to:

- `bullish_signals` -> `Catalysts`
- `bearish_signals` -> `Risks`
- `watch_items` -> `Watch`

## Classification rules

The source of truth lives in:

- [classification.py](/Users/zachanderson/projects/briarwood/briarwood/local_intelligence/classification.py)

The rules are deterministic:

1. A signal becomes `Watch` if:
   - its status is `mentioned`, `proposed`, or `reviewed`, or
   - its confidence is below `0.58`
2. Otherwise:
   - `impact_direction = positive` -> `Catalyst`
   - `impact_direction = negative` -> `Risk`
   - `impact_direction = mixed` or `neutral` -> `Watch`

This intentionally biases toward caution. Briarwood does not elevate a signal into a clear catalyst or risk unless it is both directionally meaningful and sufficiently supported.

## Priority and ranking

Within each bucket, Briarwood ranks signals using:

- confidence
- status strength
- recency
- impact direction bonus

Higher-status signals like `approved`, `funded`, `in_progress`, and `completed` rank above weaker, earlier-stage mentions.

## Confidence and trust rules

Town Pulse confidence is not purely whatever the model returned.

Confidence is influenced by:

- source type quality
- explicit status clarity
- amount of grounded factual support
- deterministic post-validation caps in the Local Intelligence validation layer

That means an ambiguous blog mention should stay lower-confidence even if the LLM sounds sure.

## Product intent

These buckets are not meant to be a complete local news taxonomy. They are a compact underwriting aid:

- `Catalysts` help explain supportive local momentum
- `Risks` help explain what could impair the thesis
- `Watch` prevents Briarwood from overstating weak or early-stage developments
