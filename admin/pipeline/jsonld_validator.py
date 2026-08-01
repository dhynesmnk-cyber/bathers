"""Offline JSON-LD structural validator (Gate 11, 2026-07-31). A hand-rolled
checker for exactly the schema.org types this site emits — the project's
consistent "avoid a dependency, hand-roll a narrow version" posture (no public
Rich Results Test API exists to call). Folded into /validate; must pass on
100% of built page types.

It parses every <script type="application/ld+json"> block in the build,
confirms each is valid JSON with @context/@type, and checks the required
properties per type (and required shapes of nested items). Trade-off, noted
in TRD.md: a hand-rolled subset can miss a property a full validator would
catch — manual spot-checks with Google's Rich Results Test continue before
major pushes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from admin.config import ROOT

DIST = ROOT / "site" / "dist"
_LD = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)

# Required top-level properties per @type. Nested items are checked separately.
REQUIRED: dict[str, list[str]] = {
    "Organization": ["name", "url"],
    "WebSite": ["name", "url", "publisher"],
    "LocalBusiness": ["name", "address"],
    "FAQPage": ["mainEntity"],
    "BlogPosting": ["headline", "datePublished", "author", "publisher"],
    "ItemList": ["itemListElement"],
    "BreadcrumbList": ["itemListElement"],
    "DefinedTermSet": ["hasDefinedTerm"],
    "DefinedTerm": ["name", "inDefinedTermSet"],
}


def _check(obj: dict, page: str, errors: list[str]) -> None:
    t = obj.get("@type")
    if "@context" not in obj:
        errors.append(f"{page}: JSON-LD block missing @context (@type={t})")
    if not t:
        errors.append(f"{page}: JSON-LD block missing @type")
        return
    if t not in REQUIRED:
        errors.append(f"{page}: unexpected @type '{t}' (not in the emitted-type allowlist)")
        return
    for prop in REQUIRED[t]:
        if prop not in obj or obj[prop] in (None, "", [], {}):
            errors.append(f"{page}: {t} missing required '{prop}'")

    # nested-shape checks
    if t == "LocalBusiness":
        addr = obj.get("address")
        if isinstance(addr, dict) and addr.get("@type") != "PostalAddress":
            errors.append(f"{page}: LocalBusiness.address is not a PostalAddress")
        for feat in obj.get("amenityFeature", []) or []:
            if feat.get("@type") != "LocationFeatureSpecification" or not feat.get("name"):
                errors.append(f"{page}: amenityFeature item malformed")
    if t == "FAQPage":
        for q in obj.get("mainEntity", []) or []:
            if q.get("@type") != "Question" or not q.get("name") or not q.get("acceptedAnswer"):
                errors.append(f"{page}: FAQPage Question malformed")
    if t in ("ItemList", "BreadcrumbList"):
        for it in obj.get("itemListElement", []) or []:
            if it.get("@type") != "ListItem" or "position" not in it:
                errors.append(f"{page}: {t} ListItem missing @type/position")
            needs = "item" if t == "BreadcrumbList" else "url"
            if not it.get(needs) or not it.get("name"):
                errors.append(f"{page}: {t} ListItem missing {needs}/name")
    if t == "DefinedTermSet":
        for dt in obj.get("hasDefinedTerm", []) or []:
            if dt.get("@type") != "DefinedTerm" or not dt.get("name"):
                errors.append(f"{page}: DefinedTermSet term malformed")
    # A BlogPosting image may be a bare URL string or, when it carries
    # provenance (Gate E4b: photo credit/licence or an AI flag), a structured
    # ImageObject — which must name its @type and a contentUrl.
    if t == "BlogPosting":
        img = obj.get("image")
        if isinstance(img, dict) and (img.get("@type") != "ImageObject" or not img.get("contentUrl")):
            errors.append(f"{page}: BlogPosting.image object is not a valid ImageObject (needs @type + contentUrl)")


def run(dist: Path = DIST) -> tuple[list[str], set[str]]:
    """Returns (errors, types_seen)."""
    errors: list[str] = []
    types_seen: set[str] = set()
    if not dist.exists():
        return [f"no build at {dist}"], types_seen
    for html in dist.rglob("*.html"):
        rel = str(html.relative_to(dist))
        for raw in _LD.findall(html.read_text(encoding="utf-8")):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                errors.append(f"{rel}: invalid JSON-LD — {exc}")
                continue
            for obj in data if isinstance(data, list) else [data]:
                if isinstance(obj, dict):
                    types_seen.add(obj.get("@type", "?"))
                    _check(obj, rel, errors)
    return errors, types_seen


def main() -> None:
    errors, seen = run()
    if errors:
        print(f"JSON-LD VALIDATION FAIL — {len(errors)} issue(s):")
        for e in errors[:60]:
            print(f"  - {e}")
        raise SystemExit(1)
    print(f"JSON-LD validation: pass — types seen: {', '.join(sorted(seen))}")


if __name__ == "__main__":
    main()
