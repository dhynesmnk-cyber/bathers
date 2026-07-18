"""Wires Harvester -> Architect -> Gatekeeper into one harvest run (TRD.md §7),
streaming a LogLine per stage so the admin UI's log pane stays truthful
(UX.md §1.1 — "never replace this with a spinner"). Runs synchronously; the
caller drains the generator to stream it out (SSE) or collect it (batch).
"""

from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass
from typing import Iterator

from admin.config import AMENITY_KEYS, FAILED_DIR, MODEL_ARCHITECT, MODEL_GATEKEEPER, MODEL_HARVESTER, PUBLISHED_DIR, ROOT, STAGING_DIR
from admin.pipeline import agents, geocode, harvest, images
from admin.pipeline.staging import render_mdx, split_frontmatter

HARVESTER_REQUIRED_KEYS = (
    "name", "state", "suburb", "address", "latitude", "longitude",
    "website", "amenities", "facts", "confidence_notes",
)


@dataclass
class LogLine:
    time: str
    level: str
    text: str


@dataclass
class HarvestOutcome:
    ok: bool
    slug: str | None = None
    thin_extraction: bool = False


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "untitled"


def _now() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n(.*)\n```$", re.DOTALL)


def _strip_code_fence(text: str) -> str:
    """Models are told not to wrap output in markdown fences and do it anyway
    often enough that stripping it is cheaper and more reliable than burning
    the one UX.md-mandated retry on pure formatting."""
    match = _FENCE_RE.match(text.strip())
    return match.group(1).strip() if match else text.strip()


def _validate_harvester_json(text: str) -> dict:
    text = _strip_code_fence(text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON — {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("top-level JSON must be an object")
    missing = [key for key in HARVESTER_REQUIRED_KEYS if key not in data]
    if missing:
        raise ValueError(f"missing keys: {', '.join(missing)}")
    if not isinstance(data["amenities"], dict):
        raise ValueError("amenities must be an object")
    return data


def _validate_mdx(text: str) -> tuple[dict, str]:
    text = _strip_code_fence(text)
    if not text.startswith("---"):
        raise ValueError("missing frontmatter delimiter")
    try:
        data, body = split_frontmatter(text, "draft")
    except Exception as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(data, dict) or not data.get("name"):
        raise ValueError("frontmatter missing or has no name")
    if not body.strip():
        raise ValueError("body is empty")
    return data, body


def _finalize_frontmatter(gate_fm: dict, harvester_data: dict, coords: tuple[float, float] | None, url: str) -> dict:
    final = dict(gate_fm)
    final["source_url"] = url
    if not final.get("website"):
        # The Harvester only reads scraped body text, so a venue's own site
        # rarely appears as a fact within it — but we already fetched this
        # page from `url`, the same assumption already made for source_url.
        final["website"] = url
    final["drafted"] = datetime.date.today().isoformat()
    final.setdefault("status", "unclaimed")
    # Amenities are the Harvester's finding, not the Architect/Gatekeeper's —
    # enforce that rather than trusting it survived two rewrite passes intact.
    final["amenities"] = {key: bool(harvester_data["amenities"].get(key, False)) for key in AMENITY_KEYS}
    if coords and not final.get("latitude"):
        final["latitude"] = coords[0]
    if coords and not final.get("longitude"):
        final["longitude"] = coords[1]
    return final


def run_harvest_pipeline(url: str, use_playwright: bool = False) -> Iterator[LogLine]:
    lines: list[LogLine] = []

    def log(text: str, level: str = "info") -> None:
        lines.append(LogLine(_now(), level, text))

    def drain() -> Iterator[LogLine]:
        nonlocal lines
        out, lines = lines, []
        yield from out

    log(f"fetching {url}")
    yield from drain()
    try:
        result = harvest.harvest_with_playwright(url) if use_playwright else harvest.harvest(url)
    except harvest.RobotsDisallowed as exc:
        log(str(exc), "error")
        yield from drain()
        return
    except harvest.ScrapeError as exc:
        log(f"fetch failed — {exc}", "error")
        yield from drain()
        return
    log(f"fetching {url}  ok ({result.html_bytes // 1000} kB)")
    yield from drain()

    if result.thin:
        log(f"thin extraction — {len(result.text)} chars — try 'Retry with Playwright'", "warn")
        yield from drain()
        return
    log(f"extracting text (trafilatura)  ok ({len(result.text)} chars)")
    yield from drain()

    try:
        harvester_data, _usage = agents.call_agent(
            model=MODEL_HARVESTER,
            system=agents.load_prompt("harvester.md"),
            user_content=result.text,
            max_tokens=2048,
            validate=_validate_harvester_json,
            log=log,
        )
    except agents.MalformedOutput as exc:
        _save_failed("harvester", url, exc.raw_text, log)
        yield from drain()
        return
    except agents.AgentError as exc:
        log(f"harvester agent failed — {exc}", "error")
        yield from drain()
        return
    yield from drain()

    name = harvester_data.get("name")
    if not name:
        note = "; ".join(harvester_data.get("confidence_notes") or []) or "not a spa/bathhouse page"
        log(f"harvester could not identify a venue on this page — {note}", "error")
        yield from drain()
        return

    slug = slugify(name)
    if (PUBLISHED_DIR / f"{slug}.mdx").exists():
        log(f"slug '{slug}' exists in _published — skipping (view existing?)", "error")
        yield from drain()
        return
    if (STAGING_DIR / f"{slug}.mdx").exists():
        log(f"slug '{slug}' already staged — skipping", "error")
        yield from drain()
        return

    coords = None
    address = harvester_data.get("address")
    if address:
        coords = geocode.geocode_address(address)
        if coords:
            log(f"geocoded address → {coords[0]:.4f}, {coords[1]:.4f}")
        yield from drain()

    architect_input = json.dumps(harvester_data, indent=2)
    try:
        (architect_fm, architect_body), _usage = agents.call_agent(
            model=MODEL_ARCHITECT,
            system=agents.load_prompt("architect.md"),
            user_content=architect_input,
            max_tokens=4096,
            validate=_validate_mdx,
            log=log,
        )
    except agents.MalformedOutput as exc:
        _save_failed("architect", slug, exc.raw_text, log)
        yield from drain()
        return
    except agents.AgentError as exc:
        log(f"architect agent failed — {exc}", "error")
        yield from drain()
        return
    architect_word_count = len(architect_body.split())
    log(f"architect agent ({MODEL_ARCHITECT})  ok — {architect_word_count} words")
    yield from drain()

    architect_mdx = render_mdx(architect_fm, architect_body)
    gatekeeper_input = f"{architect_mdx}\n\n---\nHarvester JSON (for the fact audit):\n{json.dumps(harvester_data, indent=2)}"
    try:
        (gate_fm, gate_body), _usage = agents.call_agent(
            model=MODEL_GATEKEEPER,
            system=agents.load_prompt("gatekeeper.md"),
            user_content=gatekeeper_input,
            max_tokens=4096,
            validate=_validate_mdx,
            log=log,
        )
    except agents.MalformedOutput as exc:
        _save_failed("gatekeeper", slug, exc.raw_text, log)
        yield from drain()
        return
    except agents.AgentError as exc:
        log(f"gatekeeper agent failed — {exc}", "error")
        yield from drain()
        return
    gate_word_count = len(gate_body.split())
    log(f"gatekeeper agent ({MODEL_GATEKEEPER})  ok — {gate_word_count} words")
    yield from drain()

    final_fm = _finalize_frontmatter(gate_fm, harvester_data, coords, url)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    (STAGING_DIR / f"{slug}.mdx").write_text(render_mdx(final_fm, gate_body), encoding="utf-8")
    log(f"saved → _staging/{slug}.mdx")
    yield from drain()

    candidate_urls = images.discover_image_urls(result.html, url)
    if candidate_urls:
        candidates = images.download_candidates(candidate_urls, slug)
        if candidates:
            log(f"downloaded {len(candidates)} candidate image(s) → temp_data/images/{slug}/")
            yield from drain()


def _save_failed(stage: str, key: str, raw_text: str, log) -> None:
    FAILED_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _now().replace(":", "")
    safe_key = re.sub(r"[^a-zA-Z0-9]+", "-", key).strip("-")[:60] or "unknown"
    path = FAILED_DIR / f"{safe_key}-{stage}-{stamp}.txt"
    path.write_text(raw_text, encoding="utf-8")
    log(f"{stage} agent failed validation after retry — raw output saved to {path.relative_to(ROOT)}", "error")
