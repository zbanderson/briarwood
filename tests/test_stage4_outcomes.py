from __future__ import annotations

import json
from pathlib import Path

from briarwood.eval.outcomes import build_outcome_index, load_outcomes
from scripts.backfill_outcomes import backfill_outcomes


def test_load_outcomes_jsonl_validates_rows(tmp_path: Path) -> None:
    path = tmp_path / "outcomes.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "property_id": "NJ-1",
                        "address": "1 Main St, Belmar, NJ",
                        "outcome_type": "sale_price",
                        "outcome_value": "$1,000,000",
                        "outcome_date": "2026-04-01",
                    }
                ),
                json.dumps(
                    {
                        "property_id": "NJ-2",
                        "outcome_type": "sale_price",
                        "outcome_value": -1,
                        "outcome_date": "2026-04-01",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = load_outcomes(path)

    assert result.valid_count == 1
    assert result.error_count == 1
    assert result.records[0].source == "manual_json"
    assert result.records[0].outcome_value == 1_000_000


def test_load_outcomes_csv_reports_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "outcomes.csv"
    path.write_text(
        "property_id,address,outcome_type,outcome_value,outcome_date\n"
        "NJ-1,,sale_price,1000000,2026-04-01\n"
        "NJ-1,,sale_price,1010000,2026-04-02\n",
        encoding="utf-8",
    )

    result = load_outcomes(path)

    assert result.valid_count == 2
    assert result.duplicate_keys == ["property_id:nj-1"]


def test_outcome_index_matches_property_id_before_address(tmp_path: Path) -> None:
    path = tmp_path / "outcomes.jsonl"
    path.write_text(
        json.dumps(
            {
                "property_id": "NJ-1",
                "address": "1 Main St, Belmar, NJ",
                "outcome_type": "sale_price",
                "outcome_value": 1_000_000,
                "outcome_date": "2026-04-01",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result = load_outcomes(path)
    index = build_outcome_index(result.records)

    match = index.match_mapping({"property_id": "NJ-1", "address": "Wrong Address"})

    assert match is not None
    assert match.method == "property_id"
    assert match.outcome.outcome_value == 1_000_000


def test_backfill_outcomes_dry_run_preserves_file(tmp_path: Path) -> None:
    feedback = tmp_path / "intelligence_feedback.jsonl"
    original = json.dumps(
        {
            "question": "What do you think?",
            "property_id": "NJ-1",
            "outcome": None,
        },
        sort_keys=True,
    )
    feedback.write_text(original + "\n", encoding="utf-8")
    outcomes = tmp_path / "outcomes.jsonl"
    outcomes.write_text(
        json.dumps(
            {
                "property_id": "NJ-1",
                "outcome_type": "sale_price",
                "outcome_value": 1_000_000,
                "outcome_date": "2026-04-01",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = backfill_outcomes(feedback_path=feedback, outcomes_path=outcomes, dry_run=True)

    assert result["updated"] == 1
    assert feedback.read_text(encoding="utf-8") == original + "\n"


def test_backfill_outcomes_rewrites_with_backup(tmp_path: Path) -> None:
    feedback = tmp_path / "intelligence_feedback.jsonl"
    feedback.write_text(
        json.dumps({"property_id": "NJ-1", "outcome": None}) + "\n",
        encoding="utf-8",
    )
    outcomes = tmp_path / "outcomes.jsonl"
    outcomes.write_text(
        json.dumps(
            {
                "property_id": "NJ-1",
                "outcome_type": "sale_price",
                "outcome_value": 1_000_000,
                "outcome_date": "2026-04-01",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = backfill_outcomes(feedback_path=feedback, outcomes_path=outcomes)
    row = json.loads(feedback.read_text(encoding="utf-8").strip())

    assert result["updated"] == 1
    assert Path(result["backup"]).exists()
    assert row["outcome"]["outcome_value"] == 1_000_000
    assert row["outcome_match"]["method"] == "property_id"
