import unittest

from briarwood.agents.town_county.cli import build_file_backed_service, format_outlook
from briarwood.agents.town_county.sources import TownCountyOutlookRequest


class TownCountyCliTests(unittest.TestCase):
    def test_format_outlook_returns_readable_summary(self) -> None:
        service = build_file_backed_service()
        result = service.build_outlook(
            TownCountyOutlookRequest(
                town="Belmar",
                state="NJ",
                county="Monmouth",
                school_signal=8.1,
                scarcity_signal=0.7,
                days_on_market=19,
                price_position="supported",
            )
        )

        output = format_outlook(result)

        self.assertIn("Briarwood Town/County Outlook", output)
        self.assertIn("location_thesis_label: supportive", output)
        self.assertIn("summary:", output)
        self.assertIn("demand_drivers:", output)


if __name__ == "__main__":
    unittest.main()
