from __future__ import annotations

import unittest

from briarwood.dash_app.compare import build_compare_summary
from briarwood.dash_app.data import DEFAULT_PRESET_IDS, load_reports
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


if __name__ == "__main__":
    unittest.main()
