#!/usr/bin/env bash
# Boot-time setup for the Briarwood API container on Fly.
#
# Fly mounts the persistent volume at /app/data, which masks any seed data
# baked into /app/data in the image. This script ensures the runtime data
# tree exists on the volume and copies seed datasets from /opt/seed (in the
# image) onto /app/data using cp -rn (no clobber) — so the first boot
# populates a fresh volume, and subsequent boots leave the volume's existing
# files untouched.
#
# To force-refresh seed data after a Dockerfile rebuild, ssh into the VM and
# rm the relevant /app/data/<seed-dir> entries before redeploying — the
# next boot will repopulate from /opt/seed.
set -euo pipefail

DATA_ROOT="/app/data"
SEED_ROOT="/opt/seed"

# Runtime directories the app needs to write to. Created on the volume if
# they don't already exist.
mkdir -p \
  "${DATA_ROOT}/web" \
  "${DATA_ROOT}/saved_properties" \
  "${DATA_ROOT}/learning" \
  "${DATA_ROOT}/outcomes" \
  "${DATA_ROOT}/agent_artifacts" \
  "${DATA_ROOT}/agent_sessions" \
  "${DATA_ROOT}/cache/searchapi_zillow"

# Seed data: copy from image to volume on first boot only.
if [ -d "${SEED_ROOT}" ]; then
  for sub in comps local_intelligence eval town_county; do
    if [ -d "${SEED_ROOT}/${sub}" ]; then
      mkdir -p "${DATA_ROOT}/${sub}"
      # cp -rn: no-clobber, preserves volume's existing files. -T-equivalent
      # via the trailing /. so the contents (not the dir itself) are merged.
      cp -rn "${SEED_ROOT}/${sub}/." "${DATA_ROOT}/${sub}/"
    fi
  done
fi

exec "$@"
