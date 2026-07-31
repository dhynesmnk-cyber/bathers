"""Gate 7 (2026-07-31) build-time fact-plausibility validators — they FAIL,
never warn, and only on *implausible* data, never on mere absence (a thin
venue that simply omits a field must still pass, or republishing any of the
existing venues mid-transition would break the build).

Run as `python -m admin.pipeline.validate_facts` (exit 1 on any failure) and
folded into /validate. Each check is a function returning a list of failure
strings so /validate can demonstrate a deliberately corrupted fixture failing
exactly one check (mirrors Gate 1's corrupt-field test).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from admin.config import (
    AMENITY_KEYS,
    CAPITAL_CITIES,
    FACILITY_KEYS,
    PUBLISHED_DIR,
    ROOT,
    STATE_BBOX,
)
from admin.pipeline.data_store import parse_frontmatter
from admin.pipeline.verification import populated_verifiable_fields

Venue = tuple[str, dict[str, Any]]

CAPITAL_NAMES = {c["name"] for c in CAPITAL_CITIES.values()}
# Plausibility windows — deliberately wide (catch a wrong-units or wrong-field
# error, not a legitimate outlier). Distinct from the zod data-entry bounds.
SAUNA_PLAUSIBLE = (30, 130)
PLUNGE_PLAUSIBLE = (-2, 20)
DRIVE_MINUTES_MAX = 3000  # ~50 h — no AU venue is further from a capital


def _cost_amounts(cost: str | None) -> list[float]:
    return [float(m.replace(",", "")) for m in re.findall(r"\$\s?(\d[\d,]*(?:\.\d{1,2})?)", cost or "")]


def check_verification_completeness(venues: list[Venue]) -> list[str]:
    out = []
    for slug, fm in venues:
        block = fm.get("verification") or {}
        for field in populated_verifiable_fields(fm):
            record = block.get(field)
            if not isinstance(record, dict) or not record.get("source") or not record.get("tier"):
                out.append(f"{slug}: '{field}' is populated but has no verification source+tier")
    return out


def check_price_cross_validation(venues: list[Venue]) -> list[str]:
    out = []
    for slug, fm in venues:
        price = fm.get("price") or {}
        amounts = _cost_amounts(fm.get("cost"))
        for key in ("adult_drop_in_aud", "standard_session_aud"):
            value = price.get(key)
            if value is None:
                continue
            if not amounts:
                out.append(f"{slug}: price.{key}={value} but the cost string states no dollar amount to corroborate it")
            elif not (min(amounts) <= value <= max(amounts)):
                out.append(f"{slug}: price.{key}={value} outside the cost string's range {min(amounts)}–{max(amounts)}")
    return out


def check_drive_time_sanity(venues: list[Venue]) -> list[str]:
    out = []
    for slug, fm in venues:
        dt = fm.get("drive_time")
        if not dt:
            continue
        if dt.get("from") not in CAPITAL_NAMES:
            out.append(f"{slug}: drive_time.from '{dt.get('from')}' is not a known capital")
        minutes, km = dt.get("minutes"), dt.get("km")
        if not isinstance(minutes, int) or not (0 <= minutes <= DRIVE_MINUTES_MAX):
            out.append(f"{slug}: drive_time.minutes={minutes} implausible")
        if not isinstance(km, (int, float)) or km < 0:
            out.append(f"{slug}: drive_time.km={km} implausible")
    return out


def check_coords_state_bbox(venues: list[Venue]) -> list[str]:
    out = []
    for slug, fm in venues:
        lat, lng = fm.get("latitude"), fm.get("longitude")
        if lat is None or lng is None:
            continue  # absence is fine — no map marker, not a failure
        box = STATE_BBOX.get(fm["state"])
        if box and not (box[0] <= lat <= box[1] and box[2] <= lng <= box[3]):
            out.append(f"{slug}: coords {lat},{lng} fall outside the {fm['state']} bounding box")
    return out


def check_temperature_plausibility(venues: list[Venue]) -> list[str]:
    out = []
    for slug, fm in venues:
        t = fm.get("temperatures") or {}
        for lo_key, hi_key, window, label in (
            ("sauna_min_c", "sauna_max_c", SAUNA_PLAUSIBLE, "sauna"),
            ("cold_plunge_min_c", "cold_plunge_max_c", PLUNGE_PLAUSIBLE, "cold plunge"),
        ):
            for key in (lo_key, hi_key):
                v = t.get(key)
                if v is not None and not (window[0] <= v <= window[1]):
                    out.append(f"{slug}: temperatures.{key}={v}°C implausible for a {label} ({window[0]}–{window[1]})")
    return out


def check_amenity_temperature_consistency(venues: list[Venue]) -> list[str]:
    out = []
    for slug, fm in venues:
        t = fm.get("temperatures") or {}
        amen = fm.get("amenities") or {}
        if (t.get("cold_plunge_min_c") is not None or t.get("cold_plunge_max_c") is not None or t.get("cold_plunge_display")) \
                and not amen.get("cold_plunge"):
            out.append(f"{slug}: has a cold-plunge temperature but amenities.cold_plunge is false")
        if (t.get("sauna_min_c") is not None or t.get("sauna_max_c") is not None or t.get("sauna_display")) \
                and not (amen.get("traditional_sauna") or amen.get("infrared_sauna")):
            out.append(f"{slug}: has a sauna temperature but neither sauna amenity is set")
    return out


def _glossary_keys() -> set[str]:
    text = (ROOT / "site/src/data/glossary.ts").read_text(encoding="utf-8")
    block = text.split("export const GLOSSARY", 1)[-1]
    return set(re.findall(r"^\s{2}([a-z_]+):", block, re.MULTILINE))


def check_glossary_coverage(_venues: list[Venue]) -> list[str]:
    out = []
    keys = _glossary_keys()
    schema_keys = set(AMENITY_KEYS) | set(FACILITY_KEYS)
    for missing in sorted(schema_keys - keys):
        out.append(f"glossary.ts is missing an entry for '{missing}'")
    for orphan in sorted(keys - schema_keys):
        out.append(f"glossary.ts has an entry '{orphan}' with no matching amenity/facility key")
    return out


CHECKS = (
    check_verification_completeness,
    check_price_cross_validation,
    check_drive_time_sanity,
    check_coords_state_bbox,
    check_temperature_plausibility,
    check_amenity_temperature_consistency,
    check_glossary_coverage,
)


def run(published_dir: Path = PUBLISHED_DIR) -> list[str]:
    venues = [(p.stem, parse_frontmatter(p)) for p in sorted(published_dir.glob("*.mdx"))]
    failures: list[str] = []
    for check in CHECKS:
        failures.extend(check(venues))
    return failures


def main() -> None:
    failures = run()
    if failures:
        print(f"FACT VALIDATION FAIL — {len(failures)} issue(s):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("fact validation: pass")


if __name__ == "__main__":
    main()
