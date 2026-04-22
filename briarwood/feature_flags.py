"""Process-level feature flags. Read once at import; no runtime toggling."""
from __future__ import annotations
import os


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_set(name: str) -> frozenset[str]:
    raw = os.environ.get(name, "")
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


CLAIMS_ENABLED: bool = _env_bool("BRIARWOOD_CLAIMS_ENABLED", default=False)
CLAIMS_PROPERTY_IDS: frozenset[str] = _env_set("BRIARWOOD_CLAIMS_PROPERTY_IDS")


def claims_enabled_for(property_id: str | None) -> bool:
    """True if the new claim-object pipeline should run for this property."""
    if not CLAIMS_ENABLED:
        return False
    if not CLAIMS_PROPERTY_IDS:
        return True
    return (property_id or "") in CLAIMS_PROPERTY_IDS
