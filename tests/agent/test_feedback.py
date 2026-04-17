"""Untracked-turn logger — signal classification and jsonl append."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from briarwood.agent import feedback as feedback_mod
from briarwood.agent.router import AnswerType, RouterDecision


def _decision(reason: str = "llm classify", confidence: float = 0.6) -> RouterDecision:
    return RouterDecision(
        answer_type=AnswerType.LOOKUP,
        confidence=confidence,
        target_refs=["526-west-end-ave"],
        reason=reason,
    )


class LogTurnTests(unittest.TestCase):
    def _run(self, **kwargs):
        with TemporaryDirectory() as tmp:
            log_dir = Path(tmp) / "agent_feedback"
            with patch.object(feedback_mod, "LOG_DIR", log_dir), patch.object(
                feedback_mod, "LOG_PATH", log_dir / "untracked.jsonl"
            ):
                signals = feedback_mod.log_turn(**kwargs)
                path = log_dir / "untracked.jsonl"
                if path.exists():
                    records = [json.loads(line) for line in path.read_text().splitlines()]
                else:
                    records = []
            return signals, records

    def test_llm_fallback_signal_fires_when_llm_unavailable(self) -> None:
        signals, records = self._run(
            text="how many beds?",
            decision=_decision(reason="cache", confidence=0.9),
            response="3 beds, 2 baths",
            extra={"llm_used": False},
        )
        self.assertIn("llm_fallback", signals)
        self.assertEqual(len(records), 1)
        self.assertIn("llm_fallback", records[0]["signals"])

    def test_no_signal_when_llm_used_and_high_confidence(self) -> None:
        signals, records = self._run(
            text="how many beds?",
            decision=_decision(reason="cache", confidence=0.9),
            response="3 beds, 2 baths",
            extra={"llm_used": True},
        )
        self.assertEqual(signals, [])
        self.assertEqual(records, [])

    def test_handler_no_help_signal(self) -> None:
        signals, _ = self._run(
            text="what's this?",
            decision=_decision(reason="cache", confidence=0.9),
            response="Which property should I look at?",
            extra={"llm_used": True},
        )
        self.assertIn("handler_no_help", signals)

    def test_low_confidence_signal(self) -> None:
        signals, _ = self._run(
            text="uhh",
            decision=_decision(reason="cache", confidence=0.3),
            response="ok",
            extra={"llm_used": True},
        )
        self.assertIn("low_confidence", signals)


if __name__ == "__main__":
    unittest.main()
