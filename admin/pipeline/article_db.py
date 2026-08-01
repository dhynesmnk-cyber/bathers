"""Owns `data/articles.db` — the editorial pipeline's front-end working state
(Editorial Gate E4a, 2026-08-01):

  * the **brief gate** — an auto-drafted brief per opportunity, approved or
    killed by a human before any drafting spend (the cheapest stop).
    `article_pipeline.run` refuses to draft an intent without an approved brief.
  * **opportunity-queue overrides** — a per-intent disposition (pinned or
    dismissed) layered over the auto-derived candidate list.

Like `claims.db` (and unlike `directory.db`) this file is its own source of
truth, never destructively rebuilt: a brief the operator wrote, or a dismissal
they made, can't be reconstructed from published content. `init()` only ensures
the schema (idempotent — safe to run repeatedly, operator state survives). The
*derived, committed* truths live elsewhere: `articles-meta.json` (staleness) and
`data/factchecks/` (published reports).

The opportunity *candidate* list itself is derived, not stored — it's the
comparison registry (via `articles-meta.json`, which the runner only writes for
eligible ≥5-venue comparisons) minus intents already written, with a
field-completeness signal computed from the ranking. Only the operator's
overrides and briefs are persisted here.
"""

from __future__ import annotations

import argparse
import datetime
import sqlite3
from typing import Any

from admin.config import ARTICLES_DB_PATH
from admin.pipeline import article_store, articles

# Below this fraction of ranked venues carrying a published headline figure, a
# comparison's table would read mostly empty — suppressed from the queue (with a
# reason) unless the operator pins it. A signal, not a hard rule.
MIN_FIELD_COMPLETENESS = 0.5

_BRIEF_STATUSES = ("pending", "approved", "killed")
_DISPOSITIONS = ("pinned", "dismissed")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS briefs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  query_key TEXT NOT NULL,
  title TEXT,
  brief_md TEXT NOT NULL,
  model TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL,
  decided_at TEXT,
  decided_by TEXT,
  note TEXT
);
CREATE INDEX IF NOT EXISTS idx_briefs_query_key ON briefs(query_key);
CREATE INDEX IF NOT EXISTS idx_briefs_status ON briefs(status);

CREATE TABLE IF NOT EXISTS opportunity_state (
  query_key TEXT PRIMARY KEY,
  disposition TEXT NOT NULL,
  reason TEXT,
  updated_at TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    ARTICLES_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ARTICLES_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn


def init() -> None:
    """Ensure the schema exists (idempotent). Never destroys operator state."""
    _connect().close()


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---- Briefs (the brief gate) ------------------------------------------------

def create_brief(query_key: str, brief_md: str, *, title: str | None = None, model: str | None = None) -> dict[str, Any]:
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO briefs (query_key, title, brief_md, model, status, created_at) "
            "VALUES (?, ?, ?, ?, 'pending', ?)",
            (query_key, title, brief_md, model, _now()),
        )
        conn.commit()
        return get_brief(int(cur.lastrowid), conn=conn)
    finally:
        conn.close()


def get_brief(brief_id: int, *, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    owns = conn is None
    conn = conn or _connect()
    try:
        row = conn.execute("SELECT * FROM briefs WHERE id = ?", (brief_id,)).fetchone()
        if row is None:
            raise KeyError(brief_id)
        return dict(row)
    finally:
        if owns:
            conn.close()


def latest_brief(query_key: str) -> dict[str, Any] | None:
    """The most recent brief for an intent — a later kill supersedes an earlier
    approval, so drafting eligibility keys off this row, not any-approved-ever."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM briefs WHERE query_key = ? ORDER BY id DESC LIMIT 1", (query_key,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_briefs(status: str | None = None) -> list[dict[str, Any]]:
    conn = _connect()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM briefs WHERE status = ? ORDER BY id DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM briefs ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def decide_brief(brief_id: int, status: str, *, decided_by: str | None = None, note: str | None = None) -> dict[str, Any]:
    """Approve or kill a brief (the human gate before drafting)."""
    if status not in ("approved", "killed"):
        raise ValueError(f"decide_brief status must be approved|killed, got {status!r}")
    conn = _connect()
    try:
        if conn.execute("SELECT 1 FROM briefs WHERE id = ?", (brief_id,)).fetchone() is None:
            raise KeyError(brief_id)
        conn.execute(
            "UPDATE briefs SET status = ?, decided_at = ?, decided_by = ?, note = ? WHERE id = ?",
            (status, _now(), decided_by, note, brief_id),
        )
        conn.commit()
        return get_brief(brief_id, conn=conn)
    finally:
        conn.close()


def approved_keys() -> set[str]:
    """Intents whose *latest* brief is approved (ignoring queue disposition)."""
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT b.query_key FROM briefs b
            JOIN (SELECT query_key, MAX(id) AS mx FROM briefs GROUP BY query_key) last
              ON b.id = last.mx
            WHERE b.status = 'approved'
            """
        ).fetchall()
        return {r["query_key"] for r in rows}
    finally:
        conn.close()


def draftable_keys() -> set[str]:
    """Intents an operator may draft *right now*: latest brief approved, not
    already written, and not dismissed from the queue. The single predicate the
    draft gate and the opportunity queue's `draftable` flag both key off — an
    approved-then-dismissed intent must not slip through the gate."""
    taken = articles.existing_query_keys()
    dismissed = {k for k, v in dispositions().items() if v["disposition"] == "dismissed"}
    return {k for k in approved_keys() if k not in taken and k not in dismissed}


# ---- Opportunity-queue overrides -------------------------------------------

def set_disposition(query_key: str, disposition: str, *, reason: str | None = None) -> dict[str, Any]:
    if disposition not in _DISPOSITIONS:
        raise ValueError(f"disposition must be one of {_DISPOSITIONS}, got {disposition!r}")
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO opportunity_state (query_key, disposition, reason, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(query_key) DO UPDATE SET disposition = excluded.disposition, "
            "reason = excluded.reason, updated_at = excluded.updated_at",
            (query_key, disposition, reason, _now()),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM opportunity_state WHERE query_key = ?", (query_key,)).fetchone())
    finally:
        conn.close()


def clear_disposition(query_key: str) -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM opportunity_state WHERE query_key = ?", (query_key,))
        conn.commit()
    finally:
        conn.close()


def dispositions() -> dict[str, dict[str, Any]]:
    conn = _connect()
    try:
        return {r["query_key"]: dict(r) for r in conn.execute("SELECT * FROM opportunity_state").fetchall()}
    finally:
        conn.close()


# ---- Derived opportunity queue ---------------------------------------------

def _completeness(entry: dict[str, Any]) -> tuple[int, int]:
    """(populated, total) headline figures across the current ranking — the
    fraction of ranked venues carrying a published value for the compared field."""
    sig = (entry.get("current") or {}).get("signature") or []
    total = len(sig)
    populated = sum(1 for s in sig if str(s).split("=", 1)[-1].strip())
    return populated, total


def _brief_summary(brief: dict[str, Any] | None) -> dict[str, Any] | None:
    if brief is None:
        return None
    return {k: brief.get(k) for k in ("id", "status", "created_at", "decided_at", "decided_by")}


def opportunities() -> list[dict[str, Any]]:
    """The opportunity queue: every registry comparison (≥5-venue, so present in
    articles-meta.json), tagged with whether it's already written, its
    field-completeness, the operator's disposition, and its latest brief.

    Status resolves in this order: written (already has a published/staged
    article) → dismissed → pinned → suppressed (below the completeness floor) →
    candidate. Pinned overrides suppression; dismissed hides from drafting.
    """
    meta = article_store.read_meta()
    taken = articles.existing_query_keys()
    disp = dispositions()
    draftable = draftable_keys()
    out: list[dict[str, Any]] = []
    for key, entry in meta.items():
        if not isinstance(entry, dict):
            continue
        populated, total = _completeness(entry)
        ratio = (populated / total) if total else 0.0
        d = disp.get(key)
        written = key in taken
        brief = latest_brief(key)

        reason: str | None = None
        if written:
            status = "written"
        elif d and d["disposition"] == "dismissed":
            status = "dismissed"
            reason = d.get("reason")
        elif d and d["disposition"] == "pinned":
            status = "pinned"
        elif ratio < MIN_FIELD_COMPLETENESS:
            status = "suppressed"
            reason = f"only {populated} of {total} ranked venues have a published headline figure"
        else:
            status = "candidate"

        out.append({
            "query_key": key,
            "title": entry.get("title"),
            "kind": entry.get("kind"),
            "venue_count": entry.get("venue_count"),
            "populated": populated,
            "total": total,
            "completeness": round(ratio, 2),
            "written": written,
            "status": status,
            "reason": reason,
            "disposition": d["disposition"] if d else None,
            "brief": _brief_summary(brief),
            # Single source of truth (draftable_keys): approved brief, not written,
            # not dismissed — the exact predicate the article_pipeline gate enforces.
            "draftable": key in draftable,
        })
    out.sort(key=lambda o: (o["written"], o["status"] != "candidate", o["query_key"]))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="articles.db (editorial pipeline working-state) — init + inspect.")
    parser.add_argument("--init", action="store_true", help="ensure the schema exists (idempotent)")
    parser.add_argument("--opportunities", action="store_true", help="print the derived opportunity queue")
    parser.add_argument("--briefs", action="store_true", help="print stored briefs")
    args = parser.parse_args()

    if args.init or not (args.opportunities or args.briefs):
        init()
        print(f"articles.db ready at {ARTICLES_DB_PATH}")
    if args.opportunities:
        for o in opportunities():
            b = o["brief"]
            print(
                f"  {o['status']:<10} {o['query_key']:<28} "
                f"{o['populated']}/{o['total']} figs  "
                f"brief={b['status'] if b else '-'}"
                + (f"  ({o['reason']})" if o["reason"] else "")
            )
    if args.briefs:
        for b in list_briefs():
            print(f"  #{b['id']} {b['status']:<9} {b['query_key']:<28} {b['created_at']}")


if __name__ == "__main__":
    main()
