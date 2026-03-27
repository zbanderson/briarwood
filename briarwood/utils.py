from __future__ import annotations

from datetime import datetime


def current_year() -> int:
    return datetime.now().year


def safe_divide(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator
