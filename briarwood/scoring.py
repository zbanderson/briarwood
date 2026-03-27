from __future__ import annotations

def clamp_score(value: float, floor: float = 0.0, ceiling: float = 100.0) -> float:
    return float(max(floor, min(ceiling, value)))
