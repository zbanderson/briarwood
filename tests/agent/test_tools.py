from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from briarwood.agent.tools import get_cma, get_rent_outlook, promote_unsaved_address
from briarwood.data_sources.attom_client import AttomResponse


class PromoteUnsavedAddressTests(unittest.TestCase):
    def test_promote_unsaved_address_uses_address_text_when_google_unavailable(self) -> None:
        property_detail = AttomResponse(
            endpoint="property_detail",
            cache_key="property-detail",
            raw_payload={},
            normalized_payload={
                "address": "1228 Briarwood Road, Belmar, NJ 07719",
                "beds": 3,
                "baths": 2.0,
                "sqft": 1420,
                "year_built": 1958,
                "property_type": "SINGLE_FAMILY",
            },
            from_cache=False,
        )
        assessment = AttomResponse(
            endpoint="assessment_detail",
            cache_key="assessment",
            raw_payload={},
            normalized_payload={"tax_amount": 9200},
            from_cache=False,
        )
        sale_history = AttomResponse(
            endpoint="sale_history_snapshot",
            cache_key="sale-history",
            raw_payload={},
            normalized_payload={"sale_history": [{"sale_date": "2020-01-01", "sale_price": 515000}]},
            from_cache=False,
        )
        rental = AttomResponse(
            endpoint="rental_avm",
            cache_key="rental",
            raw_payload={},
            normalized_payload={"estimated_monthly_rent": 3600},
            from_cache=False,
        )

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "briarwood.agent.tools.SAVED_PROPERTIES_DIR",
            Path(tmpdir),
        ), patch(
            "briarwood.agent.tools.GoogleMapsClient"
        ) as google_cls, patch(
            "briarwood.agent.tools.AttomClient"
        ) as attom_cls:
            google = google_cls.return_value
            google.is_configured = False

            attom = attom_cls.return_value
            attom.api_key = "attom-test"
            attom.property_detail.return_value = property_detail
            attom.assessment_detail.return_value = assessment
            attom.sale_history_snapshot.return_value = sale_history
            attom.rental_avm.return_value = rental

            promoted = promote_unsaved_address("how much is 1228 briarwood road, belmar, nj worth?")

        self.assertEqual(promoted.property_id, "1228-briarwood-road-belmar-nj-07719")
        self.assertEqual(promoted.town, "Belmar")
        self.assertEqual(promoted.state, "NJ")
        attom.property_detail.assert_called_once_with(
            "1228 briarwood road, belmar, nj",
            address1="1228 briarwood road",
            address2="Belmar, NJ",
        )


class ContractToolTests(unittest.TestCase):
    def test_get_cma_returns_comp_contract(self) -> None:
        with patch(
            "briarwood.agent.tools.get_property_summary",
            return_value={
                "address": "1600 L Street, Belmar, NJ 07719",
                "town": "Belmar",
                "state": "NJ",
                "beds": 3,
                "baths": 2.0,
            },
        ), patch(
            "briarwood.agent.tools.get_value_thesis",
            return_value={
                "ask_price": 899000.0,
                "fair_value_base": 804396.0,
                "value_low": 760000.0,
                "value_high": 860000.0,
                "pricing_view": "above_fair_value",
                "primary_value_source": "current_value",
            },
        ), patch(
            "briarwood.agent.tools.search_listings",
            return_value=[
                {
                    "property_id": "1302-l-street",
                    "address": "1302 L Street, Belmar, NJ 07719",
                    "town": "Belmar",
                    "state": "NJ",
                    "beds": 3,
                    "baths": 2.0,
                    "ask_price": 850000.0,
                    "blocks_to_beach": 18.9,
                }
            ],
        ):
            result = get_cma("1600-l-street-belmar-nj-07719")
        self.assertEqual(result.address, "1600 L Street, Belmar, NJ 07719")
        self.assertEqual(len(result.comps), 1)
        self.assertEqual(result.comps[0].property_id, "1302-l-street")

    def test_get_rent_outlook_returns_future_range(self) -> None:
        with patch(
            "briarwood.agent.tools.get_rent_estimate",
            return_value={
                "monthly_rent": 3500.0,
                "effective_monthly_rent": 3300.0,
                "annual_noi": 22000.0,
                "rent_source_type": "estimated",
                "rental_ease_label": "moderate",
                "rental_ease_score": 61.0,
            },
        ), patch(
            "briarwood.agent.tools.get_property_summary",
            return_value={"address": "1600 L Street, Belmar, NJ 07719", "ask_price": 899000.0, "town": "Belmar", "state": "NJ", "beds": 3},
        ), patch(
            "briarwood.agent.tools._search_zillow_rental_market",
            return_value={
                "market_rent": 3600,
                "rent_low": 3400,
                "rent_high": 3900,
                "rental_comp_count": 4,
            },
        ):
            outlook = get_rent_outlook(
                "1600-l-street-belmar-nj-07719",
                years=2,
                owner_occupy_then_rent=True,
            )
        self.assertEqual(outlook.horizon_years, 2)
        self.assertIsNotNone(outlook.future_rent_mid)
        self.assertIn("Current rent annualizes", outlook.basis_to_rent_framing or "")
        self.assertEqual(outlook.zillow_market_rent, 3600.0)
        self.assertEqual(outlook.zillow_rental_comp_count, 4)
        self.assertTrue(outlook.burn_chart_payload["series"])


if __name__ == "__main__":
    unittest.main()
