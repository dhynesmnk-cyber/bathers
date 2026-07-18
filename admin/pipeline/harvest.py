"""Scrape a venue URL to plain text (TRD.md §2): httpx + trafilatura, robots.txt
respected, 20s timeout, one job at a time (enforced by the caller — this
module has no concurrency of its own). Playwright is an explicit
user-triggered fallback (UX.md §1.5 "Retry with Playwright"), never automatic.
"""

from __future__ import annotations

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


def harvest(url: str) -> ScrapeResult:
    html = fetch_html(url)
    text = extract_text(html, url)
    return ScrapeResult(
        text=text, html=html, html_bytes=len(html.encode("utf-8")), thin=len(text) < THIN_EXTRACTION_CHARS
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
    return ScrapeResult(
        text=text, html=html, html_bytes=len(html.encode("utf-8")), thin=len(text) < THIN_EXTRACTION_CHARS
    )
