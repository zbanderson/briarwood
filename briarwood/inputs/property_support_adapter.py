from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from briarwood.agents.comparable_sales import FileBackedComparableSalesProvider
from briarwood.agents.rent_context import RentContextAgent, RentContextInput
from briarwood.schemas import (
    CanonicalPropertyData,
    InputCoverageStatus,
    SourceCoverageItem,
)


class PropertySupportAdapter:
    def __init__(
        self,
        *,
        rent_context_agent: RentContextAgent | None = None,
        comparable_sales_provider: FileBackedComparableSalesProvider | None = None,
    ) -> None:
        self.rent_context_agent = rent_context_agent or RentContextAgent()
        self.comparable_sales_provider = comparable_sales_provider or FileBackedComparableSalesProvider(
            Path(__file__).resolve().parents[2] / "data" / "comps" / "sales_comps.json"
        )

    def enrich(self, canonical: CanonicalPropertyData) -> CanonicalPropertyData:
        facts = canonical.facts
        assumptions = canonical.user_assumptions
        coverage = dict(canonical.source_metadata.source_coverage)

        rent_context = self.rent_context_agent.run(
            RentContextInput(
                town=facts.town,
                state=facts.state,
                sqft=facts.sqft,
                beds=facts.beds,
                baths=facts.baths,
                explicit_monthly_rent=assumptions.estimated_monthly_rent,
            )
        )

        updated_assumptions = assumptions
        if assumptions.estimated_monthly_rent is None and rent_context.rent_estimate is not None:
            updated_assumptions = replace(assumptions, estimated_monthly_rent=rent_context.rent_estimate)

        if rent_context.rent_source_type == "provided":
            coverage["rent_estimate"] = SourceCoverageItem(
                category="rent_estimate",
                status=InputCoverageStatus.USER_SUPPLIED,
                source_name="manual assumption",
            )
        elif rent_context.rent_source_type == "estimated":
            coverage["rent_estimate"] = SourceCoverageItem(
                category="rent_estimate",
                status=InputCoverageStatus.ESTIMATED,
                source_name="rent_context_prior",
                note=rent_context.assumptions[0] if rent_context.assumptions else None,
            )
        else:
            coverage["rent_estimate"] = SourceCoverageItem(
                category="rent_estimate",
                status=InputCoverageStatus.MISSING,
            )

        sales = self.comparable_sales_provider.get_sales(town=facts.town, state=facts.state)
        if updated_assumptions.manual_comp_inputs:
            coverage["comp_support"] = SourceCoverageItem(
                category="comp_support",
                status=InputCoverageStatus.USER_SUPPLIED,
                source_name="manual comps",
                note=f"{len(updated_assumptions.manual_comp_inputs)} manual comp entries provided.",
            )
        elif sales:
            verified_count = len(
                [
                    sale
                    for sale in sales
                    if sale.sale_verification_status in {"public_record_verified", "mls_verified"}
                ]
            )
            matched_count = len(
                [
                    sale
                    for sale in sales
                    if sale.sale_verification_status in {"public_record_matched", "public_record_verified", "mls_verified"}
                ]
            )
            if verified_count > 0:
                coverage["comp_support"] = SourceCoverageItem(
                    category="comp_support",
                    status=InputCoverageStatus.SOURCED,
                    source_name="file_backed_comp_db",
                    note=f"{verified_count} verified comps available in current town dataset.",
                )
            elif matched_count > 0:
                coverage["comp_support"] = SourceCoverageItem(
                    category="comp_support",
                    status=InputCoverageStatus.ESTIMATED,
                    source_name="file_backed_comp_db",
                    note=f"{matched_count} public-record-matched comps available, but no fully verified sale comps yet.",
                )
            else:
                coverage["comp_support"] = SourceCoverageItem(
                    category="comp_support",
                    status=InputCoverageStatus.ESTIMATED,
                    source_name="file_backed_comp_db",
                    note=f"{len(sales)} seed/review comps available, but none are public-record or MLS verified yet.",
                )
        else:
            coverage["comp_support"] = SourceCoverageItem(
                category="comp_support",
                status=InputCoverageStatus.MISSING,
            )

        provenance = list(canonical.source_metadata.provenance)
        provenance.append("property_support_adapter")
        return replace(
            canonical,
            user_assumptions=updated_assumptions,
            source_metadata=replace(
                canonical.source_metadata,
                source_coverage=coverage,
                provenance=provenance,
            ),
        )
