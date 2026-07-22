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
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request

from admin.config import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    CATEGORY_LABELS,
    SITE_BLOG_IMAGES_DIR,
    SITE_DIST_DIR,
    SITE_FONTS_DIR,
    STAGING_DIR,
    STATES,
    VENUES_JSON_PATH,
)
from admin.mdx_preview import render_body_html
from admin.pipeline import blog, deploy, discovery, goatcounter, images, orchestrator, places, staging
from admin.pipeline.blog import ValidationFailed as BlogValidationFailed
from admin.pipeline.staging import UndoExpired, ValidationFailed

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Bathers' Admin")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="admin-static")
# Mounted unconditionally (dir created if missing) so a later `npm run build`
# becomes visible on the next request with no admin restart required.
SITE_DIST_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/site-dist", StaticFiles(directory=str(SITE_DIST_DIR)), name="site-dist")
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
    # No credentials configured (local dev's .env leaves these blank) — auth stays off.
    if not ADMIN_USERNAME and not ADMIN_PASSWORD:
        return await call_next(request)
    if not _basic_auth_ok(request.headers.get("authorization")):
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Bathers Admin"'})
    return await call_next(request)


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


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"states": STATES, "categories": CATEGORY_LABELS})


@app.get("/blog", response_class=HTMLResponse)
def blog_page(request: Request):
    return templates.TemplateResponse(request, "blog.html", {})


@app.get("/preview/{slug}", response_class=HTMLResponse)
def preview(request: Request, slug: str):
    try:
        entry = staging.get_staging(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"no staged draft for '{slug}'")
    return templates.TemplateResponse(
        request,
        "preview.html",
        {
            "data": entry.frontmatter,
            "body_html": render_body_html(entry.body),
            "css_hrefs": _site_css_hrefs(),
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


@app.post("/api/venues/{slug}/remove-image")
def api_remove_published_image(slug: str):
    # UX.md §4.4 takedown/claim action — no UI surfaces this yet (the claim
    # workflow itself is out of scope per TRD.md §8), but the single admin
    # action itself is required regardless of who triggers it.
    try:
        staging.remove_published_image(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"no published venue '{slug}'")
    return {"ok": True}


@app.get("/api/deploy/status")
def api_deploy_status():
    return deploy.status_summary()


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


_deploy_lock = threading.Lock()  # deploy shells out to git; keep it to one run at a time


@app.post("/api/deploy")
def api_deploy(body: DeployBody):
    if not _deploy_lock.acquire(blocking=False):
        raise HTTPException(409, "a deploy is already running")

    def stream():
        try:
            for line in deploy.run_deploy(body.commit_message):
                yield _sse_line({"time": line.time, "level": line.level, "text": line.text})
        finally:
            _deploy_lock.release()
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
    return _blog_detail(entry, location)


@app.delete("/api/blog/{slug}")
def api_delete_blog_draft(slug: str):
    try:
        blog.delete_draft(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"no draft '{slug}'")
    return {"ok": True}


@app.post("/api/blog/{slug}/publish")
def api_publish_blog_post(slug: str):
    try:
        blog.publish(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"no draft '{slug}'")
    except BlogValidationFailed as exc:
        raise HTTPException(422, detail={"errors": exc.errors})
    return {"ok": True}


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


@app.get("/api/health")
def health():
    return {"staging_dir": str(STAGING_DIR), "ok": True}
