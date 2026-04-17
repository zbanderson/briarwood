"""Tests for the town development index module.

The module derives a rolling per-town signal from stored minutes and exposes
a bounded nudge for forward-looking consumers. Tests cover:

- signals math + time decay
- composite velocity weighting
- registry wiring as a leaf dependency of ``resale_scenario``
- bounded nudge (clamped at ``max_nudge``)
- scoped runner against a synthetic ``JsonMinutesStore`` root
- graceful degradation when no record / no town exists
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from briarwood.execution.context import ExecutionContext
from briarwood.execution.registry import build_module_registry
from briarwood.local_intelligence.minutes_registry import MinutesFeed
from briarwood.local_intelligence.minutes_schema import MinuteEntry, MinutesRecord
from briarwood.local_intelligence.minutes_store import JsonMinutesStore
from briarwood.modules.town_development_index import (
    DEFAULT_MAX_NUDGE,
    apply_dev_index_nudge,
    compute_town_development_index,
    read_dev_index,
    run_town_development_index,
)


NOW = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)


def _entry(month: str, *, tags: list[str], summary: str = "") -> MinuteEntry:
    return MinuteEntry(
        month=month,
        board="planning_board",
        source_url=f"https://x/{month}.pdf",
        fetched_at=NOW.isoformat(),
        status="fetched",
        summary=summary,
        summary_confidence=0.75,
        tags=tags,
    )


def _record(entries: list[MinuteEntry], *, window: int = 12) -> MinutesRecord:
    return MinutesRecord(
        town="Testville",
        state="NJ",
        board="planning_board",
        url_template="https://x/{year}.php",
        rolling_window_months=window,
        last_checked_at=NOW.isoformat(),
        entries=entries,
    )


class ComputeSignalsTests(unittest.TestCase):
    def test_empty_record_produces_neutral_velocity(self):
        signals = compute_town_development_index(record=_record([]), now=NOW)
        self.assertEqual(signals.observations_used, 0)
        self.assertIsNone(signals.approval_rate)
        # With no data, velocity leans on the 0.5 approval default + zero volume/subs
        # Score = 0.4 * 0.5 + 0.25 * 0 + 0.15 * 0 + 0.10 * 1 + 0.10 * 1 = 0.40
        self.assertAlmostEqual(signals.development_velocity, 0.40, places=2)

    def test_approval_heavy_town_has_high_velocity(self):
        entries = [
            _entry("2026-03", tags=["approv", "variance", "subdivision"], summary=""),
            _entry("2026-02", tags=["approv", "variance", "site plan"], summary=""),
            _entry("2026-01", tags=["approv", "ordinance"], summary=""),
            _entry("2025-12", tags=["approv", "variance"], summary=""),
        ]
        signals = compute_town_development_index(record=_record(entries), now=NOW)
        self.assertIsNotNone(signals.approval_rate)
        self.assertGreaterEqual(signals.approval_rate, 0.95)
        self.assertGreater(signals.development_velocity, 0.55)
        self.assertIn("approval rate", signals.explanation)

    def test_denial_and_moratorium_drag_velocity_down(self):
        entries = [
            _entry("2026-03", tags=["denied", "moratorium"], summary=""),
            _entry("2026-02", tags=["denied", "moratorium"], summary=""),
            _entry("2026-01", tags=["denied"], summary=""),
        ]
        signals = compute_town_development_index(record=_record(entries), now=NOW)
        self.assertIsNotNone(signals.approval_rate)
        self.assertLessEqual(signals.approval_rate, 0.05)
        self.assertLess(signals.development_velocity, 0.40)

    def test_time_decay_favors_recent_entries(self):
        recent = [_entry("2026-03", tags=["approv"], summary="")]
        old = [_entry("2025-05", tags=["approv"], summary="")]
        recent_signals = compute_town_development_index(record=_record(recent), now=NOW)
        old_signals = compute_town_development_index(record=_record(old), now=NOW)
        # Same approval rate (1.0 in both), but time-weighted volume differs.
        self.assertGreater(
            recent_signals.activity_volume,
            old_signals.activity_volume,
        )

    def test_contention_keywords_detected_in_summary(self):
        entries = [
            _entry(
                "2026-03",
                tags=["approv"],
                summary=(
                    "Neighbors objected to the proposal. Public comment raised "
                    "concerns about density. Application was appealed."
                ),
            )
        ]
        signals = compute_town_development_index(record=_record(entries), now=NOW)
        self.assertGreater(signals.contention, 0.0)


class RegistryWiringTests(unittest.TestCase):
    def test_dev_index_is_registered_leaf(self):
        registry = build_module_registry()
        self.assertIn("town_development_index", registry)
        spec = registry["town_development_index"]
        self.assertEqual(spec.depends_on, [])

    def test_resale_scenario_depends_on_dev_index(self):
        registry = build_module_registry()
        spec = registry["resale_scenario"]
        self.assertIn("town_development_index", spec.depends_on)


class NudgeBoundsTests(unittest.TestCase):
    def test_nudge_clamped_at_max_when_velocity_extreme(self):
        ctx = ExecutionContext(
            property_id="p",
            prior_outputs={
                "town_development_index": {
                    "data": {"development_velocity": 1.0, "town": "X", "as_of": "2026-04-17"}
                }
            },
        )
        result = apply_dev_index_nudge(base_confidence=0.6, context=ctx, max_nudge=0.04)
        self.assertAlmostEqual(result.applied_nudge, 0.04, places=4)
        self.assertAlmostEqual(result.adjusted_confidence, 0.64, places=4)

    def test_nudge_symmetric_downward(self):
        ctx = ExecutionContext(
            property_id="p",
            prior_outputs={
                "town_development_index": {
                    "data": {"development_velocity": 0.0}
                }
            },
        )
        result = apply_dev_index_nudge(base_confidence=0.6, context=ctx, max_nudge=0.04)
        self.assertAlmostEqual(result.applied_nudge, -0.04, places=4)

    def test_neutral_velocity_produces_no_nudge(self):
        ctx = ExecutionContext(
            property_id="p",
            prior_outputs={"town_development_index": {"data": {"development_velocity": 0.5}}},
        )
        result = apply_dev_index_nudge(base_confidence=0.6, context=ctx)
        self.assertAlmostEqual(result.applied_nudge, 0.0, places=6)

    def test_missing_dev_index_no_ops(self):
        ctx = ExecutionContext(property_id="p")
        result = apply_dev_index_nudge(base_confidence=0.6, context=ctx)
        self.assertEqual(result.applied_nudge, 0.0)
        self.assertEqual(result.adjusted_confidence, 0.6)

    def test_missing_base_confidence_no_ops(self):
        ctx = ExecutionContext(
            property_id="p",
            prior_outputs={"town_development_index": {"data": {"development_velocity": 1.0}}},
        )
        result = apply_dev_index_nudge(base_confidence=None, context=ctx)
        self.assertEqual(result.applied_nudge, 0.0)
        self.assertIsNone(result.adjusted_confidence)


class ScopedRunnerTests(unittest.TestCase):
    def _seed_store(self, root: Path, *, slug: str, entries: list[MinuteEntry]) -> None:
        record = _record(entries)
        path = root / f"{slug}.json"
        path.write_text(
            json.dumps(record.model_dump(mode="json"), indent=2, sort_keys=True)
        )

    def test_runner_reads_seeded_manifest_via_patched_store_root(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Match the slug pattern emitted by MinutesFeed for this test town.
            feed = MinutesFeed(
                town="Testville",
                state="NJ",
                board="planning_board",
                index_url_template="https://x/{year}.php",
            )
            self._seed_store(
                root,
                slug=feed.slug,
                entries=[
                    _entry("2026-03", tags=["approv", "subdivision"]),
                    _entry("2026-02", tags=["approv", "site plan"]),
                ],
            )

            ctx = ExecutionContext(
                property_id="p",
                property_data={"town": "Testville", "state": "NJ"},
            )
            with patch(
                "briarwood.modules.town_development_index.feeds_for_town",
                return_value=[feed],
            ), patch(
                "briarwood.modules.town_development_index.JsonMinutesStore",
                lambda: JsonMinutesStore(root=root),
            ):
                payload = run_town_development_index(ctx)

        self.assertIsNotNone(payload.get("confidence"))
        data = payload["data"]
        self.assertEqual(data["town"], "Testville")
        self.assertGreater(data["development_velocity"], 0.5)
        self.assertIn("all_boards", data)

    def test_runner_returns_empty_payload_when_no_town(self):
        ctx = ExecutionContext(property_id="p", property_data={})
        payload = run_town_development_index(ctx)
        self.assertIsNone(payload["confidence"])
        self.assertIn("missing town/state", payload["warnings"][0])

    def test_runner_returns_empty_payload_when_no_feed_for_town(self):
        ctx = ExecutionContext(
            property_id="p",
            property_data={"town": "Nowhereville", "state": "NJ"},
        )
        with patch(
            "briarwood.modules.town_development_index.feeds_for_town",
            return_value=[],
        ):
            payload = run_town_development_index(ctx)
        self.assertIsNone(payload["confidence"])
        self.assertIn("no registered minutes feeds", payload["warnings"][0])


class ReadDevIndexTests(unittest.TestCase):
    def test_returns_data_when_present(self):
        ctx = ExecutionContext(
            property_id="p",
            prior_outputs={"town_development_index": {"data": {"development_velocity": 0.7}}},
        )
        data = read_dev_index(ctx)
        self.assertEqual(data, {"development_velocity": 0.7})

    def test_returns_none_when_absent(self):
        ctx = ExecutionContext(property_id="p")
        self.assertIsNone(read_dev_index(ctx))


if __name__ == "__main__":
    unittest.main()
