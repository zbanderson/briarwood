"""Model quality harness — pre-deployment QA for specialist models.

Distinct from ``briarwood.eval.harness`` (which measures real outcomes from
captured feedback). This package scores each specialist model against six
criteria before the model touches production:

  - Accuracy
  - Consistency
  - Sensitivity
  - Explainability
  - Decision usefulness
  - Trust calibration

CLI entry:
    python -m briarwood.eval.model_quality.harness
"""

from briarwood.eval.model_quality.harness import run_quality_suite, main

__all__ = ["run_quality_suite", "main"]
