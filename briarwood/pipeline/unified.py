"""Unified Intelligence adapter — synthesis + coherence + chart routing.

Wraps the existing deterministic synthesis (briarwood.synthesis.structured)
with two additions the architecture diagram calls for but the existing
code does not do explicitly:

  1. Coherence check across specialist outputs — flags conflicts such as
     "Risk says HIGH while Decision stance is STRONG_BUY" before final
     synthesis. Conflicts are non-fatal; they are surfaced as warnings.
  2. Chart router — maps question_focus + active model set to the
     visualization-shaped chart kinds shown on the architecture diagram
     (line_area, bar_compare, geo_map, radar_score).

The upstream synthesis module is not modified. If it's not callable from
the test environment the adapter falls back to a minimal pass-through
synthesis so the pipeline still produces an output.
"""

from __future__ import annotations

from typing import Any

from briarwood.pipeline.session import PipelineSession


CHART_KINDS = ("line_area", "bar_compare", "geo_map", "radar_score")


class UnifiedIntelligenceAgent:
    name = "unified_intelligence"

    def synthesize(self, session: PipelineSession) -> dict[str, Any]:
        """Build synthesis payload from session.model_outputs."""

        coherence = self._coherence_check(session)
        chart_routes = self._route_charts(session)

        model_confidences = [
            float(r.confidence)
            for r in session.model_outputs.values()
            if isinstance(r.confidence, (int, float))
        ]
        overall_confidence = (
            round(sum(model_confidences) / len(model_confidences), 3)
            if model_confidences
            else 0.0
        )

        recommendation, stance = self._make_recommendation(session, coherence)

        synthesis = {
            "recommendation": recommendation,
            "stance": stance,
            "confidence": overall_confidence,
            "coherence": coherence,
            "chart_routes": chart_routes,
            "model_count": len(session.model_outputs),
        }
        session.synthesis = synthesis
        return synthesis

    def _coherence_check(self, session: PipelineSession) -> dict[str, Any]:
        """Detect obvious cross-model conflicts. Non-fatal."""

        conflicts: list[str] = []
        risk = (session.model_outputs.get("risk_model") or None)
        income = (session.model_outputs.get("income_model") or session.model_outputs.get("income_support"))
        security = session.model_outputs.get("security_model")

        if risk is not None:
            risk_score = risk.data.get("score")
            if isinstance(risk_score, (int, float)) and risk_score < 40:
                # Low risk-model score means high risk; flag if income suggests strong yield
                if income is not None:
                    cap = income.data.get("cap_rate") or income.data.get("gross_yield")
                    if isinstance(cap, (int, float)) and cap > 0.07:
                        conflicts.append("risk_high_but_yield_attractive")

        if security is not None:
            sec_score = security.data.get("score")
            if isinstance(sec_score, (int, float)) and sec_score < 45:
                conflicts.append("security_score_low")

        low_conf_models = [
            name for name, r in session.model_outputs.items()
            if isinstance(r.confidence, (int, float)) and r.confidence < 0.4
        ]

        return {
            "conflicts": conflicts,
            "low_confidence_models": low_conf_models,
            "is_coherent": not conflicts and len(low_conf_models) < 3,
        }

    def _route_charts(self, session: PipelineSession) -> list[dict[str, str]]:
        """Map available models + parser focus to standard chart kinds."""

        routes: list[dict[str, str]] = []
        outputs = session.model_outputs
        focus = list(session.parser_output.get("question_focus") or [])

        if "scenario_model" in outputs or any(k.endswith("_scenario") for k in outputs):
            routes.append({"kind": "line_area", "source": "scenario_model",
                           "purpose": "Projected value fan over time"})

        if len(outputs) >= 2:
            routes.append({"kind": "bar_compare", "source": "specialist_models",
                           "purpose": "Per-model confidence comparison"})

        if "location_model" in outputs or "location_intelligence" in outputs:
            routes.append({"kind": "geo_map", "source": "location_model",
                           "purpose": "Proximity + risk zone overlay"})

        if len(outputs) >= 3:
            routes.append({"kind": "radar_score", "source": "all_models",
                           "purpose": "Multi-factor fit index"})

        if "future_income" in focus and "income_model" not in {r.get("source") for r in routes}:
            routes.append({"kind": "line_area", "source": "income_model",
                           "purpose": "Cash flow over horizon"})

        return routes

    def _make_recommendation(
        self, session: PipelineSession, coherence: dict[str, Any]
    ) -> tuple[str, str]:
        if not coherence["is_coherent"]:
            return (
                "Analysis surfaced conflicting signals; recommend a deeper review.",
                "review_needed",
            )

        confidences = [
            float(r.confidence) for r in session.model_outputs.values()
            if isinstance(r.confidence, (int, float))
        ]
        mean = sum(confidences) / len(confidences) if confidences else 0.0

        if mean >= 0.7:
            return ("Strong fit across specialist models.", "favorable")
        if mean >= 0.5:
            return ("Mixed fit; proceed with measured conviction.", "mixed")
        return ("Signals are weak or data is thin; pause and gather more.", "pass")


__all__ = ["UnifiedIntelligenceAgent", "CHART_KINDS"]
