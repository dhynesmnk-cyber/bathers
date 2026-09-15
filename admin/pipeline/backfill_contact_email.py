"""One-shot contact-address backfill for published venues (Gate 13, 2026-09-10).

Gate 13's outreach flow needs somewhere to write, and `contact_email` was null
on all 39 published venues: the field has existed since the 2026-08-19 schema
migration, but nothing in the pipeline ever collected it. `PROMPTS/harvester.md`
now asks for it, which fixes every venue harvested from *here on* — and Gate
13's first batch is entirely venues harvested before today, so on its own that
change delivers nothing to the gate.

A full re-harvest would collect the addresses, but it also regenerates the
prose and restages the venue, so 23 drafts would need re-reviewing to obtain 23
email addresses. This is the same targeted shape as `backfill_geocode.py`
instead: read the page, take the address, write that one field back through the
staging render path. The prose is untouched.

**No model is asked to produce an address.** `harvest.find_contact_emails()`
scans the fetched HTML for literal addresses and ranks them; this module picks
the top-ranked one and runs it through `orchestrator._resolve_contact_email()`,
the same guard the live harvest path uses, so the two cannot diverge. An
address that was never on the page cannot come out of a literal scan — which
for a field used to email real businesses is worth more than the flexibility of
free-form extraction. Every candidate found is printed, not just the chosen
one, so a wrong pick is visible rather than buried.

Writing to `_published` is deliberate and matches `backfill_geocode.py`:
CLAUDE.md rule 5 forbids editing that directory *by hand*, and this goes
through `render_mdx()` so field order and dates are preserved exactly.

Usage:
    python -m admin.pipeline.backfill_contact_email [--dry-run] [--slugs a,b,c]
        [--overwrite] [--playwright] [--self-test]

`--overwrite` re-reads venues that already carry an address; without it they
are skipped, so the run is safe to repeat. Do not run while an admin-UI harvest
job is active — this CLI bypasses the app's single-job harvest lock.
"""

from __future__ import annotations

import argparse
import sys
import time

from admin.config import PUBLISHED_DIR
from admin.pipeline import data_store, harvest, orchestrator
from admin.pipeline.staging import render_mdx, split_frontmatter

# One request a second, and at most this many pages per venue: the landing page
# plus a couple of contact pages. Matches the geocoder's politeness posture —
# these are small businesses' own servers.
REQUEST_DELAY_SECONDS = 1.0
MAX_CONTACT_PAGES = 2


def _fetch(url: str, use_playwright: bool) -> str:
    """HTML for `url`, via httpx or — only when explicitly asked — Playwright.

    Playwright is never reached automatically here, the same rule
    `harvest.harvest()` follows (TRD.md §2, UX.md §1.5): it is a fallback a
    person chooses after seeing httpx fail, not a silent retry. Note it sends
    the same User-Agent, so it does not defeat a UA block — what it buys is a
    real browser for a site that renders its contact details in JavaScript or
    puts a JS challenge in front of them.
    """
    if use_playwright:
        return harvest.harvest_with_playwright(url).html
    return harvest.fetch_html(url)


def _candidates_for(url: str, use_playwright: bool = False) -> tuple[list[str], list[str]]:
    """(addresses, notes) — every literal address published on the venue's site.

    Tries the given page first, then its contact/enquiries pages if that page
    published nothing.
    """
    notes: list[str] = []
    try:
        html = _fetch(url, use_playwright)
    except harvest.RobotsDisallowed as exc:
        return [], [f"robots.txt disallows the fetch — {exc}"]
    except harvest.ScrapeError as exc:
        return [], [f"could not fetch {url} — {exc}"]
    except Exception as exc:  # noqa: BLE001 — Playwright raises its own error types
        return [], [f"could not fetch {url} — {type(exc).__name__}: {exc}"]

    found = harvest.find_contact_emails(html, url)
    if found:
        return found, notes

    for link in harvest.find_contact_links(html, url, limit=MAX_CONTACT_PAGES):
        time.sleep(REQUEST_DELAY_SECONDS)
        try:
            page = _fetch(link, use_playwright)
        except Exception as exc:  # noqa: BLE001 — as above
            notes.append(f"could not fetch {link} — {exc}")
            continue
        found = harvest.find_contact_emails(page, link)
        if found:
            notes.append(f"found on {link}")
            return found, notes
    return [], notes


def backfill(
    dry_run: bool = False,
    slugs: list[str] | None = None,
    overwrite: bool = False,
    use_playwright: bool = False,
) -> tuple[int, int]:
    """(updated, missed). Prints one line per venue either way."""
    wanted = set(slugs or [])
    if wanted:
        # A typo'd slug would otherwise just quietly do nothing, which on a
        # host with real network access looks identical to "already done".
        known = {path.stem for path in PUBLISHED_DIR.glob("*.mdx")}
        for slug in sorted(wanted - known):
            print(f"  ??   {slug}: no published venue with that slug")
    updated = 0
    missed = 0
    first = True
    unreachable: list[str] = []

    for path in sorted(PUBLISHED_DIR.glob("*.mdx")):
        slug = path.stem
        if wanted and slug not in wanted:
            continue
        data, body = split_frontmatter(path.read_text(encoding="utf-8"), slug)
        if data.get("contact_email") and not overwrite:
            continue
        url = data.get("website") or data.get("source_url")
        if not url:
            missed += 1
            print(f"  MISS {slug}: no website or source_url to read")
            continue

        if not first:
            time.sleep(REQUEST_DELAY_SECONDS)
        first = False

        found, notes = _candidates_for(url, use_playwright)
        for note in notes:
            print(f"       {slug}: {note}")
        if not found:
            missed += 1
            # "could not read the page" and "the page has no address" are
            # different outcomes: the first is worth retrying, the second is
            # not. Only the first goes in the retry list.
            if any(note.startswith("could not fetch") for note in notes):
                unreachable.append(slug)
                print(f"  MISS {slug}: could not read {url}")
            else:
                print(f"  MISS {slug}: no address published on {url}")
            continue

        # The same guard the harvest path applies, so the two cannot diverge.
        email, guard_note = orchestrator._resolve_contact_email({"contact_email": found[0]}, url)
        if email is None:
            missed += 1
            print(f"  MISS {slug}: {guard_note}")
            continue
        rejected = ", ".join(found[1:])
        print(
            f"  OK   {slug}: {email}"
            + (f"  (also published: {rejected})" if rejected else "")
        )
        if guard_note:
            print(f"       {slug}: {guard_note}")
        updated += 1
        if not dry_run:
            data["contact_email"] = email
            path.write_text(render_mdx(data, body), encoding="utf-8")

    if unreachable:
        print(
            "\ncould not read " + str(len(unreachable)) + " venue(s). Retry just those with a real\n"
            "browser (same User-Agent, so this helps with JS-rendered contact pages,\n"
            "not with a User-Agent block):\n"
            "  python3 -m admin.pipeline.backfill_contact_email --playwright --slugs "
            + ",".join(unreachable)
        )

    if updated and not dry_run:
        # `contact_email` is frontmatter-only — it is not in
        # data_store.VENUE_SCALAR_COLUMNS, so nothing derived should move. The
        # rebuild runs anyway to keep check 3 honest: if it does move, that is
        # a surface drift worth seeing rather than a surprise in CI.
        count = data_store.rebuild()
        print(f"rebuilt derived data — {count} venue(s)")
    return updated, missed


def _self_test() -> int:
    """Proves the scan on hand-built HTML: no network, and every rejection
    asserted alongside a clean pass. The rejections are the point — this
    module writes an address that will later be emailed, so "found something"
    is not the same as "found the right thing"."""
    site = "https://www.example-bathhouse.com.au/visit"
    results: list[tuple[str, bool]] = []

    def scan(html: str, url: str | None = site) -> list[str]:
        return harvest.find_contact_emails(html, url)

    found = scan(
        '<a href="mailto:bookings@example-bathhouse.com.au?subject=Booking">Book</a>'
        "<p>Or write to hello@example-bathhouse.com.au</p>"
    )
    results.append(("a linked address outranks one in body text", found[0] == "bookings@example-bathhouse.com.au"))
    results.append(("both published addresses are reported", len(found) == 2))

    found = scan("<p>press@some-agency.com and hello@example-bathhouse.com.au</p>")
    results.append(("the venue's own domain outranks an off-domain address", found[0] == "hello@example-bathhouse.com.au"))

    found = scan("<p>jo.smith@example-bathhouse.com.au and info@example-bathhouse.com.au</p>")
    results.append(("a general address outranks a named individual", found[0] == "info@example-bathhouse.com.au"))

    results.append(("an administrative address is not a candidate", scan('<a href="mailto:noreply@example-bathhouse.com.au">x</a>') == []))
    results.append(("a retina asset name is not mistaken for an address", scan('<img src="/logo@2x.png">') == []))
    results.append(("a CSS at-rule is not mistaken for an address", scan("<style>@media screen and (min-width:40em){}</style>") == []))
    results.append(("a placeholder domain is not a candidate", scan("<p>you@example.com</p>") == []))
    results.append(("a site-builder address is not a candidate", scan("<p>abc@sentry.wixpress.com</p>") == []))
    results.append(("a page with no address yields nothing", scan("<p>Call us on 03 9000 0000.</p>") == []))
    results.append((
        "with no base URL, addresses are still found and ranked",
        scan("<p>info@anywhere.com</p>", None) == ["info@anywhere.com"],
    ))
    results.append((
        "a duplicate address is reported once",
        scan('<a href="mailto:info@example-bathhouse.com.au">a</a><p>info@example-bathhouse.com.au</p>')
        == ["info@example-bathhouse.com.au"],
    ))

    links = harvest.find_contact_links(
        '<a href="/contact-us/">Contact</a><a href="/terms/">Terms</a>'
        '<a href="https://facebook.com/x/contact">Social</a>',
        site,
    )
    results.append(("a same-host contact page is found", links == ["https://www.example-bathhouse.com.au/contact-us/"]))

    # The chosen address must clear the same guard the live harvest applies.
    email, _ = orchestrator._resolve_contact_email(
        {"contact_email": scan('<a href="mailto:info@example-bathhouse.com.au">x</a>')[0]}, site
    )
    results.append(("the top candidate clears the harvest-path guard", email == "info@example-bathhouse.com.au"))

    for label, ok in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    return 0 if all(ok for _, ok in results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    parser.add_argument("--slugs", help="comma-separated slugs to limit the run to")
    parser.add_argument("--overwrite", action="store_true", help="re-read venues that already have an address")
    parser.add_argument(
        "--playwright",
        action="store_true",
        help="fetch with a real browser instead of httpx — for sites that render their "
             "contact details in JavaScript. Explicit by design (TRD.md §2); pair it with "
             "--slugs to retry only what the first pass could not read.",
    )
    parser.add_argument("--self-test", action="store_true", help="offline assertions, no network")
    args = parser.parse_args()

    if args.self_test:
        raise SystemExit(_self_test())

    slugs = [s.strip() for s in args.slugs.split(",") if s.strip()] if args.slugs else None
    updated, missed = backfill(
        dry_run=args.dry_run, slugs=slugs, overwrite=args.overwrite, use_playwright=args.playwright
    )
    print(f"{updated} address(es) found, {missed} venue(s) without one" + (" (dry run — nothing written)" if args.dry_run else ""))
    if not updated and not missed and not slugs:
        print("every venue already carries a contact address — pass --overwrite to re-read them")


if __name__ == "__main__":
    main()
