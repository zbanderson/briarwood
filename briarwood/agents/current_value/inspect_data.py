import csv
import re

input_file = "Monmouth25re.txt"
output_file = "monmouth_parsed.csv"

target_towns = {
    "BELMAR",
    "MANASQUAN",
    "SPRING LAKE",
    "SEA GIRT",
    "AVON-BY-THE-SEA",
    "ASBURY PARK",
    "BRADLEY BEACH",
}

def normalize_spaces(text):
    return " ".join(text.split())

def extract_town(line):
    match = re.search(r'([A-Z\s\-]+),\s*NJ', line.upper())
    if match:
        return normalize_spaces(match.group(1))
    return None

def extract_zip(line):
    match = re.search(r',\s*NJ\s*(\d{5})', line.upper())
    if match:
        return match.group(1).zfill(5)
    return None

def extract_year_built(line):
    years = re.findall(r'\b(18\d{2}|19\d{2}|20\d{2})\b', line)
    if not years:
        return None
    plausible = [y for y in years if 1850 <= int(y) <= 2026]
    return plausible[-1] if plausible else None

def extract_assessed_values(line):
    nums = re.findall(r'\b\d{4,8}\b', line)
    vals = [int(x) for x in nums if 1000 <= int(x) <= 20000000]

    if len(vals) < 3:
        return None, None, None

    for i in range(len(vals) - 2):
        a, b, c = vals[i], vals[i + 1], vals[i + 2]
        if a + b == c:
            return a, b, c

    return None, None, None

def extract_address(line, town):
    clean = normalize_spaces(line.upper())

    if not town:
        return None

    town_marker = f"{town}, NJ"
    if town_marker not in clean:
        return None

    before_town = clean.split(town_marker)[0]

    matches = re.findall(
        r'(\d+\s+[A-Z0-9#,\- ]+\b(?:AVE|AVENUE|ST|STREET|DR|DRIVE|RD|ROAD|PL|PLACE|BLVD|WAY|CT|LN|TER))',
        before_town
    )

    if matches:
        return normalize_spaces(matches[-1])

    return None

rows = []

with open(input_file, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        town = extract_town(line)
        if not town or town not in target_towns:
            continue

        clean_line = normalize_spaces(line)
        zip_code = extract_zip(clean_line)
        year_built = extract_year_built(clean_line)
        land_val, improvement_val, total_val = extract_assessed_values(clean_line)
        address = extract_address(clean_line, town)

        rows.append({
            "town": town,
            "zip": zip_code,
            "address_guess": address,
            "year_built": year_built,
            "land_assessed": land_val,
            "improvement_assessed": improvement_val,
            "total_assessed": total_val,
            "raw": clean_line,
        })

with open(output_file, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "town",
            "zip",
            "address_guess",
            "year_built",
            "land_assessed",
            "improvement_assessed",
            "total_assessed",
            "raw",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)

print(f"Saved {len(rows)} parsed rows to {output_file}")