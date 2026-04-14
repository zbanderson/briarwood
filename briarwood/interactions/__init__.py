"""Phase 4: cross-model interaction bridges.

This package replaces silo behavior with explicit modulation rules. Each
bridge is a pure function that reads two or more ``ModulePayload`` dicts and
emits a ``BridgeRecord`` describing the adjustment it recommends, along with
the reasoning that produced it.

Bridges do **not** mutate module payloads in place. They produce an
``InteractionTrace`` that the synthesizer consumes in Phase 5.
"""

from briarwood.interactions.bridge import (
    BridgeRecord,
    InteractionTrace,
    ModuleOutputs,
)
from briarwood.interactions.registry import run_all_bridges

__all__ = [
    "BridgeRecord",
    "InteractionTrace",
    "ModuleOutputs",
    "run_all_bridges",
]
