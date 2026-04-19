from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from api import events
from api.pipeline_adapter import (
    _to_listing_from_facts,
    _verdict_from_view,
    browse_stream,
    decision_stream,
    dispatch_stream,
)
from briarwood.agent.router import AnswerType, RouterDecision
from briarwood.agent.session import Session


def _run_stream(stream):
    async def _collect():
        return [event async for event in stream]

    return asyncio.run(_collect())


def _decision(answer_type: AnswerType) -> RouterDecision:
    return RouterDecision(answer_type=answer_type, confidence=0.99, reason="test")


class PipelineAdapterContractTests(unittest.TestCase):
    def test_decision_stream_emits_core_cards_before_text_and_native_chart_after(self) -> None:
        session = Session(session_id="decision-contract")
        session.last_decision_view = {
            "address": "123 Main St, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "decision_stance": "buy_if_price_improves",
            "primary_value_source": "current_value",
            "ask_price": 800000,
            "all_in_basis": 820000,
            "fair_value_base": 760000,
            "value_low": 735000,
            "value_high": 790000,
            "ask_premium_pct": 0.0526,
            "basis_premium_pct": 0.0789,
            "trust_flags": ["thin_comp_set"],
            "what_must_be_true": ["comps hold"],
            "key_risks": ["flood exposure"],
            "overrides_applied": {},
        }
        session.last_town_summary = {
            "town": "Belmar",
            "state": "NJ",
            "doc_count": 2,
            "bullish_signals": ["beach demand"],
            "bearish_signals": ["tight inventory"],
        }
        session.last_comps_preview = {
            "count": 3,
            "median_price": 775000,
            "comps": [{"property_id": "comp-1", "address": "1 Ocean Ave"}],
        }
        session.last_projection_view = {
            "address": "123 Main St, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "ask_price": 800000,
            "basis_label": "entry basis",
            "bull_case_value": 910000,
            "base_case_value": 845000,
            "bear_case_value": 760000,
            "stress_case_value": 710000,
            "spread": 150000,
        }

        pinned_listing = {
            "id": "subject-1",
            "address_line": "123 Main St, Belmar, NJ 07719",
            "city": "Belmar",
            "state": "NJ",
            "price": 800000,
            "beds": 3,
            "baths": 2.0,
            "sqft": 1500,
            "status": "active",
        }

        with (
            patch("api.pipeline_adapter._load_or_create_session", return_value=session),
            patch("api.pipeline_adapter.dispatch", return_value="This is the streamed narrative."),
            patch("api.pipeline_adapter._finalize_session"),
        ):
            emitted = _run_stream(
                decision_stream(
                    "should I buy it?",
                    _decision(AnswerType.DECISION),
                    pinned_listing,
                    conversation_id="conv-1",
                )
            )

        event_types = [event["type"] for event in emitted]
        self.assertEqual(
            event_types[:3],
            [events.EVENT_VERDICT, events.EVENT_TOWN_SUMMARY, events.EVENT_COMPS_PREVIEW],
        )
        first_text_index = event_types.index(events.EVENT_TEXT_DELTA)
        self.assertGreater(event_types.index(events.EVENT_SCENARIO_TABLE), first_text_index)
        scenario_chart_index = next(
            idx
            for idx, event in enumerate(emitted)
            if event["type"] == events.EVENT_CHART and event.get("kind") == "scenario_fan"
        )
        self.assertGreater(scenario_chart_index, first_text_index)
        self.assertIsNotNone(emitted[scenario_chart_index].get("spec"))
        scenario_table = next(event for event in emitted if event["type"] == events.EVENT_SCENARIO_TABLE)
        self.assertEqual(scenario_table.get("basis_label"), "entry basis")
        self.assertEqual(emitted[scenario_chart_index]["spec"].get("basis_label"), "entry basis")

    def test_decision_stream_emits_value_thesis_risk_strategy_rent_when_views_populated(self) -> None:
        """Regression pin for audit finding 1.5.3: _decision_stream_impl used to
        drop value_thesis / risk_profile / strategy_path / rent_outlook even when
        the session views were populated. They are module-level evidence behind
        the verdict and must surface on the decision turn."""
        session = Session(session_id="decision-contract-full-cards")
        session.last_decision_view = {
            "address": "123 Main St, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "decision_stance": "buy_if_price_improves",
            "primary_value_source": "current_value",
            "ask_price": 800000,
            "all_in_basis": 820000,
            "fair_value_base": 760000,
            "value_low": 735000,
            "value_high": 790000,
            "ask_premium_pct": 0.0526,
            "basis_premium_pct": 0.0789,
            "trust_flags": [],
            "what_must_be_true": ["comps hold"],
            "key_risks": ["flood exposure"],
            "overrides_applied": {},
        }
        session.last_value_thesis_view = {
            "address": "123 Main St, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "ask_price": 800000,
            "fair_value_base": 760000,
            "premium_discount_pct": 0.0526,
            "pricing_view": "above_fair_value",
            "primary_value_source": "current_value",
            "value_drivers": ["walkable Belmar location"],
            "key_value_drivers": ["walkable Belmar location"],
            "what_must_be_true": ["comps hold"],
            "comp_selection_summary": "Saved comps.",
            "comps": [],
        }
        session.last_risk_view = {
            "address": "123 Main St, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "ask_price": 800000,
            "bear_value": 720000,
            "stress_value": 680000,
            "risk_flags": ["flood_zone"],
            "trust_flags": [],
            "key_risks": ["Flood-zone exposure"],
            "total_penalty": 0.22,
            "confidence_tier": "moderate",
        }
        session.last_strategy_view = {
            "address": "123 Main St, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "best_path": "buy_if_price_improves",
            "recommendation": "Interesting if you can buy below ask.",
            "pricing_view": "above_fair_value",
            "primary_value_source": "current_value",
            "rental_ease_label": "seasonal/mixed",
            "rental_ease_score": 57.0,
            "rent_support_score": 52.0,
            "liquidity_score": 61.0,
            "monthly_cash_flow": -866,
            "cash_on_cash_return": 0.021,
            "annual_noi": 18500,
        }
        session.last_rent_outlook_view = {
            "address": "123 Main St, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "entry_basis": 800000,
            "monthly_rent": 2352,
            "effective_monthly_rent": 2234,
            "annual_noi": 18500,
            "rent_source_type": "seasonal_mixed",
            "rental_ease_label": "seasonal/mixed",
            "rental_ease_score": 57.0,
            "horizon_years": 3,
            "future_rent_low": 2300,
            "future_rent_mid": 2410,
            "future_rent_high": 2600,
            "basis_to_rent_framing": "~3.5% of basis.",
        }

        pinned_listing = {
            "id": "subject-2",
            "address_line": "123 Main St, Belmar, NJ 07719",
            "city": "Belmar",
            "state": "NJ",
            "price": 800000,
            "beds": 3,
            "baths": 2.0,
            "sqft": 1500,
            "status": "active",
        }

        with (
            patch("api.pipeline_adapter._load_or_create_session", return_value=session),
            patch("api.pipeline_adapter.dispatch", return_value="Decision narrative."),
            patch("api.pipeline_adapter._finalize_session"),
        ):
            emitted = _run_stream(
                decision_stream(
                    "should I buy it?",
                    _decision(AnswerType.DECISION),
                    pinned_listing,
                    conversation_id="conv-full-cards",
                )
            )

        event_types = [event["type"] for event in emitted]
        first_text_index = event_types.index(events.EVENT_TEXT_DELTA)

        for card_type in (
            events.EVENT_VERDICT,
            events.EVENT_VALUE_THESIS,
            events.EVENT_RISK_PROFILE,
            events.EVENT_STRATEGY_PATH,
            events.EVENT_RENT_OUTLOOK,
        ):
            self.assertIn(card_type, event_types, f"missing {card_type}")
            self.assertLess(
                event_types.index(card_type),
                first_text_index,
                f"{card_type} must emit before the narrative",
            )

    def test_dispatch_stream_emits_risk_card_then_text_then_native_chart(self) -> None:
        session = Session(session_id="risk-contract")
        session.last_risk_view = {
            "address": "526 West End Ave, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "ask_price": 910000,
            "bear_value": 790000,
            "stress_value": 730000,
            "risk_flags": ["flood_zone", "thin_comp_set"],
            "trust_flags": ["weak_town_context"],
            "key_risks": ["Flood-zone exposure"],
            "total_penalty": 0.34,
            "confidence_tier": "moderate",
        }

        with (
            patch("api.pipeline_adapter._load_or_create_session", return_value=session),
            patch("api.pipeline_adapter.dispatch", return_value="Risk narrative for the user."),
            patch("api.pipeline_adapter._finalize_session"),
        ):
            emitted = _run_stream(
                dispatch_stream(
                    "what could go wrong?",
                    _decision(AnswerType.RISK),
                    conversation_id="conv-2",
                )
            )

        event_types = [event["type"] for event in emitted]
        self.assertEqual(event_types[0], events.EVENT_RISK_PROFILE)
        first_text_index = event_types.index(events.EVENT_TEXT_DELTA)
        chart_index = next(
            idx
            for idx, event in enumerate(emitted)
            if event["type"] == events.EVENT_CHART and event.get("kind") == "risk_bar"
        )
        self.assertGreater(chart_index, first_text_index)
        self.assertIsNotNone(emitted[chart_index].get("spec"))

    def test_browse_stream_emits_briefing_cards_before_text_and_scenarios_after(self) -> None:
        session = Session(session_id="browse-contract-real")
        session.last_town_summary = {
            "town": "Belmar",
            "state": "NJ",
            "median_price": 867500,
            "median_ppsf": 516,
            "sold_count": 320,
            "confidence_raw": 0.72,
            "confidence_tier": "strong",
            "doc_count": 4,
            "bullish_signals": ["Main Street redevelopment"],
            "bearish_signals": [],
        }
        session.last_comps_preview = {
            "subject_pid": "subject-1",
            "subject_ask": 767000,
            "count": 2,
            "median_price": 874500,
            "comps": [
                {"property_id": "comp-1", "address": "1302 L Street", "price": 850000},
                {"property_id": "comp-2", "address": "1600 L Street", "price": 899000},
            ],
        }
        session.last_value_thesis_view = {
            "address": "1008 14th Avenue, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "ask_price": 767000,
            "fair_value_base": 723556,
            "premium_discount_pct": 0.057,
            "pricing_view": "above_fair_value",
            "primary_value_source": "current_value",
            "value_drivers": ["walkable Belmar location"],
            "key_value_drivers": ["walkable Belmar location"],
            "what_must_be_true": ["Carry costs need to pencil."],
            "comp_selection_summary": "Nearby saved listings ranked toward the subject.",
            "comps": [
                {
                    "property_id": "comp-1",
                    "address": "1302 L Street",
                    "ask_price": 850000,
                    "source_label": "Saved comp",
                    "feeds_fair_value": True,
                }
            ],
        }
        session.last_strategy_view = {
            "address": "1008 14th Avenue, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "best_path": "buy_if_price_improves",
            "recommendation": "Interesting if you can buy below ask.",
            "pricing_view": "above_fair_value",
            "primary_value_source": "current_value",
            "rental_ease_label": "seasonal/mixed",
            "rental_ease_score": 57.0,
            "rent_support_score": 52.0,
            "liquidity_score": 61.0,
            "monthly_cash_flow": -866,
            "cash_on_cash_return": 0.021,
            "annual_noi": 18500,
        }
        session.last_rent_outlook_view = {
            "address": "1008 14th Avenue, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "entry_basis": 767000,
            "monthly_rent": 2352,
            "effective_monthly_rent": 2234,
            "annual_noi": 18500,
            "rent_source_type": "seasonal_mixed",
            "rental_ease_label": "seasonal/mixed",
            "rental_ease_score": 57.0,
            "horizon_years": 3,
            "future_rent_low": 2300,
            "future_rent_mid": 2410,
            "future_rent_high": 2600,
            "zillow_market_rent": 2500,
            "zillow_rental_comp_count": 3,
            "basis_to_rent_framing": "Current rent annualizes to roughly 3.5% of the current basis.",
            "owner_occupy_then_rent": None,
            "burn_chart_payload": {"series": [{"year": 0, "rent_base": 2234, "rent_bull": 2400, "rent_bear": 2100, "monthly_obligation": 3100}]},
            "ramp_chart_payload": {"series": [{"year": 0, "net_0": -866, "net_3": -866, "net_5": -866}]},
        }
        session.last_projection_view = {
            "address": "1008 14th Avenue, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "ask_price": 767000,
            "bull_case_value": 816046,
            "base_case_value": 764343,
            "bear_case_value": 722117,
            "stress_case_value": 506489,
            "spread": 93928,
        }
        session.last_visual_advice = {
            "value": {
                "title": "Generic Value Title",
                "summary": "Generic summary",
                "companion": "Generic companion",
            },
            "rent": {
                "title": "Generic Rent Title",
                "summary": "Generic rent summary",
                "companion": "Generic rent companion",
            },
        }
        session.current_property_id = "subject-1"

        with (
            patch("api.pipeline_adapter._load_or_create_session", return_value=session),
            patch("api.pipeline_adapter.dispatch", return_value="Strong first-impression narrative."),
            patch(
                "api.pipeline_adapter._focal_listing_from_session",
                return_value={
                    "id": "subject-1",
                    "address_line": "1008 14th Avenue, Belmar, NJ 07719",
                    "city": "Belmar",
                    "state": "NJ",
                    "price": 767000,
                    "beds": 3,
                    "baths": 1.0,
                    "sqft": 960,
                    "status": "active",
                },
            ),
            patch("api.pipeline_adapter._finalize_session"),
        ):
            emitted = _run_stream(
                browse_stream(
                    "what do you think of 1008 14th Avenue, Belmar, NJ",
                    _decision(AnswerType.BROWSE),
                    conversation_id="conv-browse-real",
                )
            )

        event_types = [event["type"] for event in emitted]
        self.assertEqual(
            event_types[:6],
            [
                events.EVENT_TOWN_SUMMARY,
                events.EVENT_COMPS_PREVIEW,
                events.EVENT_VALUE_THESIS,
                events.EVENT_CMA_TABLE,
                events.EVENT_STRATEGY_PATH,
                events.EVENT_RENT_OUTLOOK,
            ],
        )
        first_text_index = event_types.index(events.EVENT_TEXT_DELTA)
        self.assertGreater(event_types.index(events.EVENT_SCENARIO_TABLE), first_text_index)
        self.assertIn(events.EVENT_LISTINGS, event_types)
        self.assertIn("value_opportunity", [event.get("kind") for event in emitted if event["type"] == events.EVENT_CHART])
        self.assertIn("cma_positioning", [event.get("kind") for event in emitted if event["type"] == events.EVENT_CHART])
        self.assertIn("scenario_fan", [event.get("kind") for event in emitted if event["type"] == events.EVENT_CHART])
        self.assertIn("rent_burn", [event.get("kind") for event in emitted if event["type"] == events.EVENT_CHART])
        cma_charts = [
            event for event in emitted if event["type"] == events.EVENT_CHART and event.get("kind") == "cma_positioning"
        ]
        self.assertEqual(len(cma_charts), 1)
        value_chart = next(
            event for event in emitted if event["type"] == events.EVENT_CHART and event.get("kind") == "value_opportunity"
        )
        self.assertEqual(value_chart.get("title"), "Ask vs fair value")
        burn_chart = next(
            event for event in emitted if event["type"] == events.EVENT_CHART and event.get("kind") == "rent_burn"
        )
        ramp_chart = next(
            event for event in emitted if event["type"] == events.EVENT_CHART and event.get("kind") == "rent_ramp"
        )
        self.assertEqual(burn_chart.get("title"), "Rent vs monthly cost")
        self.assertEqual(ramp_chart.get("title"), "Can rent catch up?")

    def test_dispatch_stream_emits_browse_cards_when_browse_turn_uses_generic_adapter(self) -> None:
        session = Session(session_id="browse-contract")
        session.last_town_summary = {
            "town": "Belmar",
            "state": "NJ",
            "median_price": 867500,
            "median_ppsf": 516,
            "sold_count": 320,
            "confidence_raw": 0.72,
            "confidence_tier": "strong",
            "doc_count": 4,
            "bullish_signals": ["Main Street redevelopment"],
            "bearish_signals": [],
        }
        session.last_comps_preview = {
            "subject_pid": "subject-1",
            "subject_ask": 767000,
            "count": 2,
            "median_price": 874500,
            "comps": [
                {"property_id": "comp-1", "address": "1302 L Street", "price": 850000},
                {"property_id": "comp-2", "address": "1600 L Street", "price": 899000},
            ],
        }
        session.last_value_thesis_view = {
            "address": "1008 14th Avenue, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "ask_price": 767000,
            "fair_value_base": 723556,
            "premium_discount_pct": 0.057,
            "pricing_view": "above_fair_value",
            "primary_value_source": "current_value",
            "value_drivers": ["walkable Belmar location"],
            "key_value_drivers": ["walkable Belmar location"],
            "what_must_be_true": ["Carry costs need to pencil."],
            "comp_selection_summary": "Nearby saved listings ranked toward the subject.",
            "comps": [
                {
                    "property_id": "comp-1",
                    "address": "1302 L Street",
                    "ask_price": 850000,
                    "source_label": "Saved comp",
                    "feeds_fair_value": True,
                }
            ],
        }
        session.last_strategy_view = {
            "address": "1008 14th Avenue, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "best_path": "buy_if_price_improves",
            "recommendation": "Interesting if you can buy below ask.",
            "pricing_view": "above_fair_value",
            "primary_value_source": "current_value",
            "rental_ease_label": "seasonal/mixed",
            "rental_ease_score": 57.0,
            "rent_support_score": 52.0,
            "liquidity_score": 61.0,
            "monthly_cash_flow": -866,
            "cash_on_cash_return": 0.021,
            "annual_noi": 18500,
        }
        session.last_rent_outlook_view = {
            "address": "1008 14th Avenue, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "entry_basis": 767000,
            "monthly_rent": 2352,
            "effective_monthly_rent": 2234,
            "annual_noi": 18500,
            "rent_source_type": "seasonal_mixed",
            "rental_ease_label": "seasonal/mixed",
            "rental_ease_score": 57.0,
            "horizon_years": 3,
            "future_rent_low": 2300,
            "future_rent_mid": 2410,
            "future_rent_high": 2600,
            "zillow_market_rent": 2500,
            "zillow_rental_comp_count": 3,
            "basis_to_rent_framing": "Current rent annualizes to roughly 3.5% of the current basis.",
            "owner_occupy_then_rent": None,
            "burn_chart_payload": {"series": [{"year": 0, "rent_base": 2234, "rent_bull": 2400, "rent_bear": 2100, "monthly_obligation": 3100}]},
            "ramp_chart_payload": {"series": [{"year": 0, "net_0": -866, "net_3": -866, "net_5": -866}]},
        }
        session.last_projection_view = {
            "address": "1008 14th Avenue, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "ask_price": 767000,
            "bull_case_value": 816046,
            "base_case_value": 764343,
            "bear_case_value": 722117,
            "stress_case_value": 506489,
            "spread": 93928,
        }
        session.last_visual_advice = {
            "cma": {"title": "Generic CMA Title", "summary": "Generic CMA summary"},
            "scenario": {"title": "Generic Scenario Title", "summary": "Generic scenario summary"},
        }

        with (
            patch("api.pipeline_adapter._load_or_create_session", return_value=session),
            patch("api.pipeline_adapter.dispatch", return_value="Strong first-impression narrative."),
            patch("api.pipeline_adapter._finalize_session"),
        ):
            emitted = _run_stream(
                dispatch_stream(
                    "tell me about 1008 14th Avenue, Belmar, NJ",
                    _decision(AnswerType.BROWSE),
                    conversation_id="conv-browse",
                )
            )

        event_types = [event["type"] for event in emitted]
        self.assertEqual(
            event_types[:6],
            [
                events.EVENT_TOWN_SUMMARY,
                events.EVENT_COMPS_PREVIEW,
                events.EVENT_VALUE_THESIS,
                events.EVENT_CMA_TABLE,
                events.EVENT_STRATEGY_PATH,
                events.EVENT_RENT_OUTLOOK,
            ],
        )
        first_text_index = event_types.index(events.EVENT_TEXT_DELTA)
        self.assertGreater(event_types.index(events.EVENT_SCENARIO_TABLE), first_text_index)
        self.assertIn("value_opportunity", [event.get("kind") for event in emitted if event["type"] == events.EVENT_CHART])
        self.assertIn("cma_positioning", [event.get("kind") for event in emitted if event["type"] == events.EVENT_CHART])
        self.assertIn("scenario_fan", [event.get("kind") for event in emitted if event["type"] == events.EVENT_CHART])
        self.assertIn("rent_burn", [event.get("kind") for event in emitted if event["type"] == events.EVENT_CHART])
        cma_chart = next(
            event for event in emitted if event["type"] == events.EVENT_CHART and event.get("kind") == "cma_positioning"
        )
        self.assertEqual(cma_chart.get("provenance"), ["CMA", "Value Thesis"])
        self.assertEqual(cma_chart.get("title"), "Where the comps sit")
        self.assertEqual(
            len([event for event in emitted if event["type"] == events.EVENT_CHART and event.get("kind") == "cma_positioning"]),
            1,
        )

    def test_listing_translation_carries_cached_street_view(self) -> None:
        facts = {
            "address": "1600 L Street, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "purchase_price": 899000,
            "beds": 3,
            "baths": 2.0,
            "sqft": 1468,
        }
        with patch(
            "api.pipeline_adapter._load_saved_enrichment",
            return_value={
                "google": {
                    "street_view_image_url": "https://maps.googleapis.com/maps/api/streetview?location=40.1815,-74.0212"
                }
            },
        ):
            listing = _to_listing_from_facts("1600-l-street", facts)

        self.assertEqual(
            listing["streetViewImageUrl"],
            "/api/street-view?location=40.1815%2C-74.0212&size=640x360&fov=90&pitch=0",
        )

    def test_rent_turn_clears_stale_decision_views_and_emits_rent_native_charts(self) -> None:
        session = Session(session_id="rent-contract")
        session.last_decision_view = {"stance": "stale"}
        session.last_projection_view = {
            "ask_price": 767000,
            "base_case_value": 764343,
            "bull_case_value": 816046,
            "bear_case_value": 722117,
        }
        session.clear_response_views()
        session.last_rent_outlook_view = {
            "address": "1008 14th Avenue, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "monthly_rent": 2352,
            "effective_monthly_rent": 2234,
            "annual_noi": 18500,
            "rent_source_type": "seasonal_mixed",
            "rental_ease_label": "seasonal/mixed",
            "rental_ease_score": 57.0,
            "horizon_years": 2,
            "future_rent_low": 2300,
            "future_rent_mid": 2410,
            "future_rent_high": 2600,
            "zillow_market_rent": 2500,
            "zillow_rental_comp_count": 3,
            "basis_to_rent_framing": "Current rent annualizes to roughly 4.1% of the current basis.",
            "owner_occupy_then_rent": None,
            "burn_chart_payload": {
                "title": "Rent burn chart",
                "series": [
                    {"year": 0, "rent_base": 2234, "rent_bull": 2400, "rent_bear": 2100, "monthly_obligation": 3100},
                    {"year": 1, "rent_base": 2301, "rent_bull": 2472, "rent_bear": 2142, "monthly_obligation": 3100},
                ],
            },
            "ramp_chart_payload": {
                "title": "Rent ramp and break-even",
                "current_rent": 2234,
                "monthly_obligation": 3100,
                "today_cash_flow": -866,
                "break_even_years": {"0": None, "3": 7, "5": 5},
                "series": [
                    {"year": 0, "net_0": -866, "net_3": -866, "net_5": -866},
                    {"year": 1, "net_0": -866, "net_3": -799, "net_5": -754},
                ],
            },
        }
        session.last_strategy_view = {
            "address": "1008 14th Avenue, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "best_path": "hold_to_rent",
            "recommendation": "This gets more interesting if you buy well below the current ask.",
            "pricing_view": "below_fair_value",
            "primary_value_source": "current_value",
            "rental_ease_label": "seasonal/mixed",
            "rental_ease_score": 57.0,
            "rent_support_score": 52.0,
            "liquidity_score": 61.0,
            "monthly_cash_flow": -866,
            "cash_on_cash_return": 0.021,
            "annual_noi": 18500,
        }

        with (
            patch("api.pipeline_adapter._load_or_create_session", return_value=session),
            patch("api.pipeline_adapter.dispatch", return_value="Rent-forward narrative."),
            patch("api.pipeline_adapter._finalize_session"),
        ):
            emitted = _run_stream(
                dispatch_stream(
                    "what if we pay 650k and rent it for a couple years?",
                    _decision(AnswerType.RENT_LOOKUP),
                    conversation_id="conv-3",
                )
            )

        event_types = [event["type"] for event in emitted]
        self.assertNotIn(events.EVENT_VERDICT, event_types)
        self.assertIn(events.EVENT_RENT_OUTLOOK, event_types)
        self.assertIn(events.EVENT_STRATEGY_PATH, event_types)
        chart_kinds = [
            event.get("kind")
            for event in emitted
            if event["type"] == events.EVENT_CHART
        ]
        self.assertIn("rent_burn", chart_kinds)
        self.assertIn("rent_ramp", chart_kinds)
        self.assertNotIn("scenario_fan", chart_kinds)
        burn_chart = next(
            event for event in emitted if event["type"] == events.EVENT_CHART and event.get("kind") == "rent_burn"
        )
        self.assertEqual(burn_chart.get("provenance"), ["Rent Outlook", "rent_x_cost"])


class VerdictFromViewTests(unittest.TestCase):
    """AUDIT 1.2.4: `_verdict_from_view` now round-trips the persisted
    decision-view dict through a Pydantic model. Happy-path shape must be
    preserved; malformed input must not crash the SSE emitter."""

    def _full_view(self) -> dict:
        return {
            "pid": "123-main-st-belmar-nj",
            "address": "123 Main St, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "decision_stance": "buy_if_price_improves",
            "primary_value_source": "current_value",
            "ask_price": 800000,
            "all_in_basis": 820000,
            "fair_value_base": 760000,
            "value_low": 735000,
            "value_high": 790000,
            "ask_premium_pct": 0.0526,
            "basis_premium_pct": 0.0789,
            "trust_flags": ["thin_comp_set"],
            "trust_summary": {"confidence": 0.72, "band": "medium"},
            "what_must_be_true": ["comps hold"],
            "key_risks": ["flood exposure"],
            "why_this_stance": ["ask premium above fair range"],
            "what_changes_my_view": ["listing drops 5%"],
            "contradiction_count": 0,
            "blocked_thesis_warnings": [],
            "overrides_applied": {"renovation_capex": 25000},
        }

    def test_happy_path_preserves_wire_shape(self) -> None:
        payload = _verdict_from_view(self._full_view())
        self.assertEqual(payload["address"], "123 Main St, Belmar, NJ 07719")
        self.assertEqual(payload["stance"], "buy_if_price_improves")
        self.assertEqual(payload["ask_price"], 800000)
        self.assertEqual(payload["trust_flags"], ["thin_comp_set"])
        self.assertEqual(payload["trust_summary"], {"confidence": 0.72, "band": "medium"})
        self.assertEqual(payload["overrides_applied"], {"renovation_capex": 25000})
        # UI expects stance, not decision_stance — the projector renames.
        self.assertNotIn("decision_stance", payload)

    def test_missing_fields_default_to_none_or_empty(self) -> None:
        payload = _verdict_from_view({})
        self.assertIsNone(payload["address"])
        self.assertIsNone(payload["stance"])
        self.assertEqual(payload["trust_flags"], [])
        self.assertEqual(payload["trust_summary"], {})
        self.assertEqual(payload["overrides_applied"], {})

    def test_extra_keys_are_ignored_not_rejected(self) -> None:
        """Persisted sessions may carry keys that predate schema changes.
        `_DecisionView` uses extra='ignore' so replay still works."""
        view = self._full_view()
        view["legacy_decision"] = "BUY"  # extra key from a prior shape
        view["random_breadcrumb"] = {"foo": "bar"}
        payload = _verdict_from_view(view)
        self.assertEqual(payload["stance"], "buy_if_price_improves")
        self.assertNotIn("legacy_decision", payload)

    def test_bad_types_fall_back_to_empty_verdict(self) -> None:
        """A type mismatch (e.g. trust_flags stored as dict instead of list)
        should not crash the SSE emitter. The projector logs and falls back
        to an all-default verdict."""
        view = self._full_view()
        view["trust_flags"] = {"not": "a list"}  # wrong type
        payload = _verdict_from_view(view)
        # Fallback shape is fully populated with defaults, not partial.
        self.assertIsNone(payload["address"])
        self.assertEqual(payload["trust_flags"], [])
        self.assertEqual(payload["trust_summary"], {})


if __name__ == "__main__":
    unittest.main()
