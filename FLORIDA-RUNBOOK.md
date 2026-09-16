# Florida runbook — Gate 16

Everything on the platform side of Gate 16 is done and on `main`'s history. What
remains is content, and content needs credentials: the harvest calls Anthropic,
discovery calls Google Places, geocoding calls Nominatim and outreach sends
mail. None of those keys exist in a CI or cloud session, so this is written to be
run on the machine where `.env` lives.

Nothing here publishes anything. Every draft lands in `content-staging/_staging/`
for review, exactly as a single harvest from the admin UI does. These are real
businesses; the approve action is a human's.

## 0. Before you start

Keys read from `.env` (see `.env.example` for the full list):

| Key | Used by | Without it |
|---|---|---|
| `ANTHROPIC_API_KEY` | Harvester / Architect / Gatekeeper | no harvest at all |
| `GOOGLE_PLACES_API_KEY` | discovery, listing verification, candidate photos | discovery returns nothing; verification silently skips |
| `GEOCODER=nominatim` + `GEOCODER_USER_AGENT` | coordinates | every venue publishes with no coordinates, and so no drive-time and no Nearby |
| `SMTP_*` | outreach email | you can still record outcomes by hand |

Check the branch builds before you add anything to it:

```bash
cd site && npm run build      # must be zero warnings
cd .. && /validate            # must be VALIDATE PASS
```

## 1. Discover

```bash
python3 -m admin.pipeline.harvest_florida --discover
```

Sweeps the eight Florida regions from `site/src/data/regions.ts` — South
Florida, the Keys, Tampa Bay, Central, North Central, Northeast, Southwest, the
Panhandle — with springs-led keywords, deduped across regions and against
everything already published or staged. Costs Places calls only; harvests
nothing.

Read the list before going further. Discovery finds businesses, not bathhouses:
expect float spas, med-spas and gyms with a sauna in the corner. The directory's
scope test is unchanged — is bathing the point of the place, or an amenity
attached to something else?

## 2. Harvest

Start small. Each venue is three agent calls.

```bash
python3 -m admin.pipeline.harvest_florida --harvest --limit 5
```

Or harvest a known URL directly — this is how to do the two `SEED.md` seeds,
Warm Mineral Springs and Safety Harbor Resort and Spa, once you have confirmed
their current official URLs. Their URLs are deliberately not recorded in this
repository: unlike seeds 1–4 they have never been verified live, and a URL
written down from memory is the kind of confident-looking wrong fact the whole
pipeline exists to prevent.

```bash
python3 -m admin.pipeline.harvest_florida --harvest --url https://…
```

Failures do not stop the sweep. The summary at the end names each URL that
produced no draft and why; raw agent output for a validation failure is in
`admin/_failed/`.

## 3. Review each draft

In the admin UI (`uvicorn admin.app:app --reload --port 8787`). The normal
keyboard review applies. What is specific to a US venue:

- **Country and subdivision.** `US` / `FL`. The editor repopulates the
  subdivision list when you change country, and derives currency — if currency
  does not read `USD`, the country did not take.
- **Locale.** The draft must be in US English with US customary units. An
  Australian-spelled US draft is a Gatekeeper miss, not a house-style choice —
  `python3 -m admin.pipeline.validate_locale` is the check and it fails the
  build, so catch it here rather than there.
- **Coordinates.** Must sit inside the Florida bounding box. `validate_facts`
  enforces it, and a venue geocoded into Georgia will fail.
- **Drive-time.** Must read from a US origin — Miami, Tampa, Orlando,
  Jacksonville, Tallahassee or Gainesville. "from Darwin" means the country did
  not reach `drive_time`.
- **Price.** Structured `price.adult_drop_in` in USD, and every number in it has
  to appear in the freeform `cost` string; they are cross-checked.
- **Gate 7 shape at publish time, not backfilled.** Every populated verifiable
  field needs a source and a confidence tier. This is the gate contract, and
  backfilling later is what Gate 9 was written to stop.

`/mdx-review` gives an advisory pre-screen before the human pass. It never
approves or moves anything.

## 4. Approve

The approve action moves the file to `_published`, upserts the DB, regenerates
`venues.json` and `venues.geojson`, and **opens the outreach record
automatically** (`staging.py` → `outreach_store.ensure`). There is no separate
step to remember.

After the first few:

```bash
python3 -m admin.pipeline.data_store --rebuild   # run twice; must be byte-identical
cd site && npm run build
```

Check `/places/north-america/united-states/florida/` renders, that the country
filter pages appear (`/places/north-america/united-states/magnesium-pool/` and
friends), and that a venue page reads in °F and miles with `US$` pricing.

## 5. Outreach

Once a venue is published its outreach row exists in `not_contacted`. Send from
the `/outreach` admin screen. The email body is country-neutral now, so a
Florida operator is not told this is an Australian directory.

Record every outcome there whatever the channel — that screen is the single
source of truth, by design.

## 6. Closing Gate 16

The done-conditions that remain are content-dependent:

- **Florida ≥5 published.** `python3 -m admin.pipeline.validate_coverage` prints
  the gap. It reports rather than fails while Gate 14 is open.
- **Every published US venue in the outreach machine.** Automatic on approve;
  `validate_outreach` asserts the integrity of what is there.
- **`llms.txt`.** Add the US routes once they resolve — `/validate` check 17
  requires every path it lists to exist in the build, which is why they are not
  in there yet.
- **The methodology page's Coverage paragraph.** It names the states actually
  covered. Add Florida when Florida is actually published, not before.

Then `/validate` clean, `npm run build` zero warnings, and deploy.

## If something looks wrong

- **Draft in the wrong English** → Gatekeeper missed the locale block. Check the
  harvest log shows `Locale: en-US`, and re-run rather than hand-editing the
  prose.
- **No coordinates** → `GEOCODER` unset, or Nominatim rate-limited (1 req/sec,
  enforced locally). Misses are cached; `admin/pipeline/backfill_geocode.py`
  retries later.
- **Drive-time absent** → expected when the venue has no coordinates. Present
  but wrong means OSRM's public demo was unreachable; it is not cached on
  failure, so re-running is safe.
- **A venue that is not really a bathhouse** → reject it with a reason. The
  scope decision is the reviewer's, and `_rejected` keeps the sidecar.
