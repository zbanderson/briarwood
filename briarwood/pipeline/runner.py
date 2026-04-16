"""Pipeline runner — ties all 8 layers together.

Usage:
    from briarwood.pipeline.runner import Pipeline

    pipeline = Pipeline(specialists={"income_model": IncomeModel(), ...})
    session = pipeline.run(raw_intent="buy and rent near the beach",
                           parsed_intent={...},
                           property_data={...})
    pipeline.record_feedback(session, explicit_signal="accepted")

The runner owns no domain logic — it is a coordinator.
"""

from __future__ import annotations

from typing import Any, Callable

from briarwood.pipeline.decision import DecisionAgent
from briarwood.pipeline.feedback import FeedbackLogger
from briarwood.pipeline.feedback_mixin import attach_feedback_interface
from briarwood.pipeline.scenario_adapter import (
    SCENARIO_MODULE_NAMES,
    ScenarioModelAdapter,
)
from briarwood.pipeline.session import PipelineSession
from briarwood.pipeline.triage import TriageAgent
from briarwood.pipeline.unified import UnifiedIntelligenceAgent


class Pipeline:
    """End-to-end coordinator for Intent → Parser → Triage → Models → Unified → Decision → Feedback."""

    def __init__(
        self,
        specialists: dict[str, Any],
        *,
        triage: TriageAgent | None = None,
        unified: UnifiedIntelligenceAgent | None = None,
        decision: DecisionAgent | None = None,
        feedback_logger: FeedbackLogger | None = None,
    ) -> None:
        self.specialists = {
            name: attach_feedback_interface(module) for name, module in specialists.items()
        }
        self.triage = triage or TriageAgent()
        self.unified = unified or UnifiedIntelligenceAgent()
        self.decision = decision or DecisionAgent()
        self.feedback = feedback_logger or FeedbackLogger()
        self.scenario_adapter = ScenarioModelAdapter()

    def run(
        self,
        *,
        raw_intent: str,
        parsed_intent: dict[str, Any] | None = None,
        property_data: dict[str, Any] | None = None,
        property_id: str | None = None,
        runner: Callable[[Any], dict[str, Any]] | None = None,
    ) -> PipelineSession:
        """Run the full pipeline. Returns the populated PipelineSession."""

        session = PipelineSession(
            raw_intent=raw_intent,
            parser_output=dict(parsed_intent or {}),
            property_id=property_id,
            property_data=dict(property_data or {}),
        )

        active_runner = runner or self._default_runner
        self.triage.dispatch(session, runner=active_runner)
        self._merge_scenario_model(session)
        # Recompute contribution map now that scenario_model is merged so the
        # downstream layers (and feedback log) see a complete picture.
        session.contribution_map = self.triage._compute_contribution_map(session)
        self.unified.synthesize(session)
        self.decision.decide(session)
        return session

    def record_feedback(
        self,
        session: PipelineSession,
        *,
        explicit_signal: str | None = None,
        outcome: str | None = None,
    ) -> None:
        """Append a feedback row and dispatch signals to contributing models."""

        self.feedback.log_session(
            session, explicit_signal=explicit_signal, outcome=outcome
        )
        self.feedback.dispatch_to_models(session, self.specialists)

    def _merge_scenario_model(self, session: PipelineSession) -> None:
        """If any sub-scenario modules produced output, fold them into one Scenario Model."""

        sub_present = any(
            name in session.model_outputs for name in SCENARIO_MODULE_NAMES
        )
        if not sub_present:
            return
        prior = {
            name: {
                "data": session.model_outputs[name].data,
                "confidence": session.model_outputs[name].confidence,
                "warnings": session.model_outputs[name].warnings,
            }
            for name in SCENARIO_MODULE_NAMES
            if name in session.model_outputs
        }
        merged = self.scenario_adapter.aggregate(prior)
        session.record_model_output(
            "scenario_model",
            merged["data"],
            confidence=merged.get("confidence"),
            warnings=merged.get("warnings") or [],
        )

    def _default_runner(self, context: Any) -> dict[str, Any]:
        """Invoke each registered specialist against the property data in context.

        Specialists that expose a ``run(property_input)`` method are invoked
        directly. This keeps the pipeline self-contained for the integration
        test while leaving the door open to plug the executor-based runner.
        """

        outputs: dict[str, Any] = {}
        property_input = dict(getattr(context, "property_data", {}) or {})
        for name, module in self.specialists.items():
            if not hasattr(module, "run"):
                continue
            try:
                result = module.run(property_input)
            except TypeError:
                # Legacy modules may expect a Pydantic PropertyInput; skip
                # cleanly in the adapter layer rather than raising.
                continue
            if isinstance(result, dict):
                outputs[name] = result
            else:
                outputs[name] = {"data": {"value": result}, "confidence": None, "warnings": []}
        return outputs


__all__ = ["Pipeline"]
