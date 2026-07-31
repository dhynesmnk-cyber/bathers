// Staleness refresh for hybrid comparison articles (Editorial Gate E1,
// 2026-08-01). Resolves every eligible comparison query against the current
// venue data and records, per query_key: the current headline fingerprint,
// whether it has drifted from the last human-reviewed baseline, and when the
// figures last changed. The output (site/src/data/articles-meta.json) is
// derived + committed — the same relationship venues.json has to directory.db:
// the admin regenerates it (admin/pipeline/article_store.py), the site reads it
// at build, /validate diffs it. It reuses the site's own selection logic
// (comparisons.ts) so "who wins" is computed one way only, never re-derived in
// Python.
//
// Run:
//   node --import ./scripts/ts-register.mjs scripts/refresh-articles.ts
//   ... --accept <query_key>   re-baseline one article (human re-review)
//   ... --accept-all           re-baseline every article
import { readFileSync, writeFileSync } from "node:fs";
import { resolveComparisons, comparisonFingerprint, type Fingerprint } from "../src/data/comparisons.ts";

const VENUES = new URL("../src/data/venues.json", import.meta.url);
const META = new URL("../src/data/articles-meta.json", import.meta.url);

interface MetaEntry {
  venue_count: number;
  stale: boolean;
  data_updated_at: string;
  reviewed: Fingerprint;
  current: Fingerprint;
}

const today = () => new Date().toISOString().slice(0, 10);

function readJson<T>(url: URL, fallback: T): T {
  try {
    return JSON.parse(readFileSync(url, "utf8")) as T;
  } catch {
    return fallback;
  }
}

// A change to the article's headline claim: who wins, the figure shown against
// them, or the order. A re-order below the winner still counts — the ranking is
// the claim the article makes.
function headlineChanged(a: Fingerprint, b: Fingerprint): boolean {
  return a.winner !== b.winner || a.headline !== b.headline || a.order.join("|") !== b.order.join("|");
}

// Any lead-column figure changed (a reprice of a listed venue), even if the
// order held — bumps data_updated_at without necessarily flagging stale.
function figuresChanged(a: Fingerprint, b: Fingerprint): boolean {
  return a.signature.join("|") !== b.signature.join("|");
}

function main(): void {
  const args = process.argv.slice(2);
  const checkOnly = args.includes("--check"); // report drift, write nothing (for /validate)
  const acceptAll = args.includes("--accept-all");
  const acceptIdx = args.indexOf("--accept");
  const acceptKey = acceptIdx >= 0 ? args[acceptIdx + 1] : null;

  const rawVenues = readJson<Array<{ slug: string }>>(VENUES, []);
  // comparisons.ts selectors read v.data.* off a CollectionEntry shape;
  // venues.json already carries that nested shape, so wrapping as {id,data} lets
  // the real select functions run unchanged.
  const venues = rawVenues.map((v) => ({ id: v.slug, data: v }));
  const prev = readJson<Record<string, MetaEntry>>(META, {});

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { eligible } = resolveComparisons(venues as any);
  const next: Record<string, MetaEntry> = {};

  for (const c of eligible) {
    const current = comparisonFingerprint(c.columns, c.venues);
    const stored = prev[c.slug];
    const forceAccept = acceptAll || acceptKey === c.slug;

    let reviewed: Fingerprint;
    let dataUpdatedAt: string;
    if (!stored) {
      // First sight: current state is the baseline; nothing to be stale against.
      reviewed = current;
      dataUpdatedAt = today();
    } else {
      reviewed = forceAccept ? current : stored.reviewed;
      dataUpdatedAt = figuresChanged(current, stored.current) ? today() : stored.data_updated_at;
    }

    next[c.slug] = {
      venue_count: c.venues.length,
      stale: headlineChanged(current, reviewed),
      data_updated_at: dataUpdatedAt,
      reviewed,
      current,
    };
  }

  // Deterministic key order for byte-stable diffs (matches venues.json style:
  // 2-space indent, trailing newline).
  const sorted: Record<string, MetaEntry> = {};
  for (const k of Object.keys(next).sort()) sorted[k] = next[k];
  const serialized = JSON.stringify(sorted, null, 2) + "\n";

  if (checkOnly) {
    // Report-only freshness gate for /validate: write nothing, exit nonzero if
    // the committed metadata would change (i.e. someone changed venue data
    // without refreshing).
    const committed = (() => {
      try {
        return readFileSync(META, "utf8");
      } catch {
        return "";
      }
    })();
    if (committed !== serialized) {
      console.error(
        "[articles] articles-meta.json is stale — run `python -m admin.pipeline.article_store --rebuild` and commit the result",
      );
      process.exit(1);
    }
    console.log("[articles] articles-meta.json is current");
    return;
  }

  writeFileSync(META, serialized, "utf8");
  const stale = Object.entries(sorted).filter(([, e]) => e.stale).map(([k]) => k);
  console.log(
    `[articles] refreshed ${Object.keys(sorted).length} comparison(s)` +
      (stale.length ? `; STALE (needs review): ${stale.join(", ")}` : "; none stale"),
  );
}

main();
