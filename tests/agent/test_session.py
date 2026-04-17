"""Session state — turn retention and persistence round-trip."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from briarwood.agent import session as session_mod
from briarwood.agent.session import MAX_TURNS_RETAINED, Session, Turn


class SessionStateTests(unittest.TestCase):
    def test_defaults_fresh_session(self) -> None:
        s = Session()
        self.assertEqual(len(s.session_id), 12)
        self.assertIsNone(s.current_property_id)
        self.assertEqual(s.turns, [])

    def test_record_appends_turn(self) -> None:
        s = Session()
        s.record("hi", "hello", "chitchat")
        self.assertEqual(len(s.turns), 1)
        self.assertEqual(s.turns[0], Turn(user="hi", assistant="hello", answer_type="chitchat"))

    def test_record_truncates_to_max_turns(self) -> None:
        """Window clamps at MAX_TURNS_RETAINED; oldest turns drop off the front."""
        s = Session()
        for i in range(MAX_TURNS_RETAINED + 5):
            s.record(f"u{i}", f"a{i}", "lookup")
        self.assertEqual(len(s.turns), MAX_TURNS_RETAINED)
        self.assertEqual(s.turns[0].user, "u5")  # first 5 dropped
        self.assertEqual(s.turns[-1].user, f"u{MAX_TURNS_RETAINED + 4}")


class SessionPersistenceTests(unittest.TestCase):
    def test_save_then_load_round_trip(self) -> None:
        with TemporaryDirectory() as tmp:
            with patch.object(session_mod, "SESSION_DIR", Path(tmp)):
                s = Session(current_property_id="526-west-end-ave")
                s.record("hi", "hello", "chitchat")
                s.record("should i buy?", "analyzing...", "decision")
                s.save()

                loaded = Session.load(s.session_id)

            self.assertEqual(loaded.session_id, s.session_id)
            self.assertEqual(loaded.current_property_id, "526-west-end-ave")
            self.assertEqual(len(loaded.turns), 2)
            self.assertEqual(loaded.turns[0].user, "hi")
            self.assertEqual(loaded.turns[1].answer_type, "decision")


if __name__ == "__main__":
    unittest.main()
