"""Pipeline reconciliation layer.

Additive adapters that wire the existing briarwood modules into the
8-layer architecture (Intent, Parser, Triage, Specialist Models, Unified
Intelligence, Decision, Feedback, Eval). Nothing here replaces existing
code — all adapters wrap existing implementations.
"""

from briarwood.pipeline.decision import DecisionAgent
from briarwood.pipeline.feedback import FeedbackLogger
from briarwood.pipeline.feedback_mixin import (
    FeedbackReceiverMixin,
    attach_feedback_interface,
)
from briarwood.pipeline.runner import Pipeline
from briarwood.pipeline.scenario_adapter import ScenarioModelAdapter
from briarwood.pipeline.session import (
    ModelResult,
    PipelineSession,
    session_from_execution_context,
    session_to_execution_context,
)
from briarwood.pipeline.triage import TriageAgent
from briarwood.pipeline.unified import UnifiedIntelligenceAgent

__all__ = [
    "DecisionAgent",
    "FeedbackLogger",
    "FeedbackReceiverMixin",
    "ModelResult",
    "Pipeline",
    "PipelineSession",
    "ScenarioModelAdapter",
    "TriageAgent",
    "UnifiedIntelligenceAgent",
    "attach_feedback_interface",
    "session_from_execution_context",
    "session_to_execution_context",
]
