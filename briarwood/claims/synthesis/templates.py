"""Deterministic text templates used by claim synthesis.

Kept tiny + f-string-based on purpose: the representation LLM writes the
prose; templates only fix the verdict headline and bridge wording so the
claim can be read and edited before LLM prose is generated.
"""
from __future__ import annotations

VERDICT_HEADLINE: dict[str, str] = {
    "value_find": "Priced ${delta_abs:,.0f} under fair market value (-{delta_pct:.1f}%).",
    "fair": "Priced roughly at fair market value.",
    "overpriced": "Priced ${delta_abs:,.0f} above fair market value (+{delta_pct:.1f}%).",
    "insufficient_data": "Not enough comparable evidence to call the price.",
}

BRIDGE_SENTENCE: str = (
    "Here's how this property compares against recent sales of similar "
    "and upgraded configurations in the area."
)

DEFAULT_NEXT_QUESTIONS: list[dict[str, str]] = [
    {
        "text": "What does the risk picture look like on this one?",
        "routes_to": "risk",
    },
    {
        "text": "How does this perform as a rental over a 5-year hold?",
        "routes_to": "rent_ramp",
    },
    {
        "text": "What would renovating this unlock in resale value?",
        "routes_to": "value_scout",
    },
]
