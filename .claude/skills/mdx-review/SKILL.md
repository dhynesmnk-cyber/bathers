---
name: mdx-review
description: Editorial pre-screen for staged venue drafts. Use when asked to review, check, or pre-screen MDX files in content-staging/_staging/ before human review. Advisory only — this skill never approves, moves, or publishes files.
---

# MDX Pre-Screen

Purpose: catch mechanical and register problems before the human review session, so the human spends their attention on judgment calls, not typos. **Never move, approve, or edit staged files under this skill — output findings only.** Approval is a human action through the admin UI, always.

For each staged file, check and report:

## Mechanical (blocking — flag as MUST FIX)
1. Frontmatter validates against SCHEMA.md §2 (all required fields, types, enums, AU bounds, summary ≤160, strict amenity object).
2. Slug/filename kebab-case, no collision with `_published`.
3. `<Pull>` tags balanced, 1–2 of them, their sentences reading naturally in flow.
4. Every number/price/temperature in the body traceable to the venue's harvested JSON in `temp_data/` (if the JSON is still present). Untraceable specifics are fabrication — always MUST FIX.
5. Any first-person visit claim or on-site sensory claim ("we visited", "you can smell") — MUST FIX.

## Editorial (advisory — flag as CONSIDER)
6. Banned-word hits (list in PROMPTS/gatekeeper.md) that survived the Gatekeeper.
7. Register drift: sentences that would sit comfortably on the venue's own website; exclamation marks; imperatives; rhetorical questions; padding sentences with no fact or image.
8. Australian English slips (-ize, -or, vacation, imperial units).
9. Opening line — does it lead with the most characteristic true thing, or with throat-clearing?
10. Length sanity: under ~300 words suggests thin facts (fine if the facts genuinely are thin); over ~750 suggests padding.

## Output format
One block per file: filename, verdict (`CLEAN` / `FIXES NEEDED` / `REVIEW CAREFULLY`), then findings as numbered lines with the exact quoted text and line number. End with a one-line queue summary. No rewrites unless explicitly asked — findings only.
