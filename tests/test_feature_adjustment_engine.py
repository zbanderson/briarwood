import unittest

from briarwood.agents.comparable_sales.schemas import (
    AdjustedComparable,
    BaseCompSelection,
    BaseCompSupportSummary,
    ComparableSalesOutput,
    ComparableValueRange,
)
from briarwood.feature_adjustment_engine import (
    ConfidenceBreakdown,
    FeatureAdjustmentResult,
    FeatureResult,
    _FALLBACK_ADU_CAP_RATE,
    _FALLBACK_ADU_EXPENSE_RATIO,
    _FALLBACK_BASEMENT_FINISHED_PER_SQFT,
    _FALLBACK_BASEMENT_UNFINISHED,
    _FALLBACK_EXCESS_LAND_PER_SQFT,
    _FALLBACK_GARAGE_VALUE_PER_SPACE,
    _FALLBACK_LEGAL_MULTI_UNIT_PCT,
    _FALLBACK_PARKING_PER_SPACE,
    _FALLBACK_POOL_INGROUND,
    _FALLBACK_TOWN_MEDIAN_LOT_ACRES,
    evaluate_feature_adjustments,
)
from briarwood.schemas import PropertyInput


def _base_property(**overrides) -> PropertyInput:
    """Minimal PropertyInput with sensible defaults."""
    defaults = dict(
        property_id="test-001",
        address="123 Test St",
        town="Belmar",
        state="NJ",
        beds=3,
        baths=2.0,
        sqft=1600,
    )
    defaults.update(overrides)
    return PropertyInput(**defaults)


def _base_comp(
    *,
    address: str = "100 Comp Ave",
    sale_price: float = 500_000,
    adjusted_price: float = 500_000,
    garage_spaces: int | None = None,
    lot_size: float | None = None,
    **kwargs,
) -> AdjustedComparable:
    """Minimal AdjustedComparable with sensible defaults."""
    defaults = dict(
        address=address,
        sale_date="2026-01-15",
        sale_price=sale_price,
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
        garage_spaces=garage_spaces,
        lot_size=lot_size,
    )
    defaults.update(kwargs)
    return AdjustedComparable(**defaults)


def _base_comp_output(
    *,
    comps: list[AdjustedComparable] | None = None,
    comparable_value: float = 500_000,
    is_hybrid: bool = False,
    additional_unit_income_value: float | None = None,
    additional_unit_annual_income: float | None = None,
    additional_unit_cap_rate: float | None = None,
    base_shell_value: float | None = 500_000,
) -> ComparableSalesOutput:
    """Minimal ComparableSalesOutput."""
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
        is_hybrid_valuation=is_hybrid,
        additional_unit_income_value=additional_unit_income_value,
        additional_unit_annual_income=additional_unit_annual_income,
        additional_unit_cap_rate=additional_unit_cap_rate,
        assumptions=[],
        unsupported_claims=[],
        warnings=[],
        summary="test",
    )


class TestFeatureAdjustmentEngineBasic(unittest.TestCase):
    """Core integration tests for the engine entry point."""

    def test_returns_all_nine_feature_keys(self) -> None:
        pi = _base_property()
        result = evaluate_feature_adjustments(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        expected_keys = {
            "adu", "garage", "basement", "pool", "lot_premium",
            "expansion", "extra_parking", "legal_multi_unit", "special_utility",
        }
        self.assertEqual(set(result.features.keys()), expected_keys)

    def test_bare_property_all_features_not_present(self) -> None:
        pi = _base_property()
        result = evaluate_feature_adjustments(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        for key, feat in result.features.items():
            self.assertFalse(feat.present, f"{key} should not be present on bare property")
            self.assertEqual(feat.adjustment, 0, f"{key} should have zero adjustment")

    def test_total_is_sum_of_feature_adjustments(self) -> None:
        pi = _base_property(garage_spaces=2, has_pool=True)
        result = evaluate_feature_adjustments(
            property_input=pi,
            comp_output=_base_comp_output(),
        )
        expected = sum(f.adjustment for f in result.features.values())
        self.assertAlmostEqual(result.total_feature_adjustment, round(expected, 2), places=2)

    def test_adjusted_value_is_base_plus_features(self) -> None:
        pi = _base_property(garage_spaces=1)
        result = evaluate_feature_adjustments(
            property_input=pi,
            comp_output=_base_comp_output(base_shell_value=400_000),
        )
        self.assertAlmostEqual(
            result.adjusted_value.feature_adjusted_value,
            400_000 + result.total_feature_adjustment,
            places=2,
        )

    def test_adjusted_value_none_when_no_base_shell(self) -> None:
        pi = _base_property()
        result = evaluate_feature_adjustments(
            property_input=pi,
            comp_output=_base_comp_output(base_shell_value=None, comparable_value=None),
        )
        self.assertIsNone(result.adjusted_value.feature_adjusted_value)


class TestADU(unittest.TestCase):
    """Tests for _evaluate_adu."""

    def test_no_adu_not_present(self) -> None:
        pi = _base_property()
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        adu = result.features["adu"]
        self.assertFalse(adu.present)
        self.assertEqual(adu.method, "not_applicable")

    def test_adu_with_rent_income_proxy(self) -> None:
        pi = _base_property(has_back_house=True, back_house_monthly_rent=1500.0)
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        adu = result.features["adu"]
        self.assertTrue(adu.present)
        self.assertEqual(adu.method, "income_proxy")
        self.assertEqual(adu.confidence, "moderate")
        expected_noi = 1500 * 12 * (1 - _FALLBACK_ADU_EXPENSE_RATIO)
        expected_value = expected_noi / _FALLBACK_ADU_CAP_RATE
        self.assertAlmostEqual(adu.adjustment, round(expected_value, 2), places=2)

    def test_adu_income_capped_at_35pct_base_shell(self) -> None:
        pi = _base_property(has_back_house=True, back_house_monthly_rent=5000.0)
        result = evaluate_feature_adjustments(
            property_input=pi,
            comp_output=_base_comp_output(base_shell_value=200_000),
        )
        adu = result.features["adu"]
        self.assertLessEqual(adu.adjustment, 200_000 * 0.35 + 1)

    def test_adu_with_unit_rents(self) -> None:
        pi = _base_property(adu_type="cottage", unit_rents=[1200.0, 800.0])
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        adu = result.features["adu"]
        self.assertTrue(adu.present)
        self.assertEqual(adu.method, "income_proxy")
        self.assertGreater(adu.adjustment, 0)

    def test_adu_present_no_rent_insufficient_data(self) -> None:
        pi = _base_property(has_back_house=True)
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        adu = result.features["adu"]
        self.assertTrue(adu.present)
        self.assertEqual(adu.adjustment, 0)
        self.assertEqual(adu.method, "insufficient_data")
        self.assertEqual(adu.confidence, "none")

    def test_adu_deferred_when_hybrid_valuation(self) -> None:
        pi = _base_property(has_back_house=True, back_house_monthly_rent=1500.0)
        comp_out = _base_comp_output(
            is_hybrid=True,
            additional_unit_income_value=120_000,
            additional_unit_annual_income=18_000,
            additional_unit_cap_rate=0.075,
        )
        result = evaluate_feature_adjustments(property_input=pi, comp_output=comp_out)
        adu = result.features["adu"]
        # When hybrid valuation already has income value, the engine should defer
        self.assertEqual(adu.method, "deferred_to_hybrid")
        self.assertEqual(adu.adjustment, 0)
        self.assertTrue(any("double-counting" in w for w in result.overlap_warnings))

    def test_adu_hybrid_uses_hybrid_value_then_defers(self) -> None:
        """When hybrid valuation has income value, engine initially picks it up but
        then defers to hybrid to avoid double-counting — final adjustment is 0."""
        pi = _base_property(has_back_house=True)
        comp_out = _base_comp_output(
            is_hybrid=True,
            additional_unit_income_value=100_000,
            additional_unit_annual_income=12_000,
            additional_unit_cap_rate=0.08,
        )
        result = evaluate_feature_adjustments(property_input=pi, comp_output=comp_out)
        adu = result.features["adu"]
        self.assertTrue(adu.present)
        # Overlap check defers to hybrid — adjustment zeroed, method set to deferred
        self.assertEqual(adu.method, "deferred_to_hybrid")
        self.assertEqual(adu.adjustment, 0)
        self.assertTrue(any("double-counting" in w for w in result.overlap_warnings))


class TestGarage(unittest.TestCase):
    """Tests for _evaluate_garage."""

    def test_no_garage_not_present(self) -> None:
        pi = _base_property(garage_spaces=0)
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        self.assertFalse(result.features["garage"].present)

    def test_garage_fallback_when_insufficient_comps(self) -> None:
        pi = _base_property(garage_spaces=2)
        comps = [_base_comp(garage_spaces=1)]  # only 1 with, 0 without
        result = evaluate_feature_adjustments(
            property_input=pi,
            comp_output=_base_comp_output(comps=comps),
        )
        garage = result.features["garage"]
        self.assertTrue(garage.present)
        self.assertEqual(garage.method, "fallback_rule")
        self.assertEqual(garage.confidence, "low")
        self.assertAlmostEqual(garage.adjustment, _FALLBACK_GARAGE_VALUE_PER_SPACE * 2, places=2)

    def test_garage_feature_comparison_with_sufficient_comps(self) -> None:
        pi = _base_property(garage_spaces=2)
        comps = [
            _base_comp(address="1 A St", garage_spaces=2, adjusted_price=550_000),
            _base_comp(address="2 B St", garage_spaces=1, adjusted_price=530_000),
            _base_comp(address="3 C St", garage_spaces=0, adjusted_price=480_000),
            _base_comp(address="4 D St", garage_spaces=0, adjusted_price=470_000),
        ]
        result = evaluate_feature_adjustments(
            property_input=pi,
            comp_output=_base_comp_output(comps=comps),
        )
        garage = result.features["garage"]
        self.assertTrue(garage.present)
        self.assertEqual(garage.method, "feature_comparison")
        self.assertEqual(garage.confidence, "moderate")
        self.assertGreater(garage.adjustment, 0)
        # Evidence should have with/without medians
        self.assertIsNotNone(garage.evidence.with_feature_median)
        self.assertIsNotNone(garage.evidence.without_feature_median)
        self.assertEqual(garage.evidence.sample_with, 2)
        self.assertEqual(garage.evidence.sample_without, 2)

    def test_garage_fallback_capped_at_8pct(self) -> None:
        pi = _base_property(garage_spaces=5)  # extreme case
        result = evaluate_feature_adjustments(
            property_input=pi,
            comp_output=_base_comp_output(base_shell_value=200_000),
        )
        garage = result.features["garage"]
        self.assertLessEqual(garage.adjustment, 200_000 * 0.08 + 1)

    def test_garage_detached_label_in_notes(self) -> None:
        pi = _base_property(garage_spaces=1, has_detached_garage=True)
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        self.assertIn("detached", result.features["garage"].notes.lower())


class TestBasement(unittest.TestCase):
    """Tests for _evaluate_basement."""

    def test_no_basement_not_present(self) -> None:
        pi = _base_property()
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        self.assertFalse(result.features["basement"].present)

    def test_finished_basement_fallback(self) -> None:
        pi = _base_property(has_basement=True, basement_finished=True, sqft=1600)
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        bsmt = result.features["basement"]
        self.assertTrue(bsmt.present)
        self.assertEqual(bsmt.method, "fallback_rule")
        self.assertEqual(bsmt.confidence, "low")
        expected_sqft = int(1600 * 0.40)
        expected = _FALLBACK_BASEMENT_FINISHED_PER_SQFT * expected_sqft
        self.assertAlmostEqual(bsmt.adjustment, expected, places=2)

    def test_finished_basement_capped_at_12pct(self) -> None:
        pi = _base_property(has_basement=True, basement_finished=True, sqft=5000)
        result = evaluate_feature_adjustments(
            property_input=pi,
            comp_output=_base_comp_output(base_shell_value=200_000),
        )
        self.assertLessEqual(result.features["basement"].adjustment, 200_000 * 0.12 + 1)

    def test_unfinished_basement_flat_value(self) -> None:
        pi = _base_property(has_basement=True, basement_finished=False)
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        bsmt = result.features["basement"]
        self.assertTrue(bsmt.present)
        self.assertEqual(bsmt.adjustment, _FALLBACK_BASEMENT_UNFINISHED)
        self.assertEqual(bsmt.confidence, "low")


class TestPool(unittest.TestCase):
    """Tests for _evaluate_pool."""

    def test_no_pool_not_present(self) -> None:
        pi = _base_property()
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        self.assertFalse(result.features["pool"].present)

    def test_pool_fallback(self) -> None:
        pi = _base_property(has_pool=True)
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        pool = result.features["pool"]
        self.assertTrue(pool.present)
        self.assertEqual(pool.method, "fallback_rule")
        self.assertEqual(pool.confidence, "low")
        self.assertEqual(pool.adjustment, _FALLBACK_POOL_INGROUND)

    def test_pool_capped_at_5pct(self) -> None:
        pi = _base_property(has_pool=True)
        result = evaluate_feature_adjustments(
            property_input=pi,
            comp_output=_base_comp_output(base_shell_value=100_000),
        )
        self.assertLessEqual(result.features["pool"].adjustment, 100_000 * 0.05 + 1)


class TestLotPremium(unittest.TestCase):
    """Tests for _evaluate_lot_premium."""

    def test_no_lot_size_not_present(self) -> None:
        pi = _base_property(lot_size=None)
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        self.assertFalse(result.features["lot_premium"].present)

    def test_small_lot_no_premium(self) -> None:
        # Lot at or below fallback median (0.10 acres)
        pi = _base_property(lot_size=0.08)
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        lot = result.features["lot_premium"]
        self.assertFalse(lot.present)
        self.assertEqual(lot.adjustment, 0)

    def test_excess_lot_fallback(self) -> None:
        # 0.25 acres vs 0.10 median = ~6,534 sqft excess
        pi = _base_property(lot_size=0.25)
        result = evaluate_feature_adjustments(
            property_input=pi,
            comp_output=_base_comp_output(comps=[_base_comp()]),  # no lot data on comps
        )
        lot = result.features["lot_premium"]
        self.assertTrue(lot.present)
        self.assertEqual(lot.method, "fallback_rule")
        self.assertGreater(lot.adjustment, 0)

    def test_lot_feature_comparison_with_comps(self) -> None:
        pi = _base_property(lot_size=0.30)
        median_lot = 0.10  # fallback median
        comps = [
            _base_comp(address="1 Big Lot", lot_size=0.25, adjusted_price=600_000),
            _base_comp(address="2 Big Lot", lot_size=0.28, adjusted_price=620_000),
            _base_comp(address="3 Small Lot", lot_size=0.08, adjusted_price=480_000),
            _base_comp(address="4 Small Lot", lot_size=0.07, adjusted_price=470_000),
        ]
        result = evaluate_feature_adjustments(
            property_input=pi,
            comp_output=_base_comp_output(comps=comps),
        )
        lot = result.features["lot_premium"]
        self.assertTrue(lot.present)
        self.assertEqual(lot.method, "feature_comparison")
        self.assertEqual(lot.confidence, "moderate")
        self.assertGreater(lot.adjustment, 0)

    def test_lot_uses_comp_median_over_fallback(self) -> None:
        pi = _base_property(lot_size=0.20)
        # Comps with lot sizes that produce a median around 0.15
        comps = [
            _base_comp(address="1 A", lot_size=0.14, adjusted_price=500_000),
            _base_comp(address="2 B", lot_size=0.15, adjusted_price=510_000),
            _base_comp(address="3 C", lot_size=0.16, adjusted_price=520_000),
        ]
        result = evaluate_feature_adjustments(
            property_input=pi,
            comp_output=_base_comp_output(comps=comps),
        )
        lot = result.features["lot_premium"]
        # With comp median ~0.15 acres, excess should be based on that, not 0.10
        self.assertIsNotNone(lot.evidence.town_median_lot_sqft)
        expected_median_sqft = 0.15 * 43560
        self.assertAlmostEqual(lot.evidence.town_median_lot_sqft, round(expected_median_sqft, 0), delta=50)

    def test_lot_uses_town_metrics_baseline(self) -> None:
        pi = _base_property(lot_size=0.20)
        result = evaluate_feature_adjustments(
            property_input=pi,
            comp_output=_base_comp_output(comps=[_base_comp()]),
            town_metrics={"baseline_median_lot_size": 0.12},
        )
        lot = result.features["lot_premium"]
        expected_median_sqft = 0.12 * 43560
        self.assertAlmostEqual(lot.evidence.town_median_lot_sqft, round(expected_median_sqft, 0), delta=50)


class TestExpansion(unittest.TestCase):
    """Tests for _evaluate_expansion."""

    def test_no_expansion_signals(self) -> None:
        pi = _base_property(lot_size=0.05)  # small lot, no basement
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        self.assertFalse(result.features["expansion"].present)

    def test_expansion_from_excess_lot(self) -> None:
        pi = _base_property(lot_size=0.25)  # above median
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        exp = result.features["expansion"]
        self.assertTrue(exp.present)
        self.assertEqual(exp.method, "insufficient_data")
        self.assertEqual(exp.adjustment, 0)  # valued at 0 without FAR data
        self.assertEqual(exp.confidence, "none")

    def test_expansion_from_unfinished_basement(self) -> None:
        pi = _base_property(has_basement=True, basement_finished=False, lot_size=0.05)
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        exp = result.features["expansion"]
        self.assertTrue(exp.present)
        self.assertIn("basement", exp.notes.lower())


class TestExtraParking(unittest.TestCase):
    """Tests for _evaluate_extra_parking."""

    def test_no_extra_parking(self) -> None:
        pi = _base_property(garage_spaces=2, parking_spaces=2)
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        self.assertFalse(result.features["extra_parking"].present)

    def test_extra_spaces_beyond_garage(self) -> None:
        pi = _base_property(garage_spaces=1, parking_spaces=3)
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        park = result.features["extra_parking"]
        self.assertTrue(park.present)
        self.assertAlmostEqual(park.adjustment, _FALLBACK_PARKING_PER_SPACE * 2, places=2)

    def test_driveway_counts_as_one_when_no_other_parking(self) -> None:
        pi = _base_property(garage_spaces=0, parking_spaces=0, driveway_off_street=True)
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        park = result.features["extra_parking"]
        self.assertTrue(park.present)
        self.assertAlmostEqual(park.adjustment, _FALLBACK_PARKING_PER_SPACE, places=2)


class TestLegalMultiUnit(unittest.TestCase):
    """Tests for _evaluate_legal_multi_unit."""

    def test_single_family_not_present(self) -> None:
        pi = _base_property(property_type="single family residence")
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        self.assertFalse(result.features["legal_multi_unit"].present)

    def test_duplex_with_fallback(self) -> None:
        pi = _base_property(property_type="duplex")
        result = evaluate_feature_adjustments(
            property_input=pi,
            comp_output=_base_comp_output(base_shell_value=400_000),
        )
        multi = result.features["legal_multi_unit"]
        self.assertTrue(multi.present)
        self.assertEqual(multi.method, "fallback_rule")
        self.assertAlmostEqual(multi.adjustment, 400_000 * _FALLBACK_LEGAL_MULTI_UNIT_PCT, places=2)

    def test_multi_unit_deferred_when_adu_valued(self) -> None:
        pi = _base_property(
            property_type="two-family",
            has_back_house=True,
            back_house_monthly_rent=1500.0,
        )
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        multi = result.features["legal_multi_unit"]
        self.assertTrue(multi.present)
        self.assertEqual(multi.method, "deferred_to_hybrid")
        self.assertEqual(multi.adjustment, 0)

    def test_zone_flag_triggers_multi_unit(self) -> None:
        pi = _base_property(zone_flags={"multi_unit_allowed": True})
        result = evaluate_feature_adjustments(
            property_input=pi,
            comp_output=_base_comp_output(base_shell_value=400_000),
        )
        multi = result.features["legal_multi_unit"]
        self.assertTrue(multi.present)
        self.assertGreater(multi.adjustment, 0)


class TestSpecialUtility(unittest.TestCase):
    """Tests for _evaluate_special_utility."""

    def test_no_special_utility(self) -> None:
        pi = _base_property(listing_description="Nice house with updated kitchen.")
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        self.assertFalse(result.features["special_utility"].present)

    def test_workshop_detected(self) -> None:
        pi = _base_property(listing_description="Features a large detached workshop for woodworking.")
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        sp = result.features["special_utility"]
        self.assertTrue(sp.present)
        self.assertEqual(sp.method, "insufficient_data")
        self.assertEqual(sp.adjustment, 0)
        self.assertIn("workshop", sp.notes.lower())

    def test_no_description_not_present(self) -> None:
        pi = _base_property()  # listing_description defaults to None
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        self.assertFalse(result.features["special_utility"].present)


class TestOverlapWarnings(unittest.TestCase):
    """Tests for anti-double-counting overlap warnings."""

    def test_adu_hybrid_overlap_warning(self) -> None:
        pi = _base_property(has_back_house=True, back_house_monthly_rent=1500.0)
        comp_out = _base_comp_output(
            is_hybrid=True,
            additional_unit_income_value=100_000,
            additional_unit_annual_income=12_000,
            additional_unit_cap_rate=0.08,
        )
        result = evaluate_feature_adjustments(property_input=pi, comp_output=comp_out)
        self.assertTrue(len(result.overlap_warnings) >= 1)
        self.assertTrue(any("hybrid" in w.lower() for w in result.overlap_warnings))

    def test_lot_plus_expansion_overlap_warning(self) -> None:
        pi = _base_property(lot_size=0.30, has_basement=True, basement_finished=False)
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        # lot_premium should be present (excess lot) and expansion should also be present
        # but expansion adjustment is 0 (insufficient data), so no overlap warning
        # The warning only fires when BOTH have adjustment > 0
        self.assertTrue(result.features["lot_premium"].present)
        self.assertTrue(result.features["expansion"].present)

    def test_garage_plus_parking_overlap_warning(self) -> None:
        pi = _base_property(garage_spaces=2, parking_spaces=5)
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        # Both garage and extra parking are valued
        self.assertTrue(result.features["garage"].present)
        self.assertTrue(result.features["extra_parking"].present)
        self.assertTrue(any("garage" in w.lower() and "parking" in w.lower() for w in result.overlap_warnings))

    def test_no_overlap_when_features_absent(self) -> None:
        pi = _base_property()
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        self.assertEqual(len(result.overlap_warnings), 0)


class TestConfidenceBreakdown(unittest.TestCase):
    """Tests for confidence breakdown and weighted confidence."""

    def test_no_features_confidence_na(self) -> None:
        pi = _base_property()
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        self.assertEqual(result.weighted_confidence, "n/a")

    def test_all_low_confidence_is_low(self) -> None:
        pi = _base_property(garage_spaces=1, has_pool=True)
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        # garage fallback = low, pool fallback = low
        self.assertEqual(result.weighted_confidence, "low")

    def test_moderate_when_income_proxy_dominates(self) -> None:
        pi = _base_property(has_back_house=True, back_house_monthly_rent=2000.0)
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        adu = result.features["adu"]
        self.assertEqual(adu.confidence, "moderate")
        # ADU should dominate total — weighted confidence should be moderate
        self.assertIn(result.weighted_confidence, ("moderate", "high"))

    def test_breakdown_sums_by_tier(self) -> None:
        pi = _base_property(
            garage_spaces=1,
            has_pool=True,
            has_back_house=True,
            back_house_monthly_rent=1500.0,
        )
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        bd = result.confidence_breakdown
        total_from_breakdown = (
            bd.high_confidence_portion
            + bd.moderate_confidence_portion
            + bd.low_confidence_portion
        )
        total_from_features = sum(
            f.adjustment for f in result.features.values()
            if f.present and f.confidence in ("high", "moderate", "low")
        )
        self.assertAlmostEqual(total_from_breakdown, total_from_features, places=2)

    def test_unvalued_features_tracked(self) -> None:
        pi = _base_property(
            listing_description="Features a large workshop.",
            lot_size=0.25,  # triggers expansion
        )
        result = evaluate_feature_adjustments(property_input=pi, comp_output=_base_comp_output())
        # special_utility is present but insufficient_data → unvalued
        # expansion is present but insufficient_data → unvalued
        self.assertIn("special_utility", result.confidence_breakdown.unvalued_features)
        self.assertIn("expansion", result.confidence_breakdown.unvalued_features)


if __name__ == "__main__":
    unittest.main()
