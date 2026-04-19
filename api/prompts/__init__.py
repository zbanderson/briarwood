"""Prompt loader.

Tier prompts live as Markdown files under api/prompts/. Each tier file may
include the shared base via a literal `{{include: _base.md}}` directive on its
own line; the loader concats the included file at that point. One level of
inclusion is supported — included files are not themselves preprocessed for
nested directives, by design (keeps the loader trivial and the include graph
flat).

Prompts are cached at module import time so call sites pay zero per-request
file I/O. If you edit a prompt during a long-running dev server, restart the
process — the cache is intentionally not invalidated on disk change.
"""

from __future__ import annotations

import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent
_INCLUDE_RE = re.compile(r"^\{\{include:\s*([^}]+?)\s*\}\}\s*$", re.MULTILINE)
_CACHE: dict[str, str] = {}


def _read(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text()


def _expand(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        included = match.group(1).strip()
        return _read(included).rstrip()
    return _INCLUDE_RE.sub(repl, text)


def load_prompt(tier: str) -> str:
    """Load a tier prompt by short name (e.g. 'risk' → 'risk.md').

    The returned string is the fully expanded system prompt, ready to pass to
    the LLM. Cached after first read.
    """
    if tier in _CACHE:
        return _CACHE[tier]
    raw = _read(f"{tier}.md")
    expanded = _expand(raw).strip()
    _CACHE[tier] = expanded
    return expanded


__all__ = ["load_prompt"]
