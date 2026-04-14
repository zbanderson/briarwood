"""Pluggable municipal source adapters.

Adapters implement a single ``fetch(town, state, focus)`` method returning
document dicts the collector can cache. Keeping adapters small and
single-purpose lets us add/remove sources without touching the collector,
service, or agent wiring.
"""

from briarwood.local_intelligence.sources.base import (
    MunicipalSourceAdapter,
    MunicipalSourceDocument,
)
from briarwood.local_intelligence.sources.static_registry import StaticRegistryAdapter

__all__ = [
    "MunicipalSourceAdapter",
    "MunicipalSourceDocument",
    "StaticRegistryAdapter",
]
