"""Representation layer.

Audit 1.4 + 1.7: the routed core produces a rich `UnifiedIntelligenceOutput`
but the chat surface emits a fixed set of charts regardless of which claims
the verdict actually makes. The representation layer formalizes the link
between verdict claims, their supporting evidence, and the chart picked to
visualize them.

Two pieces:

- `charts` — typed registry of chart specs + renderer wrappers around the
  existing `_native_*_chart` helpers in `api.pipeline_adapter`.
- `agent` — LLM layer with structured output that selects which claims to
  surface and which registered chart best represents each one.

Only the decision path consumes this this week. Browse-tier chart emission
remains hardcoded.
"""

from briarwood.representation.charts import (
    ChartSpec,
    all_specs,
    get_spec,
    register,
    render,
)
from briarwood.representation.agent import (
    ClaimType,
    RepresentationAgent,
    RepresentationPlan,
    RepresentationSelection,
)

__all__ = [
    "ChartSpec",
    "ClaimType",
    "RepresentationAgent",
    "RepresentationPlan",
    "RepresentationSelection",
    "all_specs",
    "get_spec",
    "register",
    "render",
]
