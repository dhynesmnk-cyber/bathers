# SCHEMA.md — The Data Contract

One contract, four consumers: the zod content schema, the SQLite tables, the Harvester's JSON output, and the admin frontmatter editor. **Any change to this file must be propagated to all four in the same commit.** Field names are identical everywhere — no renaming between layers.

## 1. Amenity keys (canonical order)

| Key | Notation | Full name |
|---|---|---|
| `magnesium_pool` | `Mg` | Magnesium pool |
| `infrared_sauna` | `IR` | Infrared sauna |
| `traditional_sauna` | `SA` | Traditional sauna |
| `cold_plunge` | `CP` | Cold plunge |
| `led_therapy` | `LED` | LED light therapy |

This order is used everywhere amenities are displayed.

### 1a. Facility keys (2026-07-21 addition, optional; pool-type keys added 2026-07-23)

Practical/logistics info, distinct from the bathing-experience amenities above — absent on venues published before this date, defaulting to `false`/unset. The three pool-type keys (2026-07-23) drive the homepage's pool-type grouping (UX.md §2.1) — a venue can have more than one true.

| Key | Label |
|---|---|
| `parking` | Parking |
| `towels_provided` | Towels provided |
| `changerooms` | Changerooms |
| `bookings_required` | Bookings required |
| `wheelchair_access` | Wheelchair access |
| `outdoor_pool` | Outdoor pool |
| `indoor_pool` | Indoor pool |
| `natural_spring` | Natural spring |

## 2. MDX Frontmatter

| Field | Type | Req | Rules |
|---|---|---|---|
| `name` | string | ✓ | Venue's actual trading name. |
| `state` | enum | ✓ | One of `VIC NSW QLD SA WA TAS NT ACT`. |
| `category` | enum | ✓ | *(2026-07-22, `day_spa` retired/`hotel_spa` added 2026-07-26)* One of `thermal_springs`, `bathhouse`, `hotel_spa`, `other`. The directory is scoped to venues with a pool or a sauna as a central offering; `hotel_spa` is for hotel/lodge venues with a real bathing circuit, not a treatment-only spa. Set by the Architect from the Google Places block's `primaryType` or editorial judgement; reviewer-editable. |
| `suburb` | string | ✓ | |
| `address` | string | ✓ | Street address, single line. |
| `latitude` | number | – | *(2026-07-22: no longer required)* −44.0 … −9.0 (AU bounds when present; build fails outside). Null when geocoding the address found no match — the venue simply doesn't appear on the map, it is not blocked from publishing. No manual entry UI; see §4. |
| `longitude` | number | – | *(2026-07-22: no longer required)* 112.0 … 154.0 when present. Same null handling as `latitude`. |
| `website` | string (url) | ✓ | The venue's own site. |
| `amenities` | object | ✓ | Exactly the five boolean keys from §1, all required, no extras (zod `.strict()`). |
| `facilities` | object | – | *(2026-07-21, extended 2026-07-23)* The eight boolean keys from §1a. Optional — omit entirely on venues where none are known; individual keys default `false`. |
| `hours` | string | – | *(2026-07-21)* Freeform display string, e.g. `"Mon–Sun 6am–10pm"`. Drafted by the Architect from `facts.hours`, never fabricated. |
| `cost` | string | – | *(2026-07-21)* Freeform display string, e.g. `"$45–120 per session"`. Drafted by the Architect from `facts.pricing`, never fabricated. |
| `access` | string | – | *(2026-07-21)* Freeform display string, for venues gated by hotel-guest or membership status, e.g. `"Guests of the hotel, or Langham members — day spa visitors can also book a treatment to get pool access for the day."` Drafted by the Architect from `facts`, never fabricated. Omitted for the majority of standalone venues with no such restriction. |
| `status` | enum | ✓ | `unclaimed` \| `claimed`. Default `unclaimed`. |
| `summary` | string | ✓ | ≤160 chars. Index one-liner + meta description. Written by the Architect, in register. |
| `drafted` | date (YYYY-MM-DD) | ✓ | Date the draft was generated. |
| `verified` | date (YYYY-MM-DD) | ✓ | *(2026-07-22)* Date of the most recent harvest/verification pass. Set alongside `drafted` at initial draft time, and re-set on every subsequent re-harvest — unlike `drafted`, which is meant to stay fixed. Rendered content only; not stored in SQLite (see §3). |
| `source_url` | string (url) | ✓ | The URL harvested from. |
| `image` | string | – | Path to published image asset. Present only after the separate image-publish action (UX.md §4). |
| `image_source` | string (url) | –* | *Required if `image` present (zod refinement). |
| `image_caption` | string | –* | *Required if `image` present. `PLATE I.` register. |
| `faq` | array of `{question, answer}` | – | Optional, 3–6 pairs recommended, hard cap 8. Drafted by the Architect strictly from the Harvester's `facts` object (§4); never fabricated. Reviewer-editable in the admin pane. Absent or empty array → no FAQ section renders (zero-FAQ pages must look complete, same posture as the zero-image default). |

Slug = filename (`peninsula-hot-springs.mdx`), kebab-case, unique across `_staging` + `_published`. Slug is **not** a frontmatter field — it is derived from the filename everywhere.

## 3. SQLite (`data/directory.db`)

```sql
CREATE TABLE venues (
  slug TEXT PRIMARY KEY,          -- matches MDX filename; no separate UUID
  name TEXT NOT NULL,
  state TEXT NOT NULL,
  category TEXT NOT NULL,         -- 2026-07-22
  suburb TEXT NOT NULL,
  latitude REAL,                  -- 2026-07-22: nullable — null means "no map marker", not invalid
  longitude REAL,
  status TEXT NOT NULL DEFAULT 'unclaimed',
  summary TEXT NOT NULL,
  has_image INTEGER NOT NULL DEFAULT 0,
  hours TEXT,
  cost TEXT,
  access TEXT
);
CREATE TABLE amenities (
  slug TEXT PRIMARY KEY REFERENCES venues(slug) ON DELETE CASCADE,
  magnesium_pool INTEGER NOT NULL,
  infrared_sauna INTEGER NOT NULL,
  traditional_sauna INTEGER NOT NULL,
  cold_plunge INTEGER NOT NULL,
  led_therapy INTEGER NOT NULL
);
CREATE TABLE facilities (
  slug TEXT PRIMARY KEY REFERENCES venues(slug) ON DELETE CASCADE,
  parking INTEGER NOT NULL DEFAULT 0,
  towels_provided INTEGER NOT NULL DEFAULT 0,
  changerooms INTEGER NOT NULL DEFAULT 0,
  bookings_required INTEGER NOT NULL DEFAULT 0,
  wheelchair_access INTEGER NOT NULL DEFAULT 0,
  outdoor_pool INTEGER NOT NULL DEFAULT 0,
  indoor_pool INTEGER NOT NULL DEFAULT 0,
  natural_spring INTEGER NOT NULL DEFAULT 0
);
```

The DB is derived and disposable (TRD §5): rebuildable in full from `_published` frontmatter. Approve = upsert on `slug`.

**Note on FAQ:** not stored in SQLite — like the MDX body, it is rendered content, not a query/filter dimension.

## 4. Harvester JSON output

The Harvester agent must emit **only** this object — no prose, no markdown fences:

```json
{
  "name": "string",
  "state": "VIC|NSW|QLD|SA|WA|TAS|NT|ACT|null",
  "suburb": "string|null",
  "address": "string|null",
  "latitude": null,
  "longitude": null,
  "website": "string",
  "amenities": {
    "magnesium_pool": false, "infrared_sauna": false,
    "traditional_sauna": false, "cold_plunge": false, "led_therapy": false
  },
  "facts": {
    "pools": ["verbatim-adjacent factual notes, e.g. '39°C mineral pool'"],
    "heat": [], "cold": [], "treatments": [],
    "pricing": [], "hours": [], "setting": [], "history": [], "other": []
  },
  "confidence_notes": ["anything ambiguous or unverifiable, stated plainly"]
}
```

Rules: amenity `true` only on explicit evidence in the scraped text; unknown scalar → `null`, never guessed. Coordinates are almost never on venue sites — the Harvester always leaves them `null`; the pipeline geocodes `address` automatically downstream (Nominatim, `admin/pipeline/geocode.py`) and, since 2026-07-22, that's the *only* source — if geocoding finds no match, coordinates stay `null` and the venue is simply excluded from the map (see §2). `facts` holds raw material for the Architect; empty arrays are fine.

**Note on FAQ:** the Harvester's JSON contract does not carry an `faq` key. FAQ answers are the Architect's synthesis, drafted only from the `facts` object above — adding a duplicate `faq` key to the Harvester's output would just re-derive the same facts one step early. See `PROMPTS/architect.md`.

**Note on `hours`/`cost`/`facilities`/`access` (2026-07-21):** same division of labour — the Harvester's JSON contract is unchanged; `facts.hours` and `facts.pricing` already exist and are reused as the Architect's source material for the frontmatter `hours`/`cost` strings, and `facts` generally for `facilities` and `access` (there's no dedicated Harvester bucket for "who can book" — guest/member-access details typically land in `facts.setting` or `facts.other` when a venue's own site mentions them). No new Harvester fields.

**Note on `category`/`verified` (2026-07-22):** same division of labour again — no new Harvester fields. `category` is an Architect-level judgement call like `hours`/`cost`/`access`, drawn from the appended Google Places verification block's `primaryType` when present, else from the harvested facts; it is required, so unlike those optional fields it must never be left blank (default to `other` only when genuinely ambiguous). `verified` is set by the pipeline at finalize time (`admin/pipeline/orchestrator.py`), not by any agent.

**Note on review-signal prose (2026-07-22):** when the appended Google Places verification block carries `rating`/`user_rating_count` (and optionally `reviews`), the Architect may write one brief, non-negative-leaning sentence characterising the review signal, grounded only in that real data — never inventing sentiment. Omitted entirely when no review data exists, same "omit if thin" posture as everything else in this section. This is body prose; there is no dedicated frontmatter field for it.

## 5. Sample MDX (place in `_published` at Gate 1)

```mdx
---
name: "Sense of Self"
state: "VIC"
category: "bathhouse"
suburb: "Collingwood"
address: "30–32 Easey Street, Collingwood VIC 3066"
latitude: -37.7965
longitude: 144.9885
website: "https://www.sos-senseofself.com/"
amenities:
  magnesium_pool: true
  infrared_sauna: false
  traditional_sauna: true
  cold_plunge: true
  led_therapy: false
facilities:
  parking: false
  towels_provided: true
  changerooms: true
  bookings_required: true
  wheelchair_access: false
  outdoor_pool: false
  indoor_pool: true
  natural_spring: false
hours: "Daily, sittings from 10am–9pm"
cost: "$65 per two-hour sitting"
status: "unclaimed"
summary: "A converted Easey Street warehouse holding a 39-degree mineral bath, an 80-degree Finnish sauna, a cold plunge and a hammam."
drafted: 2026-07-17
verified: 2026-07-22
source_url: "https://www.sos-senseofself.com/"
---

Behind a rusted door off Easey Street, a two-storey brick warehouse has been
given over entirely to the business of doing very little. The main bath runs
at 39 degrees and is rich in magnesium — hot enough that the cold plunge, a
sharp 10 to 12 degrees, feels like the good kind of shock rather than a dare.
Sittings run two hours and are sold in blocks, so book ahead if you can; the
good afternoon slots go first.

<Pull>The house rule before midday is no chatter, and the room is better for it.</Pull>

There's a hammam with a self-guided scrub ritual, a kessa glove if you want
to commit to it properly, and a Finnish sauna that runs to 80 degrees — plus
enough concrete and planting that the whole place feels closer to an
old-fashioned public bath than a modern day spa.
```

This sample is the Gate 1 fixture and the register reference for the Architect prompt (2026-07-21: rewritten to match the warmed register — see `PROMPTS/architect.md`). Note what it does: no first-person visit claims, facts carried in specifics (temperatures, durations, materials), warm and direct rather than promotional or logbook-dry.

## 6. Astro build note

Both content collections' MDX bodies are parsed as JSX, which requires void elements to be self-closing (`<img />`, not `<img>`). The blog pipeline (§7) enforces this automatically when saving a post body; hand-edited MDX (venue or blog) must follow the same rule.

## 7. Blog Posts (2026-07-21 addition)

Hand-authored, not part of the AI pipeline — no Harvester/Architect/Gatekeeper involvement, no SQLite table (posts aren't queried/filtered the way venues are; the Astro content collection is the only store). Mirrors the venue staging/published split: drafts live in `content-staging/_blog_staging/` until a deliberate Publish action moves them into `site/src/content/blog/_published/`.

| Field | Type | Req | Rules |
|---|---|---|---|
| `title` | string | ✓ | |
| `dateline` | date (YYYY-MM-DD) | ✓ | |
| `summary` | string | ✓ | ≤160 chars. Index one-liner + meta description. |
| `cover_image` | string | – | Path to a published image asset (`/blog-images/<slug>-<n>.webp`), written by the image-publish step. |
| `video_url` | string (url) | – | External embed only — must match a YouTube or Vimeo watch/share URL pattern. No self-hosted video. |

Slug = filename, kebab-case, derived from the title at creation (`admin.pipeline.blog.slugify`), unique across `_blog_staging` + `_published`, exactly like venues.

Body is Quill-authored HTML saved directly as the MDX body. `admin.pipeline.blog._mdx_safe_html` self-closes void elements (`<img>` → `<img />`, `<br>` → `<br />`) on every save — see §6.

Images inserted mid-draft are staged in `temp_data/blog_images/<slug>/` (gitignored) and converted to webp in `site/public/blog-images/` only at Publish, mirroring the venue image pipeline's separate publish step (UX.md §4). Images added while editing an *already-published* post skip the staging step and are converted straight to `site/public/blog-images/`, since there's no publish gate left to cross for that post.
