from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

from api.guardrails import (
    VerifierReport,
    strip_violating_sentences,
    verify_response,
)
from briarwood.agent.llm import LLMClient
from briarwood.cost_guard import BudgetExceeded

_logger = logging.getLogger(__name__)

# Minimal verifier-report shape used when the LLM is skipped due to budget
# exhaustion AND no structured_inputs were supplied (so no real verifier ran).
# Keeps the SSE `verifier_report` payload contract intact — the frontend can
# detect the fallback via `budget_exceeded: True` without a new event type.
_EMPTY_BUDGET_REPORT: dict[str, Any] = {
    "tier": None,
    "sentences_total": 0,
    "sentences_with_violations": 0,
    "ungrounded_declaration": False,
    "anchor_count": 0,
    "anchors": [],
    "violations": [],
    "budget_exceeded": True,
}

# Stopgap for grounding markers emitted by the LLM (`[[Module:field:value]]`).
# Step 6 parses these into structured anchor records upstream; we also strip
# them from the outgoing text so users never see the cruft. Pattern is greedy
# enough to catch nested `:` in values but bounded by the closing `]]`.
_GROUNDING_MARKER_RE = re.compile(r"\[\[[^\[\]]+?\]\]")

# AUDIT 1.3.5: narrative tiers that route to Anthropic Claude (Sonnet 4.6 by
# default). These prompts are the ones where the audit flagged OpenAI's prose
# quality: decision_summary softens bearish stances, edge under-weights
# downside catalysts, risk skews toward boilerplate. All three are prose-only
# renderers over structured inputs — no JSON-schema coupling to the model —
# so swapping the provider is a per-tier routing decision, not a refactor.
# Non-narrative tiers (projection, strategy, research, etc.) stay on the
# injected client unchanged.
NARRATIVE_ANTHROPIC_TIERS: frozenset[str] = frozenset(
    {"decision_summary", "edge", "risk"}
)
# Env override. Values: "auto" (default — Anthropic iff ANTHROPIC_API_KEY),
# "anthropic" (same as auto but explicit), "openai"/"off" (force OpenAI even
# when the key is present — useful for A/B or cost-cap scenarios).
NARRATIVE_PROVIDER_ENV = "BRIARWOOD_NARRATIVE_PROVIDER"

# Cached singleton. Init is cheap but not free, and the composer runs every
# turn on DECISION flows. Module-level cache avoids rebuilding per-call.
_narrative_anthropic_client: LLMClient | None = None


def _narrative_client_or_none() -> LLMClient | None:
    """Lazily resolve the Anthropic narrative client.

    AUDIT 1.3.5: returns ``None`` when narrative routing is disabled
    (explicit env opt-out, no ANTHROPIC_API_KEY, or SDK init failure) so
    the caller falls back to the injected OpenAI client. Env is re-read on
    every call — the client itself is cached once initialized.
    """
    global _narrative_anthropic_client
    mode = os.environ.get(NARRATIVE_PROVIDER_ENV, "auto").strip().lower()
    if mode in {"off", "openai"}:
        return None
    if mode not in {"auto", "anthropic"}:
        return None
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    if _narrative_anthropic_client is not None:
        return _narrative_anthropic_client
    try:
        from briarwood.agent.llm import AnthropicChatClient

        _narrative_anthropic_client = AnthropicChatClient()
    except Exception as exc:
        _logger.warning("narrative Anthropic init failed, staying on OpenAI: %s", exc)
        return None
    return _narrative_anthropic_client


def _resolve_llm_for_tier(llm: LLMClient, tier: str | None) -> LLMClient:
    """Route narrative tiers through Anthropic iff available; everything
    else keeps the injected (OpenAI) client unchanged."""
    if tier in NARRATIVE_ANTHROPIC_TIERS:
        anth = _narrative_client_or_none()
        if anth is not None:
            return anth
    return llm


def reset_narrative_client_cache() -> None:
    """Test hook — drop the cached Anthropic narrative client so env
    changes take effect on the next call."""
    global _narrative_anthropic_client
    _narrative_anthropic_client = None


# Env flag that toggles strict-regen mode. Default **on** (AUDIT 1.1.10): the
# verifier strips flagged sentences and issues a single regen retry when the
# strip count exceeds `STRICT_REGEN_THRESHOLD`. Explicit "0"/"false"/"off"
# disables and reverts to the advisory path (report emitted, text unmodified).
# Until the audit flip, this was default-off — the verifier was accumulating
# ungrounded-hedge telemetry without ever suppressing bad output.
STRICT_REGEN_FLAG = "BRIARWOOD_STRICT_REGEN"
# Number of sentences that must be stripped before we bother issuing a regen.
# One stray ungrounded number is cheaper to just drop than to pay another
# LLM round-trip for.
STRICT_REGEN_THRESHOLD = 2
# Only these violation kinds cause strip/regen. `forbidden_hedge` is recorded
# for drift telemetry but not worth retrying over.
_STRICT_KINDS: tuple[str, ...] = ("ungrounded_number", "ungrounded_entity")


def strip_grounding_markers(text: str) -> str:
    """Remove `[[Module:field:value]]` annotations from LLM output.

    Tightens whitespace left behind so prose reads naturally — markers are
    typically appended right after a number with no space, but we collapse any
    incidental double spaces that sneak through.
    """
    cleaned = _GROUNDING_MARKER_RE.sub("", text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" +([.,;:!?])", r"\1", cleaned)
    return cleaned.strip()


def _strict_regen_enabled() -> bool:
    """Read the env flag at call time so tests can toggle it per-case.

    AUDIT 1.1.10: default is now **on**. Unset / empty env var → strict mode.
    An explicit opt-out requires one of `"0" | "false" | "no" | "off"`."""
    raw = os.environ.get(STRICT_REGEN_FLAG, "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    return True


def _regen_user_prompt(original_user: str, report: VerifierReport) -> str:
    """Build the stricter retry prompt. Includes up to six flagged values so
    the LLM sees what not to restate, but bounded to keep the context small."""
    flagged = [v for v in report.violations if v.kind in _STRICT_KINDS]
    if not flagged:
        return original_user
    bullet_lines = "\n".join(
        f'- {v.kind}: "{v.value}" in sentence: {v.sentence!r}'
        for v in flagged[:6]
    )
    return (
        "Your previous draft violated grounding on:\n"
        f"{bullet_lines}\n\n"
        "Rewrite using only values present in the structured_inputs payload, "
        "or numbers you can cite with a [[Module:field:value]] marker. "
        "Do NOT restate any of the flagged values unless you cite them.\n\n"
        f"Original task:\n{original_user}"
    )


def _run_llm_with_verify(
    *,
    llm: LLMClient,
    system: str,
    user: str,
    structured_inputs: dict[str, Any] | None,
    tier: str | None,
    max_tokens: int,
) -> tuple[str, dict[str, Any] | None]:
    """Call the LLM, verify, and — when `BRIARWOOD_STRICT_REGEN` is on — strip
    flagged sentences plus (when ≥ threshold sentences are stripped) retry
    once with a stricter prompt.

    Returns `(cleaned_text, report_dict_or_none)`. Report is `None` only when
    `structured_inputs` is `None` (verifier skipped). If strict stripping
    would empty the text entirely, the un-stripped draft is returned instead
    so the user still sees a rendered response.
    """
    # AUDIT 1.3.5: narrative tiers (decision_summary/edge/risk) swap to
    # Anthropic when available. The strict-regen retry below reuses the same
    # resolved client so the whole tier stays on one provider.
    effective_llm = _resolve_llm_for_tier(llm, tier)

    budget_exceeded = False
    try:
        raw = effective_llm.complete(system=system, user=user, max_tokens=max_tokens).strip()
    except BudgetExceeded as exc:
        _logger.warning(
            "LLM budget cap reached in composer — falling back to deterministic text: %s",
            exc,
        )
        budget_exceeded = True
        raw = ""
    except Exception:
        raw = ""
    if structured_inputs is None:
        if budget_exceeded:
            return "", dict(_EMPTY_BUDGET_REPORT)
        return (strip_grounding_markers(raw) if raw else ""), None

    report = verify_response(raw, structured_inputs, tier=tier)
    strict = _strict_regen_enabled()
    sentences_stripped = 0
    regen_attempted = False

    if strict and raw:
        _, preview_stripped = strip_violating_sentences(
            raw, report, kinds=_STRICT_KINDS
        )
        if preview_stripped >= STRICT_REGEN_THRESHOLD:
            regen_attempted = True
            try:
                raw2 = effective_llm.complete(
                    system=system,
                    user=_regen_user_prompt(user, report),
                    max_tokens=max_tokens,
                ).strip()
            except BudgetExceeded as exc:
                _logger.warning(
                    "LLM budget cap reached during composer regen — keeping original draft: %s",
                    exc,
                )
                budget_exceeded = True
                raw2 = ""
            except Exception:
                raw2 = ""
            if raw2:
                report2 = verify_response(raw2, structured_inputs, tier=tier)
                # Keep the regen only if it actually improved grounding;
                # otherwise the stricter prompt made things worse and we
                # fall back to the original draft.
                if report2.sentences_with_violations < report.sentences_with_violations:
                    raw = raw2
                    report = report2

        stripped_draft, sentences_stripped = strip_violating_sentences(
            raw, report, kinds=_STRICT_KINDS
        )
        # If stripping erased everything, prefer showing the (flawed) draft
        # over a blank message; the report captures the violation count.
        final_raw = stripped_draft if stripped_draft else raw
        cleaned = strip_grounding_markers(final_raw) if final_raw else ""
    else:
        cleaned = strip_grounding_markers(raw) if raw else ""

    report_dict = report.to_dict()
    report_dict["budget_exceeded"] = budget_exceeded
    if strict:
        report_dict["strict_regen"] = {
            "enabled": True,
            "sentences_stripped": sentences_stripped,
            "regen_attempted": regen_attempted,
            "threshold": STRICT_REGEN_THRESHOLD,
        }
    return cleaned, report_dict


def compose_structured_response(
    *,
    llm: LLMClient | None,
    system: str,
    user: str,
    fallback: Callable[[], str],
    max_tokens: int = 280,
    structured_inputs: dict[str, Any] | None = None,
    tier: str | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Use the LLM as a renderer over structured facts, with a deterministic fallback.

    When `structured_inputs` and `tier` are supplied, also runs the advisory
    grounding verifier on the raw LLM draft (plus optional strict-regen
    stripping — see `_run_llm_with_verify`) and returns the report dict as the
    second tuple element. Otherwise the second element is `None`.
    """
    if llm is None:
        return fallback(), None
    cleaned, report = _run_llm_with_verify(
        llm=llm,
        system=system,
        user=user,
        structured_inputs=structured_inputs,
        tier=tier,
        max_tokens=max_tokens,
    )
    return (cleaned or fallback()), report


def complete_and_verify(
    *,
    llm: LLMClient,
    system: str,
    user: str,
    structured_inputs: dict[str, Any],
    tier: str,
    max_tokens: int = 300,
) -> tuple[str, dict[str, Any]]:
    """LLM render + grounding verifier in one call.

    Returns `(cleaned_text, verifier_report_dict)`. Cleaned text has
    `[[Module:field:value]]` markers stripped. When `BRIARWOOD_STRICT_REGEN`
    is set, sentences flagged with `ungrounded_number` / `ungrounded_entity`
    violations are dropped, and if the count reaches the threshold a single
    regen is attempted with a stricter prompt (see `_run_llm_with_verify`).

    No fallback path: callers gate on `llm is None` themselves and route to
    their tier-specific deterministic fallback before hitting this helper.
    """
    cleaned, report = _run_llm_with_verify(
        llm=llm,
        system=system,
        user=user,
        structured_inputs=structured_inputs,
        tier=tier,
        max_tokens=max_tokens,
    )
    # `structured_inputs` is required, so report is guaranteed non-None.
    assert report is not None
    return cleaned, report


def compose_contract_response(
    *,
    llm: LLMClient | None,
    contract_type: str,
    payload: dict[str, object],
    system: str,
    fallback: Callable[[], str],
    max_tokens: int = 320,
    structured_inputs: dict[str, Any] | None = None,
    tier: str | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Render a contract payload through the LLM without letting it invent data.

    Returns `(text, verifier_report_or_none)` — same tuple shape as
    `compose_structured_response`.
    """
    return compose_structured_response(
        llm=llm,
        system=system,
        user=f"contract_type: {contract_type}\npayload_json: {json.dumps(payload, default=str, sort_keys=True)}",
        fallback=fallback,
        max_tokens=max_tokens,
        structured_inputs=structured_inputs,
        tier=tier,
    )


__all__ = [
    "NARRATIVE_ANTHROPIC_TIERS",
    "NARRATIVE_PROVIDER_ENV",
    "STRICT_REGEN_FLAG",
    "STRICT_REGEN_THRESHOLD",
    "compose_structured_response",
    "compose_contract_response",
    "complete_and_verify",
    "reset_narrative_client_cache",
    "strip_grounding_markers",
]
