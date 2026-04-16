"""Fixture loading for model quality tests.

Real fixtures come from ``data/saved_properties/<id>/inputs.json``, parsed
through the existing ``load_property_from_json`` so the harness sees the
same PropertyInput the CLI does.

Synthetic fixtures come from ``data/model_quality/fixtures/*.json`` and are
hand-authored to cover scenarios real data doesn't hit (coastal flood,
teardown, cash-flow-positive, thin-data, etc.).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from briarwood.eval.model_quality.types import Fixture
from briarwood.inputs.property_loader import load_property_from_json
from briarwood.schemas import PropertyInput


ROOT = Path(__file__).resolve().parents[3]
SAVED_PROPERTIES_DIR = ROOT / "data" / "saved_properties"
SYNTHETIC_FIXTURES_DIR = ROOT / "data" / "model_quality" / "fixtures"


def load_real_fixtures(limit: int | None = None) -> list[Fixture]:
    """Load fixtures from every saved_properties/<id>/inputs.json."""

    fixtures: list[Fixture] = []
    if not SAVED_PROPERTIES_DIR.exists():
        return fixtures

    for folder in sorted(SAVED_PROPERTIES_DIR.iterdir()):
        if not folder.is_dir():
            continue
        inputs_path = folder / "inputs.json"
        if not inputs_path.exists():
            continue
        try:
            property_input = load_property_from_json(str(inputs_path))
        except Exception as exc:  # pragma: no cover — diagnostic
            print(f"[fixtures] skip {folder.name}: {exc}")
            continue

        expected = _load_expected(folder / "summary.json")
        fixtures.append(
            Fixture(
                fixture_id=f"real:{folder.name}",
                property_input=property_input,
                kind="real",
                expected=expected,
                notes=f"Loaded from {inputs_path.relative_to(ROOT)}",
            )
        )
        if limit and len(fixtures) >= limit:
            break
    return fixtures


def load_synthetic_fixtures() -> list[Fixture]:
    fixtures: list[Fixture] = []
    if not SYNTHETIC_FIXTURES_DIR.exists():
        return fixtures

    for path in sorted(SYNTHETIC_FIXTURES_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"[fixtures] invalid synthetic fixture {path.name}: {exc}")
            continue
        try:
            property_input = PropertyInput(**payload["inputs"])
        except Exception as exc:
            print(f"[fixtures] synthetic fixture {path.name} failed validation: {exc}")
            continue
        fixtures.append(
            Fixture(
                fixture_id=f"synthetic:{path.stem}",
                property_input=property_input,
                kind="synthetic",
                expected=dict(payload.get("expected") or {}),
                notes=str(payload.get("notes") or ""),
            )
        )
    return fixtures


def load_all_fixtures() -> list[Fixture]:
    return load_real_fixtures() + load_synthetic_fixtures()


def _load_expected(summary_path: Path) -> dict[str, Any]:
    if not summary_path.exists():
        return {}
    try:
        return json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


__all__ = [
    "SAVED_PROPERTIES_DIR",
    "SYNTHETIC_FIXTURES_DIR",
    "load_all_fixtures",
    "load_real_fixtures",
    "load_synthetic_fixtures",
]
