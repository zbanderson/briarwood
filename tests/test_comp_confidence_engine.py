import unittest

from briarwood.agents.comparable_sales.schemas import (
    AdjustedComparable,
    BaseCompSelection,
    BaseCompSelectionItem,
    BaseCompSupportSummary,
    ComparableSalesOutput,
)
from briarwood.comp_confidence_engine import (
    _BASE_SHELL_MIN_WEIGHT,
    _INACTIVE_SCORE,
    _LABEL_SCORES,
    _MATERIALITY_THRESHOLD,
    _WEAKEST_LAYER_CAP,
    _comp_count_score,
    _composite_label,
    _price_agreement_score,
    _score_label,
    _tier_distribution_score,
    SalesHistoryEvidence,
    evaluate_comp_confidence,
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
from briarwood.town_transfer_engine import (
    DonorTownEvidence,
    TransferResult,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _base_comp(
    *,
    address: str = "100 Comp Ave",
    adjusted_price: float = 500_000,
    similarity_score: float = 0.75,
    selection_tier: str = "tight_local",
    **kwargs,
) -> AdjustedComparable:
    defaults = dict(
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
        why_comp=["property-type family match"],
        cautions=[],
        adjustments_summary=[],
        location_tags=[],
    )
    defaults.update(kwargs)
    return AdjustedComparable(**defaults)


def _selection(
    *,
    comp_count: int = 4,
    support_quality: str = "strong",
    base_shell_value: float = 500_000,
    tier: str = "tight_local",
    similarity: float = 0.80,
) -> BaseCompSelection:
    return BaseCompSelection(
        selected_comps=[
            BaseCompSelectionItem(
                id=f"comp-{i}",
                address=f"{i} Test St",
                sale_price=base_shell_value,
                similarity_score=similarity,
                selection_tier=tier,
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
        comps = [_base_comp(adjusted_price=500_000 + i * 10_000) for i in range(4)]
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
    weighted_confidence: str = "moderate",
    total: float = 25_000,
    high_portion: float = 0.0,
    moderate_portion: float = 25_000,
    low_portion: float = 0.0,
    unvalued: list[str] | None = None,
    overlap_warnings: list[str] | None = None,
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
            high_confidence_portion=high_portion,
            moderate_confidence_portion=moderate_portion,
            low_confidence_portion=low_portion,
            unvalued_features=unvalued or [],
        ),
        overlap_warnings=overlap_warnings or [],
        adjusted_value=AdjustedValue(
            base_shell_value=500_000,
            plus_features=total,
            feature_adjusted_value=500_000 + total,
        ),
    )


def _location_result(
    *,
    weighted_confidence: str = "moderate",
    total: float = 30_000,
    high_portion: float = 0.0,
    moderate_portion: float = 30_000,
    low_portion: float = 0.0,
    unvalued: list[str] | None = None,
    overlap_warnings: list[str] | None = None,
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
            high_confidence_portion=high_portion,
            moderate_confidence_portion=moderate_portion,
            low_confidence_portion=low_portion,
            unvalued_factors=unvalued or [],
        ),
        overlap_warnings=overlap_warnings or [],
        adjusted_value=LocationAdjustedValue(
            base_shell_value=500_000,
            plus_location=total,
            location_adjusted_value=500_000 + total,
        ),
    )


def _transfer_result_inactive() -> TransferResult:
    return TransferResult(
        used=False,
        reason="Local comp support is 'strong' -- no transfer needed.",
    )


def _transfer_result_active(
    *,
    similarity: float = 0.65,
    transferred_confidence: float = 0.35,
    blended_value: float = 520_000,
    local_base: float = 500_000,
) -> TransferResult:
    return TransferResult(
        used=True,
        reason="Local support is thin.",
        donor_town="Avon By The Sea",
        translation_factor=1.05,
        translated_shell_value=530_000,
        blended_value=blended_value,
        local_base_value=local_base,
        confidence_penalty=0.25,
        transferred_confidence=transferred_confidence,
        similarity_score=similarity,
        method="ppsf_ratio_transfer",
        evidence=DonorTownEvidence(donor_town="Avon By The Sea"),
        candidates_evaluated=3,
        warnings=[],
    )


# ---------------------------------------------------------------------------
# Tests: Base Shell Layer
# ---------------------------------------------------------------------------

class TestBaseShellScoring(unittest.TestCase):

    def test_strong_support_scores_high(self):
        sel = _selection(comp_count=5, support_quality="strong", tier="tight_local", similarity=0.85)
        output = _comp_output(selection=sel)
        result = evaluate_comp_confidence(comp_output=output, base_comp_selection=sel)
        base = result.layers["base_shell"]
        self.assertGreaterEqual(base.score, 0.75)
        self.assertEqual(base.label, "strong")
        self.assertTrue(base.active)

    def test_thin_support_scores_low(self):
        sel = _selection(comp_count=1, support_quality="thin", tier="extended_support", similarity=0.40)
        output = _comp_output(comps=[_base_comp()], selection=sel)
        result = evaluate_comp_confidence(comp_output=output, base_comp_selection=sel)
        base = result.layers["base_shell"]
        self.assertLess(base.score, 0.55)


class TestSalesHistoryConfidence(unittest.TestCase):
    def test_sales_history_evidence_is_reported_when_present(self) -> None:
        output = _comp_output()
        history = SalesHistoryEvidence(
            event_count=3,
            complete_event_count=3,
            repeat_sale_pairs=2,
            history_span_years=11.5,
            most_recent_hold_years=5.5,
            history_confidence=0.82,
            history_confidence_label="strong",
            history_flags=[],
        )

        result = evaluate_comp_confidence(
            comp_output=output,
            sales_history_evidence=history,
        )

        self.assertIsNotNone(result.history_confidence)
        self.assertEqual(result.history_confidence.label, "strong")
        self.assertIn("sales history evidence is strong", result.narrative)

    def test_thin_sales_history_adds_actionable_gap(self) -> None:
        output = _comp_output()
        history = SalesHistoryEvidence(
            event_count=1,
            complete_event_count=0,
            repeat_sale_pairs=0,
            history_span_years=None,
            history_confidence=0.28,
            history_confidence_label="thin",
            history_flags=["disclosure_gap", "missing_price_per_sqft"],
        )

        result = evaluate_comp_confidence(
            comp_output=output,
            sales_history_evidence=history,
        )

        self.assertIsNotNone(result.history_confidence)
        self.assertLess(result.history_confidence.score, 0.6)
        self.assertTrue(any(g.layer == "sales_history" for g in result.actionable_gaps))
        self.assertIn(result.history_confidence.label, ("thin", "weak"))

    def test_moderate_support_is_middle(self):
        sel = _selection(comp_count=3, support_quality="moderate", tier="loose_local", similarity=0.65)
        comps = [_base_comp(adjusted_price=500_000 + i * 5000) for i in range(3)]
        output = _comp_output(comps=comps, selection=sel)
        result = evaluate_comp_confidence(comp_output=output, base_comp_selection=sel)
        base = result.layers["base_shell"]
        self.assertGreaterEqual(base.score, 0.45)
        self.assertLessEqual(base.score, 0.80)

    def test_base_shell_always_active(self):
        output = _comp_output()
        result = evaluate_comp_confidence(comp_output=output)
        self.assertTrue(result.layers["base_shell"].active)


class TestBaseShellComponents(unittest.TestCase):

    def test_comp_count_score_thresholds(self):
        self.assertEqual(_comp_count_score(0), 0.05)
        self.assertEqual(_comp_count_score(1), 0.25)
        self.assertEqual(_comp_count_score(2), 0.40)
        self.assertEqual(_comp_count_score(3), 0.65)
        self.assertEqual(_comp_count_score(4), 0.82)
        self.assertEqual(_comp_count_score(5), 0.95)
        self.assertEqual(_comp_count_score(10), 0.95)

    def test_tier_distribution_all_tight(self):
        sel = _selection(comp_count=4, tier="tight_local")
        self.assertEqual(_tier_distribution_score(sel), 1.0)

    def test_tier_distribution_all_extended(self):
        sel = _selection(comp_count=4, tier="extended_support")
        self.assertEqual(_tier_distribution_score(sel), 0.2)

    def test_tier_distribution_none(self):
        self.assertEqual(_tier_distribution_score(None), 0.30)

    def test_price_agreement_tight(self):
        # Very tight prices → high agreement
        comps = [_base_comp(adjusted_price=500_000 + i * 1_000) for i in range(4)]
        score = _price_agreement_score(comps)
        self.assertGreaterEqual(score, 0.80)

    def test_price_agreement_wide(self):
        # Wide spread → low agreement
        comps = [_base_comp(adjusted_price=p) for p in [300_000, 500_000, 700_000, 900_000]]
        score = _price_agreement_score(comps)
        self.assertLess(score, 0.50)

    def test_price_agreement_single_comp(self):
        self.assertEqual(_price_agreement_score([_base_comp()]), 0.50)


# ---------------------------------------------------------------------------
# Tests: Feature Layer
# ---------------------------------------------------------------------------

class TestFeatureLayerScoring(unittest.TestCase):

    def test_no_features_inactive(self):
        feat = _feature_result(
            total=0,
            moderate_portion=0,
            features={
                "garage": FeatureResult(
                    present=False, adjustment=0, confidence="n/a",
                    method="not_applicable", evidence=FeatureEvidence(),
                    notes="No garage",
                ),
            },
        )
        output = _comp_output()
        result = evaluate_comp_confidence(comp_output=output, feature_result=feat)
        self.assertFalse(result.layers["features"].active)
        self.assertEqual(result.layers["features"].score, _INACTIVE_SCORE)

    def test_high_confidence_features(self):
        feat = _feature_result(
            weighted_confidence="high",
            total=30_000,
            high_portion=30_000,
            moderate_portion=0,
        )
        output = _comp_output()
        result = evaluate_comp_confidence(comp_output=output, feature_result=feat)
        layer = result.layers["features"]
        self.assertTrue(layer.active)
        self.assertGreaterEqual(layer.score, 0.70)

    def test_low_confidence_features(self):
        feat = _feature_result(
            weighted_confidence="low",
            total=30_000,
            high_portion=0,
            moderate_portion=0,
            low_portion=30_000,
        )
        output = _comp_output()
        result = evaluate_comp_confidence(comp_output=output, feature_result=feat)
        layer = result.layers["features"]
        self.assertLess(layer.score, 0.55)

    def test_unvalued_features_penalized(self):
        feat_clean = _feature_result(total=20_000, moderate_portion=20_000)
        feat_unvalued = _feature_result(total=20_000, moderate_portion=20_000, unvalued=["expansion", "pool"])
        output = _comp_output()
        clean = evaluate_comp_confidence(comp_output=output, feature_result=feat_clean)
        unvalued = evaluate_comp_confidence(comp_output=output, feature_result=feat_unvalued)
        self.assertLess(unvalued.layers["features"].score, clean.layers["features"].score)

    def test_none_feature_result_inactive(self):
        output = _comp_output()
        result = evaluate_comp_confidence(comp_output=output, feature_result=None)
        self.assertFalse(result.layers["features"].active)


# ---------------------------------------------------------------------------
# Tests: Location Layer
# ---------------------------------------------------------------------------

class TestLocationLayerScoring(unittest.TestCase):

    def test_no_factors_inactive(self):
        loc = _location_result(
            total=0,
            moderate_portion=0,
            factors={
                "beach": LocationResult(
                    applicable=False, adjustment=0, confidence="n/a",
                    method="not_applicable", evidence=LocationEvidence(),
                    notes="No beach data",
                ),
            },
        )
        output = _comp_output()
        result = evaluate_comp_confidence(comp_output=output, location_result=loc)
        self.assertFalse(result.layers["location"].active)

    def test_moderate_location_confidence(self):
        loc = _location_result(weighted_confidence="moderate", total=40_000, moderate_portion=40_000)
        output = _comp_output()
        result = evaluate_comp_confidence(comp_output=output, location_result=loc)
        layer = result.layers["location"]
        self.assertTrue(layer.active)
        self.assertGreaterEqual(layer.score, 0.50)

    def test_none_location_result_inactive(self):
        output = _comp_output()
        result = evaluate_comp_confidence(comp_output=output, location_result=None)
        self.assertFalse(result.layers["location"].active)


# ---------------------------------------------------------------------------
# Tests: Town Transfer Layer
# ---------------------------------------------------------------------------

class TestTownTransferLayerScoring(unittest.TestCase):

    def test_not_used_inactive(self):
        output = _comp_output()
        result = evaluate_comp_confidence(
            comp_output=output,
            transfer_result=_transfer_result_inactive(),
        )
        layer = result.layers["town_transfer"]
        self.assertFalse(layer.active)
        self.assertEqual(layer.score, _INACTIVE_SCORE)

    def test_used_active(self):
        output = _comp_output()
        result = evaluate_comp_confidence(
            comp_output=output,
            transfer_result=_transfer_result_active(),
        )
        layer = result.layers["town_transfer"]
        self.assertTrue(layer.active)
        self.assertGreater(layer.score, 0.0)

    def test_high_similarity_scores_better(self):
        output = _comp_output()
        low = evaluate_comp_confidence(
            comp_output=output,
            transfer_result=_transfer_result_active(similarity=0.45, transferred_confidence=0.20),
        )
        high = evaluate_comp_confidence(
            comp_output=output,
            transfer_result=_transfer_result_active(similarity=0.90, transferred_confidence=0.45),
        )
        self.assertGreater(
            high.layers["town_transfer"].score,
            low.layers["town_transfer"].score,
        )

    def test_warnings_reduce_score(self):
        tr_clean = _transfer_result_active()
        tr_warns = _transfer_result_active()
        tr_warns.warnings = ["warning 1", "warning 2", "warning 3"]
        output = _comp_output()
        clean = evaluate_comp_confidence(comp_output=output, transfer_result=tr_clean)
        warns = evaluate_comp_confidence(comp_output=output, transfer_result=tr_warns)
        self.assertLess(
            warns.layers["town_transfer"].score,
            clean.layers["town_transfer"].score,
        )

    def test_none_transfer_result_inactive(self):
        output = _comp_output()
        result = evaluate_comp_confidence(comp_output=output, transfer_result=None)
        self.assertFalse(result.layers["town_transfer"].active)


# ---------------------------------------------------------------------------
# Tests: Composite Scoring
# ---------------------------------------------------------------------------

class TestCompositeScoring(unittest.TestCase):

    def test_strong_everything_high_composite(self):
        sel = _selection(comp_count=5, support_quality="strong", tier="tight_local", similarity=0.85)
        output = _comp_output(selection=sel)
        feat = _feature_result(weighted_confidence="high", total=20_000, high_portion=20_000)
        loc = _location_result(weighted_confidence="moderate", total=30_000, moderate_portion=30_000)
        result = evaluate_comp_confidence(
            comp_output=output,
            base_comp_selection=sel,
            feature_result=feat,
            location_result=loc,
            transfer_result=_transfer_result_inactive(),
        )
        self.assertGreaterEqual(result.composite_score, 0.65)
        self.assertIn(result.composite_label, ("High", "Medium"))

    def test_thin_everything_low_composite(self):
        sel = _selection(comp_count=1, support_quality="thin", tier="extended_support", similarity=0.35)
        output = _comp_output(comps=[_base_comp()], selection=sel)
        feat = _feature_result(weighted_confidence="low", total=10_000, low_portion=10_000)
        loc = _location_result(weighted_confidence="low", total=5_000, low_portion=5_000)
        result = evaluate_comp_confidence(
            comp_output=output,
            base_comp_selection=sel,
            feature_result=feat,
            location_result=loc,
        )
        self.assertLess(result.composite_score, 0.55)
        self.assertEqual(result.composite_label, "Low")

    def test_weakest_layer_caps_composite(self):
        # Strong base shell but very weak features with material dollar amount
        sel = _selection(comp_count=5, support_quality="strong", tier="tight_local", similarity=0.90)
        output = _comp_output(selection=sel, comparable_value=500_000)
        # Feature adjustment is 20% of base value — material
        feat = _feature_result(weighted_confidence="low", total=100_000, low_portion=100_000)
        result = evaluate_comp_confidence(
            comp_output=output,
            base_comp_selection=sel,
            feature_result=feat,
        )
        feature_score = result.layers["features"].score
        # Composite should be capped at weakest_material * 2.0
        self.assertLessEqual(result.composite_score, feature_score * _WEAKEST_LAYER_CAP + 0.01)

    def test_base_shell_minimum_weight(self):
        sel = _selection(comp_count=4, support_quality="strong")
        output = _comp_output(selection=sel)
        feat = _feature_result(total=20_000)
        result = evaluate_comp_confidence(
            comp_output=output,
            base_comp_selection=sel,
            feature_result=feat,
        )
        self.assertGreaterEqual(
            result.layers["base_shell"].weight_in_composite,
            _BASE_SHELL_MIN_WEIGHT,
        )

    def test_inactive_layers_not_weighted(self):
        output = _comp_output()
        result = evaluate_comp_confidence(comp_output=output)
        # Only base_shell should be active
        for key, layer in result.layers.items():
            if key == "base_shell":
                self.assertTrue(layer.active)
                self.assertGreater(layer.weight_in_composite, 0)
            else:
                self.assertFalse(layer.active)
                self.assertEqual(layer.weight_in_composite, 0.0)


# ---------------------------------------------------------------------------
# Tests: Composite Labels
# ---------------------------------------------------------------------------

class TestCompositeLabels(unittest.TestCase):

    def test_label_thresholds(self):
        self.assertEqual(_composite_label(0.80), "High")
        self.assertEqual(_composite_label(0.75), "High")
        self.assertEqual(_composite_label(0.60), "Medium")
        self.assertEqual(_composite_label(0.55), "Medium")
        self.assertEqual(_composite_label(0.50), "Low")
        self.assertEqual(_composite_label(0.30), "Low")

    def test_score_labels(self):
        self.assertEqual(_score_label(0.80), "strong")
        self.assertEqual(_score_label(0.75), "strong")
        self.assertEqual(_score_label(0.60), "adequate")
        self.assertEqual(_score_label(0.55), "adequate")
        self.assertEqual(_score_label(0.40), "weak")
        self.assertEqual(_score_label(0.20), "unsupported")


# ---------------------------------------------------------------------------
# Tests: Actionable Gaps
# ---------------------------------------------------------------------------

class TestActionableGaps(unittest.TestCase):

    def test_thin_base_produces_gap(self):
        sel = _selection(comp_count=1, support_quality="thin", tier="extended_support", similarity=0.35)
        output = _comp_output(comps=[_base_comp()], selection=sel)
        result = evaluate_comp_confidence(comp_output=output, base_comp_selection=sel)
        base_gaps = [g for g in result.actionable_gaps if g.layer == "base_shell"]
        self.assertTrue(len(base_gaps) > 0)
        self.assertEqual(base_gaps[0].impact, "high")

    def test_unvalued_features_produce_gaps(self):
        feat = _feature_result(total=20_000, moderate_portion=20_000, unvalued=["expansion", "pool"])
        output = _comp_output()
        result = evaluate_comp_confidence(comp_output=output, feature_result=feat)
        feature_gaps = [g for g in result.actionable_gaps if g.layer == "features" and "Unvalued" in g.gap]
        self.assertEqual(len(feature_gaps), 2)

    def test_fallback_features_produce_gaps(self):
        feat = _feature_result(
            weighted_confidence="low",
            total=20_000,
            low_portion=20_000,
            features={
                "basement": FeatureResult(
                    present=True, adjustment=20_000, confidence="low",
                    method="fallback_rule", evidence=FeatureEvidence(),
                    notes="Fallback basement",
                ),
            },
        )
        output = _comp_output()
        result = evaluate_comp_confidence(comp_output=output, feature_result=feat)
        fallback_gaps = [g for g in result.actionable_gaps if "fallback" in g.gap]
        self.assertTrue(len(fallback_gaps) > 0)

    def test_town_transfer_produces_gap(self):
        output = _comp_output()
        result = evaluate_comp_confidence(
            comp_output=output,
            transfer_result=_transfer_result_active(),
        )
        transfer_gaps = [g for g in result.actionable_gaps if g.layer == "town_transfer"]
        self.assertTrue(len(transfer_gaps) > 0)
        self.assertEqual(transfer_gaps[0].impact, "high")

    def test_gaps_sorted_by_impact(self):
        sel = _selection(comp_count=1, support_quality="thin", tier="extended_support", similarity=0.35)
        feat = _feature_result(
            weighted_confidence="low",
            total=5_000,
            low_portion=5_000,
            features={
                "pool": FeatureResult(
                    present=True, adjustment=5_000, confidence="low",
                    method="fallback_rule", evidence=FeatureEvidence(),
                    notes="Fallback pool",
                ),
            },
        )
        output = _comp_output(comps=[_base_comp()], selection=sel)
        result = evaluate_comp_confidence(
            comp_output=output,
            base_comp_selection=sel,
            feature_result=feat,
            transfer_result=_transfer_result_active(),
        )
        impacts = [g.impact for g in result.actionable_gaps]
        impact_order = {"high": 0, "moderate": 1, "low": 2}
        numeric = [impact_order[i] for i in impacts]
        self.assertEqual(numeric, sorted(numeric))

    def test_max_five_gaps(self):
        feat = _feature_result(
            total=10_000,
            low_portion=10_000,
            weighted_confidence="low",
            unvalued=["a", "b", "c", "d", "e", "f"],
            features={
                "garage": FeatureResult(
                    present=True, adjustment=10_000, confidence="low",
                    method="fallback_rule", evidence=FeatureEvidence(),
                    notes="",
                ),
            },
        )
        sel = _selection(comp_count=1, support_quality="thin", tier="extended_support", similarity=0.35)
        output = _comp_output(comps=[_base_comp()], selection=sel)
        result = evaluate_comp_confidence(
            comp_output=output,
            base_comp_selection=sel,
            feature_result=feat,
            transfer_result=_transfer_result_active(),
        )
        self.assertLessEqual(len(result.actionable_gaps), 5)


# ---------------------------------------------------------------------------
# Tests: Narrative
# ---------------------------------------------------------------------------

class TestNarrative(unittest.TestCase):

    def test_high_composite_narrative(self):
        sel = _selection(comp_count=5, support_quality="strong", tier="tight_local", similarity=0.85)
        output = _comp_output(selection=sel)
        result = evaluate_comp_confidence(comp_output=output, base_comp_selection=sel)
        if result.composite_label == "High":
            self.assertIn("well-supported", result.narrative)

    def test_low_composite_narrative(self):
        sel = _selection(comp_count=1, support_quality="thin", tier="extended_support", similarity=0.35)
        output = _comp_output(comps=[_base_comp()], selection=sel)
        result = evaluate_comp_confidence(comp_output=output, base_comp_selection=sel)
        self.assertIn("thin", result.narrative.lower())

    def test_narrative_mentions_active_layers(self):
        sel = _selection(comp_count=4, support_quality="strong")
        output = _comp_output(selection=sel)
        feat = _feature_result(total=20_000)
        loc = _location_result(total=15_000)
        result = evaluate_comp_confidence(
            comp_output=output,
            base_comp_selection=sel,
            feature_result=feat,
            location_result=loc,
        )
        self.assertIn("base shell", result.narrative)
        self.assertIn("feature", result.narrative)
        self.assertIn("location", result.narrative)

    def test_narrative_mentions_transfer_when_active(self):
        output = _comp_output()
        result = evaluate_comp_confidence(
            comp_output=output,
            transfer_result=_transfer_result_active(),
        )
        self.assertIn("town-transferred", result.narrative)


# ---------------------------------------------------------------------------
# Tests: Output Shape
# ---------------------------------------------------------------------------

class TestOutputShape(unittest.TestCase):

    def test_all_layers_present(self):
        output = _comp_output()
        result = evaluate_comp_confidence(comp_output=output)
        self.assertIn("base_shell", result.layers)
        self.assertIn("features", result.layers)
        self.assertIn("location", result.layers)
        self.assertIn("town_transfer", result.layers)

    def test_composite_score_bounded(self):
        output = _comp_output()
        result = evaluate_comp_confidence(comp_output=output)
        self.assertGreaterEqual(result.composite_score, 0.0)
        self.assertLessEqual(result.composite_score, 1.0)

    def test_composite_label_valid(self):
        output = _comp_output()
        result = evaluate_comp_confidence(comp_output=output)
        self.assertIn(result.composite_label, ("High", "Medium", "Low"))

    def test_weakest_layer_is_valid_key(self):
        output = _comp_output()
        result = evaluate_comp_confidence(comp_output=output)
        self.assertIn(result.weakest_layer, result.layers)

    def test_layer_scores_bounded(self):
        sel = _selection(comp_count=4, support_quality="strong")
        output = _comp_output(selection=sel)
        feat = _feature_result()
        loc = _location_result()
        result = evaluate_comp_confidence(
            comp_output=output,
            base_comp_selection=sel,
            feature_result=feat,
            location_result=loc,
            transfer_result=_transfer_result_active(),
        )
        for layer in result.layers.values():
            self.assertGreaterEqual(layer.score, 0.0)
            self.assertLessEqual(layer.score, 1.0)

    def test_layer_labels_valid(self):
        output = _comp_output()
        result = evaluate_comp_confidence(comp_output=output)
        valid = {"strong", "adequate", "weak", "unsupported"}
        for layer in result.layers.values():
            self.assertIn(layer.label, valid)

    def test_components_have_required_fields(self):
        sel = _selection(comp_count=4, support_quality="strong")
        output = _comp_output(selection=sel)
        result = evaluate_comp_confidence(comp_output=output, base_comp_selection=sel)
        for component in result.layers["base_shell"].components:
            self.assertIsInstance(component.key, str)
            self.assertIsInstance(component.value, float)
            self.assertIn(component.contribution, ("positive", "neutral", "negative"))
            self.assertIsInstance(component.note, str)

    def test_minimal_input(self):
        """Engine handles bare-minimum input without crashing."""
        output = ComparableSalesOutput(
            comparable_value=400_000,
            comp_count=0,
            confidence=0.3,
            comps_used=[],
            assumptions=[],
            unsupported_claims=[],
            warnings=[],
            summary="Bare minimum",
        )
        result = evaluate_comp_confidence(comp_output=output)
        self.assertIsInstance(result.composite_score, float)
        self.assertIn(result.composite_label, ("High", "Medium", "Low"))


# ---------------------------------------------------------------------------
# Tests: Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases(unittest.TestCase):

    def test_zero_dollar_features(self):
        """Features with $0 total but present features should still be active."""
        feat = _feature_result(
            total=0,
            moderate_portion=0,
            weighted_confidence="n/a",
            features={
                "expansion": FeatureResult(
                    present=True, adjustment=0, confidence="none",
                    method="insufficient_data", evidence=FeatureEvidence(),
                    notes="Expansion detected but not valued",
                ),
            },
        )
        output = _comp_output()
        result = evaluate_comp_confidence(comp_output=output, feature_result=feat)
        self.assertTrue(result.layers["features"].active)

    def test_negative_location_adjustment(self):
        """Flood discount (negative) should be handled correctly."""
        loc = _location_result(
            total=-25_000,
            moderate_portion=-25_000,
            factors={
                "flood": LocationResult(
                    applicable=True, adjustment=-25_000, confidence="moderate",
                    method="fallback_rule", evidence=LocationEvidence(),
                    notes="Flood discount",
                ),
            },
        )
        output = _comp_output()
        result = evaluate_comp_confidence(comp_output=output, location_result=loc)
        layer = result.layers["location"]
        self.assertTrue(layer.active)
        self.assertEqual(layer.dollar_contribution, -25_000)

    def test_no_base_comp_selection(self):
        """Engine works when base_comp_selection is None."""
        output = _comp_output(selection=None, comparable_value=450_000)
        result = evaluate_comp_confidence(comp_output=output)
        self.assertTrue(result.layers["base_shell"].active)
        self.assertIsInstance(result.composite_score, float)


if __name__ == "__main__":
    unittest.main()
