"""Decision Agent adapter.

Consumes the synthesis payload from UnifiedIntelligenceAgent and produces
the final human-readable recommendation with ranked A/B/C scenarios,
risk flags, and chart instructions — the shape the architecture diagram's
Layer 06 "Decision Agent" calls for.
"""

from __future__ import annotations

from typing import Any

from briarwood.pipeline.session import PipelineSession


class DecisionAgent:
    name = "decision_agent"

    def decide(self, session: PipelineSession) -> dict[str, Any]:
        synthesis = session.synthesis or {}
        coherence = synthesis.get("coherence") or {}

        primary_rec = {
            "strategy": synthesis.get("stance", "unknown"),
            "rationale": synthesis.get("recommendation", ""),
            "confidence": synthesis.get("confidence", 0.0),
        }

        scenarios = self._rank_scenarios(session)
        risk_flags = self._collect_risk_flags(session, coherence)
        chart_instructions = list(synthesis.get("chart_routes") or [])

        decision = {
            "primary_recommendation": primary_rec,
            "scenarios": scenarios,
            "risk_flags": risk_flags,
            "chart_instructions": chart_instructions,
            "session_id": session.session_id,
        }
        session.decision = decision
        return decision

    def _rank_scenarios(self, session: PipelineSession) -> list[dict[str, Any]]:
        """Pull scenarios from the Scenario Model output when available."""

        scenario_result = session.model_outputs.get("scenario_model")
        if scenario_result is None:
            return _placeholder_scenarios(session)

        data = scenario_result.data
        bull = data.get("bull_case_value")
        base = data.get("base_case_value")
        bear = data.get("bear_case_value")

        ranked: list[dict[str, Any]] = []
        for label, value, tag in (
            ("A", base, "base_case"),
            ("B", bull, "bull_case"),
            ("C", bear, "bear_case"),
        ):
            if value is None:
                continue
            ranked.append({
                "label": label,
                "tag": tag,
                "value": value,
                "description": f"{tag.replace('_', ' ').title()} outcome",
            })

        if ranked:
            return ranked
        return _placeholder_scenarios(session)

    def _collect_risk_flags(
        self, session: PipelineSession, coherence: dict[str, Any]
    ) -> list[str]:
        flags: list[str] = list(coherence.get("conflicts") or [])
        risk = session.model_outputs.get("risk_model")
        if risk is not None:
            warnings = risk.warnings or []
            flags.extend(warnings)
            risk_data = risk.data
            if isinstance(risk_data.get("risk_flags"), list):
                flags.extend(risk_data["risk_flags"])
        security = session.model_outputs.get("security_model")
        if security is not None:
            score = security.data.get("score")
            if isinstance(score, (int, float)) and score < 50:
                flags.append("security_below_threshold")
        return list(dict.fromkeys(flags))


def _placeholder_scenarios(session: PipelineSession) -> list[dict[str, Any]]:
    stance = (session.synthesis or {}).get("stance", "unknown")
    return [
        {"label": "A", "tag": "base_case", "description": f"Primary path: {stance}"},
        {"label": "B", "tag": "alt_case", "description": "Alternative strategy"},
        {"label": "C", "tag": "pass_case", "description": "Walk away / wait"},
    ]


__all__ = ["DecisionAgent"]
