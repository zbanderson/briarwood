from __future__ import annotations

import unittest

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

    def test_compare_summary_explains_differences(self) -> None:
        views = [build_property_analysis_view(report) for report in self.reports.values()]
        summary = build_compare_summary(views)
        self.assertGreaterEqual(len(summary.rows), 5)
        self.assertTrue(summary.why_different)

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

    def test_tear_sheet_body_surfaces_current_competition_block(self) -> None:
        report = self.reports["briarwood-rd-belmar"]
        view = build_property_analysis_view(report)
        body = render_tear_sheet_body(view, report)
        text = _flatten_text(body)
        # The top-level Tear Sheet structure now uses a presentation toggle and sub-tabs.
        self.assertIn("Presentation", text)
        # Summary content remains visible in the default overview.
        self.assertIn("/ 5", text)
        self.assertIn("DECISION SUMMARY", text)
        self.assertIn("ASSUMPTION SUMMARY", text)
        self.assertIn("Current Value Snapshot", text)
        self.assertIn("Option 1 Buy As-Is", text)
        self.assertIn("Option 2 Buy + Renovate", text)
        # Deep-dive content still present
        self.assertIn("Is the Price Right?", text)
        self.assertIn("What Does It Cost to Own?", text)
        self.assertIn("What Could Break the Thesis?", text)
        self.assertIn("Current Competition", text)
        self.assertIn("Confidence Drivers", text)
        self.assertIn("Metric Basis & Gaps", text)

    def test_compare_decision_mode_renders_heatmap_view(self) -> None:
        reports = list(self.reports.values())
        views = [build_property_analysis_view(report) for report in reports]
        summary = build_compare_summary(views)
        section = render_compare_decision_mode("heatmap", views, reports, summary, "overview")
        self.assertIn("Score Heatmap", _flatten_text(section))
        self.assertIn("Compare Decision Read", _flatten_text(section))


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
