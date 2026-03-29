from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SchoolSignalInput(BaseModel):
    """Normalized public-school proxy inputs for a Briarwood school signal."""

    model_config = ConfigDict(extra="forbid")

    geography_name: str = Field(min_length=1)
    state: str = Field(min_length=2, max_length=2)
    achievement_index: float | None = Field(default=None, ge=0, le=100)
    growth_index: float | None = Field(default=None, ge=0, le=100)
    readiness_index: float | None = Field(default=None, ge=0, le=100)
    chronic_absenteeism_pct: float | None = Field(default=None, ge=0, le=100)
    student_teacher_ratio: float | None = Field(default=None, gt=0)
    district_coverage: float | None = Field(default=None, ge=0, le=1)
    source_review_quality: float | None = Field(default=None, ge=0, le=1)
    as_of: str | None = None
    refresh_frequency_days: int | None = Field(default=None, gt=0)


class SchoolSignalOutput(BaseModel):
    """Structured Briarwood school signal output."""

    model_config = ConfigDict(extra="forbid")

    school_signal: float
    confidence: float
    summary: str
    assumptions: list[str]
    unsupported_claims: list[str]
    source_name: str = "briarwood_school_signal_nj_spr_v1"
