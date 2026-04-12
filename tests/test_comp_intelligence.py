"""Tests for the Comp Analysis Integrator (comp_intelligence.py).

Verifies that run_comp_analysis():
  - Calls each engine once and assembles a unified output
  - Composes adjusted_value deterministically from base_shell + layers
  - Uses the Comp Confidence Engine's composite_score as confidence
  - Produces schema-compatible output (ComparableCompAnalysis keys)
  - Preserves backward compatibility via build_comp_analysis alias
"""

import unittest
from unittest.mock import patch, MagicMock

from briarwood.agents.comparable_sales.schemas import (
    AdjustedComparable,
    BaseCompSelection,
    BaseCompSelectionItem,
    BaseCompSupportSummary,
    ComparableCompAnalysis,
    ComparableSalesOutput,
)
from briarwood.comp_intelligence import (
    run_comp_analysis,
    build_comp_analysis,
    _compose_value,
    _feature_adjustments_from_engine,
    _location_adjustments_from_engine,
    _town_transfer_from_engine,
    _build_support_summary,
    _support_type_from_confidence,
    _round_money,
)
from briarwood.feature_adjustment_engine import (
    AdjustedValue,
    ConfidenceBreakdown,
    FeatureAdjustmentResult,
    FeatureEvidence,
    FeatureResult,
)
from briarwood.micro_location_engine import (
    LocationAdjustedValue,
    LocationConfidenceBreakdown,
    LocationEvidence,
    LocationResult,
    MicroLocationResult,
)
from briarwood.town_transfer_engine import TransferResult
from briarwood.comp_confidence_engine import (
    CompConfidenceResult,
    ConfidenceGap,
    LayerConfidence,
)
from briarwood.schemas import PropertyInput


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _comp(
    *,
    address: str = "100 Comp Ave",
    adjusted_price: float = 500_000,
    similarity_score: float = 0.75,
) -> AdjustedComparable:
    return AdjustedComparable(
        address=address,
        sale_date="2026-01-15",
        sale_price=adjusted_price,
        time_adjusted_price=adjusted_price,
        adjusted_price=adjusted_price,
        comp_confidence_weight=0.80,
        similarity_score=similarity_score,
        fit_label="usable",
        sale_age_days=90,
        time_adjustment_pct=0.01,
        subject_adjustment_pct=0.0,
        why_comp=["property-type match"],
        cautions=[],
        adjustments_summary=[],
        location_tags=[],
    )


def _selection(
    *,
    comp_count: int = 4,
    support_quality: str = "strong",
    base_shell_value: float = 500_000,
) -> BaseCompSelection:
    return BaseCompSelection(
        selected_comps=[
            BaseCompSelectionItem(
                id=f"comp-{i}",
                address=f"{i} Test St",
                sale_price=base_shell_value,
                similarity_score=0.80,
                selection_tier="tight_local",
            )
            for i in range(comp_count)
        ],
        base_shell_value=base_shell_value,
        support_summary=BaseCompSupportSummary(
            comp_count=comp_count,
            same_town_count=comp_count,
            support_quality=support_quality,
        ),
    )


def _comp_output(
    *,
    comps: list[AdjustedComparable] | None = None,
    comparable_value: float = 500_000,
    selection: BaseCompSelection | None = None,
    confidence: float = 0.72,
) -> ComparableSalesOutput:
    if comps is None:
        comps = [_comp(adjusted_price=500_000 + i * 10_000) for i in range(4)]
    return ComparableSalesOutput(
        comparable_value=comparable_value,
        comp_count=len(comps),
        confidence=confidence,
        comps_used=comps,
        base_comp_selection=selection,
        assumptions=[],
        unsupported_claims=[],
        warnings=[],
        summary="Test output",
    )


def _feature_result(
    *,
    total: float = 25_000,
    weighted_confidence: str = "moderate",
    features: dict | None = None,
) -> FeatureAdjustmentResult:
    if features is None:
        features = {
            "garage": FeatureResult(
                present=True,
                adjustment=total,
                confidence=weighted_confidence,
                method="feature_comparison",
                evidence=FeatureEvidence(),
                notes="Test garage",
            ),
        }
    return FeatureAdjustmentResult(
        features=features,
        total_feature_adjustment=total,
        weighted_confidence=weighted_confidence,
        confidence_breakdown=ConfidenceBreakdown(
            moderate_confidence_portion=total,
        ),
        overlap_warnings=[],
        adjusted_value=AdjustedValue(
            base_shell_value=500_000,
            plus_features=total,
            feature_adjusted_value=500_000 + total,
        ),
    )


def _location_result(
    *,
    total: float = 30_000,
    weighted_confidence: str = "moderate",
    factors: dict | None = None,
) -> MicroLocationResult:
    if factors is None:
        factors = {
            "beach": LocationResult(
                applicable=True,
                adjustment=total,
                confidence=weighted_confidence,
                method="feature_comparison",
                evidence=LocationEvidence(),
                notes="Test beach",
            ),
        }
    return MicroLocationResult(
        factors=factors,
        total_location_adjustment=total,
        weighted_confidence=weighted_confidence,
        confidence_breakdown=LocationConfidenceBreakdown(
            moderate_confidence_portion=total,
        ),
        overlap_warnings=[],
        adjusted_value=LocationAdjustedValue(
            base_shell_value=500_000,
            plus_location=total,
            location_adjusted_value=500_000 + total,
        ),
    )


def _transfer_result(*, used: bool = False, **kwargs) -> TransferResult:
    defaults = dict(
        used=used,
        reason="Local support is adequate" if not used else "Thin local support",
        method="not_activated" if not used else "ppsf_ratio_translation",
    )
    defaults.update(kwargs)
    return TransferResult(**defaults)


def _confidence_result(
    *,
    composite_score: float = 0.68,
    composite_label: str = "Medium",
) -> CompConfidenceResult:
    return CompConfidenceResult(
        composite_score=composite_score,
        composite_label=composite_label,
        layers={
            "base_shell": LayerConfidence(
                layer="base_shell", score=0.75, label="adequate",
                active=True, dollar_contribution=500_000, weight_in_composite=0.50,
            ),
            "features": LayerConfidence(
                layer="features", score=0.65, label="adequate",
                active=True, dollar_contribution=25_000, weight_in_composite=0.20,
            ),
            "location": LayerConfidence(
                layer="location", score=0.60, label="adequate",
                active=True, dollar_contribution=30_000, weight_in_composite=0.20,
            ),
            "town_transfer": LayerConfidence(
                layer="town_transfer", score=0.80, label="strong",
                active=False, dollar_contribution=0, weight_in_composite=0.10,
            ),
        },
        weakest_layer="location",
        actionable_gaps=[],
        narrative="Test narrative",
    )


def _property_input(**kwargs) -> PropertyInput:
    defaults = dict(
        property_id="test-prop-1",
        address="123 Test St",
        town="Belmar",
        state="NJ",
        beds=3,
        baths=2.0,
        sqft=1500,
    )
    defaults.update(kwargs)
    return PropertyInput(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRunCompAnalysis(unittest.TestCase):
    """Integration test: run_comp_analysis produces valid ComparableCompAnalysis."""

    @patch("briarwood.comp_intelligence.evaluate_comp_confidence")
    @patch("briarwood.comp_intelligence.evaluate_town_transfer")
    @patch("briarwood.comp_intelligence.evaluate_micro_location")
    @patch("briarwood.comp_intelligence.evaluate_feature_adjustments")
    def test_produces_valid_schema(self, mock_feat, mock_loc, mock_transfer, mock_conf):
        mock_feat.return_value = _feature_result()
        mock_loc.return_value = _location_result()
        mock_transfer.return_value = _transfer_result()
        mock_conf.return_value = _confidence_result()

        output = _comp_output(selection=_selection())
        result = run_comp_analysis(output=output, property_input=_property_input())

        # Should validate as ComparableCompAnalysis without error
        analysis = ComparableCompAnalysis.model_validate(result)
        self.assertIsNotNone(analysis.base_shell_value)
        self.assertIsNotNone(analysis.adjusted_value)
        self.assertGreaterEqual(analysis.confidence, 0.0)
        self.assertLessEqual(analysis.confidence, 1.0)

    @patch("briarwood.comp_intelligence.evaluate_comp_confidence")
    @patch("briarwood.comp_intelligence.evaluate_town_transfer")
    @patch("briarwood.comp_intelligence.evaluate_micro_location")
    @patch("briarwood.comp_intelligence.evaluate_feature_adjustments")
    def test_calls_each_engine_once(self, mock_feat, mock_loc, mock_transfer, mock_conf):
        mock_feat.return_value = _feature_result()
        mock_loc.return_value = _location_result()
        mock_transfer.return_value = _transfer_result()
        mock_conf.return_value = _confidence_result()

        output = _comp_output(selection=_selection())
        run_comp_analysis(output=output, property_input=_property_input())

        mock_feat.assert_called_once()
        mock_loc.assert_called_once()
        mock_transfer.assert_called_once()
        mock_conf.assert_called_once()

    @patch("briarwood.comp_intelligence.evaluate_comp_confidence")
    @patch("briarwood.comp_intelligence.evaluate_town_transfer")
    @patch("briarwood.comp_intelligence.evaluate_micro_location")
    @patch("briarwood.comp_intelligence.evaluate_feature_adjustments")
    def test_confidence_from_engine(self, mock_feat, mock_loc, mock_transfer, mock_conf):
        """Confidence should come from CompConfidenceEngine, not the old blend."""
        mock_feat.return_value = _feature_result()
        mock_loc.return_value = _location_result()
        mock_transfer.return_value = _transfer_result()
        mock_conf.return_value = _confidence_result(composite_score=0.73)

        output = _comp_output(selection=_selection(), confidence=0.50)
        result = run_comp_analysis(output=output, property_input=_property_input())

        self.assertEqual(result["confidence"], 0.73)

    @patch("briarwood.comp_intelligence.evaluate_comp_confidence")
    @patch("briarwood.comp_intelligence.evaluate_town_transfer")
    @patch("briarwood.comp_intelligence.evaluate_micro_location")
    @patch("briarwood.comp_intelligence.evaluate_feature_adjustments")
    def test_has_all_engine_dicts(self, mock_feat, mock_loc, mock_transfer, mock_conf):
        mock_feat.return_value = _feature_result()
        mock_loc.return_value = _location_result()
        mock_transfer.return_value = _transfer_result()
        mock_conf.return_value = _confidence_result()

        output = _comp_output(selection=_selection())
        result = run_comp_analysis(output=output, property_input=_property_input())

        self.assertIsInstance(result["feature_engine"], dict)
        self.assertIsInstance(result["location_engine"], dict)
        self.assertIsInstance(result["town_transfer_engine"], dict)
        self.assertIsInstance(result["confidence_engine"], dict)

    @patch("briarwood.comp_intelligence.evaluate_comp_confidence")
    @patch("briarwood.comp_intelligence.evaluate_town_transfer")
    @patch("briarwood.comp_intelligence.evaluate_micro_location")
    @patch("briarwood.comp_intelligence.evaluate_feature_adjustments")
    def test_backward_compat_keys(self, mock_feat, mock_loc, mock_transfer, mock_conf):
        """Output must contain keys checked by test_modules.py:250-255."""
        mock_feat.return_value = _feature_result()
        mock_loc.return_value = _location_result()
        mock_transfer.return_value = _transfer_result()
        mock_conf.return_value = _confidence_result()

        output = _comp_output(selection=_selection())
        result = run_comp_analysis(output=output, property_input=_property_input())

        self.assertIn("beach", result["location_adjustments"])
        self.assertIn("cross_town_shell_transfer", result["town_transfer_adjustments"])
        self.assertIsNotNone(result["base_shell_value"])
        self.assertGreaterEqual(result["confidence"], 0.0)


class TestBuildCompAnalysisAlias(unittest.TestCase):
    """Verify build_comp_analysis is an alias for run_comp_analysis."""

    def test_alias_is_same_function(self):
        self.assertIs(build_comp_analysis, run_comp_analysis)


class TestComposeValue(unittest.TestCase):
    """Test deterministic value composition."""

    def test_base_plus_features_plus_location(self):
        value = _compose_value(
            base_shell_value=500_000,
            feature_result=_feature_result(total=25_000),
            location_result=_location_result(total=30_000),
            transfer_result=_transfer_result(used=False),
        )
        self.assertEqual(value, 555_000)

    def test_with_town_transfer(self):
        transfer = _transfer_result(
            used=True,
            blended_value=520_000,
            local_base_value=500_000,
        )
        value = _compose_value(
            base_shell_value=500_000,
            feature_result=_feature_result(total=10_000),
            location_result=_location_result(total=15_000),
            transfer_result=transfer,
        )
        # 500K + 10K + 15K + (520K - 500K) = 545K
        self.assertEqual(value, 545_000)

    def test_none_base_shell(self):
        value = _compose_value(
            base_shell_value=None,
            feature_result=_feature_result(total=25_000),
            location_result=_location_result(total=30_000),
            transfer_result=_transfer_result(used=False),
        )
        self.assertIsNone(value)

    def test_zero_adjustments(self):
        value = _compose_value(
            base_shell_value=400_000,
            feature_result=_feature_result(total=0),
            location_result=_location_result(total=0),
            transfer_result=_transfer_result(used=False),
        )
        self.assertEqual(value, 400_000)

    def test_negative_adjustments(self):
        """Flood discount produces negative location adjustment."""
        value = _compose_value(
            base_shell_value=500_000,
            feature_result=_feature_result(total=10_000),
            location_result=_location_result(total=-25_000),
            transfer_result=_transfer_result(used=False),
        )
        self.assertEqual(value, 485_000)


class TestFeatureAdjustmentsFromEngine(unittest.TestCase):
    """Test conversion from engine FeatureResult to schema FeatureAdjustment."""

    def test_present_feature_with_adjustment(self):
        result = _feature_result(total=18_000, weighted_confidence="moderate")
        items = _feature_adjustments_from_engine(result)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].key, "garage")
        self.assertEqual(items[0].amount, 18_000)
        self.assertEqual(items[0].method, "feature_comparison")
        self.assertEqual(items[0].support_type, "direct")

    def test_not_present_feature(self):
        features = {
            "pool": FeatureResult(
                present=False,
                adjustment=0,
                confidence="n/a",
                method="not_applicable",
                evidence=FeatureEvidence(),
                notes="No pool",
            ),
        }
        result = _feature_result(total=0, features=features)
        items = _feature_adjustments_from_engine(result)
        self.assertEqual(len(items), 1)
        self.assertIsNone(items[0].amount)
        self.assertEqual(items[0].support_type, "pending")

    def test_low_confidence_maps_to_observed(self):
        features = {
            "basement": FeatureResult(
                present=True,
                adjustment=8_000,
                confidence="low",
                method="fallback_rule",
                evidence=FeatureEvidence(),
                notes="Fallback",
            ),
        }
        result = _feature_result(total=8_000, features=features)
        items = _feature_adjustments_from_engine(result)
        self.assertEqual(items[0].support_type, "observed")


class TestLocationAdjustmentsFromEngine(unittest.TestCase):
    """Test conversion from engine LocationResult to schema LocationAdjustment."""

    def test_applicable_factor(self):
        result = _location_result(total=40_000, weighted_confidence="moderate")
        items = _location_adjustments_from_engine(result)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].key, "beach")
        self.assertEqual(items[0].amount, 40_000)

    def test_not_applicable_factor(self):
        factors = {
            "train": LocationResult(
                applicable=False,
                adjustment=0,
                confidence="n/a",
                method="not_applicable",
                evidence=LocationEvidence(),
                notes="No train data",
            ),
        }
        result = _location_result(total=0, factors=factors)
        items = _location_adjustments_from_engine(result)
        self.assertEqual(len(items), 1)
        self.assertIsNone(items[0].amount)


class TestTownTransferFromEngine(unittest.TestCase):
    """Test conversion from engine TransferResult to schema TownTransferAdjustment."""

    def test_not_activated(self):
        result = _transfer_result(used=False)
        items = _town_transfer_from_engine(result, "Belmar")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].key, "cross_town_shell_transfer")
        self.assertIsNone(items[0].amount)
        self.assertEqual(items[0].to_town, "Belmar")

    def test_activated(self):
        result = _transfer_result(
            used=True,
            donor_town="Avon By The Sea",
            blended_value=520_000,
            local_base_value=500_000,
        )
        items = _town_transfer_from_engine(result, "Belmar")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].amount, 20_000)
        self.assertEqual(items[0].from_town, "Avon By The Sea")
        self.assertEqual(items[0].to_town, "Belmar")
        self.assertEqual(items[0].support_type, "translated")


class TestSupportSummary(unittest.TestCase):
    """Test support summary construction."""

    def test_with_base_comp_selection(self):
        output = _comp_output(selection=_selection(comp_count=5, support_quality="strong"))
        summary = _build_support_summary(
            output,
            _feature_result(weighted_confidence="moderate"),
            _location_result(weighted_confidence="moderate"),
        )
        self.assertEqual(summary.direct_support_count, 5)
        self.assertEqual(summary.same_town_count, 5)
        self.assertEqual(summary.primary_mode, "direct_same_town")

    def test_low_confidence_engines_add_notes(self):
        output = _comp_output(selection=_selection())
        summary = _build_support_summary(
            output,
            _feature_result(weighted_confidence="low"),
            _location_result(weighted_confidence="none"),
        )
        notes_text = " ".join(summary.notes)
        self.assertIn("low", notes_text)
        self.assertIn("none", notes_text)

    def test_without_base_comp_selection(self):
        output = _comp_output(selection=None)
        summary = _build_support_summary(
            output,
            _feature_result(),
            _location_result(),
        )
        self.assertEqual(summary.direct_support_count, len(output.comps_used))


class TestSupportTypeMapping(unittest.TestCase):
    """Test confidence label to support_type mapping."""

    def test_high_is_direct(self):
        self.assertEqual(_support_type_from_confidence("high"), "direct")

    def test_moderate_is_direct(self):
        self.assertEqual(_support_type_from_confidence("moderate"), "direct")

    def test_low_is_observed(self):
        self.assertEqual(_support_type_from_confidence("low"), "observed")

    def test_none_is_pending(self):
        self.assertEqual(_support_type_from_confidence("none"), "pending")

    def test_na_is_pending(self):
        self.assertEqual(_support_type_from_confidence("n/a"), "pending")


class TestRoundMoney(unittest.TestCase):

    def test_rounds_to_two_decimals(self):
        self.assertEqual(_round_money(123.456), 123.46)

    def test_none_passthrough(self):
        self.assertIsNone(_round_money(None))


if __name__ == "__main__":
    unittest.main()
