"""MinutesFeedAdapter — per-town planning/zoning minutes URL patterns.

Some towns publish minutes at a predictable URL pattern (e.g.
``/Planning%20Board%20Meeting%20Minutes/{year}/{mmdd}{yy}.pdf``). This
adapter iterates a small date window per configured town and tries each
URL. Miss → skip quietly; hit → extract text and emit a doc.

Configuration lives in a single dict here; adding a town is a one-line
change. No scraping, no heuristics — URL templates only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Callable

from briarwood.local_intelligence.models import SourceType
from briarwood.local_intelligence.sources.base import MunicipalSourceDocument

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MinutesFeedConfig:
    """URL template for a town's published minutes.

    ``url_template`` uses ``{year}``, ``{month:02d}``, ``{day:02d}`` and/or
    ``{yy:02d}``. The adapter substitutes dates from ``date_strategy``.
    """
    url_template: str
    source_type: SourceType = SourceType.PLANNING_BOARD_MINUTES
    date_strategy: str = "monthly"  # "monthly" → first of each month; extend as needed
    lookback_months: int = 6
    title_template: str = "Planning Board Minutes {year}-{month:02d}"


# (town_lower, state_upper) → list of feed configs
MINUTES_FEED_REGISTRY: dict[tuple[str, str], list[MinutesFeedConfig]] = {
    # Template only — Avon's real URL pattern includes the specific filename;
    # kept here as a placeholder so the adapter has at least one wired town
    # without requiring network access for other towns.
}


class MinutesFeedAdapter:
    name = "minutes_feed"

    def __init__(
        self,
        *,
        registry: dict[tuple[str, str], list[MinutesFeedConfig]] | None = None,
        fetcher: Callable[[str], tuple[bytes, str | None]] | None = None,
        text_extractor: Callable[..., str] | None = None,
        today: date | None = None,
    ) -> None:
        self.registry = registry if registry is not None else MINUTES_FEED_REGISTRY
        self._fetcher = fetcher
        self._text_extractor = text_extractor
        self._today = today

    def fetch(
        self,
        *,
        town: str,
        state: str,
        focus: list[str] | None = None,
    ) -> list[MunicipalSourceDocument]:
        key = (town.strip().lower(), state.strip().upper())
        configs = self.registry.get(key, [])
        if not configs:
            return []

        fetcher = self._fetcher or _default_fetcher()
        extractor = self._text_extractor or _default_extractor
        today = self._today or date.today()
        documents: list[MunicipalSourceDocument] = []

        for cfg in configs:
            for target in _dates_for_strategy(cfg.date_strategy, today, cfg.lookback_months):
                url = cfg.url_template.format(
                    year=target.year,
                    month=target.month,
                    day=target.day,
                    yy=target.year % 100,
                )
                try:
                    payload, content_type = fetcher(url)
                except Exception:
                    # Miss is expected — most templated URLs won't resolve.
                    continue
                text = extractor(payload, content_type=content_type, url=url)
                if not text:
                    continue
                documents.append(
                    {
                        "title": cfg.title_template.format(year=target.year, month=target.month, day=target.day),
                        "url": url,
                        "source_type": cfg.source_type.value,
                        "published_at": target.isoformat(),
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "raw_text": text,
                        "cleaned_text": _clean(text),
                        "metadata": {"template": cfg.url_template, "focus": list(focus or [])},
                    }
                )
        return documents


def _dates_for_strategy(strategy: str, today: date, lookback_months: int) -> list[date]:
    if strategy != "monthly":
        return [today]
    out: list[date] = []
    year, month = today.year, today.month
    for _ in range(max(1, lookback_months)):
        out.append(date(year, month, 1))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return out


def _default_fetcher():
    from briarwood.local_intelligence.collector import _default_fetcher as _f

    return _f(12.0)


def _default_extractor(payload: bytes, *, content_type: str | None, url: str) -> str:
    from briarwood.local_intelligence.collector import _extract_html_text, _extract_pdf_text

    norm = (content_type or "").lower()
    if url.lower().endswith(".pdf") or "pdf" in norm:
        return _extract_pdf_text(payload)
    return _extract_html_text(payload)


def _clean(text: str) -> str:
    import re

    return re.sub(r"\s+", " ", text).strip()
