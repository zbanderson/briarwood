from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from briarwood.agent.tools import get_cma, get_projection, get_rent_outlook, get_value_thesis, promote_unsaved_address
from briarwood.data_sources.attom_client import AttomResponse
from briarwood.data_sources.searchapi_zillow_client import SearchApiZillowListingCandidate


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
    def test_get_value_thesis_merges_auto_cma_and_user_comp_inputs_into_fair_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            property_dir = Path(tmpdir) / "subject-property"
            property_dir.mkdir(parents=True, exist_ok=True)
            (property_dir / "inputs.json").write_text(
                json.dumps({"facts": {"purchase_price": 767000}, "user_assumptions": {}})
            )

            captured_manual_inputs: list[dict[str, object]] = []

            def _fake_run_routed_report(path, user_input=None):
                data = json.loads(Path(path).read_text())
                captured_manual_inputs[:] = list(
                    data.get("user_assumptions", {}).get("manual_comp_inputs", [])
                )
                comps_used = [
                    SimpleNamespace(
                        address=comp.get("address"),
                        bedrooms=comp.get("beds"),
                        bathrooms=comp.get("baths"),
                        sale_price=comp.get("sale_price"),
                        source_name=comp.get("source_name"),
                        source_quality=comp.get("source_quality"),
                        source_ref=comp.get("source_ref"),
                        source_summary=comp.get("source_notes"),
                        source_provenance=comp.get("source_provenance"),
                    )
                    for comp in captured_manual_inputs
                ]
                comp_payload = SimpleNamespace(
                    comps_used=comps_used,
                    base_comp_selection=SimpleNamespace(
                        support_summary=SimpleNamespace(
                            comp_count=len(comps_used),
                            support_quality="moderate",
                            notes=["Manual and CMA comp support were blended into the fair value read."],
                        )
                    ),
                )
                engine_output = SimpleNamespace(
                    outputs={
                        "valuation": SimpleNamespace(
                            data={
                                "metrics": {
                                    "mispricing_amount": 15000.0,
                                    "mispricing_pct": 0.02,
                                    "pricing_view": "fair_to_slightly_high",
                                    "value_drivers": ["Belmar demand"],
                                    "net_opportunity_delta_value": 15000.0,
                                    "net_opportunity_delta_pct": 0.02,
                                }
                            }
                        ),
                        "comparable_sales": SimpleNamespace(payload=comp_payload),
                    }
                )
                unified_output = SimpleNamespace(
                    model_dump=lambda: {
                        "value_position": {
                            "ask_price": 767000.0,
                            "fair_value_base": 752000.0,
                            "value_low": 720000.0,
                            "value_high": 785000.0,
                            "premium_discount_pct": 0.02,
                        },
                        "primary_value_source": "current_value",
                        "key_value_drivers": ["Belmar demand"],
                        "what_must_be_true": ["The selected comps stay defensible."],
                    }
                )
                return SimpleNamespace(engine_output=engine_output, unified_output=unified_output)

            fake_runner = ModuleType("briarwood.runner_routed")
            fake_runner.run_routed_report = _fake_run_routed_report

            with patch("briarwood.agent.tools.SAVED_PROPERTIES_DIR", Path(tmpdir)), patch(
                "briarwood.agent.tools.get_property_summary",
                return_value={
                    "address": "1008 14th Avenue, Belmar, NJ 07719",
                    "town": "Belmar",
                    "state": "NJ",
                    "beds": 3,
                    "baths": 1.0,
                    "ask_price": 767000.0,
                },
            ), patch(
                "briarwood.agent.tools._live_zillow_cma_candidates",
                return_value={
                    "summary": "Live Zillow market comps ranked toward the subject's layout and price.",
                    "rows": [
                        {
                            "property_id": "1302-l-street",
                            "address": "1302 L Street, Belmar, NJ 07719",
                            "town": "Belmar",
                            "state": "NJ",
                            "beds": 3,
                            "baths": 2.0,
                            "ask_price": 850000.0,
                            "source_kind": "live_market_comp",
                        }
                    ],
                },
            ), patch.dict(
                sys.modules,
                {"briarwood.runner_routed": fake_runner},
            ):
                thesis = get_value_thesis(
                    "subject-property",
                    overrides={
                        "manual_comp_inputs": [
                            {
                                "address": "1223 Briarwood Rd, Belmar, NJ 07719",
                                "town": "Belmar",
                                "state": "NJ",
                                "sale_price": 674200.0,
                                "sale_date": "2025-02-01",
                                "source_name": "User input comp",
                                "source_quality": "user_input",
                                "source_ref": "1223-briarwood-rd",
                                "source_notes": "User selected this comp for the valuation.",
                                "source_provenance": {"comp_origin": "user_input_comp"},
                            }
                        ]
                    },
                )

        self.assertEqual(len(captured_manual_inputs), 2)
        self.assertEqual(
            {comp.get("source_name") for comp in captured_manual_inputs},
            {"Live market comp", "User input comp"},
        )
        self.assertEqual(len(thesis["comps"]), 2)
        self.assertIn("user input comp", (thesis["comp_selection_summary"] or "").lower())
        self.assertIn("live market comp", (thesis["comp_selection_summary"] or "").lower())

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
            "briarwood.agent.tools.SearchApiZillowClient"
        ) as zillow_cls, patch(
            "briarwood.agent.tools.AttomClient"
        ) as attom_cls, patch(
            "briarwood.agent.tools.search_listings",
            return_value=[],
        ):
            zillow = zillow_cls.return_value
            zillow.is_configured = True
            zillow.search_listings.return_value.ok = True
            zillow.search_listings.return_value.normalized_payload = {"results": [{}]}
            zillow.to_listing_candidates.return_value = [
                SearchApiZillowListingCandidate(
                    zpid="1302-l-street",
                    address="1302 L Street, Belmar, NJ 07719",
                    town="Belmar",
                    state="NJ",
                    zip_code="07719",
                    price=850000.0,
                    beds=3,
                    baths=2.0,
                    sqft=1320,
                    property_type="single_family",
                    listing_status="for_sale",
                    listing_url="https://www.zillow.com/homedetails/1302-L-St-Belmar-NJ-07719/",
                )
            ]
            attom = attom_cls.return_value
            attom.api_key = "attom-test"
            attom.sale_history_snapshot.return_value = AttomResponse(
                endpoint="sale_history_snapshot",
                cache_key="sale-history",
                raw_payload={},
                normalized_payload={"sale_count": 2, "last_sale_date": "2020-01-01"},
                from_cache=False,
            )
            attom.assessment_detail.return_value = AttomResponse(
                endpoint="assessment_detail",
                cache_key="assessment",
                raw_payload={},
                normalized_payload={"tax_amount": 9200},
                from_cache=False,
            )
            result = get_cma("1600-l-street-belmar-nj-07719")
        self.assertEqual(result.address, "1600 L Street, Belmar, NJ 07719")
        self.assertEqual(len(result.comps), 1)
        self.assertEqual(result.comps[0].property_id, "1302-l-street")
        self.assertIn("Live Zillow market comps", result.comp_selection_summary or "")
        self.assertTrue(any("ATTOM sale history confirmed" in note for note in result.confidence_notes))

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
                "monthly_cash_flow": -400.0,
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
        self.assertTrue(outlook.ramp_chart_payload["series"])

    def test_get_rent_outlook_uses_override_basis_when_provided(self) -> None:
        with patch(
            "briarwood.agent.tools.get_rent_estimate",
            return_value={
                "monthly_rent": 3500.0,
                "effective_monthly_rent": 3300.0,
                "annual_noi": 22000.0,
                "rent_source_type": "estimated",
                "rental_ease_label": "moderate",
                "rental_ease_score": 61.0,
                "monthly_cash_flow": -400.0,
            },
        ), patch(
            "briarwood.agent.tools.get_property_summary",
            return_value={"address": "1008 14th Avenue, Belmar, NJ 07719", "ask_price": 767000.0, "town": "Belmar", "state": "NJ", "beds": 3},
        ), patch(
            "briarwood.agent.tools._search_zillow_rental_market",
            return_value=None,
        ):
            outlook = get_rent_outlook(
                "1008-14th-avenue-belmar-nj-07719",
                years=2,
                overrides={"ask_price": 650000.0},
            )

        self.assertEqual(outlook.entry_basis, 650000.0)
        self.assertIn("6.1%", outlook.basis_to_rent_framing or "")

    def test_get_rent_outlook_keeps_current_anchor_when_market_signal_is_other_regime(self) -> None:
        with patch(
            "briarwood.agent.tools.get_rent_estimate",
            return_value={
                "monthly_rent": 2352.0,
                "effective_monthly_rent": 2234.0,
                "annual_noi": 19143.0,
                "rent_source_type": "seasonal_mixed",
                "rental_ease_label": "fragile",
                "rental_ease_score": 49.96,
                "monthly_cash_flow": -866.0,
            },
        ), patch(
            "briarwood.agent.tools.get_property_summary",
            return_value={"address": "1008 14th Avenue, Belmar, NJ 07719", "ask_price": 767000.0, "town": "Belmar", "state": "NJ", "beds": 3},
        ), patch(
            "briarwood.agent.tools._search_zillow_rental_market",
            return_value={
                "market_rent": 8000,
                "rent_low": 4000,
                "rent_high": 9000,
                "rental_comp_count": 5,
            },
        ):
            outlook = get_rent_outlook("1008-14th-avenue-belmar-nj-07719", years=3)

        self.assertIn("different rental regime", outlook.market_context_note or "")
        burn_points = outlook.burn_chart_payload["series"]
        self.assertEqual(burn_points[0]["rent_base"], 2234)
        self.assertLess(outlook.future_rent_mid or 0, 3000)

    def test_get_projection_uses_override_basis_label_when_entry_price_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            property_dir = Path(tmpdir) / "subject-property"
            property_dir.mkdir(parents=True, exist_ok=True)
            (property_dir / "inputs.json").write_text(
                json.dumps({"facts": {"purchase_price": 767000}, "user_assumptions": {}})
            )

            def _fake_run_routed_report(path, user_input=None):
                del path, user_input
                engine_output = SimpleNamespace(
                    outputs={
                        "resale_scenario": SimpleNamespace(
                            data={
                                "metrics": {
                                    "ask_price": 767000.0,
                                    "bull_case_value": 816046.0,
                                    "base_case_value": 764343.0,
                                    "bear_case_value": 722117.0,
                                    "stress_case_value": 506489.0,
                                    "spread": 93928.0,
                                    "bull_total_adjustment_pct": 0.128,
                                    "base_total_adjustment_pct": 0.056,
                                    "bear_total_adjustment_pct": -0.002,
                                    "bull_growth_rate": 0.064,
                                    "base_growth_rate": -0.004,
                                    "bear_growth_rate": -0.059,
                                }
                            }
                        )
                    }
                )
                return SimpleNamespace(engine_output=engine_output)

            fake_runner = ModuleType("briarwood.runner_routed")
            fake_runner.run_routed_report = _fake_run_routed_report

            with patch("briarwood.agent.tools.SAVED_PROPERTIES_DIR", Path(tmpdir)), patch(
                "briarwood.agent.tools.get_property_summary",
                return_value={"ask_price": 767000.0, "town": "Belmar", "state": "NJ", "beds": 3},
            ), patch(
                "briarwood.agent.tools._live_zillow_cma_candidates",
                return_value={"summary": "", "rows": []},
            ), patch.dict(
                sys.modules,
                {"briarwood.runner_routed": fake_runner},
            ):
                projection = get_projection("subject-property", overrides={"ask_price": 690300.0})

        self.assertEqual(projection["ask_price"], 690300.0)
        self.assertEqual(projection["listing_ask_price"], 767000.0)
        self.assertEqual(projection["basis_label"], "entry basis")


if __name__ == "__main__":
    unittest.main()
