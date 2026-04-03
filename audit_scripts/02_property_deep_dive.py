"""Single property deep dive: complete scoring, module confidence, data completeness."""
from __future__ import annotations
import sys
sys.path.insert(0, ".")

from briarwood.dash_app.data import load_report_for_preset, _REPORT_CACHE
from briarwood.dash_app.view_models import build_property_analysis_view
from briarwood.decision_model.scoring import calculate_final_score, extract_scoring_metrics
from briarwood.decision_model.scoring_config import CATEGORY_WEIGHTS


def main(pid: str = "briarwood-rd-belmar") -> None:
    _REPORT_CACHE.clear()
    report = load_report_for_preset(pid)
    view = build_property_analysis_view(report)
    fs = calculate_final_score(report)
    metrics = extract_scoring_metrics(report)
    pi = report.property_input

    print("=" * 80)
    print(f"DEEP DIVE: {view.address}")
    print(f"Score: {fs.score:.2f}/5 — {fs.tier}")
    print(f"Action: {fs.action}")
    print("=" * 80)

    # ── Scoring breakdown ──
    print("\nCATEGORY + SUB-FACTOR SCORES:")
    print("-" * 80)
    total_effective_weight = 0.0
    for cat_key, cat in fs.category_scores.items():
        print(f"\n  {cat.category_name.upper()}: {cat.score:.2f}/5  ({cat.weight:.0%} weight)  contrib={cat.contribution:.3f}")
        for sf in cat.sub_factors:
            eff_weight = cat.weight * sf.weight * 100
            total_effective_weight += eff_weight
            dots = "●" * int(round(sf.score)) + "○" * (5 - int(round(sf.score)))
            print(f"    {sf.name:25s} {dots} {sf.score:.1f}/5  ({sf.weight:.0%} = {eff_weight:.1f}% final)  {sf.evidence[:70]}")
    print(f"\n  Total effective weight: {total_effective_weight:.1f}% (should be ~100%)")

    # ── Module confidence ──
    print("\n" + "=" * 80)
    print("MODULE CONFIDENCE:")
    print("-" * 80)
    mods = sorted(report.module_results.items(), key=lambda x: x[1].confidence, reverse=True)
    for name, result in mods:
        conf = result.confidence
        bar = "█" * int(conf * 20) + "░" * (20 - int(conf * 20))
        score_str = f"score={result.score:.0f}" if result.score else ""
        metric_count = len(result.metrics)
        print(f"  {name:30s} {conf:.2f} {bar}  {score_str:12s} ({metric_count} metrics)")

    # ── Defaults applied ──
    print("\n" + "=" * 80)
    print(f"DEFAULTS APPLIED ({len(view.defaults_applied)} fields):")
    print("-" * 80)
    for field, desc in view.defaults_applied.items():
        print(f"  {field:25s}: {desc}")
    print(f"  Geocoded: {view.geocoded}")

    # ── Data completeness ──
    print("\n" + "=" * 80)
    print("DATA COMPLETENESS:")
    print("-" * 80)
    if pi:
        groups = {
            "Required": [("address", pi.address), ("purchase_price", pi.purchase_price), ("beds", pi.beds), ("baths", pi.baths), ("sqft", pi.sqft)],
            "Pricing": [("taxes", pi.taxes), ("insurance", getattr(pi, "insurance", None))],
            "Financing": [("down_payment_percent", pi.down_payment_percent), ("interest_rate", pi.interest_rate), ("loan_term_years", pi.loan_term_years)],
            "Market": [("days_on_market", pi.days_on_market), ("flood_risk", pi.flood_risk), ("vacancy_rate", pi.vacancy_rate)],
            "Geographic": [("latitude", pi.latitude), ("longitude", pi.longitude), ("county", pi.county)],
            "Physical": [("lot_size", pi.lot_size), ("year_built", pi.year_built), ("condition_profile", pi.condition_profile), ("capex_lane", pi.capex_lane)],
            "Features": [("has_back_house", pi.has_back_house), ("has_basement", pi.has_basement), ("has_pool", pi.has_pool), ("garage_spaces", pi.garage_spaces)],
        }
        for group, fields in groups.items():
            present = sum(1 for _, v in fields if v is not None and v != 0 and v != "")
            total = len(fields)
            pct = present / total * 100
            bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
            missing = [name for name, v in fields if v is None or v == 0 or v == ""]
            miss_str = f"  missing: {', '.join(missing)}" if missing else ""
            print(f"  {group:12s}: {present}/{total} ({pct:3.0f}%) {bar}{miss_str}")

    # ── Scoring metrics available vs missing ──
    print("\n" + "=" * 80)
    print("SCORING METRICS (available vs None):")
    print("-" * 80)
    key_metrics = [
        "mispricing_pct", "bcv", "purchase_price", "sqft", "income_support_ratio",
        "price_to_rent", "monthly_cash_flow", "downside_burden", "days_on_market",
        "scarcity_support_score", "town_county_score", "risk_score", "zhvi_1yr_change",
        "regulatory_trend_score", "rental_ease_score", "liquidity_score",
        "reno_enabled", "teardown_enabled", "has_back_house", "condition_profile",
    ]
    available = 0
    for k in key_metrics:
        val = metrics.get(k)
        status = "✓" if val is not None and val != 0 and val is not False else "✗"
        if status == "✓":
            available += 1
        val_str = f"{val}" if val is not None else "None"
        if len(val_str) > 50:
            val_str = val_str[:50] + "…"
        print(f"  {status} {k:30s}: {val_str}")
    print(f"\n  Available: {available}/{len(key_metrics)} ({available / len(key_metrics) * 100:.0f}%)")


if __name__ == "__main__":
    import sys as _sys
    pid = _sys.argv[1] if len(_sys.argv) > 1 else "briarwood-rd-belmar"
    main(pid)
