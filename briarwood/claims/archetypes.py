from enum import Enum


class Archetype(str, Enum):
    """Response shape category. Cross-references AnswerType + QuestionFocus but independent.

    Each archetype corresponds to exactly one claim-object schema in briarwood.claims.
    """

    VERDICT_WITH_COMPARISON = "verdict_with_comparison"
    # Future archetypes reserved but not implemented in wedge:
    # OPTION_COMPARISON = "option_comparison"
    # SINGLE_NUMBER = "single_number"
    # TREND_OVER_TIME = "trend_over_time"
    # RISK_BREAKDOWN = "risk_breakdown"
    # ORIENTATION = "orientation"
    # RECOMMENDATION_WITH_CAVEATS = "recommendation_with_caveats"
