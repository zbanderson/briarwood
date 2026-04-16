"""ScenarioModelAdapter — unify existing scenario modules behind one interface.

The target architecture has a single "Scenario Model". The codebase has
multiple scenario modules (renovation, teardown, bull/base/bear, hold-to-rent).
This adapter merges their prior_outputs from an ExecutionContext (or a dict)
into one Scenario Model payload for the Unified Intelligence layer.

No scenario module logic is changed — this only aggregates what already ran.
"""

from __future__ import annotations

from typing import Any

from briarwood.pipeline.feedback_mixin import FeedbackReceiverMixin


SCENARIO_MODULE_NAMES = (
    "renovation_scenario",
    "teardown_scenario",
    "resale_scenario_scoped",
    "bull_base_bear",
    "hold_to_rent",
    "resale_scenario",
)


class ScenarioModelAdapter(FeedbackReceiverMixin):
    """Merge multiple scenario module outputs into one Scenario Model result."""

    name = "scenario_model"

    def aggregate(self, prior_outputs: dict[str, Any]) -> dict[str, Any]:
        """Consume `prior_outputs` (module_name → normalized result dict)."""

        scenarios: dict[str, dict[str, Any]] = {}
        confidences: list[float] = []
        warnings: list[str] = []

        for module_name in SCENARIO_MODULE_NAMES:
            output = prior_outputs.get(module_name)
            if not isinstance(output, dict):
                continue
            data = output.get("data") if isinstance(output.get("data"), dict) else output
            scenarios[module_name] = dict(data)
            conf = output.get("confidence")
            if isinstance(conf, (int, float)):
                confidences.append(float(conf))
            for w in output.get("warnings") or []:
                warnings.append(f"{module_name}:{w}")

        merged_confidence = (
            round(sum(confidences) / len(confidences), 3) if confidences else None
        )

        bull, base, bear = self._extract_value_fan(scenarios)

        return {
            "data": {
                "scenarios": scenarios,
                "scenario_count": len(scenarios),
                "bull_case_value": bull,
                "base_case_value": base,
                "bear_case_value": bear,
            },
            "confidence": merged_confidence,
            "warnings": warnings,
        }

    def _extract_value_fan(
        self, scenarios: dict[str, dict[str, Any]]
    ) -> tuple[float | None, float | None, float | None]:
        bbb = scenarios.get("bull_base_bear") or {}
        return (
            bbb.get("bull_case_value"),
            bbb.get("base_case_value"),
            bbb.get("bear_case_value"),
        )


__all__ = ["ScenarioModelAdapter", "SCENARIO_MODULE_NAMES"]
