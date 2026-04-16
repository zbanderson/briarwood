"""Triage adapter — orchestration/fan-out layer.

Wraps the existing planner/executor pair with a thin coordinator that:
  - populates a PipelineSession from parsed intent,
  - reads per-model routing weights from the eval scorecard (if present),
  - executes specialist modules in parallel via the executor's parallel mode,
  - backfills ModelResult entries on the session from ExecutionContext.

Contains no domain logic. Existing orchestrator.py and synthesis callers
continue to work unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from briarwood.pipeline.session import (
    PipelineSession,
    session_from_execution_context,
    session_to_execution_context,
)


ROOT = Path(__file__).resolve().parents[2]
MODEL_PERF_LOG = ROOT / "data" / "eval" / "model_performance_log.jsonl"


def load_model_weights(log_path: Path = MODEL_PERF_LOG) -> dict[str, float]:
    """Read the latest per-model weights from the eval scorecard.

    Falls back to an empty dict (equal weighting) if the file doesn't exist.
    """

    if not log_path.exists():
        return {}

    latest: dict[str, float] = {}
    try:
        with log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                model = row.get("model")
                weight = row.get("contribution_weight")
                if isinstance(model, str) and isinstance(weight, (int, float)):
                    latest[model] = float(weight)
    except OSError:
        return {}
    return latest


class TriageAgent:
    """Fan-out orchestrator. Holds no domain knowledge.

    Accepts a runner callable that executes the existing planner/executor
    pipeline and returns a dict of {module_name: normalized_output}. This
    keeps the adapter decoupled from the module registry internals.
    """

    def __init__(
        self,
        runner: Callable[[Any], dict[str, Any]] | None = None,
        weights: dict[str, float] | None = None,
    ) -> None:
        self._runner = runner
        self._weights = weights if weights is not None else load_model_weights()

    @property
    def weights(self) -> dict[str, float]:
        return dict(self._weights)

    def dispatch(
        self,
        session: PipelineSession,
        runner: Callable[[Any], dict[str, Any]] | None = None,
    ) -> PipelineSession:
        """Run the specialist layer and populate session.model_outputs.

        ``runner`` is a function that accepts an ExecutionContext and
        returns a dict {module_name: {data, confidence, warnings}}. If not
        provided the adapter's default runner is used.
        """

        active = runner or self._runner
        if active is None:
            raise ValueError("TriageAgent requires a runner callable.")

        context = session_to_execution_context(session)
        outputs = active(context)

        if not isinstance(outputs, dict):
            raise TypeError("runner must return a dict of module outputs.")

        for module_name, payload in outputs.items():
            if not isinstance(payload, dict):
                continue
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            session.record_model_output(
                module_name,
                data if isinstance(data, dict) else {"value": data},
                confidence=payload.get("confidence"),
                warnings=payload.get("warnings") or [],
            )

        session_from_execution_context(session, context)

        session.contribution_map = self._compute_contribution_map(session)
        return session

    def _compute_contribution_map(self, session: PipelineSession) -> dict[str, float]:
        """Combine observed confidence with learned weights (equal if none)."""

        if not session.model_outputs:
            return {}

        confidences = {
            name: float(result.confidence) if isinstance(result.confidence, (int, float)) else 0.5
            for name, result in session.model_outputs.items()
        }
        weighted = {
            name: confidences[name] * float(self._weights.get(name, 1.0))
            for name in confidences
        }
        total = sum(weighted.values()) or 1.0
        return {name: round(value / total, 4) for name, value in weighted.items()}


def compute_contribution_map_from_outputs(
    module_outputs: dict[str, Any],
    weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """Build a contribution_map from raw module outputs (for legacy callers).

    Accepts the ``outputs`` dict produced by the executor —
    ``{module_name: {data, confidence, warnings}}`` — and normalizes each
    module's contribution by confidence × optional routing weight.
    """

    weights = weights or {}
    raw: dict[str, float] = {}
    for name, payload in (module_outputs or {}).items():
        if not isinstance(payload, dict):
            continue
        conf = payload.get("confidence")
        conf_value = float(conf) if isinstance(conf, (int, float)) else 0.5
        raw[name] = conf_value * float(weights.get(name, 1.0))
    total = sum(raw.values()) or 1.0
    return {name: round(value / total, 4) for name, value in raw.items()}


__all__ = [
    "TriageAgent",
    "load_model_weights",
    "compute_contribution_map_from_outputs",
    "MODEL_PERF_LOG",
]
