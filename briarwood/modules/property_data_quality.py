from __future__ import annotations

import os
from pathlib import Path

from briarwood.data_quality.property_intelligence import compute_property_tax_quality_intelligence
from briarwood.data_sources.nj_tax_intelligence import NJTaxIntelligenceStore, town_tax_context
from briarwood.schemas import ModuleResult, PropertyInput


class PropertyDataQualityModule:
    name = "property_data_quality"

    def __init__(self, *, tax_store: NJTaxIntelligenceStore | None = None) -> None:
        self.tax_store = tax_store or _load_default_tax_store()

    def run(self, property_input: PropertyInput) -> ModuleResult:
        tax_context = (
            town_tax_context(
                self.tax_store,
                town=property_input.town,
                county=property_input.county or "",
            )
            if self.tax_store is not None and property_input.county
            else {}
        )
        tax_provenance = property_input.provenance_for("taxes")
        tax_year_provenance = property_input.provenance_for("tax_year")
        assessed_total_provenance = property_input.provenance_for("assessed_total")
        payload = compute_property_tax_quality_intelligence(
            property_facts={
                "address": property_input.address,
                "town": property_input.town,
                "state": property_input.state,
                "beds": property_input.beds,
                "baths": property_input.baths,
                "sqft": property_input.sqft,
                "property_type": property_input.property_type,
                "purchase_price": property_input.purchase_price,
                "taxes": property_input.taxes,
            },
            attom_payload={
                "tax_amount": tax_provenance.value if tax_provenance is not None and "attom" in tax_provenance.source.lower() else None,
                "tax_year": tax_year_provenance.value if tax_year_provenance is not None else None,
                "assessed_total": assessed_total_provenance.value if assessed_total_provenance is not None else None,
            },
            municipality_tax_context=tax_context,
        )
        return ModuleResult(
            module_name=self.name,
            metrics={
                "property_tax_confirmed_flag": payload.property_tax_confirmed_flag,
                "municipality_tax_context_flag": payload.municipality_tax_context_flag,
                "reassessment_risk_score": payload.reassessment_risk_score,
                "tax_burden_score": payload.tax_burden_score,
                "structural_data_quality_score": payload.structural_data_quality_score,
                "comp_eligibility_score": payload.comp_eligibility_score,
            },
            score=payload.comp_eligibility_score * 100.0,
            confidence=0.72 if payload.municipality_tax_context_flag else 0.48,
            summary=" | ".join(payload.notes) if payload.notes else "Property-level tax and structural quality signals are only partially populated.",
            payload=payload,
        )


def _load_default_tax_store() -> NJTaxIntelligenceStore | None:
    env_path = os.environ.get("BRIARWOOD_NJ_TAX_PATH", "").strip()
    if not env_path:
        return None
    path = Path(env_path)
    if not path.exists():
        return None
    try:
        return NJTaxIntelligenceStore.load_csv(path)
    except OSError:
        return None
