from __future__ import annotations

import unittest

from briarwood.modules.bull_base_bear import BullBaseBearModule
from briarwood.schemas import AnalysisReport, ModuleResult
from briarwood.dash_app.components import (
    render_compare_decision_mode,
    render_tear_sheet_body,
)
from briarwood.dash_app.compare import build_compare_summary
from briarwood.dash_app.data import DEFAULT_PRESET_IDS, load_reports
from briarwood.dash_app.scenarios import render_scenarios_section
from briarwood.dash_app.view_models import (
    build_evidence_rows,
    build_property_analysis_view,
    build_section_evidence_rows,
)


class DashViewModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.reports = load_reports(DEFAULT_PRESET_IDS)

    def test_property_analysis_view_has_core_metrics(self) -> None:
        report = self.reports["briarwood-rd-belmar"]
        view = build_property_analysis_view(report)
        self.assertEqual(view.address, report.address)
        self.assertIsNotNone(view.bcv)
        self.assertIsNotNone(view.base_case)
        self.assertTrue(view.metric_chips)
        self.assertTrue(view.comps.rows)
        self.assertTrue(view.comps.screening_summary)
        self.assertIn(view.evidence_mode, {"Listing Assisted", "Public Record", "Mls Connected"})
        self.assertGreaterEqual(len(view.comps.active_listing_rows), 1)
        self.assertIsNotNone(view.net_opportunity_delta_value)
        self.assertIsNotNone(view.all_in_basis)
        optionality = view.category_scores.get("optionality") if view.category_scores else None
        self.assertIsNotNone(optionality)
        self.assertGreater(len(optionality.sub_factors), 0)
        self.assertEqual(
            [item.key for item in view.evidence.confidence_components],
            ["rent", "capex", "market", "liquidity"],
        )
        self.assertTrue(view.evidence.assumption_statuses)
        self.assertTrue(any(item.key == "rent" for item in view.evidence.assumption_statuses))
        self.assertEqual(len(view.evidence.metric_statuses), 8)
        self.assertGreater(view.overall_confidence, 0)
        self.assertIn("town_context_confidence", view.compare_metrics)
        self.assertIn("subject_ppsf_vs_town", view.compare_metrics)
        self.assertIn("town_relative_opportunity_score", view.compare_metrics)
        self.assertIsNotNone(view.decision)
        assert view.decision is not None
        self.assertIn(view.decision.recommendation, {"Buy", "Neutral", "Avoid"})
        self.assertGreaterEqual(view.decision.conviction_score, 0)
        self.assertLessEqual(view.decision.conviction_score, 100)
        self.assertIn("positive", view.decision.decision_drivers)
        self.assertIn("negative", view.decision.decision_drivers)
        self.assertTrue(view.entry_basis_label)
        self.assertTrue(view.income_support_label)
        self.assertTrue(view.capex_load_label)
        self.assertTrue(view.liquidity_profile_label)
        self.assertTrue(view.optionality_label)
        self.assertTrue(view.risk_skew_label)
        self.assertIsNotNone(view.positioning_summary)
        self.assertTrue(view.decision.risk_statement.startswith("Risk stance:"))
        self.assertTrue(view.decision.summary_view.startswith("Positioning:"))
        self.assertIsNotNone(view.report_card)
        assert view.report_card is not None
        self.assertEqual(
            set(view.report_card.factor_scores.keys()),
            {"entry_basis", "income_support", "capex_load", "liquidity_profile", "optionality", "risk_skew"},
        )
        for value in view.report_card.factor_scores.values():
            self.assertGreaterEqual(value, -1.0)
            self.assertLessEqual(value, 1.0)
        self.assertLessEqual(len(view.report_card.positive), 3)
        self.assertLessEqual(len(view.report_card.negative), 3)
        total_abs = sum(abs(value) for value in view.report_card.factor_contributions.values())
        self.assertGreaterEqual(total_abs, 98)
        self.assertLessEqual(total_abs, 102)

    def test_compare_summary_explains_differences(self) -> None:
        views = [build_property_analysis_view(report) for report in self.reports.values()]
        summary = build_compare_summary(views)
        self.assertGreaterEqual(len(summary.rows), 5)
        self.assertTrue(summary.why_different)
        self.assertIsNotNone(summary.comparison_summary)
        assert summary.comparison_summary is not None
        self.assertTrue(summary.comparison_summary.winner)
        self.assertGreaterEqual(summary.comparison_summary.confidence, 0)
        self.assertLessEqual(summary.comparison_summary.confidence, 100)
        self.assertTrue(summary.comparison_summary.reasons_for_winner or summary.comparison_summary.strengths_of_loser)
        self.assertTrue(summary.comparison_summary.flip_condition)

    def test_evidence_rows_include_source_coverage(self) -> None:
        report = self.reports["briarwood-rd-belmar"]
        rows = build_evidence_rows(report)
        section_rows = build_section_evidence_rows(report)
        self.assertTrue(any(row["Category"] == "Address" for row in rows))
        self.assertTrue(any(row["Section"] == "Current Value" for row in section_rows))

    def test_scenarios_section_renders_forward_outlook_even_without_project_scenarios(self) -> None:
        report = self.reports["briarwood-rd-belmar"]
        section = render_scenarios_section(report)
        self.assertEqual(section.__class__.__name__, "Div")
        self.assertGreaterEqual(len(section.children), 1)

    def test_scenarios_section_surfaces_missing_scenario_reasons(self) -> None:
        property_input = self.reports["briarwood-rd-belmar"].property_input
        assert property_input is not None
        property_input = property_input.__class__(**property_input.to_dict())
        property_input.renovation_scenario = {"enabled": True, "renovation_budget": 5_000}
        property_input.teardown_scenario = {"enabled": True}
        bbb_result = BullBaseBearModule().run(property_input)
        report = AnalysisReport(
            property_id=property_input.property_id,
            address=property_input.address,
            property_input=property_input,
            module_results={
                "bull_base_bear": bbb_result,
                "current_value": self.reports["briarwood-rd-belmar"].module_results["current_value"],
                "market_value_history": self.reports["briarwood-rd-belmar"].module_results["market_value_history"],
                "renovation_scenario": ModuleResult(
                    module_name="renovation_scenario",
                    metrics={"enabled": False, "status": "missing_inputs"},
                    summary="Renovation budget $5,000 is below the minimum modeled threshold of $10,000.",
                    payload={
                        "enabled": False,
                        "status": "missing_inputs",
                        "summary": "Renovation budget $5,000 is below the minimum modeled threshold of $10,000.",
                        "missing_inputs": ["renovation_budget"],
                        "warnings": [],
                    },
                ),
                "teardown_scenario": ModuleResult(
                    module_name="teardown_scenario",
                    metrics={"enabled": False, "status": "missing_inputs"},
                    summary="Knockdown / new-build scenario needs both a construction budget and a target new-build size before Briarwood can model project economics.",
                    payload={
                        "enabled": False,
                        "status": "missing_inputs",
                        "summary": "Knockdown / new-build scenario needs both a construction budget and a target new-build size before Briarwood can model project economics.",
                        "missing_inputs": ["new_construction_cost", "new_construction_sqft"],
                        "warnings": [],
                    },
                ),
            },
        )

        section = render_scenarios_section(report)
        text = _flatten_text(section)
        self.assertIn("Renovation Scenario", text)
        self.assertIn("Knockdown / New-Build Scenario", text)
        self.assertIn("Missing inputs:", text)
        self.assertIn("renovation budget", text)
        self.assertIn("new construction cost", text)

    def test_tear_sheet_body_surfaces_current_competition_block(self) -> None:
        report = self.reports["briarwood-rd-belmar"]
        view = build_property_analysis_view(report)
        body = render_tear_sheet_body(view, report)
        text = _flatten_text(body)
        # The top-level Tear Sheet structure now uses a presentation toggle and sub-tabs.
        self.assertIn("Presentation", text)
        # Summary content remains visible in the default overview.
        self.assertIn("/ 5", text)
        self.assertTrue("DECISION SUMMARY" in text or "DECISION MEMO" in text)
        self.assertIn("Score Report Card", text)
        self.assertIn("ASSUMPTION SUMMARY", text)
        self.assertTrue("Current Value Snapshot" in text or "Section A - Value Snapshot" in text)
        self.assertIn("Option 1 Buy As-Is", text)
        self.assertIn("Option 2 Buy + Renovate", text)
        self.assertIn("Town Pulse", text)
        self.assertIn("Scenario View", text)
        self.assertIn("Risk & Constraints", text)
        # Deep-dive content still present
        self.assertIn("Is the Price Right?", text)
        self.assertIn("What Does It Cost to Own?", text)
        self.assertIn("What Could Break the Thesis?", text)
        self.assertIn("Current Competition", text)
        self.assertIn("Confidence Drivers", text)
        self.assertIn("Metric Basis & Gaps", text)

    def test_tear_sheet_body_can_filter_town_pulse_rows(self) -> None:
        report = self.reports["briarwood-rd-belmar"]
        view = build_property_analysis_view(report)
        body = render_tear_sheet_body(view, report, town_pulse_filter="bearish")
        text = _flatten_text(body)
        self.assertIn("500 River Road residential project with 12 units was denied", text)
        self.assertNotIn("1201 Main Street mixed-use redevelopment with 24 residential units was approved", text)

    def test_compare_decision_mode_renders_heatmap_view(self) -> None:
        reports = list(self.reports.values())
        views = [build_property_analysis_view(report) for report in reports]
        summary = build_compare_summary(views)
        section = render_compare_decision_mode("heatmap", views, reports, summary, "overview")
        self.assertIn("Score Heatmap", _flatten_text(section))
        self.assertIn("Compare Decision Read", _flatten_text(section))
        self.assertIn("Why One Property Wins", _flatten_text(section))


def _flatten_text(node: object) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    children = getattr(node, "children", None)
    if isinstance(children, (list, tuple)):
        return " ".join(_flatten_text(child) for child in children)
    return _flatten_text(children)


if __name__ == "__main__":
    unittest.main()
