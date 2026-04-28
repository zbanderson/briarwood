"""Layer 3 LLM synthesizer: prose from a full UnifiedIntelligenceOutput.

Cycle 4 of OUTPUT_QUALITY_HANDOFF_PLAN.md. The deterministic synthesizer
at ``briarwood.synthesis.structured.build_unified_output`` populates a
fully-typed ``UnifiedIntelligenceOutput`` from module results plus the
interaction trace; Cycle 2's ``run_chat_tier_analysis`` makes that
output co-resident in one place per chat turn. This module is the
prose-layer companion: an LLM that reads the full unified output and
the user's intent contract and writes 3-7 sentences of intent-aware
prose.

Design notes (per OUTPUT_QUALITY_HANDOFF_PLAN.md Cycle 4 and
DECISIONS.md "Composer guardrails: independent strip toggle +
reframe-licensed regen prompt" 2026-04-25):

- **Free voice.** The system prompt explicitly licenses re-framing,
  paraphrase, and voice choice. The composer's previous "rewrite using
  only values present in" wording produced robotic prose; the same
  loosening principle applies here.
- **Numeric guardrail (the only hard rule).** Every number cited must
  round to a value present in the unified output. Enforced via
  ``api.guardrails.verify_response`` over the unified output as
  ``structured_inputs``. On threshold-level violations the synthesizer
  attempts a single regen with a stricter prompt; if that doesn't help,
  the draft is returned with the violations recorded in the report so
  the caller can decide whether to fall back.
- **Observability.** The single LLM call is wrapped in
  ``complete_text_observed`` with surface name ``synthesis.llm`` so it
  shows up in the per-turn manifest's ``llm_calls`` list distinct from
  ``composer.draft`` and ``agent_router.classify``.
- **No fallback inside this module.** Returns ``("", report)`` when the
  LLM is missing or every attempt fails. Callers — specifically
  ``handle_browse`` after Cycle 4 — fall back to the existing
  ``compose_browse_surface`` composer when the synthesizer can't return
  prose.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from briarwood.agent.composer import (
    STRICT_REGEN_THRESHOLD,
    strip_grounding_markers,
)
from briarwood.agent.llm import LLMClient
from briarwood.agent.llm_observability import complete_text_observed
from briarwood.claims.base import SurfacedInsight
from briarwood.cost_guard import BudgetExceeded
from briarwood.intent_contract import IntentContract
from briarwood.synthesis.feedback_hint import current_feedback_hint

from api.guardrails import VerifierReport, verify_response

# The verifier kinds that count toward the regen threshold. Mirrors the
# composer's private _STRICT_KINDS — kept here as a copy so the synthesizer
# doesn't depend on a private symbol.
_STRICT_KINDS: tuple[str, ...] = ("ungrounded_number", "ungrounded_entity")

_logger = logging.getLogger(__name__)


_SYSTEM_PROMPT_NEWSPAPER = """You are Briarwood's Layer 3 prose synthesizer.

Briarwood's deterministic models have already produced a structured
`unified` output for one property. It contains the verdict
(`recommendation`, `decision`, `decision_stance`, `best_path`), the
value position (ask vs fair value), key value drivers, key risks,
trust flags, primary value source, optionality signals, and per-module
evidence. You also receive an `intent` contract describing what the
user actually asked for (the `answer_type` and `core_questions`).

Optionally you receive `charts` — the list of charts Briarwood's
Representation Agent picked to render alongside your prose. Each entry
has a `kind` (e.g. `value_opportunity`, `scenario_fan`, `market_trend`)
and a one-line `claim` describing why it was picked. When prose
references the substance of a chart, name what the user will see
(e.g. "the scenario fan shows…", "the town-trend line…") so chart and
prose tie together. Reference at most one or two charts in the body —
do not enumerate them all.

Optionally you receive `comp_roster` — the live comp set the user will
see in the CMA chart, one dict per comp with `address`, `ask_price`,
`listing_status` ("sold" or "active"), `is_cross_town` (bool), and
`town`. When `comp_roster` is present, the comp anchor is no longer
abstract: name 1–2 specific comps in the body, distinguishing closed
sales from active asks, and qualify cross-town rows. Use this exact
language pattern (preserve the SOLD vs ACTIVE vs cross-town split):

- SOLD same-town: "1209 16th Ave sold for $800k"
- ACTIVE: "812 16th Ave is currently asking $799k"
- SOLD cross-town: "1402 Ocean Ave in Bradley Beach sold for $760k"

Pick comps that actually carry the verdict — closest to the subject's
ask, or the ones that clinch the premium / discount read. Do not
enumerate the whole roster. Cite numbers verbatim from `comp_roster`
entries; the numeric-grounding rule below covers comp asks too.

Optionally you receive `scout_insights` — Briarwood's Value Scout has
already scanned the unified output for non-obvious angles the user
did not explicitly ask about. Each entry has `headline`, `reason`,
`category` (e.g. `rent_angle`, `town_trend`, `adu_signal`,
`comp_anomaly`), `confidence` (0-1), and `supporting_fields` (dotted
paths into `unified` the angle rests on). When `scout_insights` is
present and non-empty, the `## What's Interesting` beat MUST weave
the highest-confidence insight into prose. Paraphrase the headline in
your own voice (do NOT quote it verbatim), name the supporting field
so the user knows what evidence backs it, and tease the drilldown
without spoiling the full reason — the user will see the rest in a
dedicated card. Pick exactly one insight to weave in; the others stay
available for the drilldown surface. If `scout_insights` is empty or
absent, fall back to your usual "non-obvious angle" judgment for the
beat.

Your job is to write a front-page-newspaper-style response for the
user. The user is making a six-figure financial decision and is
scanning fast — every section must hook the eye and pay off.

STRUCTURE (mandatory):

Use markdown section headers. Open with a one-line bold lead, then
2-4 short sections. Each section starts with `## ` on its own line
followed by a blank line and a body paragraph (1-3 sentences).

Pick section names that fit the intent. Strong defaults by answer_type:

- decision / browse / lookup → `## Headline` · `## Why` · `## What's Interesting` · `## What I'd Watch`
- risk → `## Headline` · `## Why` · `## Trust Gaps` · `## What I'd Watch`
- projection / strategy → `## Headline` · `## Why` · `## Scenarios` · `## What I'd Watch`
- rent_lookup → `## Headline` · `## Rent Today` · `## What's Interesting` · `## What I'd Watch`
- edge → `## Headline` · `## Why` · `## What's Interesting` · `## What I'd Watch`

`## Headline` is a single sentence — the lead. The verdict + the most
specific evidence. No throat-clearing.
`## Why` is the supporting reasoning — name the comp anchor, the
premium/discount, the carry math.
`## What's Interesting` is the non-obvious angle — optionality,
hidden upside, an underweighted driver. Skip if there is nothing
non-obvious to say; do not pad.
`## What I'd Watch` is the trust gap, the risk to verify, or the
condition that would change the call.

VOICE — match the intent's `answer_type`. Each tier has its own
posture; pick the one that matches and write to it:

- browse → first-impression analyst. Frame the property the way you'd
  brief a buyer who just clicked on the listing. Lead with the headline
  read; pay off the "why" with the comp anchor or premium read.
- decision → buy/pass advisor. The user is asking should-I-buy. Lead
  with the recommendation and the single most important piece of
  evidence. Be direct.
- risk → underwriter naming the gaps. Lead with the most material risk
  flag or trust gap; do not soften by burying it in qualifiers. Each
  paragraph names a specific concern, not generic uncertainty.
- projection → 5-year scenario writer. Lead with the base-case
  trajectory; make the bull/bear range concrete. Use scenario
  vocabulary ("base case", "downside floor"), not abstract claims.
- strategy → strategist mapping the move. Lead with the recommended
  path (offer, hold, walk); the body explains why this path wins
  versus the alternatives.
- rent_lookup → rent-side underwriter. Lead with the rent-vs-carry
  delta. The body names the haircut, the working rent, and the
  break-even gap.
- edge → skeptic. The user is testing a value claim; lead with what
  makes you cautious or where the evidence is thinner than headline
  suggests.

In all cases: human, conversational, concrete. Re-frame, paraphrase,
choose emphasis. Do NOT echo field names. Do NOT lecture about
uncertainty in the abstract — if a trust_flag matters, name what
specifically is missing or shaky. Section bodies are short paragraphs
(1-3 sentences), not bullet lists.

NUMERIC GROUNDING (the only hard rule): every dollar amount,
percentage, multiplier, year, or count you cite must round to a value
present in the `unified` JSON. Rounded forms like '$820k' or 'roughly
820 thousand' are fine when they round to an actual value. Do not
invent numbers, comp counts, or rates. If you don't have a number to
support a claim, omit the number rather than estimate.
"""


# Plain-prose fallback for the BRIARWOOD_SYNTHESIS_NEWSPAPER=0 kill switch.
# Same numeric-grounding rule, no markdown structure — drops the synthesizer
# back to the Cycle 4 voice if the newspaper format ever causes downstream
# breakage.
_SYSTEM_PROMPT_PLAIN = """You are Briarwood's Layer 3 prose synthesizer.

Briarwood's deterministic models have already produced a structured
`unified` output for one property. It contains the verdict, the value
position (ask vs fair value), key value drivers, key risks, trust
flags, primary value source, optionality signals, and per-module
evidence. You also receive an `intent` contract describing what the
user actually asked for (the `answer_type` and `core_questions`).

Optionally you receive `comp_roster` — the live comp set the user will
see in the CMA chart. Each entry has `address`, `ask_price`,
`listing_status` ("sold" or "active"), `is_cross_town` (bool), and
`town`. When present, name 1–2 specific comps in the prose,
distinguishing closed sales ("sold for $X") from active asks
("currently asking $Y") and qualifying cross-town rows ("a $Z sale in
[neighbor town]"). Pick comps that carry the verdict; do not enumerate
the roster. Comp ask prices are grounded values for the numeric rule.

Your job is to write 3-7 sentences of intent-aware prose for the user.
Lead with what the user asked about. If the intent is should_i_buy,
lead with the buy/pass framing and the supporting drivers. If
what_could_go_wrong, lead with risk and trust gaps. If where_is_value,
lead with the value angle, premium/discount, and any optionality. If
best_path, lead with the action recommendation. If the intent has more
than one core question, weave them in order.

Voice: human, conversational, concrete. Re-frame, paraphrase, choose
emphasis. Do NOT echo field names. Do NOT write markdown headers.
Plain prose only. Do NOT lecture about uncertainty in the abstract —
if a trust_flag matters, name what specifically is missing or shaky.

NUMERIC GROUNDING (the only hard rule): every dollar amount,
percentage, multiplier, year, or count you cite must round to a value
present in the `unified` JSON. Rounded forms like '$820k' or 'roughly
820 thousand' are fine when they round to an actual value. Do not
invent numbers, comp counts, or rates. If you don't have a number to
support a claim, omit the number rather than estimate.
"""


def _newspaper_voice_enabled() -> bool:
    """Read the BRIARWOOD_SYNTHESIS_NEWSPAPER kill switch.

    Default is ON. ``"0"``, ``"false"``, ``"off"``, ``"no"`` (case-insensitive)
    disable the newspaper voice and revert to the plain-prose system prompt.
    Any other value (or unset) keeps the newspaper voice."""

    raw = os.environ.get("BRIARWOOD_SYNTHESIS_NEWSPAPER", "")
    if not raw:
        return True
    return raw.strip().lower() not in {"0", "false", "off", "no"}


def _resolve_system_prompt() -> str:
    """Pick the active system prompt based on the kill switch."""

    return _SYSTEM_PROMPT_NEWSPAPER if _newspaper_voice_enabled() else _SYSTEM_PROMPT_PLAIN


# Back-compat alias for any external import that referenced the old name.
# Equal to the active prompt at import time; callers should use
# ``_resolve_system_prompt()`` for runtime correctness.
_SYSTEM_PROMPT = _SYSTEM_PROMPT_NEWSPAPER


def _user_prompt(
    unified: dict[str, Any],
    intent: IntentContract,
    charts: list[dict[str, Any]] | None = None,
    comp_roster: list[dict[str, Any]] | None = None,
    scout_insights: list[SurfacedInsight] | None = None,
) -> str:
    """Serialize the unified output, intent contract, the selected chart
    list, the live comp roster, and the scout insights as the user message.

    Each optional input is included only when non-empty so the LLM does
    not see a flock of empty arrays for turns that legitimately have no
    chart, no comp roster, or no scout output.
    """

    intent_payload = intent.model_dump(mode="json")
    body: dict[str, Any] = {
        "intent": intent_payload,
        "unified": unified,
    }
    if charts:
        body["charts"] = charts
    if comp_roster:
        body["comp_roster"] = comp_roster
    if scout_insights:
        body["scout_insights"] = [
            insight.model_dump(mode="json") for insight in scout_insights
        ]
    return json.dumps(body, default=str, sort_keys=True)


def _verifier_inputs(
    unified: dict[str, Any],
    comp_roster: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Build the structured-inputs payload the verifier scans for grounded
    values. The unified output is the canonical source; when comp_roster is
    provided, comp ask prices (and per-row addresses / towns) are folded in
    so citations like "1209 16th Ave sold for $800k" do not get flagged as
    ungrounded."""

    if not comp_roster:
        return unified
    return {**unified, "comp_roster": comp_roster}


def _regen_user_prompt(original_user: str, report: VerifierReport) -> str:
    """Build the regen prompt with up to six flagged values + free-voice license."""

    flagged = [v for v in report.violations if v.kind in _STRICT_KINDS]
    if not flagged:
        return original_user
    bullet_lines = "\n".join(
        f'- "{v.value}" in sentence: {v.sentence!r}'
        for v in flagged[:6]
    )
    return (
        "Your previous draft cited numbers not present in the `unified` "
        "JSON:\n"
        f"{bullet_lines}\n\n"
        "Rewrite the draft. You have full freedom to reframe, paraphrase, "
        "and choose voice — keep it human and conversational. The only "
        "hard rule is numeric: every number you mention must round to a "
        "value present in `unified`. If you don't have a number to "
        "support a claim, omit the number rather than estimate or "
        "invent.\n\n"
        f"Original task:\n{original_user}"
    )


def synthesize_with_llm(
    *,
    unified: dict[str, Any],
    intent: IntentContract,
    llm: LLMClient | None,
    max_tokens: int = 360,
    charts: list[dict[str, Any]] | None = None,
    comp_roster: list[dict[str, Any]] | None = None,
    scout_insights: list[SurfacedInsight] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Render intent-aware prose from a full UnifiedIntelligenceOutput.

    Returns ``(prose, verifier_report_dict)``. ``prose`` is empty when
    the LLM is missing, the call fails, or every retry produces an
    empty draft — callers should treat empty prose as a signal to fall
    back to the deterministic / composer prose path.

    The numeric guardrail mirrors the composer's verifier
    infrastructure (api/guardrails.verify_response over ``unified`` as
    structured_inputs). When ``STRICT_REGEN_THRESHOLD`` flagged
    sentences are present in the first draft, a single regen attempt
    runs with a stricter prompt that names the offending values; the
    regen replaces the draft only if it actually improved grounding.
    """

    if llm is None or not unified:
        return "", {"empty": True, "reason": "llm_or_unified_missing"}

    user_prompt = _user_prompt(
        unified,
        intent,
        charts=charts,
        comp_roster=comp_roster,
        scout_insights=scout_insights,
    )
    verifier_inputs = _verifier_inputs(unified, comp_roster)
    system_prompt = _resolve_system_prompt()
    # Stage 2 read-back: when the conversation has a recent thumbs-down,
    # append a "vary your framing" directive so the next turn doesn't
    # repeat the framing that just got rated unfavorably. Numeric / citation
    # rules from the base prompt are unchanged.
    hint = current_feedback_hint()
    if hint:
        system_prompt = f"{system_prompt}\n\n{hint}"
    surface = "synthesis.llm"
    metadata = {
        "tier": "synthesis_llm",
        "answer_type": intent.answer_type,
        "voice": "newspaper" if system_prompt is _SYSTEM_PROMPT_NEWSPAPER else "plain",
    }

    try:
        raw = complete_text_observed(
            surface=surface,
            system=system_prompt,
            user=user_prompt,
            provider=llm.__class__.__name__,
            model=None,
            metadata=metadata,
            call=lambda: llm.complete(
                system=system_prompt,
                user=user_prompt,
                max_tokens=max_tokens,
            ),
        ).strip()
    except BudgetExceeded as exc:
        _logger.warning("synthesis.llm budget cap reached: %s", exc)
        return "", {"empty": True, "reason": "budget_exceeded"}
    except Exception as exc:  # noqa: BLE001 — caller falls back to composer
        _logger.warning("synthesis.llm draft failed: %s", exc)
        return "", {"empty": True, "reason": f"exception:{type(exc).__name__}"}

    if not raw:
        return "", {"empty": True, "reason": "blank_draft"}

    report = verify_response(raw, verifier_inputs, tier="synthesis_llm")
    flagged_count = sum(
        1 for v in report.violations if v.kind in _STRICT_KINDS
    )

    if flagged_count >= STRICT_REGEN_THRESHOLD:
        try:
            regen_user = _regen_user_prompt(user_prompt, report)
            raw2 = complete_text_observed(
                surface="synthesis.llm.regen",
                system=system_prompt,
                user=regen_user,
                provider=llm.__class__.__name__,
                model=None,
                metadata=metadata,
                call=lambda: llm.complete(
                    system=system_prompt,
                    user=regen_user,
                    max_tokens=max_tokens,
                ),
            ).strip()
        except BudgetExceeded as exc:
            _logger.warning(
                "synthesis.llm regen budget cap — keeping original draft: %s",
                exc,
            )
            raw2 = ""
        except Exception as exc:  # noqa: BLE001 — keep original draft
            _logger.warning("synthesis.llm regen failed: %s", exc)
            raw2 = ""

        if raw2:
            report2 = verify_response(raw2, verifier_inputs, tier="synthesis_llm")
            # Keep the regen only when it actually reduced violations.
            if report2.sentences_with_violations < report.sentences_with_violations:
                raw = raw2
                report = report2

    cleaned = strip_grounding_markers(raw) if raw else ""
    report_dict = report.to_dict()
    report_dict["empty"] = not bool(cleaned)
    report_dict["surface"] = surface
    return cleaned, report_dict


__all__ = ["synthesize_with_llm"]
