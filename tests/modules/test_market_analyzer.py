from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from briarwood.local_intelligence.storage import JsonLocalSignalStore
from briarwood.modules.market_analyzer import MarketAnalyzer


class MarketAnalyzerTests(unittest.TestCase):
    def test_market_analyzer_ranks_towns_and_builds_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            active_path = root / "active.json"
            sales_path = root / "sales.json"
            rent_path = root / "rent.json"
            signals_root = root / "signals"
            signals_root.mkdir()

            active_path.write_text(json.dumps({
                "listings": [
                    {
                        "address": "1 Ocean Ave",
                        "town": "Alpha",
                        "state": "NJ",
                        "list_price": 500000,
                        "listing_status": "for_sale",
                        "property_type": "Duplex",
                        "days_on_market": 18,
                        "sqft": 1000,
                        "source_notes": "Walk to the beach and strong summer rental appeal.",
                    },
                    {
                        "address": "2 Main St",
                        "town": "Alpha",
                        "state": "NJ",
                        "list_price": 520000,
                        "listing_status": "for_sale",
                        "property_type": "Single Family",
                        "days_on_market": 20,
                        "sqft": 1040,
                    },
                    {
                        "address": "10 Hill Rd",
                        "town": "Beta",
                        "state": "NJ",
                        "list_price": 700000,
                        "listing_status": "for_sale",
                        "property_type": "Single Family",
                        "days_on_market": 55,
                        "sqft": 1000,
                    },
                    {
                        "address": "11 Hill Rd",
                        "town": "Beta",
                        "state": "NJ",
                        "list_price": 710000,
                        "listing_status": "for_sale",
                        "property_type": "Single Family",
                        "days_on_market": 60,
                        "sqft": 1000,
                    },
                ]
            }, indent=2))
            sales_path.write_text(json.dumps({
                "sales": [
                    {
                        "address": "3 Ocean Ave",
                        "town": "Alpha",
                        "state": "NJ",
                        "property_type": "Duplex",
                        "sale_price": 480000,
                        "sale_date": "2026-01-15",
                        "sqft": 1000,
                    },
                    {
                        "address": "4 Ocean Ave",
                        "town": "Alpha",
                        "state": "NJ",
                        "property_type": "Single Family",
                        "sale_price": 470000,
                        "sale_date": "2026-02-15",
                        "sqft": 950,
                    },
                    {
                        "address": "12 Hill Rd",
                        "town": "Beta",
                        "state": "NJ",
                        "property_type": "Single Family",
                        "sale_price": 690000,
                        "sale_date": "2026-01-12",
                        "sqft": 1000,
                    },
                ]
            }, indent=2))
            rent_path.write_text(json.dumps({
                "towns": [
                    {"geography_name": "Alpha", "state": "NJ", "zori_current": 3200},
                    {"geography_name": "Beta", "state": "NJ", "zori_current": 2600},
                ],
                "counties": [],
            }, indent=2))
            (signals_root / "alpha-nj.json").write_text(json.dumps({
                "town": "Alpha",
                "state": "NJ",
                "signals": [
                    {
                        "id": "sig-alpha-1",
                        "town": "Alpha",
                        "state": "NJ",
                        "signal_type": "amenity",
                        "title": "Boardwalk district streetscape plan approved",
                        "canonical_key": None,
                        "source_document_id": "doc-alpha-1",
                        "source_type": "planning_board_minutes",
                        "source_date": "2026-02-10T00:00:00Z",
                        "source_url": None,
                        "status": "approved",
                        "time_horizon": "near_term",
                        "impact_direction": "positive",
                        "impact_magnitude": 4,
                        "confidence": 0.9,
                        "facts": ["Approved amenity investment near downtown."],
                        "inference": "Improves visit frequency and rental positioning.",
                        "affected_dimensions": ["amenity_trajectory"],
                        "evidence_excerpt": "Streetscape and boardwalk improvements were approved.",
                        "created_at": "2026-02-10T00:00:00Z",
                        "updated_at": "2026-02-10T00:00:00Z",
                        "first_seen_at": "2026-02-10T00:00:00Z",
                        "last_seen_at": "2026-02-10T00:00:00Z",
                        "last_transition_at": None,
                        "occurrence_count": 1,
                        "reconciliation_status": "new",
                        "previous_status": None,
                        "metadata": {"location": "Boardwalk", "units": 0},
                    }
                ],
            }, indent=2))

            analyzer = MarketAnalyzer(
                active_path=active_path,
                sales_path=sales_path,
                rent_context_path=rent_path,
                local_signal_store=JsonLocalSignalStore(signals_root),
            )
            outputs = analyzer.analyze()

        self.assertEqual([item.town for item in outputs], ["Alpha", "Beta"])
        self.assertGreater(outputs[0].market_score, outputs[1].market_score)
        self.assertGreater(outputs[0].valuation_score, outputs[1].valuation_score)
        self.assertGreater(outputs[0].investability_score, outputs[1].investability_score)
        self.assertGreater(outputs[0].catalyst_score, outputs[1].catalyst_score)
        self.assertIn("sell_through_rate", outputs[0].metrics)
        self.assertIn("price_to_rent_ratio", outputs[0].metrics)
        self.assertIn("Alpha", outputs[0].narrative)
        self.assertGreaterEqual(outputs[0].metrics["confirmed_catalysts"], 1)
