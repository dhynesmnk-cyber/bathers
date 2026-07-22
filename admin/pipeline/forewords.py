"""State / state+amenity foreword generation (UX.md §2.3).

`forewords.json` is generated-but-human-editable: entries are written once,
the first time a state or state+amenity combination gets its first published
venue, and never overwritten by a later run (UX.md — "not regenerated every
build, or the copy churns"). This is a separate build-support call from the
three-agent harvest pipeline in TRD.md §7 — same model, same integrity rules,
different job (page copy, not a venue record).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from admin.config import (
    AMENITY_FULL_NAMES,
    AMENITY_KEYS,
    CATEGORY_KEYS,
    CATEGORY_LABELS,
    FOREWORDS_JSON_PATH,
    MODEL_ARCHITECT,
    PUBLISHED_DIR,
    STATE_NAMES,
)
from admin.pipeline import agents
from admin.pipeline.data_store import iter_published

LogFn = Callable[[str, str], None]

MAX_FOREWORD_CHARS = 600

_logger = logging.getLogger("admin.forewords")


def _default_log(text: str, level: str) -> None:
    getattr(_logger, "warning" if level == "error" else "info")(text)


def load_forewords(path: Path = FOREWORDS_JSON_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_forewords(data: dict[str, Any], path: Path = FOREWORDS_JSON_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _venues_by_state(published_dir: Path = PUBLISHED_DIR) -> dict[str, list[dict[str, Any]]]:
    by_state: dict[str, list[dict[str, Any]]] = {}
    for slug, data in iter_published(published_dir):
        by_state.setdefault(data["state"], []).append({"slug": slug, **data})
    return by_state


def _venues_by_category(published_dir: Path = PUBLISHED_DIR) -> dict[str, list[dict[str, Any]]]:
    by_category: dict[str, list[dict[str, Any]]] = {}
    for slug, data in iter_published(published_dir):
        by_category.setdefault(data["category"], []).append({"slug": slug, **data})
    return by_category


def _validate_foreword(text: str) -> str:
    text = text.strip().strip('"')
    if not text:
        raise ValueError("empty foreword")
    if len(text) > MAX_FOREWORD_CHARS:
        raise ValueError(f"foreword too long ({len(text)} chars, max {MAX_FOREWORD_CHARS})")
    return text


def _generate_one(
    state: str | None, amenity_key: str | None, venues: list[dict[str, Any]], log: LogFn, category_key: str | None = None
) -> str:
    system = agents.load_prompt("foreword.md")
    payload = {
        "state": STATE_NAMES[state] if state else None,
        "amenity": AMENITY_FULL_NAMES[amenity_key] if amenity_key else None,
        "category": CATEGORY_LABELS[category_key] if category_key else None,
        "venues": [{"name": v["name"], "suburb": v["suburb"]} for v in venues],
    }
    text, usage = agents.call_agent(
        model=MODEL_ARCHITECT,
        system=system,
        user_content=json.dumps(payload, ensure_ascii=False),
        max_tokens=400,
        validate=_validate_foreword,
        log=log,
    )
    log(f"foreword: {usage.input_tokens} in / {usage.output_tokens} out tokens", "info")
    return text


def ensure_forewords(published_dir: Path = PUBLISHED_DIR, log: LogFn = _default_log) -> list[str]:
    """Generate and persist forewords for any state / state+amenity combo
    that now has >=1 published venue but no entry yet. Returns the list of
    newly-written keys (e.g. "VIC", "VIC/magnesium_pool"). Never touches an
    existing entry — a human may have hand-edited it."""
    data = load_forewords()
    by_state = _venues_by_state(published_dir)
    new_keys: list[str] = []

    for state, venues in by_state.items():
        state_entry = data.setdefault(state, {})
        if "state" not in state_entry:
            try:
                state_entry["state"] = _generate_one(state, None, venues, log)
                new_keys.append(state)
            except (agents.AgentError, agents.MalformedOutput) as exc:
                log(f"foreword for {state} failed: {exc}", "error")

        amenities_entry = state_entry.setdefault("amenities", {})
        for key in AMENITY_KEYS:
            matching = [v for v in venues if v["amenities"].get(key)]
            if not matching or key in amenities_entry:
                continue
            try:
                amenities_entry[key] = _generate_one(state, key, matching, log)
                new_keys.append(f"{state}/{key}")
            except (agents.AgentError, agents.MalformedOutput) as exc:
                log(f"foreword for {state}/{key} failed: {exc}", "error")

    categories_entry = data.setdefault("categories", {})
    by_category = _venues_by_category(published_dir)
    for category, venues in by_category.items():
        if category in categories_entry:
            continue
        try:
            categories_entry[category] = _generate_one(None, None, venues, log, category_key=category)
            new_keys.append(f"category/{category}")
        except (agents.AgentError, agents.MalformedOutput) as exc:
            log(f"foreword for category/{category} failed: {exc}", "error")

    if new_keys:
        save_forewords(data)
    return new_keys


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate forewords.json entries for any state/amenity combo missing one."
    )
    parser.add_argument("--generate-missing", action="store_true", required=True)
    parser.parse_args()
    new_keys = ensure_forewords(log=lambda text, level: print(f"{level}: {text}"))
    if new_keys:
        print(f"Generated {len(new_keys)} foreword(s): {', '.join(new_keys)}")
    else:
        print("Nothing to generate — all published state/amenity combos already have a foreword.")


if __name__ == "__main__":
    main()
