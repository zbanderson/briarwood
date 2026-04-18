"""`python -m briarwood.agent` — minimal CLI REPL for the conversational agent.

No rich/textual deps. stdlib only. Prints the router's classification per turn
so the user can see what mode the system is in.
"""

from __future__ import annotations

import sys

from briarwood.agent.dispatch import contextualize_decision, dispatch
from briarwood.agent.llm import default_client
from briarwood.agent.router import classify
from briarwood.agent.session import Session


def _banner(session: Session) -> str:
    return (
        f"Briarwood chat (session {session.session_id}). "
        f"Type a question. Ctrl-C to exit.\n"
    )


def main(argv: list[str] | None = None) -> int:
    llm = default_client()
    session = Session()
    sys.stdout.write(_banner(session))
    if llm is None:
        sys.stdout.write("(no OPENAI_API_KEY — running in deterministic fallback mode)\n")
    sys.stdout.flush()

    while True:
        try:
            text = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.stdout.write("\n")
            break
        if not text:
            continue

        decision = classify(text, client=llm)
        decision = contextualize_decision(text, decision, session)
        sys.stdout.write(
            f"[route: {decision.answer_type.value} ({decision.confidence:.2f}) — {decision.reason}]\n"
        )
        sys.stdout.flush()

        try:
            response = dispatch(text, decision, session, llm)
        except KeyboardInterrupt:
            sys.stdout.write("\n")
            sys.stdout.flush()
            break
        except Exception as exc:  # surface the error, don't crash the REPL
            response = f"(agent error: {exc})"

        from briarwood.cost_guard import get_guard
        sys.stdout.write(f"\nbriarwood > {response}\n[budget: {get_guard().summary()}]\n\n")
        sys.stdout.flush()
        session.record(text, response, decision.answer_type.value)
        session.save()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
