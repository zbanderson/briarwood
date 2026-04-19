"""Prompts-sweep: every ``(cite X)`` label in a tier prompt must resolve to
an entry in ``briarwood.agent.prompt_modules.PROMPT_MODULE_LABELS``.

The LLM uses these labels in ``[[X:field:value]]`` grounding markers; a label
the verifier does not recognize is flagged as ``unknown_module`` at runtime.
This test is the compile-time guarantee that prompt edits cannot introduce
a label that the registry has not learned about.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from briarwood.agent.prompt_modules import PROMPT_MODULE_LABELS

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "api" / "prompts"
_CITE_RE = re.compile(r"cite\s+([A-Z][A-Za-z0-9]+)")


class PromptCitationLabelsTests(unittest.TestCase):
    def test_every_cited_label_is_registered(self) -> None:
        offenders: list[tuple[str, str]] = []
        for path in sorted(_PROMPTS_DIR.glob("*.md")):
            for match in _CITE_RE.finditer(path.read_text()):
                label = match.group(1)
                if label not in PROMPT_MODULE_LABELS:
                    offenders.append((path.name, label))
        self.assertEqual(
            offenders,
            [],
            f"Prompts cite labels not in PROMPT_MODULE_LABELS: {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
