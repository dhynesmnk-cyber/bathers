"""Renders a staged MDX body to HTML for the review pane's preview iframe.

Not a general MDX/JSX renderer — the Architect/Gatekeeper prompts (PROMPTS/)
only ever produce plain paragraphs and <Pull> pull-quotes in the body (see
architect.md "Structure"), so a full MDX compiler is out of scope for a
review-only preview. <TippedPhoto> is a placeholder here since image
publishing is a separate action (UX.md §4, Gate 4).

Also holds the frontmatter-side rendering helpers for preview.html: amenity/
facility chip labels and icons (mirroring site/src/icons/paths.ts and
site/src/config.ts's AMENITY_NOTATION — an independent Python-side copy,
same "two mirrors, no shared module system" posture as admin/config.py) and
the temperature/session-gender display-line logic (mirroring
site/src/config.ts's saunaTemperatureLine/coldPlungeTemperatureLine).
"""

from __future__ import annotations

import html
import re
from typing import Any

_PULL_RE = re.compile(r"^<Pull>(.*)</Pull>$", re.DOTALL)
_TIPPED_PHOTO_RE = re.compile(r"^<TippedPhoto\b")

# 2026-07-27 addition — full labels for the five amenity keys, in the exact
# display casing used by site's AMENITY_NOTATION[key].full (distinct from
# admin.config.AMENITY_FULL_NAMES, which is lowercase for use in prose).
AMENITY_LABELS = {
    "magnesium_pool": "Magnesium pool",
    "infrared_sauna": "Infrared sauna",
    "traditional_sauna": "Traditional sauna",
    "cold_plunge": "Cold plunge",
    "led_therapy": "LED light therapy",
}

# Hand-authored inline SVG path fragments, copied from
# site/src/icons/paths.ts / admin/templates/index.html's toggle-chip icons —
# same stroke-only 24x24 visual language site-wide (DESIGN.md §6). Kept as a
# third independent copy for the same reason admin.js's FACILITY_KEYS const
# is a second one: Python/Jinja can't import the TS module.
ICON_PATHS = {
    "magnesium_pool": '<path d="M2 8c1.4 1.6 2.8 1.6 4.2 0s2.8-1.6 4.2 0 2.8 1.6 4.2 0 2.8-1.6 4.2 0"/><path d="M2 13c1.4 1.6 2.8 1.6 4.2 0s2.8-1.6 4.2 0 2.8 1.6 4.2 0 2.8-1.6 4.2 0"/><path d="M2 18c1.4 1.6 2.8 1.6 4.2 0s2.8-1.6 4.2 0 2.8 1.6 4.2 0 2.8-1.6 4.2 0"/>',
    "infrared_sauna": '<rect x="5" y="11" width="14" height="7" rx="1"/><path d="M9 11V5M12 11V3M15 11V5"/>',
    "traditional_sauna": '<path d="M12 3c2.2 3 3 5 3 7.5a3 3 0 1 1-6 0C9 8 9.8 6 12 3z"/><path d="M9 14.5a3 3 0 0 0 6 0"/>',
    "cold_plunge": '<path d="M12 2v20"/><path d="M4.5 6.5l15 11"/><path d="M4.5 17.5l15-11"/>',
    "led_therapy": '<path d="M12 3.5a5.5 5.5 0 0 0-3.2 10c.5.4.9 1 .9 1.7h4.6c0-.7.4-1.3.9-1.7A5.5 5.5 0 0 0 12 3.5z"/><path d="M9.5 18h5M10.2 20.5h3.6"/>',
    "hours": '<circle cx="12" cy="12" r="9"/><path d="M12 7.5V12l3.2 2"/>',
    "cost": '<path d="M3 11.2V5a1 1 0 0 1 1-1h6.2a1 1 0 0 1 .7.3l8.4 8.4a1 1 0 0 1 0 1.4l-6.3 6.3a1 1 0 0 1-1.4 0L3.3 11.9a1 1 0 0 1-.3-.7z"/><circle cx="7.8" cy="7.8" r="1.3"/>',
    "parking": '<rect x="3.5" y="3.5" width="17" height="17" rx="1.5"/><path d="M9 17V7h3.3a2.8 2.8 0 0 1 0 5.6H9"/>',
    "towels_provided": '<rect x="4.5" y="5" width="15" height="3.6" rx="1"/><rect x="4.5" y="10.2" width="15" height="3.6" rx="1"/><rect x="4.5" y="15.4" width="9" height="3.6" rx="1"/>',
    "changerooms": '<path d="M12 4.2a2 2 0 1 1 1.8 2c-.5.3-.8.7-.8 1.3v.3"/><path d="M12 7.8L3.2 13.6c-.8.5-.4 1.7.5 1.7h16.6c.9 0 1.3-1.2.5-1.7L12 7.8z"/>',
    "bookings_required": '<rect x="3.5" y="4.8" width="17" height="15.5" rx="1.5"/><path d="M3.5 9.3h17M8 2.8v4M16 2.8v4"/><path d="M8.3 14.3l2 2 4.4-4.4"/>',
    "wheelchair_access": '<circle cx="11" cy="4.3" r="1.6"/><path d="M11 7.7v3.3l4 1.6"/><path d="M10.7 11H7a4 4 0 1 0 2.5 7.1L13 22"/>',
    "outdoor_pool": '<circle cx="12" cy="6" r="2.3"/><path d="M12 2v1.2M8.4 3.6l.8.8M15.6 3.6l-.8.8M6.5 6.3h1.2M16.3 6.3h1.2"/><path d="M3 16c1.4 1.6 2.8 1.6 4.2 0s2.8-1.6 4.2 0 2.8 1.6 4.2 0 2.8-1.6 4.2 0"/><path d="M3 20c1.4 1.6 2.8 1.6 4.2 0s2.8-1.6 4.2 0 2.8 1.6 4.2 0 2.8-1.6 4.2 0"/>',
    "indoor_pool": '<path d="M4 9l8-5 8 5"/><path d="M5 9v3M19 9v3"/><path d="M3 16c1.4 1.6 2.8 1.6 4.2 0s2.8-1.6 4.2 0 2.8 1.6 4.2 0 2.8-1.6 4.2 0"/><path d="M3 20c1.4 1.6 2.8 1.6 4.2 0s2.8-1.6 4.2 0 2.8 1.6 4.2 0 2.8-1.6 4.2 0"/>',
    "natural_spring": '<path d="M4 20c2-6 4-9 8-9s6 3 8 9"/><path d="M8 20c1-3 2-4.5 4-4.5s3 1.5 4 4.5"/><path d="M12 4c1.6 2 2.2 3.4 2.2 4.6a2.2 2.2 0 1 1-4.4 0C9.8 7.4 10.4 6 12 4z"/>',
    "pregnancy_safe": '<circle cx="9.5" cy="5" r="2.2"/><path d="M9.5 7.5c-2.6 0-4.3 1.8-4.3 4.4v2.6"/><path d="M9.5 11a4.6 4.6 0 0 1 4.6 4.6V21"/><path d="M5.2 21v-3.4"/>',
    "step_free_entry": '<path d="M2 20h20"/><path d="M5 20L14 8h5"/><path d="M14 8v4.5"/>',
    "hoist_available": '<path d="M12 4v8"/><path d="M9 12a3 3 0 0 0 6 0"/><circle cx="12" cy="17" r="2.2"/>',
    "accessible_changerooms": '<rect x="6" y="3" width="10" height="18" rx="1.2"/><circle cx="16.5" cy="16.5" r="3"/><path d="M16.5 13.5v3l2.3 1.3"/>',
}


def _format_temp_range(min_c: Any, max_c: Any) -> str | None:
    if min_c is None or max_c is None:
        return None
    return f"{min_c}°C" if min_c == max_c else f"{min_c}–{max_c}°C"


def sauna_temperature_line(temperatures: dict[str, Any]) -> str | None:
    return temperatures.get("sauna_display") or _format_temp_range(
        temperatures.get("sauna_min_c"), temperatures.get("sauna_max_c")
    )


def cold_plunge_temperature_line(temperatures: dict[str, Any]) -> str | None:
    return temperatures.get("cold_plunge_display") or _format_temp_range(
        temperatures.get("cold_plunge_min_c"), temperatures.get("cold_plunge_max_c")
    )


def temperature_line(temperatures: dict[str, Any] | None) -> str | None:
    if not temperatures:
        return None
    parts = []
    sauna = sauna_temperature_line(temperatures)
    cold_plunge = cold_plunge_temperature_line(temperatures)
    if sauna:
        parts.append(f"Sauna {sauna}")
    if cold_plunge:
        parts.append(f"Cold plunge {cold_plunge}")
    return ". ".join(parts) or None


def session_gender_line(data: dict[str, Any]) -> str | None:
    from admin.config import SESSION_GENDER_LABELS

    parts = []
    gender = data.get("session_gender")
    if gender:
        parts.append(SESSION_GENDER_LABELS.get(gender, gender))
    note = data.get("session_gender_note")
    if note:
        parts.append(note)
    return ". ".join(parts) or None


def render_body_html(body: str) -> str:
    blocks = re.split(r"\n\s*\n", body.strip())
    parts: list[str] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        pull_match = _PULL_RE.match(block)
        if pull_match:
            inner = html.escape(pull_match.group(1).strip())
            parts.append(
                '<p class="font-display text-2xl italic leading-snug text-[var(--ink)] my-8 max-w-[65ch]" '
                'style="font-weight: 400;">' + inner + "</p>"
            )
            continue
        if _TIPPED_PHOTO_RE.match(block):
            parts.append(
                '<p class="mono text-[var(--ink-faded)]">'
                "[tipped photo — image publishing is a separate reviewer action, not shown here]</p>"
            )
            continue
        parts.append("<p>" + html.escape(block) + "</p>")
    return "\n".join(parts)
