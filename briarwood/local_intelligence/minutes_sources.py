"""Discovery + extraction + summarization interfaces for the minutes runner.

Every external dependency the runner has (HTTP, PDF parsing, LLM) is hidden
behind a protocol here so tests can inject stubs and future providers can be
swapped in without touching orchestration code.

Default implementations reuse the fetch/extract primitives in
``briarwood.local_intelligence.collector`` so we don't duplicate the HTTP +
PDF plumbing.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, Protocol
from urllib.parse import quote, urljoin, urlparse, urlunparse

from briarwood.local_intelligence.minutes_registry import MinutesFeed

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DiscoveredMinutes:
    """A candidate month of minutes discovered on a town index page."""

    month: str  # "2026-03"
    source_url: str
    title: str | None = None


@dataclass(slots=True)
class ExtractedMinutes:
    """Fetched + extracted text for a single month of minutes."""

    month: str
    source_url: str
    raw_text: str
    title: str | None = None


@dataclass(slots=True)
class MinutesSummary:
    """Summarizer output for one month of minutes."""

    summary: str
    confidence: float | None = None
    tags: list[str] | None = None


class MinutesDiscoverer(Protocol):
    """Find month-level minute document URLs for a given feed/year."""

    def discover(self, feed: MinutesFeed, year: int) -> list[DiscoveredMinutes]:
        ...


class MinutesDocumentFetcher(Protocol):
    """Fetch and extract text from a discovered minutes document."""

    def fetch(self, discovered: DiscoveredMinutes) -> ExtractedMinutes | None:
        ...


class MinutesSummarizer(Protocol):
    """Summarize extracted minutes text into a terse decision-relevant digest."""

    def summarize(self, extracted: ExtractedMinutes) -> MinutesSummary:
        ...


# ─── Default implementations ──────────────────────────────────────────────

_MONTH_PATTERNS = [
    (
        re.compile(
            r"(?P<month>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
            r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)",
            re.IGNORECASE,
        ),
        "word",
    ),
    (re.compile(r"(?P<num>0?[1-9]|1[0-2])[-_/]"), "num"),
]


_MONTH_WORD_TO_NUM = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def _month_from_text(text: str, *, year: int) -> str | None:
    """Infer ``YYYY-MM`` from an anchor text or URL fragment."""

    lowered = text.lower()
    for pattern, kind in _MONTH_PATTERNS:
        match = pattern.search(lowered)
        if not match:
            continue
        if kind == "word":
            month_num = _MONTH_WORD_TO_NUM.get(match.group("month").lower())
        else:
            month_num = int(match.group("num"))
        if month_num:
            return f"{year:04d}-{month_num:02d}"
    return None


_DOC_EXT_PATTERN = re.compile(r"\.(?:pdf|docx?|doc)(?:\?[^\"'#]*)?$", re.IGNORECASE)


class HttpIndexDiscoverer:
    """Scrape a town's yearly index page for month-labeled minute documents.

    Two strategies are tried in order:

    1. **Table rows** — ``<tr>`` containing a date cell (e.g. "March 14, 2024")
       paired with an anchor cell whose text is "Minutes". This matches the
       common municipal CMS layout (Revize, Civica, Municode) where the
       filename itself carries no month word.
    2. **Anchor text / URL** — fallback for towns that link minutes as
       ``<a href="...pdf">March Minutes</a>`` directly.

    Towns with fundamentally different structures (JavaScript-rendered, portal
    logins, RSS feeds) should implement their own ``MinutesDiscoverer``.
    """

    def __init__(
        self,
        *,
        fetcher: Callable[[str], tuple[bytes, str | None]] | None = None,
    ) -> None:
        self._fetcher = fetcher

    def discover(self, feed: MinutesFeed, year: int) -> list[DiscoveredMinutes]:
        if not feed.index_url_template:
            return []
        index_url = feed.index_url_template.format(year=year)
        fetcher = self._fetcher or _default_http_fetcher()
        try:
            payload, _ct = fetcher(index_url)
        except Exception as exc:
            logger.warning("Failed to fetch minutes index %s: %s", index_url, exc)
            return []

        html = payload.decode("utf-8", errors="ignore")
        base_url = _extract_base_url(html, index_url)
        results: list[DiscoveredMinutes] = []
        seen: set[str] = set()

        for item in self._discover_table_rows(html, base_url=base_url, year=year):
            if item.source_url in seen:
                continue
            seen.add(item.source_url)
            results.append(item)

        # Anchor fallback is only useful when the page has no meeting table
        # (or the table produced nothing we could parse). Running it after a
        # successful table pass would double-count agenda vs. minutes links.
        if not results:
            for item in self._discover_anchors(html, base_url=base_url, year=year):
                if item.source_url in seen:
                    continue
                seen.add(item.source_url)
                results.append(item)

        return results

    @staticmethod
    def _discover_table_rows(
        html: str, *, base_url: str, year: int
    ) -> list[DiscoveredMinutes]:
        results: list[DiscoveredMinutes] = []
        row_pattern = re.compile(r"<tr[^>]*>(?P<body>.*?)</tr>", re.IGNORECASE | re.DOTALL)
        cell_pattern = re.compile(r"<td[^>]*>(?P<body>.*?)</td>", re.IGNORECASE | re.DOTALL)
        anchor_pattern = re.compile(
            r'<a[^>]+href\s*=\s*"(?P<href>[^"]+)"[^>]*>(?P<text>.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        for row in row_pattern.finditer(html):
            cells = [m.group("body") for m in cell_pattern.finditer(row.group("body"))]
            if not cells:
                continue
            date_text = re.sub(r"<[^>]+>", " ", cells[0]).strip()
            month = _month_from_text(date_text, year=year)
            if not month:
                continue
            # Find an anchor in any remaining cell whose visible text mentions
            # "minutes" and whose href is a document.
            picked: tuple[str, str] | None = None
            for cell in cells[1:]:
                for a in anchor_pattern.finditer(cell):
                    href = a.group("href").strip()
                    text = re.sub(r"<[^>]+>", " ", a.group("text")).strip()
                    if "minute" not in text.lower():
                        continue
                    if not _DOC_EXT_PATTERN.search(href):
                        continue
                    picked = (href, text)
                    break
                if picked:
                    break
            if not picked:
                continue
            href, text = picked
            absolute = urljoin(base_url, href)
            results.append(
                DiscoveredMinutes(
                    month=month,
                    source_url=absolute,
                    title=f"{date_text} {text}".strip(),
                )
            )
        return results

    @staticmethod
    def _discover_anchors(
        html: str, *, base_url: str, year: int
    ) -> list[DiscoveredMinutes]:
        results: list[DiscoveredMinutes] = []
        anchor_pattern = re.compile(
            r'<a[^>]+href="(?P<href>[^"]+\.(?:pdf|docx?))(?:\?[^"]*)?"[^>]*>(?P<text>.*?)</a>',
            re.IGNORECASE | re.DOTALL,
        )
        for match in anchor_pattern.finditer(html):
            href = match.group("href")
            text = re.sub(r"<[^>]+>", " ", match.group("text")).strip()
            combined = f"{text} {href}"
            month = _month_from_text(combined, year=year)
            if not month:
                continue
            absolute = urljoin(base_url, href)
            results.append(
                DiscoveredMinutes(month=month, source_url=absolute, title=text or None)
            )
        return results


class HttpMinutesFetcher:
    """Fetch and extract text from a discovered PDF/HTML minutes document."""

    def __init__(
        self,
        *,
        fetcher: Callable[[str], tuple[bytes, str | None]] | None = None,
    ) -> None:
        self._fetcher = fetcher

    def fetch(self, discovered: DiscoveredMinutes) -> ExtractedMinutes | None:
        from briarwood.local_intelligence.collector import (
            _extract_html_text,
            _extract_pdf_text,
        )

        fetcher = self._fetcher or _default_http_fetcher()
        fetch_url = _safe_url(discovered.source_url)
        try:
            payload, content_type = fetcher(fetch_url)
        except Exception as exc:
            logger.warning("Failed to fetch minutes document %s: %s", discovered.source_url, exc)
            return None

        # Strip the `?t=...` cache-buster when inspecting the extension.
        url_path = discovered.source_url.split("?", 1)[0].lower()
        lowered_ct = (content_type or "").lower()
        if url_path.endswith(".pdf") or "pdf" in lowered_ct:
            text = _extract_pdf_text(payload)
        elif url_path.endswith(".docx") or "officedocument" in lowered_ct:
            text = _extract_docx_text(payload)
        elif url_path.endswith(".doc") or "msword" in lowered_ct:
            text = ""  # legacy .doc parsing would need antiword / textract
        else:
            text = _extract_html_text(payload)

        if not text:
            return None
        return ExtractedMinutes(
            month=discovered.month,
            source_url=discovered.source_url,
            raw_text=text,
            title=discovered.title,
        )


class HeuristicSummarizer:
    """Non-LLM fallback summarizer used until the LLM summarizer is wired.

    Extracts the first ``max_sentences`` sentences plus any that contain
    decision-relevant keywords (variance, zoning, ordinance, approval, etc.).
    """

    KEYWORD_PATTERN = re.compile(
        r"\b(variance|zoning|ordinance|application|approv|denied|hearing|"
        r"planning|subdivision|site plan|moratorium|ADU|accessory)\b",
        re.IGNORECASE,
    )

    def __init__(self, *, max_sentences: int = 5) -> None:
        self.max_sentences = max_sentences

    def summarize(self, extracted: ExtractedMinutes) -> MinutesSummary:
        text = re.sub(r"\s+", " ", extracted.raw_text).strip()
        sentences = re.split(r"(?<=[.!?])\s+", text)
        picked: list[str] = sentences[: self.max_sentences]
        picked += [
            s for s in sentences[self.max_sentences :] if self.KEYWORD_PATTERN.search(s)
        ][:3]
        summary = " ".join(dict.fromkeys(picked))
        tags = sorted({m.group(0).lower() for m in self.KEYWORD_PATTERN.finditer(text)})
        confidence = 0.55 if tags else 0.35
        return MinutesSummary(summary=summary[:1200], confidence=confidence, tags=tags)


def _extract_base_url(html: str, fallback: str) -> str:
    """Honor the document's ``<base href>`` if present.

    Town CMSes (Revize especially) set ``<base href>`` to the site root, so
    relative anchor hrefs resolve against the root rather than the current
    page path. Ignoring this produces 404s for otherwise-valid documents.
    """

    match = re.search(r"<base[^>]+href=\"([^\"]+)\"", html, re.IGNORECASE)
    if match:
        return match.group(1)
    return fallback


def _safe_url(url: str) -> str:
    """Percent-encode path and query so URLs with spaces are fetchable.

    Town CMSes commonly expose filenames with spaces (``February 8, 2024
    Meeting Minutes.pdf``). ``urlopen`` rejects unencoded spaces, so we
    re-quote the path + query while preserving the scheme/host.
    """

    parsed = urlparse(url)
    quoted_path = quote(parsed.path, safe="/%:@+$,;=&")
    quoted_query = quote(parsed.query, safe="=&%+")
    return urlunparse(parsed._replace(path=quoted_path, query=quoted_query))


def _extract_docx_text(payload: bytes) -> str:
    """Extract body text from a ``.docx`` file without python-docx.

    Docx is a ZIP; the body lives in ``word/document.xml`` with run text
    wrapped in ``<w:t>`` elements. That's enough for a keyword-heuristic
    summarizer; for richer structure we'd install ``python-docx``.
    """

    import io
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            try:
                xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
            except KeyError:
                return ""
    except Exception:
        return ""

    texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml, flags=re.DOTALL)
    joined = " ".join(texts)
    # Unescape the small set of XML entities docx uses.
    joined = (
        joined.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    )
    return re.sub(r"\s+", " ", joined).strip()


_BUYER_LENS_SYSTEM_PROMPT = (
    "You read municipal planning/zoning board minutes and summarize them for a "
    "prospective property BUYER deciding whether to purchase in this town. "
    "You care about things that move property values or risk: variance grants "
    "and denials, zoning amendments, subdivision approvals, density changes, "
    "ADU / accessory-unit rulings, moratoriums, flood / beach / coastal "
    "decisions, infrastructure projects, tax-assessment talk, and contentious "
    "public comment that signals neighborhood direction. "
    "Output rules: 3-6 bullet points, each one sentence, no preamble, no "
    "closing remarks. If the minutes are procedural only (no decisions), say "
    "'Routine meeting; no decisions affecting buyers.' on a single line."
)


class LLMBuyerLensSummarizer:
    """LLM-backed summarizer tuned for property-buyer relevance.

    Falls back to ``HeuristicSummarizer`` when no LLM client is configured or
    the call fails — so adding a new town never hard-fails on an outage.
    """

    KEYWORD_TAGS = (
        "variance",
        "zoning",
        "ordinance",
        "subdivision",
        "site plan",
        "moratorium",
        "adu",
        "accessory",
        "approv",
        "denied",
        "flood",
        "coastal",
        "assessment",
    )

    def __init__(
        self,
        *,
        client: "LLMClient | None" = None,  # noqa: F821 - forward ref; imported lazily
        max_tokens: int = 320,
        max_input_chars: int = 12_000,
        fallback: MinutesSummarizer | None = None,
    ) -> None:
        self._client = client
        self._max_tokens = max_tokens
        self._max_input_chars = max_input_chars
        self._fallback = fallback or HeuristicSummarizer()

    def summarize(self, extracted: ExtractedMinutes) -> MinutesSummary:
        client = self._client or self._default_client()
        if client is None:
            return self._fallback.summarize(extracted)

        raw = re.sub(r"\s+", " ", extracted.raw_text).strip()
        if not raw:
            return self._fallback.summarize(extracted)
        excerpt = raw[: self._max_input_chars]

        user_prompt = (
            f"Town minutes from {extracted.month} (board: planning/zoning).\n"
            f"Source: {extracted.source_url}\n\n"
            f"=== BEGIN MINUTES ===\n{excerpt}\n=== END MINUTES ===\n\n"
            "Return the buyer-lens summary now."
        )

        try:
            text = client.complete(
                system=_BUYER_LENS_SYSTEM_PROMPT,
                user=user_prompt,
                max_tokens=self._max_tokens,
            )
        except Exception as exc:
            logger.warning("LLM summarize failed for %s: %s", extracted.source_url, exc)
            return self._fallback.summarize(extracted)

        summary = (text or "").strip()
        if not summary:
            return self._fallback.summarize(extracted)

        lowered_all = f"{summary.lower()} {raw.lower()}"
        tags = sorted({t for t in self.KEYWORD_TAGS if t in lowered_all})
        confidence = 0.75 if tags else 0.55
        return MinutesSummary(summary=summary[:2400], confidence=confidence, tags=tags)

    @staticmethod
    def _default_client():
        try:
            from briarwood.agent.llm import default_client
        except Exception:
            return None
        try:
            return default_client()
        except Exception:
            return None


def _default_http_fetcher():
    from briarwood.local_intelligence.collector import _default_fetcher

    return _default_fetcher(12.0)


__all__ = [
    "DiscoveredMinutes",
    "ExtractedMinutes",
    "HeuristicSummarizer",
    "HttpIndexDiscoverer",
    "HttpMinutesFetcher",
    "LLMBuyerLensSummarizer",
    "MinutesDiscoverer",
    "MinutesDocumentFetcher",
    "MinutesSummarizer",
    "MinutesSummary",
]
