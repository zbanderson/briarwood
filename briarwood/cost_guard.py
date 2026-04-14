"""Process-wide API cost guardrails.

Hard caps per provider for the current process (session). Call sites check
the guard BEFORE making a request and record usage AFTER. Breaches raise
``BudgetExceeded``; dispatch catches and surfaces to the user.

Defaults are intentionally conservative — raise via env var when you want
more headroom.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field


class BudgetExceeded(Exception):
    """Raised when a provider budget would be breached by the next call."""


# Rough per-1K-token prices (USD). Good enough for a soft budget — if you
# need to the penny, wire an actual billing SDK.
_OPENAI_PRICES: dict[str, tuple[float, float]] = {
    # model -> (input $/1K, output $/1K)
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o": (0.0025, 0.01),
    "gpt-5-mini": (0.00025, 0.002),
    "gpt-5": (0.00125, 0.01),
    "o3-mini": (0.0011, 0.0044),
}
_DEFAULT_PRICE = (0.001, 0.004)  # fallback for unknown models


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class CostGuard:
    attom_calls: int = 0
    attom_cap: int = field(default_factory=lambda: _env_int("BRIARWOOD_BUDGET_ATTOM_CALLS", 50))
    websearch_calls: int = 0
    websearch_cap: int = field(default_factory=lambda: _env_int("BRIARWOOD_BUDGET_WEBSEARCH_CALLS", 20))
    openai_usd: float = 0.0
    openai_usd_cap: float = field(default_factory=lambda: _env_float("BRIARWOOD_BUDGET_OPENAI_USD", 1.00))
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # ---- ATTOM ----
    def check_attom(self) -> None:
        if self.attom_calls >= self.attom_cap:
            raise BudgetExceeded(
                f"ATTOM call cap reached ({self.attom_calls}/{self.attom_cap}); "
                f"raise BRIARWOOD_BUDGET_ATTOM_CALLS to continue."
            )

    def record_attom(self, *, from_cache: bool = False) -> None:
        if from_cache:
            return
        with self._lock:
            self.attom_calls += 1

    # ---- Web search ----
    def check_websearch(self) -> None:
        if self.websearch_calls >= self.websearch_cap:
            raise BudgetExceeded(
                f"Web-search call cap reached ({self.websearch_calls}/{self.websearch_cap}); "
                f"raise BRIARWOOD_BUDGET_WEBSEARCH_CALLS to continue."
            )

    def record_websearch(self) -> None:
        with self._lock:
            self.websearch_calls += 1

    # ---- OpenAI ----
    def check_openai(self) -> None:
        if self.openai_usd >= self.openai_usd_cap:
            raise BudgetExceeded(
                f"OpenAI spend cap reached (${self.openai_usd:.3f}/${self.openai_usd_cap:.2f}); "
                f"raise BRIARWOOD_BUDGET_OPENAI_USD to continue."
            )

    def record_openai(self, *, model: str, input_tokens: int, output_tokens: int) -> float:
        price_in, price_out = _OPENAI_PRICES.get(model, _DEFAULT_PRICE)
        cost = (input_tokens / 1000.0) * price_in + (output_tokens / 1000.0) * price_out
        with self._lock:
            self.openai_usd += cost
        return cost

    # ---- Summary ----
    def summary(self) -> str:
        return (
            f"ATTOM {self.attom_calls}/{self.attom_cap}, "
            f"web {self.websearch_calls}/{self.websearch_cap}, "
            f"openai ${self.openai_usd:.3f}/${self.openai_usd_cap:.2f}"
        )


_GUARD: CostGuard | None = None
_GLOBAL_LOCK = threading.Lock()


def get_guard() -> CostGuard:
    global _GUARD
    if _GUARD is None:
        with _GLOBAL_LOCK:
            if _GUARD is None:
                _GUARD = CostGuard()
    return _GUARD


def reset_guard() -> None:
    """Test hook — drop the process-wide guard so env vars are re-read."""
    global _GUARD
    with _GLOBAL_LOCK:
        _GUARD = None
