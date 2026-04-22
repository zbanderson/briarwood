import unittest

from briarwood.claims import Archetype


class ArchetypeEnumTests(unittest.TestCase):
    def test_verdict_with_comparison_value_is_stable(self) -> None:
        # Stability contract: the string value is stored/emitted and must not drift.
        self.assertEqual(Archetype.VERDICT_WITH_COMPARISON.value, "verdict_with_comparison")

    def test_enum_is_str_subclass(self) -> None:
        self.assertIsInstance(Archetype.VERDICT_WITH_COMPARISON, str)
        self.assertEqual(str(Archetype.VERDICT_WITH_COMPARISON.value), "verdict_with_comparison")

    def test_only_wedge_archetype_present(self) -> None:
        # Guard against accidentally enabling a reserved archetype before it's implemented.
        self.assertEqual({a.value for a in Archetype}, {"verdict_with_comparison"})


if __name__ == "__main__":
    unittest.main()
