"""Owns `data/outreach.db` — the operator-outreach state machine (Gate 13,
2026-09-08; the deferred Gate 8).

Its own SQLite file for the same reason `claims.db` is separate: `data_store`
deletes and recreates `directory.db` on every venue write, and an outreach
history — who was approached, when, what they said — cannot be reconstructed
from published frontmatter. Gitignored, because it holds operator names, email
addresses and private correspondence notes.

Two tables. `outreach` carries one row per venue ever contacted; `outreach_log`
is append-only, one row per transition, so "what happened with this venue" is
answerable months later even after the current state has moved on. Nothing here
deletes a log entry.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from admin.config import OUTREACH_DB_PATH, OUTREACH_STATES, OUTREACH_TRANSITIONS

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS outreach (
  slug TEXT PRIMARY KEY,
  state TEXT NOT NULL DEFAULT 'not_contacted',
  operator_name TEXT,
  operator_email TEXT,
  published_email TEXT,
  contacted_at TEXT,
  responded_at TEXT,
  resolved_at TEXT,
  confirmed_fields_json TEXT NOT NULL DEFAULT '[]',
  note TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outreach_state ON outreach(state);

CREATE TABLE IF NOT EXISTS outreach_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL,
  at TEXT NOT NULL,
  from_state TEXT,
  to_state TEXT NOT NULL,
  channel TEXT,
  note TEXT
);
CREATE INDEX IF NOT EXISTS idx_outreach_log_slug ON outreach_log(slug);
"""

# Additive schema evolution, matching claims_store.py's posture: no formal
# migration tool, applied on every connect, failure-to-apply meaning "already
# there". Needed because `CREATE TABLE IF NOT EXISTS` above never adds a column
# to a table that already exists on the Fly volume.
_MIGRATIONS = (
    "ALTER TABLE outreach ADD COLUMN published_email TEXT",
)

COLUMNS = (
    "slug", "state", "operator_name", "operator_email", "published_email",
    "contacted_at", "responded_at", "resolved_at",
    "confirmed_fields_json", "note", "created_at", "updated_at",
)


class IllegalTransition(Exception):
    """A transition the state machine does not allow. Deliberately an
    exception rather than a silent no-op: recording a venue as
    operator-confirmed without anyone having been contacted would put a false
    provenance claim into published frontmatter."""


@dataclass
class OutreachRow:
    slug: str
    state: str
    operator_name: str | None
    # Two addresses, deliberately not one. `operator_email` is who we actually
    # wrote to — part of the outreach record. `published_email` is what the
    # venue publishes on its own site, harvested rather than typed, and offered
    # to the screen as a starting point. Collapsing them would lose the
    # distinction between an address somebody has checked and one nobody has.
    operator_email: str | None
    published_email: str | None
    contacted_at: str | None
    responded_at: str | None
    resolved_at: str | None
    confirmed_fields_json: str
    note: str | None
    created_at: str
    updated_at: str

    @property
    def confirmed_fields(self) -> list[str]:
        return json.loads(self.confirmed_fields_json)


def _connect() -> sqlite3.Connection:
    OUTREACH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(OUTREACH_DB_PATH)
    conn.executescript(SCHEMA_SQL)
    for statement in _MIGRATIONS:
        try:
            conn.execute(statement)
        except sqlite3.OperationalError:
            pass  # column already exists — migration already applied
    return conn


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _row(record: tuple) -> OutreachRow:
    return OutreachRow(**dict(zip(COLUMNS, record)))


def get(slug: str) -> OutreachRow | None:
    conn = _connect()
    try:
        found = conn.execute(
            f"SELECT {', '.join(COLUMNS)} FROM outreach WHERE slug = ?", (slug,)
        ).fetchone()
        return _row(found) if found else None
    finally:
        conn.close()


def ensure(slug: str) -> OutreachRow:
    """The row for a venue, created in `not_contacted` if it has none. Called
    lazily rather than backfilled for every published venue, so the table
    reflects work actually done rather than a wall of empty rows."""
    existing = get(slug)
    if existing is not None:
        return existing
    conn = _connect()
    try:
        now = _now()
        conn.execute(
            "INSERT INTO outreach (slug, state, created_at, updated_at) VALUES (?, 'not_contacted', ?, ?)",
            (slug, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    row = get(slug)
    assert row is not None
    return row


def set_published_email(slug: str, email: str | None) -> OutreachRow:
    """Record the address the venue publishes on its own site.

    Deliberately not a transition: learning a venue's email address is not
    something that happened *with* the operator, so it earns no `outreach_log`
    entry and never moves the state machine. It is reference data attached to
    the venue, which is why it lives here rather than in published frontmatter
    — this file is gitignored, and an operator's address is not something the
    directory should publish on their behalf (owner decision, 2026-09-15).
    """
    ensure(slug)
    conn = _connect()
    try:
        conn.execute(
            "UPDATE outreach SET published_email = ?, updated_at = ? WHERE slug = ?",
            (email, _now(), slug),
        )
        conn.commit()
    finally:
        conn.close()
    row = get(slug)
    assert row is not None
    return row


def list_rows(state: str | None = None) -> list[OutreachRow]:
    conn = _connect()
    try:
        if state:
            found = conn.execute(
                f"SELECT {', '.join(COLUMNS)} FROM outreach WHERE state = ? ORDER BY slug", (state,)
            ).fetchall()
        else:
            found = conn.execute(
                f"SELECT {', '.join(COLUMNS)} FROM outreach ORDER BY slug"
            ).fetchall()
        return [_row(r) for r in found]
    finally:
        conn.close()


def transition(
    slug: str,
    to_state: str,
    *,
    channel: str | None = None,
    note: str | None = None,
    operator_name: str | None = None,
    operator_email: str | None = None,
    confirmed_fields: list[str] | None = None,
) -> OutreachRow:
    """Move a venue to `to_state`, refusing anything the machine disallows, and
    append a log entry. Timestamps are set from the destination state rather
    than passed in, so `contacted_at` always means what it says."""
    if to_state not in OUTREACH_STATES:
        raise IllegalTransition(f"unknown state {to_state!r}")
    row = ensure(slug)
    allowed = OUTREACH_TRANSITIONS.get(row.state, ())
    if to_state not in allowed:
        raise IllegalTransition(
            f"{slug}: cannot go {row.state} -> {to_state} "
            f"(allowed from {row.state}: {', '.join(allowed) or 'nothing'})"
        )

    now = _now()
    updates: dict[str, Any] = {"state": to_state, "updated_at": now}
    if to_state == "contacted":
        updates["contacted_at"] = now
    elif to_state == "responded":
        updates["responded_at"] = now
    elif to_state in ("operator_confirmed", "declined", "no_response"):
        updates["resolved_at"] = now
    if operator_name is not None:
        updates["operator_name"] = operator_name
    if operator_email is not None:
        updates["operator_email"] = operator_email
    if note is not None:
        updates["note"] = note
    if confirmed_fields is not None:
        updates["confirmed_fields_json"] = json.dumps(sorted(confirmed_fields))

    conn = _connect()
    try:
        assignments = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE outreach SET {assignments} WHERE slug = ?", (*updates.values(), slug)
        )
        conn.execute(
            "INSERT INTO outreach_log (slug, at, from_state, to_state, channel, note) VALUES (?, ?, ?, ?, ?, ?)",
            (slug, now, row.state, to_state, channel, note),
        )
        conn.commit()
    finally:
        conn.close()
    updated = get(slug)
    assert updated is not None
    return updated


def log_for(slug: str) -> list[dict[str, Any]]:
    conn = _connect()
    try:
        found = conn.execute(
            "SELECT at, from_state, to_state, channel, note FROM outreach_log WHERE slug = ? ORDER BY id",
            (slug,),
        ).fetchall()
        return [
            {"at": a, "from_state": f, "to_state": t, "channel": c, "note": n}
            for a, f, t, c, n in found
        ]
    finally:
        conn.close()


def counts_by_state() -> dict[str, int]:
    """Rows in this table, by state — not a venue tally. A venue has no row
    until something happens to it, so this under-reports `not_contacted` by
    every venue nothing has happened to yet. For the screen's numbers use
    `outreach.counts_by_state()`, which tallies published venues."""
    conn = _connect()
    try:
        found = conn.execute("SELECT state, COUNT(*) FROM outreach GROUP BY state").fetchall()
        return {state: count for state, count in found}
    finally:
        conn.close()
