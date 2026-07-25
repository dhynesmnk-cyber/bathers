"""Stripe integration via raw httpx REST calls (TRD.md §8, 2026-07-25
exception) — explicitly not the `stripe` pip package, consistent with this
project's existing no-SDK pattern (no python-dotenv, no python-multipart).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import httpx

from admin.config import STRIPE_SECRET_KEY

_BASE = "https://api.stripe.com/v1"
_TIMEOUT = 20.0


class StripeError(Exception):
    pass


class SignatureVerificationError(StripeError):
    pass


def _auth() -> tuple[str, str]:
    return (STRIPE_SECRET_KEY, "")


def create_checkout_session(
    *,
    price_id: str,
    mode: str,
    customer_email: str,
    success_url: str,
    cancel_url: str,
    metadata: dict[str, str],
) -> dict[str, Any]:
    """POST /v1/checkout/sessions. Stripe's REST API is form-encoded, not
    JSON; auth is HTTP Basic with the secret key as username, blank
    password, same as Stripe's own curl examples."""
    data = {
        "mode": mode,
        "line_items[0][price]": price_id,
        "line_items[0][quantity]": "1",
        "customer_email": customer_email,
        "success_url": success_url,
        "cancel_url": cancel_url,
        **{f"metadata[{k}]": v for k, v in metadata.items()},
    }
    response = httpx.post(f"{_BASE}/checkout/sessions", data=data, auth=_auth(), timeout=_TIMEOUT)
    if response.status_code >= 400:
        raise StripeError(f"create_checkout_session failed ({response.status_code}): {response.text}")
    return response.json()


def verify_webhook_signature(payload: bytes, sig_header: str, secret: str, tolerance: int = 300) -> dict[str, Any]:
    """Verifies Stripe's documented `t=...,v1=...` HMAC-SHA256 scheme over
    the raw request body. Raises SignatureVerificationError on any
    mismatch, staleness, or malformed header; returns the parsed event on
    success."""
    if not sig_header:
        raise SignatureVerificationError("missing Stripe-Signature header")

    pairs: dict[str, list[str]] = {}
    for item in sig_header.split(","):
        key, _, value = item.partition("=")
        pairs.setdefault(key.strip(), []).append(value.strip())

    timestamps = pairs.get("t")
    signatures = pairs.get("v1")
    if not timestamps or not signatures:
        raise SignatureVerificationError("malformed Stripe-Signature header")

    timestamp = timestamps[0]
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()

    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise SignatureVerificationError("signature mismatch")

    if abs(time.time() - int(timestamp)) > tolerance:
        raise SignatureVerificationError("timestamp outside tolerance")

    return json.loads(payload)


def find_active_subscription_by_email(email: str) -> dict[str, str] | None:
    """Live lookup, no local caching: resolve customer id(s) by exact email
    match, then check each for an active subscription on the unlimited-
    changes price. Returns {"customer_id", "subscription_id"} on the first
    match, else None."""
    customers_resp = httpx.get(
        f"{_BASE}/customers", params={"email": email}, auth=_auth(), timeout=_TIMEOUT
    )
    if customers_resp.status_code >= 400:
        raise StripeError(f"customer lookup failed ({customers_resp.status_code}): {customers_resp.text}")

    from admin.config import STRIPE_PRICE_SUBSCRIPTION

    for customer in customers_resp.json().get("data", []):
        subs_resp = httpx.get(
            f"{_BASE}/subscriptions",
            params={"customer": customer["id"], "status": "active", "price": STRIPE_PRICE_SUBSCRIPTION},
            auth=_auth(),
            timeout=_TIMEOUT,
        )
        if subs_resp.status_code >= 400:
            raise StripeError(f"subscription lookup failed ({subs_resp.status_code}): {subs_resp.text}")
        subs = subs_resp.json().get("data", [])
        if subs:
            return {"customer_id": customer["id"], "subscription_id": subs[0]["id"]}
    return None
