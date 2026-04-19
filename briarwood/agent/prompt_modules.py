"""Canonical display labels for source modules cited in LLM-composed prose.

Prompts instruct the LLM to attribute quantitative claims to the producing
module using ``[[Label:field:value]]`` markers (see ``api/prompts/_base.md``).
These labels are surface-facing identifiers distinct from:

- ``briarwood/routing_schema.ModuleName`` — backend module IDs used by the
  routing engine and executor.
- ``api/pipeline_adapter._MODULE_REGISTRY`` — SSE event → module-attribution
  mapping used for the "modules ran" footer.

The three namespaces are separate on purpose: prompt labels read naturally
in narration, backend IDs prioritize stable machine names, and SSE labels
feed UI attribution. This set is the single source of truth for labels the
LLM may cite.
"""
from __future__ import annotations


PROMPT_MODULE_LABELS: frozenset[str] = frozenset({
    "DecisionSynthesizer",
    "ValuationModel",
    "ValueThesis",
    "RiskProfile",
    "ProjectionEngine",
    "RentOutlook",
    "StrategyFit",
    "TownResearch",
})

__all__ = ["PROMPT_MODULE_LABELS"]
