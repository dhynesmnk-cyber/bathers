#!/usr/bin/env bash
# Runs on every container boot. The persistent Fly volume is mounted at
# /data — the live git checkout lives there (not baked into the image), so
# a `fly deploy` (which replaces the image) never loses the SQLite file,
# the staging queue, or temp_data.
set -euo pipefail

REPO_DIR="/data/repo"
REPO_URL="https://github.com/dhynesmnk-cyber/bathers.git"

if [ -z "${GITHUB_PAT:-}" ]; then
  echo "GITHUB_PAT is not set — set it with 'fly secrets set GITHUB_PAT=...'" >&2
  exit 1
fi

git config --global user.name "David"
git config --global user.email "d.hynes.mnk@gmail.com"
# Reads the token from the environment per-invocation — never written to
# .git/config or any file on disk.
git config --global credential.helper \
  '!f() { echo "username=x-access-token"; echo "password=$GITHUB_PAT"; }; f'

if [ ! -d "$REPO_DIR/.git" ]; then
  echo "cloning $REPO_URL into $REPO_DIR"
  git clone "$REPO_URL" "$REPO_DIR"
else
  echo "pulling latest into $REPO_DIR"
  git -C "$REPO_DIR" pull --ff-only
fi

cd "$REPO_DIR"

# Materialise .env from Fly secrets (injected as regular env vars) each boot.
# Never committed, never printed — mirrors .env.example's key set.
umask 077
cat > .env <<EOF
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
MODEL_HARVESTER=${MODEL_HARVESTER:-claude-haiku-4-5}
MODEL_ARCHITECT=${MODEL_ARCHITECT:-claude-sonnet-4-6}
MODEL_GATEKEEPER=${MODEL_GATEKEEPER:-claude-haiku-4-5}
ADMIN_PORT=${ADMIN_PORT:-8787}
GEOCODER=${GEOCODER:-}
GEOCODER_USER_AGENT=${GEOCODER_USER_AGENT:-}
GOOGLE_PLACES_API_KEY=${GOOGLE_PLACES_API_KEY:-}
GOATCOUNTER_API_TOKEN=${GOATCOUNTER_API_TOKEN:-}
GOATCOUNTER_SITE=${GOATCOUNTER_SITE:-}
ADMIN_USERNAME=${ADMIN_USERNAME:-}
ADMIN_PASSWORD=${ADMIN_PASSWORD:-}
SITE_URL=${SITE_URL:-}
EOF

# Safety net for requirements.txt drift between this image's build time and
# whatever's now on the branch just pulled — no-op if nothing changed.
pip install --no-cache-dir -q -r admin/requirements.txt

exec uvicorn admin.app:app --host 0.0.0.0 --port "${ADMIN_PORT:-8787}"
