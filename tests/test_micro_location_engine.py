import unittest

from briarwood.agents.comparable_sales.schemas import (
    AdjustedComparable,
    BaseCompSelection,
    BaseCompSupportSummary,
    ComparableSalesOutput,
)
from briarwood.micro_location_engine import (
    _FALLBACK_BEACH_PREMIUM_BY_BUCKET,
    _FALLBACK_DOWNTOWN_PREMIUM_BY_BUCKET,
    _FALLBACK_FLOOD_DISCOUNT,
    _FALLBACK_TRAIN_PREMIUM_BY_BUCKET,
    evaluate_micro_location,
)
from briarwood.schemas import PropertyInput


# --- Belmar landmark data for tests ---
_BELMAR_LANDMARKS = {
    "beach": [{"label": "Belmar Boardwalk", "latitude": 40.1760, "longitude": -74.0175}],
    "downtown": [{"label": "Belmar Main Street", "latitude": 40.178, "longitude": -74.023}],
    "train": [{"label": "Belmar NJ Transit", "latitude": 40.184, "longitude": -74.028}],
}

# Subject 2 blocks from beach (~0.10mi)
_NEAR_BEACH_LAT = 40.1775
_NEAR_BEACH_LON = -74.0175

# Subject far from beach (~1.2mi)
_FAR_BEACH_LAT = 40.190
_FAR_BEACH_LON = -74.025


def _base_property(**overrides) -> PropertyInput:
    defaults = dict(
        property_id="test-loc-001",
        address="123 Beach Ave",
        town="Belmar",
        state="NJ",
        beds=3,
        baths=2.0,
        sqft=1600,
        latitude=_NEAR_BEACH_LAT,
        longitude=_NEAR_BEACH_LON,
        landmark_points=_BELMAR_LANDMARKS,
    )
    defaults.update(overrides)
    return PropertyInput(**defaults)


def _base_comp(
    *,
    address: str = "100 Comp Ave",
    adjusted_price: float = 500_000,
    location_tags: list[str] | None = None,
    **kwargs,
) -> AdjustedComparable:
    defaults = dict(
        address=address,
        sale_date="2026-01-15",
        sale_price=adjusted_price,
        time_adjusted_price=adjusted_price,
        adjusted_price=adjusted_price,
        comp_confidence_weight=0.80,
        similarity_score=0.75,
        fit_label="usable",
        sale_age_days=90,
        time_adjustment_pct=0.01,
        subject_adjustment_pct=0.0,
        why_comp=["property-type family match"],
        cautions=[],
        adjustments_summary=[],
        location_tags=location_tags or [],
    )
    defaults.update(kwargs)
    return AdjustedComparable(**defaults)


def _base_comp_output(
    *,
    comps: list[AdjustedComparable] | None = None,
    comparable_value: float = 500_000,
    base_shell_value: float | None = 500_000,
) -> ComparableSalesOutput:
    if comps is None:
        comps = [_base_comp()]
    selection = None
    if base_shell_value is not None:
        selection = BaseCompSelection(
            base_shell_value=base_shell_value,
            support_summary=BaseCompSupportSummary(comp_count=len(comps), same_town_count=len(comps)),
        )
    return ComparableSalesOutput(
        comparable_value=comparable_value,
        comp_count=len(comps),
        confidence=0.70,
        comps_used=comps,
        base_comp_selection=selection,
        assumptions=[],
        unsupported_claims=[],
        warnings=[],
        summary="test",
    )


class TestMicroLocationEngineBasic(unittest.TestCase):
    """Core integration tests for the engine entry point."""

    def test_returns_all_five_factor_keys(self) -> None:
        result = evaluate_micro_location(
            property_input=_base_property(),
            comp_output=_base_comp_output(),
        )
        expected = {"beach", "downtown", "train", "flood", "block_quality"}
        self.assertEqual(set(result.factors.keys()), expected)

    def test_total_is_sum_of_factor_adjustments(self) -> None:
        pi = _base_property(flood_risk="medium")
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        expected = sum(f.adjustment for f in result.factors.values())
        self.assertAlmostEqual(result.total_location_adjustment, round(expected, 2), places=2)

    def test_adjusted_value_is_base_plus_location(self) -> None:
        result = evaluate_micro_location(
            property_input=_base_property(),
            comp_output=_base_comp_output(base_shell_value=400_000),
        )
        self.assertAlmostEqual(
            result.adjusted_value.location_adjusted_value,
            400_000 + result.total_location_adjustment,
            places=2,
        )

    def test_no_coordinates_all_proximity_na(self) -> None:
        pi = _base_property(latitude=None, longitude=None)
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        for key in ("beach", "downtown", "train"):
            factor = result.factors[key]
            self.assertFalse(factor.applicable, f"{key} should not be applicable without coordinates")
            self.assertEqual(factor.method, "not_applicable")

    def test_no_landmarks_all_proximity_na(self) -> None:
        pi = _base_property(landmark_points={})
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        for key in ("beach", "downtown", "train"):
            self.assertFalse(result.factors[key].applicable)


class TestBeachProximity(unittest.TestCase):
    """Tests for _evaluate_beach."""

    def test_near_beach_gets_premium(self) -> None:
        pi = _base_property()  # ~0.10mi from beach
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        beach = result.factors["beach"]
        self.assertTrue(beach.applicable)
        self.assertGreater(beach.adjustment, 0)
        self.assertIsNotNone(beach.evidence.subject_distance_miles)
        self.assertLess(beach.evidence.subject_distance_miles, 0.20)

    def test_far_beach_no_premium(self) -> None:
        pi = _base_property(latitude=_FAR_BEACH_LAT, longitude=_FAR_BEACH_LON)
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        beach = result.factors["beach"]
        self.assertTrue(beach.applicable)
        self.assertEqual(beach.adjustment, 0)

    def test_beach_feature_comparison_with_tagged_comps(self) -> None:
        pi = _base_property()
        comps = [
            _base_comp(address="1 Beach St", adjusted_price=600_000, location_tags=["beach"]),
            _base_comp(address="2 Beach St", adjusted_price=620_000, location_tags=["beach"]),
            _base_comp(address="3 Inland Ave", adjusted_price=480_000, location_tags=[]),
            _base_comp(address="4 Inland Ave", adjusted_price=470_000, location_tags=[]),
        ]
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(comps=comps),
        )
        beach = result.factors["beach"]
        self.assertTrue(beach.applicable)
        self.assertEqual(beach.method, "feature_comparison")
        self.assertEqual(beach.confidence, "moderate")
        self.assertGreater(beach.adjustment, 0)
        self.assertEqual(beach.evidence.near_bucket_count, 2)
        self.assertEqual(beach.evidence.far_bucket_count, 2)

    def test_beach_fallback_when_insufficient_tagged_comps(self) -> None:
        pi = _base_property()
        comps = [_base_comp(location_tags=["beach"])]  # only 1 tagged
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(comps=comps),
        )
        beach = result.factors["beach"]
        self.assertEqual(beach.method, "fallback_rule")
        self.assertEqual(beach.confidence, "low")
        self.assertGreater(beach.adjustment, 0)

    def test_beach_capped_at_25pct(self) -> None:
        pi = _base_property()
        comps = [
            _base_comp(address="1 A", adjusted_price=800_000, location_tags=["beach"]),
            _base_comp(address="2 B", adjusted_price=900_000, location_tags=["beach"]),
            _base_comp(address="3 C", adjusted_price=200_000, location_tags=[]),
            _base_comp(address="4 D", adjusted_price=210_000, location_tags=[]),
        ]
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(comps=comps, base_shell_value=400_000),
        )
        beach = result.factors["beach"]
        self.assertLessEqual(beach.adjustment, 400_000 * 0.25 + 1)


class TestDowntownProximity(unittest.TestCase):
    """Tests for _evaluate_downtown."""

    def test_near_downtown_gets_premium(self) -> None:
        # Subject at 40.1775, -74.0175 — about 0.28mi from downtown at 40.178, -74.023
        pi = _base_property()
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        downtown = result.factors["downtown"]
        self.assertTrue(downtown.applicable)
        # Subject is ~0.28mi from downtown → walkable bucket → premium expected
        self.assertGreater(downtown.adjustment, 0)

    def test_downtown_feature_comparison(self) -> None:
        pi = _base_property()
        comps = [
            _base_comp(address="1 Main", adjusted_price=540_000, location_tags=["downtown"]),
            _base_comp(address="2 Main", adjusted_price=530_000, location_tags=["downtown"]),
            _base_comp(address="3 Rural", adjusted_price=480_000, location_tags=[]),
            _base_comp(address="4 Rural", adjusted_price=470_000, location_tags=[]),
        ]
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(comps=comps),
        )
        downtown = result.factors["downtown"]
        self.assertEqual(downtown.method, "feature_comparison")
        self.assertEqual(downtown.confidence, "moderate")

    def test_downtown_capped_at_12pct(self) -> None:
        pi = _base_property()
        comps = [
            _base_comp(address="1 A", adjusted_price=700_000, location_tags=["downtown"]),
            _base_comp(address="2 B", adjusted_price=710_000, location_tags=["downtown"]),
            _base_comp(address="3 C", adjusted_price=200_000, location_tags=[]),
            _base_comp(address="4 D", adjusted_price=210_000, location_tags=[]),
        ]
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(comps=comps, base_shell_value=400_000),
        )
        self.assertLessEqual(result.factors["downtown"].adjustment, 400_000 * 0.12 + 1)


class TestTrainProximity(unittest.TestCase):
    """Tests for _evaluate_train."""

    def test_train_proximity_applicable(self) -> None:
        # Subject ~0.10mi from beach, ~0.28mi from downtown, ~0.85mi from train
        pi = _base_property()
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        train = result.factors["train"]
        self.assertTrue(train.applicable)

    def test_train_feature_comparison(self) -> None:
        pi = _base_property()
        comps = [
            _base_comp(address="1 Station", adjusted_price=520_000, location_tags=["train"]),
            _base_comp(address="2 Station", adjusted_price=510_000, location_tags=["train"]),
            _base_comp(address="3 Far", adjusted_price=490_000, location_tags=[]),
            _base_comp(address="4 Far", adjusted_price=480_000, location_tags=[]),
        ]
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(comps=comps),
        )
        train = result.factors["train"]
        self.assertEqual(train.method, "feature_comparison")

    def test_no_train_landmarks_not_applicable(self) -> None:
        landmarks = {k: v for k, v in _BELMAR_LANDMARKS.items() if k != "train"}
        pi = _base_property(landmark_points=landmarks)
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        self.assertFalse(result.factors["train"].applicable)


class TestFloodExposure(unittest.TestCase):
    """Tests for _evaluate_flood."""

    def test_no_flood_data_not_applicable(self) -> None:
        pi = _base_property(flood_risk=None)
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        flood = result.factors["flood"]
        self.assertFalse(flood.applicable)

    def test_high_flood_discount(self) -> None:
        pi = _base_property(flood_risk="high")
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(base_shell_value=500_000),
        )
        flood = result.factors["flood"]
        self.assertTrue(flood.applicable)
        expected = 500_000 * _FALLBACK_FLOOD_DISCOUNT["high"]
        self.assertAlmostEqual(flood.adjustment, round(expected, 2), places=2)
        self.assertLess(flood.adjustment, 0)  # should be negative

    def test_medium_flood_discount(self) -> None:
        pi = _base_property(flood_risk="medium")
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(base_shell_value=500_000),
        )
        flood = result.factors["flood"]
        expected = 500_000 * _FALLBACK_FLOOD_DISCOUNT["medium"]
        self.assertAlmostEqual(flood.adjustment, round(expected, 2), places=2)
        self.assertLess(flood.adjustment, 0)

    def test_low_flood_no_discount(self) -> None:
        pi = _base_property(flood_risk="low")
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        self.assertEqual(result.factors["flood"].adjustment, 0)

    def test_in_flood_zone_flag_overrides(self) -> None:
        pi = _base_property(flood_risk="low", zone_flags={"in_flood_zone": True})
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(base_shell_value=500_000),
        )
        flood = result.factors["flood"]
        # in_flood_zone=True should override low risk to high
        expected = 500_000 * _FALLBACK_FLOOD_DISCOUNT["high"]
        self.assertAlmostEqual(flood.adjustment, round(expected, 2), places=2)

    def test_not_in_flood_zone_flag_no_discount(self) -> None:
        pi = _base_property(flood_risk="high", zone_flags={"in_flood_zone": False})
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        # in_flood_zone=False overrides town-level "high"
        self.assertEqual(result.factors["flood"].adjustment, 0)


class TestBlockQuality(unittest.TestCase):
    """Tests for _evaluate_block_quality."""

    def test_no_data_not_applicable(self) -> None:
        pi = _base_property()
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        block = result.factors["block_quality"]
        self.assertFalse(block.applicable)

    def test_premium_zone_detected_but_unvalued(self) -> None:
        pi = _base_property(zone_flags={"in_beach_premium_zone": True})
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        block = result.factors["block_quality"]
        self.assertTrue(block.applicable)
        self.assertEqual(block.adjustment, 0)
        self.assertEqual(block.method, "insufficient_data")


class TestOverlapWarnings(unittest.TestCase):
    """Tests for overlap detection."""

    def test_beach_and_downtown_overlap_warning(self) -> None:
        pi = _base_property()
        # Both beach and downtown have premiums (fallback)
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        beach = result.factors["beach"]
        downtown = result.factors["downtown"]
        if beach.adjustment > 0 and downtown.adjustment > 0:
            self.assertTrue(
                any("overlap" in w.lower() for w in result.overlap_warnings),
                "Should warn about beach/downtown overlap",
            )

    def test_no_overlap_when_only_one_factor(self) -> None:
        # Remove downtown landmarks
        landmarks = {"beach": _BELMAR_LANDMARKS["beach"]}
        pi = _base_property(landmark_points=landmarks)
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        # Only beach is applicable, no overlap
        overlap_beach_downtown = [
            w for w in result.overlap_warnings
            if "beach" in w.lower() and "downtown" in w.lower()
        ]
        self.assertEqual(len(overlap_beach_downtown), 0)


class TestConfidenceBreakdown(unittest.TestCase):
    """Tests for confidence breakdown and weighted confidence."""

    def test_no_applicable_factors_confidence_na(self) -> None:
        pi = _base_property(latitude=None, longitude=None, flood_risk=None)
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        self.assertEqual(result.weighted_confidence, "n/a")

    def test_all_fallback_is_low(self) -> None:
        pi = _base_property()
        # With default single comp (no tags), all proximity factors use fallback
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        # If there are any adjustments, confidence should be low
        if result.total_location_adjustment > 0:
            self.assertEqual(result.weighted_confidence, "low")

    def test_moderate_with_feature_comparison(self) -> None:
        pi = _base_property()
        comps = [
            _base_comp(address="1 A", adjusted_price=600_000, location_tags=["beach"]),
            _base_comp(address="2 B", adjusted_price=620_000, location_tags=["beach"]),
            _base_comp(address="3 C", adjusted_price=480_000, location_tags=[]),
            _base_comp(address="4 D", adjusted_price=470_000, location_tags=[]),
        ]
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(comps=comps),
        )
        # Beach should be feature_comparison (moderate), which dominates
        beach = result.factors["beach"]
        self.assertEqual(beach.confidence, "moderate")
        # Overall should be moderate if beach dominates total
        if beach.adjustment > abs(result.total_location_adjustment) * 0.5:
            self.assertIn(result.weighted_confidence, ("moderate", "high"))

    def test_breakdown_sums_by_tier(self) -> None:
        pi = _base_property(flood_risk="medium")
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        bd = result.confidence_breakdown
        total_from_breakdown = (
            bd.high_confidence_portion
            + bd.moderate_confidence_portion
            + bd.low_confidence_portion
        )
        total_from_factors = sum(
            f.adjustment for f in result.factors.values()
            if f.applicable and f.confidence in ("high", "moderate", "low")
        )
        self.assertAlmostEqual(total_from_breakdown, total_from_factors, places=2)


class TestFloodNegativeAdjustment(unittest.TestCase):
    """Flood is the only factor that produces negative adjustments."""

    def test_flood_reduces_total(self) -> None:
        pi = _base_property(flood_risk="high")
        result = evaluate_micro_location(
            property_input=pi,
            comp_output=_base_comp_output(base_shell_value=500_000),
        )
        flood_adj = result.factors["flood"].adjustment
        self.assertLess(flood_adj, 0)
        # Total = sum of all factors including negative flood
        recalc = sum(f.adjustment for f in result.factors.values())
        self.assertAlmostEqual(result.total_location_adjustment, round(recalc, 2), places=2)
        # Total should be less than it would be without flood
        total_without_flood = sum(
            f.adjustment for k, f in result.factors.items() if k != "flood"
        )
        self.assertLess(result.total_location_adjustment, total_without_flood)


if __name__ == "__main__":
    unittest.main()
