"""Shared session object that travels through all pipeline layers.

PipelineSession is the vehicle that carries intent, parser output, per-model
results, synthesis, decision, and feedback through the 8-layer pipeline.
It is interop-only: it converts to/from the existing ExecutionContext and
agent.session.Session without modifying either.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ModelResult:
    """One specialist model's output + metadata."""

    model_name: str
    data: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "data": dict(self.data),
            "confidence": self.confidence,
            "warnings": list(self.warnings),
        }


@dataclass
class PipelineSession:
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    raw_intent: str = ""
    parser_output: dict[str, Any] = field(default_factory=dict)

    model_outputs: dict[str, ModelResult] = field(default_factory=dict)
    synthesis: dict[str, Any] = field(default_factory=dict)
    decision: dict[str, Any] = field(default_factory=dict)

    contribution_map: dict[str, float] = field(default_factory=dict)
    feedback: dict[str, Any] = field(default_factory=dict)

    property_id: str | None = None
    property_data: dict[str, Any] = field(default_factory=dict)

    def record_model_output(
        self,
        model_name: str,
        data: dict[str, Any],
        confidence: float | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        self.model_outputs[model_name] = ModelResult(
            model_name=model_name,
            data=dict(data),
            confidence=confidence,
            warnings=list(warnings or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "raw_intent": self.raw_intent,
            "parser_output": dict(self.parser_output),
            "model_outputs": {k: v.to_dict() for k, v in self.model_outputs.items()},
            "synthesis": dict(self.synthesis),
            "decision": dict(self.decision),
            "contribution_map": dict(self.contribution_map),
            "feedback": dict(self.feedback),
            "property_id": self.property_id,
        }


def session_to_execution_context(session: PipelineSession) -> "object":
    """Build an ExecutionContext from a PipelineSession (lazy import)."""

    from briarwood.execution.context import ExecutionContext

    return ExecutionContext(
        property_id=session.property_id,
        property_data=dict(session.property_data),
        parser_output=dict(session.parser_output),
        prior_outputs={
            name: result.data for name, result in session.model_outputs.items()
        },
    )


def session_from_execution_context(
    session: PipelineSession,
    context: "object",
) -> PipelineSession:
    """Backfill a PipelineSession from an ExecutionContext after a run."""

    from briarwood.execution.context import ExecutionContext

    if not isinstance(context, ExecutionContext):
        raise TypeError("context must be an ExecutionContext")

    for module_name, output in context.prior_outputs.items():
        if not isinstance(output, dict):
            continue
        data = output.get("data") if "data" in output else output
        confidence = output.get("confidence") if "confidence" in output else None
        warnings = output.get("warnings") if "warnings" in output else []
        session.record_model_output(
            module_name,
            data if isinstance(data, dict) else {"value": data},
            confidence=confidence,
            warnings=list(warnings) if isinstance(warnings, list) else [],
        )
    if context.property_id and not session.property_id:
        session.property_id = context.property_id
    return session


__all__ = [
    "ModelResult",
    "PipelineSession",
    "session_from_execution_context",
    "session_to_execution_context",
]
