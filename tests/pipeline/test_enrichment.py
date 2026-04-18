import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from briarwood.data_sources.attom_client import AttomResponse
from briarwood.pipeline.enrichment import enrich_property


class _FakeAttomClient:
    api_key = "test-key"

    def property_detail(self, canonical_key: str, **params):
        return AttomResponse("property_detail", "cache", {}, {"sqft": 1468, "beds": 3}, False)

    def sale_history_snapshot(self, canonical_key: str, **params):
        return AttomResponse("sale_history_snapshot", "cache", {}, {"sale_count": 2, "history_confidence": 0.8}, False)

    def assessment_detail(self, canonical_key: str, **params):
        return AttomResponse("assessment_detail", "cache", {}, {"tax_amount": 12850}, False)

    def rental_avm(self, canonical_key: str, **params):
        return AttomResponse("rental_avm", "cache", {}, {"estimated_monthly_rent": 3600}, False)


class _FakeGoogleClient:
    is_configured = True

    def geocode(self, address: str):
        return type(
            "Resp",
            (),
            {
                "ok": True,
                "error": None,
                "normalized_payload": {
                    "formatted_address": "1600 L Street, Belmar, NJ 07719, USA",
                    "latitude": 40.1815,
                    "longitude": -74.0212,
                    "town": "Belmar",
                    "state": "NJ",
                    "county": "Monmouth",
                    "zip_code": "07719",
                },
            },
        )()

    def nearby_places(self, *, latitude: float, longitude: float, radius_meters: float = 1600.0, included_types=None, max_results: int = 8):
        return type(
            "Resp",
            (),
            {
                "ok": True,
                "error": None,
                "normalized_payload": {
                    "type_counts": {"school": 1, "park": 1},
                    "nearest_by_type": {
                        "school": {"name": "Belmar Elementary", "distance_meters": 420}
                    },
                    "places": [],
                },
            },
        )()

    def street_view_image_url(self, *, latitude: float, longitude: float, size: str = "640x360", fov: int = 90, pitch: int = 0):
        return "https://maps.googleapis.com/maps/api/streetview?location=40.1815,-74.0212"


class EnrichmentBundleTests(unittest.TestCase):
    def test_enrich_property_writes_unified_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            saved_root = Path(tmpdir) / "saved_properties"
            property_dir = saved_root / "1600-l-street-belmar-nj-07719"
            property_dir.mkdir(parents=True, exist_ok=True)
            (property_dir / "summary.json").write_text(
                json.dumps(
                    {
                        "property_id": "1600-l-street-belmar-nj-07719",
                        "address": "1600 L Street, Belmar, NJ 07719",
                        "town": "Belmar",
                        "state": "NJ",
                        "ask_price": 899000.0,
                        "source_url": "https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
                        "missing_input_count": 4,
                    }
                )
                + "\n"
            )
            (property_dir / "inputs.json").write_text(
                json.dumps(
                    {
                        "facts": {
                            "address": "1600 L Street, Belmar, NJ 07719",
                            "town": "Belmar",
                            "state": "NJ",
                            "source_url": "https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
                        },
                        "source_metadata": {
                            "provenance": ["searchapi_zillow:https://www.zillow.com/..."],
                            "source_coverage": {
                                "address": {"status": "sourced"},
                                "price_ask": {"status": "sourced"},
                                "sqft": {"status": "missing"},
                            },
                        },
                    }
                )
                + "\n"
            )

            with patch("briarwood.pipeline.enrichment.SAVED_PROPERTIES_DIR", saved_root):
                bundle = enrich_property(
                    "1600-l-street-belmar-nj-07719",
                    attom_client=_FakeAttomClient(),
                    google_client=_FakeGoogleClient(),
                    town_researcher=lambda town, state: {
                        "town": town,
                        "state": state,
                        "document_count": 3,
                        "summary": {"market_direction": "constructive"},
                    },
                )

            self.assertEqual(bundle.property_id, "1600-l-street-belmar-nj-07719")
            self.assertEqual(bundle.attom["rental_avm"]["estimated_monthly_rent"], 3600)
            self.assertEqual(bundle.google["geocode"]["county"], "Monmouth")
            self.assertEqual(bundle.town_intelligence["document_count"], 3)
            artifact = json.loads((property_dir / "enrichment.json").read_text())
            self.assertEqual(artifact["source_coverage"]["sqft"], "missing")
            self.assertEqual(artifact["google"]["nearby_places"]["type_counts"]["park"], 1)

    def test_enrich_property_collects_configuration_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            saved_root = Path(tmpdir) / "saved_properties"
            property_dir = saved_root / "1223-briarwood-rd"
            property_dir.mkdir(parents=True, exist_ok=True)
            (property_dir / "summary.json").write_text(json.dumps({"property_id": "1223-briarwood-rd", "address": "1223 Briarwood Rd, Belmar, NJ 07719", "town": "Belmar", "state": "NJ"}) + "\n")
            (property_dir / "inputs.json").write_text(json.dumps({"facts": {"address": "1223 Briarwood Rd, Belmar, NJ 07719", "town": "Belmar", "state": "NJ"}, "source_metadata": {}}) + "\n")

            class _NoGoogle:
                is_configured = False

            class _NoAttom:
                api_key = ""

            with patch("briarwood.pipeline.enrichment.SAVED_PROPERTIES_DIR", saved_root):
                bundle = enrich_property(
                    "1223-briarwood-rd",
                    attom_client=_NoAttom(),
                    google_client=_NoGoogle(),
                    include_town_research=False,
                )

            self.assertGreaterEqual(len(bundle.warnings), 2)
            self.assertIn("Google Maps enrichment unavailable", bundle.warnings[0])


if __name__ == "__main__":
    unittest.main()
