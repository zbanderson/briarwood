"""Scarcity-related scoring exports."""

from briarwood.agents.scarcity.demand_consistency import DemandConsistencyScorer, score_demand_consistency
from briarwood.agents.scarcity.land_scarcity import LandScarcityScorer, score_land_scarcity
from briarwood.agents.scarcity.location_scarcity import LocationScarcityScorer, score_location_scarcity
from briarwood.agents.scarcity.scarcity_support import ScarcitySupportScorer, score_scarcity_support
from briarwood.agents.scarcity.schemas import (
    DemandConsistencyInputs,
    DemandConsistencyScore,
    LandScarcityInputs,
    LandScarcityScore,
    LocationScarcityInputs,
    LocationScarcityScore,
    ScarcitySupportInputs,
    ScarcitySupportScore,
)

__all__ = [
    "DemandConsistencyInputs",
    "DemandConsistencyScore",
    "DemandConsistencyScorer",
    "LandScarcityInputs",
    "LandScarcityScore",
    "LandScarcityScorer",
    "LocationScarcityInputs",
    "LocationScarcityScore",
    "LocationScarcityScorer",
    "ScarcitySupportInputs",
    "ScarcitySupportScore",
    "ScarcitySupportScorer",
    "score_demand_consistency",
    "score_land_scarcity",
    "score_location_scarcity",
    "score_scarcity_support",
]
