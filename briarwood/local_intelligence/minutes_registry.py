"""Per-town minutes feed registry.

Each entry describes ONE board's published-minutes feed for ONE town. Adding
a new town is a one-line change here — the refresh runner picks it up on
the next scan. Keep URL templates parameterized by ``{year}`` so the same
entry works across years without editing.

Scalability notes for future maintainers:
- Towns that publish a yearly index page (Avon's pattern) use
  ``index_url_template``. The runner discovers monthly document URLs by
  scraping that index.
- Towns that publish each month at a direct URL (e.g.
  ``.../minutes/2026-03.pdf``) can extend ``direct_url_template`` instead —
  the runner prefers that when present.
- Staleness and rolling window are per-feed so rural towns with quarterly
  meetings can set a longer TTL without starving active towns.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class MinutesFeed:
    """One board's minutes feed for one town."""

    town: str
    state: str
    board: str  # "planning_board", "zoning_board", "council", etc.
    index_url_template: str | None = None
    direct_url_template: str | None = None
    stale_after_days: int = 30
    rolling_window_months: int = 12
    tags: list[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        raw = f"{self.town}-{self.state}-{self.board}".lower()
        cleaned = "".join(ch if ch.isalnum() else "-" for ch in raw)
        while "--" in cleaned:
            cleaned = cleaned.replace("--", "-")
        return cleaned.strip("-")


MINUTES_REGISTRY: list[MinutesFeed] = [
    MinutesFeed(
        town="Avon-by-the-Sea",
        state="NJ",
        board="planning_board",
        index_url_template="https://www.avonbytheseanj.com/government/planning_board/{year}.php",
        stale_after_days=30,
        rolling_window_months=12,
        tags=["shore", "monmouth", "zoning-sensitive"],
    ),
]


def get_feed(slug: str) -> MinutesFeed | None:
    for feed in MINUTES_REGISTRY:
        if feed.slug == slug:
            return feed
    return None


def feeds_for_town(*, town: str, state: str) -> list[MinutesFeed]:
    t = town.strip().lower()
    s = state.strip().upper()
    return [f for f in MINUTES_REGISTRY if f.town.lower() == t and f.state.upper() == s]


__all__ = [
    "MINUTES_REGISTRY",
    "MinutesFeed",
    "feeds_for_town",
    "get_feed",
]
