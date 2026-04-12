from __future__ import annotations

import io
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from briarwood.local_intelligence.models import SourceType

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MunicipalSourceSeed:
    title: str
    url: str
    source_type: SourceType
    metadata: dict[str, object] = field(default_factory=dict)


FetchResult = tuple[bytes, str | None]
Fetcher = Callable[[str], FetchResult]


class MunicipalDocumentCollector:
    """Collect a small set of known municipal source documents for Town Pulse."""

    def __init__(
        self,
        *,
        registry: dict[tuple[str, str], list[MunicipalSourceSeed]] | None = None,
        fetcher: Fetcher | None = None,
        cache_root: Path | None = None,
        timeout_seconds: float = 12.0,
    ) -> None:
        self.registry = registry or MUNICIPAL_SOURCE_REGISTRY
        self.fetcher = fetcher or _default_fetcher(timeout_seconds)
        self.cache_root = cache_root or Path(__file__).resolve().parents[2] / "data" / "local_intelligence" / "documents"

    def collect(self, *, town: str, state: str, use_cache: bool = True) -> list[dict[str, object]]:
        cache_path = self._cache_path(town=town, state=state)
        if use_cache:
            cached = self._load_cache(cache_path)
            if cached is not None:
                return cached

        seeds = self.registry.get((_normalize_town_key(town), state.strip().upper()), [])
        documents: list[dict[str, object]] = []
        for seed in seeds:
            try:
                payload, content_type = self.fetcher(seed.url)
            except Exception as exc:  # pragma: no cover - environment/network specific
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

        self._save_cache(cache_path, town=town, state=state, documents=documents)
        return documents

    def _extract_text(self, payload: bytes, *, content_type: str | None, url: str) -> str:
        normalized_content_type = (content_type or "").lower()
        if url.lower().endswith(".pdf") or "pdf" in normalized_content_type:
            return _extract_pdf_text(payload)
        return _extract_html_text(payload)

    def _cache_path(self, *, town: str, state: str) -> Path:
        slug = _slugify(f"{town}-{state}")
        return self.cache_root / f"{slug}.json"

    def _load_cache(self, path: Path) -> list[dict[str, object]] | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Cannot read municipal document cache %s: %s", path, exc)
            return None
        documents = payload.get("documents")
        return documents if isinstance(documents, list) else []

    def _save_cache(self, path: Path, *, town: str, state: str, documents: list[dict[str, object]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "town": town,
            "state": state,
            "attempted_at": datetime.now(timezone.utc).isoformat(),
            "documents": documents,
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def _default_fetcher(timeout_seconds: float) -> Fetcher:
    def fetch(url: str) -> FetchResult:
        request = Request(
            url,
            headers={"User-Agent": "BriarwoodTownPulse/1.0 (+https://github.com/openai/codex)"},
        )
        with urlopen(request, timeout=timeout_seconds) as response:  # pragma: no cover - network specific
            return response.read(), response.headers.get("Content-Type")

    return fetch


def _extract_pdf_text(payload: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            return ""
    try:
        reader = PdfReader(io.BytesIO(payload))
    except Exception:  # pragma: no cover - parser-specific failure path
        return ""
    parts: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:  # pragma: no cover - parser-specific failure path
            text = ""
        if text.strip():
            parts.append(text)
    return "\n".join(parts).strip()


def _extract_html_text(payload: bytes) -> str:
    try:
        text = payload.decode("utf-8", errors="ignore")
    except Exception:
        return ""
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return _clean_text(text)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalize_town_key(town: str) -> str:
    return _clean_text(town).lower()


def _slugify(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")


def _parse_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(f"{text}T00:00:00")
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


MUNICIPAL_SOURCE_REGISTRY: dict[tuple[str, str], list[MunicipalSourceSeed]] = {
    ("avon by the sea", "NJ"): [
        MunicipalSourceSeed(
            title="Avon Planning Board Meeting Minutes",
            url="https://www.avonbytheseanj.com/January%20Planning%20Board%20Meeting%20Minutes.pdf",
            source_type=SourceType.PLANNING_BOARD_MINUTES,
            metadata={"published_at": "2024-06-01"},
        ),
        MunicipalSourceSeed(
            title="Avon Planning Board Minutes Archive Sample",
            url="https://www.avonbytheseanj.com/Planning%20Board%20Meeting%20Minutes/2009/040209.pdf",
            source_type=SourceType.PLANNING_BOARD_MINUTES,
            metadata={"published_at": "2009-04-02"},
        ),
        MunicipalSourceSeed(
            title="Avon Board of Commissioners Meeting Minutes",
            url="https://www.avonbytheseanj.com/Town%20Hall%20Meeting%20Minutes/2020/Minutes_Regular_9-14-2020.pdf",
            source_type=SourceType.ORDINANCE,
            metadata={"published_at": "2020-09-14"},
        ),
    ],
}
