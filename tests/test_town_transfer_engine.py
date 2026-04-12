import unittest
from unittest.mock import patch

from briarwood.agents.comparable_sales.schemas import (
    AdjustedComparable,
    BaseCompSelection,
    BaseCompSupportSummary,
    ComparableSalesOutput,
)
from briarwood.modules.town_aggregation_diagnostics import TownContext
from briarwood.schemas import PropertyInput
from briarwood.town_transfer_engine import (
    _ADJACENCY_BONUS,
    _CONFIDENCE_PENALTY,
    _MAX_TRANSFERRED_CONFIDENCE,
    _MIN_DONOR_SAMPLE_SIZE,
    _MIN_SIMILARITY,
    _TRANSFER_BLEND_WEIGHT,
    _blend_values,
    _compute_translation_factor,
    _index_similarity,
    _value_similarity,
    evaluate_town_transfer,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _base_property(**overrides) -> PropertyInput:
    defaults = dict(
        property_id="test-transfer-001",
        address="123 Main St",
        town="Belmar",
        state="NJ",
        beds=3,
        baths=2.0,
        sqft=1500,
    )
    defaults.update(overrides)
    return PropertyInput(**defaults)


def _base_comp(
    *,
    address: str = "100 Comp Ave",
    adjusted_price: float = 500_000,
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
        location_tags=[],
    )
    defaults.update(kwargs)
    return AdjustedComparable(**defaults)


def _base_comp_output(
    *,
    comps: list[AdjustedComparable] | None = None,
    comparable_value: float = 500_000,
    base_shell_value: float | None = 500_000,
    support_quality: str = "thin",
) -> ComparableSalesOutput:
    if comps is None:
        comps = [_base_comp()]
    selection = None
    if base_shell_value is not None:
        selection = BaseCompSelection(
            base_shell_value=base_shell_value,
            support_summary=BaseCompSupportSummary(
                comp_count=len(comps),
                same_town_count=len(comps),
                support_quality=support_quality,
            ),
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
        summary="Test output",
    )


def _town_context(
    *,
    town: str = "Belmar",
    median_ppsf: float | None = 350.0,
    town_ppsf_index: float | None = 95.0,
    town_price_index: float | None = 90.0,
    town_lot_index: float | None = 80.0,
    town_liquidity_index: float | None = 105.0,
    sample_size: int = 20,
    low_sample_flag: bool = False,
    high_dispersion_flag: bool = False,
    context_confidence: float = 0.75,
    **overrides,
) -> TownContext:
    defaults = dict(
        town=town,
        listing_count=10,
        sold_count=10,
        sample_size=sample_size,
        median_list_price=550_000.0,
        median_sale_price=500_000.0,
        median_price=500_000.0,
        median_ppsf=median_ppsf,
        median_sqft=1400.0,
        median_lot_size=0.15,
        median_days_on_market=45.0,
        median_sale_to_list_ratio=0.97,
        town_price_index=town_price_index,
        town_ppsf_index=town_ppsf_index,
        town_lot_index=town_lot_index,
        town_liquidity_index=town_liquidity_index,
        avg_confidence_score=0.70,
        missing_data_rate=0.10,
        outlier_count=1,
        sqft_coverage_rate=0.85,
        lot_size_coverage_rate=0.60,
        year_built_coverage_rate=0.90,
        ppsf_std_dev=50.0,
        low_sample_flag=low_sample_flag,
        high_missingness_flag=False,
        high_dispersion_flag=high_dispersion_flag,
        outlier_heavy_flag=False,
        low_confidence_flag=False,
        context_confidence=context_confidence,
        qa_flags=[],
    )
    defaults.update(overrides)
    return TownContext(**defaults)


_MOCK_COASTAL = [
    {"name": "Belmar", "coastal_profile_signal": 0.84},
    {"name": "Bradley Beach", "coastal_profile_signal": 0.82},
    {"name": "Spring Lake", "coastal_profile_signal": 0.97},
    {"name": "Avon By The Sea", "coastal_profile_signal": 0.91},
    {"name": "Manasquan", "coastal_profile_signal": 0.87},
]


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------

class TestActivation(unittest.TestCase):
    """Engine should only activate on thin support."""

    def test_not_activated_strong_support(self):
        output = _base_comp_output(support_quality="strong")
        result = evaluate_town_transfer(
            property_input=_base_property(),
            comp_output=output,
            base_comp_selection=output.base_comp_selection,
        )
        self.assertFalse(result.used)
        self.assertIn("strong", result.reason)

    def test_not_activated_moderate_support(self):
        output = _base_comp_output(support_quality="moderate")
        result = evaluate_town_transfer(
            property_input=_base_property(),
            comp_output=output,
            base_comp_selection=output.base_comp_selection,
        )
        self.assertFalse(result.used)
        self.assertIn("moderate", result.reason)

    def test_activated_thin_support(self):
        """Thin support should trigger the engine (mocking town context)."""
        output = _base_comp_output(support_quality="thin")
        subject_ctx = _town_context(town="Belmar")
        donor_ctx = _town_context(
            town="Bradley Beach",
            median_ppsf=340.0,
            town_ppsf_index=92.0,
            town_price_index=88.0,
        )

        def mock_get_context(town, **kwargs):
            mapping = {"Belmar": subject_ctx, "Bradley Beach": donor_ctx}
            return mapping.get(town)

        with patch("briarwood.town_transfer_engine.get_town_context", side_effect=mock_get_context), \
             patch("briarwood.town_transfer_engine._find_donor_candidates") as mock_find:
            from briarwood.town_transfer_engine import TownPairScore
            mock_find.return_value = [
                TownPairScore(donor_town="Bradley Beach", similarity=0.82, is_adjacent=True)
            ]
            result = evaluate_town_transfer(
                property_input=_base_property(),
                comp_output=output,
                base_comp_selection=output.base_comp_selection,
            )
            self.assertTrue(result.used)
            self.assertEqual(result.donor_town, "Bradley Beach")

    def test_activated_no_base_comp_selection(self):
        """No base_comp_selection defaults to thin support."""
        output = _base_comp_output(base_shell_value=None)
        output = ComparableSalesOutput(
            comparable_value=500_000,
            comp_count=1,
            confidence=0.70,
            comps_used=[_base_comp()],
            base_comp_selection=None,
            assumptions=[],
            unsupported_claims=[],
            warnings=[],
            summary="Test",
        )
        subject_ctx = _town_context(town="Belmar")
        donor_ctx = _town_context(
            town="Bradley Beach",
            median_ppsf=340.0,
            town_ppsf_index=92.0,
        )

        def mock_get_context(town, **kwargs):
            return {"Belmar": subject_ctx, "Bradley Beach": donor_ctx}.get(town)

        with patch("briarwood.town_transfer_engine.get_town_context", side_effect=mock_get_context), \
             patch("briarwood.town_transfer_engine._find_donor_candidates") as mock_find:
            from briarwood.town_transfer_engine import TownPairScore
            mock_find.return_value = [
                TownPairScore(donor_town="Bradley Beach", similarity=0.80, is_adjacent=True)
            ]
            result = evaluate_town_transfer(
                property_input=_base_property(),
                comp_output=output,
            )
            self.assertTrue(result.used)


class TestTranslationFactor(unittest.TestCase):
    """Translation factor computation."""

    def test_same_ppsf_yields_one(self):
        subject = _town_context(median_ppsf=350.0)
        donor = _town_context(median_ppsf=350.0)
        factor = _compute_translation_factor(subject, donor)
        self.assertAlmostEqual(factor, 1.0)

    def test_subject_cheaper_yields_less_than_one(self):
        subject = _town_context(median_ppsf=300.0)
        donor = _town_context(median_ppsf=400.0)
        factor = _compute_translation_factor(subject, donor)
        self.assertAlmostEqual(factor, 0.75)

    def test_subject_pricier_yields_greater_than_one(self):
        subject = _town_context(median_ppsf=500.0)
        donor = _town_context(median_ppsf=400.0)
        factor = _compute_translation_factor(subject, donor)
        self.assertAlmostEqual(factor, 1.25)

    def test_none_when_subject_ppsf_missing(self):
        subject = _town_context(median_ppsf=None)
        donor = _town_context(median_ppsf=400.0)
        self.assertIsNone(_compute_translation_factor(subject, donor))

    def test_none_when_donor_ppsf_missing(self):
        subject = _town_context(median_ppsf=350.0)
        donor = _town_context(median_ppsf=None)
        self.assertIsNone(_compute_translation_factor(subject, donor))

    def test_none_when_donor_ppsf_zero(self):
        subject = _town_context(median_ppsf=350.0)
        donor = _town_context(median_ppsf=0.0)
        self.assertIsNone(_compute_translation_factor(subject, donor))


class TestBlending(unittest.TestCase):
    """Value blending between local base and translated value."""

    def test_blend_with_both_values(self):
        local = 500_000.0
        translated = 550_000.0
        blended = _blend_values(local, translated)
        expected = local * (1 - _TRANSFER_BLEND_WEIGHT) + translated * _TRANSFER_BLEND_WEIGHT
        self.assertAlmostEqual(blended, expected)

    def test_blend_no_local_uses_translated(self):
        blended = _blend_values(None, 550_000.0)
        self.assertAlmostEqual(blended, 550_000.0)

    def test_blend_no_translated_uses_local(self):
        blended = _blend_values(500_000.0, None)
        self.assertAlmostEqual(blended, 500_000.0)

    def test_blend_both_none(self):
        self.assertIsNone(_blend_values(None, None))


class TestSimilarityScoring(unittest.TestCase):
    """Town-pair similarity score helpers."""

    def test_index_similarity_identical(self):
        self.assertAlmostEqual(_index_similarity(100.0, 100.0), 1.0)

    def test_index_similarity_close(self):
        # 95 / 100 = 0.95
        self.assertAlmostEqual(_index_similarity(95.0, 100.0), 0.95)

    def test_index_similarity_far(self):
        # 50 / 150 = 0.333
        self.assertAlmostEqual(_index_similarity(50.0, 150.0), 0.333)

    def test_index_similarity_none_returns_neutral(self):
        self.assertAlmostEqual(_index_similarity(None, 100.0), 0.5)
        self.assertAlmostEqual(_index_similarity(100.0, None), 0.5)

    def test_value_similarity_identical(self):
        self.assertAlmostEqual(_value_similarity(0.84, 0.84), 1.0)

    def test_value_similarity_close(self):
        # delta=0.02, max_delta=0.30 → 1 - 0.02/0.30 = 0.933
        result = _value_similarity(0.84, 0.82, max_delta=0.30)
        self.assertAlmostEqual(result, 0.933, places=2)

    def test_value_similarity_far(self):
        # delta=0.30, max_delta=0.30 → 1 - 1.0 = 0.0
        self.assertAlmostEqual(_value_similarity(0.50, 0.80, max_delta=0.30), 0.0)

    def test_value_similarity_none_returns_neutral(self):
        self.assertAlmostEqual(_value_similarity(None, 0.80), 0.5)


class TestConfidencePenalty(unittest.TestCase):
    """Transferred confidence is always penalized and capped."""

    def test_confidence_penalty_applied(self):
        output = _base_comp_output(support_quality="thin")
        output_confidence = output.confidence  # 0.70
        subject_ctx = _town_context(town="Belmar")
        donor_ctx = _town_context(
            town="Bradley Beach",
            median_ppsf=340.0,
            town_ppsf_index=92.0,
        )

        def mock_get_context(town, **kwargs):
            return {"Belmar": subject_ctx, "Bradley Beach": donor_ctx}.get(town)

        with patch("briarwood.town_transfer_engine.get_town_context", side_effect=mock_get_context), \
             patch("briarwood.town_transfer_engine._find_donor_candidates") as mock_find:
            from briarwood.town_transfer_engine import TownPairScore
            mock_find.return_value = [
                TownPairScore(donor_town="Bradley Beach", similarity=0.80, is_adjacent=True)
            ]
            result = evaluate_town_transfer(
                property_input=_base_property(),
                comp_output=output,
                base_comp_selection=output.base_comp_selection,
            )
            self.assertTrue(result.used)
            # Confidence should be penalized and capped
            self.assertLessEqual(result.transferred_confidence, _MAX_TRANSFERRED_CONFIDENCE)
            self.assertLess(result.transferred_confidence, output_confidence)

    def test_confidence_never_below_floor(self):
        """Even with very low initial confidence, floor should hold."""
        output = _base_comp_output(support_quality="thin")
        # Override to very low confidence
        output = ComparableSalesOutput(
            comparable_value=500_000,
            comp_count=1,
            confidence=0.10,
            comps_used=[_base_comp()],
            base_comp_selection=BaseCompSelection(
                base_shell_value=500_000,
                support_summary=BaseCompSupportSummary(
                    comp_count=1, same_town_count=1, support_quality="thin"
                ),
            ),
            assumptions=[],
            unsupported_claims=[],
            warnings=[],
            summary="Test",
        )
        subject_ctx = _town_context(town="Belmar")
        donor_ctx = _town_context(town="Bradley Beach", median_ppsf=340.0, town_ppsf_index=92.0)

        def mock_get_context(town, **kwargs):
            return {"Belmar": subject_ctx, "Bradley Beach": donor_ctx}.get(town)

        with patch("briarwood.town_transfer_engine.get_town_context", side_effect=mock_get_context), \
             patch("briarwood.town_transfer_engine._find_donor_candidates") as mock_find:
            from briarwood.town_transfer_engine import TownPairScore
            mock_find.return_value = [
                TownPairScore(donor_town="Bradley Beach", similarity=0.80, is_adjacent=True)
            ]
            result = evaluate_town_transfer(
                property_input=_base_property(),
                comp_output=output,
                base_comp_selection=output.base_comp_selection,
            )
            self.assertTrue(result.used)
            self.assertGreaterEqual(result.transferred_confidence, 0.05)


class TestDonorDisqualification(unittest.TestCase):
    """Donor towns should be disqualified for data quality issues."""

    def test_low_sample_disqualified(self):
        from briarwood.town_transfer_engine import _score_town_pair
        subject = _town_context(town="Belmar")
        donor = _town_context(town="Tiny Town", sample_size=3, low_sample_flag=True)
        score = _score_town_pair(
            subject=subject,
            donor=donor,
            subject_town="Belmar",
            donor_town="Tiny Town",
            coastal_map={},
            adjacency_map={},
        )
        self.assertTrue(score.disqualified)

    def test_no_ppsf_disqualified(self):
        from briarwood.town_transfer_engine import _score_town_pair
        subject = _town_context(town="Belmar")
        donor = _town_context(town="No Data", median_ppsf=None)
        score = _score_town_pair(
            subject=subject,
            donor=donor,
            subject_town="Belmar",
            donor_town="No Data",
            coastal_map={},
            adjacency_map={},
        )
        self.assertTrue(score.disqualified)

    def test_adequate_donor_not_disqualified(self):
        from briarwood.town_transfer_engine import _score_town_pair
        subject = _town_context(town="Belmar")
        donor = _town_context(
            town="Bradley Beach",
            median_ppsf=340.0,
            sample_size=15,
        )
        score = _score_town_pair(
            subject=subject,
            donor=donor,
            subject_town="Belmar",
            donor_town="Bradley Beach",
            coastal_map={"Belmar": 0.84, "Bradley Beach": 0.82},
            adjacency_map={"Belmar": "group_0", "Bradley Beach": "group_0"},
        )
        self.assertFalse(score.disqualified)
        self.assertGreater(score.similarity, 0.0)


class TestAdjacencyBonus(unittest.TestCase):
    """Adjacent towns get a similarity bonus."""

    def test_adjacent_towns_get_bonus(self):
        from briarwood.town_transfer_engine import _score_town_pair
        subject = _town_context(town="Belmar", town_ppsf_index=95.0)
        donor = _town_context(
            town="Bradley Beach",
            town_ppsf_index=92.0,
            median_ppsf=340.0,
        )
        # With adjacency
        score_adjacent = _score_town_pair(
            subject=subject,
            donor=donor,
            subject_town="Belmar",
            donor_town="Bradley Beach",
            coastal_map={},
            adjacency_map={"Belmar": "group_0", "Bradley Beach": "group_0"},
        )
        # Without adjacency
        score_non_adjacent = _score_town_pair(
            subject=subject,
            donor=donor,
            subject_town="Belmar",
            donor_town="Bradley Beach",
            coastal_map={},
            adjacency_map={},
        )
        self.assertGreater(score_adjacent.similarity, score_non_adjacent.similarity)
        self.assertTrue(score_adjacent.is_adjacent)
        self.assertFalse(score_non_adjacent.is_adjacent)

    def test_adjacency_bonus_magnitude(self):
        from briarwood.town_transfer_engine import _score_town_pair
        subject = _town_context(town="Belmar", town_ppsf_index=95.0)
        donor = _town_context(
            town="Bradley Beach",
            town_ppsf_index=92.0,
            median_ppsf=340.0,
        )
        score_adj = _score_town_pair(
            subject=subject,
            donor=donor,
            subject_town="Belmar",
            donor_town="Bradley Beach",
            coastal_map={},
            adjacency_map={"Belmar": "g", "Bradley Beach": "g"},
        )
        score_non = _score_town_pair(
            subject=subject,
            donor=donor,
            subject_town="Belmar",
            donor_town="Bradley Beach",
            coastal_map={},
            adjacency_map={},
        )
        delta = score_adj.similarity - score_non.similarity
        self.assertAlmostEqual(delta, _ADJACENCY_BONUS, places=2)


class TestHighDispersionPenalty(unittest.TestCase):
    """Donors with high dispersion get penalized."""

    def test_high_dispersion_lowers_similarity(self):
        from briarwood.town_transfer_engine import _score_town_pair
        subject = _town_context(town="Belmar")
        donor_clean = _town_context(
            town="Bradley Beach",
            median_ppsf=340.0,
            high_dispersion_flag=False,
        )
        donor_noisy = _town_context(
            town="Bradley Beach",
            median_ppsf=340.0,
            high_dispersion_flag=True,
        )
        score_clean = _score_town_pair(
            subject=subject, donor=donor_clean,
            subject_town="Belmar", donor_town="Bradley Beach",
            coastal_map={}, adjacency_map={},
        )
        score_noisy = _score_town_pair(
            subject=subject, donor=donor_noisy,
            subject_town="Belmar", donor_town="Bradley Beach",
            coastal_map={}, adjacency_map={},
        )
        self.assertGreater(score_clean.similarity, score_noisy.similarity)


class TestNoEligibleDonors(unittest.TestCase):
    """Engine should return used=False when no donors qualify."""

    def test_no_town_context(self):
        output = _base_comp_output(support_quality="thin")
        with patch("briarwood.town_transfer_engine.get_town_context", return_value=None):
            result = evaluate_town_transfer(
                property_input=_base_property(),
                comp_output=output,
                base_comp_selection=output.base_comp_selection,
            )
            self.assertFalse(result.used)
            self.assertIn("No town context", result.reason)

    def test_all_donors_disqualified(self):
        output = _base_comp_output(support_quality="thin")
        subject_ctx = _town_context(town="Belmar")

        def mock_get_context(town, **kwargs):
            if town == "Belmar":
                return subject_ctx
            return None

        with patch("briarwood.town_transfer_engine.get_town_context", side_effect=mock_get_context), \
             patch("briarwood.town_transfer_engine._find_donor_candidates") as mock_find:
            from briarwood.town_transfer_engine import TownPairScore
            mock_find.return_value = [
                TownPairScore(
                    donor_town="Tiny Town", similarity=0.0,
                    disqualified=True, disqualification_reason="Low sample",
                )
            ]
            result = evaluate_town_transfer(
                property_input=_base_property(),
                comp_output=output,
                base_comp_selection=output.base_comp_selection,
            )
            self.assertFalse(result.used)
            self.assertIn("disqualified", result.reason)

    def test_below_min_similarity(self):
        output = _base_comp_output(support_quality="thin")
        subject_ctx = _town_context(town="Belmar")

        def mock_get_context(town, **kwargs):
            if town == "Belmar":
                return subject_ctx
            return _town_context(town=town, median_ppsf=340.0)

        with patch("briarwood.town_transfer_engine.get_town_context", side_effect=mock_get_context), \
             patch("briarwood.town_transfer_engine._find_donor_candidates") as mock_find:
            from briarwood.town_transfer_engine import TownPairScore
            mock_find.return_value = [
                TownPairScore(donor_town="Far Town", similarity=0.20)
            ]
            result = evaluate_town_transfer(
                property_input=_base_property(),
                comp_output=output,
                base_comp_selection=output.base_comp_selection,
            )
            self.assertFalse(result.used)
            self.assertIn("below minimum", result.reason)


class TestTranslatedValue(unittest.TestCase):
    """Translated shell value and blending."""

    def test_translated_value_uses_sqft(self):
        """Translated shell = donor_ppsf * translation_factor * subject_sqft."""
        output = _base_comp_output(support_quality="thin", base_shell_value=450_000)
        subject_ctx = _town_context(town="Belmar", median_ppsf=350.0)
        donor_ctx = _town_context(
            town="Bradley Beach",
            median_ppsf=340.0,
            town_ppsf_index=92.0,
        )

        def mock_get_context(town, **kwargs):
            return {"Belmar": subject_ctx, "Bradley Beach": donor_ctx}.get(town)

        with patch("briarwood.town_transfer_engine.get_town_context", side_effect=mock_get_context), \
             patch("briarwood.town_transfer_engine._find_donor_candidates") as mock_find:
            from briarwood.town_transfer_engine import TownPairScore
            mock_find.return_value = [
                TownPairScore(donor_town="Bradley Beach", similarity=0.80, is_adjacent=True)
            ]
            result = evaluate_town_transfer(
                property_input=_base_property(sqft=1500),
                comp_output=output,
                base_comp_selection=output.base_comp_selection,
            )
            self.assertTrue(result.used)
            # translation_factor = 350/340 ≈ 1.0294
            # translated_shell = 340 * 1.0294 * 1500 = 350 * 1500 = 525000
            self.assertIsNotNone(result.translated_shell_value)
            self.assertAlmostEqual(result.translated_shell_value, 525_000.0, delta=100)

    def test_blended_value_combines_local_and_translated(self):
        """Blended value is weighted average of local base and translated."""
        output = _base_comp_output(support_quality="thin", base_shell_value=450_000)
        subject_ctx = _town_context(town="Belmar", median_ppsf=350.0)
        donor_ctx = _town_context(
            town="Bradley Beach",
            median_ppsf=340.0,
            town_ppsf_index=92.0,
        )

        def mock_get_context(town, **kwargs):
            return {"Belmar": subject_ctx, "Bradley Beach": donor_ctx}.get(town)

        with patch("briarwood.town_transfer_engine.get_town_context", side_effect=mock_get_context), \
             patch("briarwood.town_transfer_engine._find_donor_candidates") as mock_find:
            from briarwood.town_transfer_engine import TownPairScore
            mock_find.return_value = [
                TownPairScore(donor_town="Bradley Beach", similarity=0.80, is_adjacent=True)
            ]
            result = evaluate_town_transfer(
                property_input=_base_property(sqft=1500),
                comp_output=output,
                base_comp_selection=output.base_comp_selection,
            )
            self.assertTrue(result.used)
            self.assertIsNotNone(result.blended_value)
            self.assertIsNotNone(result.local_base_value)
            # Blended should be between local and translated
            self.assertGreater(result.blended_value, min(result.local_base_value, result.translated_shell_value))
            self.assertLess(result.blended_value, max(result.local_base_value, result.translated_shell_value))


class TestWarnings(unittest.TestCase):
    """Appropriate warnings should be generated."""

    def test_non_adjacent_warning(self):
        output = _base_comp_output(support_quality="thin")
        subject_ctx = _town_context(town="Belmar", median_ppsf=350.0)
        donor_ctx = _town_context(
            town="Far Town",
            median_ppsf=340.0,
            town_ppsf_index=92.0,
        )

        def mock_get_context(town, **kwargs):
            return {"Belmar": subject_ctx, "Far Town": donor_ctx}.get(town)

        with patch("briarwood.town_transfer_engine.get_town_context", side_effect=mock_get_context), \
             patch("briarwood.town_transfer_engine._find_donor_candidates") as mock_find:
            from briarwood.town_transfer_engine import TownPairScore
            mock_find.return_value = [
                TownPairScore(donor_town="Far Town", similarity=0.60, is_adjacent=False)
            ]
            result = evaluate_town_transfer(
                property_input=_base_property(),
                comp_output=output,
                base_comp_selection=output.base_comp_selection,
            )
            self.assertTrue(result.used)
            self.assertTrue(any("not in the same adjacency" in w for w in result.warnings))

    def test_large_translation_factor_warning(self):
        output = _base_comp_output(support_quality="thin")
        subject_ctx = _town_context(town="Belmar", median_ppsf=500.0)  # much higher
        donor_ctx = _town_context(
            town="Cheap Town",
            median_ppsf=200.0,
            town_ppsf_index=55.0,
        )

        def mock_get_context(town, **kwargs):
            return {"Belmar": subject_ctx, "Cheap Town": donor_ctx}.get(town)

        with patch("briarwood.town_transfer_engine.get_town_context", side_effect=mock_get_context), \
             patch("briarwood.town_transfer_engine._find_donor_candidates") as mock_find:
            from briarwood.town_transfer_engine import TownPairScore
            mock_find.return_value = [
                TownPairScore(donor_town="Cheap Town", similarity=0.50, is_adjacent=False)
            ]
            result = evaluate_town_transfer(
                property_input=_base_property(),
                comp_output=output,
                base_comp_selection=output.base_comp_selection,
            )
            self.assertTrue(result.used)
            self.assertTrue(any("Translation factor" in w for w in result.warnings))


class TestOutputShape(unittest.TestCase):
    """Output structure matches expected shape."""

    def test_inactive_result_shape(self):
        output = _base_comp_output(support_quality="strong")
        result = evaluate_town_transfer(
            property_input=_base_property(),
            comp_output=output,
            base_comp_selection=output.base_comp_selection,
        )
        self.assertFalse(result.used)
        self.assertIsNone(result.donor_town)
        self.assertIsNone(result.translation_factor)
        self.assertIsNone(result.translated_shell_value)
        self.assertEqual(result.method, "not_activated")
        self.assertEqual(result.confidence_penalty, 0.0)

    def test_active_result_has_all_fields(self):
        output = _base_comp_output(support_quality="thin")
        subject_ctx = _town_context(town="Belmar", median_ppsf=350.0)
        donor_ctx = _town_context(
            town="Bradley Beach",
            median_ppsf=340.0,
            town_ppsf_index=92.0,
        )

        def mock_get_context(town, **kwargs):
            return {"Belmar": subject_ctx, "Bradley Beach": donor_ctx}.get(town)

        with patch("briarwood.town_transfer_engine.get_town_context", side_effect=mock_get_context), \
             patch("briarwood.town_transfer_engine._find_donor_candidates") as mock_find:
            from briarwood.town_transfer_engine import TownPairScore
            mock_find.return_value = [
                TownPairScore(donor_town="Bradley Beach", similarity=0.80, is_adjacent=True)
            ]
            result = evaluate_town_transfer(
                property_input=_base_property(),
                comp_output=output,
                base_comp_selection=output.base_comp_selection,
            )
            self.assertTrue(result.used)
            self.assertIsNotNone(result.donor_town)
            self.assertIsNotNone(result.translation_factor)
            self.assertIsNotNone(result.translated_shell_value)
            self.assertIsNotNone(result.blended_value)
            self.assertIsNotNone(result.similarity_score)
            self.assertIsNotNone(result.transferred_confidence)
            self.assertIsNotNone(result.evidence)
            self.assertEqual(result.method, "ppsf_ratio_transfer")
            self.assertEqual(result.confidence_penalty, _CONFIDENCE_PENALTY)


if __name__ == "__main__":
    unittest.main()
