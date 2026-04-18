"""Hand-curated mock listings for the chat demo.

Lives backend-side because the echo stream emits them through the SSE protocol —
that exercises the full structured-payload path that the real router will use.
Replace with real comp/listing pulls (briarwood.listing_intake / ATTOM) when
the orchestrator bridge lands.
"""
from __future__ import annotations

from typing import Any

# Belmar / Avon-by-the-Sea / Asbury Park — matches the towns the existing
# pipeline already has signal data for.
BELMAR_LISTINGS: list[dict[str, Any]] = [
    {
        "id": "belmar-1600-l",
        "address_line": "1600 L St",
        "city": "Belmar",
        "state": "NJ",
        "zip": "07719",
        "price": 875_000,
        "beds": 3,
        "baths": 2,
        "sqft": 1620,
        "lot_sqft": 4500,
        "year_built": 1958,
        "status": "active",
        "lat": 40.1789,
        "lng": -74.0218,
        "source_url": "https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
        "hue": 18,
    },
    {
        "id": "belmar-briarwood-rd",
        "address_line": "204 Briarwood Rd",
        "city": "Belmar",
        "state": "NJ",
        "zip": "07719",
        "price": 949_000,
        "beds": 4,
        "baths": 3,
        "sqft": 2100,
        "lot_sqft": 5200,
        "year_built": 1972,
        "status": "active",
        "lat": 40.1801,
        "lng": -74.0244,
        "hue": 152,
    },
    {
        "id": "avon-302-woodland",
        "address_line": "302 Woodland Ave",
        "city": "Avon-by-the-Sea",
        "state": "NJ",
        "zip": "07717",
        "price": 1_125_000,
        "beds": 4,
        "baths": 2,
        "sqft": 1980,
        "lot_sqft": 4000,
        "year_built": 1925,
        "status": "active",
        "lat": 40.1900,
        "lng": -74.0150,
        "hue": 210,
    },
    {
        "id": "asbury-505-cookman",
        "address_line": "505 Cookman Ave #3",
        "city": "Asbury Park",
        "state": "NJ",
        "zip": "07712",
        "price": 695_000,
        "beds": 2,
        "baths": 2,
        "sqft": 1180,
        "year_built": 1928,
        "status": "pending",
        "lat": 40.2200,
        "lng": -74.0123,
        "hue": 280,
    },
]


def looks_like_listing_query(text: str) -> bool:
    """Cheap heuristic for the echo-mode demo.

    Replaced by the real router's intent classification once the bridge lands.
    """
    t = text.lower()
    triggers = (
        "listing",
        "listings",
        "homes",
        "houses",
        "find me",
        "show me",
        "for sale",
        "starter home",
        "3br",
        "4br",
        "under $",
        "belmar",
        "avon",
        "asbury",
    )
    return any(trigger in t for trigger in triggers)


def mock_listings_for(text: str) -> list[dict[str, Any]]:
    """Return a small slate of listings biased to whatever the user mentioned."""
    t = text.lower()
    pool = list(BELMAR_LISTINGS)
    if "asbury" in t:
        pool.sort(key=lambda l: 0 if l["city"].lower() == "asbury park" else 1)
    elif "avon" in t:
        pool.sort(key=lambda l: 0 if "avon" in l["city"].lower() else 1)
    return pool[:4]


def map_payload_for(listings: list[dict[str, Any]]) -> dict[str, Any]:
    if not listings:
        return {"center": [-74.02, 40.18], "pins": []}
    lat = sum(l["lat"] for l in listings) / len(listings)
    lng = sum(l["lng"] for l in listings) / len(listings)
    pins = [
        {
            "id": l["id"],
            "lat": l["lat"],
            "lng": l["lng"],
            "label": f"${l['price'] // 1000}k",
        }
        for l in listings
    ]
    return {"center": [lng, lat], "pins": pins}
