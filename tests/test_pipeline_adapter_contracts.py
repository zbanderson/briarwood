from __future__ import annotations

import asyncio
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from api import events
from api.pipeline_adapter import (
    _native_cma_chart,
    _native_risk_chart,
    _sanitize_valuation_module_comps,
    _seed_session_for_pinned,
    _to_listing_from_facts,
    _track_modules,
    _valuation_comps_from_view,
    _verdict_from_view,
    browse_stream,
    decision_stream,
    dispatch_stream,
)
from briarwood.agent.router import AnswerType, RouterDecision
from briarwood.agent.session import Session
from briarwood.representation.agent import (
    ClaimType,
    RepresentationPlan,
    RepresentationSelection,
)


def _run_stream(stream):
    async def _collect():
        return [event async for event in stream]

    return asyncio.run(_collect())


def _decision(answer_type: AnswerType) -> RouterDecision:
    return RouterDecision(answer_type=answer_type, confidence=0.99, reason="test")


class PipelineAdapterContractTests(unittest.TestCase):
    class _ScriptedLLM:
        def __init__(self, response):
            self._response = response

        def complete_structured(self, **_kwargs):
            return self._response

    def test_seed_session_for_saved_pin_preserves_live_listing_price_context(self) -> None:
        session = Session(session_id="seed-pin")
        pinned = {
            "id": "saved-pid",
            "address_line": "1223 Briarwood Rd, Belmar, NJ 07719",
            "city": "Belmar",
            "state": "NJ",
            "price": 699000,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "saved-pid").mkdir()
            with patch("api.pipeline_adapter._SAVED_ROOT", root):
                seeded = _seed_session_for_pinned(session, pinned)
        self.assertEqual(seeded, "saved-pid")
        self.assertEqual(session.current_property_id, "saved-pid")
        self.assertEqual(session.current_live_listing["property_id"], "saved-pid")
        self.assertEqual(session.current_live_listing["ask_price"], 699000)

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
            "signal_items": [
                {
                    "id": "sig-1",
                    "bucket": "bullish",
                    "title": "1201 Main Street redevelopment plan",
                    "status": "approved",
                    "display_line": "1201 Main Street redevelopment plan (approved)",
                    "project_summary": "Approved supply item tied to 1201 Main Street redevelopment plan at 1201 Main Street, covering about 24 units. Briarwood treats it as a watch item rather than a confirmed catalyst over the medium term, with likely effects on future_supply, home_values.",
                    "signal_type": "supply",
                    "location_label": "1201 Main Street",
                    "development_lat": 40.1815,
                    "development_lng": -74.0212,
                    "confidence": 0.82,
                    "facts": ["24 residential units were approved."],
                    "inference": "This may add moderate supply.",
                    "evidence_excerpt": "Application for 1201 Main Street mixed-use redevelopment with 24 residential units was approved.",
                    "source_document_id": "doc-1",
                    "source_title": "Belmar Planning Board Minutes",
                    "source_type": "planning_board_minutes",
                    "source_url": "https://example.com/belmar/minutes",
                    "source_date": "2026-02-11T00:00:00Z",
                }
            ],
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

        # partial_data_warning banners (F7 / NF1) may ride ahead of the core
        # cards — they are meta-events about reliability, not content. Strip
        # them before asserting the core-card ordering contract.
        content_events = [
            event for event in emitted if event["type"] != events.EVENT_PARTIAL_DATA_WARNING
        ]
        event_types = [event["type"] for event in content_events]
        self.assertEqual(
            event_types[:3],
            [events.EVENT_VERDICT, events.EVENT_TOWN_SUMMARY, events.EVENT_COMPS_PREVIEW],
        )
        first_text_index = event_types.index(events.EVENT_TEXT_DELTA)
        self.assertGreater(event_types.index(events.EVENT_SCENARIO_TABLE), first_text_index)
        scenario_chart_index = next(
            idx
            for idx, event in enumerate(content_events)
            if event["type"] == events.EVENT_CHART and event.get("kind") == "scenario_fan"
        )
        self.assertGreater(scenario_chart_index, first_text_index)
        self.assertIsNotNone(content_events[scenario_chart_index].get("spec"))
        town_event = next(event for event in content_events if event["type"] == events.EVENT_TOWN_SUMMARY)
        self.assertEqual(town_event["signal_items"][0]["id"], "sig-1")
        scenario_table = next(event for event in content_events if event["type"] == events.EVENT_SCENARIO_TABLE)
        self.assertEqual(scenario_table.get("basis_label"), "entry basis")
        self.assertEqual(content_events[scenario_chart_index]["spec"].get("basis_label"), "entry basis")

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

    def test_decision_stream_emits_primary_proof_chart_before_secondary_representation_charts(self) -> None:
        session = Session(session_id="decision-primary-chart")
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
            "lead_reason": "The all-in basis is running about 7.9% above Briarwood's fair-value read.",
            "evidence_items": ["Fair value is $760,000 against a working basis of $820,000."],
            "next_step_teaser": "Open the value chart next to see how the ask sits against Briarwood's fair-value anchor.",
            "primary_chart_claim": "price_position",
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
            "comps": [{"address": "101 Ocean Ave", "ask_price": 755000}],
        }
        session.last_market_support_view = {
            "address": "123 Main St, Belmar, NJ 07719",
            "comps": [{"address": "201 Ocean Ave", "ask_price": 765000}],
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
            "id": "subject-proof-chart",
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
            patch(
                "api.pipeline_adapter._representation_charts",
                return_value=(
                    [
                        events.chart(
                            kind="scenario_fan",
                            spec={
                                "kind": "scenario_fan",
                                "ask_price": 800000,
                                "bull_case_value": 910000,
                                "base_case_value": 845000,
                                "bear_case_value": 760000,
                            },
                            supports_claim="scenario_range",
                            why_this_chart="Secondary scenario chart.",
                        )
                    ],
                    [],
                ),
            ),
            patch("api.pipeline_adapter._finalize_session"),
        ):
            emitted = _run_stream(
                decision_stream(
                    "Underwrite this property.",
                    _decision(AnswerType.DECISION),
                    pinned_listing,
                    conversation_id="conv-primary-chart",
                )
            )

        first_text_index = next(
            idx for idx, event in enumerate(emitted) if event["type"] == events.EVENT_TEXT_DELTA
        )
        first_chart = next(
            event for event in emitted[first_text_index + 1 :] if event["type"] == events.EVENT_CHART
        )
        self.assertEqual(first_chart.get("kind"), "value_opportunity")
        self.assertEqual(first_chart.get("supports_claim"), "price_position")
        self.assertIn("proves the verdict", first_chart.get("why_this_chart", ""))

    def test_representation_drift_without_lost_surface_does_not_emit_warning_banner(self) -> None:
        """LLM chart selections that can be deterministically backfilled should
        not surface a user-facing `representation_plan` warning."""
        session = Session(session_id="decision-representation-drift")
        session.last_decision_view = {
            "address": "1008 14th Avenue, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "decision_stance": "buy_if_price_improves",
            "primary_value_source": "current_value",
            "ask_price": 767000,
            "all_in_basis": 767000,
            "fair_value_base": 720644,
            "value_low": 690000,
            "value_high": 803827,
            "ask_premium_pct": 0.0604,
            "basis_premium_pct": 0.0604,
            "trust_flags": ["thin_comp_set"],
            "what_must_be_true": ["Thin comp set gets resolved."],
            "key_risks": ["Flood-zone exposure"],
            "overrides_applied": {},
        }
        session.last_value_thesis_view = {
            "address": "1008 14th Avenue, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "ask_price": 767000,
            "fair_value_base": 720644,
            "premium_discount_pct": 0.0604,
            "pricing_view": "above_fair_value",
            "primary_value_source": "current_value",
            "value_drivers": ["walkable Belmar location"],
            "key_value_drivers": ["walkable Belmar location"],
            "what_must_be_true": ["Thin comp set gets resolved."],
            "comps": [],
        }
        session.last_risk_view = {
            "address": "1008 14th Avenue, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "ask_price": 767000,
            "bear_value": 685581,
            "stress_value": 640000,
            "risk_flags": ["flood_zone"],
            "trust_flags": ["thin_comp_set"],
            "key_risks": ["Flood-zone exposure"],
            "total_penalty": 0.22,
            "confidence_tier": "strong",
        }
        llm = self._ScriptedLLM(
            RepresentationPlan(
                selections=[
                    RepresentationSelection(
                        claim="Value drivers support the read.",
                        claim_type=ClaimType.VALUE_DRIVERS,
                        supporting_evidence=[],
                        chart_id="value_opportunity",
                        source_view=None,
                    ),
                    RepresentationSelection(
                        claim="Risk composition is available.",
                        claim_type=ClaimType.RISK_COMPOSITION,
                        supporting_evidence=[],
                        chart_id="risk_bar",
                        source_view=None,
                    ),
                ]
            )
        )

        pinned_listing = {
            "id": "subject-3",
            "address_line": "1008 14th Avenue, Belmar, NJ 07719",
            "city": "Belmar",
            "state": "NJ",
            "price": 767000,
            "beds": 3,
            "baths": 1.0,
            "sqft": 960,
            "status": "active",
        }

        with (
            patch("api.pipeline_adapter._load_or_create_session", return_value=session),
            patch("api.pipeline_adapter.get_llm", return_value=llm),
            patch("api.pipeline_adapter.dispatch", return_value="Decision narrative."),
            patch("api.pipeline_adapter._finalize_session"),
        ):
            emitted = _run_stream(
                decision_stream(
                    "Analyze 1008 14th Avenue, Belmar, NJ 07719",
                    _decision(AnswerType.DECISION),
                    pinned_listing,
                    conversation_id="conv-representation-drift",
                )
            )

        warning_sections = [
            event["section"]
            for event in emitted
            if event["type"] == events.EVENT_PARTIAL_DATA_WARNING
        ]
        self.assertNotIn("representation_plan", warning_sections)
        chart_kinds = [
            event.get("kind")
            for event in emitted
            if event["type"] == events.EVENT_CHART
        ]
        self.assertIn("value_opportunity", chart_kinds)
        self.assertIn("risk_bar", chart_kinds)

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
        # F2: browse does not run the valuation module, so comps must be
        # empty here. Live-market comps go into last_market_support_view below.
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
            "comp_selection_summary": None,
            "comps": [],
        }
        session.last_market_support_view = {
            "address": "1008 14th Avenue, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "comp_selection_summary": "Live Zillow market comps ranked toward the subject.",
            "comps": [
                {
                    "property_id": "comp-1",
                    "address": "1302 L Street",
                    "ask_price": 850000,
                    "source_label": "Live market comp",
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
        # F2: browse has no valuation-module output, so valuation_comps must
        # NOT be emitted here.
        self.assertNotIn(events.EVENT_VALUATION_COMPS, event_types)
        # CMA Phase 4a Cycle 5: BROWSE no longer emits the standalone
        # market_support_comps panel — the cma_positioning chart surfaces
        # the same comps with provenance markers, and emitting both caused
        # a visible mid-stream layout reflow. DECISION / EDGE turns still
        # emit the panel as a drilldown.
        self.assertNotIn(events.EVENT_MARKET_SUPPORT_COMPS, event_types)
        expected_head = [
            events.EVENT_TOWN_SUMMARY,
            events.EVENT_COMPS_PREVIEW,
            events.EVENT_VALUE_THESIS,
            events.EVENT_STRATEGY_PATH,
            events.EVENT_RENT_OUTLOOK,
        ]
        self.assertEqual(event_types[: len(expected_head)], expected_head)
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
        # F2: browse does not run the valuation module, so comps must be
        # empty here. Live-market comps go into last_market_support_view below.
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
            "comp_selection_summary": None,
            "comps": [],
        }
        session.last_market_support_view = {
            "address": "1008 14th Avenue, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "comp_selection_summary": "Live Zillow market comps ranked toward the subject.",
            "comps": [
                {
                    "property_id": "comp-1",
                    "address": "1302 L Street",
                    "ask_price": 850000,
                    "source_label": "Live market comp",
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
        # F2: browse has no valuation-module output, so valuation_comps must
        # NOT be emitted here.
        self.assertNotIn(events.EVENT_VALUATION_COMPS, event_types)
        # CMA Phase 4a Cycle 5: BROWSE no longer emits the standalone
        # market_support_comps panel — the cma_positioning chart surfaces
        # the same comps with provenance markers, and emitting both caused
        # a visible mid-stream layout reflow. DECISION / EDGE turns still
        # emit the panel as a drilldown.
        self.assertNotIn(events.EVENT_MARKET_SUPPORT_COMPS, event_types)
        expected_head = [
            events.EVENT_TOWN_SUMMARY,
            events.EVENT_COMPS_PREVIEW,
            events.EVENT_VALUE_THESIS,
            events.EVENT_STRATEGY_PATH,
            events.EVENT_RENT_OUTLOOK,
        ]
        self.assertEqual(event_types[: len(expected_head)], expected_head)
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

    def test_dispatch_stream_emits_structured_research_signal_items(self) -> None:
        session = Session(session_id="research-contract")
        session.last_research_view = {
            "town": "Belmar",
            "state": "NJ",
            "confidence_label": "High",
            "narrative_summary": "Belmar has constructive catalysts and a live watchlist.",
            "bullish_signals": ["1201 Main Street redevelopment plan (approved)"],
            "bearish_signals": [],
            "watch_items": ["BOROUGH OF BELMAR PLANNING BOARD SPECIAL (mentioned)"],
            "signal_items": [
                {
                    "id": "sig-1",
                    "bucket": "bullish",
                    "title": "1201 Main Street redevelopment plan",
                    "status": "approved",
                    "display_line": "1201 Main Street redevelopment plan (approved)",
                    "project_summary": "Approved supply item tied to 1201 Main Street redevelopment plan at 1201 Main Street, covering about 24 units. Briarwood treats it as a watch item rather than a confirmed catalyst over the medium term, with likely effects on future_supply, home_values.",
                    "signal_type": "supply",
                    "location_label": "1201 Main Street",
                    "development_lat": 40.1815,
                    "development_lng": -74.0212,
                    "confidence": 0.82,
                    "facts": ["24 residential units were approved."],
                    "inference": "This may add moderate supply.",
                    "evidence_excerpt": "Application for 1201 Main Street mixed-use redevelopment with 24 residential units was approved.",
                    "source_document_id": "doc-1",
                    "source_title": "Belmar Planning Board Minutes",
                    "source_type": "planning_board_minutes",
                    "source_url": "https://example.com/belmar/minutes",
                    "source_date": "2026-02-11T00:00:00Z",
                }
            ],
            "document_count": 4,
            "warnings": [],
        }

        with (
            patch("api.pipeline_adapter._load_or_create_session", return_value=session),
            patch("api.pipeline_adapter.dispatch", return_value="Town research narrative."),
            patch("api.pipeline_adapter._finalize_session"),
        ):
            emitted = _run_stream(
                dispatch_stream(
                    "what's driving Belmar?",
                    _decision(AnswerType.RESEARCH),
                    conversation_id="conv-research-signal-items",
                )
            )

        research_event = next(event for event in emitted if event["type"] == events.EVENT_RESEARCH_UPDATE)
        self.assertEqual(research_event["signal_items"][0]["id"], "sig-1")
        self.assertEqual(research_event["signal_items"][0]["development_lat"], 40.1815)

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
            "lead_reason": "The all-in basis is running about 7.9% above Briarwood's fair-value read.",
            "evidence_items": ["Fair value is $760,000 against a working basis of $820,000."],
            "next_step_teaser": "Open the value chart next to see how the ask sits against Briarwood's fair-value anchor.",
            "overrides_applied": {"renovation_capex": 25000},
        }

    def test_happy_path_preserves_wire_shape(self) -> None:
        payload = _verdict_from_view(self._full_view())
        self.assertEqual(payload["address"], "123 Main St, Belmar, NJ 07719")
        self.assertEqual(payload["stance"], "buy_if_price_improves")
        self.assertEqual(payload["ask_price"], 800000)
        self.assertEqual(payload["trust_flags"], ["thin_comp_set"])
        self.assertEqual(payload["trust_summary"], {"confidence": 0.72, "band": "medium"})
        self.assertEqual(payload["lead_reason"], self._full_view()["lead_reason"])
        self.assertEqual(payload["evidence_items"], self._full_view()["evidence_items"])
        self.assertEqual(payload["next_step_teaser"], self._full_view()["next_step_teaser"])
        self.assertEqual(payload["overrides_applied"], {"renovation_capex": 25000})
        # UI expects stance, not decision_stance — the projector renames.
        self.assertNotIn("decision_stance", payload)

    def test_missing_fields_default_to_none_or_empty(self) -> None:
        payload = _verdict_from_view({})
        self.assertIsNone(payload["address"])
        self.assertIsNone(payload["stance"])
        self.assertEqual(payload["trust_flags"], [])
        self.assertEqual(payload["trust_summary"], {})
        self.assertEqual(payload["evidence_items"], [])
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

    def test_legacy_decision_engine_labels_are_rejected(self) -> None:
        """Guard against legacy-vocabulary shape drift: if some upstream helper
        ever emits BUY / LEAN BUY / NEUTRAL / LEAN PASS / AVOID, the stance
        validator must reject it and fall back to the empty verdict, same path
        as any other unknown stance label."""
        for legacy_label in ("BUY", "LEAN BUY", "NEUTRAL", "LEAN PASS", "AVOID"):
            view = self._full_view()
            view["decision_stance"] = legacy_label
            payload = _verdict_from_view(view)
            # Fallback path — no partial pollution of the verdict.
            self.assertIsNone(payload["stance"], f"{legacy_label!r} should be rejected")
            self.assertIsNone(payload["address"])

    def test_known_stance_values_round_trip(self) -> None:
        """Every DecisionStance value must survive validation — otherwise the
        allowlist is drifting from the enum."""
        from briarwood.routing_schema import DecisionStance

        for stance in DecisionStance:
            view = self._full_view()
            view["decision_stance"] = stance.value
            payload = _verdict_from_view(view)
            self.assertEqual(payload["stance"], stance.value)


class RiskProfileEventShapeTests(unittest.TestCase):
    """AUDIT O.6: risk_profile is emitted by splatting `session.last_risk_view`
    through `events.risk_profile`. The shape is not enforced by a schema, so
    drift in the producer (dispatch.py sets the view) can silently leak or
    drop keys. Pin the wire contract here: every key the TS `RiskProfileEvent`
    relies on must survive the splat, and types must be preserved."""

    def _session_with_risk(self) -> Session:
        session = Session(session_id="risk-shape")
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
        return session

    def _emit(self, session: Session) -> dict:
        with (
            patch("api.pipeline_adapter._load_or_create_session", return_value=session),
            patch("api.pipeline_adapter.dispatch", return_value="Risk narrative."),
            patch("api.pipeline_adapter._finalize_session"),
        ):
            emitted = _run_stream(
                dispatch_stream(
                    "what could go wrong?",
                    _decision(AnswerType.RISK),
                    conversation_id="risk-shape-conv",
                )
            )
        return next(event for event in emitted if event["type"] == events.EVENT_RISK_PROFILE)

    def test_all_documented_fields_present_on_emit(self) -> None:
        """Every field the TS RiskProfileEvent carries must be on the wire."""
        payload = self._emit(self._session_with_risk())
        for key in (
            "type",
            "address",
            "town",
            "state",
            "ask_price",
            "bear_value",
            "stress_value",
            "risk_flags",
            "trust_flags",
            "key_risks",
            "total_penalty",
            "confidence_tier",
        ):
            self.assertIn(key, payload, f"missing field {key!r}")

    def test_list_fields_preserve_type_and_content(self) -> None:
        payload = self._emit(self._session_with_risk())
        self.assertIsInstance(payload["risk_flags"], list)
        self.assertIsInstance(payload["trust_flags"], list)
        self.assertIsInstance(payload["key_risks"], list)
        self.assertEqual(payload["risk_flags"], ["flood_zone", "thin_comp_set"])
        self.assertEqual(payload["trust_flags"], ["weak_town_context"])
        self.assertEqual(payload["key_risks"], ["Flood-zone exposure"])

    def test_numeric_and_enum_fields_preserve_value(self) -> None:
        payload = self._emit(self._session_with_risk())
        self.assertEqual(payload["ask_price"], 910000)
        self.assertEqual(payload["bear_value"], 790000)
        self.assertEqual(payload["stress_value"], 730000)
        self.assertAlmostEqual(payload["total_penalty"], 0.34)
        self.assertEqual(payload["confidence_tier"], "moderate")

    def test_confidence_tier_is_one_of_allowed_values(self) -> None:
        """The TS contract pins confidence_tier to 'strong' | 'moderate' |
        'thin' | null. If the producer ever introduces a new tier string,
        this test catches the drift before it reaches the frontend."""
        payload = self._emit(self._session_with_risk())
        self.assertIn(payload["confidence_tier"], {"strong", "moderate", "thin", None})


class ScenarioTableSpreadUnitTests(unittest.TestCase):
    """AUDIT 1.4.4: scenario_table emits `spread_unit="dollars"` so consumers
    never have to guess the unit of `spread`. Other modules produce a
    percent-valued `spread_pct` and the two must not be mixed."""

    def test_scenario_table_event_carries_spread_unit_literal(self) -> None:
        payload = events.scenario_table(
            rows=[{"scenario": "Bull", "value": 900000, "delta_pct": 0.1, "growth_rate": 0.03, "adjustment_pct": 0.05}],
            address="123 Main St",
            ask_price=800000,
            basis_label="entry basis",
            spread=150000,
        )
        self.assertEqual(payload["spread"], 150000)
        self.assertEqual(payload["spread_unit"], "dollars")

    def test_spread_unit_present_even_when_spread_is_none(self) -> None:
        """The unit tag stays pinned so consumers can rely on the field
        shape regardless of whether the projection produced a spread."""
        payload = events.scenario_table(rows=[])
        self.assertIsNone(payload["spread"])
        self.assertEqual(payload["spread_unit"], "dollars")


class NativeRiskChartTests(unittest.TestCase):
    """AUDIT 1.4.3: the risk_bar chart spec now carries `value_unit` and
    `value_source` so downstream can disambiguate the meaning of `value`
    (share of total penalty, not abstract "pts") and detect the fallback
    case where every bar collapses to the same synthesized default."""

    def test_computed_path_sets_value_source_computed(self) -> None:
        spec = _native_risk_chart(
            {
                "risk_flags": ["construction", "concentration"],
                "trust_flags": ["thin_comp_set"],
                "total_penalty": 0.4,
                "ask_price": 800000,
                "bear_value": 700000,
                "stress_value": 620000,
            }
        )
        self.assertIsNotNone(spec)
        spec_body = spec["spec"]
        self.assertEqual(spec_body["value_unit"], "penalty_share")
        self.assertEqual(spec_body["value_source"], "computed")
        # Sanity on the split: 0.4 / 2 flags = 0.2 per risk bar.
        risk_values = [
            item["value"] for item in spec_body["items"] if item["tone"] == "risk"
        ]
        self.assertEqual(risk_values, [0.2, 0.2])

    def test_missing_total_penalty_flags_fallback_source(self) -> None:
        spec = _native_risk_chart(
            {
                "risk_flags": ["construction", "concentration", "flood"],
                "trust_flags": [],
                # No total_penalty — each bar falls back to the 0.12 default.
            }
        )
        self.assertIsNotNone(spec)
        spec_body = spec["spec"]
        self.assertEqual(spec_body["value_unit"], "penalty_share")
        self.assertEqual(spec_body["value_source"], "fallback")
        risk_values = [
            item["value"] for item in spec_body["items"] if item["tone"] == "risk"
        ]
        # All identical — that is the ambiguity `value_source="fallback"` flags.
        self.assertEqual(len(set(risk_values)), 1)

    def test_no_flags_returns_none(self) -> None:
        spec = _native_risk_chart({"risk_flags": [], "trust_flags": []})
        self.assertIsNone(spec)


class GroundingAnchorAttributionTests(unittest.TestCase):
    """AUDIT 1.5.4: a narrative-only turn (no structured card events) must
    still credit modules the LLM cites via `[[Module:field:value]]` grounding
    anchors. Without this, the `modules_ran` badge row underreports the
    cascade — e.g., a risk-only card plus narrative that cites ValuationModel
    and ValueThesis would show just "Risk Profile"."""

    def test_anchors_in_grounding_event_credit_named_modules(self) -> None:
        async def _stream():
            yield events.grounding_annotations(
                anchors=[
                    {"module": "ValuationModel", "field": "fair_value_base", "value": 850000},
                    {"module": "ValueThesis", "field": "thesis_type", "value": "scarcity"},
                ]
            )

        collected = _run_stream(_track_modules(_stream()))
        modules_ran = [ev for ev in collected if ev.get("type") == events.EVENT_MODULES_RAN]
        self.assertEqual(len(modules_ran), 1)
        items = modules_ran[0]["items"]
        labels = {item["label"] for item in items}
        self.assertIn("Valuation Model", labels)
        self.assertIn("Value Thesis", labels)
        for item in items:
            if item["label"] in {"Valuation Model", "Value Thesis"}:
                self.assertIn("narrative", item["contributed_to"])

    def test_unknown_anchor_module_is_silently_ignored(self) -> None:
        """Anchors that don't map to a known module (malformed LLM output,
        future labels that haven't been wired yet) must not break the turn —
        they just don't get credited."""
        async def _stream():
            yield events.grounding_annotations(
                anchors=[{"module": "MadeUpModule", "field": "x", "value": 1}]
            )

        collected = _run_stream(_track_modules(_stream()))
        modules_ran = [ev for ev in collected if ev.get("type") == events.EVENT_MODULES_RAN]
        self.assertEqual(modules_ran, [])

    def test_event_and_anchor_merge_on_same_module(self) -> None:
        """When an event fires AND an anchor cites the same module, the module
        appears once with both contribution slots."""
        async def _stream():
            yield {"type": events.EVENT_VALUE_THESIS, "thesis_type": "scarcity"}
            yield events.grounding_annotations(
                anchors=[{"module": "ValueThesis", "field": "thesis_type", "value": "scarcity"}]
            )

        collected = _run_stream(_track_modules(_stream()))
        modules_ran = [ev for ev in collected if ev.get("type") == events.EVENT_MODULES_RAN]
        self.assertEqual(len(modules_ran), 1)
        items = modules_ran[0]["items"]
        value_thesis = [i for i in items if i["module"] == "value_thesis"]
        self.assertEqual(len(value_thesis), 1)
        contributed = value_thesis[0]["contributed_to"]
        self.assertIn(events.EVENT_VALUE_THESIS, contributed)
        self.assertIn("narrative", contributed)


class ValuationCompsProvenanceTests(unittest.TestCase):
    """F2 contract guard: ``valuation_comps`` events must only carry comps
    that actually fed the fair value computation. Live-market rows, saved
    neighbor context comps, and anything without a valuation-module provenance
    flag must never reach that event — otherwise the UI card ("Comps that fed
    fair value") would be a lie.

    These tests pin the contract two ways:
    1. Emission filter (``_sanitize_valuation_module_comps``) drops bad rows
       and reports drift so the stream can surface a ``partial_data_warning``
       (NEW-V-007: the guard used to raise; softened so a single stray row
       no longer aborts the whole response).
    2. Source projection (``_valuation_comps_from_view``) returns ``None``
       when the view has no comps, so no event is emitted at all.
    """

    _VALUATION_ROW = {
        "property_id": "saved-1202-m-street",
        "address": "1202 M Street, Belmar, NJ 07719",
        "beds": 3,
        "baths": 2.0,
        "ask_price": 735000.0,
        "source_label": "Saved comp",
        "selected_by": "valuation",
        "feeds_fair_value": True,
    }
    _LIVE_MARKET_ROW = {
        "property_id": "1302-l-street",
        "address": "1302 L Street, Belmar, NJ 07719",
        "beds": 3,
        "baths": 2.0,
        "ask_price": 850000.0,
        "source_label": "Live market comp",
        "selected_by": "briarwood",
        # hallmark of a non-valuation row: feeds_fair_value flag is absent
        # (a valuation-module row ALWAYS sets it True, per _selected_comp_rows)
    }

    def test_guard_accepts_valuation_module_rows(self) -> None:
        payload = {"rows": [dict(self._VALUATION_ROW)]}
        cleaned, drift = _sanitize_valuation_module_comps(payload)
        self.assertFalse(drift)
        self.assertIsNotNone(cleaned)
        self.assertEqual(len(cleaned["rows"]), 1)

    def test_guard_drops_live_market_row_without_feeds_fair_value(self) -> None:
        payload = {
            "rows": [dict(self._VALUATION_ROW), dict(self._LIVE_MARKET_ROW)],
        }
        cleaned, drift = _sanitize_valuation_module_comps(payload)
        self.assertTrue(drift)
        self.assertIsNotNone(cleaned)
        # Only the valuation-module row survives.
        self.assertEqual(len(cleaned["rows"]), 1)
        self.assertEqual(cleaned["rows"][0]["selected_by"], "valuation")

    def test_guard_drops_row_with_feeds_fair_value_false(self) -> None:
        row = dict(self._VALUATION_ROW)
        row["feeds_fair_value"] = False
        payload = {"rows": [row]}
        cleaned, drift = _sanitize_valuation_module_comps(payload)
        self.assertTrue(drift)
        # All rows dropped → no payload, but verdict itself is still reliable.
        self.assertIsNone(cleaned)

    def test_guard_drops_non_dict_row(self) -> None:
        payload = {"rows": ["not a dict", dict(self._VALUATION_ROW)]}
        cleaned, drift = _sanitize_valuation_module_comps(payload)
        self.assertTrue(drift)
        self.assertIsNotNone(cleaned)
        self.assertEqual(len(cleaned["rows"]), 1)

    def test_guard_preserves_non_row_payload_fields(self) -> None:
        payload = {
            "address": "1008 14th Avenue",
            "town": "Belmar",
            "state": "NJ",
            "summary": "Saved comps ranked toward subject.",
            "rows": [dict(self._VALUATION_ROW)],
        }
        cleaned, drift = _sanitize_valuation_module_comps(payload)
        self.assertFalse(drift)
        self.assertEqual(cleaned["address"], "1008 14th Avenue")
        self.assertEqual(cleaned["summary"], "Saved comps ranked toward subject.")

    def test_valuation_projection_returns_none_on_empty_view(self) -> None:
        # Browse populates value_thesis_view without comps; we must not emit
        # a valuation_comps event in that case.
        view = {"address": "x", "town": "y", "state": "NJ", "comps": []}
        self.assertIsNone(_valuation_comps_from_view(view))

    def test_valuation_projection_preserves_rows_and_summary(self) -> None:
        view = {
            "address": "1008 14th Avenue",
            "town": "Belmar",
            "state": "NJ",
            "comp_selection_summary": "Saved comps ranked toward subject.",
            "comps": [dict(self._VALUATION_ROW)],
        }
        payload = _valuation_comps_from_view(view)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["summary"], "Saved comps ranked toward subject.")
        self.assertEqual(payload["rows"][0]["property_id"], "saved-1202-m-street")
        # And the filter must pass what the projection produced.
        _cleaned, drift = _sanitize_valuation_module_comps(payload)
        self.assertFalse(drift)

    def test_valuation_comps_event_source_is_valuation_module(self) -> None:
        """Every valuation_comps event must carry the ``source`` literal so
        downstream consumers (UI, telemetry) can discriminate it from the
        market_support_comps event without peeking at row shape."""
        event = events.valuation_comps(
            {"rows": [dict(self._VALUATION_ROW)], "summary": "foo"}
        )
        self.assertEqual(event["type"], events.EVENT_VALUATION_COMPS)
        self.assertEqual(event["source"], "valuation_module")

    def test_market_support_comps_event_source_is_live_market(self) -> None:
        event = events.market_support_comps(
            {"rows": [dict(self._LIVE_MARKET_ROW)], "summary": "foo"}
        )
        self.assertEqual(event["type"], events.EVENT_MARKET_SUPPORT_COMPS)
        self.assertEqual(event["source"], "live_market")



class CmaPositioningChartProvenanceTests(unittest.TestCase):
    """CMA Phase 4a Cycle 5: each comp dict in the cma_positioning chart
    spec carries ``listing_status`` and ``is_cross_town`` so the React
    frontend can render distinct markers (filled circle / open triangle /
    filled circle with dashed outline)."""

    def _build_value_view(self) -> dict[str, object]:
        return {
            "address": "1008 14th Avenue, Belmar, NJ 07719",
            "ask_price": 767000,
            "fair_value_base": 720000,
            "value_low": 695000,
            "value_high": 745000,
        }

    def _build_market_view(self) -> dict[str, object]:
        return {
            "address": "1008 14th Avenue, Belmar, NJ 07719",
            "comp_selection_summary": "Comp set: 2 SOLD (1 cross-town) + 1 ACTIVE.",
            "comps": [
                {
                    "address": "905 13th Ave",
                    "ask_price": 715000,
                    "listing_status": "sold",
                    "is_cross_town": False,
                },
                {
                    "address": "1402 Ocean Ave, Bradley Beach",
                    "ask_price": 760000,
                    "listing_status": "sold",
                    "is_cross_town": True,
                },
                {
                    "address": "812 16th Ave",
                    "ask_price": 799000,
                    "listing_status": "active",
                    "is_cross_town": False,
                },
            ],
        }

    def test_cma_chart_spec_carries_listing_status_and_cross_town(self) -> None:
        event = _native_cma_chart(self._build_value_view(), market_view=self._build_market_view())
        self.assertIsNotNone(event)
        comps = event["spec"]["comps"]  # type: ignore[index]
        self.assertEqual(len(comps), 3)
        same_town_sold = next(c for c in comps if c["address"] == "905 13th Ave")
        cross_town_sold = next(c for c in comps if c["address"] == "1402 Ocean Ave, Bradley Beach")
        active = next(c for c in comps if c["address"] == "812 16th Ave")
        self.assertEqual(same_town_sold["listing_status"], "sold")
        self.assertFalse(same_town_sold["is_cross_town"])
        self.assertEqual(cross_town_sold["listing_status"], "sold")
        self.assertTrue(cross_town_sold["is_cross_town"])
        self.assertEqual(active["listing_status"], "active")
        self.assertFalse(active["is_cross_town"])

    def test_cma_chart_legend_lists_provenance_markers(self) -> None:
        event = _native_cma_chart(self._build_value_view(), market_view=self._build_market_view())
        self.assertIsNotNone(event)
        labels = [item["label"] for item in event["legend"]]  # type: ignore[index]
        self.assertIn("SOLD comp", labels)
        self.assertIn("ACTIVE comp", labels)
        self.assertIn("Cross-town SOLD", labels)

    def test_cma_chart_legacy_rows_default_provenance_to_safe_values(self) -> None:
        """Pre-Cycle-5 cached rows lack `listing_status` / `is_cross_town`.
        The chart payload still emits the keys (with safe defaults) so the
        TypeScript reader doesn't have to special-case missing fields."""
        market_view = {
            "comps": [
                {
                    "address": "Legacy comp",
                    "ask_price": 700000,
                    # No listing_status / is_cross_town keys — pre-Cycle-5 row.
                },
            ],
        }
        event = _native_cma_chart(self._build_value_view(), market_view=market_view)
        self.assertIsNotNone(event)
        comps = event["spec"]["comps"]  # type: ignore[index]
        self.assertEqual(len(comps), 1)
        self.assertIsNone(comps[0]["listing_status"])
        self.assertFalse(comps[0]["is_cross_town"])


if __name__ == "__main__":
    unittest.main()
