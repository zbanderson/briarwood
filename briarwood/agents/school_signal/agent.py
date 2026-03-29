from __future__ import annotations

from briarwood.agents.school_signal.schemas import SchoolSignalInput, SchoolSignalOutput


class SchoolSignalAgent:
    """Build a conservative Briarwood school signal from public-school proxy inputs."""

    _WEIGHTS = {
        "achievement_index": 0.30,
        "growth_index": 0.25,
        "readiness_index": 0.15,
        "absenteeism": 0.15,
        "student_teacher_ratio": 0.15,
    }

    def evaluate(self, payload: SchoolSignalInput | dict[str, object]) -> SchoolSignalOutput:
        inputs = payload if isinstance(payload, SchoolSignalInput) else SchoolSignalInput.model_validate(payload)
        assumptions: list[str] = [
            "Briarwood school signal is a local proxy built from public-source review, not an official ranking."
        ]
        unsupported_claims: list[str] = []

        components = {
            "achievement_index": self._normalize_index(inputs.achievement_index),
            "growth_index": self._normalize_index(inputs.growth_index),
            "readiness_index": self._normalize_index(inputs.readiness_index),
            "absenteeism": self._normalize_absenteeism(inputs.chronic_absenteeism_pct),
            "student_teacher_ratio": self._normalize_student_teacher_ratio(inputs.student_teacher_ratio),
        }

        total_weight = sum(self._WEIGHTS.values())
        used_weight = 0.0
        weighted_score = 0.0
        for key, weight in self._WEIGHTS.items():
            value = components[key]
            if value is None:
                continue
            used_weight += weight
            weighted_score += weight * value

        if used_weight == 0:
            return SchoolSignalOutput(
                school_signal=0.0,
                confidence=0.0,
                summary=f"{inputs.geography_name}, {inputs.state} lacks enough school data for a Briarwood school signal.",
                assumptions=assumptions,
                unsupported_claims=["School signal could not be derived because no usable school proxy inputs were available."],
            )

        normalized_score = weighted_score / used_weight
        school_signal = round(normalized_score * 10.0, 1)
        completeness = used_weight / total_weight
        coverage = inputs.district_coverage if inputs.district_coverage is not None else 0.75
        review_quality = inputs.source_review_quality if inputs.source_review_quality is not None else 0.65
        confidence = round(min(0.88, completeness * coverage * review_quality + 0.10), 2)

        if inputs.growth_index is None:
            unsupported_claims.append("Student growth data is not fully reflected in the current school proxy.")
        if inputs.readiness_index is None:
            unsupported_claims.append("College or postsecondary readiness data is not fully reflected in the current school proxy.")
        if inputs.district_coverage is not None and inputs.district_coverage < 0.9:
            unsupported_claims.append("School signal is only partial-coverage for the town and should be treated cautiously.")
        if confidence < 0.65:
            assumptions.append("Confidence is reduced because the school proxy still depends on partial manual review.")
        if inputs.refresh_frequency_days is not None and inputs.as_of is not None:
            assumptions.append(
                f"School proxy was last reviewed on {inputs.as_of} and should be refreshed about every {inputs.refresh_frequency_days} days."
            )

        label = self._label(school_signal)
        summary = f"{inputs.geography_name}, {inputs.state} shows {label} school support in Briarwood's local proxy at {school_signal:.1f}/10."
        return SchoolSignalOutput(
            school_signal=school_signal,
            confidence=confidence,
            summary=summary,
            assumptions=assumptions,
            unsupported_claims=unsupported_claims,
        )

    def _normalize_index(self, value: float | None) -> float | None:
        if value is None:
            return None
        return max(0.0, min(value / 100.0, 1.0))

    def _normalize_absenteeism(self, value: float | None) -> float | None:
        if value is None:
            return None
        if value <= 5:
            return 0.95
        if value <= 10:
            return 0.78
        if value <= 15:
            return 0.60
        if value <= 20:
            return 0.40
        return 0.20

    def _normalize_student_teacher_ratio(self, value: float | None) -> float | None:
        if value is None:
            return None
        if value <= 11:
            return 0.92
        if value <= 13:
            return 0.82
        if value <= 15:
            return 0.68
        if value <= 17:
            return 0.50
        return 0.32

    def _label(self, signal: float) -> str:
        if signal >= 8.0:
            return "strong"
        if signal >= 6.5:
            return "supportive"
        if signal >= 5.0:
            return "mixed"
        return "limited"
