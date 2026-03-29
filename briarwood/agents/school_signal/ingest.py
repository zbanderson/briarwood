from __future__ import annotations

import argparse
import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile


SOURCE_NAME = "briarwood_school_signal_nj_spr_v1"
WORKBOOK_SHEETS = {
    "accountability": "AccountabilityIndScoresSummativ",
    "readiness": "PSAT-SAT-ACTPerformance",
    "graduation": "FederalGraduationRates",
    "absenteeism": "ChronicAbsenteeism",
    "staffing": "StudentToStaffRatios",
}
XML_NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

FIELD_ALIASES = {
    "achievement_index": [
        "achievement_index",
        "academic_achievement_index",
        "performance_index",
        "proficiency_index",
    ],
    "growth_index": [
        "growth_index",
        "student_growth_index",
        "academic_growth_index",
        "progress_index",
    ],
    "readiness_index": [
        "readiness_index",
        "college_readiness_index",
        "college_career_readiness_index",
        "postsecondary_readiness_index",
    ],
    "chronic_absenteeism_pct": [
        "chronic_absenteeism_pct",
        "chronic_absenteeism",
        "chronic_absence_pct",
    ],
    "student_teacher_ratio": [
        "student_teacher_ratio",
        "student_teacher_ratio_total",
        "pupil_teacher_ratio",
    ],
}

COUNTY_ALIASES = ["county", "county_name", "CountyName"]
STATE_ALIASES = ["state", "state_abbr"]
DISTRICT_ALIASES = ["district_name", "DistrictName", "lea_name", "district"]
SCHOOL_ALIASES = ["school_name", "SchoolName", "school"]


@dataclass(slots=True)
class TownSchoolTarget:
    name: str
    state: str
    county: str
    district_tokens: list[str]
    school_tokens: list[str]
    exclude_tokens: list[str] | None = None
    min_match_count: int = 1


def build_school_signal_dataset(
    *,
    rows: list[dict[str, str]],
    targets: list[TownSchoolTarget],
    as_of: str,
    refresh_frequency_days: int = 365,
) -> dict[str, object]:
    towns: list[dict[str, object]] = []
    for target in targets:
        matched = [row for row in rows if _row_matches_target(row, target)]
        if not matched:
            continue
        aggregate = _aggregate_rows(matched)
        aggregate.update(
            {
                "name": target.name,
                "state": target.state,
                "county": target.county,
                "district_coverage": min(1.0, len(matched) / max(target.min_match_count, 1)),
                "source_review_quality": 0.72 if len(matched) >= target.min_match_count else 0.60,
                "as_of": as_of,
                "refresh_frequency_days": refresh_frequency_days,
            }
        )
        towns.append(aggregate)

    return {
        "source_name": SOURCE_NAME,
        "source_scope": f"{targets[0].county} County, {targets[0].state} targeted coverage" if targets else "targeted coverage",
        "methodology_note": (
            "Built from a targeted NJ School Performance Reports export using only the configured county/town mappings. "
            "This is a Briarwood proxy, not an official ranking."
        ),
        "source_urls": [
            "https://www.nj.gov/education/spr/",
            "https://www.nj.gov/education/spr/download/",
        ],
        "towns": towns,
    }


def build_school_signal_dataset_from_workbook_rows(
    *,
    sheet_rows: dict[str, list[dict[str, str]]],
    targets: list[TownSchoolTarget],
    as_of: str,
    refresh_frequency_days: int = 365,
) -> dict[str, object]:
    towns: list[dict[str, object]] = []
    for target in targets:
        accountability_rows = _filter_rows(sheet_rows.get(WORKBOOK_SHEETS["accountability"], []), target)
        absenteeism_rows = _filter_rows(sheet_rows.get(WORKBOOK_SHEETS["absenteeism"], []), target)
        staffing_rows = _filter_rows(sheet_rows.get(WORKBOOK_SHEETS["staffing"], []), target)
        readiness_rows = _filter_rows(sheet_rows.get(WORKBOOK_SHEETS["readiness"], []), target)
        graduation_rows = _filter_rows(sheet_rows.get(WORKBOOK_SHEETS["graduation"], []), target)

        aggregate = _aggregate_workbook_rows(
            accountability_rows=accountability_rows,
            absenteeism_rows=absenteeism_rows,
            staffing_rows=staffing_rows,
            readiness_rows=readiness_rows,
            graduation_rows=graduation_rows,
        )
        if not any(aggregate[key] is not None for key in aggregate):
            continue

        matched_school_count = len(
            {
                row.get("SchoolName", "").strip()
                for bucket in (accountability_rows, absenteeism_rows, staffing_rows, readiness_rows, graduation_rows)
                for row in bucket
                if row.get("SchoolName")
            }
        )
        completeness = _metric_completeness(aggregate)
        aggregate.update(
            {
                "name": target.name,
                "state": target.state,
                "county": target.county,
                "district_coverage": round(min(1.0, matched_school_count / max(target.min_match_count, 1)), 2),
                "source_review_quality": round(min(0.9, 0.72 + completeness * 0.18), 2),
                "as_of": as_of,
                "refresh_frequency_days": refresh_frequency_days,
            }
        )
        towns.append(aggregate)

    return {
        "source_name": SOURCE_NAME,
        "source_scope": f"{targets[0].county} County, {targets[0].state} targeted official NJ SPR coverage" if targets else "targeted official NJ SPR coverage",
        "methodology_note": (
            "Built from targeted rows in the NJ School Performance Reports workbook using configured Monmouth town and school mappings. "
            "This is a Briarwood proxy derived from official public data, not an official ranking."
        ),
        "source_urls": [
            "https://www.nj.gov/education/spr/",
            "https://www.nj.gov/education/spr/download/",
        ],
        "towns": towns,
    }


def load_targets(path: str | Path) -> list[TownSchoolTarget]:
    payload = json.loads(Path(path).read_text())
    targets: list[TownSchoolTarget] = []
    for item in payload.get("towns", []):
        targets.append(
            TownSchoolTarget(
                name=item["name"],
                state=item["state"],
                county=item["county"],
                district_tokens=item.get("district_tokens", []),
                school_tokens=item.get("school_tokens", []),
                exclude_tokens=item.get("exclude_tokens"),
                min_match_count=item.get("min_match_count", 1),
            )
        )
    return targets


def load_csv_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def load_workbook_rows(path: str | Path, sheet_names: list[str] | None = None) -> dict[str, list[dict[str, str]]]:
    workbook = _open_workbook_zip(path)
    with workbook as zf:
        shared_strings = _load_shared_strings(zf)
        sheet_paths = _load_sheet_paths(zf)
        names = sheet_names or list(sheet_paths)
        return {
            name: _read_sheet_rows(zf, sheet_paths[name], shared_strings)
            for name in names
            if name in sheet_paths
        }


def write_dataset(payload: dict[str, object], output_path: str | Path) -> None:
    Path(output_path).write_text(json.dumps(payload, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a targeted Monmouth/NJ Briarwood school signal dataset.")
    parser.add_argument(
        "--input-file",
        "--input-csv",
        dest="input_file",
        required=True,
        help="Path to a downloaded NJ SPR CSV, XLSX, or official ZIP export.",
    )
    parser.add_argument(
        "--targets",
        default="data/town_county/monmouth_school_targets.json",
        help="Path to the targeted town/district mapping config.",
    )
    parser.add_argument(
        "--output",
        default="data/town_county/monmouth_school_signal.json",
        help="Output JSON path.",
    )
    parser.add_argument("--as-of", required=True, help="Review date for the generated dataset, in YYYY-MM-DD format.")
    parser.add_argument("--refresh-frequency-days", type=int, default=365)
    args = parser.parse_args()

    targets = load_targets(args.targets)
    input_path = Path(args.input_file)
    if input_path.suffix.lower() == ".csv":
        rows = load_csv_rows(input_path)
        payload = build_school_signal_dataset(
            rows=rows,
            targets=targets,
            as_of=args.as_of,
            refresh_frequency_days=args.refresh_frequency_days,
        )
    else:
        payload = build_school_signal_dataset_from_workbook_rows(
            sheet_rows=load_workbook_rows(input_path, list(WORKBOOK_SHEETS.values())),
            targets=targets,
            as_of=args.as_of,
            refresh_frequency_days=args.refresh_frequency_days,
        )
    write_dataset(payload, args.output)
    print(f"Wrote {len(payload['towns'])} targeted town rows to {args.output}")
    return 0


def _row_matches_target(row: dict[str, str], target: TownSchoolTarget) -> bool:
    row_county = _find_first(row, COUNTY_ALIASES)
    row_state = _find_first(row, STATE_ALIASES)
    if row_county and _normalize(row_county) != _normalize(target.county):
        return False
    if row_state and _normalize(row_state) != _normalize(target.state):
        return False

    district_name = _find_first(row, DISTRICT_ALIASES)
    school_name = _find_first(row, SCHOOL_ALIASES)
    combined = f"{district_name or ''} {school_name or ''}"
    if _token_match(combined, target.exclude_tokens or []):
        return False
    district_matches = _token_match(district_name, target.district_tokens)
    school_matches = _token_match(school_name, target.school_tokens)
    return district_matches or school_matches


def _filter_rows(rows: list[dict[str, str]], target: TownSchoolTarget) -> list[dict[str, str]]:
    return [row for row in rows if _row_matches_target(row, target)]


def _aggregate_workbook_rows(
    *,
    accountability_rows: list[dict[str, str]],
    absenteeism_rows: list[dict[str, str]],
    staffing_rows: list[dict[str, str]],
    readiness_rows: list[dict[str, str]],
    graduation_rows: list[dict[str, str]],
) -> dict[str, float | None]:
    schoolwide_accountability = accountability_rows
    schoolwide_absenteeism = [row for row in absenteeism_rows if _normalize(row.get("StudentGroup", "")) == "schoolwide"]
    schoolwide_graduation = [row for row in graduation_rows if _normalize(row.get("StudentGroup", "")) == "schoolwide"]

    achievement_values = _numeric_values(
        schoolwide_accountability,
        ["IndicatorScore-ELAProficiency", "IndicatorScore-MathProficiency"],
    )
    growth_values = _numeric_values(
        schoolwide_accountability,
        ["IndicatorScore-ELAGrowth", "IndicatorScore-MathGrowth"],
    )
    readiness_values = _readiness_values(readiness_rows, schoolwide_graduation)
    absenteeism_values = _numeric_values(schoolwide_absenteeism, ["Chronic_Abs_Pct"])
    ratio_values = [
        _parse_ratio(row.get("Student_Teacher_School"))
        for row in staffing_rows
        if _parse_ratio(row.get("Student_Teacher_School")) is not None
    ]

    return {
        "achievement_index": _average(achievement_values),
        "growth_index": _average(growth_values),
        "readiness_index": _average(readiness_values),
        "chronic_absenteeism_pct": _average(absenteeism_values),
        "student_teacher_ratio": _average(ratio_values),
    }


def _aggregate_rows(rows: list[dict[str, str]]) -> dict[str, float | None]:
    return {
        "achievement_index": _average(_extract_metric(rows, "achievement_index")),
        "growth_index": _average(_extract_metric(rows, "growth_index")),
        "readiness_index": _average(_extract_metric(rows, "readiness_index")),
        "chronic_absenteeism_pct": _average(_extract_metric(rows, "chronic_absenteeism_pct")),
        "student_teacher_ratio": _average(_extract_metric(rows, "student_teacher_ratio")),
    }


def _extract_metric(rows: list[dict[str, str]], field_name: str) -> list[float]:
    values: list[float] = []
    aliases = FIELD_ALIASES[field_name]
    for row in rows:
        raw = _find_first(row, aliases)
        if raw is None or raw == "":
            continue
        try:
            values.append(float(str(raw).replace("%", "").replace(",", "").strip()))
        except ValueError:
            continue
    return values


def _find_first(row: dict[str, str], aliases: list[str]) -> str | None:
    lowered = {_normalize(key): value for key, value in row.items()}
    for alias in aliases:
        value = lowered.get(_normalize(alias))
        if value not in (None, ""):
            return value
    return None


def _token_match(value: str | None, tokens: list[str]) -> bool:
    if value is None or not tokens:
        return False
    normalized_value = _normalize(value)
    return any(_normalize(token) in normalized_value for token in tokens)


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _metric_completeness(metrics: dict[str, float | None]) -> float:
    if not metrics:
        return 0.0
    present = sum(1 for value in metrics.values() if value is not None)
    return present / len(metrics)


def _numeric_values(rows: list[dict[str, str]], keys: list[str]) -> list[float]:
    values: list[float] = []
    for row in rows:
        for key in keys:
            parsed = _parse_float(row.get(key))
            if parsed is not None:
                values.append(parsed)
    return values


def _readiness_values(
    readiness_rows: list[dict[str, str]],
    graduation_rows: list[dict[str, str]],
) -> list[float]:
    values: list[float] = []
    for row in readiness_rows:
        test_name = _normalize(row.get("Test", ""))
        if test_name not in {"sat", "act"}:
            continue
        parsed = _parse_float(row.get("BT_PCT"))
        if parsed is not None:
            values.append(parsed)
    values.extend(_numeric_values(graduation_rows, ["2024 4-Year Federal Graduation Rate"]))
    return values


def _parse_float(value: object) -> float | None:
    if value in (None, "", "N", "NA", "N/A", "*", "**"):
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if text.startswith("<"):
        text = text[1:]
        try:
            return round(float(text) / 2.0, 2)
        except ValueError:
            return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_ratio(value: object) -> float | None:
    if value in (None, "", "N", "NA", "N/A", "*", "**"):
        return None
    text = str(value).strip()
    if ":" not in text:
        return _parse_float(text)
    left, _, _right = text.partition(":")
    return _parse_float(left)


def _open_workbook_zip(path: str | Path) -> zipfile.ZipFile:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".xlsx":
        return zipfile.ZipFile(source)
    if suffix == ".zip":
        with zipfile.ZipFile(source) as outer:
            workbook_name = next((name for name in outer.namelist() if name.lower().endswith(".xlsx")), None)
            if workbook_name is None:
                raise ValueError(f"No XLSX workbook found inside {source}")
            workbook_bytes = outer.read(workbook_name)
        return zipfile.ZipFile(io.BytesIO(workbook_bytes))
    raise ValueError(f"Unsupported workbook format: {source.suffix}")


def _load_shared_strings(workbook: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
        for item in root
    ]


def _load_sheet_paths(workbook: zipfile.ZipFile) -> dict[str, str]:
    workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
    rels_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_root}
    sheets = workbook_root.find("a:sheets", XML_NS)
    if sheets is None:
        return {}
    return {
        sheet.attrib["name"]: f"xl/{rel_map[sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]}"
        for sheet in sheets
    }


def _read_sheet_rows(workbook: zipfile.ZipFile, sheet_path: str, shared_strings: list[str]) -> list[dict[str, str]]:
    root = ET.fromstring(workbook.read(sheet_path))
    sheet_data = root.find("a:sheetData", XML_NS)
    if sheet_data is None:
        return []
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    for row in sheet_data:
        values = [_cell_value(cell, shared_strings) for cell in row]
        if header is None:
            header = values
            continue
        if not any(values):
            continue
        rows.append({header[index]: values[index] if index < len(values) else "" for index in range(len(header))})
    return rows


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    inline_string = cell.find("a:is", XML_NS)
    if inline_string is not None:
        return "".join(node.text or "" for node in inline_string.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
    value_node = cell.find("a:v", XML_NS)
    if value_node is None:
        return ""
    value = value_node.text or ""
    if cell.attrib.get("t") == "s":
        return shared_strings[int(value)]
    return value


def _normalize(value: str) -> str:
    return "".join(ch for ch in value.strip().lower() if ch.isalnum())


if __name__ == "__main__":
    raise SystemExit(main())
