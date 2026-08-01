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
  echo "syncing $REPO_DIR to origin/main"
  git -C "$REPO_DIR" fetch --prune origin
  # The volume checkout accumulates runtime writes to *tracked, committed*
  # derived artefacts — data/directory.db (SQLite), site/src/data/venues.json
  # & forewords.json (regenerated on rebuild), and any _published files the
  # approve action rewrites. A plain `pull --ff-only` aborts on that dirt, and
  # under `set -e` that crash-loops the container. Hard-reset to the remote
  # instead: the committed versions of those derived files are authoritative,
  # and all gitignored volume-only state (claims.db, articles.db, temp_data/,
  # content-staging/, node_modules/) is left untouched by a tracked-file reset.
  git -C "$REPO_DIR" reset --hard origin/main
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
NETLIFY_AUTH_TOKEN=${NETLIFY_AUTH_TOKEN:-}
NETLIFY_SITE_ID=${NETLIFY_SITE_ID:-}
STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY:-}
STRIPE_WEBHOOK_SECRET=${STRIPE_WEBHOOK_SECRET:-}
STRIPE_PRICE_ONEOFF=${STRIPE_PRICE_ONEOFF:-}
STRIPE_PRICE_SUBSCRIPTION=${STRIPE_PRICE_SUBSCRIPTION:-}
SMTP_HOST=${SMTP_HOST:-}
SMTP_PORT=${SMTP_PORT:-587}
SMTP_USERNAME=${SMTP_USERNAME:-}
SMTP_PASSWORD=${SMTP_PASSWORD:-}
SMTP_FROM=${SMTP_FROM:-}
CLAIM_NOTIFY_EMAIL=${CLAIM_NOTIFY_EMAIL:-}
ADMIN_BASE_URL=${ADMIN_BASE_URL:-}
EOF

# Safety net for requirements.txt drift between this image's build time and
# whatever's now on the branch just pulled — no-op if nothing changed.
pip install --no-cache-dir -q -r admin/requirements.txt

# Build the public site so the admin has preview CSS and /site-dist views
# (node_modules persists on the volume, so this is fast after first boot).
# Non-fatal: a broken content file must never keep the admin itself down —
# that's the tool used to fix it.
if command -v npm >/dev/null 2>&1; then
  echo "building site (npm ci + npm run build)"
  (cd site && npm ci --no-audit --no-fund && npm run build) \
    || echo "WARNING: site build failed — preview styles and /site-dist views unavailable until fixed" >&2
else
  echo "WARNING: npm not available in this image — skipping site build" >&2
fi

exec uvicorn admin.app:app --host 0.0.0.0 --port "${ADMIN_PORT:-8787}"
