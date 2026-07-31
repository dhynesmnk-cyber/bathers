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

from admin.config import (
    AMENITY_KEYS,
    CATEGORY_KEYS,
    CONFIDENCE_TIERS,
    DRESS_CODE_KEYS,
    FACILITY_KEYS,
    SESSION_GENDER_KEYS,
    STATES,
    VERIFIABLE_FIELDS,
)

AU_LATITUDE_BOUNDS = (-44.0, -9.0)
AU_LONGITUDE_BOUNDS = (112.0, 154.0)
SUMMARY_MAX_CHARS = 160
MIN_PROSE_WORDS = 300
FAQ_MAX_ITEMS = 8
SAUNA_TEMP_BOUNDS = (0, 150)
COLD_PLUNGE_TEMP_BOUNDS = (-5, 40)
TEMPERATURE_KEYS = (
    "sauna_min_c", "sauna_max_c", "sauna_display",
    "cold_plunge_min_c", "cold_plunge_max_c", "cold_plunge_display",
)

_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

REQUIRED_STRING_FIELDS = ("name", "suburb", "address")
URL_FIELDS = ("website", "source_url")

# The complete set of allowed frontmatter fields (SCHEMA.md §2/§2a). Exposed
# module-level so the six-surface schema diff (admin/pipeline/schema_surfaces)
# can compare it against the zod schema and the SCHEMA.md table — the concrete
# guard against a field drifting between the validation layers.
KNOWN_FIELDS = {
    "name", "state", "category", "suburb", "address", "latitude", "longitude", "website",
    "amenities", "facilities", "hours", "cost", "access", "status", "summary", "drafted", "verified", "source_url",
    "image", "image_source", "image_caption", "faq",
    "temperatures", "dress_code", "session_gender", "session_gender_note",
    "silence_policy", "phone_policy", "minimum_age",
    "price", "drive_time", "verification", "change_log",
}


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

    category = data.get("category")
    if category not in CATEGORY_KEYS:
        errors.append(FieldError("category", f"category must be one of {', '.join(CATEGORY_KEYS)}"))

    # 2026-07-22: no longer required — null means "geocoding found no match,
    # venue excluded from the map only" (SCHEMA.md §2). Still bounds-checked
    # when present, as defense-in-depth on the auto-geocoded value.
    latitude = data.get("latitude")
    if latitude is not None:
        if not _is_number(latitude):
            errors.append(FieldError("latitude", "latitude must be a number"))
        elif not (AU_LATITUDE_BOUNDS[0] <= latitude <= AU_LATITUDE_BOUNDS[1]):
            errors.append(FieldError("latitude", "latitude out of range for AU"))

    longitude = data.get("longitude")
    if longitude is not None:
        if not _is_number(longitude):
            errors.append(FieldError("longitude", "longitude must be a number"))
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

    for field in ("hours", "cost", "access"):
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            errors.append(FieldError(field, f"'{field}' must be a string"))

    temperatures = data.get("temperatures")
    if temperatures is not None:
        if not isinstance(temperatures, dict):
            errors.append(FieldError("temperatures", "temperatures must be an object"))
        else:
            extra = [key for key in temperatures if key not in TEMPERATURE_KEYS]
            if extra:
                errors.append(FieldError("temperatures", f"temperatures has unexpected keys: {', '.join(extra)}"))
            for min_key, max_key, bounds in (
                ("sauna_min_c", "sauna_max_c", SAUNA_TEMP_BOUNDS),
                ("cold_plunge_min_c", "cold_plunge_max_c", COLD_PLUNGE_TEMP_BOUNDS),
            ):
                min_val, max_val = temperatures.get(min_key), temperatures.get(max_key)
                for key, value in ((min_key, min_val), (max_key, max_val)):
                    if value is not None and (not _is_number(value) or not (bounds[0] <= value <= bounds[1])):
                        errors.append(FieldError("temperatures", f"temperatures.{key} must be a number between {bounds[0]} and {bounds[1]}"))
                if min_val is not None and max_val is not None and _is_number(min_val) and _is_number(max_val) and min_val > max_val:
                    errors.append(FieldError("temperatures", f"temperatures.{min_key} must not exceed {max_key}"))
            for key in ("sauna_display", "cold_plunge_display"):
                value = temperatures.get(key)
                if value is not None and not isinstance(value, str):
                    errors.append(FieldError("temperatures", f"temperatures.{key} must be a string"))

    dress_code = data.get("dress_code")
    if dress_code is not None and dress_code not in DRESS_CODE_KEYS:
        errors.append(FieldError("dress_code", f"dress_code must be one of {', '.join(DRESS_CODE_KEYS)}"))

    session_gender = data.get("session_gender")
    if session_gender is not None and session_gender not in SESSION_GENDER_KEYS:
        errors.append(FieldError("session_gender", f"session_gender must be one of {', '.join(SESSION_GENDER_KEYS)}"))

    for field in ("session_gender_note", "silence_policy", "phone_policy"):
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            errors.append(FieldError(field, f"'{field}' must be a string"))

    minimum_age = data.get("minimum_age")
    if minimum_age is not None and (not isinstance(minimum_age, int) or isinstance(minimum_age, bool) or minimum_age <= 0):
        errors.append(FieldError("minimum_age", "minimum_age must be a positive integer"))

    # Gate 7 (2026-07-31, SCHEMA.md §2a) — structured price, drive-time,
    # per-field verification. All optional; validated for shape/bounds when
    # present, never required (absence is normal on thin venues).
    price = data.get("price")
    if price is not None:
        if not isinstance(price, dict):
            errors.append(FieldError("price", "price must be an object"))
        else:
            extra = [k for k in price if k not in ("adult_drop_in_aud", "standard_session_aud")]
            if extra:
                errors.append(FieldError("price", f"price has unexpected keys: {', '.join(extra)}"))
            for key in ("adult_drop_in_aud", "standard_session_aud"):
                value = price.get(key)
                if value is not None and (not _is_number(value) or value < 0):
                    errors.append(FieldError("price", f"price.{key} must be a non-negative number"))

    drive_time = data.get("drive_time")
    if drive_time is not None:
        if not isinstance(drive_time, dict):
            errors.append(FieldError("drive_time", "drive_time must be an object"))
        else:
            if not isinstance(drive_time.get("from"), str) or not drive_time.get("from", "").strip():
                errors.append(FieldError("drive_time", "drive_time.from is required"))
            minutes = drive_time.get("minutes")
            if not isinstance(minutes, int) or isinstance(minutes, bool) or minutes < 0:
                errors.append(FieldError("drive_time", "drive_time.minutes must be a non-negative integer"))
            km = drive_time.get("km")
            if not _is_number(km) or km < 0:
                errors.append(FieldError("drive_time", "drive_time.km must be a non-negative number"))

    verification = data.get("verification")
    if verification is not None:
        if not isinstance(verification, dict):
            errors.append(FieldError("verification", "verification must be an object keyed by field name"))
        else:
            extra = [k for k in verification if k not in VERIFIABLE_FIELDS]
            if extra:
                errors.append(FieldError("verification", f"verification has non-verifiable keys: {', '.join(extra)}"))
            for field_name, record in verification.items():
                if field_name not in VERIFIABLE_FIELDS:
                    continue
                if not isinstance(record, dict):
                    errors.append(FieldError("verification", f"verification.{field_name} must be an object"))
                    continue
                if not isinstance(record.get("source"), str) or not record.get("source", "").strip():
                    errors.append(FieldError("verification", f"verification.{field_name}.source is required"))
                if record.get("tier") not in CONFIDENCE_TIERS:
                    errors.append(FieldError("verification", f"verification.{field_name}.tier must be one of {', '.join(CONFIDENCE_TIERS)}"))
                rec_date = record.get("date")
                rec_date_str = rec_date.isoformat() if isinstance(rec_date, date) else rec_date
                if not isinstance(rec_date_str, str) or not _DATE_RE.match(rec_date_str):
                    errors.append(FieldError("verification", f"verification.{field_name}.date must be a date (YYYY-MM-DD)"))

    change_log = data.get("change_log")
    if change_log is not None and not isinstance(change_log, list):
        errors.append(FieldError("change_log", "change_log must be a list"))

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

    verified = data.get("verified")
    verified_str = verified.isoformat() if isinstance(verified, date) else verified
    if not isinstance(verified_str, str) or not _DATE_RE.match(verified_str):
        errors.append(FieldError("verified", "verified must be a date (YYYY-MM-DD)"))

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

    extra_fields = [key for key in data if key not in KNOWN_FIELDS]
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
