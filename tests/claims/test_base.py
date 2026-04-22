import unittest

from pydantic import ValidationError

from briarwood.claims import (
    Caveat,
    Confidence,
    NextQuestion,
    Provenance,
    SurfacedInsight,
)


class ConfidenceTests(unittest.TestCase):
    def test_from_score_band_thresholds(self) -> None:
        self.assertEqual(Confidence.from_score(0.95).band, "high")
        self.assertEqual(Confidence.from_score(0.90).band, "high")
        self.assertEqual(Confidence.from_score(0.89).band, "medium")
        self.assertEqual(Confidence.from_score(0.70).band, "medium")
        self.assertEqual(Confidence.from_score(0.69).band, "low")
        self.assertEqual(Confidence.from_score(0.50).band, "low")
        self.assertEqual(Confidence.from_score(0.49).band, "very_low")
        self.assertEqual(Confidence.from_score(0.0).band, "very_low")

    def test_score_clamped_to_range(self) -> None:
        with self.assertRaises(ValidationError):
            Confidence(score=1.5, band="high")
        with self.assertRaises(ValidationError):
            Confidence(score=-0.1, band="very_low")

    def test_band_must_be_known_literal(self) -> None:
        with self.assertRaises(ValidationError):
            Confidence(score=0.5, band="weird")  # type: ignore[arg-type]


class ProvenanceTests(unittest.TestCase):
    def test_defaults_are_empty_lists_not_shared(self) -> None:
        a = Provenance()
        b = Provenance()
        a.models_consulted.append("x")
        self.assertEqual(b.models_consulted, [])


class CaveatTests(unittest.TestCase):
    def test_severity_must_be_known(self) -> None:
        Caveat(text="ok", severity="info", source="module")
        with self.assertRaises(ValidationError):
            Caveat(text="ok", severity="critical", source="module")  # type: ignore[arg-type]


class NextQuestionTests(unittest.TestCase):
    def test_requires_both_fields(self) -> None:
        with self.assertRaises(ValidationError):
            NextQuestion(text="what")  # type: ignore[call-arg]


class SurfacedInsightTests(unittest.TestCase):
    def test_supporting_fields_defaults_empty(self) -> None:
        insight = SurfacedInsight(headline="h", reason="r", supporting_fields=[])
        self.assertEqual(insight.supporting_fields, [])


if __name__ == "__main__":
    unittest.main()
