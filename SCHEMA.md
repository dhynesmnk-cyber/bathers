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

## 2. MDX Frontmatter

| Field | Type | Req | Rules |
|---|---|---|---|
| `name` | string | ✓ | Venue's actual trading name. |
| `state` | enum | ✓ | One of `VIC NSW QLD SA WA TAS NT ACT`. |
| `suburb` | string | ✓ | |
| `address` | string | ✓ | Street address, single line. |
| `latitude` | number | ✓ | −44.0 … −9.0 (AU bounds; build fails outside). |
| `longitude` | number | ✓ | 112.0 … 154.0. |
| `website` | string (url) | ✓ | The venue's own site. |
| `amenities` | object | ✓ | Exactly the five boolean keys from §1, all required, no extras (zod `.strict()`). |
| `status` | enum | ✓ | `unclaimed` \| `claimed`. Default `unclaimed`. |
| `summary` | string | ✓ | ≤160 chars. Index one-liner + meta description. Written by the Architect, in register. |
| `drafted` | date (YYYY-MM-DD) | ✓ | Date the draft was generated. |
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
  suburb TEXT NOT NULL,
  latitude REAL NOT NULL,
  longitude REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'unclaimed',
  summary TEXT NOT NULL,
  has_image INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE amenities (
  slug TEXT PRIMARY KEY REFERENCES venues(slug) ON DELETE CASCADE,
  magnesium_pool INTEGER NOT NULL,
  infrared_sauna INTEGER NOT NULL,
  traditional_sauna INTEGER NOT NULL,
  cold_plunge INTEGER NOT NULL,
  led_therapy INTEGER NOT NULL
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

Rules: amenity `true` only on explicit evidence in the scraped text; unknown scalar → `null`, never guessed. Coordinates are almost never on venue sites — the pipeline geocodes `address` if possible, else leaves null for the reviewer to fill (the review pane's map thumbnail makes this a 10-second fix). `facts` holds raw material for the Architect; empty arrays are fine.

**Note on FAQ:** the Harvester's JSON contract does not carry an `faq` key. FAQ answers are the Architect's synthesis, drafted only from the `facts` object above — adding a duplicate `faq` key to the Harvester's output would just re-derive the same facts one step early. See `PROMPTS/architect.md`.

## 5. Sample MDX (place in `_published` at Gate 1)

```mdx
---
name: "Sense of Self"
state: "VIC"
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
status: "unclaimed"
summary: "A converted Easey Street warehouse holding a 39-degree mineral bath, an 80-degree Finnish sauna, a cold plunge and a hammam."
drafted: 2026-07-17
source_url: "https://www.sos-senseofself.com/"
---

Behind a rusted door off Easey Street, a two-storey brick warehouse has been
given over entirely to the business of doing very little. The main bath sits
at 39 degrees and is rich in magnesium; the Finnish sauna runs to 80; the
plunge, between 10 and 12, is exactly as cold as it needs to be.

<Pull>The house rule before midday is no chatter, and the room is better for it.</Pull>

Bathing here is sold in two-hour sittings, which turns out to be the correct
unit of time. There is a hammam with a self-guided scrub ritual, a kessa glove
for the committed, and enough concrete and planting to make the whole thing
feel closer to a public bath in the old sense than a day spa in the new one.
```

This sample is the Gate 1 fixture and the register reference for the Architect prompt. Note what it does: no first-person visit claims, facts carried in specifics (temperatures, durations, materials), dry rather than promotional.
