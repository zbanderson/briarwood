"""Minimum viable memory for Phase A.

One "current property" + the last N turns as plain text. Persisted to
data/agent_sessions/{session_id}.json so a follow-up invocation can rehydrate.
No vector store, no summarization, no background agent.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

SESSION_DIR = Path("data/agent_sessions")
MAX_TURNS_RETAINED = 12


@dataclass
class Turn:
    user: str
    assistant: str
    answer_type: str


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    current_property_id: str | None = None
    current_live_listing: dict[str, object] | None = None
    last_live_listing_results: list[dict[str, object]] = field(default_factory=list)
    current_search_context: dict[str, object] | None = None
    search_context: dict[str, object] | None = None
    selected_search_result: dict[str, object] | None = None
    promoted_property_id: str | None = None
    promotion_error: str | None = None
    last_answer_contract: str | None = None
    last_analysis_mode: str | None = None
    last_decision_view: dict[str, object] | None = None
    last_projection_view: dict[str, object] | None = None
    last_comparison_view: list[dict[str, object]] | None = None
    last_town_summary: dict[str, object] | None = None
    last_comps_preview: dict[str, object] | None = None
    last_risk_view: dict[str, object] | None = None
    last_value_thesis_view: dict[str, object] | None = None
    last_strategy_view: dict[str, object] | None = None
    last_rent_outlook_view: dict[str, object] | None = None
    last_research_view: dict[str, object] | None = None
    last_trust_view: dict[str, object] | None = None
    last_presentation_payload: dict[str, object] | None = None
    last_surface_narrative: str | None = None
    last_visual_advice: dict[str, object] | None = None
    last_verifier_report: dict[str, object] | None = None
    turns: list[Turn] = field(default_factory=list)

    def clear_response_views(self) -> None:
        """Clear per-turn structured render state before running a new turn.

        This prevents stale cards and charts from a previous response leaking
        into the next streamed assistant message. Conversation continuity still
        lives on `current_property_id`, search context, and prior turns.
        """
        self.last_answer_contract = None
        self.last_analysis_mode = None
        self.last_decision_view = None
        self.last_projection_view = None
        self.last_comparison_view = None
        self.last_town_summary = None
        self.last_comps_preview = None
        self.last_risk_view = None
        self.last_value_thesis_view = None
        self.last_strategy_view = None
        self.last_rent_outlook_view = None
        self.last_research_view = None
        self.last_trust_view = None
        self.last_presentation_payload = None
        self.last_surface_narrative = None
        self.last_visual_advice = None
        self.last_verifier_report = None

    def record(self, user: str, assistant: str, answer_type: str) -> None:
        self.turns.append(Turn(user=user, assistant=assistant, answer_type=answer_type))
        if len(self.turns) > MAX_TURNS_RETAINED:
            self.turns = self.turns[-MAX_TURNS_RETAINED:]

    def path(self) -> Path:
        return SESSION_DIR / f"{self.session_id}.json"

    def save(self) -> None:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        self.path().write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, session_id: str) -> "Session":
        path = SESSION_DIR / f"{session_id}.json"
        data = json.loads(path.read_text())
        turns = [Turn(**t) for t in data.get("turns", [])]
        return cls(
            session_id=data["session_id"],
            current_property_id=data.get("current_property_id"),
            current_live_listing=data.get("current_live_listing"),
            last_live_listing_results=list(data.get("last_live_listing_results") or []),
            current_search_context=data.get("current_search_context") or data.get("search_context"),
            search_context=data.get("search_context"),
            selected_search_result=data.get("selected_search_result"),
            promoted_property_id=data.get("promoted_property_id"),
            promotion_error=data.get("promotion_error"),
            last_answer_contract=data.get("last_answer_contract"),
            last_analysis_mode=data.get("last_analysis_mode"),
            last_decision_view=data.get("last_decision_view"),
            last_projection_view=data.get("last_projection_view"),
            last_comparison_view=data.get("last_comparison_view"),
            last_town_summary=data.get("last_town_summary"),
            last_comps_preview=data.get("last_comps_preview"),
            last_risk_view=data.get("last_risk_view"),
            last_value_thesis_view=data.get("last_value_thesis_view"),
            last_strategy_view=data.get("last_strategy_view"),
            last_rent_outlook_view=data.get("last_rent_outlook_view"),
            last_research_view=data.get("last_research_view"),
            last_trust_view=data.get("last_trust_view"),
            last_presentation_payload=data.get("last_presentation_payload"),
            last_surface_narrative=data.get("last_surface_narrative"),
            last_visual_advice=data.get("last_visual_advice"),
            last_verifier_report=data.get("last_verifier_report"),
            turns=turns,
        )
