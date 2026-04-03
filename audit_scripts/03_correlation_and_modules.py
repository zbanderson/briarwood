"""Correlation analysis + module performance in one pass (no pandas dependency)."""
from __future__ import annotations
import sys
sys.path.insert(0, ".")

from briarwood.dash_app.data import list_presets, load_report_for_preset, _REPORT_CACHE
from briarwood.decision_model.scoring import calculate_final_score


def main() -> None:
    _REPORT_CACHE.clear()
    presets = list_presets()

    # Collect sub-factor scores and module confidences across all properties
    sf_data: dict[str, list[float]] = {}  # sub-factor name → list of scores
    mod_confs: dict[str, list[float]] = {}  # module name → list of confidences
    mod_scores: dict[str, list[float]] = {}
    success_count = 0

    for preset in presets:
        try:
            report = load_report_for_preset(preset.preset_id)
            fs = calculate_final_score(report)

            for cat in fs.category_scores.values():
                for sf in cat.sub_factors:
                    sf_data.setdefault(sf.name, []).append(sf.score)

            for name, result in report.module_results.items():
                mod_confs.setdefault(name, []).append(result.confidence)
                mod_scores.setdefault(name, []).append(result.score)

            success_count += 1
        except Exception as e:
            print(f"  skip {preset.preset_id}: {e}")

    print(f"Analyzed {success_count}/{len(presets)} properties\n")

    # ── Correlation analysis ──
    print("=" * 80)
    print("SUB-FACTOR CORRELATION ANALYSIS")
    print("=" * 80)

    sf_names = sorted(sf_data.keys())
    n = len(sf_names)

    def pearson(xs: list[float], ys: list[float]) -> float | None:
        if len(xs) != len(ys) or len(xs) < 2:
            return None
        n = len(xs)
        mx = sum(xs) / n
        my = sum(ys) / n
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        sx = sum((x - mx) ** 2 for x in xs) ** 0.5
        sy = sum((y - my) ** 2 for y in ys) ** 0.5
        if sx == 0 or sy == 0:
            return None
        return cov / (sx * sy)

    print(f"\nAll sub-factor pairs with |r| > 0.70:")
    print("-" * 80)
    high_corr = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = sf_names[i], sf_names[j]
            r = pearson(sf_data[a], sf_data[b])
            if r is not None and abs(r) > 0.70:
                high_corr.append((a, b, r))
                print(f"  {a:25s} <-> {b:25s}  r = {r:+.3f}")
    if not high_corr:
        print("  (none found — all sub-factors appear distinct)")

    # Specific audit hypotheses
    print(f"\nAudit hypothesis tests:")
    pairs = [
        ("price_vs_comps", "ppsf_positioning"),
        ("price_vs_comps", "downside_protection"),
        ("ppsf_positioning", "downside_protection"),
        ("rent_support", "carry_efficiency"),
    ]
    for a, b in pairs:
        if a in sf_data and b in sf_data:
            r = pearson(sf_data[a], sf_data[b])
            label = "⚠️ REDUNDANT" if r is not None and abs(r) > 0.85 else "⚠  CORRELATED" if r is not None and abs(r) > 0.70 else "✓ DISTINCT"
            r_str = f"r={r:+.3f}" if r is not None else "r=N/A"
            print(f"  {a:25s} <-> {b:25s}: {r_str}  {label}")

    # Sub-factor variance (low variance = not discriminating)
    print(f"\nSub-factor variance (low = not discriminating):")
    print("-" * 80)
    for name in sf_names:
        vals = sf_data[name]
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        std = var ** 0.5
        bar = "█" * int(std * 5) + "░" * max(0, 5 - int(std * 5))
        flag = " ⚠ LOW VARIANCE" if std < 0.3 else ""
        print(f"  {name:25s}: mean={mean:.2f}  std={std:.2f}  {bar}{flag}")

    # ── Module performance ──
    print("\n" + "=" * 80)
    print("MODULE PERFORMANCE")
    print("=" * 80)

    mod_names = sorted(mod_confs.keys())
    print(f"\n{'Module':30s} {'Avg Conf':>9s} {'Min':>6s} {'Max':>6s} {'Avg Score':>10s} Health")
    print("-" * 85)

    health_groups: dict[str, list[str]] = {"HIGH": [], "MEDIUM": [], "LOW": [], "BROKEN": []}

    for name in mod_names:
        confs = mod_confs[name]
        scores = mod_scores.get(name, [])
        avg_c = sum(confs) / len(confs)
        min_c = min(confs)
        max_c = max(confs)
        avg_s = sum(scores) / len(scores) if scores else 0.0
        bar = "█" * int(avg_c * 10) + "░" * (10 - int(avg_c * 10))

        if avg_c >= 0.8:
            health = "HIGH"
        elif avg_c >= 0.5:
            health = "MEDIUM"
        elif avg_c >= 0.2:
            health = "LOW"
        else:
            health = "BROKEN"
        health_groups[health].append(name)

        print(f"  {name:28s} {avg_c:8.2f}  {min_c:5.2f}  {max_c:5.2f}  {avg_s:9.1f}  {bar}  {health}")

    print(f"\n  ✓ HIGH   ({len(health_groups['HIGH'])}): {', '.join(health_groups['HIGH']) or '(none)'}")
    print(f"  ⚠ MEDIUM ({len(health_groups['MEDIUM'])}): {', '.join(health_groups['MEDIUM']) or '(none)'}")
    print(f"  ⚠ LOW    ({len(health_groups['LOW'])}): {', '.join(health_groups['LOW']) or '(none)'}")
    print(f"  ✗ BROKEN ({len(health_groups['BROKEN'])}): {', '.join(health_groups['BROKEN']) or '(none)'}")


if __name__ == "__main__":
    main()
