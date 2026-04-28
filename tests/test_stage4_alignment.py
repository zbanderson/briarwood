from __future__ import annotations

import json
from pathlib import Path

from api.store import ConversationStore
from briarwood.eval.alignment import compute_alignment_score
from briarwood.eval.model_alignment_backfill import backfill_model_alignment
from briarwood.feedback.model_alignment_analyzer import analyze_rows
from briarwood.modules.comparable_sales_scoped import receive_feedback as receive_comp_feedback
from briarwood.modules.current_value_scoped import receive_feedback as receive_current_value_feedback
from briarwood.modules.valuation import receive_feedback as receive_valuation_feedback


def _store(tmp_path: Path) -> ConversationStore:
    return ConversationStore(tmp_path / "conversations.db")


def _outcome() -> dict[str, object]:
    return {
        "property_id": "NJ-1",
        "outcome_type": "sale_price",
        "outcome_value": 1_000_000,
        "outcome_date": "2026-04-01",
    }


def _write_outcome_file(tmp_path: Path, *, property_id: str | None = "NJ-1") -> Path:
    path = tmp_path / "outcomes.jsonl"
    row = {
        "address": "1 Main St, Belmar, NJ",
        "outcome_type": "sale_price",
        "outcome_value": 1_000_000,
        "outcome_date": "2026-04-01",
    }
    if property_id is not None:
        row["property_id"] = property_id
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return path


def _write_saved_property(tmp_path: Path, *, property_id: str = "NJ-1") -> Path:
    root = tmp_path / "saved_properties"
    property_dir = root / property_id
    property_dir.mkdir(parents=True)
    (property_dir / "inputs.json").write_text(
        json.dumps(
            {
                "property_id": property_id,
                "facts": {"address": "1 Main St, Belmar, NJ"},
            }
        ),
        encoding="utf-8",
    )
    (property_dir / "summary.json").write_text(
        json.dumps({"property_id": property_id, "address": "1 Main St, Belmar, NJ"}),
        encoding="utf-8",
    )
    return root


def _valuation_runner(_context: object) -> dict[str, object]:
    return {
        "confidence": 0.81,
        "data": {
            "legacy_payload": {
                "briarwood_current_value": 900_000,
                "pricing_view": "discounted",
            }
        },
    }


def test_compute_alignment_score_flags_high_confidence_miss() -> None:
    score = compute_alignment_score(
        predicted_value=880_000,
        confidence=0.82,
        outcome_value=1_000_000,
    )

    assert score.absolute_pct_error == 0.12
    assert score.high_confidence is True
    assert score.underperformed is True


def test_store_model_alignment_round_trip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    inserted = store.insert_model_alignment(
        {
            "module_name": "valuation",
            "property_id": "NJ-1",
            "predicted_value": 900_000,
            "confidence": 0.8,
            "outcome_type": "sale_price",
            "outcome_value": 1_000_000,
            "outcome_date": "2026-04-01",
            "absolute_error": 100_000,
            "absolute_pct_error": 0.1,
            "alignment_score": 0.5,
            "high_confidence": True,
            "underperformed": True,
            "evidence": {"source": "test"},
        }
    )

    rows = store.model_alignment_rows()

    assert rows[0]["id"] == inserted["id"]
    assert rows[0]["underperformed"] is True
    assert rows[0]["evidence"]["source"] == "test"


def test_current_value_receive_feedback_records_alignment(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = receive_current_value_feedback(
        "session-1",
        {
            "store": store,
            "turn_trace_id": "turn-1",
            "property_id": "NJ-1",
            "outcome": _outcome(),
            "module_payload": {
                "confidence": 0.8,
                "data": {
                    "legacy_payload": {
                        "briarwood_current_value": 900_000,
                        "pricing_view": "appears overpriced",
                    }
                },
            },
        },
    )

    rows = store.model_alignment_rows(module_name="current_value")

    assert result["status"] == "recorded"
    assert rows[0]["turn_trace_id"] == "turn-1"
    assert rows[0]["predicted_label"] == "appears overpriced"
    assert rows[0]["underperformed"] is True


def test_valuation_receive_feedback_skips_missing_prediction(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = receive_valuation_feedback(
        "session-1",
        {
            "store": store,
            "outcome": _outcome(),
            "module_payload": {"confidence": 0.8, "data": {"legacy_payload": {}}},
        },
    )

    assert result["status"] == "skipped"
    assert store.model_alignment_rows() == []


def test_comparable_sales_receive_feedback_records_metric_value(tmp_path: Path) -> None:
    store = _store(tmp_path)
    result = receive_comp_feedback(
        "session-1",
        {
            "store": store,
            "outcome": _outcome(),
            "module_payload": {
                "confidence": 0.78,
                "data": {
                    "metrics": {
                        "comparable_value": 940_000,
                        "comp_confidence_score": 0.81,
                    }
                },
            },
        },
    )

    rows = store.model_alignment_rows(module_name="comparable_sales")

    assert result["status"] == "recorded"
    assert rows[0]["predicted_value"] == 940_000
    assert rows[0]["underperformed"] is False


def test_model_alignment_backfill_dry_run_uses_saved_property_match(tmp_path: Path) -> None:
    saved_properties = _write_saved_property(tmp_path)
    outcomes = _write_outcome_file(tmp_path)

    result = backfill_model_alignment(
        outcomes_path=outcomes,
        saved_properties_dir=saved_properties,
        modules=["valuation"],
        dry_run=True,
        runners={"valuation": _valuation_runner},
    )

    assert result.error is None
    assert result.recorded == 1
    assert result.properties_matched == 1
    assert result.rows[0]["module_name"] == "valuation"
    assert result.rows[0]["underperformed"] is True


def test_model_alignment_backfill_records_and_skips_duplicates(tmp_path: Path) -> None:
    saved_properties = _write_saved_property(tmp_path)
    outcomes = _write_outcome_file(tmp_path)
    store = _store(tmp_path)

    first = backfill_model_alignment(
        outcomes_path=outcomes,
        saved_properties_dir=saved_properties,
        modules=["valuation"],
        store=store,
        runners={"valuation": _valuation_runner},
    )
    second = backfill_model_alignment(
        outcomes_path=outcomes,
        saved_properties_dir=saved_properties,
        modules=["valuation"],
        store=store,
        runners={"valuation": _valuation_runner},
    )

    rows = store.model_alignment_rows(module_name="valuation")
    assert first.recorded == 1
    assert second.recorded == 0
    assert second.skipped[0].reason == "duplicate_alignment_row"
    assert len(rows) == 1
    assert rows[0]["property_id"] == "NJ-1"


def test_model_alignment_backfill_matches_outcome_by_address(tmp_path: Path) -> None:
    saved_properties = _write_saved_property(tmp_path)
    outcomes = _write_outcome_file(tmp_path, property_id=None)

    result = backfill_model_alignment(
        outcomes_path=outcomes,
        saved_properties_dir=saved_properties,
        modules=["valuation"],
        dry_run=True,
        runners={"valuation": _valuation_runner},
    )

    assert result.recorded == 1
    assert result.rows[0]["evidence"]["match_method"] == "address"


def test_model_alignment_analyzer_surfaces_candidates(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.insert_model_alignment(
        {
            "module_name": "valuation",
            "turn_trace_id": "turn-1",
            "property_id": "NJ-1",
            "predicted_value": 850_000,
            "confidence": 0.9,
            "outcome_type": "sale_price",
            "outcome_value": 1_000_000,
            "outcome_date": "2026-04-01",
            "absolute_error": 150_000,
            "absolute_pct_error": 0.15,
            "alignment_score": 0.25,
            "high_confidence": True,
            "underperformed": True,
            "evidence": {"source": "test"},
        }
    )
    store.insert_model_alignment(
        {
            "module_name": "valuation",
            "property_id": "NJ-2",
            "predicted_value": 990_000,
            "confidence": 0.7,
            "outcome_type": "sale_price",
            "outcome_value": 1_000_000,
            "outcome_date": "2026-04-01",
            "absolute_error": 10_000,
            "absolute_pct_error": 0.01,
            "alignment_score": 0.95,
            "high_confidence": False,
            "underperformed": False,
            "evidence": json.dumps({"source": "test"}),
        }
    )

    report = analyze_rows(store.model_alignment_rows())

    assert report.rows_scored == 2
    assert report.modules[0].module_name == "valuation"
    assert report.modules[0].underperformed_rows == 1
    assert report.tuning_candidates[0]["turn_trace_id"] == "turn-1"
