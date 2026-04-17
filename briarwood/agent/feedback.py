"""Untracked-question logger.

Every user turn is appended to ``data/agent_feedback/untracked.jsonl`` when
one of these signals fires, so we can review what the router/handlers
don't yet handle well and patch rules accordingly:

- router confidence < 0.5
- router reason is "default fallback" (no cache rule, no LLM available)
- router reason is "llm classify" (LLM owned the decision — candidate for
  promotion to a cache rule if the pattern appears in volume)
- handler took the deterministic (no-LLM) fallback path — important signal
  for "this deployment isn't narrating" and for sampling which intents
  actually need LLM shaping.
- handler returned a "no-help" sentinel (couldn't resolve, missing property, etc.)

The log is plain jsonl — one record per line — safe to tail, grep, or
feed into ``scripts/review_untracked.py`` for batch analysis.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from briarwood.agent.router import RouterDecision

LOG_DIR = Path("data/agent_feedback")
LOG_PATH = LOG_DIR / "untracked.jsonl"

_NO_HELP_RE = re.compile(
    r"(couldn'?t|could not|unable to|i don'?t|no match|which property|"
    r"not sure which|please clarify|missing|no data|nothing to show)",
    re.IGNORECASE,
)


def _classify_signal(
    decision: RouterDecision,
    response: str,
    extra: dict[str, Any] | None = None,
) -> list[str]:
    signals: list[str] = []
    if decision.confidence < 0.5:
        signals.append("low_confidence")
    if decision.reason == "default fallback":
        signals.append("default_fallback")
    if decision.reason == "llm classify":
        signals.append("llm_classify")
    if _NO_HELP_RE.search(response or ""):
        signals.append("handler_no_help")
    # Deterministic-mode turns matter for telemetry: we want to see which
    # intents are shipping without LLM narration so we can prioritize
    # prompt work (or detect an unconfigured deployment).
    if extra and extra.get("llm_used") is False:
        signals.append("llm_fallback")
    return signals


def log_turn(
    *,
    text: str,
    decision: RouterDecision,
    response: str,
    extra: dict[str, Any] | None = None,
) -> list[str]:
    """Append a turn to the untracked log when any tracking signal fires.

    Returns the list of signals logged (empty if the turn tracked cleanly
    and nothing was written).
    """
    signals = _classify_signal(decision, response, extra)
    if not signals:
        return []

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "text": text,
        "answer_type": decision.answer_type.value,
        "confidence": decision.confidence,
        "reason": decision.reason,
        "llm_suggestion": decision.llm_suggestion.value if decision.llm_suggestion else None,
        "target_refs": list(decision.target_refs),
        "signals": signals,
        "response_preview": (response or "")[:280],
    }
    if extra:
        record["extra"] = extra

    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return signals
