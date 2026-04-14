"""WebSearchAdapter — adaptive discovery of town-scoped documents via a search API.

Supports Tavily, Serper (Google), and Brave. One provider is selected by
``provider`` argument or auto-detected from environment variables:

  - ``TAVILY_API_KEY`` → tavily
  - ``SERPER_API_KEY`` → serper
  - ``BRAVE_SEARCH_API_KEY`` → brave

If no key is found, the adapter disables itself and returns no documents —
it never raises. Cost control lives in the caller: ``max_results`` bounds
how many URLs are fetched per query; the collector's outer budget bounds
wall-clock.

``focus`` hints are mapped to query terms (e.g. ``zoning_unverified`` →
"zoning ordinance"). Each hit is fetched, stripped to text, and returned
as a document dict.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from briarwood.local_intelligence.models import SourceType
from briarwood.local_intelligence.sources.base import MunicipalSourceDocument

logger = logging.getLogger(__name__)

_FOCUS_QUERY_TERMS = {
    "zoning_unverified": "zoning ordinance",
    "zoning": "zoning ordinance",
    "weak_town_context": "planning board minutes short-term rental development",
    "short_term_rental": "short-term rental ordinance airbnb",
    "flood": "flood zone ordinance",
    "development": "planning board approvals",
}


class WebSearchAdapter:
    """Search-API-backed municipal document discovery."""

    name = "web_search"

    def __init__(
        self,
        *,
        provider: str | None = None,
        api_key: str | None = None,
        max_results: int = 4,
        fetcher: Callable[[str], tuple[bytes, str | None]] | None = None,
        text_extractor: Callable[..., str] | None = None,
        timeout_seconds: float = 10.0,
        search_fn: Callable[[str, int], list[dict]] | None = None,
    ) -> None:
        self.provider, self.api_key = self._resolve_provider(provider, api_key)
        self.max_results = max(1, int(max_results))
        self.timeout_seconds = timeout_seconds
        self._fetcher = fetcher or _default_fetcher(timeout_seconds)
        self._text_extractor = text_extractor or _default_text_extractor
        # Injectable search for tests — bypasses the HTTP layer.
        self._search_fn = search_fn

    @staticmethod
    def _resolve_provider(provider: str | None, api_key: str | None) -> tuple[str | None, str | None]:
        if provider and api_key:
            return provider, api_key
        if provider:
            env_map = {"tavily": "TAVILY_API_KEY", "serper": "SERPER_API_KEY", "brave": "BRAVE_SEARCH_API_KEY"}
            return provider, os.environ.get(env_map.get(provider, ""))
        for prov, env in (("tavily", "TAVILY_API_KEY"), ("serper", "SERPER_API_KEY"), ("brave", "BRAVE_SEARCH_API_KEY")):
            key = os.environ.get(env)
            if key:
                return prov, key
        return None, None

    def fetch(
        self,
        *,
        town: str,
        state: str,
        focus: list[str] | None = None,
    ) -> list[MunicipalSourceDocument]:
        if self._search_fn is None and (not self.provider or not self.api_key):
            logger.info("WebSearchAdapter disabled — no API key in environment.")
            return []

        query_terms = _focus_to_query(focus)
        query = f'"{town}" {state} {query_terms}'.strip()

        # Real API calls go through the cost guard; injected search_fn (tests) does not.
        if self._search_fn is None:
            from briarwood.cost_guard import BudgetExceeded, get_guard
            guard = get_guard()
            try:
                guard.check_websearch()
            except BudgetExceeded as exc:
                logger.warning("Skipping web search — %s", exc)
                return []
            guard.record_websearch()

        try:
            results = (self._search_fn or self._provider_search)(query, self.max_results)
        except Exception as exc:  # pragma: no cover - network specific
            logger.warning("Web search failed for %s: %s", query, exc)
            return []

        documents: list[MunicipalSourceDocument] = []
        for result in results[: self.max_results]:
            url = str(result.get("url") or "").strip()
            if not url:
                continue
            try:
                payload, content_type = self._fetcher(url)
            except Exception as exc:  # pragma: no cover - network specific
                logger.warning("Fetching web-search hit %s failed: %s", url, exc)
                continue
            text = self._text_extractor(payload, content_type=content_type, url=url)
            if not text:
                continue
            documents.append(
                {
                    "title": str(result.get("title") or url),
                    "url": url,
                    "source_type": SourceType.NEWS.value if "news" in url.lower() else SourceType.OTHER.value,
                    "published_at": result.get("published_at"),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "raw_text": text,
                    "cleaned_text": _clean_text(text),
                    "metadata": {
                        "provider": self.provider,
                        "query": query,
                        "focus": list(focus or []),
                        "snippet": result.get("snippet"),
                    },
                }
            )
        return documents

    def _provider_search(self, query: str, max_results: int) -> list[dict]:
        if self.provider == "tavily":
            return _tavily_search(self.api_key, query, max_results, self.timeout_seconds)
        if self.provider == "serper":
            return _serper_search(self.api_key, query, max_results, self.timeout_seconds)
        if self.provider == "brave":
            return _brave_search(self.api_key, query, max_results, self.timeout_seconds)
        return []


def _focus_to_query(focus: list[str] | None) -> str:
    if not focus:
        return "planning board zoning"
    terms: list[str] = []
    for f in focus:
        term = _FOCUS_QUERY_TERMS.get(f) or f.replace("_", " ")
        if term not in terms:
            terms.append(term)
    return " ".join(terms)


def _tavily_search(api_key: str, query: str, max_results: int, timeout: float) -> list[dict]:
    body = json.dumps({"api_key": api_key, "query": query, "max_results": max_results}).encode()
    req = Request(
        "https://api.tavily.com/search",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read())
    return [
        {"title": r.get("title"), "url": r.get("url"), "snippet": r.get("content")}
        for r in data.get("results", [])
    ]


def _serper_search(api_key: str, query: str, max_results: int, timeout: float) -> list[dict]:
    body = json.dumps({"q": query, "num": max_results}).encode()
    req = Request(
        "https://google.serper.dev/search",
        data=body,
        headers={"Content-Type": "application/json", "X-API-KEY": api_key},
    )
    with urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read())
    return [
        {"title": r.get("title"), "url": r.get("link"), "snippet": r.get("snippet")}
        for r in data.get("organic", [])
    ]


def _brave_search(api_key: str, query: str, max_results: int, timeout: float) -> list[dict]:
    url = "https://api.search.brave.com/res/v1/web/search?" + urlencode({"q": query, "count": max_results})
    req = Request(url, headers={"X-Subscription-Token": api_key, "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read())
    return [
        {"title": r.get("title"), "url": r.get("url"), "snippet": r.get("description")}
        for r in (data.get("web") or {}).get("results", [])
    ]


def _default_fetcher(timeout: float) -> Callable[[str], tuple[bytes, str | None]]:
    def fetch(url: str) -> tuple[bytes, str | None]:
        req = Request(url, headers={"User-Agent": "BriarwoodTownPulse/1.0"})
        with urlopen(req, timeout=timeout) as response:
            return response.read(), response.headers.get("Content-Type")

    return fetch


def _default_text_extractor(payload: bytes, *, content_type: str | None, url: str) -> str:
    from briarwood.local_intelligence.collector import _extract_html_text, _extract_pdf_text

    norm = (content_type or "").lower()
    if url.lower().endswith(".pdf") or "pdf" in norm:
        return _extract_pdf_text(payload)
    return _extract_html_text(payload)


def _clean_text(text: str) -> str:
    import re

    return re.sub(r"\s+", " ", text).strip()
