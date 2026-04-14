"""Briarwood conversational agent (CLI-first).

Phase A: minimal single-shot assistant. One classify step + up to two tool
calls per turn. No autonomous multi-step loop.

Entry point: ``python -m briarwood.agent``.
"""

from briarwood.agent.router import AnswerType, RouterDecision, classify
from briarwood.agent.session import Session

__all__ = ["AnswerType", "RouterDecision", "Session", "classify"]
