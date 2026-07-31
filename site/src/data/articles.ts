// Hybrid comparison articles (Editorial Gate E1, 2026-08-01). A blog post with
// a `query_key` is a comparison article: it lives under /blog/ but is the
// canonical home for that comparison intent, so the matching generated
// /compare/<query_key>/ page is suppressed and 301s to the article (netlify.toml).
// This keeps one intent at one URL — never a table at /compare/ competing with a
// voiced article at /blog/ for the same query.
import type { CollectionEntry } from "astro:content";

export interface ArticleLink {
  slug: string;
  title: string;
  queryKey: string;
}

export function comparisonArticles(posts: CollectionEntry<"blog">[]): ArticleLink[] {
  return posts
    .filter((p) => !!p.data.query_key)
    .map((p) => ({ slug: p.id, title: p.data.title, queryKey: p.data.query_key! }));
}

// The comparison keys already voiced as an article — excluded from generated
// /compare/ page + hub generation so they don't self-compete.
export function claimedKeys(posts: CollectionEntry<"blog">[]): Set<string> {
  return new Set(comparisonArticles(posts).map((a) => a.queryKey));
}

export const articlePath = (slug: string) => `/blog/${slug}/`;
