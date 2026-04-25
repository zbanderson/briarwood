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
from typing import Any

from briarwood.agent.composer import (
    STRICT_REGEN_THRESHOLD,
    strip_grounding_markers,
)
from briarwood.agent.llm import LLMClient
from briarwood.agent.llm_observability import complete_text_observed
from briarwood.cost_guard import BudgetExceeded
from briarwood.intent_contract import IntentContract

from api.guardrails import VerifierReport, verify_response

# The verifier kinds that count toward the regen threshold. Mirrors the
# composer's private _STRICT_KINDS — kept here as a copy so the synthesizer
# doesn't depend on a private symbol.
_STRICT_KINDS: tuple[str, ...] = ("ungrounded_number", "ungrounded_entity")

_logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are Briarwood's Layer 3 prose synthesizer.

Briarwood's deterministic models have already produced a structured
`unified` output for one property. It contains the verdict
(`recommendation`, `decision`, `decision_stance`, `best_path`), the
value position (ask vs fair value), key value drivers, key risks,
trust flags, primary value source, optionality signals, and per-module
evidence. You also receive an `intent` contract describing what the
user actually asked for (the `answer_type` and `core_questions`).

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


def _user_prompt(unified: dict[str, Any], intent: IntentContract) -> str:
    """Serialize the unified output and intent contract as the user message."""

    intent_payload = intent.model_dump(mode="json")
    body = {
        "intent": intent_payload,
        "unified": unified,
    }
    return json.dumps(body, default=str, sort_keys=True)


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

    user_prompt = _user_prompt(unified, intent)
    surface = "synthesis.llm"
    metadata = {
        "tier": "synthesis_llm",
        "answer_type": intent.answer_type,
    }

    try:
        raw = complete_text_observed(
            surface=surface,
            system=_SYSTEM_PROMPT,
            user=user_prompt,
            provider=llm.__class__.__name__,
            model=None,
            metadata=metadata,
            call=lambda: llm.complete(
                system=_SYSTEM_PROMPT,
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

    report = verify_response(raw, unified, tier="synthesis_llm")
    flagged_count = sum(
        1 for v in report.violations if v.kind in _STRICT_KINDS
    )

    if flagged_count >= STRICT_REGEN_THRESHOLD:
        try:
            regen_user = _regen_user_prompt(user_prompt, report)
            raw2 = complete_text_observed(
                surface="synthesis.llm.regen",
                system=_SYSTEM_PROMPT,
                user=regen_user,
                provider=llm.__class__.__name__,
                model=None,
                metadata=metadata,
                call=lambda: llm.complete(
                    system=_SYSTEM_PROMPT,
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
            report2 = verify_response(raw2, unified, tier="synthesis_llm")
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
