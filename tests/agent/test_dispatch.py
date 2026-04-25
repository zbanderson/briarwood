"""Dispatch handlers — tool-call budget + routing contracts.

Verifies:
- Lookup handler does NOT call analyze_property.
- Decision handler runs the analyzer once and returns the structured stance.
- Handlers tolerate a missing LLM client (deterministic fallback mode).
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from briarwood.agent.dispatch import (
    _analysis_overrides,
    _build_town_summary,
    _deepen_browse_followup,
    _escalate_browse_affirmative,
    handle_edge,
    contextualize_decision,
    dispatch,
    handle_browse,
    handle_decision,
    handle_lookup,
    handle_micro_location,
    handle_projection,
    handle_research,
    handle_rent_lookup,
    handle_search,
)
from briarwood.agent.property_view import PropertyView
from briarwood.agent.router import AnswerType, RouterDecision
from briarwood.agent.session import Session, Turn
from briarwood.agent.tools import LiveListingCandidate
from briarwood.agent.tools import LiveListingDecision
from briarwood.agent.tools import PromotedPropertyRecord
from briarwood.agent.tools import PropertyBrief
from briarwood.agent.tools import RentOutlook
from briarwood.agent.tools import RenovationResaleOutlook
from briarwood.agent.tools import CMAResult
from briarwood.agent.tools import ComparableProperty
from briarwood.agent.tools import ToolUnavailable
from briarwood.agent.tools import _clean_address_query


REF = "526-west-end-ave"


class LookupHandlerTests(unittest.TestCase):
    def test_lookup_never_calls_analyze_property(self) -> None:
        decision = RouterDecision(
            AnswerType.LOOKUP, confidence=0.9, target_refs=[REF], reason="test"
        )
        session = Session()
        with patch("briarwood.agent.dispatch.analyze_property") as analyzer:
            response = handle_lookup("what's the address?", decision, session, llm=None)
        analyzer.assert_not_called()
        self.assertIn("West End", response)
        self.assertEqual(session.current_property_id, REF)

    def test_clean_address_query_extracts_address_from_natural_question(self) -> None:
        extracted = _clean_address_query(
            "how much do you think 1228 briarwood road, belmar, nj is worth?"
        )
        self.assertEqual(extracted, "1228 briarwood road, belmar, nj")

    def test_lookup_listing_history_question_does_not_invent_date(self) -> None:
        decision = RouterDecision(
            AnswerType.LOOKUP, confidence=0.9, target_refs=[REF], reason="test"
        )
        session = Session()
        with patch(
            "briarwood.agent.dispatch.get_property_summary",
            return_value={"address": "526 West End Ave, Avon By The Sea, NJ 07717"},
        ), patch(
            "briarwood.agent.dispatch._load_property_facts",
            return_value={"listing_date": None, "price_history": []},
        ):
            response = handle_lookup(
                "when was the last time it was listed?",
                decision,
                session,
                llm=None,
            )
        self.assertIn("don't have a recorded listing-date event", response)
        self.assertNotIn("2026", response)


class SearchHandlerInvestmentScreenTests(unittest.TestCase):
    def test_search_cap_rate_runs_saved_corpus_screen(self) -> None:
        decision = RouterDecision(
            AnswerType.SEARCH, confidence=0.6, target_refs=[], reason="llm classify"
        )
        with patch(
            "briarwood.agent.dispatch.screen_saved_listings_by_cap_rate",
            return_value=[
                type(
                    "Screened",
                    (),
                    {
                        "property_id": "briarwood-rd-belmar",
                        "address": "1223 Briarwood Rd, Belmar, NJ 07719",
                        "ask_price": 674200.0,
                        "annual_noi": 38000.0,
                        "cap_rate": 0.056,
                        "monthly_rent": 4200.0,
                        "rent_source_type": "estimated",
                    },
                )()
            ],
        ) as screener:
            response = handle_search(
                "can you show me houses in belmar nj that have a 5.5 cap rate?",
                decision,
                Session(),
                llm=None,
            )
        screener.assert_called_once()
        self.assertIn("Saved-corpus cap-rate screen", response)
        self.assertIn("cap 5.6%", response)
        self.assertIn("underwrite whether that cap rate is actually durable", response)


class DecisionHandlerTests(unittest.TestCase):
    def test_analysis_overrides_sync_live_pinned_ask_without_marking_user_override(self) -> None:
        session = Session(
            current_live_listing={"property_id": REF, "ask_price": 699000.0},
            selected_search_result={"property_id": REF, "ask_price": 699000.0},
        )
        with patch(
            "briarwood.agent.dispatch.get_property_summary",
            return_value={"ask_price": 674200.0},
        ):
            effective, explicit = _analysis_overrides(
                "should I buy this?",
                pid=REF,
                session=session,
            )
        self.assertEqual(explicit, {})
        self.assertEqual(effective, {"ask_price": 699000.0})

    def test_decision_runs_analyze_and_reports_stance(self) -> None:
        """Clean case: no research-fixable trust flags → single analyze, no research."""
        decision = RouterDecision(
            AnswerType.DECISION, confidence=0.9, target_refs=[REF], reason="test"
        )
        session = Session()
        fake_payload = {
            "decision_stance": "buy_if_price_improves",
            "primary_value_source": "current_value",
            "trust_flags": ["incomplete_carry_inputs"],  # NOT research-fixable
            "value_position": {
                "fair_value_base": 1_379_080,
                "ask_price": 1_499_000,
                "premium_discount_pct": 0.087,
            },
            "what_must_be_true": [],
        }
        with patch(
            "briarwood.agent.property_view.analyze_property", return_value=fake_payload
        ) as analyzer, patch(
            "briarwood.agent.property_view.get_property_summary",
            return_value={"address": "526 West End Ave", "ask_price": 1_499_000},
        ), patch("briarwood.agent.dispatch.research_town") as researcher:
            response = handle_decision(
                "should I buy this?", decision, session, llm=None
            )
        analyzer.assert_called_once_with(REF, overrides={})
        researcher.assert_not_called()
        self.assertIn("buy if price improves", response)
        self.assertEqual(session.current_property_id, REF)
        self.assertTrue(response.startswith(session.last_surface_narrative))

    def test_decision_value_question_uses_fair_value_anchor(self) -> None:
        decision = RouterDecision(
            AnswerType.DECISION, confidence=0.9, target_refs=[REF], reason="test"
        )
        session = Session()
        payload = {
            "decision_stance": "pass_unless_changes",
            "primary_value_source": "current_value",
            "trust_flags": ["incomplete_carry_inputs"],
            "value_position": {
                "fair_value_base": 804396.62,
                "value_low": 742000.0,
                "value_high": 861000.0,
                "ask_price": None,
            },
            "what_must_be_true": [],
        }
        with patch(
            "briarwood.agent.property_view.analyze_property", return_value=payload
        ), patch(
            "briarwood.agent.property_view.get_property_summary",
            return_value={"address": "1600 L Street, Belmar, NJ 07719", "ask_price": None},
        ):
            response = handle_decision(
                "what is this house worth?",
                decision,
                session,
                llm=None,
            )
        self.assertIn("$804,397", response)
        self.assertIn("$742,000 to $861,000", response)
        self.assertNotIn("unknown", response.lower())

    def test_decision_splits_valuation_and_market_support_comps(self) -> None:
        decision = RouterDecision(
            AnswerType.DECISION, confidence=0.9, target_refs=[REF], reason="test"
        )
        session = Session()
        view = PropertyView(
            pid=REF,
            address="1008 14th Avenue, Belmar, NJ 07719",
            town="Belmar",
            state="NJ",
            beds=3,
            baths=1.0,
            ask_price=767000.0,
            bcv=None,
            pricing_view="appears_fully_valued",
            fair_value_base=720644.0,
            value_low=690000.0,
            value_high=803827.0,
            all_in_basis=767000.0,
            ask_premium_pct=0.0604,
            basis_premium_pct=0.0604,
            decision_stance="buy_if_price_improves",
            primary_value_source="current_value",
            trust_flags=("thin_comp_set",),
            trust_summary={"band": "Moderate confidence"},
            what_must_be_true=("Thin comp set gets resolved.",),
            key_risks=("Thin comp set",),
            why_this_stance=("Current basis sits above fair value.",),
            what_changes_my_view=("Price improves toward fair value.",),
            contradiction_count=0,
            blocked_thesis_warnings=("Thin comp set",),
            unified={"key_value_drivers": ["Beach-adjacent location"]},
        )
        live_cma = CMAResult(
            property_id=REF,
            address=view.address,
            town="Belmar",
            state="NJ",
            ask_price=767000.0,
            fair_value_base=720644.0,
            value_low=690000.0,
            value_high=803827.0,
            pricing_view="appears_fully_valued",
            primary_value_source="current_value",
            comp_selection_summary="Live Zillow market comps ranked toward the subject.",
            comps=[
                ComparableProperty(
                    property_id="1302-l-street",
                    address="1302 L Street, Belmar, NJ 07719",
                    town="Belmar",
                    state="NJ",
                    beds=3,
                    baths=2.0,
                    ask_price=850000.0,
                    blocks_to_beach=None,
                    source_label="Live market comp",
                    source_summary="Live Zillow market comp",
                )
            ],
            confidence_notes=[],
            missing_fields=[],
        )
        valuation_module_thesis = {
            "ask_price": 767000.0,
            "fair_value_base": 720644.0,
            "comp_selection_summary": "Valuation module comps used for fair value.",
            "comps": [
                {
                    "property_id": "saved-1202-m-street",
                    "address": "1202 M Street, Belmar, NJ 07719",
                    "beds": 3,
                    "baths": 2.0,
                    "ask_price": 735000.0,
                    "blocks_to_beach": None,
                    "source_label": "Saved comp",
                    "source_summary": "Saved nearby comp",
                    "inclusion_reason": "Closest match on layout.",
                    "selected_by": "valuation",
                    "feeds_fair_value": True,
                },
            ],
        }
        with patch(
            "briarwood.agent.dispatch.PropertyView.load",
            return_value=view,
        ), patch(
            "briarwood.agent.dispatch.get_cma",
            return_value=live_cma,
        ), patch(
            "briarwood.agent.dispatch.get_value_thesis",
            return_value=valuation_module_thesis,
        ), patch(
            "briarwood.agent.dispatch._build_town_summary",
            return_value={"town": "Belmar", "state": "NJ"},
        ), patch(
            "briarwood.agent.dispatch.get_projection",
            return_value={
                "ask_price": 767000.0,
                "base_case_value": 737726.0,
                "bull_case_value": 795946.0,
                "bear_case_value": 685581.0,
            },
        ), patch(
            "briarwood.agent.dispatch.get_property_summary",
            return_value={"address": view.address, "town": "Belmar", "state": "NJ"},
        ), patch(
            "briarwood.agent.dispatch.build_property_brief",
            return_value=PropertyBrief(
                property_id=REF,
                address=view.address,
                town="Belmar",
                state="NJ",
                beds=3,
                baths=1.0,
                ask_price=767000.0,
                pricing_view="appears_fully_valued",
                analysis_depth_used="decision",
                recommendation="Buy if the price improves.",
                decision="buy",
                decision_stance="buy_if_price_improves",
                best_path="Proceed carefully.",
                key_value_drivers=["Beach-adjacent location"],
                key_risks=["Thin comp set"],
                trust_flags=["thin_comp_set"],
                next_questions=["What entry price works?"],
                fair_value_base=720644.0,
                ask_premium_pct=0.0604,
                primary_value_source="current_value",
                recommended_next_run="edge",
            ),
        ), patch(
            "briarwood.agent.dispatch.get_property_presentation",
            return_value={},
        ):
            handle_decision("should I buy this?", decision, session, llm=None)

        # comps_preview still reflects the live CMA (used for the inline preview)
        self.assertEqual(session.last_comps_preview["comps"][0]["property_id"], "1302-l-street")
        # F2: value_thesis.comps now must be valuation-module comps only.
        self.assertEqual(
            session.last_value_thesis_view["comps"][0]["property_id"],
            "saved-1202-m-street",
        )
        self.assertEqual(
            session.last_value_thesis_view["comp_selection_summary"],
            "Valuation module comps used for fair value.",
        )
        # F2: live-market comps land in last_market_support_view, not value_thesis.
        self.assertIsNotNone(session.last_market_support_view)
        self.assertEqual(
            session.last_market_support_view["comps"][0]["property_id"],
            "1302-l-street",
        )
        self.assertEqual(
            session.last_market_support_view["comp_selection_summary"],
            "Live Zillow market comps ranked toward the subject.",
        )

    def test_decision_populates_risk_strategy_and_rent_slots_on_first_turn(self) -> None:
        decision = RouterDecision(
            AnswerType.DECISION, confidence=0.9, target_refs=[REF], reason="test"
        )
        session = Session()
        view = PropertyView(
            pid=REF,
            address="1008 14th Avenue, Belmar, NJ 07719",
            town="Belmar",
            state="NJ",
            beds=3,
            baths=1.0,
            ask_price=767000.0,
            bcv=None,
            pricing_view="appears_fully_valued",
            fair_value_base=720644.0,
            value_low=690000.0,
            value_high=803827.0,
            all_in_basis=767000.0,
            ask_premium_pct=0.0604,
            basis_premium_pct=0.0604,
            decision_stance="buy_if_price_improves",
            primary_value_source="current_value",
            trust_flags=("thin_comp_set",),
            trust_summary={"band": "Moderate confidence"},
            what_must_be_true=("Thin comp set gets resolved.",),
            key_risks=("Thin comp set",),
            why_this_stance=("Current basis sits above fair value.",),
            what_changes_my_view=("Price improves toward fair value.",),
            contradiction_count=0,
            blocked_thesis_warnings=("Thin comp set",),
            unified={"key_value_drivers": ["Beach-adjacent location"]},
        )
        with patch(
            "briarwood.agent.dispatch.PropertyView.load",
            return_value=view,
        ), patch(
            "briarwood.agent.dispatch._build_town_summary",
            return_value={"town": "Belmar", "state": "NJ"},
        ), patch(
            "briarwood.agent.dispatch.get_cma",
            return_value=None,
        ), patch(
            "briarwood.agent.dispatch._build_comps_preview",
            return_value=None,
        ), patch(
            "briarwood.agent.dispatch._build_decision_value_thesis",
            return_value={"comps": []},
        ), patch(
            "briarwood.agent.dispatch._build_market_support_view",
            return_value=None,
        ), patch(
            "briarwood.agent.dispatch.get_projection",
            return_value={
                "ask_price": 767000.0,
                "base_case_value": 737726.0,
                "bull_case_value": 795946.0,
                "bear_case_value": 685581.0,
                "stress_case_value": 640000.0,
            },
        ), patch(
            "briarwood.agent.dispatch.get_risk_profile",
            return_value={
                "ask_price": 767000.0,
                "risk_flags": ["flood_zone"],
                "trust_flags": ["thin_comp_set"],
                "key_risks": ["Flood-zone exposure"],
                "total_penalty": 0.22,
            },
        ), patch(
            "briarwood.agent.dispatch.get_strategy_fit",
            return_value={
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
            },
        ), patch(
            "briarwood.agent.dispatch.get_rent_estimate",
            return_value={
                "monthly_rent": 2352,
                "effective_monthly_rent": 2234,
                "annual_noi": 18500,
                "rent_source_type": "seasonal_mixed",
                "rental_ease_label": "seasonal/mixed",
                "rental_ease_score": 57.0,
            },
        ), patch(
            "briarwood.agent.dispatch.get_rent_outlook",
            return_value=RentOutlook(
                property_id=REF,
                address=view.address,
                entry_basis=767000,
                current_monthly_rent=2352,
                effective_monthly_rent=2234,
                annual_noi=18500,
                rent_source_type="seasonal_mixed",
                rental_ease_label="seasonal/mixed",
                rental_ease_score=57.0,
                horizon_years=3,
                future_rent_low=2300,
                future_rent_mid=2410,
                future_rent_high=2600,
                basis_to_rent_framing="Current rent annualizes to roughly 3.5% of the current basis.",
                owner_occupy_then_rent=None,
                zillow_market_rent=2500,
                zillow_market_rent_low=2200,
                zillow_market_rent_high=2900,
                zillow_rental_comp_count=3,
                market_context_note=None,
                burn_chart_payload={"series": [{"year": 0, "rent_base": 2234, "rent_bull": 2400, "rent_bear": 2100, "monthly_obligation": 3100}]},
                ramp_chart_payload={"series": [{"year": 0, "net_0": -866, "net_3": -866, "net_5": -866}]},
                confidence_notes=[],
            ),
        ), patch(
            "briarwood.agent.dispatch.get_property_summary",
            return_value={"address": view.address, "town": "Belmar", "state": "NJ"},
        ), patch(
            "briarwood.agent.dispatch.build_property_brief",
            return_value=PropertyBrief(
                property_id=REF,
                address=view.address,
                town="Belmar",
                state="NJ",
                beds=3,
                baths=1.0,
                ask_price=767000.0,
                pricing_view="appears_fully_valued",
                analysis_depth_used="decision",
                recommendation="Buy if the price improves.",
                decision="buy",
                decision_stance="buy_if_price_improves",
                best_path="Proceed carefully.",
                key_value_drivers=["Beach-adjacent location"],
                key_risks=["Thin comp set"],
                trust_flags=["thin_comp_set"],
                next_questions=["What entry price works?"],
                fair_value_base=720644.0,
                ask_premium_pct=0.0604,
                primary_value_source="current_value",
                recommended_next_run="edge",
            ),
        ), patch(
            "briarwood.agent.dispatch.get_property_presentation",
            return_value={},
        ):
            handle_decision("should I buy this?", decision, session, llm=None)

        self.assertIsNotNone(session.last_risk_view)
        self.assertEqual(session.last_risk_view["risk_flags"], ["flood_zone"])
        self.assertEqual(session.last_risk_view["bear_value"], 685581.0)
        self.assertEqual(session.last_risk_view["stress_value"], 640000.0)
        self.assertIsNotNone(session.last_strategy_view)
        self.assertEqual(session.last_strategy_view["best_path"], "buy_if_price_improves")
        self.assertIsNotNone(session.last_rent_outlook_view)
        self.assertEqual(session.last_rent_outlook_view["monthly_rent"], 2352)
        self.assertEqual(session.last_rent_outlook_view["horizon_years"], 3)

    def test_decision_value_questions_include_expanded_grounding_payload(self) -> None:
        decision = RouterDecision(
            AnswerType.DECISION, confidence=0.9, target_refs=[REF], reason="test"
        )
        session = Session()
        view = PropertyView(
            pid=REF,
            address="1008 14th Avenue, Belmar, NJ 07719",
            town="Belmar",
            state="NJ",
            beds=3,
            baths=1.0,
            ask_price=767000.0,
            bcv=None,
            pricing_view="appears_fully_valued",
            fair_value_base=720644.0,
            value_low=690000.0,
            value_high=803827.0,
            all_in_basis=767000.0,
            ask_premium_pct=0.0604,
            basis_premium_pct=0.0604,
            decision_stance="buy_if_price_improves",
            primary_value_source="current_value",
            trust_flags=("thin_comp_set",),
            trust_summary={"band": "Moderate confidence"},
            what_must_be_true=("Thin comp set gets resolved.",),
            key_risks=("Thin comp set",),
            why_this_stance=("Current basis sits above fair value.",),
            what_changes_my_view=("Price improves toward fair value.",),
            contradiction_count=0,
            blocked_thesis_warnings=("Thin comp set",),
            unified={
                "key_value_drivers": ["Beach-adjacent location"],
                "valuation_x_risk": {
                    "adjustments": {
                        "risk_adjusted_fair_value": 685000.0,
                        "required_discount": 0.11,
                    }
                },
            },
        )
        with patch(
            "briarwood.agent.dispatch.PropertyView.load",
            return_value=view,
        ), patch(
            "briarwood.agent.dispatch._build_town_summary",
            return_value={"town": "Belmar", "state": "NJ"},
        ), patch(
            "briarwood.agent.dispatch.get_cma",
            return_value=None,
        ), patch(
            "briarwood.agent.dispatch._build_comps_preview",
            return_value=None,
        ), patch(
            "briarwood.agent.dispatch._build_decision_value_thesis",
            return_value={"comps": []},
        ), patch(
            "briarwood.agent.dispatch._build_market_support_view",
            return_value=None,
        ), patch(
            "briarwood.agent.dispatch.get_projection",
            return_value={"ask_price": 767000.0},
        ), patch(
            "briarwood.agent.dispatch.get_risk_profile",
            return_value={},
        ), patch(
            "briarwood.agent.dispatch.get_strategy_fit",
            return_value={},
        ), patch(
            "briarwood.agent.dispatch.get_rent_estimate",
            return_value={},
        ), patch(
            "briarwood.agent.dispatch.get_rent_outlook",
            side_effect=ToolUnavailable("skip rent"),
        ), patch(
            "briarwood.agent.dispatch.get_property_summary",
            return_value={"address": view.address, "town": "Belmar", "state": "NJ"},
        ), patch(
            "briarwood.agent.dispatch.build_property_brief",
            return_value=PropertyBrief(
                property_id=REF,
                address=view.address,
                town="Belmar",
                state="NJ",
                beds=3,
                baths=1.0,
                ask_price=767000.0,
                pricing_view="appears_fully_valued",
                analysis_depth_used="decision",
                recommendation="Buy if the price improves.",
                decision="buy",
                decision_stance="buy_if_price_improves",
                best_path="Proceed carefully.",
                key_value_drivers=["Beach-adjacent location"],
                key_risks=["Thin comp set"],
                trust_flags=["thin_comp_set"],
                next_questions=["What entry price works?"],
                fair_value_base=720644.0,
                ask_premium_pct=0.0604,
                primary_value_source="current_value",
                recommended_next_run="edge",
            ),
        ), patch(
            "briarwood.agent.dispatch.get_property_presentation",
            return_value={},
        ), patch(
            "briarwood.agent.dispatch.complete_and_verify",
            return_value=(
                "Anchored value answer.",
                {
                    "tier": "decision_value",
                    "sentences_total": 0,
                    "sentences_with_violations": 0,
                    "ungrounded_declaration": False,
                    "anchor_count": 0,
                    "anchors": [],
                    "violations": [],
                },
            ),
        ) as complete:
            handle_decision("What would change your value view?", decision, session, llm=object())

        structured_inputs = complete.call_args.kwargs["structured_inputs"]
        self.assertEqual(structured_inputs["address"], view.address)
        self.assertEqual(structured_inputs["ask_price"], 767000.0)
        self.assertEqual(structured_inputs["fair_value_base"], 720644.0)
        self.assertEqual(structured_inputs["ask_premium_pct"], 0.0604)
        self.assertEqual(structured_inputs["price_gap_pct"], 0.0604)
        self.assertEqual(structured_inputs["risk_adjusted_fair_value"], 685000.0)
        self.assertEqual(structured_inputs["required_discount"], 0.11)

    def test_decision_summary_payload_includes_underwrite_digest(self) -> None:
        decision = RouterDecision(
            AnswerType.DECISION, confidence=0.9, target_refs=[REF], reason="test"
        )
        session = Session()
        view = PropertyView(
            pid=REF,
            address="1008 14th Avenue, Belmar, NJ 07719",
            town="Belmar",
            state="NJ",
            beds=3,
            baths=1.0,
            ask_price=767000.0,
            bcv=None,
            pricing_view="appears_fully_valued",
            fair_value_base=720644.0,
            value_low=690000.0,
            value_high=803827.0,
            all_in_basis=767000.0,
            ask_premium_pct=0.0604,
            basis_premium_pct=0.0604,
            decision_stance="buy_if_price_improves",
            primary_value_source="current_value",
            trust_flags=("thin_comp_set",),
            trust_summary={"band": "Moderate confidence"},
            what_must_be_true=("Thin comp set gets resolved.",),
            key_risks=("Thin comp set",),
            why_this_stance=("Current basis sits above fair value.",),
            what_changes_my_view=("Price improves toward fair value.",),
            contradiction_count=0,
            blocked_thesis_warnings=("Thin comp set",),
            unified={"key_value_drivers": ["Beach-adjacent location"]},
        )
        with patch(
            "briarwood.agent.dispatch.PropertyView.load",
            return_value=view,
        ), patch(
            "briarwood.agent.dispatch._build_town_summary",
            return_value={"town": "Belmar", "state": "NJ"},
        ), patch(
            "briarwood.agent.dispatch.get_cma",
            return_value=None,
        ), patch(
            "briarwood.agent.dispatch._build_comps_preview",
            return_value=None,
        ), patch(
            "briarwood.agent.dispatch._build_decision_value_thesis",
            return_value={
                "ask_price": 767000.0,
                "fair_value_base": 720644.0,
                "premium_discount_pct": 0.0604,
                "key_value_drivers": ["Beach-adjacent location"],
                "comps": [{"address": "101 Ocean Ave", "ask_price": 755000.0}],
            },
        ), patch(
            "briarwood.agent.dispatch._build_market_support_view",
            return_value={
                "comps": [{"address": "102 Ocean Ave", "ask_price": 760000.0}]
            },
        ), patch(
            "briarwood.agent.dispatch.get_projection",
            return_value={"ask_price": 767000.0},
        ), patch(
            "briarwood.agent.dispatch.get_risk_profile",
            return_value={},
        ), patch(
            "briarwood.agent.dispatch._risk_view_from_profile",
            return_value={
                "risk_flags": ["thin_comp_set"],
                "key_risks": ["Thin comp set"],
            },
        ), patch(
            "briarwood.agent.dispatch.get_strategy_fit",
            return_value={},
        ), patch(
            "briarwood.agent.dispatch._strategy_view_from_fit",
            return_value={"best_path": "Wait for a better basis."},
        ), patch(
            "briarwood.agent.dispatch.get_rent_estimate",
            return_value={},
        ), patch(
            "briarwood.agent.dispatch.get_rent_outlook",
            return_value={},
        ), patch(
            "briarwood.agent.dispatch._rent_outlook_view_from_result",
            return_value={},
        ), patch(
            "briarwood.agent.dispatch.get_property_summary",
            return_value={"address": view.address, "town": "Belmar", "state": "NJ"},
        ), patch(
            "briarwood.agent.dispatch.build_property_brief",
            return_value=PropertyBrief(
                property_id=REF,
                address=view.address,
                town="Belmar",
                state="NJ",
                beds=3,
                baths=1.0,
                ask_price=767000.0,
                pricing_view="appears_fully_valued",
                analysis_depth_used="decision",
                recommendation="Buy if the price improves.",
                decision="buy",
                decision_stance="buy_if_price_improves",
                best_path="Wait for a better basis.",
                key_value_drivers=["Beach-adjacent location"],
                key_risks=["Thin comp set"],
                trust_flags=["thin_comp_set"],
                next_questions=["What entry price works?"],
                fair_value_base=720644.0,
                ask_premium_pct=0.0604,
                primary_value_source="current_value",
                recommended_next_run="edge",
            ),
        ), patch(
            "briarwood.agent.dispatch.get_property_presentation",
            return_value={},
        ), patch(
            "briarwood.agent.dispatch.complete_and_verify",
            return_value=(
                "Compact underwrite.",
                {
                    "tier": "decision_summary",
                    "sentences_total": 0,
                    "sentences_with_violations": 0,
                    "ungrounded_declaration": False,
                    "anchor_count": 0,
                    "anchors": [],
                    "violations": [],
                },
            ),
        ) as complete:
            handle_decision("Underwrite this property.", decision, session, llm=object())

        structured_inputs = complete.call_args.kwargs["structured_inputs"]
        self.assertEqual(
            structured_inputs["lead_reason"],
            "The all-in basis is running about 6.0% above Briarwood's fair-value read.",
        )
        self.assertEqual(
            structured_inputs["primary_thesis"],
            "Current basis sits above fair value.",
        )
        self.assertIn(
            "Fair value is $720,644 against a working basis of $767,000.",
            structured_inputs["top_supporting_facts"],
        )
        self.assertEqual(
            structured_inputs["top_risk_or_trust_caveat"],
            "Thin comp set.",
        )
        self.assertEqual(
            structured_inputs["flip_condition"],
            "Price improves toward fair value.",
        )
        self.assertIn("value chart", structured_inputs["next_surface_hook"].lower())
        self.assertEqual(
            session.last_decision_view["lead_reason"],
            structured_inputs["lead_reason"],
        )
        self.assertEqual(
            session.last_decision_view["evidence_items"],
            structured_inputs["top_supporting_facts"],
        )
        self.assertEqual(
            session.last_decision_view["next_step_teaser"],
            structured_inputs["next_surface_hook"],
        )


class DecisionPartialDataWarningTests(unittest.TestCase):
    """F7: enrichment failures must not silently degrade — handle_decision
    records each failure on ``session.last_partial_data_warnings`` so the
    SSE layer can surface a banner."""

    def _base_view(self) -> PropertyView:
        return PropertyView(
            pid=REF,
            address="526 West End Ave, Avon By The Sea, NJ 07717",
            town="Avon By The Sea",
            state="NJ",
            beds=3,
            baths=2.0,
            ask_price=1_499_000.0,
            bcv=None,
            pricing_view="appears_fully_valued",
            fair_value_base=1_379_080.0,
            all_in_basis=1_499_000.0,
            decision_stance="buy_if_price_improves",
            primary_value_source="current_value",
            trust_flags=("incomplete_carry_inputs",),
        )

    def _run_with_failures(self, *, fail: set[str]) -> Session:
        decision = RouterDecision(
            AnswerType.DECISION, confidence=0.9, target_refs=[REF], reason="test"
        )
        session = Session()
        view = self._base_view()

        def _maybe_raise(section: str, ok_value):
            if section in fail:
                raise RuntimeError(f"forced {section} failure")
            return ok_value

        town_summary = {"town": view.town, "state": view.state}
        cma_result = CMAResult(
            property_id=REF,
            address=view.address,
            town=view.town,
            state=view.state,
            ask_price=view.ask_price,
            fair_value_base=view.fair_value_base,
            value_low=None,
            value_high=None,
            pricing_view=view.pricing_view,
            primary_value_source=view.primary_value_source,
            comp_selection_summary="Live comps.",
            comps=[],
            confidence_notes=[],
            missing_fields=[],
        )
        with patch(
            "briarwood.agent.dispatch.PropertyView.load", return_value=view
        ), patch(
            "briarwood.agent.dispatch._build_town_summary",
            side_effect=lambda *a, **kw: _maybe_raise("town_summary", town_summary),
        ), patch(
            "briarwood.agent.dispatch.get_cma",
            side_effect=lambda *a, **kw: _maybe_raise("cma", cma_result),
        ), patch(
            "briarwood.agent.dispatch._build_comps_preview",
            side_effect=lambda *a, **kw: _maybe_raise(
                "comps_preview", {"comps": []}
            ),
        ), patch(
            "briarwood.agent.dispatch._build_decision_value_thesis",
            side_effect=lambda *a, **kw: _maybe_raise(
                "value_thesis", {"comps": []}
            ),
        ), patch(
            "briarwood.agent.dispatch._build_market_support_view",
            side_effect=lambda *a, **kw: _maybe_raise(
                "market_support_comps", {"comps": []}
            ),
        ), patch(
            "briarwood.agent.dispatch.get_projection",
            side_effect=lambda *a, **kw: _maybe_raise(
                "projection",
                {
                    "ask_price": view.ask_price,
                    "base_case_value": view.fair_value_base,
                    "bull_case_value": view.fair_value_base * 1.1,
                    "bear_case_value": view.fair_value_base * 0.9,
                },
            ),
        ), patch(
            "briarwood.agent.dispatch.get_property_summary",
            return_value={"address": view.address, "town": view.town, "state": view.state},
        ):
            handle_decision("should I buy this?", decision, session, llm=None)
        return session

    def test_town_summary_failure_records_warning(self) -> None:
        session = self._run_with_failures(fail={"town_summary"})
        sections = [w["section"] for w in session.last_partial_data_warnings]
        self.assertIn("town_summary", sections)
        self.assertIsNone(session.last_town_summary)
        # Core decision still lands — verdict view populated.
        self.assertIsNotNone(session.last_decision_view)

    def test_each_enrichment_failure_records_distinct_warning(self) -> None:
        for section in [
            "town_summary",
            "cma",
            "comps_preview",
            "value_thesis",
            "market_support_comps",
            "projection",
        ]:
            with self.subTest(section=section):
                session = self._run_with_failures(fail={section})
                sections = [w["section"] for w in session.last_partial_data_warnings]
                self.assertIn(section, sections)
                entry = next(
                    w for w in session.last_partial_data_warnings if w["section"] == section
                )
                self.assertIn("forced", entry["reason"])
                self.assertTrue(entry["verdict_reliable"])


class EdgeHandlerTests(unittest.TestCase):
    def test_cma_includes_support_comps(self) -> None:
        decision = RouterDecision(
            AnswerType.EDGE, confidence=0.8, target_refs=[REF], reason="cma rewrite"
        )
        session = Session()
        with patch(
            "briarwood.agent.dispatch.get_value_thesis",
            return_value={
                "property_id": REF,
                "ask_price": 700000.0,
                "fair_value_base": 742000.0,
                "premium_discount_pct": -0.06,
                "pricing_view": "appears modestly undervalued",
                "value_drivers": ["shore location", "3/2 layout"],
                "key_value_drivers": ["shore location", "layout"],
                "what_must_be_true": ["comps stay supportive"],
                "primary_value_source": "current_value",
            },
        ), patch(
            "briarwood.agent.dispatch.get_property_summary",
            return_value={
                "address": "11 Test Ave, Belmar, NJ 07719",
                "town": "Belmar",
                "state": "NJ",
                "beds": 3,
                "baths": 2.0,
            },
        ), patch(
            "briarwood.agent.dispatch.search_listings",
            return_value=[
                {
                    "property_id": REF,
                    "address": "11 Test Ave, Belmar, NJ 07719",
                    "beds": 3,
                    "baths": 2.0,
                    "ask_price": 700000.0,
                    "blocks_to_beach": 4.0,
                },
                {
                    "property_id": "briarwood-rd-belmar",
                    "address": "1223 Briarwood Rd, Belmar, NJ 07719",
                    "beds": 3,
                    "baths": 2.0,
                    "ask_price": 674200.0,
                    "blocks_to_beach": None,
                },
                {
                    "property_id": "1302-l-street",
                    "address": "1302 L Street, Belmar, NJ 07719",
                    "beds": 3,
                    "baths": 2.0,
                    "ask_price": 850000.0,
                    "blocks_to_beach": 18.9,
                },
            ],
        ), patch(
            "briarwood.agent.dispatch.analyze_property",
            side_effect=ToolUnavailable("skip chart"),
        ):
            response = handle_edge(
                "can you perform a CMA on 11 Test Ave, Belmar, NJ?",
                decision,
                session,
                llm=None,
            )
        self.assertIn("CMA for", response)
        self.assertIn("CMA support comps:", response)
        self.assertIn("briarwood-rd-belmar", response)
        self.assertIn("1302-l-street", response)

    def test_decision_auto_researches_on_weak_town_context(self) -> None:
        """Phase C: weak_town_context triggers exactly one auto-research + re-analyze."""
        decision = RouterDecision(
            AnswerType.DECISION, confidence=0.9, target_refs=[REF], reason="test"
        )
        session = Session()
        before_payload = {
            "decision_stance": "buy_if_price_improves",
            "primary_value_source": "current_value",
            "trust_flags": ["weak_town_context"],
            "value_position": {"fair_value_base": 1_000_000, "ask_price": 1_100_000, "premium_discount_pct": 0.10},
            "what_must_be_true": [],
        }
        after_payload = {
            **before_payload,
            "trust_flags": [],  # research cleared it
        }
        with patch(
            "briarwood.agent.property_view.analyze_property",
            side_effect=[before_payload, after_payload],
        ) as analyzer, patch(
            "briarwood.agent.property_view.get_property_summary",
            return_value={"address": "526 West End Ave", "ask_price": 1_100_000},
        ), patch(
            "briarwood.agent.dispatch._summary_town_state",
            return_value=("Avon By The Sea", "NJ"),
        ), patch(
            "briarwood.agent.dispatch.research_town",
            return_value={"document_count": 3, "signal_count": 5, "warnings": []},
        ) as researcher:
            response = handle_decision(
                "should I buy this?", decision, session, llm=None
            )
        self.assertEqual(analyzer.call_count, 2)  # one before, one after research
        researcher.assert_called_once()
        self.assertIn("Research update", response)
        self.assertIn("cleared trust flags", response)

    def test_decision_with_overrides_skips_research(self) -> None:
        """What-if turns re-underwrite at the user's basis — no town fetch."""
        decision = RouterDecision(
            AnswerType.DECISION, confidence=0.7, target_refs=[REF], reason="test"
        )
        payload = {
            "decision_stance": "pass",
            "primary_value_source": "current_value",
            "trust_flags": ["weak_town_context"],  # would normally trigger research
            "value_position": {"fair_value_base": 1_000_000, "ask_price": 1_300_000, "premium_discount_pct": 0.30},
            "what_must_be_true": [],
        }
        with patch(
            "briarwood.agent.property_view.analyze_property", return_value=payload
        ) as analyzer, patch(
            "briarwood.agent.property_view.get_property_summary",
            return_value={"address": "526 West End Ave", "ask_price": 1_499_000},
        ), patch(
            "briarwood.agent.dispatch.research_town"
        ) as researcher:
            handle_decision(
                "what if i bought at 1.3m?", decision, Session(), llm=None
            )
        researcher.assert_not_called()
        analyzer.assert_called_once_with(REF, overrides={"ask_price": 1_300_000.0})

    def test_decision_without_property_ref_prompts_for_one(self) -> None:
        decision = RouterDecision(
            AnswerType.DECISION, confidence=0.9, target_refs=[], reason="test"
        )
        session = Session()  # no current property
        response = handle_decision("should I buy?", decision, session, llm=None)
        self.assertIn("Which property", response)

    def test_decision_can_analyze_current_live_listing(self) -> None:
        decision = RouterDecision(
            AnswerType.DECISION, confidence=0.8, target_refs=[], reason="browse-followup escalate"
        )
        session = Session(
            current_live_listing={
                "address": "1600 L Street, Belmar, NJ 07719",
                "listing_url": "https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
            }
        )
        with patch(
            "briarwood.agent.dispatch.promote_discovered_listing",
            return_value=PromotedPropertyRecord(
                property_id="1600-l-street-belmar-nj-07719",
                address="1600 L Street, Belmar, NJ 07719",
                town="Belmar",
                state="NJ",
                promotion_status="created",
                intake_warnings=[],
                created_new=True,
                sourced_fields=["address", "price_ask", "beds_baths"],
                inferred_fields=["county"],
                missing_fields=["sqft"],
                listing_url="https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
            ),
        ) as promoter, patch(
            "briarwood.agent.dispatch.PropertyView.load",
            return_value=PropertyView(
                pid="1600-l-street-belmar-nj-07719",
                address="1600 L Street, Belmar, NJ 07719",
                town="Belmar",
                state="NJ",
                beds=3,
                baths=2.0,
                ask_price=899000.0,
                bcv=None,
                pricing_view=None,
                fair_value_base=842000.0,
                all_in_basis=899000.0,
                decision_stance="pass_unless_price_changes",
                primary_value_source="current_value",
                trust_flags=("weak_town_context",),
            ),
        ) as loader:
            response = handle_decision("yes lets run the full analysis", decision, session, llm=None)
        promoter.assert_called_once()
        self.assertGreaterEqual(loader.call_count, 1)
        self.assertEqual(loader.call_args_list[0].args[0], "1600-l-street-belmar-nj-07719")
        self.assertEqual(session.current_property_id, "1600-l-street-belmar-nj-07719")
        self.assertIn("Verdict: pass unless price changes.", response)

    def test_decision_prefers_current_live_listing_when_last_results_are_present(self) -> None:
        decision = RouterDecision(
            AnswerType.DECISION, confidence=0.8, target_refs=[], reason="browse-followup escalate"
        )
        current = {
            "address": "1600 L Street, Belmar, NJ 07719",
            "town": "Belmar",
            "state": "NJ",
            "listing_url": "https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
        }
        session = Session(
            current_live_listing=current,
            last_live_listing_results=[
                current,
                {
                    "address": "301 10th Avenue, Belmar, NJ 07719",
                    "town": "Belmar",
                    "state": "NJ",
                    "listing_url": "https://www.zillow.com/homedetails/301-10th-Ave-Belmar-NJ-07719/331325114_zpid/",
                },
            ],
        )
        with patch(
            "briarwood.agent.dispatch.promote_discovered_listing",
            return_value=PromotedPropertyRecord(
                property_id="1600-l-street-belmar-nj-07719",
                address="1600 L Street, Belmar, NJ 07719",
                town="Belmar",
                state="NJ",
                promotion_status="reused",
                intake_warnings=[],
                created_new=False,
                sourced_fields=["address"],
                inferred_fields=[],
                missing_fields=[],
                listing_url="https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
            ),
        ) as promoter, patch(
            "briarwood.agent.dispatch.PropertyView.load",
            return_value=PropertyView(
                pid="1600-l-street-belmar-nj-07719",
                address="1600 L Street, Belmar, NJ 07719",
                town="Belmar",
                state="NJ",
                beds=3,
                baths=2.0,
                ask_price=899000.0,
                bcv=None,
                pricing_view=None,
                fair_value_base=842000.0,
                all_in_basis=899000.0,
                decision_stance="pass_unless_price_changes",
                primary_value_source="current_value",
                trust_flags=("weak_town_context",),
            ),
        ) as loader:
            response = handle_decision("yes lets run the full analysis", decision, session, llm=None)
        promoter.assert_called_once_with(listing_context=current)
        self.assertGreaterEqual(loader.call_count, 1)
        self.assertEqual(loader.call_args_list[0].args[0], "1600-l-street-belmar-nj-07719")
        self.assertIn("Verdict: pass unless price changes.", response)


class BrowseHandlerTests(unittest.TestCase):
    """Browse: underwrite-lite property brief + optional nearby support."""

    def _decision(self) -> RouterDecision:
        return RouterDecision(
            AnswerType.BROWSE, confidence=0.9, target_refs=[REF], reason="browse keyword"
        )

    def _brief(self, **overrides) -> PropertyBrief:
        payload = dict(
            property_id=REF,
            address="526 West End Ave",
            town="Avon By The Sea",
            state="NJ",
            beds=3,
            baths=2.0,
            ask_price=1_499_000,
            pricing_view="appears fully valued",
            analysis_depth_used="snapshot",
            recommendation="Buy if the price improves.",
            decision="buy",
            decision_stance="buy_if_price_improves",
            best_path="Proceed carefully with a snapshot-to-decision escalation.",
            key_value_drivers=["Ask sits below the fair value anchor", "Strong beach access"],
            key_risks=["Thin carry inputs"],
            trust_flags=["weak_town_context"],
            recommended_next_run="decision",
            next_questions=["should I buy this at the current ask?"],
            primary_value_source="current_value",
            fair_value_base=1_560_000,
            ask_premium_pct=-0.039,
        )
        payload.update(overrides)
        return PropertyBrief(**payload)

    def test_browse_uses_property_brief_contract(self) -> None:
        session = Session()
        with patch(
            "briarwood.agent.dispatch._browse_chat_tier_artifact",
            return_value=None,
        ), patch(
            "briarwood.agent.dispatch.get_property_brief",
            return_value=self._brief(),
        ) as brief_tool, patch(
            "briarwood.agent.dispatch.search_listings", return_value=[]
        ), patch("briarwood.agent.dispatch.analyze_property") as analyzer:
            response = handle_browse(
                "what do you think of 526?", self._decision(), session, llm=None
            )
        analyzer.assert_not_called()
        brief_tool.assert_called_once_with(REF, overrides={})

    def test_browse_consolidated_chat_tier_path_skips_per_tool_routed_calls(self) -> None:
        """Cycle 3 of OUTPUT_QUALITY_HANDOFF_PLAN.md.

        When ``_browse_chat_tier_artifact`` returns a populated artifact,
        ``handle_browse`` builds the brief via ``build_property_brief`` and
        derives projection / strategy_fit / rent_payload from the artifact's
        module outputs, skipping the per-tool ``run_routed_report``
        invocations that produced the audit's 33-event / 13-dormant
        fragmentation.
        """

        artifact = {
            "answer_type": "browse",
            "property_summary": {"property_id": REF},
            "parser_output": {},
            "module_results": {
                "outputs": {
                    "resale_scenario": {
                        "data": {
                            "metrics": {
                                "ask_price": 1_499_000,
                                "base_case_value": 1_580_000,
                                "bull_case_value": 1_700_000,
                                "bear_case_value": 1_410_000,
                                "spread": 290_000,
                            }
                        }
                    },
                    "carry_cost": {
                        "data": {
                            "metrics": {
                                "monthly_rent": 4_200,
                                "effective_monthly_rent": 4_100,
                                "monthly_cash_flow": -650,
                                "annual_noi": 12_400,
                                "cash_on_cash_return": 0.018,
                            }
                        }
                    },
                    "rental_option": {
                        "data": {
                            "metrics": {
                                "rental_ease_label": "Steady",
                                "rental_ease_score": 0.72,
                                "rent_support_score": 0.65,
                                "liquidity_score": 0.6,
                            }
                        }
                    },
                    "valuation": {"data": {"metrics": {"pricing_view": "appears fully valued"}}},
                },
                "trace": [],
            },
            "modules_run": [
                "valuation",
                "carry_cost",
                "comparable_sales",
                "location_intelligence",
                "strategy_classifier",
                "rental_option",
                "resale_scenario",
            ],
            "unified_output": {
                "recommendation": "Buy if the price improves.",
                "decision": "buy",
                "decision_stance": "buy_if_price_improves",
                "best_path": "Proceed carefully with a snapshot-to-decision escalation.",
                "key_value_drivers": ["Ask sits below the fair value anchor"],
                "key_risks": ["Thin carry inputs"],
                "trust_flags": [],
                "primary_value_source": "current_value",
                "value_position": {"fair_value_base": 1_560_000, "ask_premium_pct": -0.039},
                "analysis_depth_used": "snapshot",
                "next_questions": ["should I buy this at the current ask?"],
                "recommended_next_run": "decision",
            },
            "interaction_trace": {},
            "shadow_intelligence": None,
        }

        session = Session()
        with patch(
            "briarwood.agent.dispatch._browse_chat_tier_artifact",
            return_value=artifact,
        ) as chat_tier, patch(
            "briarwood.agent.dispatch.get_property_brief",
        ) as legacy_brief, patch(
            "briarwood.agent.dispatch.get_projection",
        ) as legacy_projection, patch(
            "briarwood.agent.dispatch.get_strategy_fit",
        ) as legacy_strategy, patch(
            "briarwood.agent.dispatch.get_rent_estimate",
        ) as legacy_rent, patch(
            "briarwood.agent.dispatch.search_listings", return_value=[]
        ):
            response = handle_browse(
                "what do you think of 526?", self._decision(), session, llm=None
            )

        chat_tier.assert_called_once()
        # The four per-tool runners must NOT fire — those were the
        # functions producing the audit's per-tool plan duplication.
        legacy_brief.assert_not_called()
        legacy_projection.assert_not_called()
        legacy_strategy.assert_not_called()
        legacy_rent.assert_not_called()
        # The handler still produces a real response.
        self.assertIn("526 West End Ave", response)
        self.assertIn("Decision:", response)
        self.assertIn("526 West End Ave", response)
        self.assertIn("Decision:", response)
        self.assertIn("Why:", response)
        self.assertIn("Next move:", response)
        self.assertEqual(session.last_presentation_payload["contract_type"], "property_brief")
        self.assertEqual(session.last_surface_narrative, response)


class SearchHandlerTests(unittest.TestCase):
    def _decision(self) -> RouterDecision:
        return RouterDecision(
            AnswerType.BROWSE, confidence=0.9, target_refs=[REF], reason="browse keyword"
        )

    def _brief(self, **overrides) -> PropertyBrief:
        payload = dict(
            property_id=REF,
            address="526 West End Ave",
            town="Avon By The Sea",
            state="NJ",
            beds=3,
            baths=2.0,
            ask_price=1_499_000,
            pricing_view="appears fully valued",
            analysis_depth_used="snapshot",
            recommendation="Buy if the price improves.",
            decision="buy",
            decision_stance="buy_if_price_improves",
            best_path="Proceed carefully with a snapshot-to-decision escalation.",
            key_value_drivers=["Ask sits below the fair value anchor", "Strong beach access"],
            key_risks=["Thin carry inputs"],
            trust_flags=["weak_town_context"],
            recommended_next_run="decision",
            next_questions=["should I buy this at the current ask?"],
            primary_value_source="current_value",
            fair_value_base=1_560_000,
            ask_premium_pct=-0.039,
        )
        payload.update(overrides)
        return PropertyBrief(**payload)

    def test_search_prefers_live_zillow_discovery_for_town_queries(self) -> None:
        decision = RouterDecision(
            AnswerType.SEARCH, confidence=0.9, target_refs=[], reason="search imperative"
        )
        session = Session()
        with patch(
            "briarwood.agent.dispatch.search_live_listings",
        ) as live_search, patch(
            "briarwood.agent.dispatch.search_listings"
        ) as saved_search:
            response = handle_search(
                "show me the houses that are listed for sale in Belmar",
                decision,
                session,
                llm=None,
            )
        live_search.assert_not_called()
        saved_search.assert_not_called()
        self.assertIn("I can run live listing discovery for Belmar, but I need the state too.", response)
        self.assertIn("Belmar, NJ", response)
        self.assertIsNone(session.current_live_listing)
        self.assertEqual(session.last_live_listing_results, [])

    def test_search_does_not_treat_generic_near_the_beach_phrase_as_town_prompt(self) -> None:
        decision = RouterDecision(
            AnswerType.SEARCH, confidence=0.9, target_refs=[], reason="search imperative"
        )
        session = Session()
        with patch(
            "briarwood.agent.dispatch.search_live_listings",
            side_effect=ToolUnavailable("no live path"),
        ) as live_search, patch(
            "briarwood.agent.dispatch.search_listings",
            return_value=[
                {
                    "property_id": "304-14th-ave",
                    "address": "304 14th Ave",
                    "beds": 3,
                    "baths": 2.0,
                    "ask_price": 1425000,
                }
            ],
        ) as saved_search:
            response = handle_search(
                "show me listings near the beach under 1.5m",
                decision,
                session,
                llm=None,
            )
        live_search.assert_called_once()
        saved_search.assert_called_once()
        self.assertNotIn("Please provide the town and state", response)
        self.assertIn("Live Zillow discovery was unavailable", response)
        self.assertIn("Matched 1 of the saved corpus", response)

    def test_search_prefers_live_zillow_discovery_when_town_and_state_are_provided(self) -> None:
        decision = RouterDecision(
            AnswerType.SEARCH, confidence=0.9, target_refs=[], reason="search imperative"
        )
        session = Session()
        live_rows = [
            LiveListingCandidate(
                address="1223 Briarwood Rd, Belmar, NJ 07719",
                town="Belmar",
                state="NJ",
                zip_code="07719",
                ask_price=674200,
                beds=3,
                baths=2.0,
                sqft=1468,
                property_type="Single Family",
                listing_status="For sale",
                listing_url="https://www.zillow.com/homedetails/1223-Briarwood-Rd-Belmar-NJ-07719/39225332_zpid/",
                external_id="39225332",
            )
        ]
        with patch(
            "briarwood.agent.dispatch.search_live_listings",
            return_value=live_rows,
        ) as live_search, patch(
            "briarwood.agent.dispatch.search_listings"
        ) as saved_search:
            response = handle_search(
                "show me the houses that are listed for sale in Belmar, NJ",
                decision,
                session,
                llm=None,
            )
        live_search.assert_called_once_with(
            query="Belmar, NJ",
            town="Belmar",
            state="NJ",
            beds=None,
            beds_min=None,
        )
        saved_search.assert_not_called()
        self.assertIn("Found 1 live Zillow listing", response)
        self.assertIn("1223 Briarwood Rd", response)
        self.assertIn("Next best move", response)
        self.assertEqual(session.current_live_listing["address"], "1223 Briarwood Rd, Belmar, NJ 07719")
        self.assertEqual(len(session.last_live_listing_results), 1)
        self.assertIn("Belmar, NJ", response)

    def test_search_followup_place_completion_rewrites_to_search(self) -> None:
        session = Session(search_context={"town": "Belmar", "state": None, "filters": {"beds": 3}})
        decision = RouterDecision(
            AnswerType.BROWSE, confidence=0.6, target_refs=[], reason="llm classify"
        )
        out = contextualize_decision("Yes belmar NJ", decision, session)
        self.assertEqual(out.answer_type, AnswerType.SEARCH)
        self.assertEqual(out.reason, "search-followup place completion")

    def test_search_followup_place_completion_uses_pending_filters(self) -> None:
        decision = RouterDecision(
            AnswerType.SEARCH, confidence=0.6, target_refs=[], reason="search-followup place completion"
        )
        session = Session(search_context={"town": "Belmar", "state": None, "filters": {"beds": 3}})
        live_rows = [
            LiveListingCandidate(
                address="1600 L Street, Belmar, NJ 07719",
                town="Belmar",
                state="NJ",
                zip_code="07719",
                ask_price=899000,
                beds=3,
                baths=2.0,
                sqft=1500,
                property_type="Single Family",
                listing_status="For sale",
                listing_url="https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
                external_id="39225096",
            )
        ]
        with patch(
            "briarwood.agent.dispatch.search_live_listings",
            return_value=live_rows,
        ) as live_search, patch(
            "briarwood.agent.dispatch.search_listings"
        ) as saved_search:
            response = handle_search("Yes belmar NJ", decision, session, llm=None)
        live_search.assert_called_once_with(
            query="Belmar, NJ",
            town="Belmar",
            state="NJ",
            beds=3,
            beds_min=None,
        )
        saved_search.assert_not_called()
        self.assertIn("Found 1 live Zillow listing", response)

    def test_search_refines_live_search_with_session_town_state(self) -> None:
        decision = RouterDecision(
            AnswerType.SEARCH, confidence=0.6, target_refs=[], reason="llm classify"
        )
        session = Session(search_context={"town": "Belmar", "state": "NJ", "filters": {}})
        live_rows = [
            LiveListingCandidate(
                address="1600 L Street, Belmar, NJ 07719",
                town="Belmar",
                state="NJ",
                zip_code="07719",
                ask_price=899000,
                beds=3,
                baths=2.0,
                sqft=1500,
                property_type="Single Family",
                listing_status="For sale",
                listing_url="https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
                external_id="39225096",
            )
        ]
        with patch(
            "briarwood.agent.dispatch.search_live_listings",
            return_value=live_rows,
        ) as live_search, patch(
            "briarwood.agent.dispatch.search_listings"
        ) as saved_search:
            response = handle_search("what about just 3 beds?", decision, session, llm=None)
        live_search.assert_called_once_with(
            query="Belmar, NJ",
            town="Belmar",
            state="NJ",
            beds=3,
            beds_min=None,
        )
        saved_search.assert_not_called()
        self.assertIn("Found 1 live Zillow listing", response)

    def test_search_passes_bedroom_count_into_live_zillow_query(self) -> None:
        decision = RouterDecision(
            AnswerType.SEARCH, confidence=0.6, target_refs=[], reason="llm classify"
        )
        with patch(
            "briarwood.agent.dispatch.search_live_listings",
            return_value=[],
        ) as live_search, patch(
            "briarwood.agent.dispatch.search_listings",
            return_value=[],
        ):
            handle_search(
                "what are the 3 bedroom homes listed for sale in Belmar, NJ",
                decision,
                Session(),
                llm=None,
            )
        live_search.assert_called_once_with(
            query="Belmar, NJ",
            town="Belmar",
            state="NJ",
            beds=3,
            beds_min=None,
        )

    def test_search_falls_back_to_saved_corpus_filters_when_live_discovery_is_not_available(self) -> None:
        decision = RouterDecision(
            AnswerType.SEARCH, confidence=0.9, target_refs=[], reason="search imperative"
        )
        session = Session()
        with patch(
            "briarwood.agent.dispatch.search_live_listings",
            side_effect=ToolUnavailable("no live path"),
        ), patch(
            "briarwood.agent.dispatch.search_listings",
            return_value=[
                {
                    "property_id": "304-14th-ave",
                    "address": "304 14th Ave",
                    "beds": 3,
                    "baths": 2.0,
                    "ask_price": 1425000,
                    "blocks_to_beach": 2.5,
                }
            ],
        ):
            response = handle_search(
                "show me listings near the beach under 1.5m",
                decision,
                session,
                llm=None,
            )
        self.assertIn("Live Zillow discovery was unavailable", response)
        self.assertIn("Matched 1 of the saved corpus", response)
        self.assertIn("304-14th-ave", response)
        self.assertIsNone(session.current_live_listing)
        self.assertEqual(session.last_live_listing_results, [])

    def test_browse_lists_similar_nearby_as_secondary_support(self) -> None:
        fake_neighbors = [
            {
                "property_id": "304-14th-ave",
                "address": "304 14th Ave",
                "beds": 3,
                "baths": 2.0,
                "ask_price": 1_425_000,
                "blocks_to_beach": 2.5,
            },
            {
                "property_id": REF,  # subject — must be filtered out
                "address": "526 West End Ave",
                "beds": 3,
                "baths": 2.0,
                "ask_price": 1_499_000,
                "blocks_to_beach": 3.0,
            },
        ]
        with patch(
            "briarwood.agent.dispatch._browse_chat_tier_artifact",
            return_value=None,
        ), patch(
            "briarwood.agent.dispatch.get_property_brief",
            return_value=self._brief(ask_price=1_500_000),
        ), patch(
            "briarwood.agent.dispatch.search_listings", return_value=fake_neighbors
        ) as search:
            response = handle_browse(
                "what do you think of 526?", self._decision(), Session(), llm=None
            )
        # filters should reflect beds band + price ±25% + town
        call_filters = search.call_args[0][0]
        self.assertEqual(call_filters["beds_min"], 2)
        self.assertEqual(call_filters["beds_max"], 4)
        self.assertEqual(call_filters["town"], "Avon By The Sea")
        self.assertAlmostEqual(call_filters["min_price"], 1_500_000 * 0.75)
        self.assertAlmostEqual(call_filters["max_price"], 1_500_000 * 1.25)
        self.assertIn("Decision:", response)
        self.assertIn("Next move:", response)
        self.assertNotIn("Nearby support in", response)

    def test_browse_prefers_live_cma_comps_for_rendered_slots(self) -> None:
        session = Session()
        brief = self._brief(
            address="1008 14th Avenue, Belmar, NJ 07719",
            town="Belmar",
            state="NJ",
            ask_price=767000.0,
            beds=3,
            baths=1.0,
        )
        live_cma = CMAResult(
            property_id=REF,
            address="1008 14th Avenue, Belmar, NJ 07719",
            town="Belmar",
            state="NJ",
            ask_price=767000.0,
            fair_value_base=720644.0,
            value_low=690000.0,
            value_high=803827.0,
            pricing_view="appears_fully_valued",
            primary_value_source="current_value",
            comp_selection_summary="Live Zillow market comps ranked toward the subject.",
            comps=[
                ComparableProperty(
                    property_id="1302-l-street",
                    address="1302 L Street, Belmar, NJ 07719",
                    town="Belmar",
                    state="NJ",
                    beds=3,
                    baths=2.0,
                    ask_price=850000.0,
                    blocks_to_beach=None,
                    source_label="Live market comp",
                    source_summary="Live Zillow market comp",
                )
            ],
            confidence_notes=[],
            missing_fields=[],
        )
        with patch(
            "briarwood.agent.dispatch.get_property_brief",
            return_value=brief,
        ), patch(
            "briarwood.agent.dispatch.get_property_summary",
            return_value={"address": brief.address, "town": "Belmar", "state": "NJ"},
        ), patch(
            "briarwood.agent.dispatch.get_cma",
            return_value=live_cma,
        ), patch(
            "briarwood.agent.dispatch.search_listings",
            return_value=[
                {
                    "property_id": "saved-comp",
                    "address": "1223 Briarwood Rd, Belmar, NJ 07719",
                    "beds": 3,
                    "baths": 2.0,
                    "ask_price": 674200.0,
                }
            ],
        ), patch(
            "briarwood.agent.dispatch.get_projection",
            side_effect=ToolUnavailable("skip projection"),
        ), patch(
            "briarwood.agent.dispatch.get_strategy_fit",
            side_effect=ToolUnavailable("skip strategy"),
        ), patch(
            "briarwood.agent.dispatch.get_rent_estimate",
            side_effect=ToolUnavailable("skip rent"),
        ), patch(
            "briarwood.agent.dispatch.get_property_presentation",
            return_value={},
        ), patch(
            "briarwood.agent.dispatch._build_town_summary",
            return_value={"town": "Belmar", "state": "NJ"},
        ):
            handle_browse("what do you think of 1008 14th ave?", self._decision(), session, llm=None)

        # comps_preview continues to render the live CMA rows.
        self.assertEqual(session.last_comps_preview["comps"][0]["property_id"], "1302-l-street")
        # F2: browse does not run the valuation module, so value_thesis.comps
        # must be empty and live-market comps live on last_market_support_view.
        self.assertEqual(session.last_value_thesis_view["comps"], [])
        self.assertIsNone(session.last_value_thesis_view["comp_selection_summary"])
        self.assertIsNotNone(session.last_market_support_view)
        self.assertEqual(
            session.last_market_support_view["comps"][0]["property_id"],
            "1302-l-street",
        )
        self.assertEqual(
            session.last_market_support_view["comp_selection_summary"],
            "Live Zillow market comps ranked toward the subject.",
        )

    def test_browse_omits_missing_fields_instead_of_rendering_question_marks(self) -> None:
        """Bug A: null beds/baths must not render as '? bedrooms'."""
        with patch(
            "briarwood.agent.dispatch.get_property_brief",
            return_value=self._brief(beds=None, baths=None),
        ), patch(
            "briarwood.agent.dispatch.search_listings", return_value=[]
        ):
            response = handle_browse(
                "tell me about 526", self._decision(), Session(), llm=None
            )
        self.assertNotIn("?bd", response)
        self.assertNotIn("?ba", response)
        self.assertNotIn("? bd", response)
        self.assertNotIn("? ba", response)
        self.assertNotIn("unspecified", response.lower())
        self.assertIn("526 West End Ave", response)

    def test_browse_brings_forward_purchase_relevant_signals(self) -> None:
        with patch(
            "briarwood.agent.dispatch._browse_chat_tier_artifact",
            return_value=None,
        ), patch(
            "briarwood.agent.dispatch.get_property_brief",
            return_value=self._brief(),
        ), patch(
            "briarwood.agent.dispatch.search_listings", return_value=[]
        ):
            response = handle_browse(
                "tell me about 526", self._decision(), Session(), llm=None
            )
        self.assertIn("Decision:", response)
        self.assertIn("town backdrop is still lightly documented", response.lower())
        self.assertIn("Next move:", response)

    def test_browse_does_not_surface_unknown_primary_value_source(self) -> None:
        with patch(
            "briarwood.agent.dispatch._browse_chat_tier_artifact",
            return_value=None,
        ), patch(
            "briarwood.agent.dispatch.get_property_brief",
            return_value=self._brief(
                key_value_drivers=[],
                primary_value_source="unknown",
                best_path="Proceed through the snapshot-to-decision path.",
            ),
        ), patch(
            "briarwood.agent.dispatch.search_listings", return_value=[]
        ):
            response = handle_browse(
                "tell me about 526", self._decision(), Session(), llm=None
            )
        self.assertNotIn("primary value source is unknown", response.lower())
        self.assertIn("snapshot-to-decision path", response.lower())

    def test_browse_without_property_prompts_for_one(self) -> None:
        decision = RouterDecision(
            AnswerType.BROWSE, confidence=0.9, target_refs=[], reason="test"
        )
        response = handle_browse(
            "what do you think?", decision, Session(), llm=None
        )
        self.assertIn("Which property", response)

    def test_browse_unresolved_property_mentions_saved_corpus(self) -> None:
        decision = RouterDecision(
            AnswerType.BROWSE, confidence=0.9, target_refs=[], reason="test"
        )
        with patch(
            "briarwood.agent.resolver.resolve_property_id", return_value=(None, [])
        ), patch(
            "briarwood.agent.dispatch.promote_unsaved_address",
            side_effect=ToolUnavailable("no live listing context"),
        ):
            response = handle_browse(
                "tell me about 1223 ocean ave", decision, Session(), llm=None
            )
        self.assertIn("saved corpus", response.lower())

    def test_browse_ambiguous_property_returns_candidates(self) -> None:
        decision = RouterDecision(
            AnswerType.BROWSE, confidence=0.9, target_refs=[], reason="test"
        )
        with patch(
            "briarwood.agent.resolver.resolve_property_id",
            return_value=(None, ["526-west-end-ave", "304-14th-ave"]),
        ), patch(
            "briarwood.agent.dispatch.get_property_summary",
            side_effect=[
                {"address": "526 West End Ave", "town": "Avon By The Sea"},
                {"address": "304 14th Ave", "town": "Belmar"},
            ],
        ):
            response = handle_browse(
                "tell me about west end", decision, Session(), llm=None
            )
        self.assertIn("close matches", response.lower())
        self.assertIn("526-west-end-ave", response)

    def test_reported_transcript_gets_purchase_brief(self) -> None:
        decision = RouterDecision(
            AnswerType.BROWSE, confidence=0.6, target_refs=[], reason="llm classify"
        )
        with patch(
            "briarwood.agent.resolver.resolve_property_id",
            return_value=("briarwood-rd-belmar", ["briarwood-rd-belmar"]),
        ), patch(
            "briarwood.agent.dispatch.get_property_brief",
            return_value=self._brief(
                property_id="briarwood-rd-belmar",
                address="1223 Briarwood Rd",
                town="Belmar",
            ),
        ), patch(
            "briarwood.agent.dispatch.search_listings", return_value=[]
        ):
            response = handle_browse(
                "what can you tell me about 1223 Briarwood Road, in Belmar",
                decision,
                Session(),
                llm=None,
            )
        self.assertIn("1223 Briarwood Rd", response)
        self.assertIn("Decision:", response)
        self.assertIn("Why:", response)
        self.assertIn("Next move:", response)

    def test_browse_populates_briefing_slots_for_first_impression(self) -> None:
        decision = RouterDecision(
            AnswerType.BROWSE, confidence=0.6, target_refs=[], reason="llm classify"
        )
        session = Session()
        with patch(
            "briarwood.agent.resolver.resolve_property_id",
            return_value=("briarwood-rd-belmar", ["briarwood-rd-belmar"]),
        ), patch(
            "briarwood.agent.dispatch.get_property_brief",
            return_value=self._brief(
                property_id="briarwood-rd-belmar",
                address="1223 Briarwood Rd",
                town="Belmar",
                state="NJ",
                ask_price=767000,
                fair_value_base=723556,
                ask_premium_pct=0.057,
            ),
        ), patch(
            "briarwood.agent.dispatch.get_property_summary",
            return_value={
                "address": "1223 Briarwood Rd",
                "town": "Belmar",
                "state": "NJ",
                "beds": 3,
                "baths": 2.0,
                "ask_price": 767000,
            },
        ), patch(
            "briarwood.agent.dispatch.get_projection",
            return_value={
                "ask_price": 767000,
                "bull_case_value": 816046,
                "base_case_value": 764343,
                "bear_case_value": 722117,
                "stress_case_value": 506489,
            },
        ), patch(
            "briarwood.agent.dispatch.get_strategy_fit",
            return_value={
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
            },
        ), patch(
            "briarwood.agent.dispatch.get_rent_estimate",
            return_value={
                "monthly_rent": 2352,
                "effective_monthly_rent": 2234,
                "annual_noi": 18500,
                "rent_source_type": "seasonal_mixed",
                "rental_ease_label": "seasonal/mixed",
                "rental_ease_score": 57.0,
                "monthly_cash_flow": -866,
            },
        ), patch(
            "briarwood.agent.dispatch.get_rent_outlook",
            return_value=RentOutlook(
                property_id="briarwood-rd-belmar",
                address="1223 Briarwood Rd",
                entry_basis=767000,
                current_monthly_rent=2352,
                effective_monthly_rent=2234,
                annual_noi=18500,
                rent_source_type="seasonal_mixed",
                rental_ease_label="seasonal/mixed",
                rental_ease_score=57.0,
                horizon_years=3,
                future_rent_low=2300,
                future_rent_mid=2410,
                future_rent_high=2600,
                basis_to_rent_framing="Current rent annualizes to roughly 3.5% of the current basis.",
                owner_occupy_then_rent=None,
                zillow_market_rent=2500,
                zillow_market_rent_low=2200,
                zillow_market_rent_high=2900,
                zillow_rental_comp_count=3,
                market_context_note=None,
                burn_chart_payload={"series": [{"year": 0, "rent_base": 2234, "rent_bull": 2400, "rent_bear": 2100, "monthly_obligation": 3100}]},
                ramp_chart_payload={"series": [{"year": 0, "net_0": -866, "net_3": -866, "net_5": -866}]},
                confidence_notes=[],
            ),
        ), patch(
            "briarwood.agent.dispatch.get_property_presentation",
            return_value={
                "cards": [
                    {"key": "property_header", "body": ["1223 Briarwood Rd"]},
                    {"key": "purchase_brief", "body": ["Immediate setup: buy if price improves.", "What supports it: near fair value.", "What could weaken confidence: weak_town_context.", "Next best question: should I buy this at the current ask?"]},
                    {"key": "data_coverage", "body": ["ATTOM added structured sale history and ownership timing context."]},
                    {"key": "location_pulse", "body": ["Belmar has constructive beach-town demand."]},
                ]
            },
        ), patch(
            "briarwood.agent.dispatch.search_listings",
            return_value=[
                {
                    "property_id": "1302-l-street",
                    "address": "1302 L Street",
                    "beds": 3,
                    "baths": 2.0,
                    "ask_price": 850000,
                    "sqft": 1320,
                    "blocks_to_beach": 4.0,
                },
                {
                    "property_id": "1600-l-street",
                    "address": "1600 L Street",
                    "beds": 3,
                    "baths": 2.0,
                    "ask_price": 899000,
                    "sqft": 1468,
                    "blocks_to_beach": 5.0,
                },
            ],
        ), patch(
            "briarwood.agent.dispatch._build_town_summary",
            return_value={
                "town": "Belmar",
                "state": "NJ",
                "confidence_tier": "strong",
                "confidence_raw": 0.72,
                "median_price": 867500,
                "median_ppsf": 516,
                "sold_count": 320,
                "doc_count": 4,
                "bullish_signals": ["Main Street redevelopment"],
                "bearish_signals": [],
            },
        ):
            response = handle_browse(
                "tell me about 1223 Briarwood Rd, Belmar",
                decision,
                session,
                llm=None,
            )
        self.assertIn("Decision:", response)
        self.assertIn("Why:", response)
        self.assertIn("Next move:", response)
        self.assertIsNotNone(session.last_town_summary)
        self.assertIsNotNone(session.last_comps_preview)
        self.assertIsNotNone(session.last_value_thesis_view)
        self.assertIsNotNone(session.last_strategy_view)
        self.assertIsNotNone(session.last_rent_outlook_view)
        self.assertIsNotNone(session.last_projection_view)

    def test_unsaved_address_can_auto_promote_into_browse(self) -> None:
        decision = RouterDecision(
            AnswerType.BROWSE, confidence=0.6, target_refs=[], reason="llm classify"
        )
        with patch(
            "briarwood.agent.resolver.resolve_property_id",
            return_value=(None, []),
        ), patch(
            "briarwood.agent.dispatch.promote_unsaved_address",
            return_value=PromotedPropertyRecord(
                property_id="25-main-street-belmar-nj-07719",
                address="25 Main Street, Belmar, NJ 07719",
                town="Belmar",
                state="NJ",
                promotion_status="created",
                intake_warnings=[],
                created_new=True,
                sourced_fields=["address", "beds_baths", "sqft"],
                inferred_fields=["county"],
                missing_fields=["price"],
                listing_url=None,
            ),
        ), patch(
            "briarwood.agent.dispatch.get_property_brief",
            return_value=self._brief(
                property_id="25-main-street-belmar-nj-07719",
                address="25 Main Street, Belmar, NJ 07719",
                town="Belmar",
                state="NJ",
                ask_price=None,
            ),
        ), patch(
            "briarwood.agent.dispatch.get_property_presentation",
            return_value={
                "cards": [
                    {"key": "property_header", "body": ["25 Main Street, Belmar, NJ 07719"]},
                    {
                        "key": "purchase_brief",
                        "body": [
                            "Immediate setup: buy if price improves.",
                            "What supports it: Make an offer inside the risk-adjusted band rather than at ask.",
                            "What could weaken confidence: weak_town_context.",
                            "Next best question: should I buy this at the current ask?",
                        ],
                    },
                    {
                        "key": "data_coverage",
                        "body": ["ATTOM added structured sale history and ownership timing context."],
                    },
                ]
            },
        ), patch(
            "briarwood.agent.dispatch.search_listings", return_value=[]
        ):
            response = handle_browse(
                "what do you think of 25 Main Street, Belmar, NJ 07719",
                decision,
                Session(),
                llm=None,
            )
        self.assertIn("25 Main Street, Belmar, NJ 07719", response)
        self.assertIn("price improves", response.lower())

    def test_browse_ignores_poisoned_saved_record_and_repromotes_address(self) -> None:
        decision = RouterDecision(
            AnswerType.BROWSE, confidence=0.6, target_refs=[], reason="llm classify"
        )
        with patch(
            "briarwood.agent.resolver.resolve_property_id",
            return_value=("1228-briarwood-road-belmar-nj", ["1228-briarwood-road-belmar-nj"]),
        ), patch(
            "briarwood.agent.dispatch.saved_property_has_valid_location",
            side_effect=lambda pid: False if pid == "1228-briarwood-road-belmar-nj" else True,
        ), patch(
            "briarwood.agent.dispatch.promote_unsaved_address",
            return_value=PromotedPropertyRecord(
                property_id="1228-briarwood-road-belmar-nj",
                address="1228 Briarwood Road, Belmar, NJ 07719",
                town="Belmar",
                state="NJ",
                promotion_status="created",
                intake_warnings=[],
                created_new=True,
                sourced_fields=["address", "beds_baths", "sqft"],
                inferred_fields=["county"],
                missing_fields=["price"],
                listing_url=None,
            ),
        ), patch(
            "briarwood.agent.dispatch.get_property_brief",
            return_value=self._brief(
                property_id="1228-briarwood-road-belmar-nj",
                address="1228 Briarwood Road, Belmar, NJ 07719",
                town="Belmar",
                state="NJ",
                ask_price=None,
            ),
        ), patch(
            "briarwood.agent.dispatch.get_property_presentation",
            return_value={
                "cards": [
                    {"key": "property_header", "body": ["1228 Briarwood Road, Belmar, NJ 07719"]},
                    {
                        "key": "purchase_brief",
                        "body": [
                            "Immediate setup: buy if price improves.",
                            "What supports it: Make an offer inside the risk-adjusted band rather than at ask.",
                            "What could weaken confidence: weak_town_context.",
                            "Next best question: should I buy this at the current ask?",
                        ],
                    },
                    {"key": "data_coverage", "body": ["ATTOM added structured sale history and ownership timing context."]},
                ]
            },
        ), patch(
            "briarwood.agent.dispatch.search_listings", return_value=[]
        ):
            response = handle_browse(
                "what do you think of 1228 briarwood road, belmar nj",
                decision,
                Session(),
                llm=None,
            )
        self.assertIn("1228 Briarwood Road, Belmar, NJ 07719", response)

    def test_browse_resolves_this_house_after_single_live_search_result(self) -> None:
        decision = RouterDecision(
            AnswerType.BROWSE, confidence=0.6, target_refs=[], reason="llm classify"
        )
        session = Session(
            current_live_listing={
                "address": "1600 L Street, Belmar, NJ 07719",
                "town": "Belmar",
                "state": "NJ",
                "ask_price": 899000.0,
                "beds": 3,
                "baths": 2.0,
                "property_type": "SINGLE_FAMILY",
                "listing_status": "FOR_SALE",
                "listing_url": "https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
            },
            last_live_listing_results=[
                {
                    "address": "1600 L Street, Belmar, NJ 07719",
                    "town": "Belmar",
                    "state": "NJ",
                    "ask_price": 899000.0,
                    "beds": 3,
                    "baths": 2.0,
                    "property_type": "SINGLE_FAMILY",
                    "listing_status": "FOR_SALE",
                    "listing_url": "https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
                }
            ],
        )
        with patch(
            "briarwood.agent.resolver.resolve_property_id", return_value=(None, [])
        ), patch(
            "briarwood.agent.dispatch.promote_discovered_listing",
            return_value=PromotedPropertyRecord(
                property_id="1600-l-street-belmar-nj-07719",
                address="1600 L Street, Belmar, NJ 07719",
                town="Belmar",
                state="NJ",
                promotion_status="created",
                intake_warnings=[],
                created_new=True,
                sourced_fields=["address", "price_ask", "beds_baths"],
                inferred_fields=["county"],
                missing_fields=["sqft"],
                listing_url="https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
            ),
        ), patch(
            "briarwood.agent.dispatch.get_property_enrichment",
            return_value={
                "attom": {"sale_history_snapshot": {"sale_count": 2}, "rental_avm": {"estimated_monthly_rent": 3600}},
                "google": {"geocode": {"county": "Monmouth"}, "nearby_places": {"type_counts": {"school": 1}}, "street_view_image_url": "https://maps.googleapis.com/maps/api/streetview?..."},
            },
        ), patch(
            "briarwood.agent.dispatch.get_property_brief",
            return_value=self._brief(
                property_id="1600-l-street-belmar-nj-07719",
                address="1600 L Street, Belmar, NJ 07719",
                town="Belmar",
                state="NJ",
                ask_price=899000,
            ),
        ), patch(
            "briarwood.agent.dispatch.search_listings", return_value=[]
        ):
            response = handle_browse(
                "what do you think of this house?",
                decision,
                session,
                llm=None,
            )
        self.assertIn("1600 L Street, Belmar, NJ 07719", response)
        self.assertIn("Briarwood saved", response)
        self.assertIn("Source coverage", response)
        self.assertIn("Structured enrichment pulled from ATTOM", response)
        self.assertIn("Location enrichment pulled from Google Maps", response)

    def test_browse_resolves_explicit_live_listing_address_from_last_results(self) -> None:
        decision = RouterDecision(
            AnswerType.BROWSE, confidence=0.6, target_refs=[], reason="llm classify"
        )
        session = Session(
            last_live_listing_results=[
                {
                    "address": "301 10th Avenue, Belmar, NJ 07719",
                    "town": "Belmar",
                    "state": "NJ",
                    "ask_price": 2699900.0,
                    "beds": 6,
                    "baths": 4.0,
                    "property_type": "SINGLE_FAMILY",
                    "listing_status": "FOR_SALE",
                    "listing_url": "https://www.zillow.com/homedetails/301-10th-Ave-Belmar-NJ-07719/331325114_zpid/",
                }
            ]
        )
        with patch(
            "briarwood.agent.resolver.resolve_property_id", return_value=(None, [])
        ), patch(
            "briarwood.agent.dispatch.promote_discovered_listing",
            return_value=PromotedPropertyRecord(
                property_id="301-10th-avenue-belmar-nj-07719",
                address="301 10th Avenue, Belmar, NJ 07719",
                town="Belmar",
                state="NJ",
                promotion_status="created",
                intake_warnings=[],
                created_new=True,
                sourced_fields=["address", "price_ask", "beds_baths"],
                inferred_fields=["county"],
                missing_fields=[],
                listing_url="https://www.zillow.com/homedetails/301-10th-Ave-Belmar-NJ-07719/331325114_zpid/",
            ),
        ), patch(
            "briarwood.agent.dispatch.get_property_brief",
            return_value=self._brief(
                property_id="301-10th-avenue-belmar-nj-07719",
                address="301 10th Avenue, Belmar, NJ 07719",
                town="Belmar",
                state="NJ",
                ask_price=2699900,
            ),
        ), patch(
            "briarwood.agent.dispatch.search_listings", return_value=[]
        ):
            response = handle_browse(
                "what do you think of 301 10th Avenue, Belmar, NJ 07719",
                decision,
                session,
                llm=None,
            )
        self.assertIn("301 10th Avenue, Belmar, NJ 07719", response)
        self.assertIn("Briarwood saved", response)


class SessionPropertyLeakTests(unittest.TestCase):
    """Stale session pid must not answer a question about a different property."""

    def test_unresolved_street_address_does_not_fall_back_to_session(self) -> None:
        from briarwood.agent.dispatch import _resolve_property_id

        decision = RouterDecision(
            AnswerType.LOOKUP, confidence=0.9, target_refs=[], reason="test"
        )
        session = Session(current_property_id=REF)  # prior turn left 526 loaded

        # User asks about 1223 Ocean Ave — not saved. Resolver returns None.
        # Session fallback MUST NOT quietly substitute 526.
        with patch("briarwood.agent.resolver.resolve_property_id", return_value=(None, [])):
            pid = _resolve_property_id(decision, session, "tell me about 1223 ocean ave")
        self.assertIsNone(pid)

    def test_follow_up_without_property_reference_uses_session(self) -> None:
        from briarwood.agent.dispatch import _resolve_property_id

        decision = RouterDecision(
            AnswerType.RISK, confidence=0.9, target_refs=[], reason="test"
        )
        session = Session(current_property_id=REF)

        with patch("briarwood.agent.resolver.resolve_property_id", return_value=(None, [])):
            pid = _resolve_property_id(decision, session, "what about the risks?")
        self.assertEqual(pid, REF)


class EdgeHandlerTests(unittest.TestCase):
    def test_edge_threads_overrides_into_analyze_and_thesis(self) -> None:
        """What-if prices must reach both the thesis and the chart analyzer."""
        decision = RouterDecision(
            AnswerType.EDGE, confidence=0.9, target_refs=[REF], reason="test"
        )
        from briarwood.agent.rendering import ChartUnavailable

        fake_thesis = {
            "ask_price": 1_300_000,
            "fair_value_base": 1_379_080,
            "premium_discount_pct": -0.057,
            "pricing_view": "below fair value",
        }
        with patch(
            "briarwood.agent.dispatch.get_value_thesis", return_value=fake_thesis
        ) as thesis, patch(
            "briarwood.agent.dispatch.analyze_property", return_value={}
        ) as analyzer, patch("briarwood.agent.rendering.render_chart") as render:
            render.side_effect = ChartUnavailable("chart not under test")
            handle_edge(
                "what's the edge if I bought 526-west-end-ave at 1.3m?",
                decision,
                Session(),
                llm=None,
            )
        thesis.assert_called_once_with(REF, overrides={"ask_price": 1_300_000.0})
        analyzer.assert_called_once_with(REF, overrides={"ask_price": 1_300_000.0})

    def test_cma_turn_routes_live_comps_to_market_support_not_value_thesis(self) -> None:
        decision = RouterDecision(
            AnswerType.EDGE, confidence=0.9, target_refs=[REF], reason="test"
        )
        session = Session()
        with patch(
            "briarwood.agent.dispatch.get_value_thesis",
            return_value={
                "ask_price": 767000.0,
                "fair_value_base": 723556.0,
                "premium_discount_pct": 0.057,
                "pricing_view": "appears_fully_valued",
                "value_drivers": [],
                "key_value_drivers": [],
                "what_must_be_true": [],
                "primary_value_source": "current_value",
                "comps": [],
            },
        ), patch(
            "briarwood.agent.dispatch.get_cma",
            return_value=CMAResult(
                property_id=REF,
                address="1008 14th Avenue, Belmar, NJ 07719",
                town="Belmar",
                state="NJ",
                ask_price=767000.0,
                fair_value_base=723556.0,
                value_low=690000.0,
                value_high=760000.0,
                pricing_view="appears_fully_valued",
                primary_value_source="current_value",
                comp_selection_summary="Live Zillow market comps ranked toward the subject.",
                comps=[
                    ComparableProperty(
                        property_id="1302-l-street",
                        address="1302 L Street, Belmar, NJ 07719",
                        town="Belmar",
                        state="NJ",
                        beds=3,
                        baths=2.0,
                        ask_price=850000.0,
                        blocks_to_beach=None,
                        source_label="Live market comp",
                        source_summary="Live Zillow market comp",
                    )
                ],
                confidence_notes=[],
                missing_fields=[],
            ),
        ), patch(
            "briarwood.agent.dispatch.analyze_property",
            side_effect=ToolUnavailable("skip chart"),
        ):
            response = handle_edge("what does the CMA look like?", decision, session, llm=None)

        self.assertIn("1302-l-street", response)
        # F2: thesis had no comps — value_thesis.comps must NOT silently fall
        # back to the live CMA rows. Live comps surface on last_market_support_view
        # and feed the comps_preview so the inline table still renders.
        self.assertEqual(session.last_value_thesis_view["comps"], [])
        self.assertIsNotNone(session.last_market_support_view)
        self.assertEqual(
            session.last_market_support_view["comps"][0]["property_id"],
            "1302-l-street",
        )
        self.assertEqual(session.last_comps_preview["comps"][0]["property_id"], "1302-l-street")


class ResearchHandlerTests(unittest.TestCase):
    def test_build_town_summary_includes_structured_signal_items(self) -> None:
        fake_ctx = type(
            "TownContext",
            (),
            {
                "median_price": 867500,
                "median_ppsf": 516,
                "sold_count": 320,
                "context_confidence": 0.57,
            },
        )()
        with patch(
            "briarwood.modules.town_aggregation_diagnostics.get_town_context",
            return_value=fake_ctx,
        ), patch(
            "briarwood.agent.dispatch.build_town_signal_items",
            return_value=[{"id": "sig-1", "display_line": "1201 Main Street redevelopment plan (approved)"}],
        ), patch(
            "briarwood.local_intelligence.storage.JsonLocalSignalStore.load_town_signals",
            return_value=[],
        ):
            summary = _build_town_summary("Belmar", "NJ")

        self.assertIsNotNone(summary)
        self.assertEqual(summary["signal_items"][0]["id"], "sig-1")

    def test_research_uses_loaded_property_town_context(self) -> None:
        decision = RouterDecision(
            AnswerType.RESEARCH, confidence=0.6, target_refs=[], reason="llm classify"
        )
        session = Session(current_property_id=REF)
        with patch(
            "briarwood.agent.dispatch._summary_town_state",
            return_value=("Belmar", "NJ"),
        ), patch(
            "briarwood.agent.dispatch.research_town",
            return_value={
                "document_count": 3,
                "warnings": [],
                "summary": {
                    "confidence_label": "Medium",
                    "narrative_summary": "Belmar shows active but mixed development signals.",
                    "bullish_signals": ["Board activity is picking up"],
                    "bearish_signals": ["Supply additions could weigh on pricing"],
                    "watch_items": [],
                },
            },
        ) as researcher:
            response = handle_research(
                "is belmar up and coming? is there improvement in the market?",
                decision,
                session,
                llm=None,
            )
        researcher.assert_called_once()
        self.assertIn("Belmar, NJ market read", response)
        self.assertIn("What looks constructive", response)
        self.assertIn("What could weigh on the market", response)
        self.assertIn("signal_items", session.last_research_view)

    def test_research_accepts_explicit_town_state_without_loaded_context(self) -> None:
        decision = RouterDecision(
            AnswerType.RESEARCH, confidence=0.6, target_refs=[], reason="llm classify"
        )
        with patch(
            "briarwood.agent.dispatch.research_town",
            return_value={
                "document_count": 2,
                "warnings": [],
                "summary": {
                    "confidence_label": "Medium",
                    "narrative_summary": "Belmar shows improving demand and selective reinvestment momentum.",
                    "bullish_signals": ["Shore demand remains resilient"],
                    "bearish_signals": [],
                    "watch_items": ["Seasonality"],
                },
            },
        ) as researcher:
            response = handle_research(
                "is belmar NJ up and coming?",
                decision,
                Session(),
                llm=None,
            )
        researcher.assert_called_once_with("Belmar", "NJ", ["development", "demand", "migration"])
        self.assertIn("Belmar, NJ market read", response)
        self.assertIn("Shore demand remains resilient", response)


class ProjectionHandlerTests(unittest.TestCase):
    def test_renovation_resale_question_uses_dedicated_outlook(self) -> None:
        decision = RouterDecision(
            AnswerType.PROJECTION, confidence=0.7, target_refs=[REF], reason="test"
        )
        outlook = RenovationResaleOutlook(
            property_id=REF,
            address="526 West End Ave",
            town="Avon By The Sea",
            state="NJ",
            listing_ask_price=1_499_000,
            entry_basis=699_000,
            all_in_basis=849_000,
            fair_value_base=781_303.46,
            decision_stance="buy_if_price_improves",
            recommendation="Buy if price improves.",
            best_path="Underwrite the renovation path only if margin remains strong after cost and execution friction.",
            renovated_bcv=975_000,
            current_bcv=781_303.46,
            renovation_budget=150_000,
            gross_value_creation=193_696.54,
            net_value_creation=43_696.54,
            roi_pct=29.1,
            total_hold_cost=24_000,
            budget_overrun_margin_pct=18.0,
            margin_scenarios=[
                {"label": "Budget +20%, Value -10%", "net_profit": -12_000},
            ],
            trust_flags=["weak_town_context"],
            key_risks=["Thin carry inputs"],
        )
        with patch(
            "briarwood.agent.dispatch.get_renovation_resale_outlook",
            return_value=outlook,
        ) as outlook_tool:
            response = handle_projection(
                "if we renovated it, what could we turn around and sell it for...lets assume we can get it for 699k",
                decision,
                Session(),
                llm=None,
            )
        outlook_tool.assert_called_once_with(
            REF, overrides={"ask_price": 699_000.0, "mode": "renovated"}
        )
        self.assertIn("Expected resale anchor", response)
        self.assertIn("Rough spread after renovation", response)
        self.assertIn("Stress check", response)
        self.assertIn("Confidence drag", response)


class RentLookupHandlerTests(unittest.TestCase):
    def test_rent_lookup_threads_overrides_and_owner_occupy_then_rent_hint(self) -> None:
        decision = RouterDecision(
            AnswerType.RENT_LOOKUP, confidence=0.75, target_refs=[REF], reason="test"
        )
        with patch(
            "briarwood.agent.dispatch.get_rent_estimate",
            return_value={
                "monthly_rent": 4200,
                "effective_monthly_rent": 3800,
                "rent_source_type": "estimated",
                "rental_ease_label": "Stable Rental Profile",
                "rental_ease_score": 68.0,
                "annual_noi": 22000,
            },
        ) as rent_tool, patch(
            "briarwood.agent.dispatch.get_strategy_fit",
            return_value={"best_path": "Owner-occupy first, then verify the rent-conversion path before committing to a longer hold."},
        ) as fit_tool:
            response = handle_rent_lookup(
                "what would a fully renovated 3 bed 2 bath house rent for in belmar, maybe we can buy it, live there, renovate, rent it",
                decision,
                Session(),
                llm=None,
            )
        rent_tool.assert_called_once_with(REF, overrides={"mode": "renovated"})
        self.assertEqual(fit_tool.call_count, 2)
        self.assertIn("Plain-English rent read", response)
        self.assertIn("Likely path", response)

    def test_future_rent_question_gets_year_horizon_range(self) -> None:
        decision = RouterDecision(
            AnswerType.RENT_LOOKUP, confidence=0.75, target_refs=[REF], reason="future rent rewrite"
        )
        with patch(
            "briarwood.agent.dispatch.get_rent_estimate",
            return_value={
                "monthly_rent": 4200,
                "effective_monthly_rent": 3800,
                "rent_source_type": "estimated",
                "rental_ease_label": "Stable Rental Profile",
                "rental_ease_score": 68.0,
                "annual_noi": 22000,
            },
        ), patch(
            "briarwood.agent.dispatch.get_strategy_fit",
            return_value={},
        ):
            response = handle_rent_lookup(
                "what do you think i could rent the house for in 2 years?",
                decision,
                Session(),
                llm=None,
            )
        self.assertIn("Working 2-year rent range", response)
        self.assertIn("3% annually", response)

    def test_rent_workability_followup_answers_with_break_even(self) -> None:
        decision = RouterDecision(
            AnswerType.RENT_LOOKUP, confidence=0.75, target_refs=[REF], reason="rent-workability rewrite"
        )
        with patch(
            "briarwood.agent.dispatch.get_rent_estimate",
            return_value={
                "monthly_rent": 2352,
                "effective_monthly_rent": 2211,
                "rent_source_type": "provided",
                "rental_ease_label": "Fragile Rental Profile",
                "rental_ease_score": 45.21,
                "annual_noi": 1681,
            },
        ), patch(
            "briarwood.agent.dispatch.get_property_summary",
            return_value={"address": "1008 14th Avenue", "town": "Belmar", "state": "NJ"},
        ), patch(
            "briarwood.agent.dispatch.get_rent_outlook",
            return_value=RentOutlook(
                property_id=REF,
                address="1008 14th Avenue",
                entry_basis=767000,
                current_monthly_rent=2352,
                effective_monthly_rent=2211,
                annual_noi=1681,
                rent_source_type="provided",
                rental_ease_label="Fragile Rental Profile",
                rental_ease_score=45.21,
                horizon_years=None,
                future_rent_low=None,
                future_rent_mid=None,
                future_rent_high=None,
                basis_to_rent_framing="Current rent annualizes to roughly 3.5% of the current basis.",
                owner_occupy_then_rent=None,
                zillow_market_rent=8000,
                zillow_market_rent_low=None,
                zillow_market_rent_high=None,
                zillow_rental_comp_count=5,
                market_context_note="Zillow looks like a different rental regime.",
                carry_offset_ratio=0.38,
                break_even_rent=5898,
                break_even_probability=0.2,
                adjusted_rent_confidence=0.45,
                rent_haircut_pct=0.2,
            ),
        ):
            response = handle_rent_lookup(
                "What rent would make this deal work?",
                decision,
                Session(),
                llm=None,
            )
        self.assertIn("$5,898", response)
        self.assertIn("$2,211", response)


class RiskFollowupHandlerTests(unittest.TestCase):
    def test_missing_data_followup_uses_trust_view(self) -> None:
        decision = RouterDecision(
            AnswerType.RISK, confidence=0.7, target_refs=[REF], reason="trust rewrite"
        )
        session = Session()
        with patch(
            "briarwood.agent.dispatch.get_value_thesis",
            return_value={
                "trust_summary": {
                    "band": "Moderate confidence",
                    "field_completeness": 0.61,
                    "estimated_reliance": 0.34,
                    "trust_flags": ["incomplete_carry_inputs"],
                },
                "why_this_stance": ["Current pricing looks ahead of Briarwood's current fair-value read."],
                "what_changes_my_view": ["Complete the carry-cost inputs (taxes, insurance, financing)."],
                "blocked_thesis_warnings": ["Incomplete carry inputs are still limiting conviction."],
            },
        ), patch(
            "briarwood.agent.dispatch._load_property_facts",
            return_value={"address": "1008 14th Avenue", "town": "Belmar", "state": "NJ"},
        ):
            response = dispatch(
                "What data is missing or estimated?",
                decision,
                session,
                llm=None,
            )
        self.assertIn("incomplete carry inputs", response.lower())
        self.assertIsNotNone(session.last_trust_view)
        self.assertIsNone(session.last_risk_view)


class BrowseAffirmativeEscalationTests(unittest.TestCase):
    """After a BROWSE turn, 'yes/ok/sure' should promote to DECISION."""

    def _session_post_browse(self) -> Session:
        s = Session(current_property_id=REF)
        s.turns.append(Turn(user="tell me about it", assistant="…", answer_type="browse"))
        return s

    def _browse_decision(self) -> RouterDecision:
        return RouterDecision(
            AnswerType.BROWSE, confidence=0.6, target_refs=[], reason="llm classify"
        )

    def test_yes_after_browse_escalates_to_decision(self) -> None:
        out = _escalate_browse_affirmative(
            "yes lets move forward", self._browse_decision(), self._session_post_browse()
        )
        self.assertEqual(out.answer_type, AnswerType.DECISION)
        self.assertEqual(out.target_refs, [REF])
        self.assertEqual(out.reason, "browse-followup escalate")

    def test_ok_sure_after_browse_escalates(self) -> None:
        out = _escalate_browse_affirmative(
            "ok sure", self._browse_decision(), self._session_post_browse()
        )
        self.assertEqual(out.answer_type, AnswerType.DECISION)

    def test_no_escalation_without_prior_browse(self) -> None:
        s = Session(current_property_id=REF)  # no prior turn
        out = _escalate_browse_affirmative("yes", self._browse_decision(), s)
        self.assertEqual(out.answer_type, AnswerType.BROWSE)

    def test_no_escalation_without_pinned_property(self) -> None:
        s = Session()
        s.turns.append(Turn(user="…", assistant="…", answer_type="browse"))
        out = _escalate_browse_affirmative("yes", self._browse_decision(), s)
        self.assertEqual(out.answer_type, AnswerType.BROWSE)

    def test_live_listing_browse_affirmative_escalates_to_decision(self) -> None:
        s = Session(
            current_live_listing={
                "address": "1600 L Street, Belmar, NJ 07719",
                "listing_url": "https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
            }
        )
        s.turns.append(Turn(user="what do you think of this house?", assistant="…", answer_type="browse"))
        out = _escalate_browse_affirmative("yes lets run the full analysis", self._browse_decision(), s)
        self.assertEqual(out.answer_type, AnswerType.DECISION)
        self.assertEqual(out.target_refs, [])

    def test_question_does_not_escalate(self) -> None:
        out = _escalate_browse_affirmative(
            "yes but how big is the yard?",
            self._browse_decision(),
            self._session_post_browse(),
        )
        self.assertEqual(out.answer_type, AnswerType.BROWSE)

    def test_and_after_browse_deepens_to_decision(self) -> None:
        out = _deepen_browse_followup(
            "and?", self._browse_decision(), self._session_post_browse()
        )
        self.assertEqual(out.answer_type, AnswerType.DECISION)
        self.assertEqual(out.reason, "browse-followup deepen")

    def test_go_on_after_browse_deepens_to_decision(self) -> None:
        out = _deepen_browse_followup(
            "go on", self._browse_decision(), self._session_post_browse()
        )
        self.assertEqual(out.answer_type, AnswerType.DECISION)

    def test_dispatch_routes_affirmative_to_decision_handler(self) -> None:
        """End-to-end: dispatch() should call handle_decision, not handle_browse."""
        from unittest.mock import MagicMock

        from briarwood.agent import dispatch as dispatch_mod

        session = self._session_post_browse()
        decision_mock = MagicMock(return_value="D")
        browse_mock = MagicMock(return_value="B")
        table = {
            **dispatch_mod.DISPATCH_TABLE,
            AnswerType.DECISION: decision_mock,
            AnswerType.BROWSE: browse_mock,
        }
        with patch.object(dispatch_mod, "DISPATCH_TABLE", table):
            out = dispatch("yes", self._browse_decision(), session, llm=None)
        decision_mock.assert_called_once()
        browse_mock.assert_not_called()
        self.assertEqual(out, "D")

    def test_dispatch_routes_and_followup_to_decision_handler(self) -> None:
        from unittest.mock import MagicMock

        from briarwood.agent import dispatch as dispatch_mod

        session = self._session_post_browse()
        decision_mock = MagicMock(return_value="D")
        browse_mock = MagicMock(return_value="B")
        table = {
            **dispatch_mod.DISPATCH_TABLE,
            AnswerType.DECISION: decision_mock,
            AnswerType.BROWSE: browse_mock,
        }
        with patch.object(dispatch_mod, "DISPATCH_TABLE", table):
            out = dispatch("and?", self._browse_decision(), session, llm=None)
        decision_mock.assert_called_once()
        browse_mock.assert_not_called()
        self.assertEqual(out, "D")

    def test_dispatch_routes_live_listing_affirmative_to_decision_handler(self) -> None:
        from unittest.mock import MagicMock

        from briarwood.agent import dispatch as dispatch_mod

        session = Session(
            current_live_listing={
                "address": "1600 L Street, Belmar, NJ 07719",
                "listing_url": "https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
            }
        )
        session.turns.append(Turn(user="what do you think of this house?", assistant="…", answer_type="browse"))
        decision_mock = MagicMock(return_value="D")
        browse_mock = MagicMock(return_value="B")
        table = {
            **dispatch_mod.DISPATCH_TABLE,
            AnswerType.DECISION: decision_mock,
            AnswerType.BROWSE: browse_mock,
        }
        with patch.object(dispatch_mod, "DISPATCH_TABLE", table):
            out = dispatch("yes lets run the full analysis", self._browse_decision(), session, llm=None)
        decision_mock.assert_called_once()
        browse_mock.assert_not_called()
        self.assertEqual(out, "D")


class BrowseContextFollowupTests(unittest.TestCase):
    def _session_post_browse(self) -> Session:
        s = Session(current_property_id=REF)
        s.turns.append(Turn(user="tell me about it", assistant="…", answer_type="browse"))
        return s

    def _browse_decision(self) -> RouterDecision:
        return RouterDecision(
            AnswerType.BROWSE, confidence=0.6, target_refs=[], reason="llm classify"
        )

    def test_absorption_followup_rewrites_to_explainer_reason(self) -> None:
        out = contextualize_decision(
            "what is absorption data?", self._browse_decision(), self._session_post_browse()
        )
        self.assertEqual(out.answer_type, AnswerType.BROWSE)
        self.assertEqual(out.reason, "browse-followup explain")

    def test_dispatch_returns_absorption_explanation(self) -> None:
        session = self._session_post_browse()
        with patch(
            "briarwood.agent.dispatch._summary_town_state",
            return_value=("Belmar", "NJ"),
        ):
            out = dispatch(
                "what is absorption data?",
                self._browse_decision(),
                session,
                llm=None,
            )
        self.assertIn("market-speed read", out)
        self.assertIn("Belmar", out)

    def test_town_followup_rewrites_to_research(self) -> None:
        with patch(
            "briarwood.agent.dispatch._summary_town_state",
            return_value=("Belmar", "NJ"),
        ):
            out = contextualize_decision(
                "how is belmar?", self._browse_decision(), self._session_post_browse()
            )
        self.assertEqual(out.answer_type, AnswerType.RESEARCH)
        self.assertEqual(out.reason, "browse-followup town research")

    def test_live_listing_town_followup_rewrites_to_research(self) -> None:
        session = Session(
            current_live_listing={
                "address": "1600 L Street, Belmar, NJ 07719",
                "town": "Belmar",
                "state": "NJ",
                "listing_url": "https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
            }
        )
        session.turns.append(Turn(user="what do you think of this house?", assistant="…", answer_type="browse"))
        out = contextualize_decision(
            "is belmar up and coming?", self._browse_decision(), session
        )
        self.assertEqual(out.answer_type, AnswerType.RESEARCH)
        self.assertEqual(out.reason, "browse-followup town research")

    def test_owner_occupy_then_rent_rewrites_to_strategy(self) -> None:
        session = Session(current_property_id=REF)
        out = contextualize_decision(
            "Could i live here and then rent it out in a couple years?",
            RouterDecision(
                AnswerType.DECISION, confidence=0.6, target_refs=[], reason="llm classify"
            ),
            session,
        )
        self.assertEqual(out.answer_type, AnswerType.STRATEGY)
        self.assertEqual(out.reason, "owner-occupy then rent rewrite")
        self.assertEqual(out.target_refs, [REF])

    def test_future_rent_rewrites_to_rent_lookup(self) -> None:
        session = Session(current_property_id=REF)
        out = contextualize_decision(
            "what do you think i could rent the house for in 2 years?",
            RouterDecision(
                AnswerType.PROJECTION, confidence=0.6, target_refs=[], reason="llm classify"
            ),
            session,
        )
        self.assertEqual(out.answer_type, AnswerType.RENT_LOOKUP)
        self.assertEqual(out.reason, "future rent rewrite")
        self.assertEqual(out.target_refs, [REF])

    def test_cma_rewrites_to_edge_on_active_property(self) -> None:
        session = Session(current_property_id=REF)
        out = contextualize_decision(
            "Can you perform a CMA on this property?",
            RouterDecision(
                AnswerType.SEARCH, confidence=0.6, target_refs=[], reason="llm classify"
            ),
            session,
        )
        self.assertEqual(out.answer_type, AnswerType.EDGE)
        self.assertEqual(out.reason, "cma rewrite")
        self.assertEqual(out.target_refs, [REF])

    def test_cma_rewrites_to_edge_when_property_is_named_in_text(self) -> None:
        session = Session()
        with patch(
            "briarwood.agent.resolver.resolve_property_id",
            return_value=("1600-l-street-belmar-nj-07719", ["1600-l-street-belmar-nj-07719"]),
        ), patch(
            "briarwood.agent.dispatch.saved_property_has_valid_location",
            return_value=True,
        ):
            out = contextualize_decision(
                "can you perform a CMA on 1600 L Street, Belmar, NJ",
                RouterDecision(
                    AnswerType.SEARCH, confidence=0.6, target_refs=[], reason="llm classify"
                ),
                session,
            )
        self.assertEqual(out.answer_type, AnswerType.EDGE)
        self.assertEqual(out.reason, "cma rewrite")
        self.assertEqual(out.target_refs, ["1600-l-street-belmar-nj-07719"])

    def test_comp_set_followup_rewrites_to_edge(self) -> None:
        session = Session(current_property_id=REF)
        out = contextualize_decision(
            "Show me the comp set",
            RouterDecision(
                AnswerType.SEARCH, confidence=0.6, target_refs=[], reason="llm classify"
            ),
            session,
        )
        self.assertEqual(out.answer_type, AnswerType.EDGE)
        self.assertEqual(out.reason, "comp-set rewrite")

    def test_entry_point_followup_rewrites_to_edge(self) -> None:
        session = Session(current_property_id=REF)
        out = contextualize_decision(
            "What's a good entry point?",
            RouterDecision(
                AnswerType.BROWSE, confidence=0.6, target_refs=[], reason="llm classify"
            ),
            session,
        )
        self.assertEqual(out.answer_type, AnswerType.EDGE)
        self.assertEqual(out.reason, "entry-point rewrite")

    def test_missing_data_followup_rewrites_to_risk(self) -> None:
        session = Session(current_property_id=REF)
        out = contextualize_decision(
            "What data is missing or estimated?",
            RouterDecision(
                AnswerType.RISK, confidence=0.6, target_refs=[], reason="llm classify"
            ),
            session,
        )
        self.assertEqual(out.answer_type, AnswerType.RISK)
        self.assertEqual(out.reason, "trust rewrite")

    def test_rent_workability_followup_rewrites_to_rent_lookup(self) -> None:
        session = Session(current_property_id=REF)
        out = contextualize_decision(
            "What rent would make this deal work?",
            RouterDecision(
                AnswerType.PROJECTION, confidence=0.6, target_refs=[], reason="llm classify"
            ),
            session,
        )
        self.assertEqual(out.answer_type, AnswerType.RENT_LOOKUP)
        self.assertEqual(out.reason, "rent-workability rewrite")

    def test_downside_detail_followup_rewrites_to_risk(self) -> None:
        session = Session(current_property_id=REF)
        out = contextualize_decision(
            "Show me the downside case in more detail",
            RouterDecision(
                AnswerType.PROJECTION, confidence=0.6, target_refs=[], reason="llm classify"
            ),
            session,
        )
        self.assertEqual(out.answer_type, AnswerType.RISK)
        self.assertEqual(out.reason, "downside-detail rewrite")

    def test_research_uses_live_listing_context(self) -> None:
        decision = RouterDecision(
            AnswerType.RESEARCH, confidence=0.6, target_refs=[], reason="browse-followup town research"
        )
        session = Session(
            current_live_listing={
                "address": "1600 L Street, Belmar, NJ 07719",
                "town": "Belmar",
                "state": "NJ",
                "listing_url": "https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
            }
        )
        with patch(
            "briarwood.agent.dispatch.promote_discovered_listing",
            return_value=PromotedPropertyRecord(
                property_id="1600-l-street-belmar-nj-07719",
                address="1600 L Street, Belmar, NJ 07719",
                town="Belmar",
                state="NJ",
                promotion_status="created",
                intake_warnings=[],
                created_new=True,
                sourced_fields=["address"],
                inferred_fields=["county"],
                missing_fields=["sqft"],
                listing_url="https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
            ),
        ), patch(
            "briarwood.agent.dispatch.research_town",
            return_value={
                "summary": {
                    "confidence_label": "Moderate",
                    "narrative_summary": "Belmar shows improving demand and selective reinvestment momentum.",
                    "bullish_signals": ["Strong shore demand"],
                    "bearish_signals": [],
                    "watch_items": ["Seasonality"],
                },
                "document_count": 3,
                "warnings": [],
            },
        ) as research:
            out = handle_research("is belmar up and coming?", decision, session, llm=None)
        research.assert_called_once()
        self.assertIn("Belmar, NJ market read", out)
        self.assertIn("Strong shore demand", out)


class MicroLocationHandlerTests(unittest.TestCase):
    def test_micro_location_uses_live_listing_context_when_saved_property_missing(self) -> None:
        decision = RouterDecision(
            AnswerType.MICRO_LOCATION, confidence=0.6, target_refs=[], reason="llm classify"
        )
        session = Session(
            current_live_listing={
                "address": "1600 L Street, Belmar, NJ 07719",
                "town": "Belmar",
                "state": "NJ",
                "listing_url": "https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
            }
        )
        fake_index = type("Idx", (), {"properties": []})()
        with patch(
            "briarwood.agent.dispatch.promote_discovered_listing",
            return_value=PromotedPropertyRecord(
                property_id="1600-l-street-belmar-nj-07719",
                address="1600 L Street, Belmar, NJ 07719",
                town="Belmar",
                state="NJ",
                promotion_status="created",
                intake_warnings=[],
                created_new=True,
                sourced_fields=["address"],
                inferred_fields=["county"],
                missing_fields=["sqft"],
                listing_url="https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
            ),
        ), patch(
            "briarwood.agent.index.load_index", return_value=fake_index
        ):
            response = handle_micro_location("how close to the beach is this house?", decision, session, llm=None)
        self.assertIn("1600-l-street-belmar-nj-07719", response)
        self.assertIn("micro-location row", response)


if __name__ == "__main__":
    unittest.main()
