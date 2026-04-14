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
    turns: list[Turn] = field(default_factory=list)

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
            turns=turns,
        )
