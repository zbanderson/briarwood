"""Side-by-side: same question, no-LLM path vs LLM path.

Run: python scripts/llm_ab_demo.py
"""

from __future__ import annotations

from briarwood.agent.dispatch import dispatch
from briarwood.agent.llm import default_client
from briarwood.agent.router import classify
from briarwood.agent.session import Session
from briarwood.cost_guard import get_guard

QUESTIONS = [
    # 5 Core Investment Questions
    "should I buy 526 West End?",                       # DECISION
    "what could go wrong with this one?",               # RISK
    "where is the value on 526?",                       # EDGE
    "what does this become over 5 years?",              # PROJECTION
    "what's the best way to play this?",                # STRATEGY
    # Ambiguous / factual
    "what's the address?",                              # LOOKUP
    "how close to the beach?",                          # MICRO_LOCATION
    "does 526 make sense for a family who wants to walk to the ocean?",  # ambiguous
]


def _run(label: str, llm, *, show_route: bool = True) -> None:
    session = Session()
    session.current_property_id = "526-west-end-ave"
    print(f"\n{'='*70}\n{label}\n{'='*70}")
    for q in QUESTIONS:
        d = classify(q, client=llm)
        print(f"\n> {q}")
        if show_route:
            marker = "LLM" if d.llm_suggestion else "rule"
            print(f"  [route: {d.answer_type.value} (conf {d.confidence:.2f}, {marker}) — {d.reason}]")
        try:
            ans = dispatch(q, d, session, llm)
        except Exception as e:
            ans = f"(error: {e})"
        print(f"  briarwood > {ans}")
    print(f"\n  [budget: {get_guard().summary()}]")


def main() -> None:
    _run("A) NO LLM — deterministic fallback", None)
    llm = default_client()
    if llm is None:
        print("\n(No OPENAI_API_KEY — skipping LLM pass)")
        return
    _run("B) WITH LLM — Claude/GPT facilitates router + composes answers", llm)


if __name__ == "__main__":
    main()
