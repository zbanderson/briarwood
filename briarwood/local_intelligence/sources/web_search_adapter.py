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

from dataclasses import dataclass, field
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlencode
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


@dataclass(slots=True)
class WebSearchOptions:
    """Provider-agnostic search controls with Tavily-aligned fields."""

    search_depth: str | None = None
    topic: str | None = None
    include_domains: list[str] = field(default_factory=list)
    exclude_domains: list[str] = field(default_factory=list)
    time_range: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    include_raw_content: bool = False
    include_usage: bool = False
    auto_parameters: bool = False


@dataclass(slots=True)
class TavilyExtractOptions:
    """Optional Tavily Extract step after search result discovery."""

    enabled: bool = False
    extract_depth: str = "basic"
    format: str = "markdown"
    include_images: bool = False
    include_favicon: bool = False
    include_usage: bool = False


@dataclass(slots=True)
class TavilyCrawlOptions:
    """Selective Tavily Crawl settings for stable municipal sites."""

    max_depth: int | None = None
    instructions: str | None = None
    select_domains: list[str] = field(default_factory=list)
    exclude_domains: list[str] = field(default_factory=list)
    select_paths: list[str] = field(default_factory=list)
    exclude_paths: list[str] = field(default_factory=list)
    extract_depth: str | None = None
    include_images: bool = False
    include_favicon: bool = False
    include_usage: bool = False


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
        search_fn: Callable[..., Any] | None = None,
        search_options: WebSearchOptions | None = None,
        extract_options: TavilyExtractOptions | None = None,
        extract_fn: Callable[..., Any] | None = None,
        crawl_fn: Callable[..., Any] | None = None,
        project_id: str | None = None,
    ) -> None:
        self.provider, self.api_key = self._resolve_provider(provider, api_key)
        self.max_results = max(1, int(max_results))
        self.timeout_seconds = timeout_seconds
        self._fetcher = fetcher or _default_fetcher(timeout_seconds)
        self._text_extractor = text_extractor or _default_text_extractor
        # Injectable search for tests — bypasses the HTTP layer.
        self._search_fn = search_fn
        self.search_options = search_options or WebSearchOptions()
        self.extract_options = extract_options or TavilyExtractOptions()
        self._extract_fn = extract_fn
        self._crawl_fn = crawl_fn
        self.project_id = project_id or os.environ.get("TAVILY_PROJECT")

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
            results, usage = self._run_search(query)
        except Exception as exc:  # pragma: no cover - network specific
            logger.warning("Web search failed for %s: %s", query, exc)
            return []

        extracted_by_url: dict[str, dict[str, Any]] = {}
        if self.provider == "tavily" and self.extract_options.enabled:
            try:
                extracted_by_url, extract_usage = self._extract_search_results(results)
                usage = _merge_usage(usage, extract_usage)
            except Exception as exc:  # pragma: no cover - network specific
                logger.warning("Tavily extract failed for %s: %s", query, exc)

        documents: list[MunicipalSourceDocument] = []
        for result in results[: self.max_results]:
            url = str(result.get("url") or "").strip()
            if not url:
                continue
            extracted = extracted_by_url.get(url)
            if extracted is not None:
                text = str(extracted.get("raw_content") or "").strip()
            elif result.get("raw_content"):
                text = str(result.get("raw_content") or "").strip()
            else:
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
                        "published_at": result.get("published_at"),
                        "score": result.get("score"),
                        "search_options": _search_options_metadata(self.search_options),
                        "extract_enabled": self.provider == "tavily" and self.extract_options.enabled,
                        "extract_options": _extract_options_metadata(self.extract_options),
                        "project_id": self.project_id,
                        "usage": usage,
                    },
                }
            )
        return documents

    def crawl(
        self,
        *,
        url: str,
        options: TavilyCrawlOptions | None = None,
    ) -> list[dict[str, Any]]:
        """Crawl a stable site section when search is too shallow."""

        if self.provider != "tavily" or not self.api_key:
            return []
        crawl_options = options or TavilyCrawlOptions()
        crawl_fn = self._crawl_fn or _tavily_crawl
        payload = _call_with_optional_project(
            crawl_fn,
            self.api_key,
            url,
            self.timeout_seconds,
            crawl_options,
            self.project_id,
        )
        return payload.get("results", []) if isinstance(payload, dict) else []

    def _run_search(self, query: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        search_impl = self._search_fn or self._provider_search
        response = _call_search_impl(search_impl, query, self.max_results, self.search_options)
        if isinstance(response, tuple) and len(response) == 2:
            results, usage = response
        else:
            results, usage = response, None
        return list(results or []), usage if isinstance(usage, dict) else None

    def _extract_search_results(
        self,
        results: list[dict[str, Any]],
    ) -> tuple[dict[str, dict[str, Any]], dict[str, Any] | None]:
        urls = [str(row.get("url") or "").strip() for row in results if row.get("url")]
        urls = [url for url in urls if url]
        if not urls:
            return {}, None
        extract_impl = self._extract_fn or _tavily_extract
        response = _call_with_optional_project(
            extract_impl,
            self.api_key,
            urls,
            self.timeout_seconds,
            self.extract_options,
            self.project_id,
        )
        if not isinstance(response, dict):
            return {}, None
        extracted_by_url = {
            str(item.get("url")): item
            for item in response.get("results", [])
            if isinstance(item, dict) and item.get("url")
        }
        usage = response.get("usage")
        return extracted_by_url, usage if isinstance(usage, dict) else None

    def _provider_search(self, query: str, max_results: int) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        if self.provider == "tavily":
            return _tavily_search(
                self.api_key,
                query,
                max_results,
                self.timeout_seconds,
                self.search_options,
                self.project_id,
            )
        if self.provider == "serper":
            return _serper_search(self.api_key, query, max_results, self.timeout_seconds), None
        if self.provider == "brave":
            return _brave_search(self.api_key, query, max_results, self.timeout_seconds), None
        return [], None


def _focus_to_query(focus: list[str] | None) -> str:
    if not focus:
        return "planning board zoning"
    terms: list[str] = []
    for f in focus:
        term = _FOCUS_QUERY_TERMS.get(f) or f.replace("_", " ")
        if term not in terms:
            terms.append(term)
    return " ".join(terms)


def _tavily_search(
    api_key: str,
    query: str,
    max_results: int,
    timeout: float,
    options: WebSearchOptions,
    project_id: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    body_dict: dict[str, Any] = {
        "query": query,
        "max_results": max_results,
    }
    if options.search_depth:
        body_dict["search_depth"] = options.search_depth
    if options.topic:
        body_dict["topic"] = options.topic
    if options.include_domains:
        body_dict["include_domains"] = options.include_domains
    if options.exclude_domains:
        body_dict["exclude_domains"] = options.exclude_domains
    if options.time_range:
        body_dict["time_range"] = options.time_range
    if options.start_date:
        body_dict["start_date"] = options.start_date
    if options.end_date:
        body_dict["end_date"] = options.end_date
    if options.include_raw_content:
        body_dict["include_raw_content"] = "markdown"
    if options.include_usage:
        body_dict["include_usage"] = True
    if options.auto_parameters:
        body_dict["auto_parameters"] = True
    body = json.dumps(body_dict).encode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if project_id:
        headers["X-Project-ID"] = project_id
    req = Request(
        "https://api.tavily.com/search",
        data=body,
        headers=headers,
    )
    with urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read())
    results = [
        {
            "title": r.get("title"),
            "url": r.get("url"),
            "snippet": r.get("content"),
            "published_at": r.get("published_date"),
            "score": r.get("score"),
            "raw_content": r.get("raw_content"),
        }
        for r in data.get("results", [])
    ]
    usage = data.get("usage")
    return results, usage if isinstance(usage, dict) else None


def _tavily_extract(
    api_key: str,
    urls: list[str],
    timeout: float,
    options: TavilyExtractOptions,
    project_id: str | None = None,
) -> dict[str, Any]:
    body_dict: dict[str, Any] = {
        "urls": urls,
        "extract_depth": options.extract_depth,
        "format": options.format,
        "include_images": options.include_images,
        "include_favicon": options.include_favicon,
    }
    if options.include_usage:
        body_dict["include_usage"] = True
    req_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if project_id:
        req_headers["X-Project-ID"] = project_id
    req = Request(
        "https://api.tavily.com/extract",
        data=json.dumps(body_dict).encode(),
        headers=req_headers,
    )
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read())


def _tavily_crawl(
    api_key: str,
    url: str,
    timeout: float,
    options: TavilyCrawlOptions,
    project_id: str | None = None,
) -> dict[str, Any]:
    body_dict: dict[str, Any] = {
        "url": url,
        "include_images": options.include_images,
        "include_favicon": options.include_favicon,
    }
    if options.max_depth is not None:
        body_dict["max_depth"] = options.max_depth
    if options.instructions:
        body_dict["instructions"] = options.instructions
    if options.select_domains:
        body_dict["select_domains"] = options.select_domains
    if options.exclude_domains:
        body_dict["exclude_domains"] = options.exclude_domains
    if options.select_paths:
        body_dict["select_paths"] = options.select_paths
    if options.exclude_paths:
        body_dict["exclude_paths"] = options.exclude_paths
    if options.extract_depth:
        body_dict["extract_depth"] = options.extract_depth
    if options.include_usage:
        body_dict["include_usage"] = True
    req_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if project_id:
        req_headers["X-Project-ID"] = project_id
    req = Request(
        "https://api.tavily.com/crawl",
        data=json.dumps(body_dict).encode(),
        headers=req_headers,
    )
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read())


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


def _call_search_impl(
    search_impl: Callable[..., Any],
    query: str,
    max_results: int,
    options: WebSearchOptions,
) -> Any:
    try:
        return search_impl(query, max_results, options)
    except TypeError:
        return search_impl(query, max_results)


def _call_with_optional_project(
    fn: Callable[..., Any],
    api_key: str,
    payload: Any,
    timeout: float,
    options: Any,
    project_id: str | None,
) -> Any:
    try:
        return fn(api_key, payload, timeout, options, project_id)
    except TypeError:
        return fn(api_key, payload, timeout, options)


def _merge_usage(
    current: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not current and not incoming:
        return None
    merged = dict(current or {})
    for key, value in (incoming or {}).items():
        if isinstance(value, (int, float)) and isinstance(merged.get(key), (int, float)):
            merged[key] = merged[key] + value
        else:
            merged[key] = value
    return merged


def _search_options_metadata(options: WebSearchOptions) -> dict[str, Any]:
    return {
        "search_depth": options.search_depth,
        "topic": options.topic,
        "include_domains": list(options.include_domains),
        "exclude_domains": list(options.exclude_domains),
        "time_range": options.time_range,
        "start_date": options.start_date,
        "end_date": options.end_date,
        "include_raw_content": options.include_raw_content,
        "include_usage": options.include_usage,
        "auto_parameters": options.auto_parameters,
    }


def _extract_options_metadata(options: TavilyExtractOptions) -> dict[str, Any]:
    return {
        "enabled": options.enabled,
        "extract_depth": options.extract_depth,
        "format": options.format,
        "include_images": options.include_images,
        "include_favicon": options.include_favicon,
        "include_usage": options.include_usage,
    }
