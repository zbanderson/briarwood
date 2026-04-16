"""FeedbackLogger — Layer 07 explicit-signal writer + return-path dispatch.

The existing ``intelligence_capture`` module writes implicit capture rows
when a session completes. FeedbackLogger adds:

  - An explicit-signal writer used when a user accepts / rejects / modifies
    a recommendation. Writes to the same JSONL with the extended schema
    (session_id, contribution_map, explicit_signal, outcome).
  - A ``dispatch_to_models`` method that calls ``receive_feedback`` on each
    contributing model per the session's contribution_map. Default
    implementations are no-ops (see feedback_mixin) — this just wires the
    return-path from the architecture diagram.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import json
from datetime import datetime, timezone

from briarwood.intelligence_capture import CAPTURE_PATH
from briarwood.pipeline.session import PipelineSession


class FeedbackLogger:
    def __init__(self, path: Path = CAPTURE_PATH) -> None:
        self.path = Path(path)

    def log_session(
        self,
        session: PipelineSession,
        explicit_signal: str | None = None,
        outcome: str | None = None,
    ) -> Path:
        """Write an end-of-session feedback row to the extended schema."""

        record = {
            "kind": "pipeline_session",
            "session_id": session.session_id,
            "raw_intent": session.raw_intent,
            "parser_output": dict(session.parser_output),
            "model_confidences": {
                name: result.confidence
                for name, result in session.model_outputs.items()
            },
            "synthesis": dict(session.synthesis),
            "decision_summary": {
                "primary_recommendation": (session.decision or {}).get("primary_recommendation"),
                "scenarios_count": len((session.decision or {}).get("scenarios") or []),
                "risk_flags": (session.decision or {}).get("risk_flags") or [],
            },
            "contribution_map": dict(session.contribution_map),
            "explicit_signal": explicit_signal,
            "outcome": outcome,
            "tags": self._tags(session, explicit_signal, outcome),
        }
        session.feedback = {
            "explicit_signal": explicit_signal,
            "outcome": outcome,
            "logged_at_path": str(self.path),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            **record,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
        return self.path

    def dispatch_to_models(
        self,
        session: PipelineSession,
        registry: dict[str, Any],
    ) -> dict[str, bool]:
        """Call receive_feedback on each contributing model.

        Returns a map of {model_name: dispatched}. Missing or non-conforming
        modules are skipped without error.
        """

        dispatched: dict[str, bool] = {}
        signal = {
            "explicit": session.feedback.get("explicit_signal"),
            "outcome": session.feedback.get("outcome"),
            "weight": None,
        }
        for model_name, weight in session.contribution_map.items():
            module = registry.get(model_name)
            if module is None or not hasattr(module, "receive_feedback"):
                dispatched[model_name] = False
                continue
            payload = dict(signal)
            payload["weight"] = weight
            try:
                module.receive_feedback(session.session_id, payload)
                dispatched[model_name] = True
            except Exception:
                dispatched[model_name] = False
        return dispatched

    def _tags(
        self,
        session: PipelineSession,
        explicit_signal: str | None,
        outcome: str | None,
    ) -> list[str]:
        tags = ["pipeline-session"]
        if explicit_signal:
            tags.append(f"explicit-{explicit_signal}")
        if outcome:
            tags.append(f"outcome-{outcome}")
        if session.synthesis.get("stance"):
            tags.append(f"stance-{session.synthesis['stance']}")
        return tags


__all__ = ["FeedbackLogger"]
