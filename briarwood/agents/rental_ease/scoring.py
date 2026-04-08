from __future__ import annotations

from briarwood.scoring import clamp_score


def liquidity_view_to_score(view: str | None) -> float | None:
    if view is None:
        return None
    return {
        "strong": 82.0,
        "normal": 62.0,
        "fragile": 38.0,
    }[view]


def rent_support_to_score(
    *,
    income_support_ratio: float | None,
    price_to_rent: float | None,
) -> float | None:
    if income_support_ratio is None and price_to_rent is None:
        return None

    score = 45.0
    if income_support_ratio is not None:
        if income_support_ratio >= 1.1:
            score = 88.0
        elif income_support_ratio >= 0.9:
            score = 68.0
        elif income_support_ratio >= 0.75:
            score = 52.0
        elif income_support_ratio >= 0.6:
            score = 40.0
        else:
            score = 26.0

    if price_to_rent is not None:
        if price_to_rent < 15:
            score += 10.0
        elif price_to_rent <= 20:
            score += 2.0
        elif price_to_rent > 24:
            score -= 10.0
        else:
            score -= 4.0

    return clamp_score(score)


def label_for_score(score: float) -> str:
    if score >= 80:
        return "High Absorption"
    if score >= 65:
        return "Stable Rental Profile"
    if score >= 50:
        return "Seasonal / Mixed"
    return "Fragile Rental Profile"
