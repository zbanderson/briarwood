from __future__ import annotations


def build_rental_ease_summary(
    *,
    label: str,
    liquidity_score: float,
    demand_depth_score: float,
    rent_support_score: float,
    structural_support_score: float,
    confidence: float,
    drivers: list[str],
    risks: list[str],
) -> str:
    opening = {
        "High Absorption": "Rental absorption appears strong.",
        "Stable Rental Profile": "Rental absorption appears fairly stable.",
        "Seasonal / Mixed": "Rental ease looks mixed rather than fully durable.",
        "Fragile Rental Profile": "Rental absorption looks fragile under current evidence.",
    }[label]

    strongest_pillar = max(
        (
            ("liquidity", liquidity_score),
            ("demand depth", demand_depth_score),
            ("rent support", rent_support_score),
            ("structural support", structural_support_score),
        ),
        key=lambda item: item[1],
    )[0]
    weakest_pillar = min(
        (
            ("liquidity", liquidity_score),
            ("demand depth", demand_depth_score),
            ("rent support", rent_support_score),
            ("structural support", structural_support_score),
        ),
        key=lambda item: item[1],
    )[0]

    detail = f"The strongest pillar is {strongest_pillar}, while {weakest_pillar} remains the main constraint."
    if drivers:
        detail = f"{detail} {drivers[0]}"
    caution = (
        f"{risks[0]} Confidence is {confidence:.2f}."
        if risks
        else f"Confidence is {confidence:.2f}."
    )
    return f"{opening} {detail} {caution}"
