"""Review untracked questions and ask an LLM for rule/prompt patches.

Usage:
    python scripts/review_untracked.py [--since YYYY-MM-DD] [--limit N] [--llm]

Reads ``data/agent_feedback/untracked.jsonl``, groups by signal, prints a
histogram, and — with ``--llm`` — asks Claude for specific proposals:
new router rules, AnswerType additions, or handler sentinels to stop
triggering ``handler_no_help`` when the intent is actually handleable.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

LOG_PATH = Path("data/agent_feedback/untracked.jsonl")


def load_records(since: str | None, limit: int | None) -> list[dict]:
    if not LOG_PATH.exists():
        return []
    out: list[dict] = []
    with LOG_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if since and rec.get("ts", "") < since:
                continue
            out.append(rec)
    if limit:
        out = out[-limit:]
    return out


def summarize(records: list[dict]) -> None:
    by_signal: Counter[str] = Counter()
    by_type: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    for rec in records:
        for sig in rec.get("signals", []):
            by_signal[sig] += 1
            if len(examples[sig]) < 5:
                examples[sig].append(rec["text"])
        by_type[rec.get("answer_type", "?")] += 1

    print(f"Total untracked turns: {len(records)}\n")
    print("By signal:")
    for sig, count in by_signal.most_common():
        print(f"  {sig:22} {count}")
    print("\nBy answer_type (as classified):")
    for at, count in by_type.most_common():
        print(f"  {at:18} {count}")
    print("\nExamples:")
    for sig, texts in examples.items():
        print(f"\n[{sig}]")
        for t in texts:
            print(f"  - {t[:120]}")


def ask_llm(records: list[dict]) -> None:
    from briarwood.agent.llm import default_client

    client = default_client()
    if client is None:
        print("\n(no LLM client available — set ANTHROPIC_API_KEY)")
        return

    texts = [f"- [{r['answer_type']}/{'+'.join(r['signals'])}] {r['text']}" for r in records[-40:]]
    prompt = (
        "You audit a router that classifies real-estate questions into answer types "
        "(lookup, decision, comparison, search, research, visualize, rent_lookup, "
        "micro_location, projection, risk, edge, strategy, chitchat).\n\n"
        "Below are recent turns the router flagged as untracked. Propose concrete patches:\n"
        "1. Regex additions to briarwood/agent/router.py rules (which AnswerType, what phrase).\n"
        "2. Whether any questions suggest a missing AnswerType.\n"
        "3. Handler sentinel wording to stop triggering 'handler_no_help' when we actually answered.\n\n"
        "Turns:\n" + "\n".join(texts)
    )
    reply = client.complete(system="You are a terse engineering reviewer.", user=prompt, max_tokens=800)
    print("\n--- LLM review ---\n")
    print(reply)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="ISO date filter (e.g. 2026-04-01)")
    ap.add_argument("--limit", type=int, help="Only consider the last N records")
    ap.add_argument("--llm", action="store_true", help="Ask Claude for patch proposals")
    args = ap.parse_args()

    records = load_records(args.since, args.limit)
    if not records:
        print(f"No records in {LOG_PATH}")
        return
    summarize(records)
    if args.llm:
        ask_llm(records)


if __name__ == "__main__":
    main()
