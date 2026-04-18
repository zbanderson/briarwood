"""Briarwood package."""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional local dependency
    load_dotenv = None


def _load_env_fallback(path: Path) -> None:
    """Load a simple .env file when python-dotenv is unavailable."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
if load_dotenv is not None:
    load_dotenv(_ENV_PATH)
else:  # pragma: no cover - exercised only where python-dotenv isn't installed
    _load_env_fallback(_ENV_PATH)
