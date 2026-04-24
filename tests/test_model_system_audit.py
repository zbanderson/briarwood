from __future__ import annotations

import unittest

from briarwood.eval.model_system_audit import (
    BRIDGE_ROWS,
    SAMPLE_PROPERTIES,
    SAMPLE_PROMPTS,
    UI_SURFACE_ROWS,
    run_model_system_audit,
)


class ModelSystemAuditTests(unittest.TestCase):
    def test_report_contains_expected_sections(self) -> None:
        report = run_model_system_audit()

        self.assertIn("metadata", report)
        self.assertIn("rows", report)
        self.assertIn("forwarding_matrix", report)
        self.assertIn("coherence_table", report)
        self.assertIn("sample_case_results", report)
        self.assertIn("aggregate_summaries", report)
        self.assertIn("top_priority_fixes", report)

    def test_every_scoped_module_appears_once(self) -> None:
        report = run_model_system_audit()
        module_rows = [row for row in report["rows"] if row["row_type"] == "module"]
        names = [row["name"] for row in module_rows]

        expected = {
            "valuation",
            "carry_cost",
            "risk_model",
            "confidence",
            "resale_scenario",
            "rental_option",
            "rent_stabilization",
            "hold_to_rent",
            "renovation_impact",
            "arv_model",
            "margin_sensitivity",
            "unit_income_offset",
            "legal_confidence",
            "town_development_index",
            "opportunity_cost",
            "strategy_classifier",
            "market_value_history",
            "current_value",
            "income_support",
            "scarcity_support",
            "location_intelligence",
            "comparable_sales",
            "hybrid_value",
        }
        self.assertEqual(set(names), expected)
        self.assertEqual(len(names), len(expected))

    def test_every_bridge_appears_once(self) -> None:
        report = run_model_system_audit()
        bridge_rows = [row for row in report["rows"] if row["row_type"] == "bridge"]
        names = [row["name"] for row in bridge_rows]

        expected = {row["name"] for row in BRIDGE_ROWS}
        self.assertEqual(set(names), expected)
        self.assertEqual(len(names), len(expected))

    def test_unified_and_ui_surfaces_appear(self) -> None:
        report = run_model_system_audit()
        names = {row["name"] for row in report["rows"]}

        self.assertIn("unified_intelligence", names)
        for row in UI_SURFACE_ROWS:
            self.assertIn(row["name"], names)

    def test_every_row_has_evidence(self) -> None:
        report = run_model_system_audit()
        for row in report["rows"]:
            self.assertTrue(row["evidence"], f"missing evidence for {row['name']}")

    def test_forwarding_matrix_covers_required_events(self) -> None:
        report = run_model_system_audit()
        events = {row["sse_event"] for row in report["forwarding_matrix"]}
        required = {
            "verdict",
            "town_summary",
            "comps_preview",
            "value_thesis",
            "risk_profile",
            "strategy_path",
            "rent_outlook",
            "scenario_table",
            "chart",
            "modules_ran",
        }
        self.assertTrue(required <= events)

    def test_sample_cases_cover_properties_and_prompts(self) -> None:
        report = run_model_system_audit()
        rows = report["sample_case_results"]
        self.assertEqual(len(rows), len(SAMPLE_PROPERTIES) * len(SAMPLE_PROMPTS))
        statuses = {row["status"] for row in rows}
        self.assertTrue(statuses <= {"pass", "partial", "fail"})

    def test_declared_but_unused_dependencies_are_capped(self) -> None:
        report = run_model_system_audit()
        capped = {
            row["name"]: row["unified_relativity_score"]
            for row in report["rows"]
            if row["name"] in {"risk_model", "rental_option", "resale_scenario", "confidence"}
        }
        self.assertTrue(all(score <= 60 for score in capped.values()))

    def test_rows_without_user_surface_stay_low_on_forward_score(self) -> None:
        report = run_model_system_audit()
        for row in report["rows"]:
            if row["row_type"] != "module":
                continue
            if row["user_surface_targets"]:
                continue
            self.assertLessEqual(row["forward_to_user_score"], 40, row["name"])


if __name__ == "__main__":
    unittest.main()
