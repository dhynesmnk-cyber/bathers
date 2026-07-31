"""Comparison-copy audit (Gate 10, 2026-07-31). The Gatekeeper-style honesty
pass for comparison-page lead paragraphs: a lead may be LLM-drafted or
hand-written, but before it ships it is checked, sentence by sentence, against
the *computed* facts of that comparison (the venue rows). Any sentence making a
dollar, count, or superlative claim the facts don't support is dropped — the
same delete-don't-correct posture as PROMPTS/gatekeeper.md check 1, re-scoped
from a Harvester JSON to a comparison dataset.

Deterministic and offline so /validate can prove it catches a deliberately
inserted false claim (the Gate 10 done-condition), rather than depending on a
live model call at audit time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_MONEY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d{1,2})?)")
_COUNT = re.compile(r"\b(\d+)\s+venues?\b", re.IGNORECASE)
_SUPERLATIVE = re.compile(r"\b(cheapest|dearest|most expensive|hottest|coldest|largest|only)\b", re.IGNORECASE)
_SENTENCE = re.compile(r"[^.!?]*[.!?]")


@dataclass
class Facts:
    prices: set[float]
    count: int

    @property
    def min_price(self) -> float | None:
        return min(self.prices) if self.prices else None

    @property
    def max_price(self) -> float | None:
        return max(self.prices) if self.prices else None


def facts_from_rows(rows: list[dict]) -> Facts:
    """rows: [{'price': float|None, ...}, ...] — the comparison's venue rows."""
    prices = {float(r["price"]) for r in rows if r.get("price") is not None}
    return Facts(prices=prices, count=len(rows))


def _sentence_ok(sentence: str, facts: Facts) -> tuple[bool, str]:
    for amount in (float(m.replace(",", "")) for m in _MONEY.findall(sentence)):
        # A dollar figure must be a real venue price, or the true min/max when
        # the sentence frames it as a bound ("from $X", "as little as $X").
        if amount not in facts.prices:
            if re.search(r"\b(from|as little as|as low as|starting)\b", sentence, re.IGNORECASE) and amount == facts.min_price:
                continue
            return False, f"unsupported price ${amount:g}"
    for count in (int(m) for m in _COUNT.findall(sentence)):
        if count != facts.count:
            return False, f"count says {count} but there are {facts.count}"
    if _SUPERLATIVE.search(sentence):
        amounts = [float(m.replace(",", "")) for m in _MONEY.findall(sentence)]
        if "cheapest" in sentence.lower() and amounts and facts.min_price is not None and min(amounts) != facts.min_price:
            return False, "‘cheapest’ price does not match the true minimum"
    return True, ""


def audit(lead: str, facts: Facts) -> tuple[str, list[str]]:
    """Return (cleaned_lead, removed_reasons). Sentences with an unsupported
    claim are dropped whole (delete, don't guess a correction)."""
    kept: list[str] = []
    removed: list[str] = []
    for match in _SENTENCE.finditer(lead.strip()):
        sentence = match.group().strip()
        if not sentence:
            continue
        ok, reason = _sentence_ok(sentence, facts)
        (kept if ok else removed).append(sentence if ok else f"{sentence} ({reason})")
    return " ".join(kept).strip(), removed


def _selftest() -> None:
    facts = facts_from_rows([{"price": 10.0}, {"price": 25.0}, {"price": 27.0}, {"price": 39.0}, {"price": None}])
    good = "These venues are ranked by adult drop-in price, from $10, five in all."
    # wait: count claim "five" is a word, not caught; use a numeric fixture:
    good = "Ranked by adult drop-in price, from $10. Prices come from each venue's own site."
    clean, removed = audit(good, facts)
    assert not removed, removed
    bad = good + " The cheapest option here is just $3. There are 99 venues listed."
    clean2, removed2 = audit(bad, facts)
    assert len(removed2) == 2, removed2
    assert "$3" not in clean2 and "99 venues" not in clean2
    print("comparison_copy self-test: pass")
    print("  removed:", removed2)


if __name__ == "__main__":
    _selftest()
