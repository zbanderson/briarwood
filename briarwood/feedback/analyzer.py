"""Feedback loop analyzer: reads intelligence_feedback.jsonl and produces
actionable diagnostics for routing quality, confidence calibration, and
module coverage.

Usage (CLI):
    python -m briarwood.feedback.analyzer          # print summary
    python -m briarwood.feedback.analyzer --json    # save JSON report
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from briarwood.intelligence_capture import CAPTURE_PATH


@dataclass(slots=True)
class FeedbackReport:
    """Aggregated diagnostics from the intelligence feedback log."""

    total_records: int = 0

    # Execution mode breakdown (historic records may tag other modes; new
    # records are all "scoped" since the legacy fallback has been removed).
    execution_mode_counts: dict[str, int] = field(default_factory=dict)

    # Module frequency
    module_frequency: dict[str, int] = field(default_factory=dict)
    module_selection_rate: dict[str, float] = field(default_factory=dict)

    # Confidence distribution
    confidence_buckets: dict[str, int] = field(default_factory=dict)
    low_confidence_drivers: list[dict[str, Any]] = field(default_factory=list)
    mean_confidence: float = 0.0

    # Question pattern analysis
    top_question_patterns: list[dict[str, Any]] = field(default_factory=list)
    intent_distribution: dict[str, int] = field(default_factory=dict)
    depth_distribution: dict[str, int] = field(default_factory=dict)

    # Tag analysis
    tag_counts: dict[str, int] = field(default_factory=dict)
    unknown_pattern_questions: list[str] = field(default_factory=list)

    # Missing inputs
    missing_input_frequency: dict[str, int] = field(default_factory=dict)

    # Follow-up chain analysis
    followup_count: int = 0
    trigger_counts: dict[str, int] = field(default_factory=dict)
    depth_promotion_count: int = 0
    intent_pivot_count: int = 0

    # User feedback (8C/8D)
    user_feedback_count: int = 0
    user_feedback_distribution: dict[str, int] = field(default_factory=dict)
    confidence_vs_feedback: list[dict[str, Any]] = field(default_factory=list)
    confidence_threshold_recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "execution_mode_counts": self.execution_mode_counts,
            "module_frequency": dict(sorted(self.module_frequency.items(), key=lambda x: x[1], reverse=True)),
            "module_selection_rate": {k: round(v, 3) for k, v in sorted(self.module_selection_rate.items(), key=lambda x: x[1], reverse=True)},
            "confidence_buckets": self.confidence_buckets,
            "mean_confidence": round(self.mean_confidence, 3),
            "low_confidence_drivers": self.low_confidence_drivers[:10],
            "top_question_patterns": self.top_question_patterns[:15],
            "intent_distribution": dict(sorted(self.intent_distribution.items(), key=lambda x: x[1], reverse=True)),
            "depth_distribution": dict(sorted(self.depth_distribution.items(), key=lambda x: x[1], reverse=True)),
            "tag_counts": dict(sorted(self.tag_counts.items(), key=lambda x: x[1], reverse=True)),
            "unknown_pattern_questions": self.unknown_pattern_questions[:20],
            "missing_input_frequency": dict(sorted(self.missing_input_frequency.items(), key=lambda x: x[1], reverse=True)),
            "followup_count": self.followup_count,
            "trigger_counts": self.trigger_counts,
            "depth_promotion_count": self.depth_promotion_count,
            "intent_pivot_count": self.intent_pivot_count,
            "user_feedback_count": self.user_feedback_count,
            "user_feedback_distribution": self.user_feedback_distribution,
            "confidence_vs_feedback": self.confidence_vs_feedback[:20],
            "confidence_threshold_recommendation": self.confidence_threshold_recommendation,
        }


def load_records(path: Path | None = None) -> list[dict[str, Any]]:
    """Load all records from the JSONL feedback file."""
    target = path or CAPTURE_PATH
    if not target.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def analyze(records: list[dict[str, Any]] | None = None) -> FeedbackReport:
    """Analyze feedback records and produce a diagnostic report."""
    if records is None:
        records = load_records()
    report = FeedbackReport(total_records=len(records))
    if not records:
        return report

    # Separate analysis records from user feedback records
    analysis_records = [r for r in records if r.get("feedback_type") != "user_validation"]
    feedback_records = [r for r in records if r.get("feedback_type") == "user_validation"]

    _analyze_execution_modes(analysis_records, report)
    _analyze_modules(analysis_records, report)
    _analyze_confidence(analysis_records, report)
    _analyze_questions(analysis_records, report)
    _analyze_tags(analysis_records, report)
    _analyze_missing_inputs(analysis_records, report)
    _analyze_followups(analysis_records, report)
    _analyze_user_feedback(feedback_records, analysis_records, report)

    return report


def _analyze_execution_modes(records: list[dict], report: FeedbackReport) -> None:
    modes = Counter(str(r.get("execution_mode") or "unknown") for r in records)
    report.execution_mode_counts = dict(modes)


def _analyze_modules(records: list[dict], report: FeedbackReport) -> None:
    freq: Counter[str] = Counter()
    n_property = 0
    for r in records:
        modules = r.get("selected_modules") or []
        if not modules:
            continue
        n_property += 1
        for m in modules:
            freq[str(m)] += 1
    report.module_frequency = dict(freq)
    if n_property > 0:
        report.module_selection_rate = {m: count / n_property for m, count in freq.items()}


def _analyze_confidence(records: list[dict], report: FeedbackReport) -> None:
    confidences: list[float] = []
    low_drivers: Counter[str] = Counter()

    for r in records:
        summary = r.get("unified_output_summary") or {}
        conf = summary.get("confidence")
        if not isinstance(conf, (int, float)):
            continue
        confidences.append(float(conf))

        if conf < 0.55:
            for inp in (r.get("parser_output") or {}).get("missing_inputs") or []:
                low_drivers[str(inp)] += 1

    if confidences:
        report.mean_confidence = sum(confidences) / len(confidences)

    buckets = {"0.0-0.4": 0, "0.4-0.55": 0, "0.55-0.7": 0, "0.7-0.85": 0, "0.85-1.0": 0}
    for c in confidences:
        if c < 0.4:
            buckets["0.0-0.4"] += 1
        elif c < 0.55:
            buckets["0.4-0.55"] += 1
        elif c < 0.7:
            buckets["0.55-0.7"] += 1
        elif c < 0.85:
            buckets["0.7-0.85"] += 1
        else:
            buckets["0.85-1.0"] += 1
    report.confidence_buckets = buckets

    report.low_confidence_drivers = [
        {"driver": driver, "count": count}
        for driver, count in low_drivers.most_common(10)
    ]


def _analyze_questions(records: list[dict], report: FeedbackReport) -> None:
    # Normalize questions to identify patterns
    pattern_counter: Counter[str] = Counter()
    intent_counter: Counter[str] = Counter()
    depth_counter: Counter[str] = Counter()
    question_to_routing: dict[str, dict] = {}

    for r in records:
        question = str(r.get("question") or "").strip().lower()
        if not question:
            continue
        # Normalize: strip property-specific details, keep the intent shape
        normalized = _normalize_question_pattern(question)
        pattern_counter[normalized] += 1
        if normalized not in question_to_routing:
            parser = r.get("parser_output") or {}
            question_to_routing[normalized] = {
                "example": str(r.get("question") or ""),
                "intent_type": str(parser.get("intent_type") or ""),
                "analysis_depth": str(parser.get("analysis_depth") or ""),
                "confidence": float(parser.get("confidence") or 0.0),
            }

        parser = r.get("parser_output") or {}
        intent = str(parser.get("intent_type") or "unknown")
        depth = str(parser.get("analysis_depth") or "unknown")
        intent_counter[intent] += 1
        depth_counter[depth] += 1

    report.top_question_patterns = [
        {"pattern": pattern, "count": count, **question_to_routing.get(pattern, {})}
        for pattern, count in pattern_counter.most_common(15)
    ]
    report.intent_distribution = dict(intent_counter)
    report.depth_distribution = dict(depth_counter)


def _normalize_question_pattern(question: str) -> str:
    """Reduce a question to its intent shape by stripping specifics."""
    import re
    # Remove dollar amounts, addresses, numbers
    q = re.sub(r"\$[\d,]+", "$X", question)
    q = re.sub(r"\d+\s*(bed|bath|sqft|sf|acre|year|month)", "N \\1", q)
    q = re.sub(r"\d{3,}", "X", q)
    # Collapse whitespace
    q = re.sub(r"\s+", " ", q).strip()
    # Truncate long questions
    if len(q) > 80:
        q = q[:77] + "..."
    return q


def _analyze_tags(records: list[dict], report: FeedbackReport) -> None:
    tag_counter: Counter[str] = Counter()
    unknown_questions: list[str] = []

    for r in records:
        for tag in r.get("tags") or []:
            tag_counter[str(tag)] += 1
        if "unknown-question-pattern" in (r.get("tags") or []):
            unknown_questions.append(str(r.get("question") or ""))

    report.tag_counts = dict(tag_counter)
    report.unknown_pattern_questions = unknown_questions


def _analyze_missing_inputs(records: list[dict], report: FeedbackReport) -> None:
    freq: Counter[str] = Counter()
    for r in records:
        for inp in (r.get("parser_output") or {}).get("missing_inputs") or []:
            freq[str(inp)] += 1
    report.missing_input_frequency = dict(freq)


def _analyze_followups(records: list[dict], report: FeedbackReport) -> None:
    followups = [r for r in records if r.get("trigger")]
    report.followup_count = len(followups)
    report.trigger_counts = dict(Counter(str(r.get("trigger") or "") for r in followups))
    report.depth_promotion_count = sum(
        1 for r in followups if "user-went-deeper" in (r.get("tags") or [])
    )
    report.intent_pivot_count = sum(
        1 for r in followups if "user-pivoted-intent" in (r.get("tags") or [])
    )


def _analyze_user_feedback(
    feedback_records: list[dict],
    analysis_records: list[dict],
    report: FeedbackReport,
) -> None:
    """Correlate user feedback with analysis confidence for threshold tuning."""
    report.user_feedback_count = len(feedback_records)
    if not feedback_records:
        return

    dist: Counter[str] = Counter()
    pairs: list[dict[str, Any]] = []
    for fb in feedback_records:
        rating = str(fb.get("rating") or "unknown")
        dist[rating] += 1
        conf = fb.get("analysis_confidence")
        if isinstance(conf, (int, float)):
            pairs.append({
                "rating": rating,
                "confidence": round(float(conf), 3),
                "analysis_id": fb.get("analysis_id"),
            })

    report.user_feedback_distribution = dict(dist)
    report.confidence_vs_feedback = sorted(pairs, key=lambda x: x["confidence"])

    # 8D: Confidence threshold tuning
    if len(pairs) >= 5:
        report.confidence_threshold_recommendation = _compute_threshold_recommendation(pairs)


def _compute_threshold_recommendation(pairs: list[dict[str, Any]]) -> str:
    """Suggest a confidence threshold adjustment based on user feedback correlation."""
    negative_confs: list[float] = []
    positive_confs: list[float] = []

    for p in pairs:
        rating = p["rating"]
        conf = p["confidence"]
        if rating == "no":
            negative_confs.append(conf)
        elif rating == "yes":
            positive_confs.append(conf)

    if not negative_confs and not positive_confs:
        return ""

    total = len(pairs)

    if negative_confs:
        neg_mean = sum(negative_confs) / len(negative_confs)
        neg_max = max(negative_confs)
    else:
        neg_mean = 0.0
        neg_max = 0.0

    if positive_confs:
        pos_mean = sum(positive_confs) / len(positive_confs)
    else:
        pos_mean = 1.0

    # If negative feedback clusters below a threshold, recommend raising it
    if len(negative_confs) >= 3 and neg_mean < 0.6:
        suggested = round(min(neg_max + 0.05, 0.90), 2)
        return (
            f"Based on {total} analyses with user feedback, {len(negative_confs)} negative ratings "
            f"cluster at mean confidence {neg_mean:.2f}. Consider raising the minimum confidence "
            f"for BUY recommendations to {suggested:.2f} (from current default)."
        )

    if positive_confs and negative_confs:
        gap = pos_mean - neg_mean
        if gap > 0.15:
            return (
                f"Positive feedback averages {pos_mean:.2f} confidence vs {neg_mean:.2f} for negative. "
                f"The {gap:.2f} gap suggests confidence is a meaningful quality signal."
            )

    return ""


def format_report(report: FeedbackReport) -> str:
    """Format a FeedbackReport as a human-readable console summary."""
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("  BRIARWOOD INTELLIGENCE FEEDBACK REPORT")
    lines.append("=" * 64)
    lines.append(f"\nTotal logged interactions: {report.total_records}")

    lines.append(f"\n── Execution Modes {'─' * 44}")
    for mode, count in sorted(report.execution_mode_counts.items(), key=lambda x: -x[1]):
        pct = count / max(report.total_records, 1) * 100
        lines.append(f"  {mode:25s} {count:>4d}  ({pct:.0f}%)")

    lines.append(f"\n── Module Selection {'─' * 43}")
    for module, count in sorted(report.module_frequency.items(), key=lambda x: -x[1]):
        rate = report.module_selection_rate.get(module, 0)
        lines.append(f"  {module:25s} {count:>4d}  ({rate:.0%} of analyses)")

    lines.append(f"\n── Confidence {'─' * 49}")
    lines.append(f"  Mean: {report.mean_confidence:.2f}")
    for bucket, count in report.confidence_buckets.items():
        bar = "█" * min(count, 30)
        lines.append(f"  {bucket:10s} {count:>4d}  {bar}")
    if report.low_confidence_drivers:
        lines.append("  Top drivers of low confidence:")
        for item in report.low_confidence_drivers[:5]:
            lines.append(f"    - {item['driver']}: {item['count']}x")

    lines.append(f"\n── Intent Distribution {'─' * 40}")
    for intent, count in sorted(report.intent_distribution.items(), key=lambda x: -x[1]):
        lines.append(f"  {intent:35s} {count:>4d}")

    lines.append(f"\n── Depth Distribution {'─' * 41}")
    for depth, count in sorted(report.depth_distribution.items(), key=lambda x: -x[1]):
        lines.append(f"  {depth:20s} {count:>4d}")

    lines.append(f"\n── Missing Inputs {'─' * 44}")
    for inp, count in sorted(report.missing_input_frequency.items(), key=lambda x: -x[1]):
        lines.append(f"  {inp:25s} {count:>4d}")

    lines.append(f"\n── Tags {'─' * 55}")
    for tag, count in sorted(report.tag_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {tag:45s} {count:>4d}")

    if report.unknown_pattern_questions:
        lines.append(f"\n── Unknown Question Patterns ({'─' * 33})")
        for q in report.unknown_pattern_questions[:10]:
            lines.append(f"  ? {q}")

    if report.top_question_patterns:
        lines.append(f"\n── Top Question Patterns ({'─' * 37})")
        for item in report.top_question_patterns[:10]:
            lines.append(f"  [{item.get('count', 0):>3d}x] {item.get('pattern', '')}")
            lines.append(f"         → {item.get('intent_type', '?')} / {item.get('analysis_depth', '?')} (conf {item.get('confidence', 0):.2f})")

    if report.followup_count:
        lines.append(f"\n── Follow-up Chains ({'─' * 42})")
        lines.append(f"  Total follow-ups: {report.followup_count}")
        for trigger, count in report.trigger_counts.items():
            lines.append(f"    {trigger}: {count}")
        lines.append(f"  Depth promotions: {report.depth_promotion_count}")
        lines.append(f"  Intent pivots:    {report.intent_pivot_count}")

    if report.user_feedback_count:
        lines.append(f"\n── User Feedback ({'─' * 45})")
        lines.append(f"  Total responses: {report.user_feedback_count}")
        for rating, count in sorted(report.user_feedback_distribution.items(), key=lambda x: -x[1]):
            lines.append(f"    {rating}: {count}")
        if report.confidence_threshold_recommendation:
            lines.append(f"\n  📊 {report.confidence_threshold_recommendation}")

    lines.append("\n" + "=" * 64)
    return "\n".join(lines)


if __name__ == "__main__":
    recs = load_records()
    result = analyze(recs)
    if "--json" in sys.argv:
        output_path = CAPTURE_PATH.parent / "feedback_report.json"
        output_path.write_text(json.dumps(result.to_dict(), indent=2) + "\n")
        print(f"Report saved to {output_path}")
    else:
        print(format_report(result))
