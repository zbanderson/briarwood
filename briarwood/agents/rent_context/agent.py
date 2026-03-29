from __future__ import annotations

from briarwood.agents.rent_context.priors import get_rent_prior
from briarwood.agents.rent_context.schemas import RentContextInput, RentContextOutput


class RentContextAgent:
    """Resolve whether rent is provided, estimated, or still missing."""

    def run(self, payload: RentContextInput | dict[str, object]) -> RentContextOutput:
        inputs = payload if isinstance(payload, RentContextInput) else RentContextInput.model_validate(payload)

        if inputs.explicit_monthly_rent is not None:
            return RentContextOutput(
                rent_estimate=round(inputs.explicit_monthly_rent, 2),
                rent_source_type="provided",
                confidence=0.9,
                assumptions=[],
                warnings=[],
            )

        prior = get_rent_prior(inputs.town, inputs.state)
        if prior is not None and inputs.sqft is not None and inputs.sqft > 0:
            estimated_rent = round(inputs.sqft * prior.monthly_rent_per_sqft, 2)
            return RentContextOutput(
                rent_estimate=estimated_rent,
                rent_source_type="estimated",
                confidence=prior.confidence,
                assumptions=[
                    (
                        f"Rent estimate uses Briarwood's {prior.town} town-level rent prior at about "
                        f"${prior.monthly_rent_per_sqft:.2f}/sqft."
                    )
                ],
                warnings=[
                    "Monthly rent was estimated from a town-level prior and should not be treated as a property-specific rental comp."
                ],
            )

        if prior is not None and inputs.beds is not None:
            base_rent = prior.base_monthly_rent_by_bed.get(inputs.beds)
            if base_rent is not None:
                bath_adjustment = 0.0
                if inputs.baths is not None:
                    bath_adjustment = max(-150.0, min((inputs.baths - max(inputs.beds - 1, 1)) * 125.0, 250.0))
                estimated_rent = round(base_rent + bath_adjustment, 2)
                return RentContextOutput(
                    rent_estimate=estimated_rent,
                    rent_source_type="estimated",
                    confidence=max(prior.confidence - 0.08, 0.22),
                    assumptions=[
                        (
                            f"Rent estimate uses Briarwood's {prior.town} town-level bed-count prior because square footage is missing."
                        )
                    ],
                    warnings=[
                        "Monthly rent was estimated from a town-level bed-count prior and should not be treated as a property-specific rental comp."
                    ],
                )

        warnings = ["Monthly rent was not provided, so Briarwood could not verify property-level rental support."]
        if prior is not None and inputs.sqft is None and inputs.beds is None:
            warnings.append("A town-level rent prior exists, but both square footage and bed count are missing so no rent estimate was used.")

        return RentContextOutput(
            rent_estimate=None,
            rent_source_type="missing",
            confidence=0.0,
            assumptions=[],
            warnings=warnings,
        )


def resolve_rent_context(payload: RentContextInput | dict[str, object]) -> RentContextOutput:
    return RentContextAgent().run(payload)
