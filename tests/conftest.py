"""Repo-wide pytest configuration.

Two production observability artifacts must not be polluted by test runs:

1. The LLM call ledger writes one JSON line per call to a JSONL sink
   (``briarwood/agent/llm_observability.py``; default
   ``data/llm_calls.jsonl``).
2. The intelligence-capture helper appends user-validation and routed
   capture records to a JSONL hopper read by the feedback analyzer
   (``briarwood/intelligence_capture.py``; default
   ``data/learning/intelligence_feedback.jsonl``).

This hook redirects both to per-session tmp files before any test
collects or runs. Individual tests can still override either env var via
monkeypatch — function-scoped overrides restore to the session value
after the test.
"""

from __future__ import annotations

import os
import tempfile


def pytest_sessionstart(session) -> None:  # noqa: D401, ARG001
    if "BRIARWOOD_LLM_JSONL_PATH" not in os.environ:
        tmpdir = tempfile.mkdtemp(prefix="briarwood-test-llm-jsonl-")
        os.environ["BRIARWOOD_LLM_JSONL_PATH"] = os.path.join(
            tmpdir, "llm_calls.jsonl"
        )
    if "BRIARWOOD_INTEL_FEEDBACK_PATH" not in os.environ:
        tmpdir = tempfile.mkdtemp(prefix="briarwood-test-intel-feedback-")
        os.environ["BRIARWOOD_INTEL_FEEDBACK_PATH"] = os.path.join(
            tmpdir, "intelligence_feedback.jsonl"
        )
