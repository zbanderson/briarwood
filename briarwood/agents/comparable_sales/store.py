from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from briarwood.agents.comparable_sales.schemas import ActiveListingRecord, ComparableSale


@dataclass(slots=True)
class CompDataset:
    metadata: dict[str, object]
    sales: list[ComparableSale]


class JsonComparableSalesStore:
    """Lightweight JSON-backed comp store for v1 import and manual entry flows."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> CompDataset:
        if not self.path.exists():
            return CompDataset(metadata={}, sales=[])
        payload = json.loads(self.path.read_text())
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        raw_sales = payload.get("sales", []) if isinstance(payload, dict) else []
        if not isinstance(raw_sales, list):
            raw_sales = []
        return CompDataset(
            metadata=metadata if isinstance(metadata, dict) else {},
            sales=[ComparableSale.model_validate(item) for item in raw_sales if isinstance(item, dict)],
        )

    def save(self, dataset: CompDataset) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "metadata": dataset.metadata,
            "sales": [sale.model_dump(exclude_none=True) for sale in dataset.sales],
        }
        self.path.write_text(json.dumps(payload, indent=2) + "\n")

    def append(self, sale: ComparableSale) -> ComparableSale:
        dataset = self.load()
        dataset.sales.append(sale)
        self.save(dataset)
        return sale

    def upsert(self, sale: ComparableSale, *, match_on: str = "source_ref") -> ComparableSale:
        dataset = self.load()
        replacement_key = getattr(sale, match_on, None)
        replaced = False
        if replacement_key:
            for index, existing in enumerate(dataset.sales):
                if getattr(existing, match_on, None) == replacement_key:
                    dataset.sales[index] = sale
                    replaced = True
                    break
        if not replaced:
            dataset.sales.append(sale)
        self.save(dataset)
        return sale

    def next_source_ref(self, town: str, prefix: str = "MANUAL") -> str:
        dataset = self.load()
        base = f"{town.strip().upper().replace(' ', '-')}-{prefix}"
        used = {
            sale.source_ref
            for sale in dataset.sales
            if sale.source_ref and sale.source_ref.startswith(base)
        }
        counter = 1
        while True:
            candidate = f"{base}-{counter:03d}"
            if candidate not in used:
                return candidate
            counter += 1


@dataclass(slots=True)
class ActiveListingDataset:
    metadata: dict[str, object]
    listings: list[ActiveListingRecord]


class JsonActiveListingStore:
    """JSON-backed store for active listings kept separate from closed-sale comps."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> ActiveListingDataset:
        if not self.path.exists():
            return ActiveListingDataset(metadata={}, listings=[])
        payload = json.loads(self.path.read_text())
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        raw_rows = payload.get("listings", []) if isinstance(payload, dict) else []
        if not isinstance(raw_rows, list):
            raw_rows = []
        return ActiveListingDataset(
            metadata=metadata if isinstance(metadata, dict) else {},
            listings=[ActiveListingRecord.model_validate(item) for item in raw_rows if isinstance(item, dict)],
        )

    def save(self, dataset: ActiveListingDataset) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "metadata": dataset.metadata,
            "listings": [row.model_dump(exclude_none=True) for row in dataset.listings],
        }
        self.path.write_text(json.dumps(payload, indent=2) + "\n")

    def append(self, row: ActiveListingRecord) -> ActiveListingRecord:
        dataset = self.load()
        dataset.listings.append(row)
        self.save(dataset)
        return row

    def upsert(self, row: ActiveListingRecord, *, match_on: str = "source_ref") -> ActiveListingRecord:
        dataset = self.load()
        replacement_key = getattr(row, match_on, None)
        replaced = False
        if replacement_key:
            for index, existing in enumerate(dataset.listings):
                if getattr(existing, match_on, None) == replacement_key:
                    dataset.listings[index] = row
                    replaced = True
                    break
        if not replaced:
            dataset.listings.append(row)
        self.save(dataset)
        return row
