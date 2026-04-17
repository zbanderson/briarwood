"""Charts package — a clean API keyed on Layer 05 chart kinds.

Thin wrapper over the figure builders in ``briarwood.agent.rendering``.
No duplication of plotting logic: figure construction lives in the
rendering module, the wrapper here only:

  - constrains the public surface to the four canonical kinds emitted
    by ``pipeline/unified.py`` chart router,
  - returns a structured ``ChartArtifact`` (HTML string + optional PNG
    bytes + source data) rather than writing files,
  - provides a helper that builds the spec from a session + chart route
    dict as produced by the Unified Intelligence Agent.
"""

from briarwood.charts.artifact import ChartArtifact
from briarwood.charts.render import CHART_KINDS, render, render_from_route

__all__ = ["CHART_KINDS", "ChartArtifact", "render", "render_from_route"]
