"""Deterministic backstop to the LLM fact-checker (Editorial Gate E2, 2026-08-01).

The adversarial fact-check (PROMPTS/factcheck.md, a separate model role) produces
a claim-by-claim table. This module adds an offline, deterministic layer and
assembles the stored report:

  * any hardcoded numeric/currency/temperature figure typed into the prose (i.e.
    a figure NOT injected through a data component) is, by definition, a claim not
    tied to the data — recorded as `unsupported`. Reuses the same scanner the
    build-time check (validate_articles) uses, so the two never disagree.
  * a report is `blocked` if it carries any `unsupported` claim, from either the
    model or this deterministic layer.

Being deterministic and offline, /validate can prove it catches an inserted false
claim without a live model call (the E2 done-condition), the same posture as
comparison_copy.py for lead paragraphs.
"""

from __future__ import annotations

import datetime
from typing import Any

from admin.pipeline.validate_articles import find_hardcoded_numbers

VERDICTS = ("supported", "unsupported", "unverifiable")


def deterministic_findings(body: str) -> list[dict[str, Any]]:
    """Hardcoded figures in prose — each an unsupported claim (a literal not tied
    to the data)."""
    return [
        {
            "claim": hit,
            "verdict": "unsupported",
            "note": "hardcoded figure in prose — must be a data component/token",
            "source": "deterministic",
        }
        for hit in find_hardcoded_numbers(body)
    ]


def report_status(claims: list[dict[str, Any]]) -> tuple[str, int]:
    unsupported = sum(1 for c in claims if c.get("verdict") == "unsupported")
    return ("blocked" if unsupported else "ok"), unsupported


def build_report(
    slug: str,
    query_key: str,
    model: str,
    llm_claims: list[dict[str, Any]],
    body: str,
) -> dict[str, Any]:
    """Combine the model's claim table with the deterministic findings into the
    stored report. The model's claims are tagged source='llm'; malformed
    elements are coerced to a safe unverifiable shape rather than dropped."""
    claims: list[dict[str, Any]] = []
    for c in llm_claims:
        if not isinstance(c, dict):
            continue
        verdict = c.get("verdict")
        claims.append(
            {
                "claim": str(c.get("claim", "")).strip(),
                "verdict": verdict if verdict in VERDICTS else "unverifiable",
                "note": str(c.get("note", "")).strip(),
                "source": "llm",
            }
        )
    claims.extend(deterministic_findings(body))
    status, unsupported = report_status(claims)
    return {
        "slug": slug,
        "query_key": query_key,
        "checked_at": datetime.date.today().isoformat(),
        "model": model,
        "status": status,
        "unsupported_count": unsupported,
        "claims": claims,
    }


def _selftest() -> None:
    # A body with a literal $ figure in prose must be caught deterministically,
    # and the report must block, even if the model returned all-supported.
    body = "The cheapest is <Superlative queryKey=\"cheapest\" /> and costs just $3 flat."
    report = build_report("x", "cheapest", "test-model", [{"claim": "it is calm", "verdict": "supported", "note": ""}], body)
    assert report["status"] == "blocked", report
    assert any(c["source"] == "deterministic" and c["verdict"] == "unsupported" for c in report["claims"]), report
    # A clean body (figures via components only) with a model unsupported claim
    # must also block.
    clean = "The cheapest is <Superlative queryKey=\"cheapest\" />, a simple sauna."
    report2 = build_report("x", "cheapest", "test-model", [{"claim": "it has a rooftop pool", "verdict": "unsupported", "note": "not in data"}], clean)
    assert report2["status"] == "blocked", report2
    # Clean body + all supported/unverifiable => ok.
    report3 = build_report("x", "cheapest", "test-model", [{"claim": "calm", "verdict": "unverifiable", "note": ""}], clean)
    assert report3["status"] == "ok", report3
    print("article_factcheck self-test: pass")


if __name__ == "__main__":
    _selftest()
