"""Feedback return-path interface for specialist models.

Provides a default no-op `receive_feedback` method so every model has a
uniform hook the feedback loop can call. Models can override to store
labeled signals for eventual fine-tuning; default is a safe no-op.
"""

from __future__ import annotations

from typing import Any


class FeedbackReceiverMixin:
    """Mix into any specialist module to expose a feedback return path."""

    def receive_feedback(self, session_id: str, signal: dict[str, Any]) -> None:
        """Accept a feedback signal from a scored session. Default: no-op.

        Signal shape (minimum):
            {"explicit": "accepted" | "rejected" | "modified" | None,
             "outcome": "aligned" | "diverged" | None,
             "weight": float}
        """

        return None


def attach_feedback_interface(module: Any) -> Any:
    """Attach a no-op `receive_feedback` to any existing module instance.

    Lets us wire the interface onto legacy modules without touching their
    class definitions.
    """

    if not hasattr(module, "receive_feedback"):
        def _noop(session_id: str, signal: dict[str, Any]) -> None:
            return None
        module.receive_feedback = _noop  # type: ignore[attr-defined]
    return module


__all__ = ["FeedbackReceiverMixin", "attach_feedback_interface"]
