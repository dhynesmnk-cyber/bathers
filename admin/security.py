"""Admin-app security primitives (Gate 12, 2026-09-08).

Collected here rather than inline in `admin/app.py` so the whole posture reads
in one place: what fails closed, what is capped, what is throttled, what is
recorded. `app.py` keeps a single middleware that calls into this module.

The posture this file assumes is the *real* one, recorded as a dated entry in
TRD.md §2: the admin app runs on a public host (Fly.io), not on localhost as
the original stack table said. Everything below follows from that — an app
reachable from the internet that holds the Anthropic, Stripe, Netlify, SMTP
and Google Places credentials and can push to git.
"""

from __future__ import annotations

import base64
import binascii
import json
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

from admin.config import (
    ADMIN_ALLOW_INSECURE_AUTH,
    ADMIN_MIN_PASSWORD_LENGTH,
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    AUDIT_LOG_PATH,
    AUTH_LOCKOUT_SECONDS,
    AUTH_MAX_FAILURES,
    AUTH_WINDOW_SECONDS,
    MAX_ADMIN_REQUEST_BYTES,
    MAX_PHOTO_BYTES,
    MAX_PUBLIC_REQUEST_BYTES,
)


class InsecureConfiguration(RuntimeError):
    """Raised at app import when auth would silently be off. Deliberately
    fatal: the failure mode this replaces was a *silent* one."""


class PhotoRejected(Exception):
    pass


# ---------------------------------------------------------------------------
# Startup assertion — the fail-open fix
# ---------------------------------------------------------------------------
#
# Before Gate 12 the middleware waved every request through when both
# ADMIN_USERNAME and ADMIN_PASSWORD were blank. That is a reasonable local-dev
# default and a serious hole on a public host: one unset Fly secret exposed all
# of this app's routes, including deploy and the pipeline runners, with nothing
# in the logs to say so. Blank credentials are now fatal unless the operator
# has explicitly asked for an unauthenticated app by setting
# ADMIN_ALLOW_INSECURE_AUTH — which docker-entrypoint.sh deliberately does not
# materialise into .env, so it cannot be turned on in production by accident.


@dataclass(frozen=True)
class AuthPosture:
    enforced: bool
    reason: str


def resolve_auth_posture() -> AuthPosture:
    """Decide whether Basic Auth is enforced, or raise if the answer would be
    'no' by accident. Call once at app import."""
    have_credentials = bool(ADMIN_USERNAME) and bool(ADMIN_PASSWORD)
    if have_credentials:
        return AuthPosture(True, "Basic Auth enforced")
    if ADMIN_ALLOW_INSECURE_AUTH:
        return AuthPosture(
            False,
            "Basic Auth DISABLED by explicit ADMIN_ALLOW_INSECURE_AUTH — "
            "never set this on a host reachable from the internet",
        )
    raise InsecureConfiguration(
        "ADMIN_USERNAME and ADMIN_PASSWORD must both be set — this app holds "
        "the Anthropic, Stripe, Netlify and SMTP credentials and can push to "
        "git. For an unauthenticated local dev run, set "
        "ADMIN_ALLOW_INSECURE_AUTH=1 in .env deliberately."
    )


def password_warnings() -> list[str]:
    """Non-fatal posture warnings, logged at startup. Deliberately not fatal:
    refusing to boot over password length would take a running deployment
    down on upgrade, which is a worse failure than a loud warning."""
    warnings: list[str] = []
    if ADMIN_PASSWORD and len(ADMIN_PASSWORD) < ADMIN_MIN_PASSWORD_LENGTH:
        warnings.append(
            f"ADMIN_PASSWORD is shorter than {ADMIN_MIN_PASSWORD_LENGTH} characters — "
            "this is the only credential on a publicly reachable app"
        )
    return warnings


def credentials_ok(header: str | None) -> bool:
    """Constant-time Basic Auth check. Both comparisons always run so a valid
    username with a wrong password costs the same as a wrong username."""
    if not header or not header.startswith("Basic "):
        return False
    try:
        username, _, password = base64.b64decode(header[6:]).decode("utf-8").partition(":")
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return False
    user_ok = secrets.compare_digest(username, ADMIN_USERNAME)
    password_ok = secrets.compare_digest(password, ADMIN_PASSWORD)
    return user_ok and password_ok


# ---------------------------------------------------------------------------
# Auth-attempt throttling
# ---------------------------------------------------------------------------
#
# In-process and deliberately so: this app runs as a single machine
# (fly.toml sets min_machines_running = 1, auto_stop_machines = 'off'), and a
# throttle that resets on restart is worth far more than a new dependency or a
# third SQLite file. A restart-clears-the-lockout window is an accepted
# limitation, recorded here rather than hidden.


class Throttle:
    def __init__(self, max_events: int, window_seconds: int, lockout_seconds: int) -> None:
        self._max = max_events
        self._window = window_seconds
        self._lockout = lockout_seconds
        self._events: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def locked(self, key: str, *, now: float | None = None) -> float:
        """Seconds remaining on this key's lockout, 0.0 if not locked."""
        now = time.time() if now is None else now
        with self._lock:
            until = self._locked_until.get(key, 0.0)
            return max(0.0, until - now)

    def record(self, key: str, *, now: float | None = None) -> bool:
        """Count one event against this key. Returns True if it tripped the
        lockout — used both as a failure counter (auth) and as a quota
        counter (claim submissions)."""
        now = time.time() if now is None else now
        with self._lock:
            events = [t for t in self._events.get(key, []) if now - t < self._window]
            events.append(now)
            self._events[key] = events
            if len(events) >= self._max:
                self._locked_until[key] = now + self._lockout
                self._events[key] = []
                return True
            return False

    def clear(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)
            self._locked_until.pop(key, None)


auth_throttle = Throttle(AUTH_MAX_FAILURES, AUTH_WINDOW_SECONDS, AUTH_LOCKOUT_SECONDS)


def client_key(headers: Any, peer: str | None) -> str:
    """Bucket key for throttling and the audit log.

    `Fly-Client-IP` is set by Fly's proxy and overwrites anything the caller
    sends, so it is the true peer address in production. `X-Forwarded-For` is
    deliberately NOT trusted — it is caller-controlled on any host not behind a
    proxy that rewrites it. Off Fly this falls back to the socket peer.

    A spoofed header can only move an attacker between throttle buckets, never
    past one: every limiter that matters here is paired with a global counter
    that no per-caller key can dodge.
    """
    fly_ip = headers.get("fly-client-ip") if hasattr(headers, "get") else None
    return (fly_ip or peer or "unknown").strip()[:64]


# ---------------------------------------------------------------------------
# Request size caps
# ---------------------------------------------------------------------------


def request_byte_cap(path: str, public: bool) -> int:
    return MAX_PUBLIC_REQUEST_BYTES if public else MAX_ADMIN_REQUEST_BYTES


def oversize_reason(content_length: str | None, cap: int, *, public: bool) -> str | None:
    """None if the declared body size is acceptable, else why it isn't.

    An unauthenticated caller must declare Content-Length: every browser does
    for a JSON POST, and refusing an undeclared body is what stops a chunked
    upload from streaming past the cap before any handler sees it. Authenticated
    admin routes are not held to that — the operator is trusted and some of them
    stream.
    """
    if content_length is None or content_length == "":
        return "a Content-Length header is required" if public else None
    try:
        declared = int(content_length)
    except ValueError:
        return "malformed Content-Length"
    if declared < 0:
        return "malformed Content-Length"
    if declared > cap:
        return f"request body exceeds {cap} bytes"
    return None


# ---------------------------------------------------------------------------
# Uploaded-photo validation
# ---------------------------------------------------------------------------
#
# Before Gate 12 the claim photo was decoded with no size cap and stored with a
# file extension taken straight from the caller's Content-Type header. Path
# traversal was already neutralised (the extension is the last '/' segment) but
# nothing bounded the write, and the volume that write lands on is the one
# holding claims.db and articles.db.

_SIGNATURES: tuple[tuple[str, str, tuple[bytes, ...]], ...] = (
    ("image/jpeg", "jpg", (b"\xff\xd8\xff",)),
    ("image/png", "png", (b"\x89PNG\r\n\x1a\n",)),
    ("image/webp", "webp", ()),  # RIFF....WEBP — checked separately, offset 8
)

ALLOWED_PHOTO_TYPES = tuple(entry[0] for entry in _SIGNATURES)


def sniff_photo(data: bytes) -> tuple[str, str] | None:
    """(content_type, extension) from the file's own bytes, or None if the
    bytes are not one of the allowed image formats. The caller's declared
    Content-Type is never what decides how the file is stored."""
    for content_type, ext, prefixes in _SIGNATURES:
        if any(data.startswith(prefix) for prefix in prefixes):
            return content_type, ext
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def decode_photo(b64_data: str, declared_type: str | None) -> tuple[bytes, str, str]:
    """Decode, cap and sniff a submitted claim photo.

    Returns (bytes, content_type, extension) — both derived from the sniffed
    signature, never from `declared_type`, which is only used to reject an
    obviously wrong declaration early. Raises PhotoRejected with a message safe
    to return to an unauthenticated caller.
    """
    if declared_type and declared_type.split(";")[0].strip().lower() not in ALLOWED_PHOTO_TYPES:
        raise PhotoRejected("photo must be a JPEG, PNG or WebP image")
    # base64 inflates by 4/3; refuse before decoding rather than after, so an
    # oversized payload never becomes an oversized buffer.
    if len(b64_data) > (MAX_PHOTO_BYTES * 4 // 3) + 8:
        raise PhotoRejected(f"photo exceeds the {MAX_PHOTO_BYTES // (1024 * 1024)}MB limit")
    try:
        data = base64.b64decode(b64_data, validate=True)
    except (ValueError, binascii.Error):
        raise PhotoRejected("photo data must be valid base64")
    if len(data) > MAX_PHOTO_BYTES:
        raise PhotoRejected(f"photo exceeds the {MAX_PHOTO_BYTES // (1024 * 1024)}MB limit")
    if not data:
        raise PhotoRejected("photo is empty")
    sniffed = sniff_photo(data)
    if sniffed is None:
        raise PhotoRejected("photo must be a JPEG, PNG or WebP image")
    content_type, ext = sniffed
    return data, content_type, ext


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
#
# Append-only JSONL, one line per state-changing request. Gitignored (it
# records requester IPs) and volume-resident, so it survives a `fly deploy` the
# same way claims.db does. It answers the question the previous setup could
# not: who deployed, who published, and when.

_audit_lock = threading.Lock()

# Never recorded, at any level: request bodies (they carry requester PII and
# submitted patches, which claims.db already holds under review), and the
# Authorization header.
AUDIT_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def audit(
    *,
    method: str,
    path: str,
    status: int,
    client: str,
    authenticated: bool,
    note: str = "",
) -> None:
    entry = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "method": method,
        "path": path,
        "status": status,
        "client": client,
        "authenticated": authenticated,
    }
    if note:
        entry["note"] = note
    line = json.dumps(entry, separators=(",", ":"), ensure_ascii=False)
    try:
        with _audit_lock:
            AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with AUDIT_LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except OSError:
        # An unwritable audit log must never take the admin down — the admin is
        # the tool used to fix whatever made it unwritable.
        pass


# ---------------------------------------------------------------------------
# Self-test (Gate 12) — `python3 -m admin.security`
# ---------------------------------------------------------------------------
# Same posture as validate_facts.py / schema_surfaces.py: the module proves its
# own invariants, and /validate runs it. Every check below asserts BOTH that a
# deliberately bad input is rejected and that a good one still passes — a
# hardening check that only ever says "no" is not evidence of anything.


def _self_test() -> int:
    import sys

    failures: list[str] = []

    def check(label: str, condition: bool) -> None:
        if condition:
            print(f"  ok    {label}")
        else:
            failures.append(label)
            print(f"  FAIL  {label}")

    module = sys.modules[__name__]

    print("auth posture:")
    original = (module.ADMIN_USERNAME, module.ADMIN_PASSWORD, module.ADMIN_ALLOW_INSECURE_AUTH)
    try:
        module.ADMIN_USERNAME, module.ADMIN_PASSWORD = "", ""
        module.ADMIN_ALLOW_INSECURE_AUTH = False
        try:
            resolve_auth_posture()
            check("blank credentials refuse to start", False)
        except InsecureConfiguration:
            check("blank credentials refuse to start", True)

        module.ADMIN_ALLOW_INSECURE_AUTH = True
        check("explicit opt-in permits an unauthenticated run", not resolve_auth_posture().enforced)

        module.ADMIN_USERNAME, module.ADMIN_PASSWORD = "owner", "a-long-enough-password"
        module.ADMIN_ALLOW_INSECURE_AUTH = False
        check("credentials present enforce auth", resolve_auth_posture().enforced)

        good = base64.b64encode(b"owner:a-long-enough-password").decode()
        bad = base64.b64encode(b"owner:wrong").decode()
        check("correct credentials accepted", credentials_ok(f"Basic {good}"))
        check("wrong password rejected", not credentials_ok(f"Basic {bad}"))
        check("missing header rejected", not credentials_ok(None))
        check("malformed header rejected", not credentials_ok("Basic !!!not-base64!!!"))
    finally:
        module.ADMIN_USERNAME, module.ADMIN_PASSWORD, module.ADMIN_ALLOW_INSECURE_AUTH = original

    print("photo validation:")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    jpeg = b"\xff\xd8\xff" + b"\x00" * 64
    webp = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 64

    for label, payload, ext in (("PNG", png, "png"), ("JPEG", jpeg, "jpg"), ("WebP", webp, "webp")):
        try:
            _, _, got = decode_photo(base64.b64encode(payload).decode(), None)
            check(f"{label} accepted and sniffed as .{ext}", got == ext)
        except PhotoRejected as exc:
            check(f"{label} accepted and sniffed as .{ext} ({exc})", False)

    def rejects(label: str, b64: str, declared: str | None = None) -> None:
        try:
            decode_photo(b64, declared)
            check(label, False)
        except PhotoRejected:
            check(label, True)

    rejects("a PDF renamed as a PNG is rejected on its bytes",
            base64.b64encode(b"%PDF-1.7\n" + b"\x00" * 64).decode(), "image/png")
    rejects("an HTML payload declared as an image is rejected",
            base64.b64encode(b"<html><script>alert(1)</script>").decode(), "image/jpeg")
    rejects("a disallowed declared type is rejected early",
            base64.b64encode(png).decode(), "image/svg+xml")
    rejects("invalid base64 is rejected", "not base64 at all!!", "image/png")
    rejects("an empty photo is rejected", "", "image/png")
    rejects("an oversized photo is rejected before decoding",
            "A" * ((MAX_PHOTO_BYTES * 4 // 3) + 128), "image/png")

    # The extension can no longer be steered by the caller's header — the whole
    # point of the sniff.
    _, _, ext = decode_photo(base64.b64encode(png).decode(), "image/jpeg")
    check("a mislabelled PNG is stored as .png, not the declared .jpg", ext == "png")

    print("request size caps:")
    check("an oversized public body is refused",
          oversize_reason(str(MAX_PUBLIC_REQUEST_BYTES + 1), MAX_PUBLIC_REQUEST_BYTES, public=True) is not None)
    check("an in-range public body passes",
          oversize_reason("2048", MAX_PUBLIC_REQUEST_BYTES, public=True) is None)
    check("an undeclared public body is refused",
          oversize_reason(None, MAX_PUBLIC_REQUEST_BYTES, public=True) is not None)
    check("an undeclared admin body passes",
          oversize_reason(None, MAX_ADMIN_REQUEST_BYTES, public=False) is None)
    check("a malformed Content-Length is refused",
          oversize_reason("twelve", MAX_PUBLIC_REQUEST_BYTES, public=True) is not None)
    check("a negative Content-Length is refused",
          oversize_reason("-1", MAX_PUBLIC_REQUEST_BYTES, public=True) is not None)

    print("throttling:")
    throttle = Throttle(max_events=3, window_seconds=60, lockout_seconds=60)
    check("under the limit is not locked", throttle.locked("a") == 0)
    tripped = [throttle.record("a") for _ in range(3)]
    check("the limit trips a lockout", tripped[-1] is True)
    check("a locked key stays locked", throttle.locked("a") > 0)
    check("another key is unaffected", throttle.locked("b") == 0)
    throttle.clear("a")
    check("a cleared key is released", throttle.locked("a") == 0)

    stale = Throttle(max_events=2, window_seconds=60, lockout_seconds=60)
    stale.record("c", now=0.0)
    check("an event outside the window does not accumulate", stale.record("c", now=600.0) is False)

    print("client key:")
    check("the Fly-set peer address wins",
          client_key({"fly-client-ip": "203.0.113.7"}, "10.0.0.1") == "203.0.113.7")
    check("a caller-controlled X-Forwarded-For is ignored",
          client_key({"x-forwarded-for": "1.2.3.4"}, "10.0.0.1") == "10.0.0.1")
    check("an unknown peer degrades safely", client_key({}, None) == "unknown")

    print()
    if failures:
        print(f"FAIL — {len(failures)} check(s): {'; '.join(failures)}")
        return 1
    print("PASS — admin/security.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
