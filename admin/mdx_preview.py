"""Renders a staged MDX body to HTML for the review pane's preview iframe.

Not a general MDX/JSX renderer — the Architect/Gatekeeper prompts (PROMPTS/)
only ever produce plain paragraphs and <Pull> pull-quotes in the body (see
architect.md "Structure"), so a full MDX compiler is out of scope for a
review-only preview. <TippedPhoto> is a placeholder here since image
publishing is a separate action (UX.md §4, Gate 4).
"""

from __future__ import annotations

import html
import re

_PULL_RE = re.compile(r"^<Pull>(.*)</Pull>$", re.DOTALL)
_TIPPED_PHOTO_RE = re.compile(r"^<TippedPhoto\b")


def render_body_html(body: str) -> str:
    blocks = re.split(r"\n\s*\n", body.strip())
    parts: list[str] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        pull_match = _PULL_RE.match(block)
        if pull_match:
            inner = html.escape(pull_match.group(1).strip())
            parts.append(
                '<p class="font-display text-2xl italic leading-snug text-[var(--ink)] my-8 max-w-[65ch]" '
                'style="font-weight: 400;">' + inner + "</p>"
            )
            continue
        if _TIPPED_PHOTO_RE.match(block):
            parts.append(
                '<p class="mono text-[var(--ink-faded)]">'
                "[tipped photo — image publishing is a separate reviewer action, not shown here]</p>"
            )
            continue
        parts.append("<p>" + html.escape(block) + "</p>")
    return "\n".join(parts)
