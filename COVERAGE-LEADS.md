# COVERAGE-LEADS.md — research leads for the Gate 14 coverage floor

**What this file is.** A starting point for the Gate 14 backlog: 22 venues to
get every state and territory to the floor of five. Nothing in it is content,
and nothing in it is verified.

**What this file is not.** Not a source. Every named venue below is *recall,
not research* — a name to go and check, written down so the search has a
starting point instead of a blank page. Some will have closed, some will turn
out to be treatment-only and fail the pool-or-sauna rule (`PROMPTS/harvester.md`
rule 7), and some may not exist as described. Nothing here may be published,
quoted, or treated as a fact about a venue. The only thing that makes a venue
publishable is the pipeline reading the venue's own site: harvest the URL, read
the draft, approve it. This is the same posture SEED.md takes with its fifth
seed — *verify the URL before harvesting rather than trusting this file* —
applied to a whole list.

**Two kinds of lead, deliberately.** Natural thermal springs and artesian bore
baths are stable, publicly documented places, and those are named below.
Bathhouses and sauna businesses are not: they open, close, move and rebrand
faster than any list survives, and a name recalled from memory is exactly the
wrong way to find them. For those, this file gives **discovery runs** instead —
the `region` strings to feed `admin/pipeline/discovery.py`, which searches
Google Places live and returns real listings with real URLs. Prefer a discovery
run over a name from this file wherever both are offered.

Standing shortfall (`python3 -m admin.pipeline.validate_coverage` is the
authoritative number, not this table):

| Subdivision | Published | Needs | Reachable? |
|---|---|---|---|
| NSW | 4 | 1 | yes — one named lead below should close it |
| TAS | 3 | 2 | yes |
| QLD | 2 | 3 | yes — two named leads plus two chains already in the catalogue |
| SA | 1 | 4 | one named lead; the other three ride on discovery |
| WA | 1 | 4 | one named lead; the other three ride on discovery |
| NT | 1 | 4 | yes, probably without the escape — see below |
| ACT | 1 | 4 | **the real question.** See below. |

---

## NSW — needs 1

| Lead | Where | Confidence | Check first |
|---|---|---|---|
| Yarrangobilly Caves thermal pool | Kosciuszko NP | high — a Gate 9 named target | NSW NPWS manages it; find the park page rather than a tourism aggregator. A national-park pool has no operator to do outreach with, so expect it to stay `not_contacted`. |
| Lightning Ridge bore baths | Lightning Ridge | moderate | Same shape as the four bore baths already published (Boomi, Burren Junction, Pilliga, Moree) — check it is a distinct site and not one of them under another name. |

Discovery runs: `Sydney`, `Byron Bay`, `Newcastle`, `Wollongong`.

## TAS — needs 2

| Lead | Where | Confidence | Check first |
|---|---|---|---|
| Hastings Caves thermal pool | Hastings, southern TAS | high | Parks Tasmania. Same no-operator caveat as Yarrangobilly. |
| Floating sauna, Lake Derby | Derby, north-east TAS | moderate | A sauna on the lake; confirm it is still operating and takes bookings. |

Discovery runs: `Hobart`, `Launceston`, `Freycinet`.

## QLD — needs 3

| Lead | Where | Confidence | Check first |
|---|---|---|---|
| Innot Hot Springs | Innot Hot Springs, far north QLD | high — a Gate 9 named target | Confirm whether the bathing is the caravan park's or a separate operation. |
| Talaroo Hot Springs | Talaroo, near Georgetown | moderate | Indigenous-owned; check access is public and booked rather than restricted. |
| Soak Bathhouse — Gold Coast / Brisbane sites | south-east QLD | high — SEED.md names this as a multi-location chain | Only the South Yarra site is published. `find_duplicates()` will flag the shared domain on harvest; the sites are genuinely distinct venues, which is the case that guard exists to surface, not to block. |
| City Cave — QLD sites | Brisbane and around | high — the franchise is Brisbane-founded | Same as above: City Cave Braybrook is published, the QLD sites are separate venues. Franchise pages are thin, so expect a thin-extraction warning. |

Discovery runs: `Brisbane`, `Gold Coast`, `Sunshine Coast`, `Cairns`.

## SA — needs 4

| Lead | Where | Confidence | Check first |
|---|---|---|---|
| Dalhousie Springs | Witjira National Park | high — a Gate 9 named target | Remote; the park page is the source. No operator.  |

Discovery runs: `Adelaide`, `Adelaide Hills`, `Barossa Valley`, `Port Lincoln`.
SA is one named lead and three unknowns — run discovery before assuming a
shortfall is real.

## WA — needs 4

| Lead | Where | Confidence | Check first |
|---|---|---|---|
| Zebedee Springs | El Questro, the Kimberley | high — a Gate 9 named target | Access is via El Questro station and seasonal; check whether it is gated behind a station pass, which changes what `access` should say. |
| Merse Wellness — other Perth sites | Perth metro | moderate | Osborne Park is published; if it is a small chain the other sites are separate venues. |

Discovery runs: `Perth`, `Fremantle`, `Margaret River`, `Broome`.

## NT — needs 4, and probably reachable

I said earlier that NT might need the logged-reason escape. Looking at it
properly, it probably does not:

| Lead | Where | Confidence | Check first |
|---|---|---|---|
| Mataranka Thermal Pool | Elsey NP / Mataranka Homestead | high | **A different place from the published `bitter-springs`**, about a kilometre away, and Gate 9 listed the two separately. Confirm they are distinct before publishing — this is the one lead here at real risk of being a duplicate. |
| Tjuwaliyn (Douglas) Hot Springs | Douglas-Daly | high | NT Parks. |
| Katherine Hot Springs | Katherine | high | Town-managed; check it is open (it closes after wet-season flooding). |
| Berry Springs / Howard Springs | near Darwin | moderate, and **eligibility is the question** | Natural swimming holes rather than thermal pools. Whether a spring-fed swimming hole is a "pool" under rule 7 is a judgement call the harvester shouldn't be left to make alone — decide it deliberately, and if the answer is yes, say so in the gate record, because it widens what the directory covers. |

Discovery run: `Darwin`.

With the three high-confidence entries above, NT reaches four without touching
the eligibility question, and five with any Darwin venue discovery turns up.

## ACT — needs 4, and this is the real question

ACT is the one subdivision where the floor may genuinely be unreachable, and
not because the work hasn't been done. The territory is a single city of about
470,000 people with no thermal geology at all — there is no natural-springs
path to five the way there is in NT, QLD or NSW. Whether Canberra holds five
venues where a pool or a sauna is the reason to visit is an open question about
the territory, not a backlog.

So: run `Canberra` through discovery first. If it returns five eligible venues,
publish them and the floor holds. If it returns one or two, that is what
`data/coverage-reasons.json` is for — and the reason should say *that*, with the
discovery result behind it, not "not done yet". The reasons file validates a
≥20-character reason and a `YYYY-MM-DD` date precisely so this decision has to
be written down rather than assumed.

Same reasoning applies to SA and WA if discovery comes back thin, but both have
a named natural-springs lead and much larger populations, so treat a shortfall
there as a backlog until discovery says otherwise.

---

## Running a discovery pass

```bash
# needs GOOGLE_PLACES_API_KEY — Fly has it, this sandbox does not
uvicorn admin.app:app --port 8787   # then the harvest panel's discovery field
```

`discovery.discover_venues(region)` searches `bathhouse`, `hot springs`,
`thermal baths` and `sauna` in `<region>, Australia`, drops anything whose
domain is already published or staged, and returns names with URLs. It never
harvests or stages anything — a human queues each URL. Feed it the region
strings above one at a time and work the results; that is the path to the floor
for every urban venue on this list.

## Order worth working in

1. **The four Gate 9 named targets** — Yarrangobilly, Innot, Dalhousie,
   Zebedee. Each is a single URL with no discovery needed, and each adds a
   different subdivision. Four harvests, four states moved.
2. **NT's three thermal pools** — Mataranka, Tjuwaliyn, Katherine. Takes NT
   from 1 to 4.
3. **The two chains already in the catalogue** — Soak's QLD sites and City
   Cave's. Known-good domains, known-good page shapes.
4. **Discovery for QLD, TAS and NSW**, which are 1–3 short each.
5. **Discovery for SA, WA and Canberra**, then decide ACT on the result.

Every venue published here lands in the outreach queue automatically
(`approve()` calls `outreach_store.ensure()`), so Gate 14 feeds Gate 13 — and
each new venue harvested from today has its published contact address recorded
in the outreach store, so the outreach it opens has somewhere to write.
