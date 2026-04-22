"""Pipeline shared infrastructure.

This package formerly housed a parallel verdict stack (`Pipeline`,
`UnifiedIntelligenceAgent`, `DecisionAgent`, `FeedbackLogger`,
`ScenarioModelAdapter`). The canonical verdict now lives in
``briarwood/synthesis/structured.py`` and flows through the routed
runner + FastAPI adapter; the parallel Dash/tear-sheet rendering
stack and its legacy projector were removed as part of the
verdict-path consolidation.

What remains here is shared infrastructure used by the routed stack and
other active code paths:

- ``session``: ``PipelineSession`` / ``ModelResult`` — state container used
  by routed runner, charts, and triage.
- ``triage``: ``TriageAgent`` + ``load_model_weights`` — imported by
  ``runner_routed`` and ``modules/confidence``.
- ``feedback_mixin``: ``FeedbackReceiverMixin`` + ``attach_feedback_interface``
  — imported by ``modules/security_model``.
- ``enrichment``: ``enrich_property`` + ``load_saved_enrichment`` — imported
  by ``agent/tools``.
- ``presentation``: ``build_property_presentation`` — imported by
  ``agent/tools``.
- ``representation``: flagged for review (currently test-only).
"""

from briarwood.pipeline.enrichment import (
    PropertyEnrichmentBundle,
    enrich_property,
    load_saved_enrichment,
)
from briarwood.pipeline.feedback_mixin import (
    FeedbackReceiverMixin,
    attach_feedback_interface,
)
from briarwood.pipeline.presentation import (
    PropertyPresentationPayload,
    build_property_presentation,
)
from briarwood.pipeline.session import (
    ModelResult,
    PipelineSession,
    session_from_execution_context,
    session_to_execution_context,
)
from briarwood.pipeline.triage import TriageAgent

__all__ = [
    "FeedbackReceiverMixin",
    "ModelResult",
    "PipelineSession",
    "PropertyEnrichmentBundle",
    "PropertyPresentationPayload",
    "TriageAgent",
    "attach_feedback_interface",
    "build_property_presentation",
    "enrich_property",
    "load_saved_enrichment",
    "session_from_execution_context",
    "session_to_execution_context",
]
