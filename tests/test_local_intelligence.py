import unittest

from briarwood.modules.local_intelligence import LocalIntelligenceModule
from briarwood.schemas import PropertyInput


def sample_property() -> PropertyInput:
    return PropertyInput(
        property_id="local-1",
        address="1 Main St",
        town="Belmar",
        state="NJ",
        county="Monmouth",
        beds=3,
        baths=2.0,
        sqft=1500,
        purchase_price=700000,
        town_population=5600,
        local_documents=[
            {
                "meeting_date": "2026-02-11",
                "document_type": "planning board minutes",
                "text": (
                    "Application for 1201 Main Street mixed-use redevelopment with 24 residential units was approved. "
                    "Board members found the project consistent with the master plan."
                ),
            },
            {
                "meeting_date": "2026-02-25",
                "document_type": "zoning board minutes",
                "text": (
                    "The proposal for 500 River Road residential project with 12 units was denied after traffic concern and parking issue were discussed."
                ),
            },
        ],
    )


class LocalIntelligenceTests(unittest.TestCase):
    def test_local_intelligence_extracts_projects_and_scores(self) -> None:
        result = LocalIntelligenceModule().run(sample_property())

        self.assertEqual(result.metrics["total_projects"], 2)
        self.assertEqual(result.metrics["total_units"], 36)
        self.assertGreater(result.metrics["development_activity_score"], 0)
        self.assertGreater(result.metrics["regulatory_trend_score"], 0)
        self.assertGreater(result.confidence, 0.4)
        self.assertTrue(result.payload.projects)
        self.assertTrue(any(project.status == "approved" for project in result.payload.projects))
        self.assertTrue(any("pipeline" in bullet.lower() or "approval" in bullet.lower() for bullet in result.payload.narrative))

    def test_local_intelligence_handles_missing_documents(self) -> None:
        property_input = sample_property()
        property_input.local_documents = []

        result = LocalIntelligenceModule().run(property_input)

        self.assertEqual(result.metrics["total_projects"], 0)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("unavailable", result.summary.lower())


if __name__ == "__main__":
    unittest.main()
