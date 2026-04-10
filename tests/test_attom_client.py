from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from briarwood.data_sources.attom_client import AttomClient


class AttomClientTests(unittest.TestCase):
    def test_attom_client_normalizes_property_detail_and_uses_cache(self) -> None:
        fixture_dir = Path(__file__).resolve().parent / "fixtures" / "attom"
        payload = json.loads((fixture_dir / "property_detail.json").read_text())
        calls: list[str] = []

        def transport(url, params, headers, timeout):
            calls.append(url)
            return payload

        with tempfile.TemporaryDirectory() as tmpdir:
            client = AttomClient(
                api_key="test-key",
                cache_dir=tmpdir,
                transport=transport,
            )
            first = client.property_detail("belmar-1223-briarwood", address1="1223 Briarwood Rd", address2="Belmar, NJ")
            second = client.property_detail("belmar-1223-briarwood", address1="1223 Briarwood Rd", address2="Belmar, NJ")

        self.assertTrue(first.ok)
        self.assertEqual(first.normalized_payload["beds"], 4)
        self.assertEqual(first.normalized_payload["sqft"], 2180)
        self.assertFalse(first.from_cache)
        self.assertTrue(second.from_cache)
        self.assertEqual(len(calls), 1)

    def test_attom_client_normalizes_assessment_detail(self) -> None:
        fixture_dir = Path(__file__).resolve().parent / "fixtures" / "attom"
        payload = json.loads((fixture_dir / "assessment_detail.json").read_text())

        def transport(url, params, headers, timeout):
            return payload

        with tempfile.TemporaryDirectory() as tmpdir:
            client = AttomClient(
                api_key="test-key",
                cache_dir=tmpdir,
                transport=transport,
            )
            response = client.assessment_detail("belmar-1223-briarwood", address1="1223 Briarwood Rd", address2="Belmar, NJ")

        self.assertTrue(response.ok)
        self.assertEqual(response.normalized_payload["tax_amount"], 12850)
        self.assertEqual(response.normalized_payload["assessed_total"], 585000)
        self.assertIsNotNone(response.fetched_at)

    def test_attom_client_normalizes_batch_endpoints(self) -> None:
        fixture_dir = Path(__file__).resolve().parent / "fixtures" / "attom"
        community_payload = json.loads((fixture_dir / "community_demographics.json").read_text())
        permits_payload = json.loads((fixture_dir / "building_permits.json").read_text())

        def transport(url, params, headers, timeout):
            if "community" in url:
                return community_payload
            return permits_payload

        with tempfile.TemporaryDirectory() as tmpdir:
            client = AttomClient(api_key="test-key", cache_dir=tmpdir, transport=transport)
            demographics = client.community_demographics("belmar-town", locality="Belmar", state="NJ")
            permits = client.building_permits("belmar-town", locality="Belmar", state="NJ")

        self.assertTrue(demographics.ok)
        self.assertIn("housing_median_rent", demographics.normalized_payload)
        self.assertTrue(permits.ok)
        self.assertIn("permit_count", permits.normalized_payload)
