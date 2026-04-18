import tempfile
import unittest

from briarwood.data_sources.google_maps_client import GoogleMapsClient


class GoogleMapsClientTests(unittest.TestCase):
    def test_geocode_normalizes_core_fields(self) -> None:
        def transport(url, *, method, params, headers, timeout_seconds, body=None):
            self.assertEqual(method, "GET")
            self.assertIn("Belmar", params["address"])
            return {
                "results": [
                    {
                        "formatted_address": "1600 L Street, Belmar, NJ 07719, USA",
                        "place_id": "test-place-id",
                        "types": ["street_address"],
                        "geometry": {"location": {"lat": 40.1815, "lng": -74.0212}},
                        "address_components": [
                            {"long_name": "Belmar", "short_name": "Belmar", "types": ["locality"]},
                            {"long_name": "New Jersey", "short_name": "NJ", "types": ["administrative_area_level_1"]},
                            {"long_name": "Monmouth County", "short_name": "Monmouth", "types": ["administrative_area_level_2"]},
                            {"long_name": "07719", "short_name": "07719", "types": ["postal_code"]},
                        ],
                    }
                ]
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            client = GoogleMapsClient(api_key="test-key", cache_dir=tmpdir, transport=transport)
            response = client.geocode("1600 L Street, Belmar, NJ 07719")

        self.assertTrue(response.ok)
        self.assertEqual(response.normalized_payload["town"], "Belmar")
        self.assertEqual(response.normalized_payload["state"], "NJ")
        self.assertEqual(response.normalized_payload["county"], "Monmouth")
        self.assertEqual(response.normalized_payload["zip_code"], "07719")

    def test_nearby_places_tracks_counts_and_nearest(self) -> None:
        def transport(url, *, method, params, headers, timeout_seconds, body=None):
            self.assertEqual(method, "POST")
            self.assertIn("X-Goog-FieldMask", headers)
            self.assertEqual(body["includedTypes"], ["school", "park"])
            return {
                "places": [
                    {
                        "id": "school-1",
                        "displayName": {"text": "Belmar Elementary"},
                        "formattedAddress": "1101 Main St, Belmar, NJ 07719",
                        "primaryType": "school",
                        "location": {"latitude": 40.1819, "longitude": -74.019},
                        "rating": 4.2,
                        "userRatingCount": 12,
                        "googleMapsUri": "https://maps.google.com/?cid=school1",
                    },
                    {
                        "id": "park-1",
                        "displayName": {"text": "Silver Lake Park"},
                        "formattedAddress": "Belmar, NJ 07719",
                        "primaryType": "park",
                        "location": {"latitude": 40.1809, "longitude": -74.018},
                        "rating": 4.7,
                        "userRatingCount": 31,
                        "googleMapsUri": "https://maps.google.com/?cid=park1",
                    },
                ]
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            client = GoogleMapsClient(api_key="test-key", cache_dir=tmpdir, transport=transport)
            response = client.nearby_places(
                latitude=40.1815,
                longitude=-74.0212,
                included_types=["school", "park"],
            )

        self.assertTrue(response.ok)
        self.assertEqual(response.normalized_payload["type_counts"]["school"], 1)
        self.assertEqual(response.normalized_payload["type_counts"]["park"], 1)
        self.assertEqual(response.normalized_payload["nearest_by_type"]["school"]["name"], "Belmar Elementary")

    def test_street_view_image_url_uses_subject_coordinates(self) -> None:
        client = GoogleMapsClient(api_key="test-key")

        url = client.street_view_image_url(latitude=40.1815, longitude=-74.0212)

        self.assertIn("streetview", url)
        self.assertIn("40.1815%2C-74.0212", url)
        self.assertIn("key=test-key", url)


if __name__ == "__main__":
    unittest.main()
