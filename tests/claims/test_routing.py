import unittest

from briarwood.agent.router import AnswerType
from briarwood.claims import Archetype
from briarwood.claims.routing import map_to_archetype


class RoutingTests(unittest.TestCase):
    def test_decision_plus_pinned_routes_to_verdict_with_comparison(self) -> None:
        result = map_to_archetype(
            AnswerType.DECISION, question_focus=None, has_pinned_listing=True
        )
        self.assertEqual(result, Archetype.VERDICT_WITH_COMPARISON)

    def test_lookup_plus_pinned_routes_to_verdict_with_comparison(self) -> None:
        result = map_to_archetype(
            AnswerType.LOOKUP, question_focus=["price"], has_pinned_listing=True
        )
        self.assertEqual(result, Archetype.VERDICT_WITH_COMPARISON)

    def test_decision_without_pinned_returns_none(self) -> None:
        result = map_to_archetype(
            AnswerType.DECISION, question_focus=None, has_pinned_listing=False
        )
        self.assertIsNone(result)

    def test_lookup_without_pinned_returns_none(self) -> None:
        result = map_to_archetype(
            AnswerType.LOOKUP, question_focus=None, has_pinned_listing=False
        )
        self.assertIsNone(result)

    def test_unsupported_answer_types_return_none_even_when_pinned(self) -> None:
        for answer_type in (
            AnswerType.COMPARISON,
            AnswerType.SEARCH,
            AnswerType.RESEARCH,
            AnswerType.VISUALIZE,
            AnswerType.RENT_LOOKUP,
            AnswerType.MICRO_LOCATION,
            AnswerType.PROJECTION,
            AnswerType.RISK,
            AnswerType.EDGE,
            AnswerType.STRATEGY,
            AnswerType.BROWSE,
            AnswerType.CHITCHAT,
        ):
            result = map_to_archetype(
                answer_type, question_focus=None, has_pinned_listing=True
            )
            self.assertIsNone(
                result,
                msg=f"{answer_type} should not route to an archetype in the wedge",
            )

    def test_question_focus_does_not_change_result_in_wedge(self) -> None:
        # Forward-compat param: wedge ignores it, but we pin behavior so a
        # future archetype can't silently start branching on it.
        for focus in (None, [], ["price"], ["price", "condition"]):
            self.assertEqual(
                map_to_archetype(
                    AnswerType.DECISION,
                    question_focus=focus,
                    has_pinned_listing=True,
                ),
                Archetype.VERDICT_WITH_COMPARISON,
                msg=f"focus={focus}",
            )
            self.assertIsNone(
                map_to_archetype(
                    AnswerType.COMPARISON,
                    question_focus=focus,
                    has_pinned_listing=True,
                ),
                msg=f"focus={focus}",
            )


if __name__ == "__main__":
    unittest.main()
