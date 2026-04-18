import unittest

from briarwood.agent.tools import CMAResult, ComparableProperty, PropertyBrief, RentOutlook, TownMarketRead
from briarwood.pipeline.presentation import build_property_presentation


class PresentationPayloadTests(unittest.TestCase):
    def test_build_property_presentation_returns_cards_tables_and_charts(self) -> None:
        brief = PropertyBrief(
            property_id="1600-l-street-belmar-nj-07719",
            address="1600 L Street, Belmar, NJ 07719",
            town="Belmar",
            state="NJ",
            beds=3,
            baths=2.0,
            ask_price=899000.0,
            pricing_view="above_fair_value",
            analysis_depth_used="snapshot",
            recommendation="Buy if price improves.",
            decision="buy_if_price_improves",
            decision_stance="buy_if_price_improves",
            best_path="Make an offer inside the risk-adjusted band rather than at ask.",
            key_value_drivers=["shore-adjacent scarcity"],
            key_risks=["thin carry support"],
            trust_flags=["weak_town_context"],
            recommended_next_run="decision",
            next_questions=["should I buy this at the current ask?"],
            primary_value_source="current_value",
            fair_value_base=804396.0,
            ask_premium_pct=0.105,
        )
        enrichment = {
            "property_id": "1600-l-street-belmar-nj-07719",
            "listing_source": {"source_url": "https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/"},
            "source_coverage": {"address": "sourced", "sqft": "missing"},
            "attom": {
                "sale_history_snapshot": {
                    "sale_history": [
                        {"sale_date": "2024-03-01", "sale_price": 780000, "sale_type": "arms_length"}
                    ]
                }
            },
            "google": {
                "geocode": {"county": "Monmouth"},
                "nearby_places": {"type_counts": {"school": 1, "park": 1}},
                "street_view_image_url": "https://maps.googleapis.com/maps/api/streetview?...",
            },
            "town_intelligence": {"summary": {"market_direction": "constructive"}},
            "warnings": [],
        }
        risk = {"trust_flags": ["weak_town_context"]}

        payload = build_property_presentation(
            "1600-l-street-belmar-nj-07719",
            brief=brief,
            enrichment=enrichment,
            risk=risk,
            contract_type="property_brief",
            analysis_mode="browse",
        )

        self.assertEqual(payload.property_id, "1600-l-street-belmar-nj-07719")
        self.assertEqual(payload.contract_type, "property_brief")
        self.assertGreaterEqual(len(payload.cards), 3)
        self.assertTrue(any(card.key == "purchase_brief" for card in payload.cards))
        self.assertTrue(any(table.key == "sale_history" for table in payload.tables))
        self.assertTrue(any(chart.kind == "verdict_gauge" for chart in payload.charts))
        self.assertTrue(any(chart.kind == "risk_bar" for chart in payload.charts))

    def test_build_property_presentation_omits_risk_chart_when_not_provided(self) -> None:
        brief = PropertyBrief(
            property_id="1600-l-street-belmar-nj-07719",
            address="1600 L Street, Belmar, NJ 07719",
            town="Belmar",
            state="NJ",
            beds=3,
            baths=2.0,
            ask_price=899000.0,
            pricing_view="above_fair_value",
            analysis_depth_used="snapshot",
            recommendation="Buy if price improves.",
            decision="buy_if_price_improves",
            decision_stance="buy_if_price_improves",
            best_path=None,
            key_value_drivers=[],
            key_risks=[],
            trust_flags=[],
            recommended_next_run=None,
            next_questions=[],
            primary_value_source="current_value",
            fair_value_base=None,
            ask_premium_pct=None,
        )

        payload = build_property_presentation(
            "1600-l-street-belmar-nj-07719",
            brief=brief,
            enrichment={},
            risk=None,
        )

        self.assertFalse(any(chart.kind == "risk_bar" for chart in payload.charts))

    def test_build_property_presentation_adds_contract_specific_sections(self) -> None:
        brief = PropertyBrief(
            property_id="1600-l-street-belmar-nj-07719",
            address="1600 L Street, Belmar, NJ 07719",
            town="Belmar",
            state="NJ",
            beds=3,
            baths=2.0,
            ask_price=899000.0,
            pricing_view="above_fair_value",
            analysis_depth_used="snapshot",
            recommendation="Buy if price improves.",
            decision="buy_if_price_improves",
            decision_stance="buy_if_price_improves",
            best_path=None,
            key_value_drivers=[],
            key_risks=[],
            trust_flags=[],
            recommended_next_run=None,
            next_questions=[],
            primary_value_source="current_value",
            fair_value_base=804396.0,
            ask_premium_pct=0.105,
        )
        cma = CMAResult(
            property_id="1600-l-street-belmar-nj-07719",
            address="1600 L Street, Belmar, NJ 07719",
            town="Belmar",
            state="NJ",
            ask_price=899000.0,
            fair_value_base=804396.0,
            value_low=760000.0,
            value_high=860000.0,
            pricing_view="above_fair_value",
            primary_value_source="current_value",
            comp_selection_summary="Same-town saved comps, filtered by bedroom count.",
            comps=[
                ComparableProperty(
                    property_id="1302-l-street",
                    address="1302 L Street, Belmar, NJ 07719",
                    town="Belmar",
                    state="NJ",
                    beds=3,
                    baths=2.0,
                    ask_price=850000.0,
                    blocks_to_beach=18.9,
                    selection_rationale="same town and bedroom count",
                )
            ],
            confidence_notes=[],
            missing_fields=[],
        )
        rent_outlook = RentOutlook(
            property_id="1600-l-street-belmar-nj-07719",
            address="1600 L Street, Belmar, NJ 07719",
            current_monthly_rent=3500.0,
            effective_monthly_rent=3300.0,
            annual_noi=22000.0,
            rent_source_type="estimated",
            rental_ease_label="moderate",
            rental_ease_score=61.0,
            horizon_years=2,
            future_rent_low=3300.0,
            future_rent_mid=3501.0,
            future_rent_high=3634.0,
            basis_to_rent_framing="Current rent annualizes to roughly 4.4% of the current basis.",
            owner_occupy_then_rent="Owner-occupy then rent can work if carry is manageable.",
            zillow_market_rent=3600.0,
            zillow_market_rent_low=3400.0,
            zillow_market_rent_high=3900.0,
            zillow_rental_comp_count=4,
            burn_chart_payload={"series": [{"year": 0, "rent_base": 3600, "rent_bull": 3800, "rent_bear": 3400, "monthly_obligation": 4100}]},
            confidence_notes=[],
        )
        town_read = TownMarketRead(
            town="Belmar",
            state="NJ",
            confidence_label="High",
            narrative_summary="Belmar shows constructive demand and selective reinvestment.",
            bullish_signals=["Redevelopment approvals"],
            bearish_signals=["Traffic-sensitive denials"],
            watch_items=[],
            document_count=4,
            warnings=[],
        )
        payload = build_property_presentation(
            "1600-l-street-belmar-nj-07719",
            brief=brief,
            enrichment={},
            risk=None,
            cma=cma,
            rent_outlook=rent_outlook,
            town_read=town_read,
            contract_type="cma",
            analysis_mode="edge",
        )
        self.assertTrue(any(card.key == "cma" for card in payload.cards))
        self.assertTrue(any(card.key == "rent_outlook" for card in payload.cards))
        self.assertTrue(any(card.key == "town_pulse" for card in payload.cards))
        self.assertTrue(any(table.key == "cma_comps" for table in payload.tables))
        self.assertTrue(any(chart.kind == "rent_burn" for chart in payload.charts))


if __name__ == "__main__":
    unittest.main()
