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
USER_AGENT = "BathersDirectoryBot/1.0 (local admin tool; contact via venue's own listing)"


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

_PRICING_STRONG = ("pricing", "prices", "price", "rates", "admission", "tariff", "fees", "cost")
_PRICING_WEAK = ("bathe", "bathing", "book", "experience", "package", "treatment", "menu")
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
        haystack = f"{parts.path.lower()} {anchor_text}"
        if any(keyword in haystack for keyword in _PRICING_STRONG):
            score = 2
        elif any(keyword in haystack for keyword in _PRICING_WEAK):
            score = 1
        else:
            continue
        scored[absolute] = max(scored.get(absolute, 0), score)
    ranked = sorted(scored, key=lambda link: (-scored[link], len(link)))
    return ranked[:limit]


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
            page.goto(url, timeout=TIMEOUT_SECONDS * 1000, wait_until="networkidle")
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
