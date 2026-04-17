"""Runner-level tests for the per-town minutes freshness system.

We exercise the full orchestration with stub Discoverer/Fetcher/Summarizer
implementations so the HTTP + PDF plumbing is out of scope here (those
primitives are covered by their own unit tests).
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from briarwood.local_intelligence.minutes_registry import MinutesFeed
from briarwood.local_intelligence.minutes_runner import run_refresh
from briarwood.local_intelligence.minutes_schema import (
    MinuteEntry,
    MinutesRecord,
    expected_months,
    missing_months,
)
from briarwood.local_intelligence.minutes_sources import (
    DiscoveredMinutes,
    ExtractedMinutes,
    HttpIndexDiscoverer,
    HttpMinutesFetcher,
    LLMBuyerLensSummarizer,
    MinutesSummary,
    _extract_base_url,
    _extract_docx_text,
    _safe_url,
)
from briarwood.local_intelligence.minutes_store import JsonMinutesStore


FIXED_NOW = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)


def _feed(**overrides) -> MinutesFeed:
    defaults = dict(
        town="Test Town",
        state="NJ",
        board="planning_board",
        index_url_template="https://example.test/{year}.php",
        stale_after_days=30,
        rolling_window_months=6,
    )
    defaults.update(overrides)
    return MinutesFeed(**defaults)


class StubDiscoverer:
    """Emits a configurable list of DiscoveredMinutes keyed by year."""

    def __init__(self, by_year: dict[int, list[DiscoveredMinutes]]) -> None:
        self.by_year = by_year
        self.calls: list[tuple[str, int]] = []

    def discover(self, feed, year):
        self.calls.append((feed.slug, year))
        return list(self.by_year.get(year, []))


class StubFetcher:
    """Returns a fixed ExtractedMinutes for every request, or None to force fail."""

    def __init__(self, text: str = "A variance was granted.", fail_months: set[str] | None = None) -> None:
        self.text = text
        self.fail_months = fail_months or set()
        self.calls: list[str] = []

    def fetch(self, discovered):
        self.calls.append(discovered.month)
        if discovered.month in self.fail_months:
            return None
        return ExtractedMinutes(
            month=discovered.month,
            source_url=discovered.source_url,
            raw_text=self.text,
            title=discovered.title,
        )


class StubSummarizer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def summarize(self, extracted):
        self.calls.append(extracted.month)
        return MinutesSummary(summary=f"summary:{extracted.month}", confidence=0.6, tags=["variance"])


class MinutesRunnerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _store(self) -> JsonMinutesStore:
        return JsonMinutesStore(root=self.root)

    def test_fresh_and_complete_feed_is_skipped(self):
        feed = _feed()
        store = self._store()
        months = expected_months(now=FIXED_NOW, window=feed.rolling_window_months)
        record = MinutesRecord(
            town=feed.town,
            state=feed.state,
            board=feed.board,
            url_template=feed.index_url_template or "",
            stale_after_days=feed.stale_after_days,
            rolling_window_months=feed.rolling_window_months,
            last_checked_at=FIXED_NOW.isoformat(),
            entries=[
                MinuteEntry(month=m, board=feed.board, status="fetched", summary=f"s:{m}")
                for m in months
            ],
        )
        store.save(feed, record)

        discoverer = StubDiscoverer({})
        fetcher = StubFetcher()
        summarizer = StubSummarizer()

        report = run_refresh(
            registry=[feed],
            store=store,
            discoverer=discoverer,
            fetcher=fetcher,
            summarizer=summarizer,
            now=FIXED_NOW,
        )
        self.assertEqual(len(report.results), 1)
        result = report.results[0]
        self.assertEqual(result.skipped_reason, "fresh_and_complete")
        self.assertFalse(discoverer.calls)
        self.assertEqual(fetcher.calls, [])

    def test_stale_record_triggers_discovery_and_fetch(self):
        feed = _feed()
        store = self._store()
        target_month = expected_months(now=FIXED_NOW, window=feed.rolling_window_months)[0]
        disc = DiscoveredMinutes(
            month=target_month, source_url="https://example.test/x.pdf", title="Minutes"
        )
        discoverer = StubDiscoverer({FIXED_NOW.year: [disc]})
        fetcher = StubFetcher()
        summarizer = StubSummarizer()

        report = run_refresh(
            registry=[feed],
            store=store,
            discoverer=discoverer,
            fetcher=fetcher,
            summarizer=summarizer,
            now=FIXED_NOW,
        )
        result = report.results[0]
        self.assertIn(target_month, result.fetched_months)
        self.assertEqual(fetcher.calls, [target_month])
        self.assertEqual(summarizer.calls, [target_month])

        # Persisted record has the new entry with "fetched" status.
        saved = store.load(feed)
        self.assertIsNotNone(saved)
        by_month = saved.entries_by_month()
        self.assertEqual(by_month[target_month].status, "fetched")
        self.assertEqual(by_month[target_month].summary, f"summary:{target_month}")
        self.assertEqual(saved.last_checked_at, FIXED_NOW.isoformat())
        self.assertEqual(saved.last_successful_refresh_at, FIXED_NOW.isoformat())

    def test_dry_run_does_not_persist(self):
        feed = _feed()
        store = self._store()
        target_month = expected_months(now=FIXED_NOW, window=feed.rolling_window_months)[0]
        disc = DiscoveredMinutes(month=target_month, source_url="https://example.test/x.pdf")
        discoverer = StubDiscoverer({FIXED_NOW.year: [disc]})
        fetcher = StubFetcher()
        summarizer = StubSummarizer()

        report = run_refresh(
            registry=[feed],
            store=store,
            discoverer=discoverer,
            fetcher=fetcher,
            summarizer=summarizer,
            now=FIXED_NOW,
            dry_run=True,
        )
        result = report.results[0]
        self.assertIn(target_month, result.fetched_months)
        self.assertEqual(fetcher.calls, [])  # dry-run skips the fetch
        self.assertIsNone(store.load(feed))

    def test_fetch_failure_recorded_and_does_not_mark_success(self):
        feed = _feed()
        store = self._store()
        target_month = expected_months(now=FIXED_NOW, window=feed.rolling_window_months)[0]
        disc = DiscoveredMinutes(month=target_month, source_url="https://example.test/x.pdf")
        discoverer = StubDiscoverer({FIXED_NOW.year: [disc]})
        fetcher = StubFetcher(fail_months={target_month})
        summarizer = StubSummarizer()

        report = run_refresh(
            registry=[feed],
            store=store,
            discoverer=discoverer,
            fetcher=fetcher,
            summarizer=summarizer,
            now=FIXED_NOW,
        )
        result = report.results[0]
        self.assertIn(target_month, result.failed_months)
        self.assertEqual(summarizer.calls, [])

        saved = store.load(feed)
        self.assertEqual(saved.entries_by_month()[target_month].status, "fetch_failed")
        self.assertEqual(saved.last_checked_at, FIXED_NOW.isoformat())
        self.assertIsNone(saved.last_successful_refresh_at)

    def test_slug_filter_limits_feeds_processed(self):
        feed_a = _feed(town="Alpha")
        feed_b = _feed(town="Bravo")
        store = self._store()
        discoverer = StubDiscoverer({})
        fetcher = StubFetcher()
        summarizer = StubSummarizer()

        report = run_refresh(
            registry=[feed_a, feed_b],
            store=store,
            discoverer=discoverer,
            fetcher=fetcher,
            summarizer=summarizer,
            now=FIXED_NOW,
            slug_filter={feed_b.slug},
        )
        self.assertEqual([r.slug for r in report.results], [feed_b.slug])

    def test_force_scans_full_rolling_window(self):
        feed = _feed(rolling_window_months=3)
        store = self._store()
        months = expected_months(now=FIXED_NOW, window=feed.rolling_window_months)
        record = MinutesRecord(
            town=feed.town,
            state=feed.state,
            board=feed.board,
            url_template=feed.index_url_template or "",
            stale_after_days=feed.stale_after_days,
            rolling_window_months=feed.rolling_window_months,
            last_checked_at=FIXED_NOW.isoformat(),
            entries=[
                MinuteEntry(month=m, board=feed.board, status="fetched", summary=f"old:{m}")
                for m in months
            ],
        )
        store.save(feed, record)

        discovered = [
            DiscoveredMinutes(month=m, source_url=f"https://example.test/{m}.pdf") for m in months
        ]
        discoverer = StubDiscoverer({FIXED_NOW.year: discovered})
        fetcher = StubFetcher(text="New variance decision.")
        summarizer = StubSummarizer()

        report = run_refresh(
            registry=[feed],
            store=store,
            discoverer=discoverer,
            fetcher=fetcher,
            summarizer=summarizer,
            now=FIXED_NOW,
            force=True,
        )
        result = report.results[0]
        self.assertEqual(set(result.fetched_months), set(months))

        saved = store.load(feed)
        for m in months:
            self.assertEqual(saved.entries_by_month()[m].summary, f"summary:{m}")

    def test_missing_months_triggers_multi_year_discovery(self):
        # A window spanning Dec 2025 → Apr 2026 should query both years.
        now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=timezone.utc)
        feed = _feed(rolling_window_months=5)
        store = self._store()
        # Record has no entries at all → every month in window is missing.
        discoverer = StubDiscoverer({2026: [], 2025: []})
        fetcher = StubFetcher()
        summarizer = StubSummarizer()

        report = run_refresh(
            registry=[feed],
            store=store,
            discoverer=discoverer,
            fetcher=fetcher,
            summarizer=summarizer,
            now=now,
        )
        years_queried = {year for (_slug, year) in discoverer.calls}
        self.assertEqual(years_queried, {2025, 2026})
        # Nothing was discovered → no fetches attempted.
        self.assertFalse(fetcher.calls)
        # Record still gets last_checked_at stamped.
        saved = store.load(feed)
        self.assertEqual(saved.last_checked_at, now.isoformat())


class MinutesSchemaHelperTests(unittest.TestCase):
    def test_expected_months_most_recent_first(self):
        now = datetime(2026, 4, 17, tzinfo=timezone.utc)
        months = expected_months(now=now, window=4)
        self.assertEqual(months, ["2026-04", "2026-03", "2026-02", "2026-01"])

    def test_expected_months_wraps_year_boundary(self):
        now = datetime(2026, 2, 1, tzinfo=timezone.utc)
        months = expected_months(now=now, window=4)
        self.assertEqual(months, ["2026-02", "2026-01", "2025-12", "2025-11"])

    def test_missing_months_excludes_fetched_entries(self):
        now = datetime(2026, 4, 17, tzinfo=timezone.utc)
        record = MinutesRecord(
            town="T",
            state="NJ",
            board="planning_board",
            url_template="u",
            rolling_window_months=3,
            entries=[
                MinuteEntry(month="2026-04", board="planning_board", status="fetched"),
                MinuteEntry(month="2026-03", board="planning_board", status="fetch_failed"),
            ],
        )
        self.assertEqual(missing_months(record, now=now), ["2026-03", "2026-02"])

    def test_is_stale_when_last_checked_absent(self):
        record = MinutesRecord(
            town="T", state="NJ", board="planning_board", url_template="u"
        )
        self.assertTrue(record.is_stale(now=FIXED_NOW))

    def test_is_fresh_within_ttl(self):
        recent = (FIXED_NOW - timedelta(days=5)).isoformat()
        record = MinutesRecord(
            town="T",
            state="NJ",
            board="planning_board",
            url_template="u",
            stale_after_days=30,
            last_checked_at=recent,
        )
        self.assertFalse(record.is_stale(now=FIXED_NOW))

    def test_is_stale_past_ttl(self):
        old = (FIXED_NOW - timedelta(days=45)).isoformat()
        record = MinutesRecord(
            town="T",
            state="NJ",
            board="planning_board",
            url_template="u",
            stale_after_days=30,
            last_checked_at=old,
        )
        self.assertTrue(record.is_stale(now=FIXED_NOW))


class MinutesRegistryTests(unittest.TestCase):
    def test_slug_is_stable_and_urlsafe(self):
        feed = _feed(town="Avon by the Sea", state="nj", board="Planning Board")
        self.assertEqual(feed.slug, "avon-by-the-sea-nj-planning-board")

    def test_get_feed_and_feeds_for_town(self):
        from briarwood.local_intelligence.minutes_registry import (
            MINUTES_REGISTRY,
            feeds_for_town,
            get_feed,
        )

        # At least the seeded Avon feed should exist.
        self.assertTrue(MINUTES_REGISTRY)
        avon = feeds_for_town(town="Avon-by-the-Sea", state="NJ")
        self.assertTrue(avon)
        found = get_feed(avon[0].slug)
        self.assertEqual(found, avon[0])
        self.assertIsNone(get_feed("no-such-slug"))


class HttpIndexDiscovererTests(unittest.TestCase):
    """Parsing tests for table-row + anchor discovery strategies."""

    def _stub_fetcher(self, html: str):
        def fetch(url):
            return html.encode("utf-8"), "text/html"

        return fetch

    def test_base_href_resolves_relative_links_to_root(self):
        html = """
        <html><head><base href="https://example.gov/"></head>
        <body><table><tr>
            <td>March 14, 2024</td>
            <td><a href="Agenda.pdf">Agenda</a></td>
            <td><a href="March 14, 2024 Meeting Minutes.pdf">Minutes</a></td>
        </tr></table></body></html>
        """
        feed = _feed(index_url_template="https://example.gov/planning/{year}.php")
        d = HttpIndexDiscoverer(fetcher=self._stub_fetcher(html))
        items = d.discover(feed, 2024)
        self.assertEqual(len(items), 1)
        # Resolves against <base>, not the subdirectory.
        self.assertTrue(
            items[0].source_url.startswith("https://example.gov/March 14, 2024"),
            items[0].source_url,
        )

    def test_table_strategy_pairs_date_cell_with_minutes_anchor(self):
        html = """
        <table>
          <tr><th>Date</th><th>Agenda</th><th>Minutes</th></tr>
          <tr>
            <td>January 11, 2024</td>
            <td>&nbsp;</td>
            <td>&nbsp;</td>
          </tr>
          <tr>
            <td>February 8, 2024</td>
            <td><a href="feb-agenda.docx">Agenda</a></td>
            <td><a href="feb-minutes.docx?t=123">Minutes</a></td>
          </tr>
          <tr>
            <td>December 12, 2024</td>
            <td>CANCELLED</td>
            <td>CANCELLED</td>
          </tr>
        </table>
        """
        feed = _feed(index_url_template="https://ex.test/{year}.php")
        d = HttpIndexDiscoverer(fetcher=self._stub_fetcher(html))
        items = d.discover(feed, 2024)
        # Jan and Dec rows have no anchors; only Feb produces a discovery.
        self.assertEqual([i.month for i in items], ["2024-02"])
        self.assertTrue(items[0].source_url.endswith("feb-minutes.docx?t=123"))

    def test_anchor_fallback_when_no_table(self):
        html = """
        <html><body>
        <a href="march-2024-minutes.pdf">March 2024 Minutes</a>
        <a href="april-2024-minutes.pdf">April 2024 Minutes</a>
        <a href="unrelated.pdf">Ordinance 42</a>
        </body></html>
        """
        feed = _feed(index_url_template="https://ex.test/{year}")
        d = HttpIndexDiscoverer(fetcher=self._stub_fetcher(html))
        items = d.discover(feed, 2024)
        months = sorted(i.month for i in items)
        self.assertEqual(months, ["2024-03", "2024-04"])

    def test_dedupes_when_table_and_anchor_strategies_overlap(self):
        html = """
        <html><body>
        <table><tr>
          <td>March 14, 2024</td>
          <td><a href="mar-2024-minutes.pdf">Agenda</a></td>
          <td><a href="mar-2024-minutes.pdf">Minutes</a></td>
        </tr></table>
        </body></html>
        """
        feed = _feed(index_url_template="https://ex.test/{year}")
        d = HttpIndexDiscoverer(fetcher=self._stub_fetcher(html))
        items = d.discover(feed, 2024)
        self.assertEqual(len(items), 1)

    def test_returns_empty_when_no_index_template(self):
        feed = _feed(index_url_template=None)
        d = HttpIndexDiscoverer(fetcher=self._stub_fetcher("<html></html>"))
        self.assertEqual(d.discover(feed, 2024), [])


class UrlAndDocHelperTests(unittest.TestCase):
    def test_safe_url_encodes_spaces(self):
        encoded = _safe_url("https://ex.test/February 8, 2024 Minutes.pdf?t=1")
        # Spaces must be percent-encoded; commas are RFC 3986-safe in paths.
        self.assertNotIn(" ", encoded)
        self.assertIn("%20", encoded)
        self.assertTrue(encoded.endswith("?t=1"))

    def test_safe_url_idempotent(self):
        already = "https://ex.test/path/File.pdf?x=1"
        self.assertEqual(_safe_url(already), already)

    def test_extract_base_url_prefers_base_tag(self):
        html = '<html><head><base href="https://other.example/"></head></html>'
        self.assertEqual(_extract_base_url(html, "https://fallback/x.php"), "https://other.example/")

    def test_extract_base_url_falls_back_without_tag(self):
        self.assertEqual(_extract_base_url("<html></html>", "https://fallback/x.php"), "https://fallback/x.php")

    def test_extract_docx_text_reads_word_runs(self):
        import io
        import zipfile

        body_xml = (
            '<?xml version="1.0"?><w:document xmlns:w="x">'
            '<w:body><w:p><w:r><w:t>Variance granted</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>for 210 Washington &amp; 212 Main</w:t></w:r></w:p>'
            '</w:body></w:document>'
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("word/document.xml", body_xml)
        text = _extract_docx_text(buf.getvalue())
        self.assertIn("Variance granted", text)
        self.assertIn("210 Washington & 212 Main", text)

    def test_extract_docx_text_returns_empty_on_garbage(self):
        self.assertEqual(_extract_docx_text(b"not a zip"), "")


class LLMBuyerLensFallbackTests(unittest.TestCase):
    class _FailingClient:
        def complete(self, **_):
            raise RuntimeError("LLM unreachable")

    class _EmptyClient:
        def complete(self, **_):
            return ""

    def test_falls_back_when_no_client(self):
        # Bypass the ambient default_client() which would pick up a real API
        # key from the environment and actually call OpenAI in CI.
        from unittest.mock import patch

        summarizer = LLMBuyerLensSummarizer(client=None, fallback=_HeuristicMarker())
        ex = ExtractedMinutes(
            month="2025-03",
            source_url="https://ex/x.pdf",
            raw_text="A variance was granted.",
        )
        with patch("briarwood.agent.llm.default_client", return_value=None):
            out = summarizer.summarize(ex)
        self.assertEqual(out.summary, "FALLBACK")

    def test_falls_back_when_client_errors(self):
        summarizer = LLMBuyerLensSummarizer(
            client=self._FailingClient(), fallback=_HeuristicMarker()
        )
        ex = ExtractedMinutes(
            month="2025-03", source_url="https://ex/x.pdf", raw_text="text"
        )
        self.assertEqual(summarizer.summarize(ex).summary, "FALLBACK")

    def test_falls_back_when_client_returns_empty(self):
        summarizer = LLMBuyerLensSummarizer(
            client=self._EmptyClient(), fallback=_HeuristicMarker()
        )
        ex = ExtractedMinutes(
            month="2025-03", source_url="https://ex/x.pdf", raw_text="text"
        )
        self.assertEqual(summarizer.summarize(ex).summary, "FALLBACK")


class _HeuristicMarker:
    """Test-only fallback that returns a distinctive summary."""

    def summarize(self, extracted):
        return MinutesSummary(summary="FALLBACK", confidence=0.1, tags=[])


class PoliteDelayAndMaxFeedsTests(unittest.TestCase):
    def test_max_feeds_caps_processing(self):
        feeds = [
            _feed(town=f"Town{i}", index_url_template=f"https://ex.test/{i}/" + "{year}")
            for i in range(3)
        ]
        with TemporaryDirectory() as tmp:
            store = JsonMinutesStore(root=Path(tmp))
            # Every feed is stale (empty store) so they're all eligible.
            from briarwood.local_intelligence.minutes_runner import run_refresh
            report = run_refresh(
                registry=feeds,
                store=store,
                discoverer=StubDiscoverer({}),
                fetcher=StubFetcher(),
                summarizer=StubSummarizer(),
                now=FIXED_NOW,
                max_feeds=2,
            )
        checked = [r for r in report.results if r.checked]
        self.assertEqual(len(checked), 2)


class JsonMinutesStoreTests(unittest.TestCase):
    def test_round_trip(self):
        with TemporaryDirectory() as tmp:
            store = JsonMinutesStore(root=Path(tmp))
            feed = _feed()
            record = store.load_or_initialize(feed)
            record.entries.append(
                MinuteEntry(month="2026-03", board=feed.board, status="fetched", summary="s")
            )
            record.last_checked_at = FIXED_NOW.isoformat()
            store.save(feed, record)

            reloaded = store.load(feed)
            self.assertIsNotNone(reloaded)
            self.assertEqual(len(reloaded.entries), 1)
            self.assertEqual(reloaded.entries[0].month, "2026-03")


if __name__ == "__main__":
    unittest.main()
