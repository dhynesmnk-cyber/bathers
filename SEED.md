# SEED.md — Pipeline Test Venues

Gate 4's done-condition runs against these URLs. All four primary URLs were verified live in July 2026. They are deliberately varied: a large hot-springs destination, a design-led springs complex, an inner-city warehouse bathhouse, and a multi-site urban chain — different site structures, different amenity vocabularies, a good spread for testing extraction.

Seeds 6–7 were added for Gate 16 (2026-09-15) and are American. Their URLs are deliberately **not** recorded here: unlike seeds 1–4 they have never been verified live by this project, and a URL written down from memory is the kind of confident-looking wrong fact the whole pipeline exists to prevent. Find and confirm each before harvesting.

| # | Venue | URL | State | Why it's a good test |
|---|---|---|---|---|
| 1 | Sense of Self | https://www.sos-senseofself.com/ | VIC | Warehouse bathhouse; magnesium bath, Finnish sauna, cold plunge, hammam. Rich specific facts (temperatures, session lengths). Also the SCHEMA.md sample — pipeline output can be compared directly against the hand-written fixture. |
| 2 | Peninsula Hot Springs | https://www.peninsulahotsprings.com/bathe/bath-house | VIC | Large multi-experience site; tests fact extraction from a sprawling page and the Harvester's discipline about what *isn't* evidenced on this specific page. |
| 3 | Alba Thermal Springs & Spa | https://albathermalsprings.com.au/ | VIC | Heavily marketed copy ("sanctuary", "rejuvenation" throughout) — the ideal stress test for the Architect/Gatekeeper banned list. Sauna and steam room stated; magnesium is not — amenity extraction should reflect that. |
| 4 | Soak Bathhouse | https://soakbathhouse.com.au/ | QLD | Multi-location chain (Gold Coast, Brisbane, more) — tests how the pipeline handles one URL describing several venues. Expected behaviour: Harvester notes the ambiguity in `confidence_notes`; reviewer decides. Also the only non-VIC seed, exercising state handling. |
| 5 | Hepburn Bathhouse & Spa | (find current official URL at harvest time — historic mineral-springs bathhouse, Hepburn Springs VIC) | VIC | Optional fifth. Verify the URL before harvesting rather than trusting this file. |
| 6 | Warm Mineral Springs | (find current official URL at harvest time — city-operated natural mineral spring, North Port FL) | US / FL | Gate 16 seed. A natural spring with no bathhouse framing at all, in US English and US customary units — exercises the locale branch, the US geocode path, the Florida bbox and a US drive-time origin end to end. |
| 7 | Safety Harbor Resort and Spa | (find current official URL at harvest time — historic mineral-springs spa, Safety Harbor FL) | US / FL | Gate 16 seed. A hotel-spa-shaped US venue: tests `category` assignment and USD structured pricing against a page that markets heavily, the US counterpart to seed 3. |

## Expectations per run

- Seeds 1–3 should each produce a schema-valid staged draft with ≥6 items across the `facts` arrays and zero banned words in the final MDX.
- Seed 3's draft must not claim a magnesium pool.
- Seed 4 is allowed to produce a draft needing reviewer intervention — that's the point. What it must not do is silently blend multiple locations into one confident venue record.
- Coordinates will be null or geocoded-approximate on all seeds; correcting them in the review pane's map thumbnail is part of the Gate 4 walkthrough, not a failure.
- Seeds 6–7 must produce drafts in US English with US customary units — `python3 -m admin.pipeline.validate_locale` is the check, and an Australian-spelled US draft failing it is the Gate 16 done-condition, not a bug in the seed.
- Seeds 6–7 must geocode inside the Florida bounding box and drive-time from a US origin (Tampa or Orlando for both). A drive time "from Darwin" means the country did not reach `drive_time`.

Do not publish any of these drafts to the live site during testing without reviewing them as a human first — they are real businesses.
