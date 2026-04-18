import unittest
from pathlib import Path

from briarwood.agent.tools import search_live_listings
from briarwood.data_sources.searchapi_zillow_client import SearchApiZillowClient
from briarwood.listing_intake.normalizer import normalize_listing
from briarwood.listing_intake.schemas import ListingRawData
from briarwood.listing_intake.parsers import ZillowUrlParser


class SearchApiZillowClientTests(unittest.TestCase):
    def test_url_parser_falls_back_to_metadata_when_client_is_disabled(self) -> None:
        parser = ZillowUrlParser(client=SearchApiZillowClient(api_key=""))

        raw, warnings = parser.parse(
            "https://www.zillow.com/homedetails/17-Cedar-Ln-Brookline-MA-02445/123456_zpid/"
        )

        self.assertEqual(raw.address, "17 Cedar Ln Brookline Ma 02445")
        self.assertIsNone(raw.price)
        self.assertIn("URL intake is metadata-only unless SearchAPI Zillow is configured.", warnings)

    def test_url_parser_hydrates_listing_fields_via_searchapi(self) -> None:
        def transport(
            url: str,
            params: dict[str, str],
            headers: dict[str, str],
            timeout_seconds: float,
        ) -> dict[str, object]:
            self.assertEqual(url, "https://www.searchapi.io/api/v1/search")
            self.assertEqual(params["engine"], "zillow")
            self.assertIn("1223 Briarwood Rd", params["q"])
            return {
                "organic_results": [
                    {
                        "zpid": "39225332",
                        "address": "1223 Briarwood Rd, Belmar, NJ 07719",
                        "link": "https://www.zillow.com/homedetails/1223-Briarwood-Rd-Belmar-NJ-07719/39225332_zpid/",
                        "extracted_price": 674200,
                        "beds": 3,
                        "baths": 2.0,
                        "living_area": 1468,
                        "lot_size": 5001,
                        "home_type": "Single Family",
                        "year_built": 1950,
                        "days_on_zillow": 12,
                        "description": "Belmar shore colonial with renovation upside.",
                    }
                ]
            }

        parser = ZillowUrlParser(
            client=SearchApiZillowClient(
                api_key="test-key",
                transport=transport,
                cache_dir=Path("/tmp/briarwood-searchapi-client-tests"),
            )
        )

        raw, warnings = parser.parse(
            "https://www.zillow.com/homedetails/1223-Briarwood-Rd-Belmar-NJ-07719/39225332_zpid/"
        )

        self.assertEqual(raw.address, "1223 Briarwood Rd, Belmar, NJ 07719")
        self.assertEqual(raw.price, 674200.0)
        self.assertEqual(raw.beds, 3)
        self.assertEqual(raw.baths, 2.0)
        self.assertEqual(raw.sqft, 1468)
        self.assertEqual(raw.lot_sqft, 5001)
        self.assertEqual(raw.property_type, "Single Family")
        self.assertEqual(raw.year_built, 1950)
        self.assertEqual(raw.days_on_market, 12)
        self.assertIn("Live Zillow hydration succeeded via SearchAPI.", warnings)

    def test_search_listings_returns_multiple_candidates(self) -> None:
        def transport(
            url: str,
            params: dict[str, str],
            headers: dict[str, str],
            timeout_seconds: float,
        ) -> dict[str, object]:
            self.assertEqual(params["engine"], "zillow")
            self.assertEqual(params["q"], "Belmar, NJ homes for sale")
            return {
                "organic_results": [
                    {
                        "zpid": "1",
                        "address": "1223 Briarwood Rd, Belmar, NJ 07719",
                        "extracted_price": 674200,
                        "beds": 3,
                        "baths": 2.0,
                        "living_area": 1468,
                        "home_type": "Single Family",
                        "status": "For sale",
                        "link": "https://www.zillow.com/homedetails/1223-Briarwood-Rd-Belmar-NJ-07719/1_zpid/",
                    },
                    {
                        "zpid": "2",
                        "address": "1600 L St, Belmar, NJ 07719",
                        "extracted_price": 999000,
                        "beds": 3,
                        "baths": 2.0,
                        "living_area": 1800,
                        "home_type": "Single Family",
                        "status": "For sale",
                        "link": "https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/2_zpid/",
                    },
                ]
            }

        client = SearchApiZillowClient(
            api_key="test-key",
            transport=transport,
            cache_dir=Path("/tmp/briarwood-searchapi-client-tests"),
        )
        response = client.search_listings(query="Belmar, NJ homes for sale", max_results=5)

        self.assertTrue(response.ok)
        candidates = client.to_listing_candidates(response.normalized_payload)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].town, "Belmar")
        self.assertEqual(candidates[0].state, "NJ")
        self.assertEqual(candidates[0].price, 674200.0)
        self.assertEqual(candidates[1].price, 999000.0)

    def test_search_listings_supports_rental_params(self) -> None:
        def transport(
            url: str,
            params: dict[str, str],
            headers: dict[str, str],
            timeout_seconds: float,
        ) -> dict[str, object]:
            self.assertEqual(params["listing_status"], "for_rent")
            self.assertEqual(params["beds_min"], "3")
            self.assertEqual(params["rent_min"], "2500")
            self.assertEqual(params["rent_max"], "5000")
            return {
                "organic_results": [
                    {
                        "zpid": "rent-1",
                        "address": "1600 L St, Belmar, NJ 07719",
                        "price": 3600,
                        "beds": 3,
                        "baths": 2.0,
                        "status": "For rent",
                    }
                ]
            }

        client = SearchApiZillowClient(
            api_key="test-key",
            transport=transport,
            cache_dir=Path("/tmp/briarwood-searchapi-client-tests"),
        )
        response = client.search_listings(
            query="Belmar, NJ",
            listing_status="for_rent",
            beds_min=3,
            rent_min=2500,
            rent_max=5000,
        )

        self.assertTrue(response.ok)
        candidates = client.to_listing_candidates(response.normalized_payload)
        self.assertEqual(candidates[0].price, 3600.0)
        self.assertEqual(candidates[0].listing_status, "For rent")

    def test_live_listing_helper_filters_to_requested_town_and_beds(self) -> None:
        def transport(
            url: str,
            params: dict[str, str],
            headers: dict[str, str],
            timeout_seconds: float,
        ) -> dict[str, object]:
            self.assertEqual(params["q"], "Belmar, NJ")
            return {
                "properties": [
                    {
                        "zpid": "1",
                        "address": "1223 Briarwood Rd, Belmar, NJ 07719",
                        "extracted_price": 674200,
                        "beds": 3,
                        "baths": 2.0,
                    },
                    {
                        "zpid": "2",
                        "address": "4717 De Grey Ln, Plano, TX 75093",
                        "extracted_price": 675000,
                        "beds": 4,
                        "baths": 4.0,
                    },
                ]
            }

        client = SearchApiZillowClient(
            api_key="test-key",
            transport=transport,
            cache_dir=Path("/tmp/briarwood-searchapi-client-tests"),
        )
        candidates = search_live_listings(
            query="Belmar, NJ",
            town="Belmar",
            state="NJ",
            beds=3,
            client=client,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].address, "1223 Briarwood Rd, Belmar, NJ 07719")

    def test_normalizer_parses_location_without_commas(self) -> None:
        result = normalize_listing(
            ListingRawData(
                source="zillow",
                intake_mode="url_intake",
                address="1600 L Street Belmar NJ 07719",
                price=899000.0,
                beds=3,
                baths=2.0,
            )
        )

        self.assertEqual(result.normalized_property_data.town, "Belmar")
        self.assertEqual(result.normalized_property_data.state, "NJ")
        self.assertEqual(result.normalized_property_data.county, "Monmouth")


if __name__ == "__main__":
    unittest.main()
