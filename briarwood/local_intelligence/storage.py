from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from briarwood.local_intelligence.models import TownSignal


class LocalSignalStore(Protocol):
    """Persistence boundary for town-level signal history."""

    def load_town_signals(self, *, town: str, state: str) -> list[TownSignal]:
        ...

    def save_town_signals(self, *, town: str, state: str, signals: list[TownSignal]) -> None:
        ...


class JsonLocalSignalStore:
    """Simple file-backed store for persisted TownSignal records."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2] / "data" / "local_intelligence" / "signals"

    def load_town_signals(self, *, town: str, state: str) -> list[TownSignal]:
        path = self._town_path(town=town, state=state)
        if not path.exists():
            return []
        payload = json.loads(path.read_text())
        return [TownSignal.model_validate(item) for item in payload.get("signals", [])]

    def save_town_signals(self, *, town: str, state: str, signals: list[TownSignal]) -> None:
        path = self._town_path(town=town, state=state)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "town": town,
            "state": state,
            "signals": [signal.model_dump(mode="json") for signal in signals],
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    def _town_path(self, *, town: str, state: str) -> Path:
        slug = _slugify(f"{town}-{state}")
        return self.root / f"{slug}.json"


def _slugify(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")
