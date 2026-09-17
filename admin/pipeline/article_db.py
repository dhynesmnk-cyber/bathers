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
            "source": "registry",
            "demand": None,  # filled below where Search Console has a figure
        })

    _merge_demand(out)
    # Demand rows have no query_key, so they sort last and by strength — and the
    # key must not compare None against a string, which is what a bare
    # o["query_key"] would do the moment the feed returns an unmatched query.
    out.sort(
        key=lambda o: (
            o["source"] != "registry",
            o["written"],
            o["status"] != "candidate",
            -(o["demand"]["impressions"] if o["source"] == "gsc" and o["demand"] else 0),
            o["query_key"] or "",
        )
    )
    return out


def _merge_demand(out: list[dict[str, Any]]) -> None:
    """Fold Search Console demand into the queue (Gate 15).

    Two things happen, and the difference matters:

    - A query that maps onto a comparison the registry already knows about
      annotates that row with its impressions. It does not change the row's
      status; a real article is still a real article whether or not anyone
      searched for it this quarter.
    - A query that maps onto nothing becomes a new row — a content gap the
      registry cannot see, because the registry is derived from venues the site
      already has rather than from what people actually ask.

    **A demand row is never draftable.** It carries no `query_key` the drafting
    gate recognises and no brief, and `draftable` is pinned False here rather
    than computed, so no arrangement of data can make one draft itself. Demand
    surfaces an intent for a human to brief; the brief gate still governs. That
    rule is older than this feed and is not relaxed by it.

    A missing or unconfigured feed leaves the queue exactly as it was.
    """
    try:
        from admin.pipeline import gsc

        rows = gsc.demand_signal()
    except Exception:  # noqa: BLE001 — the queue must survive a broken feed
        return
    if not rows:
        return

    by_key = {o["query_key"]: o for o in out}
    for row in rows:
        if row.matched_query_key and row.matched_query_key in by_key:
            existing = by_key[row.matched_query_key]["demand"]
            # One comparison can match several queries; keep the strongest.
            if existing is None or row.impressions > existing["impressions"]:
                by_key[row.matched_query_key]["demand"] = {
                    "query": row.query,
                    "impressions": row.impressions,
                    "clicks": row.clicks,
                    "avg_position": row.avg_position,
                }
            continue

        out.append({
            "query_key": None,
            "title": row.query,
            "kind": "demand",
            "venue_count": None,
            "populated": 0,
            "total": 0,
            "completeness": 0.0,
            "written": False,
            "status": "demand",
            "reason": "search demand with no comparison behind it — brief it or ignore it",
            "disposition": None,
            "brief": None,
            "draftable": False,
            "source": "gsc",
            "demand": {
                "query": row.query,
                "impressions": row.impressions,
                "clicks": row.clicks,
                "avg_position": row.avg_position,
            },
        })


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
            # A demand row has no query_key — format its query instead, and never
            # pass None to a width-formatted field.
            label = o["query_key"] or f"“{o['title']}”"
            demand = o.get("demand")
            print(
                f"  {o['status']:<10} {label:<28} "
                f"{o['populated']}/{o['total']} figs  "
                f"brief={b['status'] if b else '-'}"
                + (f"  {demand['impressions']} impr" if demand else "")
                + (f"  ({o['reason']})" if o["reason"] else "")
            )
    if args.briefs:
        for b in list_briefs():
            print(f"  #{b['id']} {b['status']:<9} {b['query_key']:<28} {b['created_at']}")


if __name__ == "__main__":
    main()
