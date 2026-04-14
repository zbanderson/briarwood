"""Keyword learner: identifies misclassified question patterns from feedback logs
and suggests new keyword → intent mappings for the router.

The learner reads intelligence_feedback.jsonl, finds records tagged
``unknown-question-pattern`` or with low parser confidence, extracts
distinctive n-grams, and writes suggested additions to a JSON file
that the router loads at startup.

Usage:
    python -m briarwood.feedback.keyword_learner           # print suggestions
    python -m briarwood.feedback.keyword_learner --apply   # write to learned_keywords.json
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from briarwood.feedback.analyzer import load_records

LEARNED_KEYWORDS_PATH = Path(__file__).resolve().parents[2] / "data" / "learning" / "learned_keywords.json"


def load_learned_keywords() -> dict[str, list[str]]:
    """Load the learned keyword → intent mapping from disk."""
    if not LEARNED_KEYWORDS_PATH.exists():
        return {}
    try:
        data = json.loads(LEARNED_KEYWORDS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {k: list(v) for k, v in data.items() if isinstance(v, list)}
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def save_learned_keywords(keywords: dict[str, list[str]]) -> Path:
    """Write the learned keyword mapping to disk."""
    LEARNED_KEYWORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEARNED_KEYWORDS_PATH.write_text(
        json.dumps(keywords, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return LEARNED_KEYWORDS_PATH


def suggest_keywords(records: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Analyze misclassified or low-confidence records and suggest new keywords.

    Returns a list of suggestion dicts:
    ``{"keyword": str, "suggested_intent": str, "source_questions": list[str], "reason": str}``
    """
    if records is None:
        records = load_records()

    # Collect questions that had routing problems
    problem_questions: list[tuple[str, str, float]] = []  # (question, routed_intent, confidence)
    for r in records:
        tags = r.get("tags") or []
        parser = r.get("parser_output") or {}
        conf = float(parser.get("confidence") or 1.0)
        question = str(r.get("question") or "").strip().lower()
        intent = str(parser.get("intent_type") or "")

        if not question:
            continue

        is_problem = (
            "unknown-question-pattern" in tags
            or conf < 0.60
            or r.get("was_conditional_answer")
        )
        if is_problem:
            problem_questions.append((question, intent, conf))

    if not problem_questions:
        return []

    # Extract distinctive 2-3 word phrases from problem questions
    ngram_to_intent: dict[str, Counter[str]] = {}
    ngram_sources: dict[str, list[str]] = {}
    for question, intent, _conf in problem_questions:
        words = _tokenize(question)
        for n in (2, 3):
            for i in range(len(words) - n + 1):
                gram = " ".join(words[i : i + n])
                if _is_stopword_ngram(gram):
                    continue
                if gram not in ngram_to_intent:
                    ngram_to_intent[gram] = Counter()
                    ngram_sources[gram] = []
                ngram_to_intent[gram][intent] += 1
                if len(ngram_sources[gram]) < 3:
                    ngram_sources[gram].append(question)

    # Filter: keep n-grams that appear 2+ times with a dominant intent
    from briarwood.router import INTENT_KEYWORDS
    existing_keywords = {kw for keywords in INTENT_KEYWORDS.values() for kw in keywords}

    suggestions: list[dict[str, Any]] = []
    for gram, intent_counts in ngram_to_intent.items():
        total = sum(intent_counts.values())
        if total < 2:
            continue
        if gram in existing_keywords:
            continue
        dominant_intent, dominant_count = intent_counts.most_common(1)[0]
        if dominant_count / total < 0.6:
            continue
        suggestions.append({
            "keyword": gram,
            "suggested_intent": dominant_intent,
            "count": total,
            "source_questions": ngram_sources.get(gram, [])[:3],
            "reason": f"Appeared in {total} misrouted questions, {dominant_count}/{total} mapped to {dominant_intent}",
        })

    suggestions.sort(key=lambda x: x["count"], reverse=True)
    return suggestions[:20]


def apply_suggestions(suggestions: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Merge suggestions into the learned keywords file.

    Returns the updated learned keywords dict.
    """
    current = load_learned_keywords()
    for s in suggestions:
        intent = s["suggested_intent"]
        keyword = s["keyword"]
        if intent not in current:
            current[intent] = []
        if keyword not in current[intent]:
            current[intent].append(keyword)
    save_learned_keywords(current)
    return current


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase alpha tokens."""
    return [w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 1]


_STOP_WORDS = frozenset(
    "the a an in on at to for of is it this that and or but with from by as be"
    " we i my our me do does can could would should will what how why which".split()
)


def _is_stopword_ngram(gram: str) -> bool:
    """Return True if all words in the n-gram are stop words."""
    words = gram.split()
    return all(w in _STOP_WORDS for w in words)


if __name__ == "__main__":
    suggestions = suggest_keywords()
    if not suggestions:
        print("No keyword suggestions found — routing is handling all patterns well.")
        sys.exit(0)

    print(f"Found {len(suggestions)} keyword suggestions:\n")
    for s in suggestions:
        print(f"  \"{s['keyword']}\" → {s['suggested_intent']}  ({s['count']}x)")
        print(f"    Reason: {s['reason']}")
        for q in s["source_questions"][:2]:
            print(f"    Example: \"{q}\"")
        print()

    if "--apply" in sys.argv:
        updated = apply_suggestions(suggestions)
        print(f"Applied {len(suggestions)} suggestions to {LEARNED_KEYWORDS_PATH}")
        print(f"Total learned keywords: {sum(len(v) for v in updated.values())}")
