from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RentContextInput(BaseModel):
    """Inputs for resolving usable rent context."""

    model_config = ConfigDict(extra="forbid")

    town: str = Field(min_length=1)
    state: str = Field(min_length=2, max_length=2)
    sqft: int | None = Field(default=None, ge=0)
    beds: int | None = Field(default=None, ge=0)
    baths: float | None = Field(default=None, ge=0)
    explicit_monthly_rent: float | None = Field(default=None, ge=0)


class RentContextOutput(BaseModel):
    """Structured rent context for downstream underwriting."""

    model_config = ConfigDict(extra="forbid")

    rent_estimate: float | None
    rent_source_type: str = Field(pattern="^(provided|estimated|missing)$")
    confidence: float = Field(ge=0, le=1)
    assumptions: list[str]
    warnings: list[str]
