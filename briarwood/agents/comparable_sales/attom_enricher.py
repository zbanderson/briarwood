"""
Enrich comparable sales with ATTOM property detail API data.

ATTOM provides parcel-level detail (beds, baths, sqft, year_built, lot_size,
lat/lon, stories, garage_spaces, condition) that may be missing from seed
comp data or SR1A-ingested records.

Usage (programmatic):
    from briarwood.agents.comparable_sales.attom_enricher import ATTOMEnricher
    enricher = ATTOMEnricher(api_key="...")
    result = enricher.enrich_store("data/comps/sales_comps.json")

Usage (CLI):
    python -m briarwood.agents.comparable_sales.attom_enricher \
        --comps data/comps/sales_comps.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

# ATTOM API base URL
_BASE_URL = "https://api.gateway.attomdata.com/propertyapi/v1.0.0"

# Rate-limit: ATTOM free tier allows ~1 req/sec
_REQUEST_DELAY_SECONDS = 0.5

# Zip codes for Monmouth County towns in our comp set.
# ATTOM requires zip for reliable address matching.
_TOWN_ZIP_CODES: dict[str, str] = {
    "Asbury Park": "07712",
    "Avon By The Sea": "07717",
    "Belmar": "07719",
    "Bradley Beach": "07720",
    "Brookline": "07719",  # unincorporated area within Belmar zip
    "Manasquan": "08736",
    "Neptune": "07753",
    "Neptune City": "07753",
    "Ocean Grove": "07756",
    "Sea Girt": "08750",
    "Spring Lake": "07762",
    "Spring Lake Heights": "07762",
    "Wall Township": "07719",
    "Wall": "07719",
    "Lake Como": "07719",
    "South Belmar": "07719",
}


@dataclass(slots=True)
class ATTOMEnrichResult:
    """Summary of an ATTOM enrichment run."""
    total_records: int = 0
    records_needing_enrichment: int = 0
    api_calls_made: int = 0
    api_calls_succeeded: int = 0
    api_calls_failed: int = 0
    beds_enriched: int = 0
    baths_enriched: int = 0
    sqft_enriched: int = 0
    year_built_enriched: int = 0
    lot_size_enriched: int = 0
    latlon_enriched: int = 0
    stories_enriched: int = 0
    garage_enriched: int = 0
    errors: list[str] = field(default_factory=list)


def _needs_enrichment(sale: dict) -> bool:
    """Return True if the sale record has any missing fields ATTOM can fill."""
    return (
        not sale.get("beds")
        or not sale.get("baths")
        or not sale.get("sqft")
        or not sale.get("year_built")
        or not sale.get("lot_size")
        or not sale.get("latitude")
        or not sale.get("stories")
    )


class ATTOMEnricher:
    """Look up property details from the ATTOM API and enrich comp records."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("ATTOM_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "ATTOM API key required. Set ATTOM_API_KEY env var or pass api_key=."
            )
        self._session = requests.Session()
        self._session.headers.update({
            "apikey": self._api_key,
            "Accept": "application/json",
        })

    def lookup_property(self, address1: str, address2: str) -> dict | None:
        """Look up a single property by address.

        Args:
            address1: Street address (e.g. "304 14th Ave")
            address2: City, state zip (e.g. "Belmar, NJ 07719")

        Returns:
            The first property dict from ATTOM response, or None on failure.
        """
        url = f"{_BASE_URL}/property/detail"
        params = {"address1": address1, "address2": address2}

        try:
            resp = self._session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                properties = data.get("property", [])
                if properties:
                    return properties[0]
                logger.debug("ATTOM: no property found for %s, %s", address1, address2)
                return None
            elif resp.status_code == 404:
                logger.debug("ATTOM 404: %s, %s", address1, address2)
                return None
            else:
                logger.warning(
                    "ATTOM API error %d for %s, %s: %s",
                    resp.status_code, address1, address2, resp.text[:200],
                )
                return None
        except requests.RequestException as exc:
            logger.warning("ATTOM request failed for %s, %s: %s", address1, address2, exc)
            return None

    @staticmethod
    def extract_fields(prop: dict) -> dict:
        """Extract enrichment fields from an ATTOM property response."""
        building = prop.get("building", {})
        rooms = building.get("rooms", {})
        size = building.get("size", {})
        construction = building.get("construction", {})
        parking = building.get("parking", {})
        bldg_summary = building.get("summary", {})
        lot = prop.get("lot", {})
        location = prop.get("location", {})
        summary = prop.get("summary", {})

        # Extract beds
        beds = rooms.get("beds")
        if beds is not None:
            beds = int(beds) if beds > 0 else None

        # Extract baths (prefer bathstotal, fall back to bathsfull)
        baths = rooms.get("bathstotal")
        if baths is None:
            baths = rooms.get("bathsfull")
        if baths is not None:
            baths = float(baths) if baths > 0 else None

        # Extract sqft (prefer universalsize, fall back to livingsize, bldgsize)
        sqft = size.get("universalsize") or size.get("livingsize") or size.get("bldgsize")
        if sqft is not None:
            sqft = int(sqft) if sqft > 0 else None

        # Year built
        year_built = summary.get("yearbuilt")
        if year_built is not None:
            year_built = int(year_built) if 1700 < year_built <= 2030 else None

        # Lot size in acres
        lot_size = lot.get("lotsize1")
        if lot_size is not None:
            lot_size = round(float(lot_size), 4) if lot_size > 0 else None

        # Lat/lon
        lat = location.get("latitude")
        lon = location.get("longitude")
        if lat is not None:
            lat = float(lat)
        if lon is not None:
            lon = float(lon)

        # Stories
        stories = bldg_summary.get("levels")
        if stories is not None:
            stories = float(stories) if stories > 0 else None

        # Garage
        garage = parking.get("garagetype")
        garage_spaces = parking.get("prkgSpaces")
        if garage_spaces is not None:
            try:
                garage_spaces = int(float(str(garage_spaces)))
                if garage_spaces <= 0:
                    garage_spaces = None
            except (ValueError, TypeError):
                garage_spaces = None
        elif garage and str(garage).upper() not in ("", "NONE"):
            garage_spaces = 1  # ATTOM often has type but not count

        return {
            "beds": beds,
            "baths": baths,
            "sqft": sqft,
            "year_built": year_built,
            "lot_size": lot_size,
            "latitude": lat,
            "longitude": lon,
            "stories": stories,
            "garage_spaces": garage_spaces,
        }

    def _build_address2(self, sale: dict) -> str:
        """Build the city/state/zip string for ATTOM lookup."""
        town = sale.get("town", "")
        state = sale.get("state", "NJ")
        zip_code = _TOWN_ZIP_CODES.get(town, "")
        if zip_code:
            return f"{town}, {state} {zip_code}"
        return f"{town}, {state}"

    def enrich_store(
        self,
        comps_path: str | Path,
        *,
        dry_run: bool = False,
        max_calls: int | None = None,
    ) -> ATTOMEnrichResult:
        """Enrich all records in a comp store JSON file with ATTOM data.

        Args:
            comps_path: Path to the JSON comp store.
            dry_run: If True, look up but don't save.
            max_calls: Optional cap on API calls (for testing/budgeting).
        """
        result = ATTOMEnrichResult()
        path = Path(comps_path)
        dataset = json.loads(path.read_text(encoding="utf-8"))
        sales = dataset.get("sales", [])
        result.total_records = len(sales)

        # Find records that need enrichment
        to_enrich = [
            (idx, sale) for idx, sale in enumerate(sales)
            if isinstance(sale, dict) and _needs_enrichment(sale)
        ]
        result.records_needing_enrichment = len(to_enrich)
        logger.info(
            "ATTOM enrichment: %d of %d records need enrichment",
            len(to_enrich), len(sales),
        )

        for idx, sale in to_enrich:
            if max_calls is not None and result.api_calls_made >= max_calls:
                logger.info("Reached max_calls=%d, stopping.", max_calls)
                break

            address1 = sale.get("address", "")
            address2 = self._build_address2(sale)
            if not address1:
                continue

            result.api_calls_made += 1
            prop = self.lookup_property(address1, address2)

            if prop is None:
                result.api_calls_failed += 1
                continue

            result.api_calls_succeeded += 1
            fields = self.extract_fields(prop)

            # Apply fields only where the sale record is missing data
            if not sale.get("beds") and fields["beds"] is not None:
                sale["beds"] = fields["beds"]
                result.beds_enriched += 1

            if not sale.get("baths") and fields["baths"] is not None:
                sale["baths"] = fields["baths"]
                result.baths_enriched += 1

            if not sale.get("sqft") and fields["sqft"] is not None:
                sale["sqft"] = fields["sqft"]
                result.sqft_enriched += 1

            if not sale.get("year_built") and fields["year_built"] is not None:
                sale["year_built"] = fields["year_built"]
                result.year_built_enriched += 1

            if not sale.get("lot_size") and fields["lot_size"] is not None:
                sale["lot_size"] = fields["lot_size"]
                result.lot_size_enriched += 1

            if not sale.get("latitude") and fields["latitude"] is not None:
                sale["latitude"] = fields["latitude"]
                sale["longitude"] = fields["longitude"]
                result.latlon_enriched += 1

            if not sale.get("stories") and fields["stories"] is not None:
                sale["stories"] = fields["stories"]
                result.stories_enriched += 1

            if not sale.get("garage_spaces") and fields["garage_spaces"] is not None:
                sale["garage_spaces"] = fields["garage_spaces"]
                result.garage_enriched += 1

            # Throttle to respect rate limits
            time.sleep(_REQUEST_DELAY_SECONDS)

        if not dry_run and result.api_calls_succeeded > 0:
            dataset["metadata"] = dataset.get("metadata", {})
            dataset["metadata"]["attom_enrichment_date"] = time.strftime("%Y-%m-%d")
            dataset["metadata"]["attom_records_enriched"] = result.api_calls_succeeded
            path.write_text(json.dumps(dataset, indent=2) + "\n", encoding="utf-8")
            logger.info("Saved enriched dataset to %s", path)

        logger.info(
            "ATTOM enrichment complete: %d calls, %d succeeded, "
            "%d beds, %d baths, %d sqft, %d year_built, %d lot_size, %d lat/lon",
            result.api_calls_made, result.api_calls_succeeded,
            result.beds_enriched, result.baths_enriched, result.sqft_enriched,
            result.year_built_enriched, result.lot_size_enriched, result.latlon_enriched,
        )
        return result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Enrich Briarwood comp store with ATTOM property detail data."
    )
    parser.add_argument(
        "--comps",
        default="data/comps/sales_comps.json",
        help="Path to the JSON comp store.",
    )
    parser.add_argument(
        "--max-calls",
        type=int,
        default=None,
        help="Max API calls to make (for testing/budgeting).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Look up data but don't save changes.",
    )
    args = parser.parse_args()

    enricher = ATTOMEnricher()
    result = enricher.enrich_store(
        args.comps,
        dry_run=args.dry_run,
        max_calls=args.max_calls,
    )

    print(f"\n{'='*60}")
    print("Briarwood ATTOM Enrichment — Summary")
    print(f"{'='*60}")
    print(f"Total records:             {result.total_records}")
    print(f"Needing enrichment:        {result.records_needing_enrichment}")
    print(f"API calls made:            {result.api_calls_made}")
    print(f"API calls succeeded:       {result.api_calls_succeeded}")
    print(f"API calls failed:          {result.api_calls_failed}")
    print(f"  beds enriched:           {result.beds_enriched}")
    print(f"  baths enriched:          {result.baths_enriched}")
    print(f"  sqft enriched:           {result.sqft_enriched}")
    print(f"  year_built enriched:     {result.year_built_enriched}")
    print(f"  lot_size enriched:       {result.lot_size_enriched}")
    print(f"  lat/lon enriched:        {result.latlon_enriched}")
    print(f"  stories enriched:        {result.stories_enriched}")
    print(f"  garage enriched:         {result.garage_enriched}")
    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  - {err}")
    print()
    return 0 if not result.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
