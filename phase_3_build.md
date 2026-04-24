Phase 3: Wedge Build Plan

Executes design_doc.md §8 (Option A: full wedge). References the Phase 1 inventory and Phase 2 gap analysis. Claude Code executes this one section at a time, with review gates at each ✋ marker.


0. Scope Reminder
In scope (wedge v1):

One archetype: verdict_with_comparison
One user flow: pinned property + "is this a good price?"-shaped question
Hardcoded persona (investor)
Turn 1 only (no conversation memory writes)
New code path, feature-flagged, legacy path untouched

Out of scope (deferred to Phase B):

User Context Object (persona hardcoded in wedge)
Scenario Generator (single implicit scenario)
Editor loop-back (v1 is pass/fail)
option_comparison or any other archetype
Cross-session persistence
Trust calibration, Loop 2 feedback

Hard guardrails (from design_doc §9):

Briarwood specialty modules (briarwood/modules/) are read-only. Do not modify.
UI components (web/src/components/chat/messages.tsx) do not move until backend contract stable. Wedge reuses existing SSE event shapes.
Value Scout is a distinct module from day one. Do not fold into Editor or synthesis.
Claim objects are the contract between components. No prose passed between new pipeline stages.


1. Feature Flag Mechanism
Invent one. Dead simple, no dependencies.
1.1 Create briarwood/feature_flags.py
python"""Process-level feature flags. Read once at import; no runtime toggling."""
from __future__ import annotations
import os

def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

def _env_set(name: str) -> frozenset[str]:
    raw = os.environ.get(name, "")
    return frozenset(p.strip() for p in raw.split(",") if p.strip())

CLAIMS_ENABLED: bool = _env_bool("BRIARWOOD_CLAIMS_ENABLED", default=False)
CLAIMS_PROPERTY_IDS: frozenset[str] = _env_set("BRIARWOOD_CLAIMS_PROPERTY_IDS")

def claims_enabled_for(property_id: str | None) -> bool:
    """True if the new claim-object pipeline should run for this property."""
    if not CLAIMS_ENABLED:
        return False
    if not CLAIMS_PROPERTY_IDS:
        return True  # global on
    return (property_id or "") in CLAIMS_PROPERTY_IDS
1.2 Usage contract
Exactly one caller: the chat-tier dispatch router (briarwood/agent/dispatch.py handle_decision, L1809). No other file imports from feature_flags.
✋ Review gate 1. Confirm flag name and semantics before implementation.

2. Archetype + Claim Object Foundation
This is the keystone per §9.B.5. Nothing else can start until this exists.
2.1 Create briarwood/claims/ package
Files to create:

briarwood/claims/__init__.py — exports public types
briarwood/claims/archetypes.py — the Archetype enum
briarwood/claims/base.py — shared base types (provenance, confidence, scenario, caveat)
briarwood/claims/verdict_with_comparison.py — the wedge archetype

2.2 archetypes.py
pythonfrom enum import Enum

class Archetype(str, Enum):
    """Response shape category. Cross-references AnswerType + QuestionFocus but independent.

    Each archetype corresponds to exactly one claim-object schema in briarwood.claims.
    """
    VERDICT_WITH_COMPARISON = "verdict_with_comparison"
    # Future archetypes reserved but not implemented in wedge:
    # OPTION_COMPARISON = "option_comparison"
    # SINGLE_NUMBER = "single_number"
    # TREND_OVER_TIME = "trend_over_time"
    # RISK_BREAKDOWN = "risk_breakdown"
    # ORIENTATION = "orientation"
    # RECOMMENDATION_WITH_CAVEATS = "recommendation_with_caveats"
2.3 base.py
Shared Pydantic models reused across archetypes:
pythonfrom pydantic import BaseModel, Field
from typing import Literal

class Provenance(BaseModel):
    """Which modules contributed to this claim. Honest accounting of what ran vs skipped."""
    models_consulted: list[str] = Field(default_factory=list)
    models_skipped: list[str] = Field(default_factory=list)
    skip_reason: str | None = None
    bridges_fired: list[str] = Field(default_factory=list)

class Confidence(BaseModel):
    """Per-claim confidence. Drives assertion rubric in representation."""
    score: float = Field(ge=0.0, le=1.0)
    band: Literal["high", "medium", "low", "very_low"]

    @classmethod
    def from_score(cls, score: float) -> "Confidence":
        if score >= 0.90: band = "high"
        elif score >= 0.70: band = "medium"
        elif score >= 0.50: band = "low"
        else: band = "very_low"
        return cls(score=score, band=band)

class Caveat(BaseModel):
    """Something the user should know but the system couldn't verify."""
    text: str
    severity: Literal["info", "warning", "blocking"]
    source: str  # module or bridge that raised it

class NextQuestion(BaseModel):
    """Specialist-aware follow-up prompt. Routes cleanly back into the pipeline."""
    text: str
    routes_to: str  # archetype or module name this question would invoke

class SurfacedInsight(BaseModel):
    """Value Scout's output. Optional — None if Scout found nothing notable."""
    headline: str
    reason: str  # why Scout flagged this
    supporting_fields: list[str]  # claim-object fields that substantiate it
2.4 verdict_with_comparison.py
The actual wedge schema. Fields match the design-doc example (§claim object schema in the earlier conversation) but typed and validated.
pythonfrom pydantic import BaseModel, Field, model_validator
from typing import Literal
from .base import Provenance, Confidence, Caveat, NextQuestion, SurfacedInsight
from .archetypes import Archetype

class Subject(BaseModel):
    property_id: str
    address: str
    beds: int
    baths: float
    sqft: int
    ask_price: float
    status: Literal["active", "pending", "sold", "unknown"] = "unknown"

class Verdict(BaseModel):
    label: Literal["value_find", "fair", "overpriced", "insufficient_data"]
    headline: str  # pre-written by synthesis, not regenerated by representation
    basis_fmv: float
    ask_vs_fmv_delta_pct: float
    method: str  # e.g., "comp_model_v3"
    comp_count: int
    comp_radius_mi: float
    comp_window_months: int
    confidence: Confidence

class ComparisonScenario(BaseModel):
    id: str
    label: str
    metric_range: tuple[float, float]  # (low, high)
    metric_median: float
    is_subject: bool = False
    sample_size: int
    flag: Literal["value_opportunity", "caution", "none"] = "none"
    flag_reason: str | None = None

class Comparison(BaseModel):
    metric: Literal["price_per_sqft"]  # wedge supports one metric
    unit: str = "$/sqft"
    scenarios: list[ComparisonScenario]
    chart_rule: Literal["horizontal_bar_with_ranges"]
    emphasis_scenario_id: str | None = None

    @model_validator(mode="after")
    def validate_emphasis_exists(self):
        if self.emphasis_scenario_id:
            ids = {s.id for s in self.scenarios}
            if self.emphasis_scenario_id not in ids:
                raise ValueError(f"emphasis_scenario_id {self.emphasis_scenario_id} not in scenarios")
        return self

class VerdictWithComparisonClaim(BaseModel):
    archetype: Literal[Archetype.VERDICT_WITH_COMPARISON] = Archetype.VERDICT_WITH_COMPARISON
    subject: Subject
    verdict: Verdict
    bridge_sentence: str  # transition into the comparison
    comparison: Comparison
    caveats: list[Caveat] = Field(default_factory=list)
    next_questions: list[NextQuestion] = Field(default_factory=list)
    provenance: Provenance
    surfaced_insight: SurfacedInsight | None = None  # populated by Value Scout
2.5 Chart rule registry for the wedge
One supported chart per archetype in v1. No new chart infrastructure; the horizontal_bar_with_ranges chart kind maps to the existing native chart spec pipeline (see inventory §4.3). If that exact kind doesn't exist in the current chart registry, add it as a new kind value in the chart emission path — but do not invent new UI cards.
✋ Review gate 2. Confirm schema shape and chart-rule approach before implementation. Especially: does the existing chart SSE event and its kind field support horizontal_bar_with_ranges rendering, or does the wedge need a small UI card addition?

3. Intent Parser: Archetype Mapping
Minimal change. No new LLM call. No persona inference.
3.1 Where
New file: briarwood/claims/routing.py
3.2 What
pythonfrom briarwood.agent.router import AnswerType
from briarwood.router import QuestionFocus  # if importable; else adapter
from .archetypes import Archetype

def map_to_archetype(
    answer_type: AnswerType,
    question_focus: "QuestionFocus | None",
    has_pinned_listing: bool,
) -> Archetype | None:
    """Map existing classification to archetype. Returns None if no archetype matches
    (caller falls back to legacy path)."""
    if not has_pinned_listing:
        return None
    if answer_type in {AnswerType.DECISION, AnswerType.LOOKUP}:
        return Archetype.VERDICT_WITH_COMPARISON
    return None
Deliberately narrow. Only one archetype exists in the wedge; anything else returns None and routes to legacy.
3.3 Contract test
New file: tests/claims/test_routing.py. Pins that DECISION + pinned listing → VERDICT_WITH_COMPARISON and that unsupported combinations return None.
✋ Review gate 3. Confirm mapping logic before implementation.

4. Synthesis: Claim Object Producer
New code path. Legacy build_unified_output() untouched.
4.1 Where
New file: briarwood/claims/synthesis/verdict_with_comparison.py
4.2 What it does
Input: the same module_results, bridge_records, property_summary, parser_output that build_unified_output() consumes today.
Output: VerdictWithComparisonClaim instance.
Implementation: deterministic, no LLM. Per design doc, "Output Intelligence" is listed as an LLM step but the existing synthesizer is deterministic and that's better when it works. The wedge keeps it deterministic.
Key sources per field:

subject.* ← property_summary
verdict.basis_fmv ← valuation module briarwood_current_value
verdict.ask_vs_fmv_delta_pct ← computed from ask + FMV
verdict.label ← rule: delta <= -5% → value_find, -5% < delta < 5% → fair, delta >= 5% → overpriced, otherwise insufficient_data
verdict.headline ← templated from delta + dollar amount (no LLM)
verdict.confidence ← confidence module score
verdict.comp_count / radius / window ← valuation module metrics
comparison.scenarios ← valuation module's comp-selection output for the three tiers (subject config, renovated same-config, renovated +bath). If +bath scenario data is absent, drop that scenario and add a caveat.
bridge_sentence ← templated string
caveats ← bridge_records warnings + any module warnings
next_questions ← templated set of three follow-ups specific to this archetype
provenance ← derived from which modules ran

4.3 Templates
Put the headline/bridge-sentence templates in briarwood/claims/synthesis/templates.py. Keep them simple f-strings; no template engine needed yet.
pythonVERDICT_HEADLINE = {
    "value_find": "Priced ${delta_abs:,.0f} under fair market value (-{delta_pct:.1f}%).",
    "fair": "Priced roughly at fair market value.",
    "overpriced": "Priced ${delta_abs:,.0f} above fair market value (+{delta_pct:.1f}%).",
    "insufficient_data": "Not enough comparable evidence to call the price.",
}

BRIDGE_SENTENCE = (
    "Here's how this property compares against recent sales of similar "
    "and upgraded configurations in the area."
)
4.4 Consumer path
The decision handler (new, §7) calls build_verdict_with_comparison_claim() instead of build_unified_output() when the flag is on.
✋ Review gate 4. Confirm field mappings before implementation. Especially: does the valuation module already emit the three-tier comp ranges, or does the synthesizer need to assemble them from raw comps?

5. Value Scout v1
New module. One pattern. Separate from synthesis per guardrail.
5.1 Where
New package: briarwood/value_scout/

briarwood/value_scout/__init__.py
briarwood/value_scout/scout.py — entrypoint
briarwood/value_scout/patterns/uplift_dominance.py — the one v1 pattern

5.2 Entrypoint signature
pythondef scout_claim(claim: VerdictWithComparisonClaim) -> SurfacedInsight | None:
    """Scan the claim for non-obvious value. Returns None if nothing notable."""
Runs all registered patterns, returns the highest-scoring non-null result, or None.
5.3 Pattern: uplift dominance
Given the comparison scenarios, find the one with the highest (median_uplift_over_subject) / (rough_investment_delta). If that ratio exceeds a threshold and it isn't the subject itself, emit:
pythonSurfacedInsight(
    headline="The {scenario_label} path shows the strongest upside for the investment required.",
    reason="${uplift_per_sqft}/sqft median uplift is {multiple}x higher than the {other_scenario} path per dollar of renovation investment.",
    supporting_fields=["comparison.scenarios[{id}].metric_median", ...]
)
Investment deltas are rough estimates since the wedge doesn't have renovation cost modeling. Use conservative placeholder estimates in a constants file and flag this in the code as a known limitation for Phase B.
5.4 Contract test
New file: tests/value_scout/test_uplift_dominance.py. Two golden cases: one where pattern fires, one where it doesn't.
✋ Review gate 5. Confirm pattern logic and the placeholder investment estimates before implementation.

6. Editor v1
New module. Pass/fail. No loop-back.
6.1 Where
New package: briarwood/editor/

briarwood/editor/__init__.py
briarwood/editor/validator.py — entrypoint
briarwood/editor/checks.py — individual check functions

6.2 Entrypoint signature
pythonfrom typing import NamedTuple

class EditResult(NamedTuple):
    passed: bool
    failures: list[str]  # human-readable reasons

def edit_claim(claim: VerdictWithComparisonClaim) -> EditResult:
    ...
6.3 Checks for v1
Run in order; collect all failures:

Schema conformance — Pydantic validation already enforces this; the check is "did the claim even construct." Trivially passes if we got here.
Scenario data completeness — every scenario in comparison.scenarios has non-zero sample_size.
Verdict-delta coherence — verdict.label matches the rule applied to ask_vs_fmv_delta_pct. Catches the case where upstream code or future refactors diverge.
Emphasis coherence — if comparison.emphasis_scenario_id is set, it matches the surfaced_insight subject (if Scout fired).
Caveat-for-gap — if any comparison scenario has sample_size < 5, there is a corresponding caveat.

6.4 Failure handling
If edit_claim returns passed=False:

Log the failures
Emit an SSE event (new event type claim_rejected or reuse partial_data_warning) with the failure list for dev visibility
Fall back to the legacy handle_decision path for this turn so the user still gets a response

This is the safety valve. A broken wedge never blocks a user.
✋ Review gate 6. Confirm check set and fallback behavior before implementation. Especially: new SSE event type vs reuse of partial_data_warning?

7. Representation: Driven by Schema
Inverts control per design §3.2. Claim object dictates output; LLM only writes prose around fixed structure.
7.1 Where
New file: briarwood/claims/representation/verdict_with_comparison.py
Existing briarwood/representation/agent.py untouched. The wedge does not reuse RepresentationAgent because its control flow is inverted (it extracts claims; we are given claims).
7.2 Three sub-steps, in order
7.2.1 Render verdict headline + bridge
Deterministic. Take claim.verdict.headline and claim.bridge_sentence verbatim. No LLM.
7.2.2 Render prose around structured fields
Single LLM call with a tight prompt. Input: the claim object serialized. Output: 2–4 sentences of prose that integrate the headline, bridge, and any surfaced insight into natural language appropriate to the hardcoded investor persona.
New prompt file: api/prompts/claim_verdict_with_comparison.md. Short. Includes _base.md. Explicit instructions:

Do not invent numbers not present in the claim
Do not soften or strengthen the verdict beyond what confidence band allows (see 7.3)
Echo the surfaced insight if present
Output plain prose, no markdown

7.2.3 Emit chart + table + next questions
Deterministic. Translate the claim's comparison into the existing SSE chart event shape (§4.3 of inventory). Translate next_questions into a suggestions SSE event.
7.3 Confidence-to-assertion rubric
New file: briarwood/claims/representation/rubric.py. Functions that wrap/modify prose based on verdict.confidence.band:

high → no modification
medium → prepend "Based on [N] comparable sales,"
low → convert point claims to ranges, prepend "Our best estimate is,"
very_low → do not lead with the claim; start with "We don't have high confidence here, but..."

Applied after the LLM call to the verdict-bearing sentence only.
7.4 Persona handling in wedge
Hardcoded to investor via a constant. Affects prose prompt:

Higher density OK
Uses terms like FMV, $/sqft, comp count without defining them
Leads with numbers

No UserContext object is read. Phase B adds that.
✋ Review gate 7. Confirm the split of deterministic vs LLM work, and the rubric thresholds, before implementation.

8. Wire Into Dispatch
8.1 Where
Modify briarwood/agent/dispatch.py handle_decision (L1809).
8.2 How
Add a branch at the top of handle_decision (before any existing logic):
pythonfrom briarwood.feature_flags import claims_enabled_for
from briarwood.claims.routing import map_to_archetype
from briarwood.claims.archetypes import Archetype

def handle_decision(user_text, router_decision, session, llm_client) -> str:
    # New claim-object path, feature-flagged
    pinned = session.current_live_listing
    property_id = (pinned or {}).get("property_id") if pinned else None
    if claims_enabled_for(property_id):
        archetype = map_to_archetype(
            router_decision.answer_type,
            router_decision.parser_output.question_focus if hasattr(router_decision, "parser_output") else None,
            has_pinned_listing=pinned is not None,
        )
        if archetype == Archetype.VERDICT_WITH_COMPARISON:
            try:
                return _handle_decision_via_claim(user_text, router_decision, session, llm_client)
            except Exception as e:
                # Log, emit diagnostic, fall through to legacy
                logger.warning("claims path failed, falling back: %s", e)
    # Legacy path (unchanged)
    ... existing handle_decision body ...
_handle_decision_via_claim is a new private function in the same file (or a new file imported here) that orchestrates: run analysis → build claim → Scout → Editor → render → return prose. Editor failure also falls through to legacy.
8.3 Guardrail
The legacy handle_decision body is not edited. The only change is prepending the branch. This is critical — it means rolling back the wedge is flipping one env var.
✋ Review gate 8. Confirm the branching pattern and exception handling before implementation.

9. Tests
Minimum coverage to prove the wedge works.
9.1 Fixtures
New file: tests/claims/fixtures/belmar_house.py. Fabricated property + module outputs that exercise all three comparison scenarios and allow Value Scout's uplift-dominance pattern to fire. Keep it pure Python, no external data dependencies.
9.2 Test files

tests/claims/test_archetypes.py — enum values stable
tests/claims/test_routing.py — map_to_archetype happy path + unsupported combinations
tests/claims/test_verdict_with_comparison_schema.py — Pydantic validation, edge cases (missing emphasis target, empty scenarios)
tests/claims/test_synthesis.py — fixture → claim; field mappings; verdict label thresholds
tests/value_scout/test_scout.py — pattern fires on fixture; returns None when it shouldn't
tests/editor/test_validator.py — all six checks independently; pass/fail aggregation
tests/claims/test_representation.py — claim → rendered prose. Assert headline preserved verbatim; confidence rubric applied correctly
tests/claims/test_golden_e2e.py — end-to-end on Belmar fixture: claim built, scout fires, editor passes, representation produces expected prose + chart event payload

9.3 Feature flag tests

tests/test_feature_flags.py — env-var parsing; property-ID allowlist behavior

✋ Review gate 9. Confirm test plan before implementation.

10. Execution Order for Claude Code
Claude Code must execute these in order. Each step ends with git commit and review.

Feature flag module (§1) + tests
Claims package skeleton (§2.1–2.3): archetypes.py, base.py, __init__.py, schema tests for base
verdict_with_comparison.py schema (§2.4) + schema tests
Chart-rule verification (§2.5): verify existing chart infrastructure supports horizontal_bar_with_ranges or identify the exact UI addition needed. If UI addition is needed, stop and escalate — the plan says UI doesn't move.
Intent routing (§3) + tests
Synthesis producer (§4) + tests
Value Scout (§5) + tests
Editor (§6) + tests
Representation (§7) + prose prompt + tests
Dispatch wiring (§8)
End-to-end golden test (§9.2 test_golden_e2e.py)
Manual smoke test: flag on, Belmar fixture, observe SSE stream

After step 12, the wedge is done. Phase B begins.

11. Definition of Done for the Wedge
All of the following true simultaneously:

BRIARWOOD_CLAIMS_ENABLED=true with the Belmar fixture produces a claim-path response that is qualitatively better than the legacy path (subjective — you judge)
All new tests pass
All existing tests still pass (legacy path untouched)
Feature flag off produces byte-identical behavior to pre-wedge
Editor rejection falls back cleanly to legacy
No changes committed to any file in briarwood/modules/
No changes committed to any file in web/src/components/chat/ unless step 4 identified a required UI addition and you explicitly approved it
DESIGN_DOC.md and this file updated with any decisions made during build that diverged from the plan


12. What Gets Learned
The wedge answers these questions. Write the answers in a WEDGE_RETRO.md when done:

Did the claim-object-as-contract approach produce the quality improvement we predicted?
Where did the Briarwood module outputs need cleaning or enriching to fit the schema?
How much representation work stayed deterministic vs. needed LLM judgment?
Did Value Scout's one pattern produce genuine insights, noise, or nothing?
Did the Editor catch real problems, or was it redundant with Pydantic validation?
What's the next archetype to build, and why?


End of Phase 3 build plan. Review gates must be passed in order; do not skip ahead.