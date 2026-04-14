"""Parse what-if overrides from user text.

"what if i bought at 1.3M" -> {"ask_price": 1_300_000}
"renovate and price at $1.35m" -> {"ask_price": 1_350_000, "mode": "renovated"}

The override dict is applied to a property's inputs.json before the routed
pipeline runs, so the underwrite reflects the user's actual scenario
(entry basis, renovation stance) rather than the canonical listing.
"""

from __future__ import annotations

import json
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# "$1.3", "$1.3M", "1.3 million", "1,300,000", "1300000"
_PRICE_RE = re.compile(
    r"\$?\s*("
    r"(?:\d{1,3}(?:,\d{3})+)"              # 1,300,000
    r"|\d+(?:\.\d+)?\s*(?:m|mm|mil|million|k|thousand)?"  # 1.3m / 1300 / 1300k
    r")",
    re.IGNORECASE,
)

_PRICE_TRIGGER_RE = re.compile(
    r"\b("
    r"(?:what if|if i|assume|suppose|say)\s+(?:i\s+)?(?:buy|bought|paid|pay|offer|offered)"
    r"|(?:buy|bought|paid|pay|offer|offered)\s+(?:it\s+|this\s+)?(?:at|for)"
    r"|(?:bought|paid|pay|offer|offering|offered)\s+\$?\d"
    r"|(?:at|for)\s+\$?\d"
    r"|ask(?:ing)?\s+(?:price\s+)?(?:of\s+|at\s+)?\$?\d"
    r"|pric(?:e|ed)\s+at\s+\$?\d"
    r")",
    re.IGNORECASE,
)

_RENO_RE = re.compile(r"\b(renovate[d]?|renovation|fully renovated|post[- ]reno|after reno)\b", re.IGNORECASE)


def _to_dollars(raw: str, trailing: str) -> float | None:
    """Convert a price token + optional unit suffix to dollars."""
    cleaned = raw.replace(",", "").strip()
    try:
        base = float(cleaned)
    except ValueError:
        return None
    t = trailing.lower().strip()
    if t in ("m", "mm", "mil", "million"):
        base *= 1_000_000
    elif t in ("k", "thousand"):
        base *= 1_000
    else:
        # Bare numbers: "1.3" or "1.35" → millions (real-estate context);
        # "300" → thousands; "300000" / "1,300,000" → literal.
        if "," not in raw:
            if base < 10:  # "1.3", "2"
                base *= 1_000_000
            elif base < 1_000:  # "300", "500"
                base *= 1_000
    return base if base >= 10_000 else None  # sanity floor


def _extract_price(text: str, start: int = 0) -> float | None:
    """Find the first reasonable price at or after *start*.

    A price token with an explicit unit (``$``, ``m``, ``k``) wins over a
    bare number — so "526 w end ave ... for 1.3m" resolves to 1.3m, not
    the street number. Bare numbers are only accepted if no unit-qualified
    price exists in the region.
    """
    unit_hit: float | None = None
    bare_hit: float | None = None
    for match in re.finditer(
        r"(\$)?\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(m|mm|mil|million|k|thousand)?\b",
        text[start:],
        flags=re.IGNORECASE,
    ):
        dollar = match.group(1) or ""
        raw = match.group(2)
        trailing = match.group(3) or ""
        dollars = _to_dollars(raw, trailing)
        if dollars is None or dollars < 50_000:
            continue
        if dollar or trailing:
            unit_hit = dollars
            break
        if bare_hit is None:
            bare_hit = dollars
    return unit_hit if unit_hit is not None else bare_hit


def parse_overrides(text: str) -> dict[str, Any]:
    """Extract what-if overrides from a user turn.

    Returns an empty dict when nothing override-shaped is present.
    Keys: ``ask_price`` (float), ``mode`` ('renovated' | 'as_is').
    """
    overrides: dict[str, Any] = {}

    # Only parse a price when the sentence signals a what-if, not a random number.
    # Anchor price search at the trigger phrase so street numbers earlier in the
    # text ("526 w end ave ... for 1.3m") don't shadow the intended price.
    trigger = _PRICE_TRIGGER_RE.search(text)
    if trigger:
        price = _extract_price(text, start=trigger.start())
        if price is None:
            price = _extract_price(text)
        if price is not None:
            overrides["ask_price"] = price

    if _RENO_RE.search(text):
        overrides["mode"] = "renovated"

    return overrides


@contextmanager
def inputs_with_overrides(inputs_path: Path, overrides: dict[str, Any]):
    """Yield a tmp-file path containing the inputs json with overrides applied.

    Nothing is written if overrides is empty — the original path is yielded.
    """
    if not overrides:
        yield inputs_path
        return

    data = json.loads(inputs_path.read_text())
    facts = data.setdefault("facts", {})
    if "ask_price" in overrides:
        facts["purchase_price"] = float(overrides["ask_price"])
    if overrides.get("mode") == "renovated":
        facts["capex_lane"] = "full"

    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    try:
        json.dump(data, tmp)
        tmp.flush()
        tmp.close()
        yield Path(tmp.name)
    finally:
        Path(tmp.name).unlink(missing_ok=True)


def summarize(overrides: dict[str, Any]) -> str:
    """Human-readable one-liner for the CLI to echo back."""
    if not overrides:
        return ""
    bits = []
    if "ask_price" in overrides:
        bits.append(f"entry basis ${overrides['ask_price']:,.0f}")
    if overrides.get("mode") == "renovated":
        bits.append("full renovation")
    return "overrides applied: " + ", ".join(bits)
