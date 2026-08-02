"""Comparison-article pipeline: draft -> adversarial fact-check (Editorial Gate
E2, 2026-08-01). Mirrors orchestrator.py: a synchronous generator yielding one
LogLine per step so the admin log pane stays truthful (UX.md §1.1), drained by
the caller to stream (SSE) or collect (CLI).

Unlike the venue harvest pipeline there is no scrape. The venue set is resolved
by the site's own TypeScript selection (comparisons.ts) and read back from the
committed articles-meta.json + venues.json — the Python side never re-implements
"who wins". Two agents run, deliberately distinct roles:

  1. MODEL_ARTICLE drafts the voiced MDX (figures as data components, never
     literals — enforced by the no-hardcoded-number validator on its output).
  2. MODEL_FACTCHECK audits that draft against the venue records and returns a
     claim table; article_factcheck adds a deterministic layer and decides
     whether the report blocks publication.

Output lands in content-staging/_article_staging/<slug>.mdx plus its
<slug>.factcheck.json — never in _published (that is the approve action's job,
CLAUDE.md rule 5).
"""

from __future__ import annotations

import datetime
import json
import re
from dataclasses import dataclass
from typing import Any, Iterator

import yaml

from admin.config import (
    ARTICLE_STAGING_DIR,
    ARTICLES_META_JSON_PATH,
    BLOG_PUBLISHED_DIR,
    FACTCHECKS_DIR,
    FAILED_DIR,
    MODEL_ARTICLE,
    MODEL_BRIEF,
    MODEL_ESSAY,
    MODEL_ESSAY_CHECK,
    MODEL_FACTCHECK,
    VENUES_JSON_PATH,
)
from admin.pipeline import agents, article_db, article_factcheck
from admin.pipeline.validate_articles import find_hardcoded_numbers, register_issues

# The venue-record fields the agents may reason from (everything a comparison can
# surface). Kept explicit so the drafting/fact-check context is stable.
_RECORD_FIELDS = (
    "slug", "name", "suburb", "state", "category", "price", "temperatures",
    "amenities", "facilities", "hours", "cost", "dress_code", "session_gender",
    "session_gender_note", "silence_policy", "phone_policy", "minimum_age",
)

# The lighter roster an essay is grounded on: the only real venues it may name, and
# the only facts about them it may state. Deliberately narrow — an essay is prose,
# not a data table, so it gets identity + location + kind, nothing to recite.
_ROSTER_FIELDS = ("name", "suburb", "state", "category")

_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n(.*)\n```$", re.DOTALL)


@dataclass
class LogLine:
    time: str
    level: str
    text: str


@dataclass
class ArticleOutcome:
    ok: bool
    slug: str | None = None
    status: str | None = None  # "ok" | "blocked"
    unsupported_count: int = 0


def _now() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def _strip_code_fence(text: str) -> str:
    match = _FENCE_RE.match(text.strip())
    return match.group(1).strip() if match else text.strip()


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        raise ValueError("missing frontmatter delimiter")
    _, fm_yaml, body = text.split("---", 2)
    data = yaml.safe_load(fm_yaml) or {}
    if not isinstance(data, dict):
        raise ValueError("frontmatter is not a mapping")
    return data, body.strip("\n")


def _clean_register(text: str) -> str:
    """Deterministic, meaning-preserving register fixes so the two content-tier
    retries are spent on substance (hardcoded figures), not cosmetics: em dashes
    and their `--` substitute become house commas, and the banned "rather than"
    contrast construction becomes the unbanned "instead of". Mirrors restyle.py's
    dedash posture for venue prose; anything not safely mechanical (a "not just"
    construction, a first-person claim) is still re-asked, not silently rewritten."""
    text = re.sub(r"\s*—\s*", ", ", text)
    text = re.sub(r"(?<=\w)\s*--\s*(?=\w)", ", ", text)
    text = re.sub(r"\brather than\b", "instead of", text, flags=re.IGNORECASE)
    return text


def _validate_draft(text: str) -> tuple[dict[str, Any], str]:
    text = _strip_code_fence(text)
    data, body = _split_frontmatter(text)
    body = _clean_register(body)
    if not data.get("title"):
        raise ValueError("frontmatter has no title")
    summary = data.get("summary")
    if not summary:
        raise ValueError("frontmatter has no summary")
    if len(str(summary)) > 160:
        raise ValueError(f"summary is {len(str(summary))} chars (max 160)")
    if not body.strip():
        raise ValueError("body is empty")
    if "<ComparisonTable" not in body or "<ExtractiveAnswer" not in body:
        raise ValueError("body must include <ExtractiveAnswer> and <ComparisonTable>")
    hits = find_hardcoded_numbers(body)
    if hits:
        raise ValueError(
            "figures must be data components, not literals — offending prose: " + "; ".join(hits[:3])
        )
    reg = register_issues(body)
    if reg:
        raise ValueError("house-register violations — fix these: " + "; ".join(reg[:3]))
    return data, body


def _validate_factcheck(text: str) -> list[dict[str, Any]]:
    text = _strip_code_fence(text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON — {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("fact-check output must be a JSON array")
    return data


def _load_meta() -> dict[str, Any]:
    return json.loads(ARTICLES_META_JSON_PATH.read_text(encoding="utf-8"))


def _resolved_records(order: list[str]) -> list[dict[str, Any]]:
    venues = {v["slug"]: v for v in json.loads(VENUES_JSON_PATH.read_text(encoding="utf-8"))}
    records = []
    for slug in order:
        v = venues.get(slug)
        if v:
            records.append({k: v[k] for k in _RECORD_FIELDS if k in v})
    return records


def _venue_roster() -> list[dict[str, Any]]:
    """Every published venue trimmed to _ROSTER_FIELDS — the only real venues an
    essay may name, and the only facts about them it may state. Read straight from
    the committed venues.json (no scrape, no comparison selection)."""
    venues = json.loads(VENUES_JSON_PATH.read_text(encoding="utf-8"))
    return [{k: v[k] for k in _ROSTER_FIELDS if k in v} for v in venues]


def _save_failed(stage: str, slug: str, raw_text: str, log) -> None:
    FAILED_DIR.mkdir(parents=True, exist_ok=True)
    path = FAILED_DIR / f"article-{stage}-{slug}.txt"
    path.write_text(raw_text, encoding="utf-8")
    log(f"saved raw {stage} output to {path.relative_to(FAILED_DIR.parent.parent)}", "warn")


def _draft_system(prompt_file: str) -> str:
    """Compose a drafter's structural prompt with the shared HOUSE VOICE spec, so
    tone, the artistic subtext, the banned vocabulary and the Australian-English
    rules live in one file (PROMPTS/house_voice.md) across every article and essay
    drafter. Checkers (factcheck.md, essay_check.md) and the internal brief are not
    composed with it — they classify or plan, they don't write published prose."""
    return agents.load_prompt(prompt_file) + "\n\n" + agents.load_prompt("house_voice.md")


def run(query_key: str, slug: str, author: str | None = None) -> Iterator[LogLine]:
    lines: list[LogLine] = []

    def log(text: str, level: str = "info") -> None:
        lines.append(LogLine(_now(), level, text))

    def drain() -> Iterator[LogLine]:
        nonlocal lines
        out, lines = lines, []
        yield from out

    slug = re.sub(r"[^a-z0-9-]", "", slug.lower())
    log(f"article '{slug}' from comparison '{query_key}'")
    yield from drain()

    # 1. Resolve the venue set from the committed metadata (the TS selection).
    try:
        meta = _load_meta()
    except FileNotFoundError:
        log("articles-meta.json missing — run article_store --rebuild first", "error")
        yield from drain()
        return
    entry = meta.get(query_key)
    if not entry:
        log(f"unknown comparison '{query_key}' or below the 5-venue threshold — nothing to write", "error")
        yield from drain()
        return

    # Brief gate (Editorial Gate E4a): no drafting spend unless this intent is
    # draftable — an approved brief, not dismissed from the queue (the same
    # predicate the admin surfaces). Published articles predate the gate and are
    # never re-drafted (the slug-exists guard below), so nothing to grandfather.
    if query_key not in article_db.draftable_keys():
        disp = article_db.dispositions().get(query_key)
        if disp and disp["disposition"] == "dismissed":
            reason = "it is dismissed from the queue — restore it first"
        else:
            existing = article_db.latest_brief(query_key)
            reason = f"no approved brief (brief: {existing['status'] if existing else 'none'}) — brief and approve it first"
        log(f"cannot draft '{query_key}': {reason} (brief gate)", "error")
        yield from drain()
        return

    if (BLOG_PUBLISHED_DIR / f"{slug}.mdx").exists() or (ARTICLE_STAGING_DIR / f"{slug}.mdx").exists():
        log(f"slug '{slug}' already exists (staging or published) — pick another", "error")
        yield from drain()
        return

    records = _resolved_records(entry["current"]["order"])
    log(f"resolved {len(records)} venues; ranking: {entry['title']}")
    yield from drain()

    facts_pack = json.dumps(
        {"query_key": query_key, "title": entry["title"], "caption": entry["caption"], "venues": records},
        ensure_ascii=False,
        indent=2,
    )

    # 2. Draft.
    log(f"drafting with {MODEL_ARTICLE}")
    yield from drain()
    draft_user = (
        f"Write the comparison article for this data. Use the query_key '{query_key}' in every "
        f"component. The venue records are the only facts you may use.\n\n{facts_pack}"
    )
    try:
        (fm, body), usage = agents.call_agent(
            MODEL_ARTICLE, _draft_system("article_draft.md"), draft_user, 3000, _validate_draft, log
        )
    except agents.MalformedOutput as exc:
        _save_failed("draft", slug, exc.raw_text, log)
        log("draft failed validation after retry — stopping", "error")
        yield from drain()
        return
    except agents.AgentError as exc:
        log(f"draft call failed — {exc}", "error")
        yield from drain()
        return
    log(f"drafted '{fm['title']}' ({usage.input_tokens} in / {usage.output_tokens} out tokens)")
    yield from drain()

    # 3. Adversarial fact-check (a distinct role, never the drafter on itself).
    log(f"fact-checking with {MODEL_FACTCHECK}")
    yield from drain()
    fc_user = (
        "Audit this article body against the venue records. Return the JSON claim table only.\n\n"
        f"--- ARTICLE BODY ---\n{body}\n\n--- VENUE RECORDS ---\n{facts_pack}"
    )
    try:
        llm_claims, fc_usage = agents.call_agent(
            MODEL_FACTCHECK, agents.load_prompt("factcheck.md"), fc_user, 2000, _validate_factcheck, log
        )
    except agents.MalformedOutput as exc:
        _save_failed("factcheck", slug, exc.raw_text, log)
        log("fact-check failed validation after retry — stopping", "error")
        yield from drain()
        return
    except agents.AgentError as exc:
        log(f"fact-check call failed — {exc}", "error")
        yield from drain()
        return

    report = article_factcheck.build_report(slug, query_key, MODEL_FACTCHECK, llm_claims, body)
    log(
        f"fact-check: {len(report['claims'])} claim(s), {report['unsupported_count']} unsupported "
        f"({fc_usage.input_tokens} in / {fc_usage.output_tokens} out tokens)"
    )
    yield from drain()

    # 4. Stamp deterministic frontmatter + write staging artifacts.
    fm["query_key"] = query_key
    fm["dateline"] = datetime.date.today()
    fm["reviewed_at"] = datetime.date.today()
    if author:
        fm["author"] = author
    ARTICLE_STAGING_DIR.mkdir(parents=True, exist_ok=True)
    (ARTICLE_STAGING_DIR / f"{slug}.mdx").write_text(_render_mdx(fm, body), encoding="utf-8")
    (ARTICLE_STAGING_DIR / f"{slug}.factcheck.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if report["status"] == "blocked":
        log(
            f"staged '{slug}' but BLOCKED for review: {report['unsupported_count']} unsupported claim(s) "
            "must be resolved before it can be approved",
            "error",
        )
    else:
        log(f"staged '{slug}' — fact-check clean, ready for review")
    yield from drain()


def _validate_brief(text: str) -> str:
    """A brief must be substantive and end on a clear write/skip recommendation
    so the editor gets an unambiguous signal at the gate."""
    text = _strip_code_fence(text).strip()
    if len(text) < 80:
        raise ValueError("brief is too short to be a useful plan")
    if not re.search(r"^##\s*Recommendation:\s*(write|skip)\b", text, re.IGNORECASE | re.MULTILINE):
        raise ValueError("brief must end with a '## Recommendation:' line resolving to 'write' or 'skip'")
    return text


def brief(query_key: str) -> Iterator[LogLine]:
    """Auto-draft an editorial brief for an opportunity and store it pending in
    articles.db (Editorial Gate E4a). A human approves or kills it before any
    drafting spend — the brief gate. Streams LogLines like run(); does not draft."""
    lines: list[LogLine] = []

    def log(text: str, level: str = "info") -> None:
        lines.append(LogLine(_now(), level, text))

    def drain() -> Iterator[LogLine]:
        nonlocal lines
        out, lines = lines, []
        yield from out

    try:
        meta = _load_meta()
    except FileNotFoundError:
        log("articles-meta.json missing — run article_store --rebuild first", "error")
        yield from drain()
        return
    entry = meta.get(query_key)
    if not entry:
        log(f"unknown comparison '{query_key}' or below the 5-venue threshold — nothing to brief", "error")
        yield from drain()
        return

    records = _resolved_records(entry["current"]["order"])
    log(f"briefing '{entry['title']}' ({len(records)} venues) with {MODEL_BRIEF}")
    yield from drain()

    facts_pack = json.dumps(
        {"query_key": query_key, "title": entry["title"], "caption": entry["caption"],
         "kind": entry.get("kind"), "venues": records},
        ensure_ascii=False, indent=2,
    )
    user = (
        "Write the editorial brief for this proposed comparison article. The venue "
        f"records are the only facts you may reason from.\n\n{facts_pack}"
    )
    try:
        brief_md, usage = agents.call_agent(
            MODEL_BRIEF, agents.load_prompt("article_brief.md"), user, 1200, _validate_brief, log
        )
    except agents.MalformedOutput as exc:
        _save_failed("brief", query_key, exc.raw_text, log)
        log("brief failed validation after retry — stopping", "error")
        yield from drain()
        return
    except agents.AgentError as exc:
        log(f"brief call failed — {exc}", "error")
        yield from drain()
        return

    stored = article_db.create_brief(query_key, brief_md, title=entry.get("title"), model=MODEL_BRIEF)
    log(
        f"brief #{stored['id']} stored pending for '{query_key}' — approve or kill it before drafting "
        f"({usage.input_tokens} in / {usage.output_tokens} out tokens)"
    )
    yield from drain()


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(title: str) -> str:
    """Slug from a comparison title, made unique against the published (/blog/)
    and article-staging sets so the collapsed write flow doesn't collide."""
    base = _SLUG_RE.sub("-", title.strip().lower()).strip("-") or "article"
    slug = base
    n = 2
    while (BLOG_PUBLISHED_DIR / f"{slug}.mdx").exists() or (ARTICLE_STAGING_DIR / f"{slug}.mdx").exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def write(query_key: str, author: str | None = None) -> Iterator[LogLine]:
    """Collapsed 'write about X' flow (2026-08-01 admin-UX change): brief ->
    auto-approve the brief -> draft -> fact-check, streamed as one job, landing
    the draft in _article_staging for the unchanged human publish gate. The brief
    is still generated and stored as the editorial record; only its approval is
    automatic (the operator's editorial direction is the topic they chose). The
    fact-check block and the human Approve & publish step are NOT bypassed."""

    def log(text: str, level: str = "info") -> LogLine:
        return LogLine(_now(), level, text)

    before = article_db.latest_brief(query_key)
    before_id = before["id"] if before else None

    # brief() streams its own log lines and stores a pending brief on success.
    yield from brief(query_key)

    latest = article_db.latest_brief(query_key)
    if latest is None or latest["id"] == before_id:
        yield log("brief step produced no new brief — stopping before drafting", "error")
        return

    article_db.decide_brief(latest["id"], "approved", decided_by="auto — collapsed write flow")
    yield log(f"brief #{latest['id']} auto-approved (collapsed write flow)")

    try:
        meta = _load_meta()
    except FileNotFoundError:
        yield log("articles-meta.json missing — run article_store --rebuild first", "error")
        return
    entry = meta.get(query_key) or {}
    slug = _slugify(entry.get("title") or query_key)

    # run()'s own slug-exists and validation guards still apply from here.
    yield from run(query_key, slug, author)


def _validate_essay_draft(text: str) -> tuple[dict[str, Any], str]:
    """Essay draft validation: like _validate_draft but without the data-component
    discipline (an essay binds no live figures, so general prose numbers such as
    "a 40-degree bath" are legitimate). Still enforces frontmatter, at least one
    section heading (GEO structure), and the house register."""
    text = _strip_code_fence(text)
    data, body = _split_frontmatter(text)
    body = _clean_register(body)
    if not data.get("title"):
        raise ValueError("frontmatter has no title")
    summary = data.get("summary")
    if not summary:
        raise ValueError("frontmatter has no summary")
    if len(str(summary)) > 160:
        raise ValueError(f"summary is {len(str(summary))} chars (max 160)")
    if not body.strip():
        raise ValueError("body is empty")
    if "## " not in body:
        raise ValueError("essay needs at least one '##' section heading")
    if "query_key" in data:
        raise ValueError("an essay must not set query_key (that is a comparison article)")
    reg = register_issues(body)
    if reg:
        raise ValueError("house-register violations — fix these: " + "; ".join(reg[:3]))
    return data, body


def essay(topic: str, author: str | None = None) -> Iterator[LogLine]:
    """Free-form essay flow (2026-08-01): draft a voiced blog essay on a typed
    topic in the house style, then run a *separate* integrity check that flags
    first-person visit claims, invented venue facts and named cultural references
    for the human. No query_key and no live table — the piece stages beside the
    comparison drafts and publishes into the blog collection as a plain essay. The
    human publish gate (reading the report, then Approve & publish) is unchanged."""
    lines: list[LogLine] = []

    def log(text: str, level: str = "info") -> None:
        lines.append(LogLine(_now(), level, text))

    def drain() -> Iterator[LogLine]:
        nonlocal lines
        out, lines = lines, []
        yield from out

    topic = topic.strip()
    if not topic:
        log("no topic given for the essay", "error")
        yield from drain()
        return
    log(f"essay on '{topic}'")
    yield from drain()

    try:
        roster = _venue_roster()
    except FileNotFoundError:
        log("venues.json missing — rebuild the data store first", "error")
        yield from drain()
        return
    log(f"grounding on {len(roster)} published venues (name/suburb/state/category only)")
    yield from drain()
    roster_pack = json.dumps({"topic": topic, "venues": roster}, ensure_ascii=False, indent=2)

    # 1. Draft.
    log(f"drafting with {MODEL_ESSAY}")
    yield from drain()
    draft_user = (
        f"Write the essay on this topic: {topic}\n\n"
        "You may name only the venues in this roster, and only the plain facts given. "
        "Do not invent venues or figures.\n\n"
        f"{roster_pack}"
    )
    try:
        (fm, body), usage = agents.call_agent(
            MODEL_ESSAY, _draft_system("essay_draft.md"), draft_user, 2500, _validate_essay_draft, log
        )
    except agents.MalformedOutput as exc:
        _save_failed("essay-draft", _slugify(topic), exc.raw_text, log)
        log("essay draft failed validation after retry — stopping", "error")
        yield from drain()
        return
    except agents.AgentError as exc:
        log(f"essay draft call failed — {exc}", "error")
        yield from drain()
        return
    slug = _slugify(fm["title"])
    log(f"drafted '{fm['title']}' -> {slug} ({usage.input_tokens} in / {usage.output_tokens} out tokens)")
    yield from drain()

    # 2. Integrity check (a distinct role — visit claims, invented facts, named refs).
    log(f"integrity check with {MODEL_ESSAY_CHECK}")
    yield from drain()
    check_user = (
        "Audit this essay body. Return the JSON claim table only.\n\n"
        f"--- ESSAY BODY ---\n{body}\n\n"
        f"--- VENUE ROSTER (the only real venues + facts) ---\n{roster_pack}"
    )
    try:
        llm_claims, fc_usage = agents.call_agent(
            MODEL_ESSAY_CHECK, agents.load_prompt("essay_check.md"), check_user, 2000, _validate_factcheck, log
        )
    except agents.MalformedOutput as exc:
        _save_failed("essay-check", slug, exc.raw_text, log)
        log("integrity check failed validation after retry — stopping", "error")
        yield from drain()
        return
    except agents.AgentError as exc:
        log(f"integrity check call failed — {exc}", "error")
        yield from drain()
        return

    report = article_factcheck.build_report(
        slug, None, MODEL_ESSAY_CHECK, llm_claims, body,
        deterministic=article_factcheck.register_findings,
    )
    # The essay_check prompt notes a real reference with the exact prefix "named
    # cultural reference — …"; match the prefix so a note that *denies* one ("no
    # named cultural reference to surface") isn't miscounted.
    named = sum(1 for c in report["claims"] if c.get("note", "").lower().lstrip().startswith("named cultural reference"))
    log(
        f"integrity: {len(report['claims'])} claim(s), {report['unsupported_count']} to resolve"
        + (f", {named} named reference(s) to verify" if named else "")
        + f" ({fc_usage.input_tokens} in / {fc_usage.output_tokens} out tokens)"
    )
    yield from drain()

    # 3. Stamp deterministic frontmatter (no query_key, no reviewed_at) + write.
    fm["dateline"] = datetime.date.today()
    if author:
        fm["author"] = author
    ARTICLE_STAGING_DIR.mkdir(parents=True, exist_ok=True)
    (ARTICLE_STAGING_DIR / f"{slug}.mdx").write_text(_render_mdx(fm, body), encoding="utf-8")
    (ARTICLE_STAGING_DIR / f"{slug}.factcheck.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if report["status"] == "blocked":
        log(
            f"staged essay '{slug}' but BLOCKED for review: {report['unsupported_count']} claim(s) "
            "must be resolved before it can be approved",
            "error",
        )
    else:
        log(f"staged essay '{slug}' — integrity clean, ready for review")
    yield from drain()


def factcheck_existing(slug: str) -> Iterator[LogLine]:
    """Fact-check an already-published comparison article against the current
    venue data and write/refresh its stored report (data/factchecks/<slug>.json).
    Used to give a hand-placed article a report, and as the Stage 8 post-publish
    re-verification trigger. Does not modify the article prose."""
    lines: list[LogLine] = []

    def log(text: str, level: str = "info") -> None:
        lines.append(LogLine(_now(), level, text))

    def drain() -> Iterator[LogLine]:
        nonlocal lines
        out, lines = lines, []
        yield from out

    path = BLOG_PUBLISHED_DIR / f"{slug}.mdx"
    if not path.exists():
        log(f"no published article '{slug}'", "error")
        yield from drain()
        return
    fm, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    query_key = fm.get("query_key")
    if not query_key:
        log(f"'{slug}' is an essay (no query_key) — nothing to fact-check", "error")
        yield from drain()
        return
    entry = _load_meta().get(query_key)
    if not entry:
        log(f"comparison '{query_key}' is no longer eligible", "error")
        yield from drain()
        return
    records = _resolved_records(entry["current"]["order"])
    facts_pack = json.dumps(
        {"query_key": query_key, "title": entry["title"], "caption": entry["caption"], "venues": records},
        ensure_ascii=False, indent=2,
    )
    log(f"re-fact-checking '{slug}' with {MODEL_FACTCHECK}")
    yield from drain()
    fc_user = (
        "Audit this article body against the venue records. Return the JSON claim table only.\n\n"
        f"--- ARTICLE BODY ---\n{body}\n\n--- VENUE RECORDS ---\n{facts_pack}"
    )
    try:
        llm_claims, _ = agents.call_agent(
            MODEL_FACTCHECK, agents.load_prompt("factcheck.md"), fc_user, 2000, _validate_factcheck, log
        )
    except (agents.MalformedOutput, agents.AgentError) as exc:
        log(f"fact-check failed — {exc}", "error")
        yield from drain()
        return
    report = article_factcheck.build_report(slug, query_key, MODEL_FACTCHECK, llm_claims, body)
    FACTCHECKS_DIR.mkdir(parents=True, exist_ok=True)
    FACTCHECKS_DIR.joinpath(f"{slug}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    level = "error" if report["status"] == "blocked" else "info"
    log(f"report written: {report['status']} ({report['unsupported_count']} unsupported)", level)
    yield from drain()


def refactcheck(slug: str) -> Iterator[LogLine]:
    """Re-fact-check a slug wherever it lives. A staged draft (the review-pane
    Re-fact-check button) rewrites its staging sidecar report; a published article
    (the Published list's Re-verify) rewrites its committed factchecks record.
    Dispatch is staging-first — approve/unpublish keep a slug out of both at once."""
    if (ARTICLE_STAGING_DIR / f"{slug}.mdx").exists():
        yield from factcheck_staged(slug)
    else:
        yield from factcheck_existing(slug)


def factcheck_staged(slug: str) -> Iterator[LogLine]:
    """Re-run the fact-check on a *staged* draft and rewrite its staging sidecar
    report (content-staging/_article_staging/<slug>.factcheck.json) — the record the
    review screen and the approve gate read. This is how an operator clears a
    blocked draft after editing: an LLM-flagged unsupported claim only clears on a
    fresh full check (a body edit alone re-runs the deterministic layer only,
    keeping LLM claims). Handles both a comparison draft (query_key, audited against
    the venue records) and an essay (no query_key, integrity-checked against the
    roster) — the same two roles as generation. Does not modify the prose."""
    lines: list[LogLine] = []

    def log(text: str, level: str = "info") -> None:
        lines.append(LogLine(_now(), level, text))

    def drain() -> Iterator[LogLine]:
        nonlocal lines
        out, lines = lines, []
        yield from out

    path = ARTICLE_STAGING_DIR / f"{slug}.mdx"
    if not path.exists():
        log(f"no staged article '{slug}'", "error")
        yield from drain()
        return
    fm, body = _split_frontmatter(path.read_text(encoding="utf-8"))
    query_key = fm.get("query_key")

    if not query_key:
        # Essay: integrity-check against the roster (register/visit deterministic
        # layer), the same stage as essay generation.
        try:
            roster = _venue_roster()
        except FileNotFoundError:
            log("venues.json missing — rebuild the data store first", "error")
            yield from drain()
            return
        roster_pack = json.dumps(
            {"topic": fm.get("title", slug), "venues": roster}, ensure_ascii=False, indent=2
        )
        log(f"re-checking essay '{slug}' with {MODEL_ESSAY_CHECK}")
        yield from drain()
        check_user = (
            "Audit this essay body. Return the JSON claim table only.\n\n"
            f"--- ESSAY BODY ---\n{body}\n\n"
            f"--- VENUE ROSTER (the only real venues + facts) ---\n{roster_pack}"
        )
        try:
            llm_claims, _ = agents.call_agent(
                MODEL_ESSAY_CHECK, agents.load_prompt("essay_check.md"), check_user, 2000, _validate_factcheck, log
            )
        except (agents.MalformedOutput, agents.AgentError) as exc:
            log(f"integrity check failed — {exc}", "error")
            yield from drain()
            return
        report = article_factcheck.build_report(
            slug, None, MODEL_ESSAY_CHECK, llm_claims, body,
            deterministic=article_factcheck.register_findings,
        )
    else:
        # Comparison: audit against the current venue records (hardcoded-figure
        # deterministic layer), the same stage as generation / published re-verify.
        entry = _load_meta().get(query_key)
        if not entry:
            log(f"comparison '{query_key}' is no longer eligible", "error")
            yield from drain()
            return
        records = _resolved_records(entry["current"]["order"])
        facts_pack = json.dumps(
            {"query_key": query_key, "title": entry["title"], "caption": entry["caption"], "venues": records},
            ensure_ascii=False, indent=2,
        )
        log(f"re-fact-checking '{slug}' with {MODEL_FACTCHECK}")
        yield from drain()
        fc_user = (
            "Audit this article body against the venue records. Return the JSON claim table only.\n\n"
            f"--- ARTICLE BODY ---\n{body}\n\n--- VENUE RECORDS ---\n{facts_pack}"
        )
        try:
            llm_claims, _ = agents.call_agent(
                MODEL_FACTCHECK, agents.load_prompt("factcheck.md"), fc_user, 2000, _validate_factcheck, log
            )
        except (agents.MalformedOutput, agents.AgentError) as exc:
            log(f"fact-check failed — {exc}", "error")
            yield from drain()
            return
        report = article_factcheck.build_report(slug, query_key, MODEL_FACTCHECK, llm_claims, body)

    (ARTICLE_STAGING_DIR / f"{slug}.factcheck.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    level = "error" if report["status"] == "blocked" else "info"
    log(f"report written: {report['status']} ({report['unsupported_count']} unsupported)", level)
    yield from drain()


_FIELD_ORDER = ("title", "dateline", "summary", "author", "query_key", "reviewed_at")


def _render_mdx(fm: dict[str, Any], body: str) -> str:
    ordered = {k: fm[k] for k in _FIELD_ORDER if k in fm and fm[k] not in (None, "")}
    # date objects dump unquoted (matches the blog/venue frontmatter style).
    front = yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return f"---\n{front}---\n\n{body.strip()}\n"
