from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from typing import Any, Callable

from briarwood.agent.tools import SAVED_PROPERTIES_DIR, analyze_property

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FEEDBACK_PATH = ROOT / "data" / "learning" / "intelligence_feedback.jsonl"
DEFAULT_GOLD_STANDARD_PATH = ROOT / "data" / "eval" / "gold_standard_dataset.sample.json"


@dataclass(slots=True)
class HistoricalBacktestCase:
    property_id: str
    address: str | None
    ask_price: float | None
    actual_sale_price: float | None
    days_on_market: int | None
    actual_monthly_rent: float | None
    user_mode: str = "investor"


@dataclass(slots=True)
class GoldStandardEntry:
    property_id: str
    investor_grades: list[dict[str, Any]] = field(default_factory=list)


def run_backtest_program(
    *,
    saved_properties_dir: Path = SAVED_PROPERTIES_DIR,
    feedback_path: Path = DEFAULT_FEEDBACK_PATH,
    gold_standard_path: Path = DEFAULT_GOLD_STANDARD_PATH,
    property_ids: list[str] | None = None,
    analyze_fn: Callable[[str], dict[str, Any]] | None = None,
    output_path: Path | None = None,
    markdown_path: Path | None = None,
) -> dict[str, Any]:
    """Run Briarwood's repeatable historical backtest harness."""

    analysis = analyze_fn or analyze_property
    ids = property_ids or _discover_property_ids(saved_properties_dir)
    cases = [_load_case(saved_properties_dir, property_id) for property_id in ids]
    analyses = {
        case.property_id: _safe_analyze(case.property_id, analysis)
        for case in cases
    }
    feedback = _load_feedback_records(feedback_path)
    gold = _load_gold_standard(gold_standard_path)

    report = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cases": len(cases),
            "feedback_records": len(feedback),
            "gold_standard_entries": len(gold),
        },
        "cases": [asdict(case) for case in cases],
        "metrics": {
            "valuation_mae": _valuation_mae(cases, analyses),
            "valuation_mape": _valuation_mape(cases, analyses),
            "recommendation_hit_rate": _recommendation_hit_rate(gold, analyses),
            "false_positive_rate": _false_positive_rate(gold, analyses),
            "false_negative_rate": _false_negative_rate(gold, analyses),
            "confidence_calibration_curve": _confidence_calibration_curve(gold, analyses),
            "verdict_stability_under_sparse_inputs": _stability_metric(
                saved_properties_dir=saved_properties_dir,
                analyses=analyses,
                analyze_fn=analysis,
                property_ids=[case.property_id for case in cases[: min(5, len(cases))]],
            ),
        },
        "dataset_health": {
            "cases_with_actual_sale_price": sum(1 for case in cases if case.actual_sale_price is not None),
            "cases_with_days_on_market": sum(1 for case in cases if case.days_on_market is not None),
            "cases_with_actual_rent": sum(1 for case in cases if case.actual_monthly_rent is not None),
            "cases_with_gold_standard": len(gold),
        },
        "top_gaps": _top_dataset_gaps(cases, gold),
    }

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if markdown_path is not None:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(_to_markdown(report), encoding="utf-8")
    return report


def _discover_property_ids(saved_properties_dir: Path) -> list[str]:
    return sorted(
        path.name
        for path in saved_properties_dir.iterdir()
        if path.is_dir() and (path / "summary.json").exists() and (path / "inputs.json").exists()
    )


def _load_case(saved_properties_dir: Path, property_id: str) -> HistoricalBacktestCase:
    summary = json.loads((saved_properties_dir / property_id / "summary.json").read_text(encoding="utf-8"))
    inputs = json.loads((saved_properties_dir / property_id / "inputs.json").read_text(encoding="utf-8"))
    facts = dict(inputs.get("facts") or {})
    sale_history = list(facts.get("sale_history") or [])
    actual_sale_price = None
    if sale_history:
        last = sale_history[-1]
        if isinstance(last, dict) and isinstance(last.get("sale_price"), (int, float)):
            actual_sale_price = float(last["sale_price"])
    actual_monthly_rent = None
    if isinstance(facts.get("seasonal_monthly_rent"), (int, float)):
        actual_monthly_rent = float(facts["seasonal_monthly_rent"])
    elif isinstance(inputs.get("user_assumptions", {}).get("estimated_monthly_rent"), (int, float)):
        actual_monthly_rent = float(inputs["user_assumptions"]["estimated_monthly_rent"])
    return HistoricalBacktestCase(
        property_id=property_id,
        address=summary.get("address"),
        ask_price=_as_float(summary.get("ask_price")),
        actual_sale_price=actual_sale_price,
        days_on_market=_as_int(facts.get("days_on_market")),
        actual_monthly_rent=actual_monthly_rent,
    )


def _safe_analyze(property_id: str, analyze_fn: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    try:
        return dict(analyze_fn(property_id) or {})
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def _load_feedback_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            records.append(json.loads(text))
        except json.JSONDecodeError:
            continue
    return records


def _load_gold_standard(path: Path) -> list[GoldStandardEntry]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    entries: list[GoldStandardEntry] = []
    for row in list(payload.get("entries") or []):
        if not isinstance(row, dict):
            continue
        entries.append(
            GoldStandardEntry(
                property_id=str(row.get("property_id") or ""),
                investor_grades=list(row.get("investor_grades") or []),
            )
        )
    return entries


def _valuation_mae(cases: list[HistoricalBacktestCase], analyses: dict[str, dict[str, Any]]) -> float | None:
    errors: list[float] = []
    for case in cases:
        if case.actual_sale_price is None:
            continue
        fair = _fair_value(analyses.get(case.property_id) or {})
        if fair is None:
            continue
        errors.append(abs(fair - case.actual_sale_price))
    return round(sum(errors) / len(errors), 2) if errors else None


def _valuation_mape(cases: list[HistoricalBacktestCase], analyses: dict[str, dict[str, Any]]) -> float | None:
    errors: list[float] = []
    for case in cases:
        if case.actual_sale_price is None or case.actual_sale_price == 0:
            continue
        fair = _fair_value(analyses.get(case.property_id) or {})
        if fair is None:
            continue
        errors.append(abs(fair - case.actual_sale_price) / case.actual_sale_price)
    return round(sum(errors) / len(errors), 4) if errors else None


def _recommendation_hit_rate(gold: list[GoldStandardEntry], analyses: dict[str, dict[str, Any]]) -> float | None:
    hits = total = 0
    for entry in gold:
        expected = _consensus_grade(entry.investor_grades)
        predicted = _decision_value(analyses.get(entry.property_id) or {})
        if expected is None or predicted is None:
            continue
        total += 1
        if expected == predicted:
            hits += 1
    return round(hits / total, 4) if total else None


def _false_positive_rate(gold: list[GoldStandardEntry], analyses: dict[str, dict[str, Any]]) -> float | None:
    fp = denom = 0
    for entry in gold:
        expected = _consensus_grade(entry.investor_grades)
        predicted = _decision_value(analyses.get(entry.property_id) or {})
        if expected is None or predicted is None:
            continue
        if expected != "pass":
            continue
        denom += 1
        if predicted in {"buy", "mixed"}:
            fp += 1
    return round(fp / denom, 4) if denom else None


def _false_negative_rate(gold: list[GoldStandardEntry], analyses: dict[str, dict[str, Any]]) -> float | None:
    fn = denom = 0
    for entry in gold:
        expected = _consensus_grade(entry.investor_grades)
        predicted = _decision_value(analyses.get(entry.property_id) or {})
        if expected is None or predicted is None:
            continue
        if expected != "buy":
            continue
        denom += 1
        if predicted == "pass":
            fn += 1
    return round(fn / denom, 4) if denom else None


def _confidence_calibration_curve(
    gold: list[GoldStandardEntry],
    analyses: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    buckets = [
        {"min": 0.0, "max": 0.3, "label": "0.0-0.3", "rows": []},
        {"min": 0.3, "max": 0.55, "label": "0.3-0.55", "rows": []},
        {"min": 0.55, "max": 0.75, "label": "0.55-0.75", "rows": []},
        {"min": 0.75, "max": 1.01, "label": "0.75-1.0", "rows": []},
    ]
    for entry in gold:
        expected = _consensus_grade(entry.investor_grades)
        analysis = analyses.get(entry.property_id) or {}
        predicted = _decision_value(analysis)
        confidence = _as_float(analysis.get("confidence"))
        if expected is None or predicted is None or confidence is None:
            continue
        row = {"correct": expected == predicted}
        for bucket in buckets:
            if bucket["min"] <= confidence < bucket["max"]:
                bucket["rows"].append(row)
                break
    curve: list[dict[str, Any]] = []
    for bucket in buckets:
        rows = list(bucket["rows"])
        hit_rate = None
        if rows:
            hit_rate = round(sum(1 for row in rows if row["correct"]) / len(rows), 4)
        curve.append(
            {
                "bucket": bucket["label"],
                "count": len(rows),
                "observed_hit_rate": hit_rate,
            }
        )
    return curve


def _stability_metric(
    *,
    saved_properties_dir: Path,
    analyses: dict[str, dict[str, Any]],
    analyze_fn: Callable[[str], dict[str, Any]],
    property_ids: list[str],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for property_id in property_ids:
        path = saved_properties_dir / property_id / "inputs.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        sparse = json.loads(json.dumps(payload))
        facts = dict(sparse.get("facts") or {})
        for key in ("taxes", "year_built", "days_on_market", "lot_size"):
            facts[key] = None
        sparse["facts"] = facts
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(sparse, handle)
            temp_path = Path(handle.name)
        try:
            from briarwood.runner_routed import run_routed_report

            sparse_result = run_routed_report(temp_path).unified_output.model_dump()
        except Exception:
            sparse_result = {}
        finally:
            temp_path.unlink(missing_ok=True)
        full = analyses.get(property_id) or {}
        full_conf = _as_float(full.get("confidence"))
        sparse_conf = _as_float(sparse_result.get("confidence"))
        rows.append(
            {
                "property_id": property_id,
                "full_confidence": full_conf,
                "sparse_confidence": sparse_conf,
                "confidence_drop": round(full_conf - sparse_conf, 4)
                if full_conf is not None and sparse_conf is not None
                else None,
            }
        )
    valid_drops = [row["confidence_drop"] for row in rows if isinstance(row.get("confidence_drop"), (int, float))]
    return {
        "count": len(rows),
        "average_confidence_drop": round(sum(valid_drops) / len(valid_drops), 4) if valid_drops else None,
        "rows": rows,
    }


def _top_dataset_gaps(cases: list[HistoricalBacktestCase], gold: list[GoldStandardEntry]) -> list[str]:
    gaps: list[str] = []
    if not any(case.actual_sale_price is not None for case in cases):
        gaps.append("No sale-history outcomes are available yet for valuation error scoring.")
    if not any(case.actual_monthly_rent is not None for case in cases):
        gaps.append("No realized-rent outcomes are available yet for rental backtesting.")
    if not gold:
        gaps.append("Gold-standard investor grades are not populated yet.")
    return gaps


def _to_markdown(report: dict[str, Any]) -> str:
    metrics = dict(report.get("metrics") or {})
    dataset = dict(report.get("dataset_health") or {})
    lines = [
        "# Briarwood Backtest Report",
        "",
        f"- Generated at: `{report.get('metadata', {}).get('generated_at')}`",
        f"- Cases: `{report.get('metadata', {}).get('cases')}`",
        "",
        "## Metrics",
        "",
        f"- Valuation MAE: `{metrics.get('valuation_mae')}`",
        f"- Valuation MAPE: `{metrics.get('valuation_mape')}`",
        f"- Recommendation hit rate: `{metrics.get('recommendation_hit_rate')}`",
        f"- False positive rate: `{metrics.get('false_positive_rate')}`",
        f"- False negative rate: `{metrics.get('false_negative_rate')}`",
        "",
        "## Dataset Health",
        "",
        f"- Cases with actual sale price: `{dataset.get('cases_with_actual_sale_price')}`",
        f"- Cases with days on market: `{dataset.get('cases_with_days_on_market')}`",
        f"- Cases with actual rent: `{dataset.get('cases_with_actual_rent')}`",
        f"- Cases with gold standard: `{dataset.get('cases_with_gold_standard')}`",
        "",
        "## Top Gaps",
        "",
    ]
    for gap in list(report.get("top_gaps") or []):
        lines.append(f"- {gap}")
    return "\n".join(lines) + "\n"


def _fair_value(analysis: dict[str, Any]) -> float | None:
    value_position = dict(analysis.get("value_position") or {})
    return _as_float(value_position.get("fair_value_base"))


def _decision_value(analysis: dict[str, Any]) -> str | None:
    decision = analysis.get("decision")
    if hasattr(decision, "value"):
        return str(decision.value)
    if isinstance(decision, str):
        return decision
    return None


def _consensus_grade(grades: list[dict[str, Any]]) -> str | None:
    counts: dict[str, int] = {}
    for grade in grades:
        if not isinstance(grade, dict):
            continue
        value = str(grade.get("grade") or "").strip().lower()
        if value not in {"buy", "mixed", "pass"}:
            continue
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda item: item[1])[0]


def _as_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


__all__ = ["run_backtest_program"]
