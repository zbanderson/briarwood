"""Per-criterion check functions.

Each function takes (spec, fixture, invoke_fn) and returns a CriterionResult.
Kept in one file so the scoring logic is readable in one place.
"""

from __future__ import annotations

import copy
from typing import Any, Callable

from briarwood.eval.model_quality.types import (
    CriterionResult,
    Fixture,
    ModelSpec,
    Sensitivity,
)


InvokeFn = Callable[[Any], dict[str, Any]]


def _data(output: dict[str, Any]) -> dict[str, Any]:
    data = output.get("data") if isinstance(output, dict) else None
    return data if isinstance(data, dict) else {}


def _get_nested(data: dict[str, Any], field: str) -> Any:
    if field in data:
        return data[field]
    for v in data.values():
        if isinstance(v, dict) and field in v:
            return v[field]
    return None


# ---------- Accuracy ----------

def check_accuracy(spec: ModelSpec, fixture: Fixture) -> CriterionResult:
    """Model output fields land inside declared numeric bands."""

    try:
        output = spec.invoke(fixture.property_input)
    except Exception as exc:
        return CriterionResult("accuracy", False, 0.0, [f"invoke error: {exc}"])

    data = _data(output)
    details: list[str] = []
    total = 0
    hits = 0
    for field, (lo, hi) in spec.numeric_bounds.items():
        value = _get_nested(data, field)
        total += 1
        if not isinstance(value, (int, float)):
            details.append(f"{field}: missing or non-numeric")
            continue
        if lo <= value <= hi:
            hits += 1
            details.append(f"{field}={value:.4g} ✓ within [{lo}, {hi}]")
        else:
            details.append(f"{field}={value:.4g} ✗ outside [{lo}, {hi}]")

    score = (hits / total) if total else 0.0
    return CriterionResult("accuracy", score >= 0.75, round(score, 3), details)


# ---------- Consistency ----------

def check_consistency(spec: ModelSpec, fixture: Fixture) -> CriterionResult:
    """Trivial perturbations produce near-identical outputs."""

    try:
        base = _data(spec.invoke(fixture.property_input))
    except Exception as exc:
        return CriterionResult("consistency", False, 0.0, [f"invoke error: {exc}"])

    perturbed_inputs = _perturb_trivially(fixture.property_input)
    passes = 0
    total = 0
    details: list[str] = []

    for label, perturbed in perturbed_inputs:
        try:
            alt = _data(spec.invoke(perturbed))
        except Exception as exc:
            details.append(f"{label}: invoke error {exc}")
            continue
        for field in spec.numeric_bounds:
            total += 1
            b = _get_nested(base, field)
            a = _get_nested(alt, field)
            if not isinstance(b, (int, float)) or not isinstance(a, (int, float)):
                details.append(f"{label}/{field}: non-numeric")
                continue
            rel = abs(a - b) / max(abs(b), 1e-9)
            if rel <= 0.02:  # within 2%
                passes += 1
                details.append(f"{label}/{field}: Δ={rel:.3%} ✓")
            else:
                details.append(f"{label}/{field}: Δ={rel:.3%} ✗ (threshold 2%)")

    score = (passes / total) if total else 1.0
    return CriterionResult("consistency", score >= 0.9, round(score, 3), details)


def _perturb_trivially(property_input: Any) -> list[tuple[str, Any]]:
    """Return [(label, perturbed_input)] with trivial changes."""

    out: list[tuple[str, Any]] = []
    try:
        clone = property_input.model_copy(deep=True)
    except AttributeError:
        clone = copy.deepcopy(property_input)

    # Tiny price nudge (+0.5%) — shouldn't meaningfully change any output
    price = getattr(clone, "purchase_price", None)
    if isinstance(price, (int, float)):
        clone2 = _clone(clone)
        clone2.purchase_price = round(price * 1.005, 2)
        out.append(("price_+0.5%", clone2))

    # Whitespace on address
    addr = getattr(clone, "address", None)
    if isinstance(addr, str):
        clone3 = _clone(clone)
        clone3.address = f"  {addr}  "
        out.append(("address_whitespace", clone3))
    return out


def _clone(obj: Any) -> Any:
    try:
        return obj.model_copy(deep=True)
    except AttributeError:
        return copy.deepcopy(obj)


# ---------- Sensitivity ----------

def check_sensitivity(spec: ModelSpec, fixture: Fixture) -> CriterionResult:
    """Meaningful input changes move outputs in the expected direction."""

    if not spec.sensitivities:
        return CriterionResult("sensitivity", True, 1.0, ["no sensitivities declared"])

    try:
        base = _data(spec.invoke(fixture.property_input))
    except Exception as exc:
        return CriterionResult("sensitivity", False, 0.0, [f"invoke error: {exc}"])

    passes = 0
    total = 0
    details: list[str] = []

    for sens in spec.sensitivities:
        total += 1
        perturbed = _apply_sensitivity(fixture.property_input, sens)
        if perturbed is None:
            details.append(f"{sens.label or sens.input_field}: input missing, skipped")
            total -= 1
            continue
        try:
            alt = _data(spec.invoke(perturbed))
        except Exception as exc:
            details.append(f"{sens.label or sens.input_field}: invoke error {exc}")
            continue

        b = _get_nested(base, sens.output_field)
        a = _get_nested(alt, sens.output_field)
        if not isinstance(b, (int, float)) or not isinstance(a, (int, float)):
            details.append(f"{sens.label or sens.input_field}→{sens.output_field}: non-numeric")
            continue

        move_rel = (a - b) / max(abs(b), 1e-9)
        ok = _sensitivity_matches(sens, move_rel)
        if ok:
            passes += 1
            details.append(
                f"{sens.label or sens.input_field}→{sens.output_field}: "
                f"{move_rel:+.2%} ({sens.expected_direction}) ✓"
            )
        else:
            details.append(
                f"{sens.label or sens.input_field}→{sens.output_field}: "
                f"{move_rel:+.2%} ✗ expected {sens.expected_direction} "
                f"(min {sens.min_move_pct:.0%})"
            )

    score = (passes / total) if total else 1.0
    return CriterionResult("sensitivity", score >= 0.8, round(score, 3), details)


def _apply_sensitivity(property_input: Any, sens: Sensitivity) -> Any | None:
    clone = _clone(property_input)
    if not hasattr(clone, sens.input_field):
        return None
    current = getattr(clone, sens.input_field)
    delta = sens.delta
    if isinstance(delta, (int, float)) and isinstance(current, (int, float)):
        new_value = current * (1.0 + delta) if abs(delta) < 10 else current + delta
    else:
        new_value = delta  # categorical replacement
    try:
        setattr(clone, sens.input_field, new_value)
    except Exception:
        return None
    return clone


def _sensitivity_matches(sens: Sensitivity, move_rel: float) -> bool:
    if sens.expected_direction == "any":
        return abs(move_rel) >= sens.min_move_pct
    if sens.expected_direction == "unchanged":
        return abs(move_rel) <= max(sens.min_move_pct, 0.01)
    if sens.expected_direction == "up":
        return move_rel >= max(sens.min_move_pct, 0.0)
    if sens.expected_direction == "down":
        return move_rel <= -max(sens.min_move_pct, 0.0)
    return False


# ---------- Explainability ----------

def check_explainability(spec: ModelSpec, fixture: Fixture) -> CriterionResult:
    """Rationale / feature attribution fields are present and non-empty."""

    try:
        output = spec.invoke(fixture.property_input)
    except Exception as exc:
        return CriterionResult("explainability", False, 0.0, [f"invoke error: {exc}"])

    data = _data(output)
    warnings = output.get("warnings") if isinstance(output, dict) else []

    fields = list(spec.explainability_fields) or ["notes", "rationale", "warnings"]
    hits = 0
    total = len(fields)
    details: list[str] = []
    for field in fields:
        value = _get_nested(data, field)
        if value is None and field == "warnings":
            value = warnings
        if isinstance(value, str) and value.strip():
            hits += 1
            details.append(f"{field}: present ({len(value)} chars)")
        elif isinstance(value, (list, dict)) and value:
            hits += 1
            details.append(f"{field}: present ({len(value)} entries)")
        else:
            details.append(f"{field}: absent or empty")

    score = hits / total if total else 0.0
    return CriterionResult("explainability", score >= 0.5, round(score, 3), details)


# ---------- Decision usefulness ----------

def check_decision_usefulness(spec: ModelSpec, fixture: Fixture) -> CriterionResult:
    """Output exposes fields that answer the 4 decision questions."""

    try:
        output = spec.invoke(fixture.property_input)
    except Exception as exc:
        return CriterionResult("decision_usefulness", False, 0.0, [f"invoke error: {exc}"])

    data = _data(output)
    dq = spec.decision_questions
    questions = {
        "should_i_buy": dq.should_i_buy,
        "what_could_go_wrong": dq.what_could_go_wrong,
        "where_is_value": dq.where_is_value,
        "what_path": dq.what_path,
    }

    details: list[str] = []
    total = 0
    hits = 0
    for question, fields in questions.items():
        if not fields:
            continue
        total += 1
        answered = [f for f in fields if _is_actionable(_get_nested(data, f))]
        if answered:
            hits += 1
            details.append(f"{question}: ✓ via {answered}")
        else:
            details.append(f"{question}: ✗ none of {fields} actionable")

    score = hits / total if total else 0.0
    return CriterionResult("decision_usefulness", score >= 0.75, round(score, 3), details)


def _is_actionable(value: Any) -> bool:
    """Has units/direction/magnitude — i.e., a real answer not a null placeholder."""

    if value is None:
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


# ---------- Trust calibration ----------

def check_trust_calibration(spec: ModelSpec, fixture: Fixture) -> CriterionResult:
    """Progressively thinner inputs should drop confidence (monotonically-ish)."""

    try:
        full_output = spec.invoke(fixture.property_input)
    except Exception as exc:
        return CriterionResult("trust_calibration", False, 0.0, [f"invoke error: {exc}"])

    full_conf = full_output.get("confidence") if isinstance(full_output, dict) else None
    if not isinstance(full_conf, (int, float)):
        return CriterionResult(
            "trust_calibration", False, 0.0,
            ["model does not return a numeric confidence"],
        )

    details: list[str] = [f"full_inputs confidence={full_conf:.3f}"]
    confidences = [float(full_conf)]
    passes = 0
    total = 0
    for field in spec.trust_drop_fields:
        stripped = _clone(fixture.property_input)
        if not hasattr(stripped, field):
            continue
        try:
            setattr(stripped, field, None)
        except Exception:
            continue
        try:
            thin = spec.invoke(stripped)
        except Exception as exc:
            details.append(f"drop {field}: invoke error {exc}")
            continue
        thin_conf = thin.get("confidence") if isinstance(thin, dict) else None
        if not isinstance(thin_conf, (int, float)):
            details.append(f"drop {field}: no confidence returned")
            continue
        total += 1
        confidences.append(float(thin_conf))
        # Expect thin_conf <= full_conf (allow tiny noise)
        if thin_conf <= full_conf + 0.02:
            passes += 1
            details.append(f"drop {field}: conf={thin_conf:.3f} ✓ (≤ full)")
        else:
            details.append(f"drop {field}: conf={thin_conf:.3f} ✗ (rose above full)")

    score = (passes / total) if total else 1.0
    return CriterionResult("trust_calibration", score >= 0.75, round(score, 3), details)


ALL_CRITERIA: dict[str, Callable[[ModelSpec, Fixture], CriterionResult]] = {
    "accuracy": check_accuracy,
    "consistency": check_consistency,
    "sensitivity": check_sensitivity,
    "explainability": check_explainability,
    "decision_usefulness": check_decision_usefulness,
    "trust_calibration": check_trust_calibration,
}


__all__ = [
    "ALL_CRITERIA",
    "check_accuracy",
    "check_consistency",
    "check_decision_usefulness",
    "check_explainability",
    "check_sensitivity",
    "check_trust_calibration",
]
