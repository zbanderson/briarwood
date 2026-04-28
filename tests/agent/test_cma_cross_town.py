"""CMA Phase 4a Cycle 4 — cross-town comp expansion tests.

Pins:
- ``cma_invariants.TOWN_ADJACENCY`` map shape and per-town adjacencies.
- ``cma_invariants.neighbors_for_town`` lookup behavior (case-insensitive,
  hyphen-tolerant, missing-town → empty).
- ``_live_zillow_cma_candidates`` cross-town SOLD expansion: triggers only
  when same-town SOLD count is below ``MIN_SOLD_COUNT``; tags cross-town
  rows; updates ``comp_selection_summary``; never fires on ACTIVE.
- ``get_cma`` propagation of ``is_cross_town`` onto ``ComparableProperty``.

The mock SearchApi client switches on the ``query`` string (``"<Town>,
NJ"``) so per-town fixtures can be returned independently. This is the
pattern needed to exercise the multi-town call path without hitting live
APIs.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from briarwood.agent.tools import (
    CMAResult,
    _live_zillow_cma_candidates,
    get_cma,
)
from briarwood.data_sources.searchapi_zillow_client import (
    SearchApiZillowListingCandidate,
    SearchApiZillowResponse,
)
from briarwood.modules import cma_invariants


_SUMMARY = {
    "address": "1008 14th Avenue, Belmar, NJ 07719",
    "town": "Belmar",
    "state": "NJ",
    "beds": 3,
    "baths": 1.0,
    "ask_price": 767_000.0,
}


def _make_candidate(
    *,
    address: str,
    town: str = "Belmar",
    price: float = 800_000.0,
    beds: int = 3,
    baths: float = 2.0,
    date_sold: str | None = None,
    days_on_market: int | None = None,
) -> SearchApiZillowListingCandidate:
    return SearchApiZillowListingCandidate(
        zpid=address.split()[0],
        address=address,
        town=town,
        state="NJ",
        zip_code="07719",
        price=price,
        beds=beds,
        baths=baths,
        sqft=1_500,
        property_type="single_family",
        listing_status=None,
        listing_url=None,
        date_sold=date_sold,
        days_on_market=days_on_market,
        tax_assessed_value=453_000.0,
        zestimate=820_000.0,
        rent_zestimate=4_200.0,
        lot_sqft=5_000.0,
    )


def _make_response(candidates: list[SearchApiZillowListingCandidate]) -> SearchApiZillowResponse:
    return SearchApiZillowResponse(
        cache_key="test",
        raw_payload={"properties": []},
        normalized_payload={
            "results": [
                {
                    "zpid": c.zpid,
                    "address": c.address,
                    "town": c.town,
                    "state": c.state,
                    "price": c.price,
                    "beds": c.beds,
                    "baths": c.baths,
                    "sqft": c.sqft,
                    "property_type": c.property_type,
                    "lot_sqft": c.lot_sqft,
                    "date_sold": c.date_sold,
                    "days_on_market": c.days_on_market,
                    "tax_assessed_value": c.tax_assessed_value,
                    "zestimate": c.zestimate,
                    "rent_zestimate": c.rent_zestimate,
                }
                for c in candidates
            ],
        },
        from_cache=False,
        fetched_at="2026-04-26T12:00:00Z",
        error=None,
    )


def _patch_searchapi_per_town(
    sold_by_town: dict[str, list[SearchApiZillowListingCandidate]],
    active_by_town: dict[str, list[SearchApiZillowListingCandidate]] | None = None,
):
    """Mock SearchApi client that returns per-town fixtures.

    ``sold_by_town`` keys are town names matching what the production
    code passes as ``query="<town>, <state>"``. The mock parses the town
    out of the query string and returns the matching list (empty list
    when missing). ``active_by_town`` is similar; default empty.
    """
    active_by_town = active_by_town or {}
    mock = MagicMock()
    mock.is_configured = True

    def _search(*, query, listing_status=None, max_results=None, beds_min=None):
        # Query is "<Town>, NJ" — extract the town.
        town = query.split(",", 1)[0].strip() if isinstance(query, str) else ""
        if listing_status == "sold":
            return _make_response(sold_by_town.get(town, []))
        return _make_response(active_by_town.get(town, []))

    mock.search_listings.side_effect = _search

    from briarwood.data_sources.searchapi_zillow_client import (
        SearchApiZillowClient as _RealClient,
    )

    mock.to_listing_candidates = _RealClient.to_listing_candidates.__get__(mock)
    return mock


# ---------------------------------------------------------------------------
# TOWN_ADJACENCY shape + neighbors_for_town lookup
# ---------------------------------------------------------------------------


class TownAdjacencyMapTests(unittest.TestCase):
    def test_six_target_towns_present(self):
        expected = {
            "Belmar",
            "Avon By The Sea",
            "Bradley Beach",
            "Spring Lake",
            "Sea Girt",
            "Manasquan",
        }
        self.assertEqual(set(cma_invariants.TOWN_ADJACENCY.keys()), expected)

    def test_each_town_has_at_least_one_neighbor(self):
        for town, neighbors in cma_invariants.TOWN_ADJACENCY.items():
            self.assertIsInstance(neighbors, tuple, town)
            self.assertGreater(len(neighbors), 0, f"{town} has no neighbors")

    def test_no_self_reference(self):
        for town, neighbors in cma_invariants.TOWN_ADJACENCY.items():
            self.assertNotIn(town, neighbors, f"{town} is its own neighbor")

    def test_specific_belmar_neighbors_pinned(self):
        # Pin the value so future drift fails CI.
        self.assertEqual(
            cma_invariants.TOWN_ADJACENCY["Belmar"],
            ("Bradley Beach", "Spring Lake", "Avon By The Sea"),
        )

    def test_specific_manasquan_neighbors_pinned(self):
        # Manasquan is the southern endpoint — Sea Girt + Spring Lake.
        self.assertEqual(
            cma_invariants.TOWN_ADJACENCY["Manasquan"],
            ("Sea Girt", "Spring Lake"),
        )

    def test_neighbors_for_town_returns_tuple(self):
        result = cma_invariants.neighbors_for_town("Belmar")
        self.assertIsInstance(result, tuple)
        self.assertEqual(result, ("Bradley Beach", "Spring Lake", "Avon By The Sea"))

    def test_neighbors_for_town_case_insensitive(self):
        # "BELMAR", "belmar", "Belmar" should all resolve identically.
        canonical = cma_invariants.neighbors_for_town("Belmar")
        self.assertEqual(cma_invariants.neighbors_for_town("BELMAR"), canonical)
        self.assertEqual(cma_invariants.neighbors_for_town("belmar"), canonical)
        self.assertEqual(cma_invariants.neighbors_for_town("  belmar  "), canonical)

    def test_neighbors_for_town_hyphen_tolerant(self):
        # "Avon-by-the-Sea" (the normalize_town output) and
        # "Avon By The Sea" (the human-readable form) should both resolve.
        canonical = cma_invariants.neighbors_for_town("Avon By The Sea")
        self.assertEqual(cma_invariants.neighbors_for_town("Avon-by-the-Sea"), canonical)
        self.assertEqual(cma_invariants.neighbors_for_town("avon-BY-the-SEA"), canonical)

    def test_unknown_town_returns_empty(self):
        # Towns outside the supported geography → empty tuple → no cross-town.
        self.assertEqual(cma_invariants.neighbors_for_town("Cape May"), ())
        self.assertEqual(cma_invariants.neighbors_for_town("Hoboken"), ())

    def test_empty_or_none_returns_empty(self):
        self.assertEqual(cma_invariants.neighbors_for_town(""), ())
        self.assertEqual(cma_invariants.neighbors_for_town("   "), ())
        self.assertEqual(cma_invariants.neighbors_for_town(None), ())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _live_zillow_cma_candidates — cross-town expansion behavior
# ---------------------------------------------------------------------------


class CrossTownExpansionTests(unittest.TestCase):
    def test_no_expansion_when_sold_count_meets_floor(self):
        # 5 same-town SOLD == MIN_SOLD_COUNT → no cross-town expansion.
        same_town_sold = [
            _make_candidate(
                address=f"{i} Same St, Belmar, NJ 07719",
                town="Belmar",
                date_sold="2026-04-01",
            )
            for i in range(5)
        ]
        # Cross-town fixtures populated but should NOT be queried.
        cross_town_sold = [
            _make_candidate(
                address="999 BB Ave, Bradley Beach, NJ 07720",
                town="Bradley Beach",
                date_sold="2026-04-05",
            )
        ]
        sold_by_town = {"Belmar": same_town_sold, "Bradley Beach": cross_town_sold}

        with patch(
            "briarwood.agent.tools.SearchApiZillowClient",
            return_value=_patch_searchapi_per_town(sold_by_town),
        ), patch(
            "briarwood.agent.tools._fallback_saved_cma_candidates",
            return_value=([], ""),
        ):
            result = _live_zillow_cma_candidates("subj-1", _SUMMARY, subject_ask=767_000.0)

        rows = result["rows"]
        self.assertEqual(len(rows), 5)
        # All same-town. No row tagged is_cross_town.
        for row in rows:
            self.assertFalse(bool(row.get("is_cross_town")))
        self.assertNotIn("cross-town", result["summary"])

    def test_expansion_fires_when_sold_count_below_floor(self):
        # 3 same-town SOLD (< MIN_SOLD_COUNT=5) → cross-town expansion fires.
        same_town_sold = [
            _make_candidate(
                address=f"{i} Same St, Belmar, NJ 07719",
                town="Belmar",
                date_sold="2026-04-01",
            )
            for i in range(3)
        ]
        cross_town_sold_bb = [
            _make_candidate(
                address=f"BB-{i} Bradley Way, Bradley Beach, NJ 07720",
                town="Bradley Beach",
                date_sold="2026-04-05",
            )
            for i in range(2)
        ]
        cross_town_sold_sl = [
            _make_candidate(
                address=f"SL-{i} Spring Way, Spring Lake, NJ 07762",
                town="Spring Lake",
                date_sold="2026-04-10",
            )
            for i in range(2)
        ]
        # Avon By The Sea returns nothing (third neighbor) — exercises empty
        # neighbor response.
        sold_by_town = {
            "Belmar": same_town_sold,
            "Bradley Beach": cross_town_sold_bb,
            "Spring Lake": cross_town_sold_sl,
            "Avon By The Sea": [],
        }

        with patch(
            "briarwood.agent.tools.SearchApiZillowClient",
            return_value=_patch_searchapi_per_town(sold_by_town),
        ), patch(
            "briarwood.agent.tools._fallback_saved_cma_candidates",
            return_value=([], ""),
        ):
            result = _live_zillow_cma_candidates("subj-1", _SUMMARY, subject_ask=767_000.0)

        rows = result["rows"]
        # 3 same-town + 4 cross-town = 7 SOLD (no ACTIVE in fixture).
        self.assertEqual(len(rows), 7)
        cross_town_rows = [r for r in rows if r.get("is_cross_town")]
        same_town_rows = [r for r in rows if not r.get("is_cross_town")]
        self.assertEqual(len(cross_town_rows), 4)
        self.assertEqual(len(same_town_rows), 3)

        # Cross-town rows carry neighbor-aware selection_rationale.
        for row in cross_town_rows:
            self.assertIn("neighboring", row["selection_rationale"])
        # Cross-town towns recorded in row.town for chart/prose.
        cross_town_towns = sorted({r["town"] for r in cross_town_rows})
        self.assertEqual(cross_town_towns, ["Bradley Beach", "Spring Lake"])

    def test_summary_describes_cross_town_addition(self):
        same_town_sold = [
            _make_candidate(
                address=f"{i} Same St, Belmar, NJ 07719",
                town="Belmar",
                date_sold="2026-04-01",
            )
            for i in range(2)
        ]
        cross_town_sold = [
            _make_candidate(
                address=f"BB-{i} Bradley Way, Bradley Beach, NJ 07720",
                town="Bradley Beach",
                date_sold="2026-04-05",
            )
            for i in range(3)
        ]
        sold_by_town = {
            "Belmar": same_town_sold,
            "Bradley Beach": cross_town_sold,
            "Spring Lake": [],
            "Avon By The Sea": [],
        }

        with patch(
            "briarwood.agent.tools.SearchApiZillowClient",
            return_value=_patch_searchapi_per_town(sold_by_town),
        ), patch(
            "briarwood.agent.tools._fallback_saved_cma_candidates",
            return_value=([], ""),
        ):
            result = _live_zillow_cma_candidates("subj-1", _SUMMARY, subject_ask=767_000.0)

        # 2 same-town SOLD + 3 cross-town SOLD = 5 total SOLD; cross-town count = 3.
        self.assertIn("5 SOLD (3 cross-town)", result["summary"])

    def test_unknown_town_no_expansion_attempt(self):
        # Subject in a town outside TOWN_ADJACENCY → no cross-town expansion
        # (trigger may fire on count, but neighbors_for_town returns empty).
        out_of_geo_summary = dict(_SUMMARY, town="Cape May")
        # 2 same-town SOLD < MIN_SOLD_COUNT, but Cape May has no neighbors.
        same_town_sold = [
            _make_candidate(
                address=f"{i} Cape Way, Cape May, NJ 08204",
                town="Cape May",
                date_sold="2026-04-01",
            )
            for i in range(2)
        ]
        # Saved fallback fixture so we can verify TOTAL floor still kicks in
        # the saved fallback (cross-town expansion does NOT fire because
        # adjacency is empty).
        saved_rows = [
            {
                "property_id": f"saved-{i}",
                "address": f"saved-{i} Saved St, Cape May, NJ 08204",
                "town": "Cape May",
                "state": "NJ",
                "beds": 3,
                "baths": 2.0,
                "ask_price": 800_000.0,
                "blocks_to_beach": None,
                "selection_rationale": "saved",
                "source_kind": "saved_comp",
                "source_summary": "saved",
            }
            for i in range(3)
        ]

        def _fake_fallback(_pid, _summary, _ask):
            return saved_rows, "saved"

        with patch(
            "briarwood.agent.tools.SearchApiZillowClient",
            return_value=_patch_searchapi_per_town({"Cape May": same_town_sold}),
        ), patch(
            "briarwood.agent.tools._fallback_saved_cma_candidates",
            side_effect=_fake_fallback,
        ):
            result = _live_zillow_cma_candidates("subj-1", out_of_geo_summary, subject_ask=767_000.0)

        rows = result["rows"]
        # No cross-town rows.
        for row in rows:
            self.assertFalse(bool(row.get("is_cross_town")))
        # Saved fallback STILL fires because TOTAL count was below MIN_TOTAL.
        self.assertIn("saved fallback", result["summary"])
        self.assertNotIn("cross-town", result["summary"])

    def test_active_inventory_not_expanded_cross_town(self):
        # Same-town SOLD plenty, ACTIVE thin → no cross-town expansion fires
        # at all (cross-town is SOLD-only by design).
        same_town_sold = [
            _make_candidate(
                address=f"{i} Same St, Belmar, NJ 07719",
                town="Belmar",
                date_sold="2026-04-01",
            )
            for i in range(6)
        ]
        # 1 same-town ACTIVE — below MIN_ACTIVE_COUNT (3) but should NOT
        # trigger cross-town expansion either (cross-town is for SOLD only).
        same_town_active = [
            _make_candidate(
                address="A1 Active Ave, Belmar, NJ 07719",
                town="Belmar",
                days_on_market=14,
            )
        ]
        # Cross-town fixtures populated but cross-town expansion should
        # never fire (same-town SOLD already meets the floor).
        cross_town_sold = [
            _make_candidate(
                address="BB Cross, Bradley Beach, NJ 07720",
                town="Bradley Beach",
                date_sold="2026-04-05",
            )
        ]
        sold_by_town = {"Belmar": same_town_sold, "Bradley Beach": cross_town_sold}
        active_by_town = {"Belmar": same_town_active}

        with patch(
            "briarwood.agent.tools.SearchApiZillowClient",
            return_value=_patch_searchapi_per_town(sold_by_town, active_by_town),
        ), patch(
            "briarwood.agent.tools._fallback_saved_cma_candidates",
            return_value=([], ""),
        ):
            result = _live_zillow_cma_candidates("subj-1", _SUMMARY, subject_ask=767_000.0)

        rows = result["rows"]
        cross_town_rows = [r for r in rows if r.get("is_cross_town")]
        self.assertEqual(len(cross_town_rows), 0)


# ---------------------------------------------------------------------------
# get_cma propagation of is_cross_town to ComparableProperty
# ---------------------------------------------------------------------------


class GetCmaCrossTownPropagationTests(unittest.TestCase):
    def test_is_cross_town_flag_reaches_comparable_property(self):
        # 3 same-town SOLD + 3 cross-town SOLD; verify ComparableProperty
        # carries is_cross_town=True for the cross-town rows.
        same_town_sold = [
            _make_candidate(
                address=f"{i} Same St, Belmar, NJ 07719",
                town="Belmar",
                date_sold="2026-04-01",
            )
            for i in range(3)
        ]
        cross_town_sold = [
            _make_candidate(
                address=f"BB-{i} Bradley Way, Bradley Beach, NJ 07720",
                town="Bradley Beach",
                date_sold="2026-04-05",
            )
            for i in range(3)
        ]
        sold_by_town = {
            "Belmar": same_town_sold,
            "Bradley Beach": cross_town_sold,
            "Spring Lake": [],
            "Avon By The Sea": [],
        }
        thesis = {
            "ask_price": 767_000.0,
            "fair_value_base": 720_000.0,
            "value_low": 700_000.0,
            "value_high": 750_000.0,
            "pricing_view": "fair",
            "primary_value_source": "comp_anchor",
        }

        with patch(
            "briarwood.agent.tools.SearchApiZillowClient",
            return_value=_patch_searchapi_per_town(sold_by_town),
        ), patch(
            "briarwood.agent.tools.get_property_summary",
            return_value=_SUMMARY,
        ), patch(
            "briarwood.agent.tools._attom_subject_cma_notes",
            return_value=[],
        ), patch(
            "briarwood.agent.tools._fallback_saved_cma_candidates",
            return_value=([], ""),
        ):
            result = get_cma("subj-1", thesis=thesis)

        self.assertIsInstance(result, CMAResult)
        cross_town_comps = [c for c in result.comps if c.is_cross_town]
        same_town_comps = [c for c in result.comps if not c.is_cross_town]

        self.assertEqual(len(cross_town_comps), 3)
        self.assertEqual(len(same_town_comps), 3)
        # Cross-town comps actually live in neighboring towns.
        self.assertTrue(all(c.town == "Bradley Beach" for c in cross_town_comps))
        # comp_selection_summary mentions the cross-town addition.
        self.assertIn("cross-town", result.comp_selection_summary or "")


if __name__ == "__main__":
    unittest.main()
