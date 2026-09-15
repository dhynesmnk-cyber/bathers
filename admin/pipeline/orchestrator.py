"""Wires Harvester -> Architect -> Gatekeeper into one harvest run (TRD.md §7),
streaming a LogLine per stage so the admin UI's log pane stays truthful
(UX.md §1.1 — "never replace this with a spinner"). Runs synchronously; the
caller drains the generator to stream it out (SSE) or collect it (batch).
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from dataclasses import asdict, dataclass
from typing import Iterator
from urllib.parse import urlsplit

from admin.config import AMENITY_KEYS, DEFAULT_COUNTRY, FAILED_DIR, MODEL_ARCHITECT, MODEL_GATEKEEPER, MODEL_HARVESTER, PUBLISHED_DIR, ROOT, STAGING_DIR
from admin import schema
from admin.pipeline import agents, drivetime, geocode, harvest, images, outreach_store, places, staging, verification
from admin.pipeline.staging import render_mdx, split_frontmatter

HARVESTER_REQUIRED_KEYS = (
    "name", "country", "state_province", "city", "zipcode", "address", "latitude", "longitude",
    "website", "contact_email", "amenities", "facts", "confidence_notes",
)

# Addresses a venue's own page can carry that are not the venue's (Gate 13,
# 2026-09-10). The Harvester is told not to emit these (PROMPTS/harvester.md
# rule 9) but a shared footer makes them easy to mistake for the contact
# address, and writing to one means asking a booking platform or a web agency
# to confirm facts about someone else's venue.
_NON_OPERATOR_EMAIL_LOCAL_PARTS = frozenset(
    {"webmaster", "postmaster", "noreply", "no-reply", "donotreply", "abuse", "privacy"}
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


def _resolve_contact_email(harvester_data: dict, website: str | None) -> tuple[str | None, str | None]:
    """(email, note) — the Harvester's `contact_email`, or None with a reason.

    Kept a machine step rather than an agent judgement for the same reason
    amenities are re-stamped below: this address is used to write to a real
    business, so a malformed or obviously-not-theirs value must be dropped
    here, not caught by a reviewer reading prose. `note` is logged so a
    dropped address is visible in the harvest log rather than silent.
    """
    raw = harvester_data.get("contact_email")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, None
    if not isinstance(raw, str):
        return None, f"harvester returned a non-string contact_email ({type(raw).__name__}) — dropped"
    email = raw.strip().strip("<>.,;: \t\r\n")
    if not schema._is_email(email):
        return None, f"harvester returned an unusable contact_email ({email!r}) — dropped"
    local, _, domain = email.rpartition("@")
    if local.lower() in _NON_OPERATOR_EMAIL_LOCAL_PARTS:
        return None, f"contact_email {email!r} is an administrative address, not an operator's — dropped"
    note = None
    site_host = _bare_host(website)
    if site_host and _bare_host(domain) != site_host:
        # Not dropped: plenty of small operators publish a gmail address, and
        # guessing which off-domain addresses are wrong would lose real ones.
        # Flagged so the reviewer looks before outreach writes to it.
        note = f"contact_email {email!r} is not on the venue's own domain ({site_host}) — confirm it before outreach"
    return email, note


def _bare_host(url: str | None) -> str | None:
    """Host of a URL or a bare hostname, lowercased and www-stripped."""
    if not url:
        return None
    host = urlsplit(url if "//" in url else f"//{url}").netloc.lower()
    host = host.split(":")[0].removeprefix("www.")
    return host or None


def _finalize_frontmatter(gate_fm: dict, harvester_data: dict, coords: tuple[float, float] | None, url: str) -> dict:
    final = dict(gate_fm)
    final["source_url"] = url
    if not final.get("website"):
        # The Harvester only reads scraped body text, so a venue's own site
        # rarely appears as a fact within it — but we already fetched this
        # page from `url`, the same assumption already made for source_url.
        final["website"] = url
    final["drafted"] = datetime.date.today()
    final["verified"] = datetime.date.today()
    final.setdefault("status", "unclaimed")
    # Amenities are the Harvester's finding, not the Architect/Gatekeeper's —
    # enforce that rather than trusting it survived two rewrite passes intact.
    final["amenities"] = {key: bool(harvester_data["amenities"].get(key, False)) for key in AMENITY_KEYS}
    if coords and not final.get("latitude"):
        final["latitude"] = coords[0]
    if coords and not final.get("longitude"):
        final["longitude"] = coords[1]
    # Gate 7 (2026-07-31): drive-time + per-field verification are stamped by
    # the pipeline, not the agents — same posture as `verified` above. Drive-
    # time is OSRM-computed from the just-resolved coordinates; verification
    # marks every populated verifiable field `published_by_venue` from this
    # harvest's source URL (Gate 8 outreach upgrades individual fields later).
    dt = drivetime.drive_time(
        final.get("latitude"), final.get("longitude"), final.get("country", DEFAULT_COUNTRY)
    )
    if dt:
        final["drive_time"] = dt
    block = verification.build_verification(
        final, source=url, tier="published_by_venue", date=final["verified"]
    )
    if block:
        final["verification"] = block
    return final


def run_harvest_pipeline(url: str, use_playwright: bool = False, allow_existing_slug: bool = False) -> Iterator[LogLine]:
    """`allow_existing_slug` is a narrow, deliberate escape hatch for
    re-harvesting a venue that already has a slug in `_published` or
    `_staging` — e.g. regenerating existing content after a prompt/voice
    change. It never writes to `_published` directly (CLAUDE.md rule 5);
    output still lands in `_staging/`, to be reviewed and approved normally.
    The normal single-URL harvest form never sets this — it always goes
    through the duplicate-slug guards below."""
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

    harvester_input = result.text
    if result.title or result.meta_description:
        # Body extraction strips header/nav/footer chrome as boilerplate, which is
        # often exactly where a venue's name lives — trafilatura's own page
        # metadata (title/description) carries it instead.
        harvester_input = (
            f"Page title: {result.title or '(none)'}\n"
            f"Page description: {result.meta_description or '(none)'}\n\n"
            f"Body text:\n{result.text}"
        )

    # Pricing usually lives off the homepage (2026-07-23 — see
    # harvest.find_pricing_links). Follow the strongest 1–2 internal pricing
    # links and append their text as labelled blocks, so `facts.pricing`
    # can be populated from the venue's own published rates. Failures are
    # non-fatal — the harvest proceeds on the main page alone.
    # On a browser-backed run (user-triggered, so still within the
    # "Playwright fallback only" rule) the pricing links get the same
    # fetcher as the main page — a site whose main page needed JS rendering
    # renders its pricing pages the same way.
    fetch_extra = harvest.harvest_with_playwright if use_playwright else harvest.harvest
    for link in harvest.find_pricing_links(result.html, url):
        try:
            extra = fetch_extra(link)
        except (harvest.RobotsDisallowed, harvest.ScrapeError) as exc:
            log(f"pricing link {link} — fetch failed ({exc})", "warn")
            yield from drain()
            continue
        if len(extra.text) < 200:
            log(f"pricing link {link} — thin extraction, ignored", "warn")
            yield from drain()
            continue
        harvester_input += f"\n\nAdditional page from the same site ({link}):\n{extra.text[:6000]}"
        log(f"followed pricing link {link}  ok ({len(extra.text)} chars)")
        yield from drain()

    try:
        harvester_data, _usage = agents.call_agent(
            model=MODEL_HARVESTER,
            system=agents.load_prompt("harvester.md"),
            user_content=harvester_input,
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

    # Pool-or-sauna eligibility (TRD.md §8's 2026-07-26 scope note): a venue
    # must have a real pool or sauna as a central offering, not just a
    # treatment menu. `facts.pools` (not just the `magnesium_pool` boolean)
    # is checked too, since the Harvester only sets that boolean when the
    # word "magnesium" appears — a genuine thermal-springs/artesian venue
    # with no magnesium/sauna wording would otherwise be wrongly rejected.
    amenities = harvester_data.get("amenities") or {}
    has_sauna_or_named_pool = any(amenities.get(k) for k in ("magnesium_pool", "infrared_sauna", "traditional_sauna"))
    has_pool_evidence = bool((harvester_data.get("facts") or {}).get("pools"))
    if not (has_sauna_or_named_pool or has_pool_evidence):
        log("no pool or sauna evidence on this page — out of scope for this directory", "error")
        yield from drain()
        return

    slug = slugify(name)
    if not allow_existing_slug:
        if (PUBLISHED_DIR / f"{slug}.mdx").exists():
            log(f"slug '{slug}' exists in _published — skipping (view existing?)", "error")
            yield from drain()
            return
        if (STAGING_DIR / f"{slug}.mdx").exists():
            log(f"slug '{slug}' already staged — skipping", "error")
            yield from drain()
            return
    else:
        log(f"regenerating '{slug}' (allow_existing_slug) — output still lands in _staging/", "warn")
        yield from drain()

    coords = None
    address = harvester_data.get("address")
    if address:
        coords = geocode.geocode_address(
            address, harvester_data.get("country", DEFAULT_COUNTRY), log=log
        )
        if coords:
            log(f"geocoded address → {coords[0]:.4f}, {coords[1]:.4f}")
        yield from drain()

    places_result = places.check_listing(
        name,
        harvester_data.get("city"),
        harvester_data.get("state_province"),
        harvester_data.get("country", DEFAULT_COUNTRY),
    )
    # Google's Place ID is stable across harvest runs even when the Harvester
    # extracts a different display name (and therefore a different slug) for
    # the same physical venue — key temp_data storage on it when available so
    # a later re-harvest doesn't orphan the first run's Places/image data.
    image_key = places_result.place_id if (places_result.found and places_result.place_id) else slug
    places.record_slug_key(slug, image_key)
    places.save_check(image_key, places_result)
    if places_result.skipped:
        log("Google Places check skipped — GOOGLE_PLACES_API_KEY not set")
    elif places_result.error:
        log(f"Google Places check inconclusive — {places_result.error}", "warn")
    elif places_result.found:
        log(f"checking Google Places... found: {places_result.formatted_address}")
    else:
        log("checking Google Places... NO LISTING FOUND, flagging for review", "warn")
    yield from drain()

    # Appended as a separate labelled block rather than merged into the
    # Harvester JSON contract (SCHEMA.md's "one contract, four consumers"
    # rule) — both the Architect and Gatekeeper need to see it, since the
    # Gatekeeper's fact audit only trusts what's in its own prompt input.
    places_block = (
        f"\n\n---\nGoogle Places verification (authoritative if present):\n{json.dumps(asdict(places_result), indent=2)}"
        if not places_result.skipped
        else ""
    )

    architect_input = json.dumps(harvester_data, indent=2) + places_block
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
    gatekeeper_input = (
        f"{architect_mdx}\n\n---\nHarvester JSON (for the fact audit):\n{json.dumps(harvester_data, indent=2)}"
        + places_block
    )
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

    # The operator's published address goes to the gitignored outreach store,
    # never into frontmatter (owner decision, 2026-09-15): the directory should
    # not publish a business's contact address on its behalf, and `_published/`
    # is committed to a public repository. It is still the Harvester's finding
    # rather than the Architect's — resolved straight from the Harvester JSON,
    # the same posture as `amenities` — it just lands somewhere else.
    #
    # A store failure must not fail a harvest that otherwise succeeded: the
    # draft is already written, and the address is recoverable by re-running
    # `backfill_contact_email`. Same reasoning as approve()'s ensure() call.
    contact_email, email_note = _resolve_contact_email(harvester_data, final_fm.get("website"))
    if email_note:
        log(email_note, "warn")
    if contact_email:
        try:
            outreach_store.set_published_email(slug, contact_email)
            log(f"contact address recorded for outreach — {contact_email}")
        except Exception as exc:  # noqa: BLE001 — see comment above
            log(f"could not record the contact address for {slug} — {exc}", "warn")
    for dupe in staging.find_duplicates(slug, final_fm):
        log(f"possible duplicate of {dupe['name']} ({dupe['location']}: {dupe['slug']}) — {dupe['reason']}", "warn")
    yield from drain()

    candidate_urls = images.discover_image_urls(result.html, url)
    attributions: dict[str, str] = {}
    if places_result.photos:
        for photo in places_result.photos:
            photo_url = places.fetch_photo_media_url(photo.name)
            candidate_urls.append(photo_url)
            attributions[photo_url] = photo.attribution
        log(f"Google Places supplied {len(places_result.photos)} candidate photo(s)")
        yield from drain()
    if candidate_urls:
        images.record_slug_key(slug, image_key)
        candidates = images.download_candidates(candidate_urls, image_key, attributions=attributions)
        if candidates:
            log(f"downloaded {len(candidates)} candidate image(s) → temp_data/images/{image_key}/")
            yield from drain()


def _save_failed(stage: str, key: str, raw_text: str, log) -> None:
    FAILED_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _now().replace(":", "")
    safe_key = re.sub(r"[^a-zA-Z0-9]+", "-", key).strip("-")[:60] or "unknown"
    path = FAILED_DIR / f"{safe_key}-{stage}-{stamp}.txt"
    path.write_text(raw_text, encoding="utf-8")
    log(f"{stage} agent failed validation after retry — raw output saved to {path.relative_to(ROOT)}", "error")


def _self_test() -> int:
    """Proves the contact_email guard (Gate 13, 2026-09-10).

    This is the one harvested field the pipeline uses to *write to a real
    business*, so its rejections are asserted alongside a clean pass — a guard
    that only ever says no would be indistinguishable from one that drops
    everything, which is exactly how a field stays empty on all 39 venues
    without anybody noticing.
    """
    site = "https://example-bathhouse.com.au/visit"
    cases: list[tuple[str, bool]] = []

    def resolve(raw, website=site):
        return _resolve_contact_email({"contact_email": raw}, website)

    email, note = resolve("hello@example-bathhouse.com.au")
    cases.append(("a published on-domain address is kept, unflagged", email == "hello@example-bathhouse.com.au" and note is None))

    email, note = resolve("  <Bookings@Example-Bathhouse.com.au>,  ")
    cases.append(("stray punctuation and brackets are stripped", email == "Bookings@Example-Bathhouse.com.au"))

    email, note = resolve(None)
    cases.append(("a null address stays null, with nothing to log", email is None and note is None))

    email, note = resolve("   ")
    cases.append(("a blank string is treated as null", email is None and note is None))

    email, note = resolve("not an address")
    cases.append(("a malformed address is dropped with a reason", email is None and note is not None))

    email, note = resolve(["a@b.com"])
    cases.append(("a non-string address is dropped with a reason", email is None and "non-string" in (note or "")))

    email, note = resolve("noreply@example-bathhouse.com.au")
    cases.append(("an administrative address is dropped", email is None and "administrative" in (note or "")))

    email, note = resolve("hello@some-booking-platform.com")
    cases.append(("an off-domain address is kept but flagged", email == "hello@some-booking-platform.com" and "not on the venue's own domain" in (note or "")))

    email, note = resolve("hello@www.example-bathhouse.com.au")
    cases.append(("a www-prefixed host is not mistaken for a different domain", email and note is None))

    email, note = resolve("hello@anything.com", website=None)
    cases.append(("with no website to compare against, nothing is flagged", email == "hello@anything.com" and note is None))

    cases.append(("contact_email is a required Harvester key", "contact_email" in HARVESTER_REQUIRED_KEYS))
    # The address is collected but never published (owner decision, 2026-09-15).
    # Asserted from both directions: it must not be a frontmatter field, and it
    # must not be in the render order — either one would put an operator's
    # address into a public repository on the next re-save.
    cases.append((
        "contact_email is NOT a published frontmatter field",
        "contact_email" not in schema.KNOWN_FIELDS,
    ))
    cases.append((
        "render_frontmatter would not write contact_email into published content",
        "contact_email" not in staging.FRONTMATTER_FIELD_ORDER,
    ))
    cases.append((
        "the outreach store can hold it instead",
        "published_email" in outreach_store.COLUMNS,
    ))

    for label, ok in cases:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    return 0 if all(ok for _, ok in cases) else 1


def main() -> None:
    if "--self-test" in sys.argv:
        raise SystemExit(_self_test())
    raise SystemExit("orchestrator has no CLI beyond --self-test; harvest runs from the admin app")


if __name__ == "__main__":
    main()
