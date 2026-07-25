"""Owns `data/claims.db` — visitor-submitted claim-listing requests (TRD.md
§8, 2026-07-25 exception). Unlike `data_store.py`'s `directory.db`, this file
is never destructively rebuilt: it's its own source of truth, not a derived
artefact, since a claim request (requester contact, submitted patch, Stripe
session state) can't be reconstructed from published venue frontmatter.
"""

from __future__ import annotations

import datetime
import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from admin.config import CLAIMS_DB_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS claim_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL,
  submitted_at TEXT NOT NULL,
  requester_name TEXT NOT NULL,
  requester_email TEXT NOT NULL,
  plan_type TEXT NOT NULL,
  patch_json TEXT NOT NULL,
  has_photo INTEGER NOT NULL DEFAULT 0,
  photo_path TEXT,
  photo_caption TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  review_note TEXT,
  reviewed_at TEXT,
  stripe_checkout_session_id TEXT,
  stripe_customer_id TEXT,
  is_returning_subscriber INTEGER NOT NULL DEFAULT 0,
  honeypot_tripped INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_claim_requests_slug ON claim_requests(slug);
CREATE INDEX IF NOT EXISTS idx_claim_requests_status ON claim_requests(status);
CREATE INDEX IF NOT EXISTS idx_claim_requests_session ON claim_requests(stripe_checkout_session_id);
"""

COLUMNS = (
    "id", "slug", "submitted_at", "requester_name", "requester_email", "plan_type",
    "patch_json", "has_photo", "photo_path", "photo_caption", "status", "review_note",
    "reviewed_at", "stripe_checkout_session_id", "stripe_customer_id",
    "is_returning_subscriber", "honeypot_tripped",
)


@dataclass
class ClaimRequest:
    id: int
    slug: str
    submitted_at: str
    requester_name: str
    requester_email: str
    plan_type: str
    patch_json: str
    has_photo: bool
    photo_path: str | None
    photo_caption: str | None
    status: str
    review_note: str | None
    reviewed_at: str | None
    stripe_checkout_session_id: str | None
    stripe_customer_id: str | None
    is_returning_subscriber: bool
    honeypot_tripped: bool

    @property
    def patch(self) -> dict[str, Any]:
        return json.loads(self.patch_json)


def _connect() -> sqlite3.Connection:
    CLAIMS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CLAIMS_DB_PATH)
    conn.executescript(SCHEMA_SQL)
    return conn


def _row_to_request(row: tuple) -> ClaimRequest:
    data = dict(zip(COLUMNS, row))
    data["has_photo"] = bool(data["has_photo"])
    data["is_returning_subscriber"] = bool(data["is_returning_subscriber"])
    data["honeypot_tripped"] = bool(data["honeypot_tripped"])
    return ClaimRequest(**data)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def create_request(
    *,
    slug: str,
    requester_name: str,
    requester_email: str,
    plan_type: str,
    patch: dict[str, Any],
    has_photo: bool = False,
    photo_caption: str | None = None,
    honeypot_tripped: bool = False,
) -> ClaimRequest:
    conn = _connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO claim_requests
              (slug, submitted_at, requester_name, requester_email, plan_type,
               patch_json, has_photo, photo_caption, status, honeypot_tripped)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                slug, _now(), requester_name, requester_email, plan_type,
                json.dumps(patch), int(has_photo), photo_caption, int(honeypot_tripped),
            ),
        )
        conn.commit()
        return get_request(cur.lastrowid, conn=conn)
    finally:
        conn.close()


def get_request(request_id: int, *, conn: sqlite3.Connection | None = None) -> ClaimRequest:
    owns_conn = conn is None
    conn = conn or _connect()
    try:
        row = conn.execute(
            f"SELECT {', '.join(COLUMNS)} FROM claim_requests WHERE id = ?", (request_id,)
        ).fetchone()
        if row is None:
            raise KeyError(request_id)
        return _row_to_request(row)
    finally:
        if owns_conn:
            conn.close()


def get_by_session_id(session_id: str) -> ClaimRequest | None:
    conn = _connect()
    try:
        row = conn.execute(
            f"SELECT {', '.join(COLUMNS)} FROM claim_requests WHERE stripe_checkout_session_id = ?",
            (session_id,),
        ).fetchone()
        return _row_to_request(row) if row else None
    finally:
        conn.close()


def list_requests(status: str | None = None) -> list[ClaimRequest]:
    conn = _connect()
    try:
        if status:
            rows = conn.execute(
                f"SELECT {', '.join(COLUMNS)} FROM claim_requests WHERE status = ? ORDER BY id DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {', '.join(COLUMNS)} FROM claim_requests ORDER BY id DESC"
            ).fetchall()
        return [_row_to_request(r) for r in rows]
    finally:
        conn.close()


def count_recent_for_slug(slug: str, since_seconds: int) -> int:
    cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=since_seconds)).isoformat()
    conn = _connect()
    try:
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM claim_requests WHERE slug = ? AND submitted_at >= ?",
            (slug, cutoff),
        ).fetchone()
        return count
    finally:
        conn.close()


def set_photo_path(request_id: int, path: str) -> None:
    conn = _connect()
    try:
        conn.execute("UPDATE claim_requests SET photo_path = ? WHERE id = ?", (path, request_id))
        conn.commit()
    finally:
        conn.close()


def update_status(request_id: int, status: str, *, review_note: str | None = None) -> ClaimRequest:
    conn = _connect()
    try:
        if review_note is not None:
            conn.execute(
                "UPDATE claim_requests SET status = ?, review_note = ?, reviewed_at = ? WHERE id = ?",
                (status, review_note, _now(), request_id),
            )
        else:
            conn.execute("UPDATE claim_requests SET status = ? WHERE id = ?", (status, request_id))
        conn.commit()
        return get_request(request_id, conn=conn)
    finally:
        conn.close()


def set_stripe_session(request_id: int, session_id: str, customer_id: str | None) -> ClaimRequest:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE claim_requests SET stripe_checkout_session_id = ?, stripe_customer_id = ? WHERE id = ?",
            (session_id, customer_id, request_id),
        )
        conn.commit()
        return get_request(request_id, conn=conn)
    finally:
        conn.close()


def set_stripe_customer(request_id: int, customer_id: str) -> ClaimRequest:
    conn = _connect()
    try:
        conn.execute("UPDATE claim_requests SET stripe_customer_id = ? WHERE id = ?", (customer_id, request_id))
        conn.commit()
        return get_request(request_id, conn=conn)
    finally:
        conn.close()


def mark_returning_subscriber(request_id: int) -> None:
    conn = _connect()
    try:
        conn.execute("UPDATE claim_requests SET is_returning_subscriber = 1 WHERE id = ?", (request_id,))
        conn.commit()
    finally:
        conn.close()
