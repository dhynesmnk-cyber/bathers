"""FastAPI admin app — UX.md §1 single-screen hub. Vanilla JS + Jinja2 per
TRD.md §2 — no SPA framework.
"""

from __future__ import annotations

import base64
import json
import secrets
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request

from admin.config import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    AMENITY_KEYS,
    CATEGORY_LABELS,
    DRESS_CODE_LABELS,
    FACILITY_KEYS,
    FACILITY_LABELS,
    SESSION_GENDER_LABELS,
    SITE_BLOG_IMAGES_DIR,
    SITE_DIST_DIR,
    SITE_FONTS_DIR,
    SITE_URL,
    STAGING_DIR,
    STATES,
    STRIPE_WEBHOOK_SECRET,
    VENUES_JSON_PATH,
)
from admin.mdx_preview import (
    AMENITY_LABELS,
    ICON_PATHS,
    drive_time_line,
    price_line,
    render_body_html,
    session_gender_line,
    temperature_line,
    verification_summary,
)
from admin.pipeline import article_db, article_pipeline, article_store, articles, blog, claims, claims_store, deploy, discovery, goatcounter, gsc, images, notify, orchestrator, places, staging, stripe_client
from admin.pipeline.articles import PublishBlocked
from admin.pipeline.articles import ValidationFailed as ArticleValidationFailed
from admin.pipeline.blog import ValidationFailed as BlogValidationFailed
from admin.pipeline.staging import UndoExpired, ValidationFailed

# Exempted from Basic Auth (require_basic_auth, below) — the claim form and
# Stripe webhook are this app's only unauthenticated public write paths
# (TRD.md §8, 2026-07-25 exception). Everything else stays behind auth.
PUBLIC_PATHS = {"/api/claims/submit", "/api/stripe/webhook"}
# The email Approve/Deny confirm-and-act pages (2026-07-25 addition) carry a
# variable claim id, so they're matched by prefix rather than exact path.
# Auth here is the per-request action_token, not Basic Auth — see
# claims.verify_action_token.
PUBLIC_PATH_PREFIXES = ("/claim-action/",)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Where We Bathe Admin")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="admin-static")
# Mounted unconditionally (dir created if missing) so a later `npm run build`
# becomes visible on the next request with no admin restart required.
# html=True so directory URLs (/site-dist/spa/<slug>/) serve their index.html —
# the Done panel's "view live" fallback when SITE_URL is unset.
SITE_DIST_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/site-dist", StaticFiles(directory=str(SITE_DIST_DIR), html=True), name="site-dist")
if SITE_FONTS_DIR.exists():
    app.mount("/fonts", StaticFiles(directory=str(SITE_FONTS_DIR)), name="admin-fonts")
SITE_BLOG_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/blog-images", StaticFiles(directory=str(SITE_BLOG_IMAGES_DIR)), name="blog-images")


def _basic_auth_ok(header: str | None) -> bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        username, _, password = base64.b64decode(header[6:]).decode("utf-8").partition(":")
    except (ValueError, UnicodeDecodeError):
        return False
    return secrets.compare_digest(username, ADMIN_USERNAME) and secrets.compare_digest(password, ADMIN_PASSWORD)


@app.middleware("http")
async def require_basic_auth(request: Request, call_next):
    if request.url.path in PUBLIC_PATHS or request.url.path.startswith(PUBLIC_PATH_PREFIXES):
        return await call_next(request)
    # No credentials configured (local dev's .env leaves these blank) — auth stays off.
    if not ADMIN_USERNAME and not ADMIN_PASSWORD:
        return await call_next(request)
    if not _basic_auth_ok(request.headers.get("authorization")):
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Where We Bathe Admin"'})
    return await call_next(request)


# Starlette applies the most-recently-added middleware outermost, so adding
# this after require_basic_auth makes CORS run before the auth check —
# needed so a preflight OPTIONS on /api/claims/submit from the (different-
# origin) static site never hits the 401 path. Restricted to the site's own
# origin plus the Astro dev server default.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[SITE_URL, "http://localhost:4321"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


def _site_css_hrefs() -> list[str]:
    astro_dir = SITE_DIST_DIR / "_astro"
    if not astro_dir.exists():
        return []
    return [f"/site-dist/_astro/{path.name}" for path in sorted(astro_dir.glob("*.css"))]


def _entry_summary(entry: staging.StagingEntry) -> dict[str, Any]:
    data = entry.frontmatter
    return {
        "slug": entry.slug,
        "name": data.get("name"),
        "state": data.get("state"),
        "suburb": data.get("suburb"),
        "amenities": data.get("amenities"),
        "status": entry.status,
        "word_count": entry.word_count,
        "errors": [asdict(e) for e in entry.errors],
        "saved_at": entry.saved_at,
        "duplicates": staging.find_duplicates(entry.slug, data),
    }


def _entry_detail(entry: staging.StagingEntry) -> dict[str, Any]:
    candidates = images.list_candidates(entry.slug)
    places_check = places.load_check(entry.slug)
    return {
        **_entry_summary(entry),
        "frontmatter": entry.frontmatter,
        "body": entry.body,
        "image_candidates": [
            {
                "index": c.index,
                "url": f"/api/queue/{entry.slug}/images/{c.index}/file",
                "source_url": c.source_url,
                "attribution": c.attribution,
            }
            for c in candidates
        ],
        "places_check": asdict(places_check) if places_check else None,
    }


def _static_version(*names: str) -> int:
    """Cache-buster for /static includes — a stale browser-cached script running
    against a newer template silently breaks the screen. Defaults to the shared
    admin bundle; pass a screen's own assets to bust those too."""
    names = names or ("admin.js", "admin.css")
    return max(int((BASE_DIR / "static" / name).stat().st_mtime) for name in names)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "states": STATES,
            "categories": CATEGORY_LABELS,
            "dress_codes": DRESS_CODE_LABELS,
            "session_genders": SESSION_GENDER_LABELS,
            "site_url": SITE_URL,
            "static_version": _static_version(),
        },
    )


@app.get("/blog", response_class=HTMLResponse)
def blog_page(request: Request):
    return templates.TemplateResponse(
        request,
        "blog.html",
        {"static_version": _static_version("blog.js", "blog.css", "admin.css")},
    )


@app.get("/claims", response_class=HTMLResponse)
def claims_page(request: Request):
    return templates.TemplateResponse(request, "claims.html", {})


@app.get("/articles", response_class=HTMLResponse)
def articles_page(request: Request):
    return templates.TemplateResponse(
        request,
        "articles.html",
        {"static_version": _static_version("articles.js", "articles.css", "admin.css")},
    )


@app.get("/preview/{slug}", response_class=HTMLResponse)
def preview(request: Request, slug: str):
    try:
        entry = staging.get_staging(slug)
    except FileNotFoundError:
        try:
            entry = staging.get_published(slug)
        except FileNotFoundError:
            raise HTTPException(404, f"no draft or published venue for '{slug}'")
    data = entry.frontmatter
    return templates.TemplateResponse(
        request,
        "preview.html",
        {
            "data": data,
            "body_html": render_body_html(entry.body),
            "css_hrefs": _site_css_hrefs(),
            "amenity_keys": AMENITY_KEYS,
            "amenity_labels": AMENITY_LABELS,
            "facility_keys": FACILITY_KEYS,
            "facility_labels": FACILITY_LABELS,
            "dress_code_labels": DRESS_CODE_LABELS,
            "icon_paths": ICON_PATHS,
            "temperature_line": temperature_line(data.get("temperatures")),
            "session_gender_line": session_gender_line(data),
            "price_line": price_line(data),
            "drive_time_line": drive_time_line(data),
            "verification_rows": verification_summary(data),
        },
    )


@app.get("/api/queue")
def api_list_queue():
    return [_entry_summary(e) for e in staging.list_staging()]


@app.get("/api/queue/{slug}")
def api_get_queue_item(slug: str):
    try:
        entry = staging.get_staging(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"no staged draft for '{slug}'")
    return _entry_detail(entry)


class PatchBody(BaseModel):
    patch: dict[str, Any]


@app.patch("/api/queue/{slug}")
def api_update_queue_item(slug: str, body: PatchBody):
    try:
        entry = staging.update_staging(slug, body.patch)
    except FileNotFoundError:
        raise HTTPException(404, f"no staged draft for '{slug}'")
    return _entry_detail(entry)


@app.post("/api/queue/{slug}/approve")
def api_approve(slug: str):
    try:
        staging.approve(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"no staged draft for '{slug}'")
    except ValidationFailed as exc:
        raise HTTPException(422, detail={"errors": [asdict(e) for e in exc.errors]})
    remaining = staging.list_staging()
    return {"ok": True, "next_slug": remaining[0].slug if remaining else None}


class RejectBody(BaseModel):
    reason: str


@app.post("/api/queue/{slug}/reject")
def api_reject(slug: str, body: RejectBody):
    if not body.reason.strip():
        raise HTTPException(400, "a reject reason is required")
    try:
        staging.reject(slug, body.reason)
    except FileNotFoundError:
        raise HTTPException(404, f"no staged draft for '{slug}'")
    remaining = staging.list_staging()
    return {"ok": True, "next_slug": remaining[0].slug if remaining else None}


@app.post("/api/queue/{slug}/undo")
def api_undo(slug: str):
    try:
        staging.undo_approve(slug)
    except UndoExpired:
        raise HTTPException(410, "undo window has expired")
    return {"ok": True}


class HarvestBody(BaseModel):
    url: str
    use_playwright: bool = False


_harvest_lock = threading.Lock()  # UX.md §1.1 — one harvest job at a time


def _sse_line(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@app.post("/api/harvest")
def api_harvest(body: HarvestBody):
    if not _harvest_lock.acquire(blocking=False):
        raise HTTPException(409, "a harvest job is already running")

    def stream():
        try:
            for line in orchestrator.run_harvest_pipeline(body.url, use_playwright=body.use_playwright):
                yield _sse_line({"time": line.time, "level": line.level, "text": line.text})
        finally:
            _harvest_lock.release()
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/queue/{slug}/images/{index}/file")
def api_image_file(slug: str, index: int):
    candidate = next((c for c in images.list_candidates(slug) if c.index == index), None)
    if candidate is None:
        raise HTTPException(404, "no such candidate image")
    path = images.resolve_image_dir(slug) / candidate.filename
    if not path.exists():
        raise HTTPException(404, "candidate image file missing")
    return FileResponse(path)


class PublishImageBody(BaseModel):
    caption: str


@app.post("/api/queue/{slug}/images/{index}/publish")
def api_publish_image(slug: str, index: int, body: PublishImageBody):
    if not body.caption.strip():
        raise HTTPException(400, "a caption is required")
    try:
        fields = images.publish_image(slug, index, body.caption.strip())
    except FileNotFoundError:
        raise HTTPException(404, "no such candidate image")
    entry = staging.publish_image_fields(slug, fields)
    return _entry_detail(entry)


@app.post("/api/queue/{slug}/images/remove")
def api_remove_staged_image(slug: str):
    images.remove_image(slug)  # candidate downloads stay in temp_data/ — only the published file/fields are cleared
    entry = staging.remove_image_fields(slug)
    return _entry_detail(entry)


@app.get("/api/venues/{slug}")
def api_get_published_venue(slug: str):
    try:
        entry = staging.get_published(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"no published venue '{slug}'")
    return _entry_detail(entry)


@app.patch("/api/venues/{slug}")
def api_update_published_venue(slug: str, body: PatchBody):
    try:
        entry = staging.update_published(slug, body.patch)
    except FileNotFoundError:
        raise HTTPException(404, f"no published venue '{slug}'")
    except ValidationFailed as exc:
        raise HTTPException(422, detail={"errors": [asdict(e) for e in exc.errors]})
    return _entry_detail(entry)


@app.delete("/api/venues/{slug}")
def api_delete_published_venue(slug: str):
    try:
        staging.delete_published(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"no published venue '{slug}'")
    return {"ok": True}


@app.post("/api/venues/{slug}/remove-image")
def api_remove_published_image(slug: str):
    # UX.md §4.4 takedown/claim action (the claim workflow itself is out of
    # scope per TRD.md §8) — wired into the Done panel's edit view alongside
    # general editing.
    try:
        staging.remove_published_image(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"no published venue '{slug}'")
    return {"ok": True}


@app.get("/api/deploy/status")
def api_deploy_status():
    # `deploying` reflects the shared DEPLOY_LOCK, so the blog/article screens'
    # go-live chip is truthful whether the deploy was manual or auto-triggered.
    return {**deploy.status_summary(), "deploying": deploy.DEPLOY_LOCK.locked()}


@app.get("/api/deploy/preview")
def api_deploy_preview():
    preview = deploy.build_preview()
    return {
        "files": preview.files,
        "unexpected": preview.unexpected,
        "guard_violations": preview.guard_violations,
        "commit_message": preview.commit_message,
        "blocked": preview.blocked,
    }


class DeployBody(BaseModel):
    commit_message: str = ""


@app.post("/api/deploy")
def api_deploy(body: DeployBody):
    if not deploy.DEPLOY_LOCK.acquire(blocking=False):
        raise HTTPException(409, "a deploy is already running")

    def stream():
        try:
            for line in deploy.run_deploy(body.commit_message):
                yield _sse_line({"time": line.time, "level": line.level, "text": line.text})
        finally:
            deploy.DEPLOY_LOCK.release()
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


class DiscoverBody(BaseModel):
    region: str
    keywords: list[str] | None = None


@app.post("/api/discover")
def api_discover(body: DiscoverBody):
    if not places.GOOGLE_PLACES_API_KEY:
        raise HTTPException(400, "GOOGLE_PLACES_API_KEY is not set — discovery is unavailable")
    try:
        candidates = discovery.discover_venues(body.region, body.keywords)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Places API error — {exc}") from exc
    return [asdict(c) for c in candidates]


def _blog_summary(entry: blog.BlogEntry, location: str) -> dict[str, Any]:
    fm = entry.frontmatter
    return {
        "slug": entry.slug,
        "title": fm.get("title"),
        "summary": fm.get("summary"),
        "dateline": str(fm.get("dateline")) if fm.get("dateline") else None,
        "status": location,
        "saved_at": entry.saved_at,
        "is_protected": entry.slug in blog.PROTECTED_SLUGS,
    }


def _blog_detail(entry: blog.BlogEntry, location: str) -> dict[str, Any]:
    return {**_blog_summary(entry, location), "frontmatter": entry.frontmatter, "body": entry.body}


@app.get("/api/blog")
def api_list_blog():
    return [_blog_summary(entry, location) for entry, location in blog.list_all()]


class CreateBlogPostBody(BaseModel):
    title: str


@app.post("/api/blog")
def api_create_blog_post(body: CreateBlogPostBody):
    try:
        entry = blog.create_draft(body.title)
    except BlogValidationFailed as exc:
        raise HTTPException(400, detail={"errors": exc.errors})
    return _blog_detail(entry, "draft")


@app.get("/api/blog/{slug}")
def api_get_blog_post(slug: str):
    try:
        entry, location = blog.get(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"no blog post '{slug}'")
    return _blog_detail(entry, location)


class BlogPatchBody(BaseModel):
    patch: dict[str, Any]


@app.patch("/api/blog/{slug}")
def api_update_blog_post(slug: str, body: BlogPatchBody):
    try:
        entry, location = blog.update(slug, body.patch)
    except FileNotFoundError:
        raise HTTPException(404, f"no blog post '{slug}'")
    except BlogValidationFailed as exc:
        raise HTTPException(422, detail={"errors": exc.errors})
    return _blog_detail(entry, location)


@app.delete("/api/blog/{slug}")
def api_delete_blog_post(slug: str, background_tasks: BackgroundTasks):
    """Permanently delete a blog post (draft or published). Deleting a published
    post removes it from the live site, so that deletion rides an auto-deploy."""
    try:
        location = blog.delete(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"no blog post '{slug}'")
    deploying = location == "published"
    if deploying:
        background_tasks.add_task(deploy.run_auto_deploy)
    return {"ok": True, "deploying": deploying}


@app.post("/api/blog/{slug}/publish")
def api_publish_blog_post(slug: str, background_tasks: BackgroundTasks):
    try:
        blog.publish(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"no draft '{slug}'")
    except BlogValidationFailed as exc:
        raise HTTPException(422, detail={"errors": exc.errors})
    # One-click go-live (2026-08-01): publishing to _published now auto-deploys,
    # so the operator doesn't have to switch to the hub Deploy strip afterwards.
    background_tasks.add_task(deploy.run_auto_deploy)
    return {"ok": True, "deploying": True}


@app.post("/api/blog/{slug}/unpublish")
def api_unpublish_blog_post(slug: str, background_tasks: BackgroundTasks):
    """Take a published post off the live site, recoverably — moves it back to
    drafts and auto-deploys the _published deletion."""
    try:
        blog.unpublish(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"no published post '{slug}'")
    background_tasks.add_task(deploy.run_auto_deploy)
    return {"ok": True, "deploying": True}


# ---- Comparison articles (Editorial Gate E2) — draft -> fact-check -> review ----
# The staged draft/review flow for hybrid comparison articles. Mirrors the harvest
# SSE + blog staging patterns; approval is gated on a clean fact-check report.

_article_lock = threading.Lock()


def _article_summary(entry: articles.ArticleEntry) -> dict[str, Any]:
    report = entry.report or {}
    return {
        "slug": entry.slug,
        "title": entry.frontmatter.get("title"),
        "query_key": entry.frontmatter.get("query_key"),
        "status": report.get("status", "no-report"),
        "unsupported": report.get("unsupported_count", 0),
        "saved_at": entry.saved_at,
    }


def _article_detail(entry: articles.ArticleEntry) -> dict[str, Any]:
    return {**_article_summary(entry), "frontmatter": entry.frontmatter, "body": entry.body, "report": entry.report}


@app.get("/api/articles")
def api_list_articles():
    return [_article_summary(e) for e in articles.list_staging()]


@app.get("/api/articles/opportunities")
def api_article_opportunities():
    """The opportunity queue (Editorial Gate E4a): every registry comparison
    (>=5 venues) tagged with whether it's already written, its field
    completeness, the operator's disposition (pin/dismiss) and its latest brief.
    Draftable intents (approved brief, not written/dismissed) feed the generate
    form; the rest surface for briefing or dismissal."""
    return article_db.opportunities()


class DispositionBody(BaseModel):
    disposition: str  # "pinned" | "dismissed" | "clear"
    reason: str | None = None


@app.post("/api/articles/opportunities/{query_key}/disposition")
def api_set_disposition(query_key: str, body: DispositionBody):
    """Pin an opportunity (keep despite a sparse table) or dismiss it (hide from
    drafting), or clear the override."""
    if body.disposition == "clear":
        article_db.clear_disposition(query_key)
        return {"ok": True, "disposition": None}
    try:
        row = article_db.set_disposition(query_key, body.disposition, reason=body.reason)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"ok": True, "disposition": row["disposition"]}


class GenerateBriefBody(BaseModel):
    query_key: str


@app.post("/api/articles/brief/generate")
def api_generate_brief(body: GenerateBriefBody):
    """Auto-draft an editorial brief for an intent and store it pending — the
    brief gate's first step. Streams the pipeline log (SSE)."""
    if not _article_lock.acquire(blocking=False):
        raise HTTPException(409, "an article job is already running")

    def stream():
        try:
            for line in article_pipeline.brief(body.query_key):
                yield _sse_line({"time": line.time, "level": line.level, "text": line.text})
        finally:
            _article_lock.release()
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/articles/briefs")
def api_list_briefs(status: str | None = None):
    return article_db.list_briefs(status)


@app.get("/api/articles/briefs/{brief_id}")
def api_get_brief(brief_id: int):
    try:
        return article_db.get_brief(brief_id)
    except KeyError:
        raise HTTPException(404, f"no brief #{brief_id}")


class DecideBriefBody(BaseModel):
    status: str  # "approved" | "killed"
    decided_by: str | None = None
    note: str | None = None


@app.post("/api/articles/briefs/{brief_id}/decide")
def api_decide_brief(brief_id: int, body: DecideBriefBody):
    """Approve or kill a brief — the human gate before any drafting spend."""
    try:
        brief = article_db.decide_brief(brief_id, body.status, decided_by=body.decided_by, note=body.note)
    except KeyError:
        raise HTTPException(404, f"no brief #{brief_id}")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"ok": True, "brief": brief}


@app.get("/api/articles/published")
def api_published_staleness():
    """Post-publish staleness dashboard (Editorial Gate E4c) — published
    comparison articles with their two dates, stale flag, what has moved since the
    last human baseline, and fact-check status. Also reports whether a
    GSC/analytics demand feed is wired (a documented seam, deferred)."""
    return {"articles": article_store.published_staleness(), "demand_feed": gsc.is_configured()}


# NOTE: this static route must be declared before /api/articles/{slug} so it is
# not swallowed as slug="published".
@app.get("/api/articles/{slug}")
def api_get_article(slug: str):
    try:
        return _article_detail(articles.get_staging(slug))
    except FileNotFoundError:
        raise HTTPException(404, f"no staged article '{slug}'")


@app.post("/api/articles/{query_key}/rebaseline")
def api_rebaseline_article(query_key: str):
    """Sign off a stale article: re-baseline it to the current figures, clearing
    the stale flag (a human has re-read the prose against the moved data). The
    Stage-8 re-verification (re-run the fact-check) is the existing
    /api/articles/{slug}/factcheck endpoint."""
    try:
        article_store.accept(query_key)
    except Exception as exc:  # noqa: BLE001 — surface a refresh-runner failure
        raise HTTPException(500, f"re-baseline failed — {exc}")
    return {"ok": True}


class GenerateArticleBody(BaseModel):
    query_key: str
    slug: str
    author: str | None = None


@app.post("/api/articles/generate")
def api_generate_article(body: GenerateArticleBody):
    if not _article_lock.acquire(blocking=False):
        raise HTTPException(409, "an article job is already running")

    def stream():
        try:
            for line in article_pipeline.run(body.query_key, body.slug, body.author):
                yield _sse_line({"time": line.time, "level": line.level, "text": line.text})
        finally:
            _article_lock.release()
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


class WriteArticleBody(BaseModel):
    query_key: str
    author: str | None = None


@app.post("/api/articles/write")
def api_write_article(body: WriteArticleBody):
    """Collapsed 'write about X' flow (2026-08-01): brief -> auto-approve ->
    draft -> fact-check as one streamed job, landing in review for the human
    publish gate. One button instead of the brief/generate stages."""
    if not _article_lock.acquire(blocking=False):
        raise HTTPException(409, "an article job is already running")

    def stream():
        try:
            for line in article_pipeline.write(body.query_key, body.author):
                yield _sse_line({"time": line.time, "level": line.level, "text": line.text})
        finally:
            _article_lock.release()
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


class WriteEssayBody(BaseModel):
    topic: str
    author: str | None = None


@app.post("/api/articles/write-essay")
def api_write_essay(body: WriteEssayBody):
    """Free-form essay flow (2026-08-01): draft a voiced blog essay on a typed
    topic + integrity-check it as one streamed job, landing in review beside the
    comparison drafts. No query_key and no live table — it publishes into the blog
    collection as a plain essay. The human publish gate is unchanged; the integrity
    block (first-person visit claims, invented venue facts) still gates approval."""
    if not _article_lock.acquire(blocking=False):
        raise HTTPException(409, "an article job is already running")

    def stream():
        try:
            for line in article_pipeline.essay(body.topic, body.author):
                yield _sse_line({"time": line.time, "level": line.level, "text": line.text})
        finally:
            _article_lock.release()
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/articles/{slug}/factcheck")
def api_refactcheck_article(slug: str):
    """Re-run the fact-check and rewrite the stored report. Dispatches on where the
    slug lives: a staged draft (the review-pane Re-fact-check button) rewrites its
    staging sidecar report so a block can clear; an already-published article (the
    Published list's Re-verify, Stage 8 re-verification) rewrites its committed
    factchecks record."""
    if not _article_lock.acquire(blocking=False):
        raise HTTPException(409, "an article job is already running")

    def stream():
        try:
            for line in article_pipeline.refactcheck(slug):
                yield _sse_line({"time": line.time, "level": line.level, "text": line.text})
        finally:
            _article_lock.release()
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


class ArticlePatchBody(BaseModel):
    patch: dict[str, Any]


@app.patch("/api/articles/{slug}")
def api_update_article(slug: str, body: ArticlePatchBody):
    try:
        return _article_detail(articles.update_staging(slug, body.patch))
    except FileNotFoundError:
        raise HTTPException(404, f"no staged article '{slug}'")


class ApproveArticleBody(BaseModel):
    # Optional operator force-publish (2026-08-03): a reason bypasses ONLY the
    # fact-check block, recorded on the report. A plain approve sends no body.
    override_reason: str | None = None


@app.post("/api/articles/{slug}/approve")
def api_approve_article(
    slug: str, background_tasks: BackgroundTasks, body: ApproveArticleBody = ApproveArticleBody()
):
    try:
        redirect = articles.approve(slug, override_reason=body.override_reason)
    except FileNotFoundError:
        raise HTTPException(404, f"no staged article '{slug}'")
    except PublishBlocked as exc:
        raise HTTPException(409, detail={"blocked": str(exc)})
    except ArticleValidationFailed as exc:
        raise HTTPException(422, detail={"errors": exc.errors})
    # One-click go-live (2026-08-01): a clean, human-approved article now
    # auto-deploys. The fact-check block above still gates this path.
    background_tasks.add_task(deploy.run_auto_deploy)
    return {"ok": True, "redirect": redirect, "deploying": True}


class RejectArticleBody(BaseModel):
    reason: str


@app.post("/api/articles/{slug}/reject")
def api_reject_article(slug: str, body: RejectArticleBody):
    try:
        articles.reject(slug, body.reason)
    except FileNotFoundError:
        raise HTTPException(404, f"no staged article '{slug}'")
    return {"ok": True}


@app.post("/api/articles/{slug}/unpublish")
def api_unpublish_article(slug: str, background_tasks: BackgroundTasks):
    """Take a published comparison article off the live site, recoverably —
    moves it back to article staging (with its fact-check report) and
    auto-deploys the _published deletion."""
    try:
        articles.unpublish(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"no published article '{slug}'")
    background_tasks.add_task(deploy.run_auto_deploy)
    return {"ok": True, "deploying": True}


@app.delete("/api/articles/{slug}")
def api_delete_article(slug: str, background_tasks: BackgroundTasks):
    """Permanently delete a staged or published article/essay. Deleting a published
    one removes it from the live site, so that deletion rides an auto-deploy.
    Unlike reject/unpublish this keeps no recoverable copy."""
    try:
        location = articles.delete(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"no article '{slug}'")
    deploying = location == "published"
    if deploying:
        background_tasks.add_task(deploy.run_auto_deploy)
    return {"ok": True, "deploying": deploying}


@app.get("/api/blog/{slug}/images/{index}/file")
def api_blog_draft_image(slug: str, index: int):
    path = blog.draft_image_path(slug, index)
    if path is None or not path.exists():
        raise HTTPException(404, "no such draft image")
    return FileResponse(path)


class UploadBlogImageBody(BaseModel):
    # Base64 JSON rather than multipart/form-data — avoids adding the
    # python-multipart dependency (not in TRD.md's stack, and unnecessary
    # for images this size) for the sake of one upload endpoint; every other
    # write in this API is already JSON, so this keeps the same shape.
    data: str
    content_type: str


@app.post("/api/blog/{slug}/images")
def api_upload_blog_image(slug: str, body: UploadBlogImageBody):
    try:
        raw = base64.b64decode(body.data)
    except (ValueError, base64.binascii.Error):
        raise HTTPException(400, "data must be valid base64")
    try:
        result = blog.save_image(slug, raw, body.content_type)
    except FileNotFoundError:
        raise HTTPException(404, f"no blog post '{slug}'")
    except BlogValidationFailed as exc:
        raise HTTPException(400, detail={"errors": exc.errors})
    return result


@app.get("/api/published")
def api_published():
    return json.loads(VENUES_JSON_PATH.read_text(encoding="utf-8")) if VENUES_JSON_PATH.exists() else []


@app.get("/api/conversions")
def api_conversions(refresh: bool = False):
    counts = goatcounter.fetch_click_counts() if refresh else (goatcounter.get_cached_counts() or goatcounter.fetch_click_counts())
    venues = json.loads(VENUES_JSON_PATH.read_text(encoding="utf-8")) if VENUES_JSON_PATH.exists() else []
    names = {v["slug"]: v["name"] for v in venues}
    rows = [
        {"slug": slug, "name": names.get(slug, slug), "count": count}
        for slug, count in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return {"configured": goatcounter.configured(), "rows": rows}


## ---- Claim-listing flow (TRD.md §8, 2026-07-25 exception) ----
#
# The only two routes in PUBLIC_PATHS (above) are below: /api/claims/submit
# (the public form) and /api/stripe/webhook (Stripe's callback). Everything
# else here is a normal authenticated admin route.


def _claim_summary(request: claims_store.ClaimRequest) -> dict[str, Any]:
    return {
        "id": request.id,
        "slug": request.slug,
        "venue_name": claims._venue_name(request.slug),
        "requester_name": request.requester_name,
        "plan_type": request.plan_type,
        "status": request.status,
        "submitted_at": request.submitted_at,
    }


def _claim_detail(request: claims_store.ClaimRequest) -> dict[str, Any]:
    return {
        **_claim_summary(request),
        "requester_email": request.requester_email,
        "patch": request.patch,
        "diff": claims.compute_diff(request.slug, request.patch),
        "has_photo": request.has_photo,
        "photo_caption": request.photo_caption,
        "review_note": request.review_note,
        "reviewed_at": request.reviewed_at,
        "is_returning_subscriber": request.is_returning_subscriber,
    }


class ClaimPhotoBody(BaseModel):
    data: str
    content_type: str


class ClaimSubmitBody(BaseModel):
    slug: str
    requester_name: str
    requester_email: str
    plan_type: Literal["one_off", "subscription"]
    patch: dict[str, Any]
    photo: ClaimPhotoBody | None = None
    photo_caption: str | None = None
    website: str = ""  # honeypot — real visitors never see or fill this field


@app.post("/api/claims/submit")
def api_submit_claim(body: ClaimSubmitBody):
    photo_bytes = None
    if body.photo is not None:
        if not body.photo_caption or not body.photo_caption.strip():
            raise HTTPException(400, "a caption is required when a photo is attached")
        try:
            photo_bytes = base64.b64decode(body.photo.data)
        except (ValueError, base64.binascii.Error):
            raise HTTPException(400, "photo data must be valid base64")
    try:
        claims.submit_request(
            slug=body.slug,
            requester_name=body.requester_name,
            requester_email=body.requester_email,
            plan_type=body.plan_type,
            patch=body.patch,
            photo_bytes=photo_bytes,
            photo_content_type=body.photo.content_type if body.photo else None,
            photo_caption=body.photo_caption,
            honeypot_value=body.website,
        )
    except FileNotFoundError:
        raise HTTPException(404, f"no published venue '{body.slug}'")
    except claims.InvalidPatch as exc:
        raise HTTPException(400, str(exc))
    except claims.RateLimitExceeded:
        raise HTTPException(429, "too many requests for this venue — try again later")
    # Always the same shape, honeypot hit or not — nothing here should tell
    # an automated caller it was filtered.
    return {"ok": True}


@app.post("/api/stripe/webhook")
async def api_stripe_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()  # must stay raw/unparsed for signature verification
    try:
        event = stripe_client.verify_webhook_signature(
            payload, request.headers.get("stripe-signature", ""), STRIPE_WEBHOOK_SECRET
        )
    except stripe_client.SignatureVerificationError as exc:
        raise HTTPException(400, str(exc))

    if event.get("type") == "checkout.session.completed":
        session = event["data"]["object"]
        claims.handle_checkout_completed(session["id"], session.get("customer"))
        background_tasks.add_task(deploy.run_auto_deploy)

    return {"received": True}


@app.get("/api/claims")
def api_list_claims(status: str | None = None):
    return [_claim_summary(r) for r in claims_store.list_requests(status)]


@app.get("/api/claims/{claim_id}")
def api_get_claim(claim_id: int):
    try:
        request = claims_store.get_request(claim_id)
    except KeyError:
        raise HTTPException(404, f"no claim request '{claim_id}'")
    return _claim_detail(request)


@app.get("/api/claims/{claim_id}/photo")
def api_claim_photo(claim_id: int):
    try:
        request = claims_store.get_request(claim_id)
    except KeyError:
        raise HTTPException(404, f"no claim request '{claim_id}'")
    if not request.has_photo or not request.photo_path:
        raise HTTPException(404, "no photo for this request")
    path = Path(request.photo_path)
    if not path.exists():
        raise HTTPException(404, "photo file missing")
    return FileResponse(path)


class ClaimReviewBody(BaseModel):
    review_note: str = ""


@app.post("/api/claims/{claim_id}/approve")
def api_approve_claim(claim_id: int, body: ClaimReviewBody):
    try:
        request = claims.approve_request(claim_id, body.review_note)
    except KeyError:
        raise HTTPException(404, f"no claim request '{claim_id}'")
    except stripe_client.StripeError as exc:
        raise HTTPException(502, f"Stripe error — {exc}")
    return _claim_detail(request)


class ClaimDenyBody(BaseModel):
    review_note: str


@app.post("/api/claims/{claim_id}/deny")
def api_deny_claim(claim_id: int, body: ClaimDenyBody):
    if not body.review_note.strip():
        raise HTTPException(400, "a review reason is required")
    try:
        request = claims.deny_request(claim_id, body.review_note)
    except KeyError:
        raise HTTPException(404, f"no claim request '{claim_id}'")
    return _claim_detail(request)


@app.post("/api/claims/{claim_id}/publish")
def api_publish_claim(claim_id: int, background_tasks: BackgroundTasks):
    try:
        request = claims_store.get_request(claim_id)
    except KeyError:
        raise HTTPException(404, f"no claim request '{claim_id}'")
    if request.status != "approved" or not request.is_returning_subscriber:
        raise HTTPException(409, "only an approved subscriber request can be published this way")
    claims.publish_request(claim_id)
    background_tasks.add_task(deploy.run_auto_deploy)
    return {"ok": True}


## ---- Email Approve/Deny confirm-and-act pages (2026-07-25 addition) ----
#
# Public (see PUBLIC_PATH_PREFIXES above) — auth is the per-request
# action_token, not Basic Auth, so the owner can act straight from the
# notification email with no login. GET only ever renders a confirmation
# page (safe against mail-scanner/prefetch auto-visits); POST is the only
# thing that actually approves/denies, reusing claims.approve_request /
# claims.deny_request unchanged — this is a narrower entry point into the
# same logic the authenticated JSON API above already calls, not a second
# approval pathway.


def _claim_action_context(claim: claims_store.ClaimRequest, *, action: str, token: str) -> dict[str, Any]:
    return {
        "state": "confirm",
        "action": action,
        "claim_id": claim.id,
        "token": token,
        "venue_name": claims._venue_name(claim.slug),
        "requester_name": claim.requester_name,
        "requester_email": claim.requester_email,
        "plan_label": notify.PLAN_LABELS.get(claim.plan_type, claim.plan_type),
        "diff": claims.compute_diff(claim.slug, claim.patch),
        "has_photo": claim.has_photo,
    }


@app.get("/claim-action/{claim_id}/{action}", response_class=HTMLResponse)
def claim_action_confirm(request: Request, claim_id: int, action: str, token: str = ""):
    if action not in ("approve", "deny"):
        raise HTTPException(404)
    claim = claims.verify_action_token(claim_id, token)
    if claim is None:
        return templates.TemplateResponse(request, "claim_action.html", {"state": "invalid"})
    return templates.TemplateResponse(
        request, "claim_action.html", _claim_action_context(claim, action=action, token=token)
    )


@app.post("/claim-action/{claim_id}/{action}", response_class=HTMLResponse)
async def claim_action_submit(request: Request, claim_id: int, action: str, background_tasks: BackgroundTasks):
    if action not in ("approve", "deny"):
        raise HTTPException(404)
    # Plain url-encoded form body, parsed by hand with stdlib parse_qsl —
    # avoids adding python-multipart, which FastAPI's Form(...) parameter
    # type requires even for non-multipart bodies (same reasoning as the
    # blog image upload's base64-JSON-over-multipart choice elsewhere).
    fields = dict(parse_qsl((await request.body()).decode("utf-8")))
    token = fields.get("token", "")
    # Re-validate from scratch — never trust that the GET's check still
    # holds by the time the form is submitted.
    claim = claims.verify_action_token(claim_id, token)
    if claim is None:
        return templates.TemplateResponse(request, "claim_action.html", {"state": "invalid"})

    if action == "approve":
        try:
            claims.approve_request(claim_id)
        except stripe_client.StripeError as exc:
            return templates.TemplateResponse(
                request, "claim_action.html", {"state": "error", "message": f"Stripe error — {exc}"}
            )
        message = "Approved. The requester has been emailed next steps."
    else:
        reason = fields.get("reason", "").strip() or "Not approved"
        claims.deny_request(claim_id, reason)
        message = "Denied. The requester has been notified."

    return templates.TemplateResponse(request, "claim_action.html", {"state": "done", "message": message})


@app.get("/api/health")
def health():
    return {"staging_dir": str(STAGING_DIR), "ok": True}
