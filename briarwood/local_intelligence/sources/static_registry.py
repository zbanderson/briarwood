"""StaticRegistryAdapter — wraps the pre-curated MunicipalSourceSeed registry.

This adapter preserves the legacy behavior: look up known seed URLs for a
(town, state) pair, fetch them, and return document dicts. It exists so the
collector can treat "curated seeds" as just one adapter among many.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from briarwood.local_intelligence.sources.base import MunicipalSourceDocument

if TYPE_CHECKING:
    from briarwood.local_intelligence.collector import Fetcher, MunicipalSourceSeed

logger = logging.getLogger(__name__)


class StaticRegistryAdapter:
    """Fetches seeds from a hand-curated (town, state) → [MunicipalSourceSeed] map."""

    name = "static_registry"

    def __init__(
        self,
        *,
        registry: dict[tuple[str, str], "list[MunicipalSourceSeed]"],
        fetcher: "Fetcher",
        text_extractor,
    ) -> None:
        self.registry = registry
        self.fetcher = fetcher
        self._extract_text = text_extractor

    def fetch(
        self,
        *,
        town: str,
        state: str,
        focus: list[str] | None = None,
    ) -> list[MunicipalSourceDocument]:
        from briarwood.local_intelligence.collector import _clean_text, _normalize_town_key, _parse_datetime

        seeds = self.registry.get((_normalize_town_key(town), state.strip().upper()), [])
        documents: list[MunicipalSourceDocument] = []
        for seed in seeds:
            try:
                payload, content_type = self.fetcher(seed.url)
            except Exception as exc:  # pragma: no cover - network specific
                logger.warning("Municipal source fetch failed for %s: %s", seed.url, exc)
                continue

            text = self._extract_text(payload, content_type=content_type, url=seed.url)
            if not text:
                logger.warning("Municipal source yielded no readable text for %s", seed.url)
                continue

            published_at = _parse_datetime(seed.metadata.get("published_at"))
            documents.append(
                {
                    "title": seed.title,
                    "url": seed.url,
                    "source_type": seed.source_type.value,
                    "published_at": published_at.isoformat() if published_at is not None else None,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "raw_text": text,
                    "cleaned_text": _clean_text(text),
                    "metadata": dict(seed.metadata),
                }
            )
        return documents
