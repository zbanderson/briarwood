from __future__ import annotations

import unittest

from briarwood.evidence import compute_critical_assumption_statuses, compute_metric_input_statuses, has_known_optionality_detail
from briarwood.schemas import (
    AnalysisReport,
    InputCoverageStatus,
    ModuleResult,
    PropertyInput,
    SourceCoverageItem,
    SourceMetadata,
    UserAssumptions,
)


class RecommendationAndRefreshTests(unittest.TestCase):
    def test_explicit_negative_optionality_inputs_do_not_stay_missing(self) -> None:
        property_input = PropertyInput(
            property_id="optionality-known-no",
            address="1 Main St",
            town="Belmar",
            state="NJ",
            beds=3,
            baths=2.0,
            sqft=1400,
            lot_size=3200.0,
            property_type="Single Family Residence",
            has_back_house=False,
            has_basement=False,
            garage_spaces=0,
        )
        report = AnalysisReport(
            property_id=property_input.property_id,
            address=property_input.address,
            property_input=property_input,
            module_results={
                "comparable_sales": ModuleResult(module_name="comparable_sales", metrics={"comp_count": 0}),
            },
        )

        status = next(item for item in compute_metric_input_statuses(report) if item.key == "optionality")

        self.assertTrue(has_known_optionality_detail(property_input))
        self.assertNotIn("ADU/basement/garage detail", status.missing_inputs)

    def test_manual_payload_reanalysis_marks_condition_and_capex_as_confirmed(self) -> None:
        property_input = PropertyInput(
            property_id="manual-refresh",
            address="2 Main St",
            town="Belmar",
            state="NJ",
            beds=3,
            baths=2.0,
            sqft=1500,
            purchase_price=725000,
            condition_profile="updated",
            capex_lane="light",
            condition_confirmed=True,
            capex_confirmed=True,
            user_assumptions=UserAssumptions(
                condition_profile_override="updated",
                condition_confirmed=True,
                capex_lane_override="light",
                capex_confirmed=True,
            ),
            source_metadata=SourceMetadata(
                evidence_mode="public_record",
                provenance=["manual_subject_entry"],
                source_coverage={
                    "condition_assumption": SourceCoverageItem(
                        category="condition_assumption",
                        status=InputCoverageStatus.USER_SUPPLIED,
                        source_name="manual entry",
                    ),
                    "capex_assumption": SourceCoverageItem(
                        category="capex_assumption",
                        status=InputCoverageStatus.USER_SUPPLIED,
                        source_name="manual entry",
                    ),
                },
            ),
        )

        report = AnalysisReport(
            property_id=property_input.property_id,
            address=property_input.address,
            property_input=property_input,
            module_results={
                "income_support": ModuleResult(module_name="income_support", metrics={"rent_source_type": "missing"}),
            },
        )
        statuses = {item.key: item for item in compute_critical_assumption_statuses(report)}

        self.assertEqual(statuses["condition_profile"].status, "confirmed")
        self.assertEqual(statuses["capex"].status, "confirmed")
        self.assertEqual(property_input.coverage_for("condition_assumption").status.value, "user_supplied")
        self.assertEqual(property_input.coverage_for("capex_assumption").status.value, "user_supplied")


if __name__ == "__main__":
    unittest.main()
