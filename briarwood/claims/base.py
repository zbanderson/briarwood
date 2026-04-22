from typing import Literal

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    """Which modules contributed to this claim. Honest accounting of what ran vs skipped."""

    models_consulted: list[str] = Field(default_factory=list)
    models_skipped: list[str] = Field(default_factory=list)
    skip_reason: str | None = None
    bridges_fired: list[str] = Field(default_factory=list)


class Confidence(BaseModel):
    """Per-claim confidence. Drives assertion rubric in representation."""

    score: float = Field(ge=0.0, le=1.0)
    band: Literal["high", "medium", "low", "very_low"]

    @classmethod
    def from_score(cls, score: float) -> "Confidence":
        if score >= 0.90:
            band: Literal["high", "medium", "low", "very_low"] = "high"
        elif score >= 0.70:
            band = "medium"
        elif score >= 0.50:
            band = "low"
        else:
            band = "very_low"
        return cls(score=score, band=band)


class Caveat(BaseModel):
    """Something the user should know but the system couldn't verify."""

    text: str
    severity: Literal["info", "warning", "blocking"]
    source: str


class NextQuestion(BaseModel):
    """Specialist-aware follow-up prompt. Routes cleanly back into the pipeline."""

    text: str
    routes_to: str


class SurfacedInsight(BaseModel):
    """Value Scout's output. Optional — None if Scout found nothing notable."""

    headline: str
    reason: str
    supporting_fields: list[str]
    scenario_id: str | None = None
