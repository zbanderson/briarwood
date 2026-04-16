"""Model eval harness — Layer 08 of the architecture.

Per-specialist-model scoring, regression checks, and drift detection over
the captured feedback corpus. Runnable as a standalone CLI:

    python -m briarwood.eval.harness

See harness.py for the attachment point for a cron/scheduler hook.
"""

from briarwood.eval.harness import run_eval, score_model, main

__all__ = ["run_eval", "score_model", "main"]
