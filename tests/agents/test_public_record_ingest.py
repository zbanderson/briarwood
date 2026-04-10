"""Tests for the SR1A parser, MOD-IV enricher, and bulk ingestion pipeline."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from briarwood.agents.comparable_sales.sr1a_parser import (
    MONMOUTH_DISTRICT_CODES,
    SR1ARawRecord,
    SR1AParseResult,
    _full_block_lot,
    _is_residential,
    _is_usable_sale,
    _parse_deed_date,
    parse_sr1a_file,
    parse_sr1a_line,
)
from briarwood.agents.comparable_sales.modiv_enricher import MODIVEnricher, MODIVRecord
from briarwood.agents.comparable_sales.ingest_public_bulk import run_bulk_ingest
from briarwood.agents.comparable_sales.store import JsonComparableSalesStore


def _build_sr1a_line(
    *,
    county: str = "13",
    district: str = "07",
    un_type: str = "U",
    nu_code: str = "   ",
    reported_price: int = 750000,
    verified_price: int = 750000,
    assessed_land: int = 200000,
    assessed_bldg: int = 300000,
    assessed_total: int = 500000,
    property_location: str = "304 14TH AVE",
    deed_date: str = "031526",  # MMDDYY = March 15, 2026
    block: str = "00123",
    block_suffix: str = "    ",
    lot: str = "00045",
    lot_suffix: str = "    ",
    property_class: str = " 2",
    condo: str = "N",
    year_built: str = "1940",
    living_space: str = "0001298",
    serial_number: str = "0012345",
    deed_book: str = "06789",
    deed_page: str = "00123",
    grantor_name: str = "DOE, JOHN",
    grantee_name: str = "SMITH, JANE",
) -> str:
    """Build a synthetic 662-character SR1A fixed-width line."""
    line = [" "] * 662

    def place(start: int, end: int, value: str) -> None:
        for i, ch in enumerate(value[:end - start + 1]):
            line[start - 1 + i] = ch

    place(1, 2, county.ljust(2))
    place(3, 4, district.ljust(2))
    place(5, 9, "00001")         # batch
    place(10, 16, "0000001")     # DLN
    place(17, 19, "ZAA")         # operator
    place(20, 25, "260401")      # last update
    place(34, 34, un_type)
    place(35, 37, nu_code)
    place(38, 46, str(reported_price).zfill(9))
    place(47, 55, str(verified_price).zfill(9))
    place(56, 64, str(assessed_land).zfill(9))
    place(65, 73, str(assessed_bldg).zfill(9))
    place(74, 82, str(assessed_total).zfill(9))
    place(99, 105, serial_number)
    place(110, 144, grantor_name.ljust(35))
    place(204, 238, grantee_name.ljust(35))
    place(298, 322, property_location.ljust(25))
    place(329, 333, deed_book)
    place(334, 338, deed_page)
    place(339, 344, deed_date)
    place(351, 355, block)
    place(356, 359, block_suffix)
    place(360, 364, lot)
    place(365, 368, lot_suffix)
    place(627, 628, property_class)
    place(649, 649, condo)
    place(652, 655, year_built)
    place(656, 662, living_space)

    return "".join(line)


# ── SR1A Parser Tests ─────────────────────────────────────────────────────────


class SR1ALineParserTests(unittest.TestCase):
    def test_parse_valid_line(self) -> None:
        line = _build_sr1a_line()
        record = parse_sr1a_line(line)
        self.assertIsNotNone(record)
        self.assertEqual(record.county_code, "13")
        self.assertEqual(record.district_code, "07")
        self.assertEqual(record.un_type, "U")
        self.assertEqual(record.verified_sales_price, 750000)
        self.assertEqual(record.property_location, "304 14TH AVE")
        self.assertEqual(record.deed_date, "031526")
        self.assertEqual(record.block, "00123")
        self.assertEqual(record.lot, "00045")
        self.assertEqual(record.property_class, "2")
        self.assertEqual(record.year_built, 1940)
        self.assertEqual(record.living_space, 1298)

    def test_short_line_returns_none(self) -> None:
        self.assertIsNone(parse_sr1a_line("too short"))

    def test_deed_date_parsing(self) -> None:
        self.assertEqual(_parse_deed_date("031526"), "2026-03-15")
        self.assertEqual(_parse_deed_date("120195"), "1995-12-01")
        self.assertIsNone(_parse_deed_date(""))
        self.assertIsNone(_parse_deed_date("abc"))

    def test_usable_sale_flag(self) -> None:
        usable = SR1ARawRecord(
            county_code="13", district_code="07", un_type="U", nu_code="",
            reported_sales_price=500000, verified_sales_price=500000,
            assessed_land=0, assessed_bldg=0, assessed_total=0,
            property_location="", deed_date="", block="", block_suffix="",
            lot="", lot_suffix="", qualification_code="", property_class="2",
            condo_flag="N", year_built=None, living_space=None,
            serial_number="", deed_book="", deed_page="",
            grantor_name="", grantee_name="",
        )
        self.assertTrue(_is_usable_sale(usable))
        usable.un_type = "N"
        self.assertFalse(_is_usable_sale(usable))

    def test_residential_filter(self) -> None:
        record = SR1ARawRecord(
            county_code="13", district_code="07", un_type="U", nu_code="",
            reported_sales_price=500000, verified_sales_price=500000,
            assessed_land=0, assessed_bldg=0, assessed_total=0,
            property_location="", deed_date="", block="", block_suffix="",
            lot="", lot_suffix="", qualification_code="", property_class=" 2",
            condo_flag="N", year_built=None, living_space=None,
            serial_number="", deed_book="", deed_page="",
            grantor_name="", grantee_name="",
        )
        self.assertTrue(_is_residential(record))
        record.property_class = "4A"
        self.assertFalse(_is_residential(record))
        record.property_class = "4C"
        self.assertTrue(_is_residential(record))

    def test_block_lot_formatting(self) -> None:
        record = SR1ARawRecord(
            county_code="13", district_code="07", un_type="U", nu_code="",
            reported_sales_price=0, verified_sales_price=0,
            assessed_land=0, assessed_bldg=0, assessed_total=0,
            property_location="", deed_date="", block="00123", block_suffix="",
            lot="00045", lot_suffix="A", qualification_code="", property_class="2",
            condo_flag="N", year_built=None, living_space=None,
            serial_number="", deed_book="", deed_page="",
            grantor_name="", grantee_name="",
        )
        self.assertEqual(_full_block_lot(record), "00123/00045.A")


class SR1AFileParserTests(unittest.TestCase):
    def _write_fixture(self, lines: list[str]) -> Path:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="latin-1")
        for line in lines:
            tmp.write(line + "\n")
        tmp.close()
        return Path(tmp.name)

    def test_parse_file_with_mixed_records(self) -> None:
        lines = [
            # Usable residential sale in Belmar (district 07)
            _build_sr1a_line(
                district="07", un_type="U", property_class=" 2",
                reported_price=850000, verified_price=850000,
                property_location="527 8TH AVE",
                deed_date="011526", year_built="1955", living_space="0001800",
            ),
            # Non-usable sale (should be filtered)
            _build_sr1a_line(
                district="07", un_type="N", nu_code="01 ",
                reported_price=100, verified_price=100,
                property_location="TRANSFER ONLY",
            ),
            # Commercial property (should be filtered)
            _build_sr1a_line(
                district="07", un_type="U", property_class="4A",
                reported_price=2000000, verified_price=2000000,
                property_location="100 MAIN ST",
            ),
            # Different county (should be filtered)
            _build_sr1a_line(
                county="01", district="07", un_type="U", property_class=" 2",
                reported_price=600000, verified_price=600000,
            ),
            # Usable residential in Bradley Beach (district 08)
            _build_sr1a_line(
                district="08", un_type="U", property_class=" 2",
                reported_price=650000, verified_price=650000,
                property_location="802 CENTRAL AVE",
                deed_date="021026", year_built="1970", living_space="0001200",
            ),
            # Sale with low price (below $10K minimum)
            _build_sr1a_line(
                district="07", un_type="U", property_class=" 2",
                reported_price=100, verified_price=100,
                property_location="1 GIFT TRANSFER",
                deed_date="030126",
            ),
            # Usable apartment building
            _build_sr1a_line(
                district="07", un_type="U", property_class="4C",
                reported_price=1200000, verified_price=1200000,
                property_location="200 MAIN ST",
                deed_date="030526", year_built="1960", living_space="0004000",
            ),
            # Usable condo
            _build_sr1a_line(
                district="07", un_type="U", property_class=" 2",
                condo="Y",
                reported_price=350000, verified_price=350000,
                property_location="100 OCEAN AVE #5",
                deed_date="030826", year_built="1985", living_space="0000950",
            ),
            # Missing deed date (should be filtered)
            _build_sr1a_line(
                district="07", un_type="U", property_class=" 2",
                reported_price=500000, verified_price=500000,
                property_location="99 NO DATE ST",
                deed_date="      ",
            ),
            # Zero price (should be filtered)
            _build_sr1a_line(
                district="07", un_type="U", property_class=" 2",
                reported_price=0, verified_price=0,
                property_location="0 ZERO ST",
                deed_date="030126",
            ),
        ]
        path = self._write_fixture(lines)
        try:
            result = parse_sr1a_file(path, county_code="13")
            # Should parse: 527 8th Ave, 802 Central Ave, 200 Main St, 100 Ocean Ave #5 = 4
            self.assertEqual(result.parsed, 4)
            self.assertEqual(result.skipped_non_usable, 1)
            self.assertEqual(result.skipped_non_residential, 1)
            self.assertGreaterEqual(result.skipped_county, 1)
            self.assertEqual(result.skipped_low_price, 1)
            self.assertEqual(result.skipped_no_price, 1)
            self.assertEqual(result.skipped_no_date, 1)

            # Check first parsed sale
            sale = result.sales[0]
            self.assertEqual(sale.town, "Belmar")
            self.assertEqual(sale.state, "NJ")
            self.assertEqual(sale.sale_price, 850000.0)
            self.assertEqual(sale.sale_date, "2026-01-15")
            self.assertEqual(sale.sale_verification_status, "public_record_verified")
            self.assertEqual(sale.verification_source_type, "public_record")
            self.assertEqual(sale.year_built, 1955)
            self.assertEqual(sale.sqft, 1800)
            self.assertEqual(sale.property_type, "single_family")

            # Check Bradley Beach sale
            bradley = result.sales[1]
            self.assertEqual(bradley.town, "Bradley Beach")

            # Check apartment
            apt = result.sales[2]
            self.assertEqual(apt.property_type, "apartment")
            self.assertEqual(apt.sale_price, 1200000.0)

            # Check condo
            condo = result.sales[3]
            self.assertEqual(condo.property_type, "condo")
        finally:
            path.unlink(missing_ok=True)

    def test_target_districts_filter(self) -> None:
        lines = [
            _build_sr1a_line(district="07", property_location="BELMAR SALE"),
            _build_sr1a_line(district="08", property_location="BRADLEY SALE"),
        ]
        path = self._write_fixture(lines)
        try:
            result = parse_sr1a_file(path, county_code="13", target_districts=["07"])
            self.assertEqual(result.parsed, 1)
            self.assertEqual(result.sales[0].town, "Belmar")
        finally:
            path.unlink(missing_ok=True)

    def test_verification_status_is_public_record(self) -> None:
        lines = [_build_sr1a_line()]
        path = self._write_fixture(lines)
        try:
            result = parse_sr1a_file(path)
            self.assertEqual(result.parsed, 1)
            sale = result.sales[0]
            self.assertEqual(sale.sale_verification_status, "public_record_verified")
            self.assertEqual(sale.verification_status, "public_record")
            self.assertEqual(sale.source_name, "NJ SR1A")
        finally:
            path.unlink(missing_ok=True)

    def test_nonexistent_file_returns_empty(self) -> None:
        result = parse_sr1a_file("/nonexistent/file.txt")
        self.assertEqual(result.parsed, 0)


class DistrictCodeMappingTests(unittest.TestCase):
    def test_belmar_is_07(self) -> None:
        self.assertEqual(MONMOUTH_DISTRICT_CODES["07"], "Belmar")

    def test_bradley_beach_is_08(self) -> None:
        self.assertEqual(MONMOUTH_DISTRICT_CODES["08"], "Bradley Beach")

    def test_all_53_districts(self) -> None:
        self.assertEqual(len(MONMOUTH_DISTRICT_CODES), 53)


# ── MOD-IV Enricher Tests ────────────────────────────────────────────────────


class MODIVEnricherTests(unittest.TestCase):
    def _write_modiv_csv(self, rows: list[dict]) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8", newline=""
        )
        import csv
        writer = csv.DictWriter(tmp, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        tmp.close()
        return Path(tmp.name)

    def test_load_and_lookup(self) -> None:
        csv_path = self._write_modiv_csv([
            {
                "district_code": "07",
                "block": "123",
                "lot": "45",
                "qualifier": "",
                "property_class": "2",
                "year_built": "1940",
                "calc_acre": "0.09",
                "assessed_land": "200000",
                "assessed_improvement": "300000",
                "latitude": "40.1745",
                "longitude": "-74.0192",
                "land_description": "50X100",
            },
        ])
        try:
            enricher = MODIVEnricher()
            count = enricher.load_csv(csv_path)
            self.assertEqual(count, 1)

            record = enricher.lookup("07", "123", "45")
            self.assertIsNotNone(record)
            self.assertEqual(record.year_built, 1940)
            self.assertAlmostEqual(record.calc_acre, 0.09)
            self.assertAlmostEqual(record.latitude, 40.1745)
        finally:
            csv_path.unlink(missing_ok=True)

    def test_lookup_miss(self) -> None:
        enricher = MODIVEnricher()
        self.assertIsNone(enricher.lookup("07", "999", "999"))

    def test_invalid_year_built_rejected(self) -> None:
        csv_path = self._write_modiv_csv([
            {
                "district_code": "07", "block": "1", "lot": "1", "qualifier": "",
                "property_class": "2", "year_built": "1600", "calc_acre": "0.1",
                "assessed_land": "", "assessed_improvement": "",
                "latitude": "", "longitude": "", "land_description": "",
            },
        ])
        try:
            enricher = MODIVEnricher()
            enricher.load_csv(csv_path)
            record = enricher.lookup("07", "1", "1")
            self.assertIsNotNone(record)
            self.assertIsNone(record.year_built)  # rejected as too old
        finally:
            csv_path.unlink(missing_ok=True)

    def test_zero_acreage_treated_as_none(self) -> None:
        csv_path = self._write_modiv_csv([
            {
                "district_code": "07", "block": "2", "lot": "2", "qualifier": "",
                "property_class": "2", "year_built": "1960", "calc_acre": "0",
                "assessed_land": "", "assessed_improvement": "",
                "latitude": "", "longitude": "", "land_description": "",
            },
        ])
        try:
            enricher = MODIVEnricher()
            enricher.load_csv(csv_path)
            record = enricher.lookup("07", "2", "2")
            self.assertIsNone(record.calc_acre)
        finally:
            csv_path.unlink(missing_ok=True)

    def test_enrich_sales(self) -> None:
        from briarwood.agents.comparable_sales.schemas import ComparableSale

        csv_path = self._write_modiv_csv([
            {
                "district_code": "07", "block": "123", "lot": "45", "qualifier": "",
                "property_class": "2", "year_built": "1940", "calc_acre": "0.09",
                "assessed_land": "200000", "assessed_improvement": "300000",
                "latitude": "40.1745", "longitude": "-74.0192",
                "land_description": "50X100",
            },
        ])
        try:
            enricher = MODIVEnricher()
            enricher.load_csv(csv_path)

            sale = ComparableSale(
                address="304 14TH AVE", town="Belmar", state="NJ",
                sale_price=750000, sale_date="2026-03-15",
                source_notes="Block/Lot 123/45; assessed total $500,000",
            )
            result = enricher.enrich_sales([sale])
            self.assertEqual(result.lookups_matched, 1)
            self.assertEqual(sale.year_built, 1940)
            self.assertAlmostEqual(sale.lot_size, 0.09)
            self.assertAlmostEqual(sale.latitude, 40.1745)
        finally:
            csv_path.unlink(missing_ok=True)


class MODIVGeoJSONTests(unittest.TestCase):
    def test_load_geojson(self) -> None:
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-74.0192, 40.1745]},
                    "properties": {
                        "DIST_CODE": "07",
                        "BLOCK": "123",
                        "LOT": "45",
                        "QUALIFIER": "",
                        "PROPERTY_CLASS": "2",
                        "YEAR_BUILT": "1940",
                        "CALC_ACRE": "0.09",
                        "ASSESSED_LAND": "200000",
                        "ASSESSED_IMPROV": "300000",
                        "LAND_DESC": "50X100",
                    },
                },
            ],
        }
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".geojson", delete=False, encoding="utf-8"
        )
        json.dump(geojson, tmp)
        tmp.close()
        path = Path(tmp.name)
        try:
            enricher = MODIVEnricher()
            count = enricher.load_geojson(path)
            self.assertEqual(count, 1)
            record = enricher.lookup("07", "123", "45")
            self.assertIsNotNone(record)
            self.assertAlmostEqual(record.latitude, 40.1745)
            self.assertAlmostEqual(record.longitude, -74.0192)
            self.assertEqual(record.year_built, 1940)
        finally:
            path.unlink(missing_ok=True)


# ── Bulk Ingest Orchestrator Tests ───────────────────────────────────────────


class BulkIngestTests(unittest.TestCase):
    def _write_sr1a_fixture(self, lines: list[str]) -> Path:
        tmp_dir = Path(tempfile.mkdtemp())
        sr1a_file = tmp_dir / "test_sr1a.txt"
        sr1a_file.write_text("\n".join(lines) + "\n", encoding="latin-1")
        return tmp_dir

    def test_full_pipeline_creates_new_records(self) -> None:
        lines = [
            _build_sr1a_line(
                district="07", property_location="100 MAIN ST",
                reported_price=600000, verified_price=600000,
                deed_date="020126", year_built="1950", living_space="0001500",
                block="00010", lot="00001",
            ),
            _build_sr1a_line(
                district="07", property_location="200 OCEAN AVE",
                reported_price=800000, verified_price=800000,
                deed_date="030126", year_built="1965", living_space="0002000",
                block="00020", lot="00002",
            ),
        ]
        sr1a_dir = self._write_sr1a_fixture(lines)
        comps_path = sr1a_dir / "test_comps.json"

        try:
            result = run_bulk_ingest(
                sr1a_dir=sr1a_dir,
                comps_path=comps_path,
            )
            self.assertEqual(result.sr1a_files_processed, 1)
            self.assertEqual(result.sr1a_total_parsed, 2)
            self.assertEqual(result.new_records_added, 2)

            # Verify records in store
            store = JsonComparableSalesStore(comps_path)
            dataset = store.load()
            self.assertEqual(len(dataset.sales), 2)
            self.assertEqual(dataset.sales[0].sale_price, 600000.0)
            self.assertEqual(dataset.sales[0].town, "Belmar")
        finally:
            import shutil
            shutil.rmtree(sr1a_dir, ignore_errors=True)

    def test_deduplication_on_second_run(self) -> None:
        lines = [
            _build_sr1a_line(
                district="07", property_location="100 MAIN ST",
                reported_price=600000, verified_price=600000,
                deed_date="020126", block="00010", lot="00001",
            ),
        ]
        sr1a_dir = self._write_sr1a_fixture(lines)
        comps_path = sr1a_dir / "test_comps.json"

        try:
            # First run
            result1 = run_bulk_ingest(sr1a_dir=sr1a_dir, comps_path=comps_path)
            self.assertEqual(result1.new_records_added, 1)

            # Second run with same data — should update, not duplicate
            result2 = run_bulk_ingest(sr1a_dir=sr1a_dir, comps_path=comps_path)
            self.assertEqual(result2.existing_records_updated, 1)
            self.assertEqual(result2.new_records_added, 0)

            store = JsonComparableSalesStore(comps_path)
            dataset = store.load()
            self.assertEqual(len(dataset.sales), 1)  # no duplicates
        finally:
            import shutil
            shutil.rmtree(sr1a_dir, ignore_errors=True)


# ── SR1A Verification + MOD-IV Enrichment on Existing Store (Part D) ─────────


class SR1AVerificationTests(unittest.TestCase):
    """Test merge_sr1a_verification wiring into existing comp dicts."""

    def test_sr1a_upgrades_verification_status(self) -> None:
        from briarwood.agents.comparable_sales.ingest_public_records import merge_sr1a_verification
        from briarwood.agents.comparable_sales.schemas import ComparableSale

        comp_dataset: dict = {
            "metadata": {},
            "sales": [
                {
                    "address": "100 Main St",
                    "town": "Belmar",
                    "state": "NJ",
                    "sale_price": 600000,
                    "sale_date": "2026-01-02",
                    "sale_verification_status": "seeded",
                },
            ],
        }
        sr1a_sales = [
            ComparableSale(
                address="100 MAIN ST", town="Belmar", state="NJ",
                sale_price=600000, sale_date="2026-01-02",
                source_ref="SR1A-1307-10-1",
            ),
        ]
        counts = merge_sr1a_verification(
            comp_dataset=comp_dataset,
            sr1a_sales=sr1a_sales,
            as_of="2026-04-10",
        )
        self.assertEqual(counts["matched"], 1)
        self.assertEqual(counts["upgraded"], 1)
        self.assertEqual(comp_dataset["sales"][0]["sale_verification_status"], "public_record_verified")
        self.assertEqual(comp_dataset["sales"][0]["verification_source_type"], "sr1a_state_record")

    def test_already_verified_not_double_counted(self) -> None:
        from briarwood.agents.comparable_sales.ingest_public_records import merge_sr1a_verification
        from briarwood.agents.comparable_sales.schemas import ComparableSale

        comp_dataset: dict = {
            "metadata": {},
            "sales": [
                {
                    "address": "100 Main St",
                    "town": "Belmar",
                    "state": "NJ",
                    "sale_price": 600000,
                    "sale_date": "2026-01-02",
                    "sale_verification_status": "public_record_verified",
                },
            ],
        }
        sr1a_sales = [
            ComparableSale(
                address="100 MAIN ST", town="Belmar", state="NJ",
                sale_price=600000, sale_date="2026-01-02",
                source_ref="SR1A-1307-10-1",
            ),
        ]
        counts = merge_sr1a_verification(
            comp_dataset=comp_dataset,
            sr1a_sales=sr1a_sales,
            as_of="2026-04-10",
        )
        self.assertEqual(counts["matched"], 1)
        self.assertEqual(counts["already_verified"], 1)
        self.assertEqual(counts["upgraded"], 0)

    def test_no_match_when_price_differs(self) -> None:
        from briarwood.agents.comparable_sales.ingest_public_records import merge_sr1a_verification
        from briarwood.agents.comparable_sales.schemas import ComparableSale

        comp_dataset: dict = {
            "metadata": {},
            "sales": [
                {
                    "address": "100 Main St",
                    "town": "Belmar",
                    "state": "NJ",
                    "sale_price": 600000,
                    "sale_date": "2026-01-02",
                    "sale_verification_status": "seeded",
                },
            ],
        }
        sr1a_sales = [
            ComparableSale(
                address="100 MAIN ST", town="Belmar", state="NJ",
                sale_price=200000,  # very different price
                sale_date="2025-06-15",  # very different date
                source_ref="SR1A-1307-10-1",
            ),
        ]
        counts = merge_sr1a_verification(
            comp_dataset=comp_dataset,
            sr1a_sales=sr1a_sales,
            as_of="2026-04-10",
        )
        self.assertEqual(counts["matched"], 0)


class MODIVStoreEnrichmentTests(unittest.TestCase):
    """Test apply_modiv_enrichment on raw comp dicts."""

    def _write_modiv_csv(self, rows: list[dict]) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8", newline=""
        )
        import csv as _csv
        writer = _csv.DictWriter(tmp, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        tmp.close()
        return Path(tmp.name)

    def test_enriches_year_built_and_latlon(self) -> None:
        from briarwood.agents.comparable_sales.ingest_public_records import apply_modiv_enrichment

        csv_path = self._write_modiv_csv([
            {
                "district_code": "07", "block": "10", "lot": "1", "qualifier": "",
                "property_class": "2", "year_built": "1950", "calc_acre": "0.12",
                "assessed_land": "200000", "assessed_improvement": "300000",
                "latitude": "40.1780", "longitude": "-74.0200",
                "land_description": "50X100",
            },
        ])
        try:
            enricher = MODIVEnricher()
            enricher.load_csv(csv_path)

            comp_dataset: dict = {
                "metadata": {},
                "sales": [
                    {
                        "address": "100 Main St",
                        "town": "Belmar",
                        "state": "NJ",
                        "sale_price": 600000,
                        "sale_date": "2026-01-02",
                        "source_notes": "Block/Lot 10/1; District 07",
                    },
                ],
            }
            counts = apply_modiv_enrichment(
                comp_dataset=comp_dataset,
                enricher=enricher,
            )
            self.assertEqual(counts["matched"], 1)
            self.assertEqual(comp_dataset["sales"][0]["year_built"], 1950)
            self.assertAlmostEqual(comp_dataset["sales"][0]["lot_size"], 0.12)
            self.assertAlmostEqual(comp_dataset["sales"][0]["latitude"], 40.1780)
        finally:
            csv_path.unlink(missing_ok=True)

    def test_does_not_overwrite_existing_values(self) -> None:
        from briarwood.agents.comparable_sales.ingest_public_records import apply_modiv_enrichment

        csv_path = self._write_modiv_csv([
            {
                "district_code": "07", "block": "10", "lot": "1", "qualifier": "",
                "property_class": "2", "year_built": "1950", "calc_acre": "0.12",
                "assessed_land": "200000", "assessed_improvement": "300000",
                "latitude": "40.1780", "longitude": "-74.0200",
                "land_description": "50X100",
            },
        ])
        try:
            enricher = MODIVEnricher()
            enricher.load_csv(csv_path)

            comp_dataset: dict = {
                "metadata": {},
                "sales": [
                    {
                        "address": "100 Main St",
                        "town": "Belmar",
                        "state": "NJ",
                        "sale_price": 600000,
                        "year_built": 1940,  # already set
                        "lot_size": 0.10,    # already set
                        "latitude": 40.1700, # already set
                        "source_notes": "Block/Lot 10/1; District 07",
                    },
                ],
            }
            counts = apply_modiv_enrichment(
                comp_dataset=comp_dataset,
                enricher=enricher,
            )
            self.assertEqual(counts["matched"], 1)
            # Existing values should be preserved
            self.assertEqual(comp_dataset["sales"][0]["year_built"], 1940)
            self.assertAlmostEqual(comp_dataset["sales"][0]["lot_size"], 0.10)
            self.assertAlmostEqual(comp_dataset["sales"][0]["latitude"], 40.1700)
            self.assertEqual(counts["year_built"], 0)
            self.assertEqual(counts["acreage"], 0)
            self.assertEqual(counts["latlon"], 0)
        finally:
            csv_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
