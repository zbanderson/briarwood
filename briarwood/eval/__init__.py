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


__all__ = ["run_eval", "score_model", "main"]
