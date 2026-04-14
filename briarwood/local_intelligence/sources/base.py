"""Adapter protocol for municipal source providers.

Adapters are deliberately minimal: one ``fetch`` method. The collector is
responsible for caching, deduping, and text extraction — adapters only
locate documents.

A ``MunicipalSourceDocument`` is a loose dict rather than a dataclass so the
shape matches the collector's existing persisted JSON schema without a
migration. Required keys: ``title``, ``url``, ``source_type``, ``raw_text``.
Optional: ``published_at`` (ISO), ``metadata`` (dict).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

MunicipalSourceDocument = dict[str, Any]


@runtime_checkable
class MunicipalSourceAdapter(Protocol):
    """A provider of municipal documents for a given town/state."""

    name: str

    def fetch(
        self,
        *,
        town: str,
        state: str,
        focus: list[str] | None = None,
    ) -> list[MunicipalSourceDocument]:
        """Return a list of source document dicts.

        ``focus`` is an optional list of topical hints (e.g. "zoning",
        "short_term_rental"). Adapters MAY use it to scope their query; they
        MUST NOT fail if it is empty.
        """
        ...
