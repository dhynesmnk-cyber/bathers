"""Field-level frontmatter validator mirroring SCHEMA.md §2 / the zod schema
in site/src/content/config.ts exactly. Field names, bounds and messages are
kept in lockstep with that file per SCHEMA.md's "one contract" rule.

Unlike pipeline.data_store.parse_frontmatter (which only checks required
keys are present), this validates types, enums, bounds and string limits,
returning every failing field rather than raising on the first one — the
review pane needs to highlight all of them at once (UX.md §1.5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from admin.config import AMENITY_KEYS, FACILITY_KEYS, STATES

AU_LATITUDE_BOUNDS = (-44.0, -9.0)
AU_LONGITUDE_BOUNDS = (112.0, 154.0)
SUMMARY_MAX_CHARS = 160
MIN_PROSE_WORDS = 300
FAQ_MAX_ITEMS = 8

_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

REQUIRED_STRING_FIELDS = ("name", "suburb", "address")
URL_FIELDS = ("website", "source_url")


@dataclass
class FieldError:
    field: str
    message: str


def _is_url(value: Any) -> bool:
    return isinstance(value, str) and bool(_URL_RE.match(value))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_frontmatter(data: dict[str, Any]) -> list[FieldError]:
    """Validate a parsed frontmatter dict against SCHEMA.md §2. Returns every
    failing field (empty list = valid). Does not raise."""
    errors: list[FieldError] = []

    for field in REQUIRED_STRING_FIELDS:
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(FieldError(field, f"'{field}' is required"))

    state = data.get("state")
    if state not in STATES:
        errors.append(FieldError("state", f"state must be one of {', '.join(STATES)}"))

    latitude = data.get("latitude")
    if not _is_number(latitude):
        errors.append(FieldError("latitude", "latitude is required and must be a number"))
    elif not (AU_LATITUDE_BOUNDS[0] <= latitude <= AU_LATITUDE_BOUNDS[1]):
        errors.append(FieldError("latitude", "latitude out of range for AU"))

    longitude = data.get("longitude")
    if not _is_number(longitude):
        errors.append(FieldError("longitude", "longitude is required and must be a number"))
    elif not (AU_LONGITUDE_BOUNDS[0] <= longitude <= AU_LONGITUDE_BOUNDS[1]):
        errors.append(FieldError("longitude", "longitude out of range for AU"))

    for field in URL_FIELDS:
        value = data.get(field)
        if not _is_url(value):
            errors.append(FieldError(field, f"'{field}' must be a valid http(s) URL"))

    amenities = data.get("amenities")
    if not isinstance(amenities, dict):
        errors.append(FieldError("amenities", "amenities object is required"))
    else:
        missing = [key for key in AMENITY_KEYS if key not in amenities]
        extra = [key for key in amenities if key not in AMENITY_KEYS]
        non_bool = [
            key for key in AMENITY_KEYS if key in amenities and not isinstance(amenities[key], bool)
        ]
        if missing:
            errors.append(FieldError("amenities", f"amenities missing keys: {', '.join(missing)}"))
        if extra:
            errors.append(FieldError("amenities", f"amenities has unexpected keys: {', '.join(extra)}"))
        if non_bool:
            errors.append(FieldError("amenities", f"amenities keys must be boolean: {', '.join(non_bool)}"))

    facilities = data.get("facilities")
    if facilities is not None:
        if not isinstance(facilities, dict):
            errors.append(FieldError("facilities", "facilities must be an object of booleans"))
        else:
            extra = [key for key in facilities if key not in FACILITY_KEYS]
            non_bool = [
                key for key in FACILITY_KEYS if key in facilities and not isinstance(facilities[key], bool)
            ]
            if extra:
                errors.append(FieldError("facilities", f"facilities has unexpected keys: {', '.join(extra)}"))
            if non_bool:
                errors.append(FieldError("facilities", f"facilities keys must be boolean: {', '.join(non_bool)}"))

    for field in ("hours", "cost"):
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            errors.append(FieldError(field, f"'{field}' must be a string"))

    status = data.get("status", "unclaimed")
    if status not in ("unclaimed", "claimed"):
        errors.append(FieldError("status", "status must be 'unclaimed' or 'claimed'"))

    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        errors.append(FieldError("summary", "summary is required"))
    elif len(summary) > SUMMARY_MAX_CHARS:
        errors.append(FieldError("summary", f"summary exceeds {SUMMARY_MAX_CHARS} characters"))

    drafted = data.get("drafted")
    drafted_str = drafted.isoformat() if isinstance(drafted, date) else drafted
    if not isinstance(drafted_str, str) or not _DATE_RE.match(drafted_str):
        errors.append(FieldError("drafted", "drafted must be a date (YYYY-MM-DD)"))

    image = data.get("image")
    if image:
        if not _is_url(data.get("image_source")):
            errors.append(FieldError("image_source", "image_source is required when image is present"))
        if not isinstance(data.get("image_caption"), str) or not data.get("image_caption", "").strip():
            errors.append(FieldError("image_caption", "image_caption is required when image is present"))

    faq = data.get("faq")
    if faq is not None:
        if not isinstance(faq, list):
            errors.append(FieldError("faq", "faq must be a list of {question, answer} pairs"))
        elif len(faq) > FAQ_MAX_ITEMS:
            errors.append(FieldError("faq", f"faq exceeds {FAQ_MAX_ITEMS} pairs"))
        else:
            for i, item in enumerate(faq):
                if not isinstance(item, dict):
                    errors.append(FieldError("faq", f"faq[{i}] must be an object with question/answer"))
                    continue
                question = item.get("question")
                answer = item.get("answer")
                if not isinstance(question, str) or not question.strip():
                    errors.append(FieldError("faq", f"faq[{i}].question is required"))
                if not isinstance(answer, str) or not answer.strip():
                    errors.append(FieldError("faq", f"faq[{i}].answer is required"))

    known_fields = {
        "name", "state", "suburb", "address", "latitude", "longitude", "website",
        "amenities", "facilities", "hours", "cost", "status", "summary", "drafted", "source_url",
        "image", "image_source", "image_caption", "faq",
    }
    extra_fields = [key for key in data if key not in known_fields]
    if extra_fields:
        errors.append(FieldError("_root", f"unexpected field(s): {', '.join(extra_fields)}"))

    return errors


def count_prose_words(body: str) -> int:
    stripped = re.sub(r"</?Pull>", "", body)
    stripped = re.sub(r"<TippedPhoto[^>]*/?>", "", stripped)
    return len(stripped.split())


def staging_status(
    errors: list[FieldError],
    word_count: int,
    has_pending_images: bool = False,
    places_flagged: bool = False,
) -> str:
    if errors or word_count < MIN_PROSE_WORDS or places_flagged:
        return "FLAGGED"
    if has_pending_images:
        return "IMG PENDING"
    return "DRAFTED"
