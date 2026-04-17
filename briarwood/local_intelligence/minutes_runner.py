"""Orchestrate per-town minutes freshness refreshes.

The runner ties the pieces in this package together:

- ``minutes_registry`` lists the feeds to refresh
- ``minutes_store`` loads/persists per-feed records
- ``minutes_sources`` provides the discover/fetch/summarize primitives

Each feed is processed independently so one town's outage can't starve the
rest. A per-feed ``RefreshResult`` is collected into a ``RefreshReport`` so
a scheduler, CLI, or dashboard can surface what changed without re-reading
disk.

Scalability: adding a town is a one-line change in ``minutes_registry``.
Swapping the discoverer (e.g. for a town whose index is JavaScript-rendered
or gated behind a portal) is a constructor-arg change on this runner — no
registry edits required.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from briarwood.local_intelligence.minutes_registry import (
    MINUTES_REGISTRY,
    MinutesFeed,
)
from briarwood.local_intelligence.minutes_schema import (
    MinuteEntry,
    MinutesRecord,
    expected_months,
    missing_months,
)
from briarwood.local_intelligence.minutes_sources import (
    DiscoveredMinutes,
    HeuristicSummarizer,
    HttpIndexDiscoverer,
    HttpMinutesFetcher,
    LLMBuyerLensSummarizer,
    MinutesDiscoverer,
    MinutesDocumentFetcher,
    MinutesSummarizer,
)
from briarwood.local_intelligence.minutes_store import JsonMinutesStore

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RefreshResult:
    """Per-feed outcome of a single refresh pass."""

    slug: str
    town: str
    state: str
    board: str
    checked: bool = False
    stale_before: bool = False
    missing_before: list[str] = field(default_factory=list)
    fetched_months: list[str] = field(default_factory=list)
    failed_months: list[str] = field(default_factory=list)
    skipped_reason: str | None = None
    error: str | None = None


@dataclass(slots=True)
class RefreshReport:
    """Aggregate outcome across every feed processed in one run."""

    started_at: str
    finished_at: str | None = None
    results: list[RefreshResult] = field(default_factory=list)

    @property
    def total_fetched(self) -> int:
        return sum(len(r.fetched_months) for r in self.results)

    @property
    def total_failed(self) -> int:
        return sum(len(r.failed_months) for r in self.results)


def run_refresh(
    *,
    registry: list[MinutesFeed] | None = None,
    store: JsonMinutesStore | None = None,
    discoverer: MinutesDiscoverer | None = None,
    fetcher: MinutesDocumentFetcher | None = None,
    summarizer: MinutesSummarizer | None = None,
    now: datetime | None = None,
    dry_run: bool = False,
    force: bool = False,
    slug_filter: set[str] | None = None,
    polite_delay_seconds: float = 0.0,
    max_feeds: int | None = None,
) -> RefreshReport:
    """Iterate every registered feed and refresh any that are stale or incomplete.

    ``force`` bypasses the staleness check and re-discovers all feeds. ``dry_run``
    runs discovery + planning but skips fetch/summarize/persist — useful for
    a "what would change" preview in CI or a scheduler dashboard.
    ``polite_delay_seconds`` inserts a sleep between each document fetch so a
    multi-town run doesn't hammer a single municipal host. ``max_feeds`` caps
    how many *eligible* feeds are processed this run — useful for chunking
    when the registry grows into the hundreds.
    """

    registry = registry if registry is not None else MINUTES_REGISTRY
    store = store or JsonMinutesStore()
    discoverer = discoverer or HttpIndexDiscoverer()
    fetcher = fetcher or HttpMinutesFetcher()
    # LLMBuyerLensSummarizer falls back to HeuristicSummarizer when no LLM
    # client is configured, so callers don't need to choose up front.
    summarizer = summarizer or LLMBuyerLensSummarizer()
    now = now or datetime.now(timezone.utc)

    started = now.isoformat()
    report = RefreshReport(started_at=started)

    processed_eligible = 0
    for feed in registry:
        if slug_filter and feed.slug not in slug_filter:
            continue
        result = _refresh_one(
            feed=feed,
            store=store,
            discoverer=discoverer,
            fetcher=fetcher,
            summarizer=summarizer,
            now=now,
            dry_run=dry_run,
            force=force,
            polite_delay_seconds=polite_delay_seconds,
        )
        report.results.append(result)
        if result.checked:
            processed_eligible += 1
        if max_feeds is not None and processed_eligible >= max_feeds:
            break

    report.finished_at = (now if dry_run else datetime.now(timezone.utc)).isoformat()
    return report


def _refresh_one(
    *,
    feed: MinutesFeed,
    store: JsonMinutesStore,
    discoverer: MinutesDiscoverer,
    fetcher: MinutesDocumentFetcher,
    summarizer: MinutesSummarizer,
    now: datetime,
    dry_run: bool,
    force: bool,
    polite_delay_seconds: float = 0.0,
) -> RefreshResult:
    result = RefreshResult(
        slug=feed.slug,
        town=feed.town,
        state=feed.state,
        board=feed.board,
    )

    try:
        record = store.load_or_initialize(feed)
    except Exception as exc:
        result.error = f"load failed: {exc}"
        logger.exception("Failed to load minutes record for %s", feed.slug)
        return result

    result.stale_before = record.is_stale(now=now)
    result.missing_before = missing_months(record, now=now)

    should_run = force or result.stale_before or bool(result.missing_before)
    if not should_run:
        result.skipped_reason = "fresh_and_complete"
        return result

    result.checked = True
    wanted_months = set(result.missing_before)
    # When forced or stale with no explicit gaps, walk the full rolling window
    # so a re-run can re-fetch documents that may have been updated in place.
    if force or (result.stale_before and not wanted_months):
        wanted_months = set(expected_months(now=now, window=record.rolling_window_months))

    years = sorted({int(month.split("-")[0]) for month in wanted_months}) or [now.year]
    discovered: list[DiscoveredMinutes] = []
    for year in years:
        try:
            discovered.extend(discoverer.discover(feed, year))
        except Exception as exc:
            logger.warning("Discovery failed for %s year=%s: %s", feed.slug, year, exc)
            result.error = (result.error or "") + f"discover({year}): {exc}; "

    dedup: dict[str, DiscoveredMinutes] = {}
    for item in discovered:
        if item.month in wanted_months and item.month not in dedup:
            dedup[item.month] = item

    if dry_run:
        result.fetched_months = sorted(dedup.keys())
        return result

    new_entries: dict[str, MinuteEntry] = {}
    for i, (month, disc) in enumerate(sorted(dedup.items(), reverse=True)):
        if i > 0 and polite_delay_seconds > 0:
            time.sleep(polite_delay_seconds)
        entry = _process_month(
            disc=disc,
            feed=feed,
            fetcher=fetcher,
            summarizer=summarizer,
            now=now,
        )
        new_entries[month] = entry
        if entry.status == "fetched":
            result.fetched_months.append(month)
        else:
            result.failed_months.append(month)

    record = _merge_entries(record, new_entries)
    record.last_checked_at = now.isoformat()
    if result.fetched_months:
        record.last_successful_refresh_at = now.isoformat()

    try:
        store.save(feed, record)
    except Exception as exc:
        logger.exception("Failed to persist minutes record for %s", feed.slug)
        result.error = (result.error or "") + f"save: {exc}; "
    return result


def _process_month(
    *,
    disc: DiscoveredMinutes,
    feed: MinutesFeed,
    fetcher: MinutesDocumentFetcher,
    summarizer: MinutesSummarizer,
    now: datetime,
) -> MinuteEntry:
    extracted = None
    try:
        extracted = fetcher.fetch(disc)
    except Exception as exc:
        logger.warning("Fetch failed for %s %s: %s", feed.slug, disc.month, exc)

    if extracted is None:
        return MinuteEntry(
            month=disc.month,
            board=feed.board,
            source_url=disc.source_url,
            fetched_at=now.isoformat(),
            status="fetch_failed",
        )

    try:
        summary = summarizer.summarize(extracted)
    except Exception as exc:
        logger.warning("Summarize failed for %s %s: %s", feed.slug, disc.month, exc)
        return MinuteEntry(
            month=disc.month,
            board=feed.board,
            source_url=disc.source_url,
            fetched_at=now.isoformat(),
            status="fetch_failed",
            raw_excerpt=extracted.raw_text[:1000],
        )

    return MinuteEntry(
        month=disc.month,
        board=feed.board,
        source_url=disc.source_url,
        fetched_at=now.isoformat(),
        status="fetched",
        summary=summary.summary,
        summary_confidence=summary.confidence,
        tags=summary.tags or [],
        raw_excerpt=extracted.raw_text[:1000],
    )


def _merge_entries(
    record: MinutesRecord, new_entries: dict[str, MinuteEntry]
) -> MinutesRecord:
    """Replace matching months in-place; drop anything outside the rolling window."""

    allowed = set(expected_months(window=record.rolling_window_months))
    allowed.update(new_entries.keys())
    existing = {e.month: e for e in record.entries if e.month in allowed}
    existing.update(new_entries)
    merged = sorted(existing.values(), key=lambda e: e.month, reverse=True)
    return record.model_copy(update={"entries": merged})


__all__ = [
    "RefreshReport",
    "RefreshResult",
    "run_refresh",
]
