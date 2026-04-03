"""Portfolio-level audit: score distribution, data quality, module health."""
from __future__ import annotations
import sys
sys.path.insert(0, ".")

from briarwood.dash_app.data import list_presets, load_report_for_preset, _REPORT_CACHE
from briarwood.dash_app.view_models import build_property_analysis_view
from briarwood.decision_model.scoring import calculate_final_score, extract_scoring_metrics


def main() -> None:
    _REPORT_CACHE.clear()
    presets = list_presets()
    print(f"Found {len(presets)} presets\n")

    results: list[dict] = []
    errors: list[str] = []

    for preset in presets:
        pid = preset.preset_id
        try:
            report = load_report_for_preset(pid)
            view = build_property_analysis_view(report)
            fs = calculate_final_score(report)
            metrics = extract_scoring_metrics(report)

            row = {
                "id": pid,
                "address": view.address,
                "ask": view.ask_price,
                "bcv": view.bcv,
                "score": fs.score,
                "tier": fs.tier,
                "defaults_count": len(view.defaults_applied),
                "geocoded": view.geocoded,
            }
            for cat_key, cat in fs.category_scores.items():
                row[cat_key] = cat.score

            # Count neutral-defaulted sub-factors
            neutral_count = 0
            for cat in fs.category_scores.values():
                for sf in cat.sub_factors:
                    if sf.score == 3.0 and any(kw in sf.evidence.lower() for kw in ("unavailable", "unknown", "insufficient", "cannot")):
                        neutral_count += 1
            row["neutral_defaults"] = neutral_count

            results.append(row)
            print(f"  OK  {pid}: {fs.score:.2f} ({fs.tier})")
        except Exception as e:
            errors.append(f"{pid}: {e}")
            print(f"  ERR {pid}: {e}")

    scored = [r for r in results if r.get("score") is not None]

    print("\n" + "=" * 80)
    print("PORTFOLIO SUMMARY")
    print("=" * 80)
    print(f"\nTotal presets: {len(presets)}")
    print(f"Successfully scored: {len(scored)}")
    print(f"Errors: {len(errors)}")

    if scored:
        scores = [r["score"] for r in scored]
        print(f"\nScore distribution:")
        print(f"  Mean:   {sum(scores) / len(scores):.2f}")
        print(f"  Min:    {min(scores):.2f}")
        print(f"  Max:    {max(scores):.2f}")

        from collections import Counter
        tier_counts = Counter(r["tier"] for r in scored)
        print(f"\nRecommendation tiers:")
        for tier, count in tier_counts.most_common():
            print(f"  {tier:30s}: {count}")

        cats = ["price_context", "economic_support", "optionality", "market_position", "risk_layer"]
        print(f"\nCategory averages:")
        for cat in cats:
            vals = [r[cat] for r in scored if r.get(cat) is not None]
            if vals:
                avg = sum(vals) / len(vals)
                lo, hi = min(vals), max(vals)
                print(f"  {cat:22s}: avg {avg:.2f}  range [{lo:.1f} – {hi:.1f}]")

        print(f"\nData quality:")
        geo_count = sum(1 for r in scored if r.get("geocoded"))
        avg_defaults = sum(r.get("defaults_count", 0) for r in scored) / len(scored)
        avg_neutrals = sum(r.get("neutral_defaults", 0) for r in scored) / len(scored)
        print(f"  Geocoded:              {geo_count}/{len(scored)}")
        print(f"  Avg defaults applied:  {avg_defaults:.1f} fields")
        print(f"  Avg neutral sub-factors: {avg_neutrals:.1f}/20")

    if errors:
        print(f"\nErrors:")
        for e in errors:
            print(f"  {e}")


if __name__ == "__main__":
    main()
