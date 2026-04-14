# Unified Intelligence Layer

## Purpose

Unified Intelligence sits between Briarwood-native module outputs and the user-facing answer.

Its job is to synthesize structured evidence into a decision-ready response for the current question. It is a synthesis layer, not a calculator. It does not own valuation, rent math, comp logic, risk scoring, legal classification, or scenario math. Those remain inside Briarwood-native modules.

## Position In The System

Flow:

1. User question
2. Parser and router
3. Selected Briarwood-native modules
4. Unified Intelligence
5. User-facing answer

Unified Intelligence should only operate on structured inputs that already passed through the parser and module layer.

## Inputs

Allowed inputs:

- parsed intent contract
- selected module outputs
- property summary
- scenario assumptions
- module confidence values
- warnings
- missing inputs

Disallowed inputs:

- raw user text beyond the parser stage
- full listing text
- raw comp dumps
- freeform unbounded notes

Reason:

The synthesis layer should work from bounded, auditable contracts. It should not quietly re-interpret raw evidence that should have been normalized upstream.

## Responsibilities

Unified Intelligence is responsible for:

- synthesizing across module outputs
- prioritizing what matters most for the current question
- weighting conclusions by confidence
- producing a final decision: `buy`, `mixed`, or `pass`
- recommending the best path
- continuing the decision flywheel by surfacing the next best question

Unified Intelligence is not responsible for:

- creating new numeric analysis
- overriding module math
- inventing evidence not present in the inputs
- hiding material warnings just to make the answer cleaner

## Question-Depth Behavior

### Snapshot

Use when the user wants a fast directional answer.

Expected behavior:

- give the shortest useful recommendation
- emphasize the top 1-2 value drivers
- emphasize the top 1-2 risks
- keep conditionality visible
- avoid sprawling path recommendations

Output style:

- headline answer first
- very selective supporting facts
- next question should usually narrow uncertainty

### Decision

Use when the user wants a clear buy-or-pass judgment with practical context.

Expected behavior:

- produce a direct decision
- explain why in ranked order
- connect the decision to the most decision-relevant modules
- include a concrete best path

Output style:

- recommendation first
- key value drivers and key risks balanced
- next question should improve conviction or execution quality

### Scenario

Use when the user is explicitly comparing paths or future states.

Expected behavior:

- frame the answer around scenarios and tradeoffs
- explain what changes under different paths
- make path selection explicit
- reflect sensitivity to assumptions and time horizon

Output style:

- recommendation may be conditional on a path
- best path should be more specific
- next question should usually test the highest-impact assumption

### Deep Dive

Use when the user wants a fuller underwriting-style synthesis.

Expected behavior:

- integrate more modules without becoming a data dump
- preserve hierarchy: decision first, evidence second
- show where confidence is earned versus where it is weak
- surface execution dependencies clearly

Output style:

- still decision-first
- more supporting facts are acceptable
- next question should focus on the biggest unresolved decision bottleneck

## Output Contract

Unified Intelligence must return a structured final output with this shape:

- `recommendation`: concise investment-minded recommendation in plain language
- `decision`: one of `buy`, `mixed`, `pass`
- `best_path`: recommended action path based on the current evidence
- `key_value_drivers`: list of the most important upside or support factors
- `key_risks`: list of the most important downside, fragility, or execution risks
- `confidence`: calibrated confidence between 0 and 1
- `analysis_depth_used`: depth used for this answer
- `next_questions`: high-leverage follow-up questions only
- `recommended_next_run`: optional recommendation for a deeper or more focused follow-up run
- `supporting_facts`: optional bounded facts that support the recommendation

Notes:

- `recommendation` should be readable by a user
- `decision` should be machine-safe and normalized
- `best_path` should bridge analysis to action
- `supporting_facts` should stay compact and structured

Example shape:

```json
{
  "recommendation": "Mixed. Buy only if the rent path is legal and the price leaves room for near-term carry pressure.",
  "decision": "mixed",
  "best_path": "Owner-occupy first, verify legal rentability, then re-run a hold-to-rent scenario before committing to a long hold.",
  "key_value_drivers": [
    "Entry price appears below current value range",
    "Optional future rental upside improves flexibility"
  ],
  "key_risks": [
    "Liquidity is weaker than headline value suggests",
    "Rental legality is not yet fully supported"
  ],
  "confidence": 0.64,
  "analysis_depth_used": "scenario",
  "next_questions": [
    "Can the additional unit be rented legally?",
    "What does carry look like if lease-up takes 6 months longer than expected?"
  ],
  "recommended_next_run": "scenario:hold_to_rent",
  "supporting_facts": {
    "valuation_gap_pct": 0.09,
    "liquidity_signal": "weak",
    "legal_confidence": 0.42
  }
}
```

## Trust Calibration Rules

Confidence should go down when:

- key modules disagree materially
- a critical module has low confidence
- required inputs are missing
- the recommendation depends on unresolved legality
- scenario outputs are highly assumption-sensitive
- path selection depends on data not yet verified

Confidence can go up when:

- multiple relevant modules align on the same conclusion
- the current question is narrow and the inputs are sufficient
- the highest-impact assumptions are explicit and well supported
- there are few material warnings or missing inputs
- the recommended path remains strong across adjacent scenarios

Confidence should not increase just because the language model can tell a cleaner story.

## Conflict Resolution Examples

### Attractive Value But Weak Liquidity

Desired behavior:

- do not convert cheap-looking value into an automatic `buy`
- keep the value signal
- explicitly surface exit risk and time-to-liquidity risk
- likely result: `mixed` unless the user has a hold profile that can absorb liquidity weakness

Example framing:

"Value looks attractive, but weak liquidity reduces the practical quality of that value."

### Strong Unit Income Offset But Uncertain Legality

Desired behavior:

- do not treat projected income as fully decision-grade
- keep the income upside as an option, not a base fact
- downgrade confidence materially
- likely result: `mixed` until legality is verified

Example framing:

"Income support is promising, but it should be discounted until legal use is clearer."

### Strong ARV But Weak Renovation Margin

Desired behavior:

- do not let a high ARV headline dominate the answer
- focus on margin after costs, friction, and execution risk
- treat upside as fragile if margin is thin
- likely result: `mixed` or `pass` depending on the margin weakness

Example framing:

"Headline upside exists, but the renovation path does not leave enough margin for execution risk."

## Best Path Logic

`best_path` is the bridge between analysis and action.

It should answer:

- what the user should do next
- under what conditions the recommendation holds
- which path is currently strongest

Good `best_path` behavior:

- specific enough to guide action
- grounded in current module outputs
- conditional when uncertainty is still material
- aligned with the user’s intent and question depth

Weak `best_path` behavior:

- vague summaries of the recommendation
- repeated restatement of module outputs
- action steps that assume facts not in evidence

Examples:

- "Buy for owner-occupancy only if short-hold resale is not the base case."
- "Treat this as a hold-to-rent candidate, but only after legal rentability and realistic lease-up assumptions are confirmed."
- "Pass on the renovation path unless purchase basis improves enough to restore margin."

## Next Question Logic

`next_questions` should only surface high-leverage follow-up questions.

Good next questions:

- materially change the decision
- resolve the largest uncertainty
- improve path selection
- tighten confidence where it matters most

Bad next questions:

- nice-to-know trivia
- broad exploratory prompts with no decision impact
- questions already answered by the current module set

Examples:

- "Can the additional unit be rented legally?"
- "What is the carry impact if taxes and insurance come in 15% higher?"
- "Does resale still work if renovation costs run 20% over plan?"

## OpenAI Rules

Allowed uses:

- structured synthesis
- prioritization
- best-path framing
- next-best questions

Not allowed:

- new valuation logic
- rent calculations
- comp selection
- legal scoring
- new scenario math

Operational rule:

OpenAI may summarize and prioritize module outputs, but it must not create new analytical truth. If a conclusion requires new math or a new scoring rule, that work belongs in a Briarwood-native module.

## Failure Behavior

If required inputs are missing, Unified Intelligence must stay conditional.

Required failure behavior:

- reduce confidence
- state the dependency clearly
- keep recommendations provisional where needed
- surface the next best question or next best run
- do not pretend certainty

Examples:

- If rentability is uncertain, do not present future rental income as settled.
- If valuation confidence is weak, do not present a crisp buy call as if it is fully earned.
- If hold assumptions are missing, do not overcommit to a best path that depends on time horizon.

## Engineering Notes

- Inputs should be contract-based and typed.
- Outputs should remain stable enough for downstream UI rendering.
- Supporting facts should stay bounded and reviewable.
- The layer should remain replaceable without rewriting native analytical modules.
- When in doubt, preserve analytical honesty over answer smoothness.
