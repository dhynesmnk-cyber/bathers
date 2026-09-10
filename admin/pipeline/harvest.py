"""Scrape a venue URL to plain text (TRD.md §2): httpx + trafilatura, robots.txt
respected, 20s timeout, one job at a time (enforced by the caller — this
module has no concurrency of its own). Playwright is an explicit
user-triggered fallback (UX.md §1.5 "Retry with Playwright"), never automatic.
"""

from __future__ import annotations

import re
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura

TIMEOUT_SECONDS = 20.0
THIN_EXTRACTION_CHARS = 500
USER_AGENT = "WhereWeBatheBot/1.0 (local admin tool; contact via venue's own listing)"


class ScrapeError(Exception):
    pass


class RobotsDisallowed(Exception):
    pass


@dataclass
class ScrapeResult:
    text: str
    html: str
    html_bytes: int
    thin: bool
    title: str | None = None
    meta_description: str | None = None


def _robots_allowed(url: str) -> bool:
    parts = urlsplit(url)
    robots_url = urljoin(f"{parts.scheme}://{parts.netloc}", "/robots.txt")
    try:
        response = httpx.get(robots_url, timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT})
    except httpx.HTTPError:
        return True  # no reachable robots.txt — proceed
    if response.status_code >= 400:
        return True
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser.can_fetch(USER_AGENT, url)


def fetch_html(url: str) -> str:
    if not _robots_allowed(url):
        raise RobotsDisallowed(f"robots.txt disallows fetching {url}")
    try:
        response = httpx.get(
            url, timeout=TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        )
    except httpx.TimeoutException as exc:
        raise ScrapeError(f"timed out after {TIMEOUT_SECONDS:.0f}s") from exc
    except httpx.HTTPError as exc:
        raise ScrapeError(str(exc)) from exc
    if response.status_code >= 400:
        raise ScrapeError(f"HTTP {response.status_code}")
    return response.text


def extract_text(html: str, url: str) -> str:
    text = trafilatura.extract(html, url=url, favor_recall=True)
    return (text or "").strip()


def extract_metadata(html: str, url: str) -> tuple[str | None, str | None]:
    """Page <title> and meta description — often carry the venue's name and a
    marketing summary that trafilatura's body extraction strips as boilerplate
    (header/nav/footer chrome), especially on non-article-style pages."""
    doc = trafilatura.extract_metadata(html, default_url=url)
    if doc is None:
        return None, None
    return doc.title or None, doc.description or None


# ---- Pricing-link discovery (2026-07-23) ----
#
# Most venue homepages don't publish prices — pricing lives on a separate
# /pricing, /rates or booking page, so single-page harvests leave `cost`
# honestly empty. These helpers find the 1–2 most likely internal pricing
# links in the fetched HTML; the orchestrator fetches them through the same
# robots/timeout machinery and appends their text to the Harvester input.

_PRICING_STRONG = {"pricing", "prices", "price", "rates", "admission", "tariff", "fees", "cost"}
_PRICING_WEAK = {"bathe", "bathing", "book", "experience", "package", "packages",
                 "treatment", "treatments", "menu", "service", "services"}
# Generic pages that share a keyword ("terms-of-service", "privacy-policy") but
# never carry pricing — presence of any of these tokens disqualifies a link.
_PRICING_NOISE = {"terms", "privacy", "policy", "cookie", "cookies", "contact",
                  "about", "careers", "blog", "news", "faq", "gift", "voucher"}
_ANCHOR_RE = re.compile(r"<a\b[^>]*?href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
_SKIP_EXTENSIONS_RE = re.compile(r"\.(pdf|jpe?g|png|webp|svg|gif|zip|docx?)$", re.I)


def find_pricing_links(html: str, base_url: str, limit: int = 2) -> list[str]:
    """Same-host links whose path or anchor text suggests a pricing page,
    strongest matches first. Never leaves the venue's own site."""
    base = urlsplit(base_url)
    base_host = base.netloc.lower().removeprefix("www.")
    scored: dict[str, int] = {}
    for match in _ANCHOR_RE.finditer(html):
        absolute = urljoin(base_url, match.group(1)).split("#")[0]
        parts = urlsplit(absolute)
        if parts.scheme not in ("http", "https"):
            continue
        if parts.netloc.lower().removeprefix("www.") != base_host:
            continue
        if parts.path.rstrip("/") == base.path.rstrip("/"):
            continue  # the page we already have
        if _SKIP_EXTENSIONS_RE.search(parts.path):
            continue
        anchor_text = re.sub(r"<[^>]+>", " ", match.group(2)).lower()
        # Whole-word tokens from the path and anchor, so "service" matches
        # /services but "terms-of-service" is caught by the noise set below
        # (and "prices" doesn't fire on an unrelated "enterprises").
        tokens = set(re.findall(r"[a-z]+", f"{parts.path.lower()} {anchor_text}"))
        if tokens & _PRICING_NOISE:
            continue
        if tokens & _PRICING_STRONG:
            score = 2
        elif tokens & _PRICING_WEAK:
            score = 1
        else:
            continue
        scored[absolute] = max(scored.get(absolute, 0), score)
    ranked = sorted(scored, key=lambda link: (-scored[link], len(link)))
    return ranked[:limit]


# --- Contact addresses (Gate 13, 2026-09-10) -----------------------------
# Outreach needs an address to write to, and `contact_email` was null on all 39
# published venues because nothing collected it. These two helpers read
# candidates out of the fetched HTML rather than asking a model to produce one:
# an address that was never on the page cannot come out of a literal scan, and
# for a field used to email a real business that guarantee is worth more than
# the flexibility of free-form extraction.

_EMAIL_IN_HTML_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
# Local parts nobody at a bathhouse reads, and addresses belonging to the tools
# a site is built with rather than to the venue.
_EMAIL_LOCAL_NOISE = frozenset({
    "webmaster", "postmaster", "noreply", "no-reply", "donotreply", "do-not-reply",
    "abuse", "privacy", "dmca", "unsubscribe", "mailer-daemon", "root", "admin@example",
})
_EMAIL_DOMAIN_NOISE = (
    "example.com", "example.org", "example.net", "domain.com", "yourdomain.com",
    "email.com", "sentry.io", "wixpress.com", "squarespace.com", "shopify.com",
    "godaddy.com", "cloudflare.com", "wordpress.com", "sentry-next.wixpress.com",
)
# `logo@2x.png`, `icon@3x.svg` — retina asset names look exactly like addresses.
_EMAIL_ASSET_RE = re.compile(r"\.(png|jpe?g|webp|svg|gif|css|js|woff2?)$", re.I)
# Preference order within a venue's own domain. A general or bookings address is
# the one an operator answers; a named individual is a fallback, not a target.
_EMAIL_LOCAL_PREFERRED = ("bookings", "booking", "reservations", "enquiries", "enquiry",
                          "inquiries", "info", "hello", "hi", "contact", "reception", "stay")

_CONTACT_STRONG = {"contact", "contactus", "enquiries", "enquiry", "bookings"}
_CONTACT_WEAK = {"about", "visit", "faq", "faqs", "help"}


def _plausible_email(candidate: str) -> bool:
    local, _, domain = candidate.rpartition("@")
    if not local or "." not in domain:
        return False
    if local.lower() in _EMAIL_LOCAL_NOISE:
        return False
    if _EMAIL_ASSET_RE.search(candidate):
        return False
    lowered = domain.lower()
    if any(lowered == noise or lowered.endswith("." + noise) for noise in _EMAIL_DOMAIN_NOISE):
        return False
    # A bare TLD-ish tail like `@2x.png` is caught above; this catches `@1.2`.
    return bool(re.match(r"^[A-Za-z]{2,}$", lowered.rsplit(".", 1)[-1]))


def find_contact_emails(html: str, base_url: str | None = None) -> list[str]:
    """Literal addresses published on the page, best candidate first.

    `mailto:` hrefs rank above addresses found in body text — a site that links
    an address is stating it is for contacting them. Within each group, the
    venue's own domain beats an off-domain address, and a general or bookings
    local part beats a named individual. Order is the ranking; the caller
    decides how much of it to keep.
    """
    site_host = None
    if base_url:
        site_host = urlsplit(base_url).netloc.lower().split(":")[0].removeprefix("www.")

    linked: list[str] = []
    for match in _ANCHOR_RE.finditer(html):
        href = match.group(1).strip()
        if not href.lower().startswith("mailto:"):
            continue
        address = href[len("mailto:"):].split("?")[0].strip()
        for found in _EMAIL_IN_HTML_RE.findall(address):
            linked.append(found)

    in_text = _EMAIL_IN_HTML_RE.findall(re.sub(r"<[^>]+>", " ", html))

    def rank(address: str) -> tuple[int, int, int]:
        local, _, domain = address.rpartition("@")
        host = domain.lower().removeprefix("www.")
        on_domain = 0 if (site_host and (host == site_host or host.endswith("." + site_host))) else 1
        try:
            preference = _EMAIL_LOCAL_PREFERRED.index(local.lower())
        except ValueError:
            preference = len(_EMAIL_LOCAL_PREFERRED)
        return (on_domain, preference, len(address))

    ranked: list[str] = []
    seen: set[str] = set()
    for group in (linked, in_text):
        for address in sorted({a for a in group if _plausible_email(a)}, key=rank):
            if address.lower() in seen:
                continue
            seen.add(address.lower())
            ranked.append(address)
    return ranked


def find_contact_links(html: str, base_url: str, limit: int = 2) -> list[str]:
    """Same-host contact/enquiries pages, strongest first — where a venue that
    keeps its address off the landing page usually keeps it."""
    base = urlsplit(base_url)
    base_host = base.netloc.lower().removeprefix("www.")
    scored: dict[str, int] = {}
    for match in _ANCHOR_RE.finditer(html):
        absolute = urljoin(base_url, match.group(1)).split("#")[0]
        parts = urlsplit(absolute)
        if parts.scheme not in ("http", "https"):
            continue
        if parts.netloc.lower().removeprefix("www.") != base_host:
            continue
        if parts.path.rstrip("/") == base.path.rstrip("/"):
            continue
        if _SKIP_EXTENSIONS_RE.search(parts.path):
            continue
        anchor_text = re.sub(r"<[^>]+>", " ", match.group(2)).lower()
        tokens = set(re.findall(r"[a-z]+", f"{parts.path.lower()} {anchor_text}"))
        if tokens & _CONTACT_STRONG:
            score = 2
        elif tokens & _CONTACT_WEAK:
            score = 1
        else:
            continue
        scored[absolute] = max(scored.get(absolute, 0), score)
    return sorted(scored, key=lambda link: (-scored[link], len(link)))[:limit]


def harvest(url: str) -> ScrapeResult:
    html = fetch_html(url)
    text = extract_text(html, url)
    title, description = extract_metadata(html, url)
    return ScrapeResult(
        text=text,
        html=html,
        html_bytes=len(html.encode("utf-8")),
        thin=len(text) < THIN_EXTRACTION_CHARS,
        title=title,
        meta_description=description,
    )


def harvest_with_playwright(url: str) -> ScrapeResult:
    """Explicit user-triggered fallback for JS-rendered sites. Playwright is
    only ever invoked from here, never from `harvest()`."""
    from playwright.sync_api import sync_playwright  # imported lazily — heavy, rarely used

    if not _robots_allowed(url):
        raise RobotsDisallowed(f"robots.txt disallows fetching {url}")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            # "load" not "networkidle": many venue sites carry live chat widgets
            # or analytics beacons that never let the network fall idle, so
            # networkidle reliably times out even once the page is fully
            # rendered. "load" fires on the load event; a short settle gives
            # late client-rendered content (pricing tables) time to paint.
            page.goto(url, timeout=TIMEOUT_SECONDS * 1000, wait_until="load")
            page.wait_for_timeout(1500)
            html = page.content()
        finally:
            browser.close()
    text = extract_text(html, url)
    title, description = extract_metadata(html, url)
    return ScrapeResult(
        text=text,
        html=html,
        html_bytes=len(html.encode("utf-8")),
        thin=len(text) < THIN_EXTRACTION_CHARS,
        title=title,
        meta_description=description,
    )
