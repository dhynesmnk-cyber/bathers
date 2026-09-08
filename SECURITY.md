# SECURITY.md — operating the admin app safely

Gate 12, 2026-09-08. Referenced from TRD.md §2's dated hosting-posture entry.

This file covers the running system, not the code: what holds credentials, how
often they turn over, and what to do in what order when one leaks. The controls
themselves live in `admin/security.py` (auth, throttling, caps, audit log) and
`admin/pipeline/backup.py` (snapshots and restore).

---

## 1. What is exposed, and what it holds

The **public site** (`wherewebathe.com`, Netlify) is static with no runtime
backend. It holds no secrets and executes no server code. Its only hardening is
the header block in `netlify.toml`.

The **admin app** (`bathers-admin`, Fly.io, syd) is reachable from the public
internet — see TRD.md §2. It holds:

| Credential | Blast radius if leaked |
|---|---|
| `GITHUB_PAT` | Push access to this repository — arbitrary published content |
| `STRIPE_SECRET_KEY` | Charges, refunds, customer records |
| `STRIPE_WEBHOOK_SECRET` | Forged payment events → unpaid claims auto-published and deployed |
| `ANTHROPIC_API_KEY` | Metered spend |
| `NETLIFY_AUTH_TOKEN` | Build status; site administration |
| `GOOGLE_PLACES_API_KEY` | Metered spend |
| `SMTP_PASSWORD` | Outbound mail from the site's own address |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Everything above, plus `claims.db`'s requester PII |

`ADMIN_PASSWORD` is the one that matters most: it is a single shared credential
with no second factor, and it fronts all the others.

### Unauthenticated paths

Three, and only three (`PUBLIC_PATHS` / `PUBLIC_PATH_PREFIXES` in `admin/app.py`):

- `POST /api/claims/submit` — the public claim form. Capped, type-sniffed and
  rate-limited three ways (per slug, per client, global).
- `POST /api/stripe/webhook` — signature-verified with stdlib `hmac`. This is
  the one path that writes published content and deploys with no human step,
  so `STRIPE_WEBHOOK_SECRET` is as sensitive as the Stripe key itself.
- `GET|POST /claim-action/<id>` — the owner's approve/deny links from the
  notification email. Authenticated by a 256-bit per-request `action_token`,
  constant-time compared, inert once the request leaves `pending`.

Adding a fourth is a deliberate act. It needs a line here saying why.

---

## 2. Rotation cadence

| Credential | Cadence | Notes |
|---|---|---|
| `ADMIN_PASSWORD` | 90 days | Also immediately on any laptop loss or shared-screen exposure |
| `GITHUB_PAT` | 90 days | Use a fine-grained token scoped to this repository only |
| `STRIPE_SECRET_KEY` | 180 days, or immediately on suspicion | Roll via Stripe's key-roll flow, which keeps the old key alive briefly |
| `STRIPE_WEBHOOK_SECRET` | On endpoint change | Stripe permits two active signing secrets during a roll |
| `ANTHROPIC_API_KEY` | 180 days | |
| `GOOGLE_PLACES_API_KEY` | 180 days | Restrict by API and by referrer/IP where the console allows |
| `NETLIFY_AUTH_TOKEN` | 180 days | |
| `SMTP_PASSWORD` | 180 days | An app password, never the mailbox's own password |

Rotation is `fly secrets set NAME=value`, which restarts the machine and
re-materialises `.env` from `docker-entrypoint.sh`. Rotate one at a time and
confirm the app boots between each — the entrypoint refuses to start without
admin credentials, so a typo is a crash loop, not a silent open door.

Never print a secret's value into a terminal, a log, a commit message or an
issue. `.env` is read-only to this project (CLAUDE.md rule 5).

---

## 3. If a credential leaks

Order matters. Revoke the ability to *change the world* before the ability to
*read* it.

1. **`GITHUB_PAT` first.** Revoke on GitHub. It is the only credential that can
   rewrite what the public sees.
2. **`STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`.** Roll both. Check
   Stripe's event log for `checkout.session.completed` events you cannot match
   to a `claims.db` row.
3. **`ADMIN_PASSWORD`.** Rotate, then read `data/audit.log` for the exposure
   window: every state-changing request is there with its client address and
   whether it was authenticated.
4. **Metered keys** (`ANTHROPIC_API_KEY`, `GOOGLE_PLACES_API_KEY`) and
   `NETLIFY_AUTH_TOKEN`, `SMTP_PASSWORD`. Rotate and check each provider's
   usage graph for a step change.
5. **Prove the published site is untampered.** `git log --stat origin/main` for
   the window, against `data/audit.log`'s deploy entries. Every legitimate
   deploy leaves both a commit and an audit line; a commit with no matching
   audit line, or a published file outside `deploy.py`'s `ALLOWED_PREFIXES`, is
   the thing to look for.
6. **If `claims.db` may have been read**, it holds requester names, email
   addresses and submitted patches. Notify affected requesters — they gave that
   data to a claim form, not to the internet.

---

## 4. Backups

`data/claims.db` and `data/articles.db` are the only state no rebuild can
restore, and they are deliberately outside git. `admin/pipeline/backup.py`
snapshots both every 12 hours through SQLite's online backup API, verifies each
snapshot by restoring it and running `PRAGMA integrity_check`, and keeps 30.

```bash
python3 -m admin.pipeline.backup --list
python3 -m admin.pipeline.backup --snapshot
python3 -m admin.pipeline.backup --verify latest
python3 -m admin.pipeline.backup --restore latest --into /tmp/restore
```

`--restore` never overwrites the live databases; moving the result into place is
a separate deliberate step, because restoring onto a running admin's
`claims.db` is how a recovery becomes a second incident.

**Run the drill quarterly**, not just the verify: restore into a scratch
directory, point `CLAIMS_DB_PATH`/`ARTICLES_DB_PATH` at it, and confirm the
admin lists claims unchanged. A backup nobody has restored is a hypothesis.

**Known limit.** Snapshots live on the Fly volume, and Fly's own daily volume
snapshots are what make them off-host. Those are same-provider: they cover a
lost machine or a bad deploy, not a lost Fly account. A genuinely off-provider
copy needs a destination to send to — an open decision, not an oversight.

---

## 5. Known accepted risks

Written down rather than assumed, so they are re-decided rather than forgotten.

- **One shared admin credential, no second factor.** Proportionate to a
  single-operator project; it is also the single point of failure.
- **Throttle state is in-process** and clears on restart. `fly.toml` keeps one
  machine running with auto-stop off, so a restart is rare; a determined
  attacker who can force one gets their attempt budget back.
- **`Fly-Client-IP` is trusted** for throttle bucketing. Fly's proxy sets it, so
  it is accurate in production. Off Fly it is spoofable — which only lets a
  caller move between buckets, never past the global limiters that back each
  per-client one.
- **No dependency-advisory monitoring.** Pins are exact
  (`admin/requirements.txt`, `site/package-lock.json`) but nothing watches for
  CVEs. Enabling Dependabot is a small, obvious next step.
- **The Stripe webhook auto-publishes and auto-deploys** with no human in the
  loop (TRD.md §8, 2026-07-25). Deliberate and narrow, but it means
  `STRIPE_WEBHOOK_SECRET` is a content-integrity credential, not just a
  payments one.
