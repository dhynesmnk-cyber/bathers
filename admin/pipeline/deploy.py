"""Deploy strip backend (UX.md §1.4): git status summary, diff preview,
tracked-file guard, and the streamed add -> commit -> push.

Only these are ever committed: `_published/`, published images
(site/public/images/), the SQLite file, the generated JSON/GeoJSON
(venues.json, venues.geojson, forewords.json — all pipeline-derived
artefacts the build needs), and the 2026-07-21 blog additions
(site/src/content/blog/_published/, site/public/blog-images/). `_staging/`,
`_rejected/`, `_blog_staging/`, `temp_data/`, `.env` must never be tracked
at all; the guard refuses to run if any of them somehow are (e.g.
force-added by hand).
"""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import httpx

from admin.config import NETLIFY_AUTH_TOKEN, NETLIFY_SITE_ID, ROOT, SITE_DIR

ALLOWED_PREFIXES = (
    "site/src/content/spas/_published/",
    "site/public/images/",
    "data/directory.db",
    "site/src/data/venues.json",
    "site/public/venues.geojson",
    "site/src/data/forewords.json",
    "site/src/content/blog/_published/",
    "site/public/blog-images/",
)

GUARD_PATHSPECS = ("temp_data", "content-staging", ".env", ".env.*")
GUARD_ALLOWLIST = {".env.example"}  # intentionally tracked per .gitignore's `!.env.example`


class DeployRefused(Exception):
    pass


@dataclass
class LogLine:
    time: str
    level: str
    text: str


@dataclass
class DeployPreview:
    files: list[str]
    unexpected: list[str]
    guard_violations: list[str]
    commit_message: str

    @property
    def blocked(self) -> bool:
        return bool(self.guard_violations) or bool(self.unexpected)


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _run_git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def _is_allowed(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in ALLOWED_PREFIXES)


def guard_violations() -> list[str]:
    result = _run_git("ls-files", "--", *GUARD_PATHSPECS)
    return sorted(f for f in result.stdout.splitlines() if f and f not in GUARD_ALLOWLIST)


def _status_entries() -> list[tuple[str, str]]:
    result = _run_git("status", "--porcelain=v1")
    entries: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        code, path = line[:2], line[3:]
        if " -> " in path:  # rename entries: "old -> new"
            path = path.split(" -> ", 1)[1]
        entries.append((code, path))
    return entries


def _published_slugs_changed(entries: list[tuple[str, str]], prefix: str) -> list[str]:
    slugs = [Path(path).stem for _, path in entries if path.startswith(prefix) and path.endswith(".mdx")]
    return sorted(set(slugs))


def _auto_commit_message(venue_slugs: list[str], post_slugs: list[str]) -> str:
    if not venue_slugs and not post_slugs:
        return "Publish: data refresh"
    parts = []
    if venue_slugs:
        shown = venue_slugs[:2]
        rest = len(venue_slugs) - len(shown)
        suffix = f" (+{rest} venue{'s' if rest != 1 else ''})" if rest > 0 else ""
        parts.append(f"{', '.join(shown)}{suffix}")
    if post_slugs:
        shown = post_slugs[:2]
        rest = len(post_slugs) - len(shown)
        suffix = f" (+{rest} post{'s' if rest != 1 else ''})" if rest > 0 else ""
        parts.append(f"blog: {', '.join(shown)}{suffix}")
    return f"Publish: {'; '.join(parts)}"


def build_preview() -> DeployPreview:
    entries = _status_entries()
    files = sorted({path for _, path in entries if _is_allowed(path)})
    unexpected = sorted({path for _, path in entries if not _is_allowed(path)})
    return DeployPreview(
        files=files,
        unexpected=unexpected,
        guard_violations=guard_violations(),
        commit_message=_auto_commit_message(
            _published_slugs_changed(entries, "site/src/content/spas/_published/"),
            _published_slugs_changed(entries, "site/src/content/blog/_published/"),
        ),
    )


def status_summary() -> dict:
    preview = build_preview()
    last = _run_git("log", "-1", "--format=%cI", "--", *ALLOWED_PREFIXES)
    last_deploy_text = "no deploy yet"
    stamp = last.stdout.strip()
    if last.returncode == 0 and stamp:
        commit_time = datetime.fromisoformat(stamp)
        days = (datetime.now(timezone.utc) - commit_time).days
        last_deploy_text = "today" if days <= 0 else f"{days}d ago"
    return {
        "file_count": len(preview.files),
        "last_deploy": last_deploy_text,
        "blocked": preview.blocked,
    }


NETLIFY_POLL_INTERVAL_SECONDS = 10
NETLIFY_POLL_TIMEOUT_SECONDS = 360
BUILD_LOG_TAIL_LINES = 15


def _site_build_gate() -> Iterator[LogLine]:
    """Pre-push `npm run build` — refuses the deploy (via DeployRefused)
    rather than letting broken content reach Netlify, where the failure is
    silent from the admin's point of view. Skips with a warning where npm
    isn't available."""
    if shutil.which("npm") is None:
        yield LogLine(_now(), "warn", "npm not available — skipping pre-push build check; Netlify will still build on push")
        return
    yield LogLine(_now(), "info", "verifying site build (npm run build)")
    result = subprocess.run(
        ["npm", "run", "build"], cwd=SITE_DIR, capture_output=True, text=True, timeout=600
    )
    if result.returncode == 0:
        yield LogLine(_now(), "info", "site build ok")
        return
    output = (result.stdout + "\n" + result.stderr).strip().splitlines()
    for line in output[-BUILD_LOG_TAIL_LINES:]:
        yield LogLine(_now(), "error", line)
    raise DeployRefused("site build failed — fix the content above before deploying")


def _poll_netlify(commit_sha: str) -> Iterator[LogLine]:
    """After push, watch the resulting Netlify build until it's ready or
    errors — closing the gap where 'push ok' looked like a successful deploy
    while the site build failed. No token configured → informational only."""
    if not NETLIFY_AUTH_TOKEN:
        yield LogLine(_now(), "info", "pushed — Netlify builds automatically; set NETLIFY_AUTH_TOKEN in .env for build status here")
        return
    url = f"https://api.netlify.com/api/v1/sites/{NETLIFY_SITE_ID}/deploys"
    headers = {"Authorization": f"Bearer {NETLIFY_AUTH_TOKEN}"}
    deadline = time.monotonic() + NETLIFY_POLL_TIMEOUT_SECONDS
    last_state = None
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(url, headers=headers, params={"per_page": 10}, timeout=15)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            yield LogLine(_now(), "warn", f"netlify status check failed — {exc}; check app.netlify.com")
            return
        deploy = next((d for d in resp.json() if (d.get("commit_ref") or "").startswith(commit_sha)), None)
        state = deploy.get("state") if deploy else None
        if state != last_state and state is not None:
            yield LogLine(_now(), "info", f"netlify: {state}")
            last_state = state
        if state == "ready":
            yield LogLine(_now(), "info", f"netlify: live — {deploy.get('ssl_url') or deploy.get('url') or ''}")
            return
        if state == "error":
            message = deploy.get("error_message") or "build failed"
            if "no content change" in message:
                yield LogLine(_now(), "info", "netlify: skipped build — no site content changed")
            else:
                yield LogLine(_now(), "error", f"netlify: {message}")
            return
        time.sleep(NETLIFY_POLL_INTERVAL_SECONDS)
    yield LogLine(_now(), "warn", "netlify: build still running after 6 min — check app.netlify.com")


def run_deploy(commit_message: str) -> Iterator[LogLine]:
    # Sync first — the Fly checkout (or a local one) may be behind origin,
    # which would reject the push at the end.
    yield LogLine(_now(), "info", "git pull --ff-only")
    pull = _run_git("pull", "--ff-only")
    if pull.returncode != 0:
        yield LogLine(_now(), "error", f"git pull failed — {(pull.stderr or pull.stdout).strip()}")
        return

    preview = build_preview()

    if preview.guard_violations:
        yield LogLine(_now(), "error", "refused — tracked files under a gitignored directory: " + ", ".join(preview.guard_violations))
        return
    if preview.unexpected:
        yield LogLine(_now(), "error", "refused — unexpected tracked files outside the publish set: " + ", ".join(preview.unexpected))
        return
    if not preview.files:
        yield LogLine(_now(), "warn", "nothing to deploy — no changes in the publish set")
        return

    try:
        yield from _site_build_gate()
    except DeployRefused as exc:
        yield LogLine(_now(), "error", f"refused — {exc}")
        return
    except subprocess.TimeoutExpired:
        yield LogLine(_now(), "error", "refused — site build timed out after 10 minutes")
        return

    yield LogLine(_now(), "info", f"add {len(preview.files)} file(s)")
    add = _run_git("add", "--", *preview.files)
    if add.returncode != 0:
        yield LogLine(_now(), "error", f"git add failed — {add.stderr.strip()}")
        return

    message = commit_message.strip() or preview.commit_message
    yield LogLine(_now(), "info", f"commit — {message}")
    commit = _run_git("commit", "-m", message)
    if commit.returncode != 0:
        yield LogLine(_now(), "error", f"git commit failed — {(commit.stderr or commit.stdout).strip()}")
        return
    first_line = commit.stdout.strip().splitlines()[0] if commit.stdout.strip() else "commit ok"
    yield LogLine(_now(), "info", first_line)

    yield LogLine(_now(), "info", "push")
    push = _run_git("push")
    if push.returncode != 0:
        yield LogLine(_now(), "error", f"git push failed — {(push.stderr or push.stdout).strip()}")
        return
    yield LogLine(_now(), "info", "push ok")

    sha = _run_git("rev-parse", "HEAD").stdout.strip()
    yield from _poll_netlify(sha)
