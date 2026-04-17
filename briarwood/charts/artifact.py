"""Rendered-chart container returned by the charts package."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChartArtifact:
    kind: str
    html: str
    png_bytes: bytes | None = None
    source_data: dict[str, Any] = field(default_factory=dict)


__all__ = ["ChartArtifact"]
