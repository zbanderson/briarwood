from __future__ import annotations

import unittest

from briarwood.data_quality.eligibility import classify_comp_eligibility
from briarwood.data_quality.provenance import FieldEvidence, PropertyEvidenceProfile


def _evidence(field_name: str, value, status: str) -> FieldEvidence:
    return FieldEvidence(
        field_name=field_name,
        chosen_value=value,
        chosen_source="test",
        chosen_source_tier=1,
        chosen_status=status,
        arbitration_reason="test",
        updated_at="2026-04-10T00:00:00Z",
        candidates=[],
    )


class CompEligibilityTests(unittest.TestCase):
    def test_eligible_when_identity_and_structural_core_are_clean(self) -> None:
        profile = PropertyEvidenceProfile(
            identity_fields={
                "address": _evidence("address", "1223 Briarwood Rd", "confirmed"),
                "town": _evidence("town", "Belmar", "confirmed"),
                "state": _evidence("state", "NJ", "confirmed"),
            },
            structural_fields={
                "beds": _evidence("beds", 4, "confirmed"),
                "baths": _evidence("baths", 2.5, "confirmed"),
                "sqft": _evidence("sqft", 2180, "confirmed"),
                "property_type": _evidence("property_type", "single_family", "confirmed"),
            },
        )
        result = classify_comp_eligibility(profile)
        self.assertEqual(result.status, "eligible")

    def test_market_only_when_structural_profile_is_thin(self) -> None:
        profile = PropertyEvidenceProfile(
            identity_fields={
                "address": _evidence("address", "1223 Briarwood Rd", "confirmed"),
                "town": _evidence("town", "Belmar", "confirmed"),
                "state": _evidence("state", "NJ", "confirmed"),
            },
            structural_fields={
                "beds": _evidence("beds", None, "missing"),
                "baths": _evidence("baths", 2.0, "confirmed"),
                "sqft": _evidence("sqft", None, "missing"),
                "property_type": _evidence("property_type", "single_family", "confirmed"),
            },
        )
        result = classify_comp_eligibility(profile)
        self.assertEqual(result.status, "market_only")

    def test_rejected_when_identity_conflict_is_fatal(self) -> None:
        profile = PropertyEvidenceProfile(
            identity_fields={
                "address": _evidence("address", "1223 Briarwood Rd", "confirmed"),
                "town": _evidence("town", "Belmar", "needs_review"),
                "state": _evidence("state", "NJ", "confirmed"),
            },
            structural_fields={
                "beds": _evidence("beds", 4, "confirmed"),
                "baths": _evidence("baths", 2.5, "confirmed"),
                "sqft": _evidence("sqft", 2180, "confirmed"),
                "property_type": _evidence("property_type", "single_family", "confirmed"),
            },
        )
        result = classify_comp_eligibility(profile)
        self.assertEqual(result.status, "rejected")
