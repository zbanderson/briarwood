# Briarwood

Briarwood is a lightweight real estate decision intelligence prototype focused on single-property analysis.

## Chat UI Dev

Start the FastAPI bridge and the Next.js chat UI together with one command:

```bash
make dev
```

That boots:

- `http://127.0.0.1:8000` for the API
- `http://127.0.0.1:3000` for the chat UI

The launcher prefers the repo's `venv` automatically when it exists, prefixes
logs by service, and shuts both processes down together when you press `Ctrl+C`.

## v1 Modules

- Property Snapshot
- Cost / Valuation
- Bull / Base / Bear
- Risk & Constraints
- Town Intelligence

Each module runs independently and returns:

- `metrics`
- `score`
- `confidence`
- `summary`

## Project Shape

- [`app.py`](/Users/zachanderson/projects/briarwood/app.py): command-line entrypoint for ad hoc reports
- [`briarwood/runner.py`](/Users/zachanderson/projects/briarwood/briarwood/runner.py): reusable runner for code-driven report generation
- [`briarwood/schemas.py`](/Users/zachanderson/projects/briarwood/briarwood/schemas.py): shared input and output shapes
- [`briarwood/settings.py`](/Users/zachanderson/projects/briarwood/briarwood/settings.py): underwriting assumptions and thresholds
- [`briarwood/modules/`](/Users/zachanderson/projects/briarwood/briarwood/modules): independent analysis modules
- [`briarwood/listing_intake/`](/Users/zachanderson/projects/briarwood/briarwood/listing_intake): listing normalization layer for Zillow and future sources
- [`briarwood/reports/`](/Users/zachanderson/projects/briarwood/briarwood/reports): tear sheet schemas, section builders, and HTML rendering
- [`data/sample_property.json`](/Users/zachanderson/projects/briarwood/data/sample_property.json): example property input

## Tear Sheet File Structure

```text
briarwood/reports/
├─ schemas.py
├─ tear_sheet.py
├─ renderer.py
├─ assets/
│  └─ tear_sheet.css
├─ templates/
│  └─ tear_sheet.html
└─ sections/
   ├─ header_section.py
   ├─ conclusion_section.py
   ├─ thesis_section.py
   ├─ scenario_chart_section.py
   └─ case_columns_section.py
```

## Listing Intake

`listing_intake` is intentionally separate from valuation and tear-sheet generation.
Its job is to take a listing source and normalize it into Briarwood-friendly property data.

Supported v1 inputs:

- Zillow URL
- pasted Zillow listing text

Two explicit intake modes:

- `url_intake`
  - accepts a Zillow URL
  - stores source URL
  - infers minimal metadata only
  - does not claim to extract full listing fields
- `text_intake`
  - accepts pasted Zillow listing text
  - extracts real listing fields from the text
  - is the primary v1 path

Run it with a sample text file:

```bash
python3 -m briarwood.listing_intake.cli data/sample_zillow_listing.txt
```

Preview intake from the main Briarwood CLI without running valuation:

```bash
python3 app.py \
  --listing-text-file data/sample_zillow_listing_belmar.txt \
  --source-url "https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/?" \
  --preview-intake
```

Include raw extracted fields in the preview:

```bash
python3 app.py \
  --listing-text-file data/sample_zillow_listing_belmar.txt \
  --source-url "https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/?" \
  --preview-intake \
  --debug-raw
```

Run it with a Zillow URL:

```bash
python3 -m briarwood.listing_intake.cli "https://www.zillow.com/homedetails/17-Cedar-Ln-Brookline-MA-02445/123456_zpid/"
```

Returned object shape:

- `intake_mode`
- `raw_extracted_data`
- `normalized_property_data`
- `missing_fields`
- `warnings`

Normalized listing fields include:

- `address`
- `purchase_price`
- `beds`
- `baths`
- `sqft`
- `lot_size`
- `property_type`
- `year_built`
- `listing_description`
- `days_on_market`
- `hoa_monthly`
- `tax_history`
- `price_history`

Example pasted listing text:

```text
Zillow
17 Cedar Lane, Brookline, MA 02445
Price $895,000
3 bd 2 ba 1,850 sqft
Lot size 4,792 sqft
Property type Single Family
Built in 1958
18 days on Zillow
HOA $0 / month
Overview: Classic Brookline single-family home with stable layout, finished lower level, and strong commuter access.
Price history
Mar 01, 2026 Listed for sale $895,000
Jan 15, 2020 Sold $760,000
Tax history
2025 Taxes $10,800 Assessed value $842,000
```

Example parsed output:

```json
{
  "intake_mode": "text_intake",
  "raw_extracted_data": {
    "source": "zillow",
    "intake_mode": "text_intake",
    "address": "17 Cedar Lane, Brookline, MA 02445",
    "price": 895000.0,
    "beds": 3,
    "baths": 2.0,
    "square_footage": 1850
  },
  "normalized_property_data": {
    "address": "17 Cedar Lane, Brookline, MA 02445",
    "town": "Brookline",
    "state": "MA",
    "purchase_price": 895000.0,
    "beds": 3,
    "baths": 2.0,
    "sqft": 1850
  },
  "missing_fields": [],
  "warnings": []
}
```

Example URL-only behavior:

```json
{
  "intake_mode": "url_intake",
  "raw_extracted_data": {
    "source": "zillow",
    "intake_mode": "url_intake",
    "listing_url": "https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/",
    "address": "1600 L St Belmar Nj 07719"
  },
  "normalized_property_data": {
    "address": "1600 L St Belmar Nj 07719",
    "source": "zillow",
    "source_url": "https://www.zillow.com/homedetails/1600-L-St-Belmar-NJ-07719/39225096_zpid/"
  },
  "missing_fields": [
    "purchase_price",
    "beds",
    "baths",
    "sqft",
    "property_type",
    "year_built"
  ],
  "warnings": [
    "URL intake is metadata-only in v1; no live page fetching is performed.",
    "Provide pasted listing text to extract richer fields like description, HOA, tax history, and price history.",
    "URL-only intake stores source metadata and inferred address text, but does not extract real listing fields."
  ]
}
```

Parser notes:

- Regex-based:
  - price
  - beds / baths
  - sqft
  - lot size
  - year built
  - HOA
  - taxes / tax history
  - days on market
  - description block
  - price history
- Rule-based:
  - URL mode routing
  - Zillow slug cleanup into address-like text
  - fallback property-type detection from known phrases
  - normalization of address into town / state / zip

To feed valuation later:

```python
from briarwood.listing_intake.service import ListingIntakeService
from briarwood.inputs.property_loader import load_property_from_listing_intake_result

service = ListingIntakeService()
result = service.intake(open("data/sample_zillow_listing.txt").read())
property_input = load_property_from_listing_intake_result(
    result,
    property_id="brookline-001",
)
```

Or go directly from listing source to `PropertyInput`:

```python
from briarwood.inputs.property_loader import load_property_from_listing_source

listing_text = open("data/sample_zillow_listing.txt").read()
property_input = load_property_from_listing_source(
    listing_text,
    property_id="brookline-001",
)
```

## Property Input

Each property JSON should include the main fields used by the modules:

- `property_id`
- `address`
- `town`
- `state`
- `beds`
- `baths`
- `sqft`
- `purchase_price`
- `taxes`
- `insurance`
- `estimated_monthly_rent`
- `down_payment_percent`
- `interest_rate`

Optional fields like `vacancy_rate`, `days_on_market`, `year_built`, `school_rating`, and `flood_risk` will improve some module outputs.

## Run

The canonical surface is the FastAPI + Next.js chat stack. Start the API:

```bash
uvicorn api.main:app --reload
```

And the web app:

```bash
cd web && npm install && npm run dev
```

Run the analysis pipeline directly in Python via the routed runner:

```python
from briarwood.inputs.property_loader import load_property_from_json
from briarwood.runner_routed import run_routed_report

property_input = load_property_from_json("data/sample_property.json")
result = run_routed_report(property_input)

print(result.unified_output.decision_stance)
```

## Test

```bash
python3 -m unittest discover -s tests
```

## How Cost / Valuation Works

The cost / valuation module lives in [`briarwood/modules/cost_valuation.py`](/Users/zachanderson/projects/briarwood/briarwood/modules/cost_valuation.py). Its assumptions live in [`briarwood/settings.py`](/Users/zachanderson/projects/briarwood/briarwood/settings.py).

### Inputs used

- `purchase_price`
- `sqft`
- `taxes`
- `insurance`
- `estimated_monthly_rent`
- `down_payment_percent`
- `interest_rate`
- `vacancy_rate` if present, otherwise `default_vacancy_rate`

### Calculations

`down_payment_amount`

```text
purchase_price * down_payment_percent
```

`loan_amount`

```text
purchase_price - down_payment_amount
```

`monthly_taxes`

```text
taxes / 12
```

`monthly_insurance`

```text
insurance / 12
```

`monthly_mortgage_payment`

```text
Standard fixed-rate amortizing loan payment
```

`monthly_total_cost`

```text
monthly_taxes + monthly_insurance + monthly_mortgage_payment
```

`annual_gross_rent`

```text
estimated_monthly_rent * 12
```

`annual_effective_rent`

```text
annual_gross_rent * (1 - vacancy_rate)
```

`annual_noi`

```text
annual_effective_rent - taxes - insurance
```

`monthly_cash_flow`

```text
(annual_noi - annual_debt_service) / 12
```

`price_per_sqft`

```text
purchase_price / sqft
```

`gross_yield`

```text
annual_gross_rent / purchase_price
```

`cap_rate`

```text
annual_noi / purchase_price
```

`dscr`

```text
annual_noi / annual_debt_service
```

`cash_on_cash_return`

```text
annual_cash_flow / down_payment_amount
```

### Score logic

The valuation score is a weighted heuristic, not an appraisal.

- Start with `base_score`
- Add a capped contribution from `cap_rate`
- Add a capped contribution from `dscr` above the baseline
- Add a capped contribution from `cash_on_cash_return`
- Add or subtract points based on monthly cash flow
- Clamp the final result to `0-100`

All of these weights and caps are editable in [`briarwood/settings.py`](/Users/zachanderson/projects/briarwood/briarwood/settings.py).

### Confidence logic

Confidence is based on how many required valuation fields are present:

- `purchase_price`
- `sqft`
- `taxes`
- `insurance`
- `estimated_monthly_rent`
- `down_payment_percent`
- `interest_rate`

The module scales confidence from a floor value up as more of those inputs are populated.

## How To Pressure Test

To pressure test calculations one by one:

1. Start with [`data/sample_property.json`](/Users/zachanderson/projects/briarwood/data/sample_property.json).
2. Change one input at a time, like `interest_rate` or `estimated_monthly_rent`.
3. Re-run `python3 app.py data/sample_property.json`.
4. Inspect the `cost_valuation` metrics block and summary.
5. If you want to change a default assumption rather than property data, edit [`briarwood/settings.py`](/Users/zachanderson/projects/briarwood/briarwood/settings.py) or pass a CLI override.

## Design Notes

- Nothing in the report flow is tied to one property.
- Modules still run independently and can be composed into one `AnalysisReport`.
- Assumptions that are likely to change are centralized in [`briarwood/settings.py`](/Users/zachanderson/projects/briarwood/briarwood/settings.py), not hidden deep in module code.
- The runner in [`briarwood/runner.py`](/Users/zachanderson/projects/briarwood/briarwood/runner.py) is the path to future batch runs, APIs, or saved report generation.

## Tear Sheet MVP

The tear sheet layer is intentionally lightweight and HTML-first.

- [`briarwood/reports/schemas.py`](/Users/zachanderson/projects/briarwood/briarwood/reports/schemas.py): typed payloads for each tear sheet section
- [`briarwood/reports/sections/`](/Users/zachanderson/projects/briarwood/briarwood/reports/sections): one builder per section
- [`briarwood/reports/tear_sheet.py`](/Users/zachanderson/projects/briarwood/briarwood/reports/tear_sheet.py): assembles a `TearSheet` from the shared `AnalysisReport`
- [`briarwood/reports/renderer.py`](/Users/zachanderson/projects/briarwood/briarwood/reports/renderer.py): renders the tear sheet as a single HTML page
- [`briarwood/reports/templates/tear_sheet.html`](/Users/zachanderson/projects/briarwood/briarwood/reports/templates/tear_sheet.html): static page structure
- [`briarwood/reports/assets/tear_sheet.css`](/Users/zachanderson/projects/briarwood/briarwood/reports/assets/tear_sheet.css): static institutional-style presentation

The tear sheet follows this structure:

- Header
- Conclusion block
- Thesis block
- Scenario chart
- Bull / Base / Bear case columns

Static:

- page layout
- typography and spacing
- section order
- card styling
- chart style

Dynamic:

- property name and subtitle
- ask / bear / base / bull values
- valuation explanation
- thesis bullets
- case assumptions, drivers, and risks

## Dash Workspace

Briarwood now also has a lightweight Dash workspace for interactive analysis.

- [`briarwood/dash_app/app.py`](/Users/zachanderson/projects/briarwood/briarwood/dash_app/app.py): Dash entrypoint and callbacks
- [`briarwood/dash_app/data.py`](/Users/zachanderson/projects/briarwood/briarwood/dash_app/data.py): sample property presets and analysis/export orchestration
- [`briarwood/dash_app/view_models.py`](/Users/zachanderson/projects/briarwood/briarwood/dash_app/view_models.py): UI-facing adapters over the existing Briarwood report pipeline
- [`briarwood/dash_app/compare.py`](/Users/zachanderson/projects/briarwood/briarwood/dash_app/compare.py): side-by-side comparison logic and “why are these different?” summaries
- [`briarwood/dash_app/components.py`](/Users/zachanderson/projects/briarwood/briarwood/dash_app/components.py): reusable cards, tables, and tab builders

Run it locally with:

```bash
./venv/bin/python -m briarwood.dash_app.app
```

Current workflow:

- use the top header to:
  - add a new property
  - select a saved/analyzed property
  - load multiple properties for comparison
- switch between two top-level modes:
  - `Single Property`
  - `Compare`
- use the shared section tabs in each mode:
  - `Overview`
  - `Value`
  - `Forward`
  - `Risk`
  - `Location`
  - `Income Support`
  - `Evidence`
- in `Compare`, each property renders as a vertical swim lane so the same section lines up across columns
- export a tear sheet for the focused property through the existing HTML report writer
- reopen saved properties without recomputing analysis when a persisted report is available

The Dash app is intentionally a thin orchestration layer. It does not recompute BCV, scenarios, or risk logic in the UI.

### Manual Subject + Comp Entry

The workspace now supports a first-pass internal Add Property workflow:

- enter a subject property directly from the `Add Property` button
- capture core facts, physical differentiators, and income/support inputs
- optionally add up to 10 manual comps
- run analysis without needing pasted listing text
- persist the full saved property bundle into:
  - `data/saved_properties/<property_id>/inputs.json`
  - `data/saved_properties/<property_id>/report.pkl`
  - `data/saved_properties/<property_id>/summary.json`
  - `data/saved_properties/<property_id>/tear_sheet.html`

Manual comps are intentionally optional:

- if no comps are entered, the report still runs
- if comps are entered, Briarwood routes them through the existing comparable-sales path
- comp confidence stays explicit and weak evidence still lowers support
