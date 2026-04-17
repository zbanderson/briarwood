"""Per-adapter contract tests with mocked HTTP.

These tests do NOT hit the network. Each adapter is exercised against a
stubbed fetcher / search function that returns canned bytes.
"""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from briarwood.local_intelligence.collector import (
    MUNICIPAL_SOURCE_REGISTRY,
    MunicipalDocumentCollector,
    MunicipalSourceSeed,
)
from briarwood.local_intelligence.models import SourceType
from briarwood.local_intelligence.sources import StaticRegistryAdapter
from briarwood.local_intelligence.sources.minutes_feed_adapter import (
    MinutesFeedAdapter,
    MinutesFeedConfig,
)
from briarwood.local_intelligence.sources.web_search_adapter import WebSearchAdapter
from briarwood.local_intelligence.sources.web_search_adapter import (
    TavilyCrawlOptions,
    TavilyExtractOptions,
    WebSearchOptions,
)


def _fake_html(body: str) -> bytes:
    return f"<html><body><h1>{body}</h1></body></html>".encode()


class StaticRegistryAdapterTests(unittest.TestCase):
    def test_fetches_only_registered_seeds(self) -> None:
        seed = MunicipalSourceSeed(
            title="Test Minutes",
            url="https://example.gov/minutes.html",
            source_type=SourceType.PLANNING_BOARD_MINUTES,
            metadata={"published_at": "2024-06-01"},
        )
        registry = {("testville", "NJ"): [seed]}
        calls: list[str] = []

        def fetcher(url: str):
            calls.append(url)
            return _fake_html("Planning Board minutes body"), "text/html"

        def extractor(payload: bytes, *, content_type, url):
            return payload.decode("utf-8")

        adapter = StaticRegistryAdapter(
            registry=registry,
            fetcher=fetcher,
            text_extractor=extractor,
        )
        docs = adapter.fetch(town="Testville", state="NJ")
        self.assertEqual(calls, ["https://example.gov/minutes.html"])
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["title"], "Test Minutes")
        self.assertIn("Planning Board", docs[0]["raw_text"])

    def test_returns_empty_when_town_not_registered(self) -> None:
        adapter = StaticRegistryAdapter(
            registry={},
            fetcher=lambda url: (b"", None),
            text_extractor=lambda payload, *, content_type, url: "",
        )
        self.assertEqual(adapter.fetch(town="Nowhere", state="NJ"), [])


class WebSearchAdapterTests(unittest.TestCase):
    def test_disabled_without_api_key_returns_empty(self) -> None:
        # No key, no search_fn injected → adapter must no-op silently.
        adapter = WebSearchAdapter(provider=None, api_key=None)
        self.assertEqual(adapter.fetch(town="Avon by the Sea", state="NJ"), [])

    def test_search_fn_drives_url_fetch(self) -> None:
        def fake_search(query: str, max_results: int):
            self.assertIn("Avon by the Sea", query)
            self.assertIn("zoning", query)
            return [{"title": "Zoning Update", "url": "https://example.gov/zoning", "snippet": "..."}]

        def fetcher(url: str):
            return _fake_html("Zoning ordinance text"), "text/html"

        def extractor(payload: bytes, *, content_type, url):
            return payload.decode("utf-8")

        adapter = WebSearchAdapter(
            provider="tavily",
            api_key="test",  # not used because search_fn short-circuits
            search_fn=fake_search,
            fetcher=fetcher,
            text_extractor=extractor,
            max_results=3,
        )
        docs = adapter.fetch(town="Avon by the Sea", state="NJ", focus=["zoning_unverified"])
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["url"], "https://example.gov/zoning")
        self.assertEqual(docs[0]["metadata"]["focus"], ["zoning_unverified"])

    def test_respects_max_results_cap(self) -> None:
        def fake_search(q, n):
            return [{"title": f"r{i}", "url": f"https://ex/{i}", "snippet": ""} for i in range(10)]

        adapter = WebSearchAdapter(
            provider="tavily",
            api_key="test",
            search_fn=fake_search,
            fetcher=lambda url: (_fake_html("x"), "text/html"),
            text_extractor=lambda p, *, content_type, url: p.decode("utf-8"),
            max_results=2,
        )
        self.assertEqual(len(adapter.fetch(town="T", state="NJ")), 2)

    def test_tavily_search_options_and_extract_are_added_to_metadata(self) -> None:
        captured: dict[str, object] = {}

        def fake_search(query: str, max_results: int, options: WebSearchOptions):
            captured["query"] = query
            captured["max_results"] = max_results
            captured["options"] = options
            return (
                [
                    {
                        "title": "Planning Board Minutes",
                        "url": "https://example.gov/minutes",
                        "snippet": "search snippet",
                        "published_at": "2026-01-20",
                        "score": 0.92,
                    }
                ],
                {"credits": 1},
            )

        def fake_extract(api_key, urls, timeout, options, project_id):
            captured["extract_api_key"] = api_key
            captured["extract_urls"] = urls
            captured["extract_options"] = options
            captured["project_id"] = project_id
            return {
                "results": [
                    {
                        "url": urls[0],
                        "raw_content": "# Minutes\nTown council planning discussion",
                    }
                ],
                "usage": {"credits": 2},
            }

        adapter = WebSearchAdapter(
            provider="tavily",
            api_key="test",
            search_fn=fake_search,
            extract_fn=fake_extract,
            max_results=2,
            search_options=WebSearchOptions(
                search_depth="advanced",
                topic="news",
                include_domains=["example.gov"],
                start_date="2026-01-01",
                end_date="2026-01-31",
                include_raw_content=True,
                include_usage=True,
            ),
            extract_options=TavilyExtractOptions(
                enabled=True,
                extract_depth="advanced",
                include_usage=True,
            ),
            project_id="local-intel",
        )
        docs = adapter.fetch(town="Belmar", state="NJ", focus=["development"])
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["cleaned_text"], "# Minutes Town council planning discussion")
        self.assertEqual(docs[0]["metadata"]["usage"]["credits"], 3)
        self.assertEqual(docs[0]["metadata"]["search_options"]["search_depth"], "advanced")
        self.assertTrue(docs[0]["metadata"]["extract_enabled"])
        self.assertEqual(captured["project_id"], "local-intel")

    def test_tavily_crawl_uses_option_payload(self) -> None:
        captured: dict[str, object] = {}

        def fake_crawl(api_key, url, timeout, options, project_id):
            captured["api_key"] = api_key
            captured["url"] = url
            captured["options"] = options
            captured["project_id"] = project_id
            return {"results": [{"url": "https://example.gov/docs/1", "raw_content": "Minutes"}]}

        adapter = WebSearchAdapter(
            provider="tavily",
            api_key="test",
            crawl_fn=fake_crawl,
            project_id="minutes-refresh",
        )
        results = adapter.crawl(
            url="https://example.gov",
            options=TavilyCrawlOptions(
                max_depth=2,
                instructions="Find planning board and ordinance pages",
                select_paths=["/docs/.*"],
            ),
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(captured["project_id"], "minutes-refresh")
        self.assertEqual(captured["options"].max_depth, 2)


class MinutesFeedAdapterTests(unittest.TestCase):
    def test_returns_empty_when_town_not_configured(self) -> None:
        adapter = MinutesFeedAdapter(registry={})
        self.assertEqual(adapter.fetch(town="Avon", state="NJ"), [])

    def test_monthly_strategy_tries_lookback_window(self) -> None:
        tries: list[str] = []

        def fetcher(url: str):
            tries.append(url)
            if "2024-06" in url:
                return _fake_html("June minutes"), "text/html"
            raise RuntimeError("not found")

        def extractor(payload, *, content_type, url):
            return payload.decode("utf-8")

        cfg = MinutesFeedConfig(
            url_template="https://town.gov/minutes-{year}-{month:02d}.html",
            lookback_months=3,
        )
        adapter = MinutesFeedAdapter(
            registry={("testville", "NJ"): [cfg]},
            fetcher=fetcher,
            text_extractor=extractor,
            today=date(2024, 6, 15),
        )
        docs = adapter.fetch(town="Testville", state="NJ")
        self.assertEqual(len(tries), 3)  # 3-month lookback
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["published_at"], "2024-06-01")


class CollectorWithMultipleAdaptersTests(unittest.TestCase):
    def test_collector_merges_adapters_and_dedupes_urls(self) -> None:
        class FakeAdapterA:
            name = "a"
            def fetch(self, *, town, state, focus=None):
                return [{"title": "A", "url": "https://x/1", "raw_text": "body", "source_type": "news"}]

        class FakeAdapterB:
            name = "b"
            def fetch(self, *, town, state, focus=None):
                # Duplicate URL should be deduped against adapter A.
                return [
                    {"title": "B1 dup", "url": "https://x/1", "raw_text": "dup", "source_type": "news"},
                    {"title": "B2", "url": "https://x/2", "raw_text": "body", "source_type": "news"},
                ]

        with TemporaryDirectory() as tmp:
            collector = MunicipalDocumentCollector(
                adapters=[FakeAdapterA(), FakeAdapterB()],
                cache_root=Path(tmp),
            )
            docs = collector.collect(town="T", state="NJ", use_cache=False)
            urls = [d["url"] for d in docs]
            self.assertEqual(urls, ["https://x/1", "https://x/2"])

    def test_focus_bypasses_cache(self) -> None:
        """Research calls (focus != None) must re-fetch even if cache exists."""
        call_count = {"n": 0}

        class CountingAdapter:
            name = "c"
            def fetch(self, *, town, state, focus=None):
                call_count["n"] += 1
                return [{"title": "X", "url": "https://x/1", "raw_text": "body", "source_type": "news"}]

        with TemporaryDirectory() as tmp:
            collector = MunicipalDocumentCollector(
                adapters=[CountingAdapter()],
                cache_root=Path(tmp),
            )
            collector.collect(town="T", state="NJ")  # populates cache
            collector.collect(town="T", state="NJ")  # hits cache
            collector.collect(town="T", state="NJ", focus=["zoning"])  # bypasses
            self.assertEqual(call_count["n"], 2)  # call #2 was served from cache


if __name__ == "__main__":
    unittest.main()
