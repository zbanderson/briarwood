from __future__ import annotations

import unittest

from briarwood.data_quality.arbitration import apply_evidence_profile, build_property_evidence_profile, choose_field_value
from briarwood.data_quality.pipeline import DataQualityPipeline
from briarwood.data_quality.provenance import FieldCandidate
from briarwood.schemas import CanonicalPropertyData, EvidenceMode, PropertyFacts, SourceMetadata, UserAssumptions


class DataQualityPipelineTests(unittest.TestCase):
    def test_single_source_field_selection(self) -> None:
        evidence = choose_field_value(
            "sqft",
            [FieldCandidate(field_name="sqft", value=2050, source="attom", source_tier=2)],
        )
        self.assertEqual(evidence.chosen_value, 2050)
        self.assertEqual(evidence.chosen_status, "confirmed")

    def test_multi_source_arbitration_prefers_sale_policy(self) -> None:
        evidence = choose_field_value(
            "last_sale_price",
            [
                FieldCandidate(field_name="last_sale_price", value=905000, source="attom sale detail", source_tier=2),
                FieldCandidate(field_name="last_sale_price", value=910000, source="sr1a", source_tier=1),
            ],
        )
        self.assertEqual(evidence.chosen_source, "sr1a")
        self.assertEqual(evidence.chosen_value, 910000)
        self.assertEqual(evidence.chosen_status, "confirmed_with_conflict")

    def test_user_override_precedence(self) -> None:
        evidence = choose_field_value(
            "beds",
            [
                FieldCandidate(field_name="beds", value=4, source="attom", source_tier=2),
                FieldCandidate(field_name="beds", value=5, source="manual override", source_tier=1, is_user_override=True),
            ],
        )
        self.assertEqual(evidence.chosen_source, "manual override")
        self.assertEqual(evidence.chosen_value, 5)

    def test_conflict_detection_for_sqft(self) -> None:
        evidence = choose_field_value(
            "sqft",
            [
                FieldCandidate(field_name="sqft", value=2000, source="modiv", source_tier=1),
                FieldCandidate(field_name="sqft", value=2450, source="attom", source_tier=2),
            ],
        )
        self.assertEqual(evidence.chosen_status, "confirmed_with_conflict")

    def test_tax_field_precedence_prefers_user_confirmed_bill(self) -> None:
        evidence = choose_field_value(
            "tax_amount",
            [
                FieldCandidate(field_name="tax_amount", value=13200, source="attom assessment", source_tier=2),
                FieldCandidate(field_name="tax_amount", value=12980, source="user confirmed tax bill", source_tier=1),
            ],
        )
        self.assertEqual(evidence.chosen_source, "user confirmed tax bill")
        self.assertEqual(evidence.chosen_value, 12980)

    def test_record_validation_rejects_bad_address_and_wrong_state(self) -> None:
        pipeline = DataQualityPipeline(expected_state="NJ")
        result = pipeline.run(
            {
                "address": "Beautiful beachside opportunity with marina views and endless charm",
                "town": "Belmar",
                "state": "NY",
                "sale_price": None,
                "sale_date": None,
            },
            record_type="sale",
        )
        codes = {issue.code for issue in result.issues}
        self.assertEqual(result.status, "rejected")
        self.assertIn("listing_description_as_address", codes)
        self.assertIn("wrong_state", codes)
        self.assertIn("missing_sale_price", codes)
        self.assertIn("missing_sale_date", codes)

    def test_town_mismatch_handling_needs_review(self) -> None:
        pipeline = DataQualityPipeline(expected_state="NJ")
        result = pipeline.run(
            {
                "address": "1223 Briarwood Rd",
                "town": "Spring Lake",
                "state": "NJ",
                "sale_price": 900000,
                "sale_date": "2025-01-01",
            },
            field_candidates={
                "town": [
                    FieldCandidate(field_name="town", value="Spring Lake", source="listing text", source_tier=3),
                    FieldCandidate(field_name="town", value="Belmar", source="public record", source_tier=1),
                ]
            },
            record_type="sale",
        )
        self.assertEqual(result.status, "needs_review")
        self.assertEqual(result.evidence_profile.summary_flags["identity_match_status"], "needs_review")

    def test_build_property_evidence_profile_sets_comp_eligibility(self) -> None:
        canonical = CanonicalPropertyData(
            property_id="subject-1",
            facts=PropertyFacts(
                address="1223 Briarwood Rd",
                town="Belmar",
                state="NJ",
                beds=4,
                baths=2.5,
                sqft=2180,
                property_type="single_family",
                purchase_price=910000,
                taxes=12850,
            ),
            user_assumptions=UserAssumptions(estimated_monthly_rent=3400),
            source_metadata=SourceMetadata(evidence_mode=EvidenceMode.PUBLIC_RECORD),
        )
        profile = build_property_evidence_profile(
            canonical,
            {
                "sr1a": {"last_sale_price": 910000, "last_sale_date": "2025-03-11"},
                "attom_assessment": {"tax_amount": 12850, "tax_year": "2025"},
            },
        )
        self.assertEqual(profile.summary_flags["identity_match_status"], "confirmed")
        self.assertEqual(profile.summary_flags["comp_eligibility_status"], "accepted")
        updated = apply_evidence_profile(canonical, {"sr1a": {"last_sale_price": 910000}})
        self.assertIsNotNone(updated.source_metadata.property_evidence_profile)
