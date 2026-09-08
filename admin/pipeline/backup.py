"""Consistent snapshots of the two databases that cannot be rebuilt (Gate 12,
2026-09-08).

`data/directory.db` is a derived artefact — `data_store.rebuild()` recreates it
from `_published` frontmatter, so losing it costs one command. `claims.db` and
`articles.db` are not: a claim request (requester contact, submitted patch,
Stripe session state) and an editorial brief the operator wrote cannot be
reconstructed from anything. They are also the two files deliberately kept out
of git, which means the repository is not their backup and nothing else was.

**Consistency.** Copies go through sqlite3's online backup API rather than a
file copy, so a snapshot taken while the admin is mid-write is a valid
database, not a torn page. Each snapshot carries a SHA-256 manifest and is
verified by reopening every restored file and running `PRAGMA integrity_check`
— a backup nobody has restored is a hypothesis, not a backup.

**Where the copies live.** `data/backups/` on the Fly volume, gitignored. The
volume is encrypted at rest and Fly takes its own daily volume snapshots, which
is what makes this off-host. Be clear about the limit of that: volume snapshots
are same-provider, so they cover a lost machine or a bad deploy, not a lost Fly
account. A genuinely off-provider copy needs a destination to send to, which is
a decision, not a default — until it is made, `--restore --into` is deliberately
easy to point at a local directory so an operator can pull a copy down by hand.

No new dependency: stdlib `sqlite3`, `gzip`, `hashlib`, `pathlib`, `shutil`.
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from admin import security
from admin.config import (
    ARTICLES_DB_PATH,
    BACKUP_INTERVAL_HOURS,
    BACKUP_KEEP,
    BACKUPS_DIR,
    CLAIMS_DB_PATH,
)

# The databases worth snapshotting: the ones no rebuild can restore.
# directory.db is deliberately absent — `data_store.py --rebuild` is its backup.
SOURCES: tuple[Path, ...] = (CLAIMS_DB_PATH, ARTICLES_DB_PATH)

MANIFEST_NAME = "manifest.json"
DEFAULT_KEEP = 30


class BackupError(Exception):
    pass


@dataclass(frozen=True)
class Snapshot:
    path: Path
    taken_at: str
    files: dict[str, str]  # archive filename -> sha256 of the uncompressed db

    @property
    def name(self) -> str:
        return self.path.name


def _now_stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _consistent_copy(source: Path, dest: Path) -> None:
    """sqlite3's online backup API — safe against a concurrent writer, which a
    plain file copy is not."""
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def snapshot(*, keep: int = DEFAULT_KEEP) -> Snapshot:
    """Take one snapshot of every source database that exists, then prune."""
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    taken_at = _now_stamp()
    target = BACKUPS_DIR / taken_at
    target.mkdir(exist_ok=True)

    files: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as tmpdir:
        for source in SOURCES:
            if not source.exists():
                # A database that has never been written is not an error — the
                # admin creates each on first use.
                continue
            staged = Path(tmpdir) / source.name
            _consistent_copy(source, staged)
            archive = target / f"{source.name}.gz"
            with staged.open("rb") as raw, gzip.open(archive, "wb") as gz:
                shutil.copyfileobj(raw, gz)
            files[archive.name] = _sha256(staged)

    manifest = {"taken_at": taken_at, "files": files}
    (target / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    prune(keep=keep)
    return Snapshot(target, taken_at, files)


def list_snapshots() -> list[Snapshot]:
    if not BACKUPS_DIR.exists():
        return []
    found: list[Snapshot] = []
    for entry in sorted(BACKUPS_DIR.iterdir()):
        manifest_path = entry / MANIFEST_NAME
        if not entry.is_dir() or not manifest_path.exists():
            continue
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        found.append(Snapshot(entry, data["taken_at"], data["files"]))
    return found


def prune(*, keep: int = DEFAULT_KEEP) -> list[str]:
    """Drop all but the newest `keep` snapshots. Names sort chronologically."""
    snapshots = list_snapshots()
    removed: list[str] = []
    for stale in snapshots[:-keep] if keep > 0 else []:
        shutil.rmtree(stale.path)
        removed.append(stale.name)
    return removed


def restore(snapshot_name: str, into: Path) -> list[Path]:
    """Decompress a snapshot's databases into `into`, verifying each against the
    manifest hash and SQLite's own integrity check.

    Deliberately never writes over the live databases: it restores to a
    directory the operator names, and moving the result into place is a separate,
    deliberate step. Restoring straight onto a running admin's claims.db is how a
    recovery turns into a second incident.
    """
    source = BACKUPS_DIR / snapshot_name
    manifest_path = source / MANIFEST_NAME
    if not manifest_path.exists():
        raise BackupError(f"no snapshot '{snapshot_name}' in {BACKUPS_DIR}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    into.mkdir(parents=True, exist_ok=True)
    restored: list[Path] = []
    for archive_name, expected_sha in manifest["files"].items():
        archive = source / archive_name
        if not archive.exists():
            raise BackupError(f"{snapshot_name}: missing {archive_name}")
        dest = into / archive_name[: -len(".gz")]
        with gzip.open(archive, "rb") as gz, dest.open("wb") as out:
            shutil.copyfileobj(gz, out)
        actual_sha = _sha256(dest)
        if actual_sha != expected_sha:
            raise BackupError(
                f"{snapshot_name}/{archive_name}: sha256 mismatch — "
                f"expected {expected_sha[:12]}…, got {actual_sha[:12]}…"
            )
        _integrity_check(dest)
        restored.append(dest)
    return restored


def _integrity_check(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        (result,) = conn.execute("PRAGMA integrity_check").fetchone()
    finally:
        conn.close()
    if result != "ok":
        raise BackupError(f"{db_path.name}: integrity_check returned {result!r}")


def verify(snapshot_name: str) -> list[Path]:
    """Restore into a temp directory and throw the result away — proves the
    snapshot is restorable without touching anything live."""
    with tempfile.TemporaryDirectory() as tmpdir:
        return [p.name for p in restore(snapshot_name, Path(tmpdir))]


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


def start_scheduler(*, interval_hours: int = BACKUP_INTERVAL_HOURS, keep: int = BACKUP_KEEP) -> threading.Thread | None:
    """Snapshot on a timer for as long as the admin process lives.

    A daemon thread rather than a cron machine or a systemd timer: fly.toml
    keeps one machine running with auto_stop off, so this process is the thing
    that is always up, and an in-process timer adds no infrastructure to forget
    about. It takes one snapshot at startup so a freshly booted machine is
    covered immediately rather than `interval_hours` later.

    Failures are logged and swallowed. A backup that cannot be written must
    never take the admin down — but it must never be silent either, which is
    why every outcome goes to the audit log.
    """
    if interval_hours <= 0:
        return None

    def loop() -> None:
        while True:
            try:
                snap = snapshot(keep=keep)
                verify(snap.name)
                audit_note = f"backup {snap.name} ok ({len(snap.files)} database(s))"
            except Exception as exc:  # noqa: BLE001 — see docstring
                audit_note = f"backup FAILED: {exc}"
            print(f"[admin] {audit_note}")
            security.audit(method="INTERNAL", path="/backup", status=0,
                           client="scheduler", authenticated=True, note=audit_note)
            time.sleep(interval_hours * 3600)

    thread = threading.Thread(target=loop, name="backup-scheduler", daemon=True)
    thread.start()
    return thread


# ---------------------------------------------------------------------------
# Self-test — `python3 -m admin.pipeline.backup --self-test`
# ---------------------------------------------------------------------------


def _self_test() -> int:
    # sys.modules[__name__], not `import admin.pipeline.backup` — under
    # `python -m` that import builds a SECOND module object whose BackupError is
    # a different class from this one's, so `except BackupError` would not catch
    # what the functions under test raise.
    module = sys.modules[__name__]

    failures: list[str] = []

    def check(label: str, condition: bool) -> None:
        if condition:
            print(f"  ok    {label}")
        else:
            failures.append(label)
            print(f"  FAIL  {label}")

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        live = root / "live.db"
        conn = sqlite3.connect(live)
        conn.execute("CREATE TABLE claim_requests (id INTEGER PRIMARY KEY, email TEXT)")
        conn.executemany("INSERT INTO claim_requests (email) VALUES (?)",
                         [(f"owner{i}@example.com",) for i in range(50)])
        conn.commit()
        conn.close()

        original_dir, original_sources = module.BACKUPS_DIR, module.SOURCES
        module.BACKUPS_DIR = root / "backups"
        module.SOURCES = (live,)
        try:
            # A snapshot taken while a writer holds the database open must still
            # be valid — that is the whole reason for the online backup API.
            writer = sqlite3.connect(live)
            writer.execute("INSERT INTO claim_requests (email) VALUES ('mid-write@example.com')")
            snap = module.snapshot()
            writer.close()
            check("snapshot captures the source database", "live.db.gz" in snap.files)

            restored = module.restore(snap.name, root / "restore-a")
            check("restore writes the database back", restored and restored[0].exists())

            conn = sqlite3.connect(restored[0])
            (rows,) = conn.execute("SELECT COUNT(*) FROM claim_requests").fetchone()
            conn.close()
            check("restored database carries every committed row", rows == 50)

            check("verify passes on a good snapshot", bool(module.verify(snap.name)))

            # Corruption must be caught, not silently restored.
            archive = module.BACKUPS_DIR / snap.name / "live.db.gz"
            with gzip.open(archive, "wb") as gz:
                gz.write(b"this is not a database")
            try:
                module.verify(snap.name)
                check("a corrupted snapshot fails verification", False)
            except BackupError:
                check("a corrupted snapshot fails verification", True)

            try:
                module.restore("20000101T000000Z", root / "restore-b")
                check("an unknown snapshot name is refused", False)
            except BackupError:
                check("an unknown snapshot name is refused", True)

            # Retention.
            for stamp in ("20260101T000000Z", "20260102T000000Z", "20260103T000000Z"):
                fake = module.BACKUPS_DIR / stamp
                fake.mkdir(parents=True, exist_ok=True)
                (fake / MANIFEST_NAME).write_text(json.dumps({"taken_at": stamp, "files": {}}), encoding="utf-8")
            module.prune(keep=2)
            check("prune keeps only the newest snapshots", len(module.list_snapshots()) == 2)
        finally:
            module.BACKUPS_DIR, module.SOURCES = original_dir, original_sources

    print()
    if failures:
        print(f"FAIL — {len(failures)} check(s): {'; '.join(failures)}")
        return 1
    print("PASS — admin/pipeline/backup.py")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--snapshot", action="store_true", help="take a snapshot now")
    group.add_argument("--list", action="store_true", help="list stored snapshots")
    group.add_argument("--verify", metavar="NAME", help="prove a snapshot restores (NAME or 'latest')")
    group.add_argument("--restore", metavar="NAME", help="restore a snapshot (NAME or 'latest')")
    group.add_argument("--self-test", action="store_true", help="run the module's own checks")
    parser.add_argument("--into", type=Path, help="directory to restore into (required with --restore)")
    parser.add_argument("--keep", type=int, default=DEFAULT_KEEP, help=f"snapshots to retain (default {DEFAULT_KEEP})")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    def resolve(name: str) -> str:
        if name != "latest":
            return name
        snapshots = list_snapshots()
        if not snapshots:
            raise BackupError("no snapshots stored yet")
        return snapshots[-1].name

    try:
        if args.snapshot:
            snap = snapshot(keep=args.keep)
            print(f"{snap.name} — {len(snap.files)} database(s) in {snap.path}")
            for name in sorted(snap.files):
                print(f"  {name}")
            verify(snap.name)
            print("verified: restores cleanly")
            return 0

        if args.list:
            snapshots = list_snapshots()
            if not snapshots:
                print(f"no snapshots in {BACKUPS_DIR}")
                return 0
            for snap in snapshots:
                print(f"{snap.name}  {len(snap.files)} database(s)")
            return 0

        if args.verify:
            names = verify(resolve(args.verify))
            print(f"verified {resolve(args.verify)}: {', '.join(names)}")
            return 0

        if args.restore:
            if args.into is None:
                parser.error("--restore requires --into (this never overwrites the live databases)")
            restored = restore(resolve(args.restore), args.into)
            for path in restored:
                print(f"restored {path}")
            print("Move these into place deliberately — the admin was not touched.")
            return 0
    except BackupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
