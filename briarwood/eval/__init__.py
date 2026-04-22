"""Briarwood evaluation package.

The package exposes lazy wrappers so lightweight tooling such as the
operational sweep can import submodules without eagerly importing the full
feedback/model harness stack.
"""

from __future__ import annotations


def run_eval(*args, **kwargs):
    from briarwood.eval.harness import run_eval as _run_eval

    return _run_eval(*args, **kwargs)


def score_model(*args, **kwargs):
    from briarwood.eval.harness import score_model as _score_model

    return _score_model(*args, **kwargs)


def main(*args, **kwargs):
    from briarwood.eval.harness import main as _main

    return _main(*args, **kwargs)


def run_backtest_program(*args, **kwargs):
    from briarwood.eval.backtest_program import run_backtest_program as _run_backtest_program

    return _run_backtest_program(*args, **kwargs)


def run_canonical_underwrite_benchmark(*args, **kwargs):
    from briarwood.eval.canonical_underwrite_benchmark import run_benchmark as _run_benchmark

    return _run_benchmark(*args, **kwargs)


__all__ = [
    "run_eval",
    "score_model",
    "main",
    "run_backtest_program",
    "run_canonical_underwrite_benchmark",
]
