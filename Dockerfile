# Briarwood API container — FastAPI + briarwood/ package, served by uvicorn.
#
# Build:   docker build -t briarwood-api .
# Run:     docker run --rm -p 8000:8000 --env-file .env briarwood-api
#
# Notes:
#   * Python 3.13 is the floor for the 3.14 venv used in dev. Slim-bookworm
#     is the smallest official image with a recent enough libc/openssl for the
#     httpx + cryptography stack.
#   * Data lives at /app/data and is intended to be backed by a Fly volume
#     mounted there (see fly.toml). The conversations.db, saved_properties/,
#     intelligence_feedback.jsonl, etc. all read/write under that prefix.
#   * No system Python override needed; uvicorn is invoked via the venv's
#     site-packages installed into the system interpreter inside the image.

FROM python:3.13-slim-bookworm

# Smaller, predictable runtime + don't write .pyc to the read-only layers.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Tooling: curl is useful for healthchecks; build-essential is needed only if
# a wheel is unavailable for the target arch. Keep the layer thin.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so subsequent code edits don't bust the wheel cache.
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/requirements.txt

# Copy application code. .dockerignore filters out venv/, data/public_records/,
# tests/, and dev artifacts so the image stays small.
COPY api /app/api
COPY briarwood /app/briarwood

# Ship read-only seed datasets to /opt/seed (NOT /app/data). The Fly volume
# mount at /app/data masks anything baked into /app/data on first boot, so
# seed data must live elsewhere in the image and be copied onto the volume
# at boot via the entrypoint script. /opt/seed is outside the volume mount.
COPY data/comps /opt/seed/comps
COPY data/local_intelligence /opt/seed/local_intelligence
COPY data/eval /opt/seed/eval
COPY data/town_county /opt/seed/town_county

# Entrypoint: ensures /app/data directory tree exists on the mounted volume,
# then no-clobber-copies seed data from /opt/seed onto the volume on first
# boot. Subsequent boots are no-ops because the seed paths already exist.
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

# Healthcheck — /healthz is unauthenticated and returns 200 unconditionally
# (see api/main.py).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# uvicorn directly. No reload, no auto-discovery — explicit module path so the
# container fails fast if the import surface drifts.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
