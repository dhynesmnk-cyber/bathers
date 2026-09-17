"""Reader for the constants that live only in `site/src/config.ts`.

Most cross-cutting constants are mirrored into `admin/config.py` (rule 4), but a
few are genuinely TS-only because nothing on the Python side ever needed them:
`POOL_TYPES`, `POOL_NATIONAL_FILTERS`, `CROSS_CUTTING_FACILITY_FILTERS` and
`AMENITY_NOTATION`'s short codes. The validators do need them, and copying them
into Python would create exactly the drift those validators exist to catch — so
they are read out of the TS file itself, which is the one place they are written
down.

`validate_places` has parsed config.ts this way since Gate 16; this module is
that parser lifted out so the discoverability checks can share it rather than
grow a second one. A module whose job is catching duplication should not be
duplicated to build it.

Deliberately a regex reader, not a TS parser: every constant here is a
hand-written literal in a file this repo controls, and a dependency for reading
four object literals would be its own kind of mistake (rule 2). If a literal is
ever reformatted past what these patterns match, the readers return less than
they should — so each caller treats an empty result as a failure worth naming
rather than a quiet pass.
"""

from __future__ import annotations

import re

from admin.config import SITE_DIR

CONFIG_TS = SITE_DIR / "src" / "config.ts"


def _text() -> str:
    return CONFIG_TS.read_text(encoding="utf-8")


def _block(const: str, text: str | None = None) -> str:
    """The body of `export const <const> = …`, up to its terminator.

    Returns "" when the constant is absent, which callers report rather than
    skip: a constant that has been renamed is a reason to fail, not to pass.
    """
    text = _text() if text is None else text
    parts = text.split(f"export const {const}", 1)
    if len(parts) < 2:
        return ""
    body = parts[1]
    for terminator in ("] as const;", "};", "] ="):
        if terminator in body:
            body = body.split(terminator, 1)[0]
            break
    return body


def slugs(const: str) -> set[str]:
    """Every `slug: "…"` in the named constant."""
    return set(re.findall(r'slug:\s*"([a-z0-9-]+)"', _block(const)))


def entries(const: str) -> list[dict[str, str]]:
    """Every `{ slug, key, label }` row in the named constant, in file order."""
    out: list[dict[str, str]] = []
    for slug, key, label in re.findall(
        r'\{\s*slug:\s*"([a-z0-9-]+)",\s*key:\s*"([a-z0-9_]+)"(?:\s*as\s*const)?,\s*label:\s*"([^"]+)"',
        _block(const),
    ):
        out.append({"slug": slug, "key": key, "label": label})
    return out


def amenity_notation_shorts() -> list[str]:
    """The cryptic amenity codes — Mg, IR, SA, CP, LED.

    Read rather than hardcoded because they are precisely what /validate's
    abbreviation check must never find rendered, and a stale copy here would
    mean checking for codes the site no longer uses while missing the ones it
    does.
    """
    return re.findall(r'short:\s*"([A-Za-z]+)"', _block("AMENITY_NOTATION"))
