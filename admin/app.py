"""FastAPI admin app — UX.md §1 single-screen hub. Gate 3 scope only: harvest
panel is stubbed (real pipeline is Gate 4), deploy strip is not built here
(Gate 5). Vanilla JS + Jinja2 per TRD.md §2 — no SPA framework.
"""

from __future__ import annotations

import datetime
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request

from admin.config import SITE_DIST_DIR, SITE_FONTS_DIR, STAGING_DIR
from admin.mdx_preview import render_body_html
from admin.pipeline import staging
from admin.pipeline.staging import UndoExpired, ValidationFailed

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Bathers' Admin")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="admin-static")
if SITE_DIST_DIR.exists():
    app.mount("/site-dist", StaticFiles(directory=str(SITE_DIST_DIR)), name="site-dist")
if SITE_FONTS_DIR.exists():
    app.mount("/fonts", StaticFiles(directory=str(SITE_FONTS_DIR)), name="admin-fonts")


def _site_css_href() -> str | None:
    if not SITE_DIST_DIR.exists():
        return None
    matches = sorted((SITE_DIST_DIR / "_astro").glob("*.css")) if (SITE_DIST_DIR / "_astro").exists() else []
    if not matches:
        return None
    return f"/site-dist/_astro/{matches[0].name}"


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
    return {**_entry_summary(entry), "frontmatter": entry.frontmatter, "body": entry.body}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


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
            "css_href": _site_css_href(),
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


@app.post("/api/harvest")
def api_harvest(body: HarvestBody):
    # Pipeline stubbed for Gate 3 (real Harvester/Architect/Gatekeeper wiring
    # is Gate 4, CLAUDE.md). Log pane is wired to real responses so the UI
    # shape doesn't change when the pipeline lands.
    now = datetime.datetime.now().strftime("%H:%M:%S")
    return {
        "lines": [
            {"time": now, "level": "info", "text": f"fetching {body.url}"},
            {"time": now, "level": "error", "text": "pipeline not implemented yet — arrives in Gate 4"},
        ]
    }


@app.get("/api/health")
def health():
    return {"staging_dir": str(STAGING_DIR), "ok": True}
