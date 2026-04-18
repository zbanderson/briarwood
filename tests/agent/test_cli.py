from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from briarwood.agent.cli import main
from briarwood.agent.router import AnswerType, RouterDecision


class CliTests(unittest.TestCase):
    def test_keyboard_interrupt_during_dispatch_exits_cleanly(self) -> None:
        stdout = io.StringIO()
        decision = RouterDecision(
            AnswerType.DECISION, confidence=0.7, target_refs=["pid"], reason="test"
        )
        with patch("briarwood.agent.cli.default_client", return_value=None), patch(
            "builtins.input", side_effect=["should I buy this?"]
        ), patch(
            "briarwood.agent.cli.classify", return_value=decision
        ), patch(
            "briarwood.agent.cli.contextualize_decision", return_value=decision
        ), patch(
            "briarwood.agent.cli.dispatch", side_effect=KeyboardInterrupt
        ), patch(
            "sys.stdout", stdout
        ):
            exit_code = main([])

        self.assertEqual(exit_code, 0)
        self.assertIn("Briarwood chat", stdout.getvalue())
        self.assertIn("[route: decision", stdout.getvalue())
        self.assertNotIn("Traceback", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
