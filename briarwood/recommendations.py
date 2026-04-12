from __future__ import annotations

CANONICAL_RECOMMENDATION_LABELS: tuple[str, str, str] = ("Buy", "Neutral", "Avoid")


def recommendation_label_from_score(score: float) -> str:
    if score >= 3.30:
        return "Buy"
    if score >= 2.50:
        return "Neutral"
    return "Avoid"


def recommendation_action_from_score(score: float) -> str:
    label = recommendation_label_from_score(score)
    if label == "Buy":
        return "The setup is favorable enough to keep moving with focused diligence on the weakest point."
    if label == "Neutral":
        return "The thesis is mixed. Resolve the top gap before taking a position."
    return "The current evidence does not support moving forward."


def normalize_recommendation_label(label: str | None) -> str:
    normalized = (label or "").strip().lower()
    if normalized in {"buy", "lean buy", "strong buy", "high conviction buy", "attractive"}:
        return "Buy"
    if normalized in {"neutral", "hold", "hold / dig deeper", "dig deeper", "caution"}:
        return "Neutral"
    if normalized in {"avoid", "lean avoid", "lean away", "pass", "lean pass"}:
        return "Avoid"
    return "Neutral"


def recommendation_rank(label: str | None) -> int:
    return {
        "Avoid": 0,
        "Neutral": 1,
        "Buy": 2,
    }.get(normalize_recommendation_label(label), 1)


def downgrade_recommendation(label: str, steps: int = 1) -> str:
    ordered = ["Avoid", "Neutral", "Buy"]
    idx = recommendation_rank(label)
    return ordered[max(0, idx - steps)]


def cap_recommendation(label: str, cap: str) -> str:
    return label if recommendation_rank(label) <= recommendation_rank(cap) else normalize_recommendation_label(cap)
