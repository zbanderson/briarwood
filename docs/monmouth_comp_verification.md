# Monmouth Comp Verification

## Purpose

This workflow lets Briarwood move the comp database from:

- seeded local comp review

to:

- county/public-record matched sale rows
- eventually MLS-verified comps

The goal is to improve trust before MLS integration is ready.

---

## What We Need

For each Monmouth sale row, Briarwood only needs a few fields:

- `property_address`
- `municipality`
- `state`
- `sale_price`
- `sale_date`
- `instrument_number`

Those fields are enough to:

- match a seed comp to a real sale record
- distinguish `seeded` from `public_record_matched`
- promote high-confidence rows to `public_record_verified`

---

## Input File

Use:

- [monmouth_public_record_template.csv](/Users/zachanderson/projects/briarwood/data/comps/monmouth_public_record_template.csv)

That file is only a shape/template. It is not real county data.

Place the actual county export somewhere like:

- `data/comps/monmouth_public_records_2026_03_29.csv`

---

## Merge Command

Run:

```bash
./venv/bin/python -m briarwood.agents.comparable_sales.ingest_public_records \
  --input-csv data/comps/monmouth_public_records_2026_03_29.csv \
  --comps data/comps/sales_comps.json \
  --output data/comps/sales_comps.json \
  --as-of 2026-03-29 \
  --source-name "Monmouth County public record"
```

This will:

- match county rows to existing Briarwood comps by town + normalized address
- compare sale date and sale price
- mark matched rows as:
  - `public_record_verified`
  - or `public_record_matched`
- leave unmatched rows as:
  - `seeded`

---

## Verification Tiers

Current Briarwood tiers:

- `seeded`
  - internal local comp seed only
- `public_record_matched`
  - address match plus partial sale-record alignment
- `public_record_verified`
  - address plus strong sale-date and sale-price match
- `mls_verified`
  - future highest-confidence tier once MLS is connected

Important:

- `address_verification_status` is not the same as sale verification
- a comp can have a known address but still lack a verified sale record

---

## Current Product Standard

Until MLS is connected:

- public-record verification is the strongest comp evidence tier
- seeded comps should still influence the model less
- the tear sheet should say when the comp set is still mostly seed/review only

---

## Recommended First Pass

Start with Belmar only:

- `1223 Briarwood Rd`
- current Belmar comp rows in [sales_comps.json](/Users/zachanderson/projects/briarwood/data/comps/sales_comps.json)

The immediate goal is simple:

1. verify that the active Belmar sale comps are real
2. promote them to public-record tiers where justified
3. leave questioned rows excluded

That gives Briarwood a real trust upgrade without waiting for a full MLS pipeline.
