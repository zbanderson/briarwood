# Briarwood System — Architecture Design Doc

> **Purpose of this document:** Capture the architecture decisions, product thinking, and build strategy for evolving the Briarwood system from "specialists that produce dumps" into a unified intelligence that surfaces real value to users. This doc is the north star — reference it from every Claude Code session so the design stays coherent across builds.

---

## 1. The Problem We're Solving

The Briarwood specialty models (economic, scenario, risk, location, security, town, etc.) do excellent, differentiated work. They are the crown jewels of this system. But the user-facing experience doesn't reflect that quality:

- Responses feel like data dumps — everything the system knows, all at once
- Charts and tables are hard to read, with no clear visual hierarchy or emphasis
- The system answers the literal question but misses the deeper value the user actually wants
- There's no sense that specialists are working together; outputs feel blended and generic
- The experience doesn't adapt to who's asking (first-time buyer vs. seasoned investor)

**The core diagnosis:** the Briarwood specialists are strong, but everything around them — the layers that decompose user intent, route to specialists, synthesize outputs, and present results — is underdetermined. There's no contract between components, no persona awareness, no editorial discipline, and no explicit step that asks "what's the non-obvious value here?"

---

## 2. The Target Experience

When a user asks *"tell me about this house"* or *"what are my options on this property?"*, the system should:

1. **Understand what they're really asking** — and infer, over time, who they are and what they care about
2. **Dispatch the right specialists** with the right scenarios to evaluate
3. **Synthesize the results into a structured claim** — not a paragraph, a schema
4. **Scan for non-obvious value** — the insight the user didn't know to ask about
5. **Edit for quality** — verify the answer is coherent, complete, and calibrated to the user's sophistication
6. **Render deterministically** — claim object → prose + chart + follow-up prompts, with visual emphasis on what matters

The user never sees any of this machinery. They just see a response that feels like it was written by someone who listened, thought carefully, and knows something they didn't.

---

## 3. Architecture

### 3.1 Original Components (Already Built)

| Component | Role |
|---|---|
| **Intent Parser (LLM)** | Breaks down what the user is asking |
| **Triage Agent (LLM)** | Routes intent; dispatches to specialists |
| **Briarwood Specialty Models (non-LLM)** | Economic, scenario, risk, location, security, town, etc. — the knowledge |
| **Output Intelligence (LLM)** | Assembles specialist results into a user-facing answer |
| **Representation Agent (LLM)** | Writes prose, picks charts, formats the response |

### 3.2 New Components (To Build)

| Component | Role | Position |
|---|---|---|
| **User Context Object** | Persistent within-session model of the user — persona, goals, sophistication, open threads, conversation memory | Read/written by multiple agents; state not a component |
| **Scenario Generator** | For open-ended questions ("what are my options?"), enumerates the scenarios specialists should evaluate in parallel | Between Intent Parser and Triage |
| **Value Scout** | Scans the assembled claim for non-obvious value the user didn't ask about. Distinct agent, distinct prompt. | Between Output Intelligence and Editor |
| **Editor** | Quality gate. Validates claim against user question, confidence rubric, consistency with prior claims. Rejects and loops back if checks fail. | Between Value Scout and Representation |

### 3.3 Data Contract: The Claim Object

The single most important design decision: **components communicate via structured claim objects, not prose.**

Output Intelligence produces a claim object. Value Scout annotates it. Editor validates it. Representation renders it. This is what makes ugly charts go away, what makes the system internally consistent, and what makes the Editor's job concrete instead of vibes-based.

**Claim objects have archetypes.** A "verdict + comparison" question produces a different shape than a "what are my options" question. Each archetype has its own schema, its own chart rules, and its own editor checklist.

**Initial archetype catalog (to expand over time):**

- `verdict_with_comparison` — "Is this a good price?" → verdict + comp table
- `option_comparison` — "What are my options?" → scenario matrix with recommendation
- `single_number` — "What's it worth?" → point estimate with range
- `trend_over_time` — "How's this market moving?" → time series
- `risk_breakdown` — "What could go wrong?" → categorized risk factors
- `orientation` — "Tell me about this area" → broad explanatory overview
- `recommendation_with_caveats` — "Should I?" → ranked advice with dependencies

---

### 3.4 North Star: AI-Native Principles

Briarwood is being built as an AI-native, "queryable" company. The four
principles below are load-bearing across every architectural decision —
when something feels like a tradeoff, the side that honors more of these
principles wins.

These principles are not aspirations. Each is named here, points to where
it currently lives in the codebase, and points to where it gets reinforced
in the staged buildout. The staged buildout itself is in
[`ROADMAP.md`](ROADMAP.md).

**1. Contracts First.** Components communicate via typed schemas, never
prose. This is the existing philosophy from § 3.3 above made explicit as
a principle. Today: every module's I/O is a `pydantic` schema; the
unified intelligence layer reads `ModulePayload` and emits
`UnifiedIntelligenceOutput`; the claims pipeline emits structured claim
objects. The synthesizer is the only layer that produces prose, and it
produces prose **from** structured inputs. Future agents follow the same
rule: prose is an output format, not an interface.

**2. Queryable Outputs.** Every analysis result is machine-consumable so
downstream LLM agents can reason over it without parsing text. This is
what enables Value Scout (§ 5) and what will enable every future
LLM-driven surface. Today: module outputs carry confidence, provenance,
and structured `extra_data`. The Scout buildout (Phase 4b) is the proof
of value — Scout reads `UnifiedIntelligenceOutput` and surfaces the
non-obvious read entirely from structured data.

**3. Every Action Is An Artifact.** Every turn, module run, LLM call,
and tool call leaves a durable inspectable record. Today: partially
operative. `TurnManifest` (`briarwood/agent/turn_manifest.py`) and
`LLMCallLedger` (`briarwood/agent/llm_observability.py`) capture rich
per-turn detail in memory but do not persist by default. Stage 1 of
[`ROADMAP.md`](ROADMAP.md) makes them durable, and
Stage 3 surfaces the resulting data in a business-facing dashboard.

**4. Closed Feedback Loops.** Every output schema carries a path back to
the input so the system improves from use. This expands and operationalizes
the existing § 7 (Dual Feedback Loops). Today: Loop 1 (Model Accuracy)
is write-only — `intelligence_feedback.jsonl` accumulates but no consumer
reads `outcome` because `outcome` is always null. Loop 2 (Communication
Calibration) is unbuilt — no user-facing rating surface exists. Stage 2
of the roadmap closes Loop 2; Stage 4 closes Loop 1.

A loop is **closed** only when both the write path AND the read path are
implemented and the read path provably runs. Write-only signals do not
count — see § 7 below.

---

## 4. The User Context Object

Persistent within a session. Tracks who the user is and what they're working on. Read by Intent Parser, Output Intelligence, Value Scout, Editor, and Representation — each uses it differently.

### 4.1 Schema (draft)

```json
{
  "session": {
    "session_id": "...",
    "turn_count": 4,
    "started_at": "...",
    "last_updated": "..."
  },
  "persona": {
    "labels": { "investor": 0.6, "first_time_buyer": 0.3, "move_up_buyer": 0.1 },
    "signals_observed": [
      { "turn": 2, "signal": "asked_about_rental_yield", "weight": 0.3 },
      { "turn": 3, "signal": "used_term_cap_rate", "weight": 0.4 }
    ],
    "stable_since_turn": 3
  },
  "sophistication": {
    "level": "intermediate",
    "vocabulary_signals": ["comps", "cap_rate", "FMV"],
    "asks_definitions": false,
    "prefers_density": "medium-high"
  },
  "goals": {
    "stated": [
      { "goal": "rental_income", "turn": 2, "verbatim": "rent it for a few years" }
    ],
    "inferred": [
      { "goal": "tax_efficiency", "confidence": 0.5, "basis": "mentioned 2-year hold" }
    ],
    "ruled_out": [
      { "goal": "quick_flip", "reason": "user stated multi-year horizon" }
    ]
  },
  "constraints": {
    "stated": [ { "type": "hold_period", "value": "2+ years", "turn": 3 } ],
    "inferred": [],
    "unknown_but_relevant": ["budget", "financing", "risk_tolerance"]
  },
  "focus": {
    "current_subject": { "type": "specific_property", "address": "..." },
    "area_of_interest": { "type": "town", "value": "Belmar, NJ" },
    "scope_trajectory": ["single_property", "property_plus_scenarios"]
  },
  "open_threads": [
    { "thread": "renovation_cost", "opened_turn": 2, "status": "pending", "priority": "high" },
    { "thread": "school_quality", "opened_turn": 0, "status": "deferred", "note": "phase 2" }
  ],
  "conversation_memory": {
    "key_facts_established": ["Subject: 3bd/1.5ba, needs work, Belmar NJ"],
    "claims_made_by_system": [
      { "turn": 1, "claim": "priced $38k under FMV", "confidence": 0.9 }
    ],
    "user_reactions": [
      { "turn": 2, "claim_ref": 1, "reaction": "engaged" }
    ]
  },
  "trust_calibration": {
    "user_agreement_rate": 0.85,
    "user_pushback_events": []
  },
  "presentation_preferences": {
    "tone": "analytical_but_warm",
    "density": "medium-high",
    "chart_appetite": "high",
    "caveat_tolerance": "medium"
  }
}
```

### 4.2 Key Decisions

- **Multi-label persona with confidences.** Users are often multiple things at once (first-time buyer who thinks like an investor). The response should honor both.
- **Proactive question-asking only when blocked.** Never interrogate. If an answer requires a missing constraint, ask inline and naturally. Otherwise, track unknowns silently in `unknown_but_relevant`.
- **Context resets across sessions** in v1. Cross-session memory becomes a premium feature. Possible free-tier middle ground: retain `persona` and `sophistication` (cheap, makes cold-start feel calibrated) but reset `focus`, `goals`, `open_threads`.
- **Who writes what:**
  - Intent Parser → `persona`, `sophistication`, `goals`, `constraints`, `focus`
  - Output Intelligence → `open_threads`, `conversation_memory.claims_made_by_system`
  - Editor → `user_reactions` (retrospectively, from next turn's content)

---

## 5. Value Scout — The Core Product Feature

Value Scout is a distinct agent with a single job:

> **"The user asked X. We're about to answer X. Is there a Y they should know about — something they didn't ask — that changes the picture?"**

If nothing, Value Scout passes through silently. If something, it annotates the claim object with a `surfaced_insight`.

**Example:** User asks *"is this house a good price?"* Comps model says yes, $38k under FMV. Value Scout notices that the 2ba conversion scenario has a $127/sqft uplift. It flags: *"the real opportunity here isn't the discount — it's the bathroom addition."* Representation weaves that into the response.

**Why Value Scout is the product:** the user's "aha moment" — the thing they tell friends about — is when the system surfaces something they didn't know to ask. Everything else (claim objects, archetypes, user context) exists to make Value Scout moments possible and reliable.

**Build it as a distinct module from day one.** Even if v1 only checks one pattern, keep it separate. Folding it into the Editor or Output Intelligence to save time buries the feature permanently.

---

## 6. Editor and the Confidence Rubric

### 6.1 Editor Checklist

The Editor validates every claim object before it goes to Representation:

1. Does the claim object conform to its archetype's schema?
2. Does every scenario reference real data, or is missing data acknowledged as a caveat?
3. Does the claim actually answer the user's question? (Not "did data return" — did we *answer*.)
4. Is the claim consistent with prior claims this session? If not, is the contradiction acknowledged?
5. Does the assertion strength match the confidence level? (see rubric below)
6. Are high-priority `open_threads` either addressed or deferred with explanation?
7. Did Value Scout run? Did it find something? Is the finding justified by the data?

If any check fails, Editor returns the claim object to the relevant upstream agent with a specific reason — not "make it better," but "scenario 2 is missing a risk score, rerun risk model."

### 6.2 Confidence-to-Assertion Rubric

| Confidence | Phrasing |
|---|---|
| >90% | State it flatly. *"This house is $38k under FMV."* |
| 70–90% | State with light hedging. *"Based on 23 comps, this looks roughly $38k under FMV."* |
| 50–70% | Frame as a range or possibility. *"Fair value is probably $510–540k, best estimate $523k."* |
| <50% | Don't lead with it. Surface as "we'd need more data to say confidently." |

Applied per-claim, not per-response. A single response can contain a >90% claim and a 60% claim with different phrasing.

---

## 7. Dual Feedback Loops

A loop is **closed** only when both the write path AND the read path
exist and the read path provably runs. A signal that is captured but
never consumed is a write-only path, not a closed loop, and should not
be described as one. This distinction is load-bearing — the audit on
2026-04-27 found that today's `intelligence_feedback.jsonl` is
write-only, which the system was treating as if it were closed.

Two separate feedback mechanisms — kept separate on purpose:

### Loop 1: Model Accuracy (System-to-System)

- Editor validates claims against prior claims, inter-model agreement, and (when available) ground truth outcomes (final sale prices, appraisals, verified facts).
- High-confidence claims that prove correct reinforce the producing models.
- This is about *is the underlying number right.*

### Loop 2: Communication Calibration (User-to-System)

- User reactions (agree, disagree, ignore, act on) feed `trust_calibration` and `user_reactions`.
- Adjusts *how assertively* the system communicates to this user — not whether the underlying claim is true.
- Same claim can become softer in delivery without becoming less accurate: *"The house is worth $523k"* → *"Our model puts this at $523k, though I know that's higher than you were expecting."*

**Why the separation matters:** if user pushback degraded model confidence, the system would learn to tell users what they want to hear. That's the worst failure mode for a value-surfacing product. Users disagreeing doesn't mean the model was wrong.

---

## 8. Build Strategy: The Wedge

Don't try to build everything at once. Prove the approach with the smallest testable slice.

### 8.1 The Wedge (v1)

**Scope:** one archetype, one user flow, turn 1 only.

- **Archetype:** `verdict_with_comparison`
- **Flow:** "Is this Belmar house a good price?" — hardcoded investor-leaning persona
- **Skip:** User Context object (hardcode persona), cross-session memory, other archetypes, trust calibration, Scenario Generator (single implicit scenario)

### 8.2 What to Build

1. Claim object schema for `verdict_with_comparison` (in code, typed)
2. Output Intelligence prompt that produces the schema from Briarwood outputs
3. Minimal Value Scout that checks one pattern (e.g., "does any scenario dominate on $/sqft uplift per dollar invested?")
4. Representation template that renders the claim object deterministically — headline, prose, chart, follow-up prompts
5. Basic Editor that validates the schema and checks referenced scenarios have data

### 8.3 What You'll Learn

- Whether the claim-object-as-contract approach actually produces the quality we want
- Where the Briarwood outputs need cleaning or enriching to fit the schema
- How much Representation work is deterministic vs. still LLM-judgment-dependent
- Whether Value Scout's pattern-matching produces genuine insights or noise

### 8.4 What Comes After the Wedge

- Add the User Context object (start with persona + sophistication only)
- Add the `option_comparison` archetype — the house's "what are my options" flow
- Add the Scenario Generator to enumerate option scenarios for open-ended questions
- Expand Value Scout's pattern library
- Add cross-session persistence (premium tier)

---

## 9. Working with Claude Code

When applying this design to the workspace, follow this sequence. Do not skip phases.

### Phase 1: Inventory (no code changes)

Prompt Claude Code to read the codebase and produce a map:

- Each Briarwood specialty model — location, I/O, invocation
- Current Intent Parser / Triage logic
- Current Output Intelligence layer
- Current Representation layer
- UI request/response path
- Any existing concept of session state or conversation history

Output: markdown inventory document. No recommendations yet.

### Phase 2: Gap Analysis (no code changes)

Compare inventory to target architecture in this doc. For each target component:

- Does something like this exist today?
- If yes, what changes to match target?
- If no, where does it fit?
- What's the order of operations?

Output: gap analysis document.

### Phase 3: Wedge Proposal (no code changes)

Based on gap analysis, propose the smallest slice for the `verdict_with_comparison` wedge (Section 8):

- Which files get modified
- Which files get created
- Claim object schema in code
- Contract between Output Intelligence and Representation
- Tests/checks that prove it works

Output: build plan. Review before implementation.

### Phase 4: Build (reviewed, one file at a time)

Only after approving the plan. Implement one component at a time with review between each.

### Guardrails for Claude Code

- **Briarwood specialists are read-only.** The target architecture sits *around* them. If Claude Code proposes changes to specialist models, it has misunderstood the design.
- **UI stays untouched until backend contract is stable.** Ugly charts get fixed because the claim object schema tells the UI exactly what to draw. Don't touch the UI before the schema exists.
- **Value Scout must be a distinct module from day one.** Not folded into Editor or Output Intelligence, even in v1.
- **Claim objects are the contract.** Components talk to each other via structured claim objects, never prose.

---

## 10. Glossary

- **Archetype** — a category of response shape (verdict+comparison, option comparison, etc.) with its own claim object schema, chart rules, and editor checklist
- **Briarwood specialists** — the non-LLM specialty models (economic, risk, location, etc.) that do the actual domain work
- **Claim Object** — the structured data contract components use to communicate. Contains verdict, comparison, caveats, next questions, provenance.
- **Editor** — quality-gate agent that validates claim objects before rendering
- **Scenario Generator** — agent that enumerates scenarios for open-ended questions (e.g., "what are my options" → {as-is, light reno, full reno, full reno + bath})
- **User Context Object** — persistent within-session model of user persona, goals, sophistication, open threads, conversation memory
- **Value Scout** — agent that scans the assembled claim for non-obvious insight the user didn't explicitly ask about. The core product feature.
- **Verdict** — a single-word judgment label (value_find, fair, overpriced, etc.) backed by a specific basis
- **Wedge** — the smallest testable slice (v1: verdict_with_comparison, single flow, turn 1)