# ROADMAP — Expansion, Security, Promotion, Monetisation

**Status: proposal, not a gate contract.** Nothing here is approved scope. It
is a review of the project as it stands on 2026-09-08 and a set of proposed
goals and gates for your sign-off. Per CLAUDE.md rule 1 no work starts against
any of it until you approve; per rule 3 the items marked **[decision]** are
scope questions I cannot answer for you.

Once approved, the gate contracts in §5 move into CLAUDE.md in the house style
of Gates 1–11, and this file stays as the reasoning behind them.

---

## 1. Where the project actually stands

Measured from the repository, not from memory.

| Dimension | Reading |
|---|---|
| Published venues | 36 |
| Coverage by state | VIC 24 · NSW 4 · TAS 3 · QLD 2 · SA 1 · NT 1 · ACT 1 · **WA 0** |
| Coverage by category | bathhouse 16 · thermal_springs 12 · hotel_spa 5 · other 3 |
| Published editorial | 10 posts (essays + data-bound comparison articles) |
| Claim status | 36 of 36 `unclaimed` — no venue has ever been claimed |
| Verification tiers | 63 field records, **all** `published_by_venue`; zero `operator_confirmed` |
| Build gates | 22 `/validate` checks, all automated, all offline |
| Admin surface | ~10,000 lines of pipeline Python, 60 HTTP routes |
| Public site | Astro SSG on Netlify, apex `wherewebathe.com`, zero runtime backend |
| Admin hosting | FastAPI on Fly.io (`bathers-admin`, syd), public HTTPS, persistent volume |
| Last content commit | 2026-08-12 · last code commit 2026-08-19 |

**What is genuinely strong.** The machinery is well past what a directory of
36 venues needs. The fact model (per-field source/tier/date), the six-surface
schema diff, the fact-plausibility validators that fail rather than warn, the
data-bound articles that cannot contain a hardcoded number, the internal-link
graph check, the offline JSON-LD validator — this is infrastructure most
directory sites never build. The public attack surface is a static site with
no runtime backend, which is the right shape.

**What is the actual problem.** The catalogue is too small and too concentrated
to convert any of that machinery into outcomes. 67% of venues are in one state.
Nothing has been operator-verified. Nothing has been claimed. Gate 8 (operator
outreach) was specified and never built — there is no outreach module, no
outreach table, and no outreach admin screen anywhere in `admin/`. Gate 9's
done-condition ("at least one venue published in each of SA/WA/NT/ACT, or an
explicitly logged reason for any state still at zero") is unmet for WA, with no
logged reason.

**The diagnosis in one line:** the build is ahead of the business. The next
phase is not more pipeline — it is coverage, contact, and the two security
fixes that must land before either of those makes the admin app more valuable
to attack.

---

## 2. Security

The public site is fine. The admin app is where the risk sits, and the risk
grew when it moved from "localhost only" (TRD.md §2) to a public Fly.io host —
a drift that was never re-examined against the threat model.

**What that host holds:** the Anthropic API key, the Stripe secret key, the
Netlify auth token, SMTP credentials, a Google Places key, and a git credential
with push access to the repository. It is also the one component in the system
that commits and pushes to git, and therefore reaches the live site.
Compromising it means arbitrary published content, spend on three metered APIs,
and access to visitor contact details in `claims.db`.

### Findings, most severe first

1. **Auth fails open.** `admin/app.py:100-102` — if `ADMIN_USERNAME` and
   `ADMIN_PASSWORD` are both blank, the middleware waves every request
   through. That is a sensible local-dev default and a serious one on an
   internet-facing host: a single unset Fly secret silently exposes all 60
   routes, including deploy and the pipeline runners. `.env.example` ships both
   values blank with no warning that blank means "no auth". **Fix:** bind
   fail-open to an explicit local-dev signal and refuse to start unauthenticated
   otherwise, plus a startup assertion that logs which mode it is in.
2. **Unbounded unauthenticated upload.** `/api/claims/submit` accepts a
   base64 photo with no size cap anywhere in `admin/app.py` or
   `admin/pipeline/claims.py`, and derives the stored file extension from the
   client-supplied `content_type` (`claims.py:100`) with no allowlist. Path
   traversal is neutralised by the `split("/")[-1]`, but disk exhaustion on the
   Fly volume is not — and the volume is where `claims.db` and `articles.db`
   live. **Fix:** a byte cap before decode, a content-type allowlist, and a
   magic-byte sniff rather than trusting the header.
3. **Rate limiting is keyed on the wrong thing.** `claims.py` limits to 5
   submissions per venue per hour. Across 36 slugs that permits 180 rows an
   hour, each one sending the owner an email via `notify.py` — an inbox-flood
   and disk-fill amplifier from a single unauthenticated caller. **Fix:** add a
   global and per-source limit alongside the existing per-slug one.
4. **Single shared credential, no lockout, no audit trail.** HTTP Basic, one
   username/password, no attempt throttling, no record of who deployed or
   published what. For an app that can push to git this is thin. **Fix:** at
   minimum, auth-attempt throttling and an append-only log of every
   state-changing route.
5. **No backup path for the two gitignored databases.** `claims.db` and
   `articles.db` are, by design, the only copy of the claim/payment lifecycle
   and the article opportunity queue. They live on one Fly volume with no
   backup or restore procedure anywhere in the repo. **Fix:** scheduled
   encrypted snapshot off-host, and a documented restore drill.
6. **No security headers on the public site.** `netlify.toml` sets redirects
   only — no CSP, `X-Content-Type-Options`, `Referrer-Policy`, or
   `Permissions-Policy`. Low severity for a static site, near-zero cost to fix.
7. **No CI and no dependency monitoring.** There is no `.github/` directory:
   `/validate` runs only when someone runs it. Dependencies are pinned
   (`playwright==1.48.0`, `astro@5.18.2`) with nothing watching for advisories.
8. **Undocumented secret rotation.** Six credential families, no stated
   rotation cadence and no documented revocation procedure.

### Proposed security goals

- Zero paths by which a misconfiguration exposes the admin app publicly.
- Every unauthenticated write path bounded in size, rate, and type.
- Both non-derivable databases restorable from an off-host backup, proven by a
  drill, not by assertion.
- `/validate` running automatically on every push, not on memory.
- A written incident procedure: what to revoke, in what order, and how to prove
  the published site was untampered with.

---

## 3. Expansion

Two different things are called expansion; they need separating.

**Coverage expansion (the real gap).** WA has zero venues. SA, NT and ACT have
one each. A directory that claims national scope with 67% of its catalogue in
Victoria cannot rank for, or honestly answer, a national question. Every
comparison page, every national amenity route, and every article the machinery
generates is quality-capped by this.

Named venues from Gate 9's own list are still absent — Moree, Yarrangobilly,
Innot, Mataranka, Bitter Springs, Dalhousie, Zebedee. These are exactly the
remote thermal springs that differentiate an Australian bathing directory from
a metropolitan bathhouse list, and exactly the venues a competitor is least
likely to cover well.

**Depth expansion (the quiet gap).** All 36 venues sit at
`published_by_venue` — the site currently knows only what venues say about
themselves. The `operator_confirmed` tier exists in `config.py` and has never
been reached. That tier is the site's actual editorial differentiator and it is
unearned.

### Proposed expansion goals

- **Coverage floor:** ≥5 published venues in every state and territory,
  WA first. Concretely: 36 → ~75 venues.
- ~~**Concentration ceiling:** no single state above 40% of the catalogue.~~
  *Dropped 2026-09-10 by owner decision: at 26 of 39 in Victoria it would have
  cost 26 new venues purely to move a ratio, and a ceiling fights the territory
  if Victoria really does hold most of Australia's bathhouses. The floor stands
  on its own.*
- **Depth floor:** ≥40% of published venues carrying at least one
  `operator_confirmed` field — which requires Gate 8 to exist.
- **Sustained cadence:** a standing weekly publish rhythm rather than the
  batch-then-idle pattern of the last three weeks.

Everything here runs through the existing pipeline at existing quality gates.
This is throughput, not new machinery.

---

## 4. Promotion

The technical SEO work is done and done well: apex canonicalisation, national
routes, region taxonomy, `llms.txt`, breadcrumbs, `ItemList`, `DefinedTermSet`,
per-page OG cards, an offline JSON-LD validator, and a routing-hygiene check
that keeps query-param URLs out of the crawl space.

**What is missing is everything downstream of publishing.**

- **No measurement loop.** `admin/pipeline/gsc.py` is explicitly a documented
  placeholder that calls no Google API and returns an empty list. GoatCounter
  tracks Book-now clicks only. So there is no answer to "which pages earn
  impressions", and the article opportunity queue is choosing topics from a
  registry rather than from demand.
- **No off-site presence.** Zero backlink strategy, no outreach to tourism
  bodies or regional visitor sites, no supplied-data relationships.
- **No distribution.** Ten good posts with no channel — no newsletter, no
  social cadence, no syndication.
- **The AI-citation thesis is untested.** The site is built to be cited by
  assistants; nobody has checked whether it is.

### Proposed promotion goals

- Wire the GSC feedback loop for real, and use it to choose article topics —
  demand surfaces an intent, the existing brief gate still governs whether it
  is written. Never auto-publish from a demand signal.
- A monthly citation audit: ask several assistants a set of standing Australian
  bathing questions and record whether the site is cited, in a tracked file.
- Earn links where the content is genuinely the best available: regional
  tourism bodies, state visitor sites, and the operators themselves — which is
  the same conversation as Gate 8 outreach, and should be one motion, not two.
- One distribution channel, chosen and actually run. **[decision]** which.

---

## 5. Monetisation

The claim product is built end-to-end and has earned nothing: 36 of 36 venues
`unclaimed`. The mechanism is not the problem — Stripe Checkout, webhook
signature verification, the approve/deny flow, the subscriber lookup and the
auto-publish path all exist and work.

**The problem is arithmetic and sequencing.** At $25 one-off or $5/month, full
conversion of the entire current catalogue is roughly $900 once, or $180/month.
Realistic conversion at 20% is about $35/month. The claim product cannot be the
business at 36 venues, and no amount of funnel tuning changes that.

More importantly, **nobody has ever asked**. Every venue is unclaimed and no
operator has been contacted, because Gate 8 was never built. The claim product
has not underperformed — it has not been marketed at all.

So monetisation is not a build problem. It is downstream of two things:
coverage (more venues to claim) and traffic (a reason worth $5/month). Which
means the correct monetisation move right now is **Gate 8 outreach**, because
it does three jobs at once:

1. upgrades verification tiers to `operator_confirmed` (editorial value),
2. opens the relationship in which claiming is a natural next step (revenue),
3. produces the operator contact that earns links (promotion).

That is why the sequencing below puts outreach first and revenue expansion
last.

### Revenue lines beyond claims — **[decision] required**

Each of these is new scope under CLAUDE.md rule 3, and each carries an
editorial-integrity question against rule 6. I am not proposing any of them;
I am naming them so you can rule them in or out deliberately.

| Line | Fit | Integrity risk |
|---|---|---|
| Affiliate/commission on Book now | Infrastructure already exists (GoatCounter tracks the clicks) | Moderate — ranking must never follow commission. Would need a stated policy and visible disclosure. |
| Sponsored placement | Clear revenue, simple | High — hardest to reconcile with the site's verification posture. |
| Higher-tier claim plan (photo galleries, priority support) | Extends a built product | Low |
| Data licensing to tourism/wellness operators | The fact model is genuinely licensable | Low |
| Reader-side products (guides, itineraries) | Uses existing editorial capability | Low |

My read: the low-risk lines are data licensing and a higher claim tier;
affiliate is viable **only** with a written, published policy that ordering is
never influenced by commission; sponsored placement I would decline at this
stage because it undercuts the one thing the site is being built to be trusted
for.

### Proposed monetisation goals

- **First revenue at all**, from any line — the current figure is zero.
- Claim conversion measured against contacted operators, not against total
  venues, so the number means something.
- A written and published position on commercial relationships before the
  first one exists, not after.

---

## 6. Proposed gates

In the house style of Gates 1–11: scope, then a done-condition that can be
checked. Sequential and blocking per rule 1.

### Gate 12 — Admin hardening & operational safety
Fail-open auth replaced with an explicit local-dev opt-in plus a startup
assertion; byte cap, content-type allowlist and magic-byte sniff on the claim
photo path; global and per-source rate limits alongside the per-slug one;
auth-attempt throttling; an append-only audit log of every state-changing
route; scheduled off-host encrypted backups of `claims.db` and `articles.db`
with a documented restore procedure; security headers in `netlify.toml`; a CI
workflow running `/validate` on every push; a documented secret-rotation
cadence and revocation order.

**Done when:** the admin app refuses to start unauthenticated outside an
explicit dev mode, demonstrated against a blank-credential config; an
oversized, a wrong-type, and a mislabelled photo upload are each rejected with
the right status and nothing written to disk; the global rate limit
demonstrably blocks a burst across many slugs; both databases are restored from
backup into a scratch environment and the admin runs against them unchanged;
`/validate` passes clean in CI on a pushed branch; the header set is live on
the apex; the rotation procedure is written into TRD.md as a dated entry.

### Gate 13 — Operator outreach (the deferred Gate 8)
The outreach state machine specified in Gate 8 —
not-contacted → contacted → responded → operator-confirmed / no-response /
declined — in its own gitignored SQLite file for the same reason `claims.db` is
separate; email via the existing `notify.py` SMTP pattern, no new dependency; a
manual-entry admin screen as the single source of truth regardless of channel;
tier upgrades flowing into the existing `verification` block, upgrade-only,
never a silent downgrade; the claim offer introduced as part of the same
conversation.

**Done when:** the state machine is visible in a new admin screen and every
transition is exercised; a test outreach email sends via existing SMTP config;
a manually recorded operator response upgrades a venue's confidence tier,
visible on the next build and asserted by `validate_facts`; the first real
batch (all VIC venues) has gone out with outcomes recorded; at least one venue
carries an `operator_confirmed` field in published frontmatter.

### Gate 14 — Coverage to a national floor
WA first, then SA/NT/ACT to the floor, then the named remote thermal springs
from Gate 9's list; every new venue harvested at full Gate-7 fact-model shape
at publish time, never backfilled; outreach opened for each new venue as part
of publishing it, not as a later pass.

**Done when:** every state and territory carries ≥5 published venues, or a
logged, dated reason for any that cannot *(the 40% concentration ceiling
proposed here was dropped 2026-09-10 — see §3)*; the full `/validate` suite
passes against the expanded set; state,
region, national and comparison pages regenerate with no manual intervention
beyond the normal approve action; every newly published venue is in the
outreach state machine.

### Gate 15 — Measurement, distribution & first revenue
`gsc.py` replaced with a real Search Console integration feeding the existing
opportunity queue as a ranked prompt only — never auto-creating articles; a
tracked monthly AI-citation audit; a published commercial-relationships policy;
whichever revenue lines you rule in at §5 built behind that policy; one chosen
distribution channel actually running.

**Done when:** the opportunity queue shows demand-derived candidates alongside
registry-derived ones and the brief gate still governs every one; the citation
audit has three months of recorded results; the policy is live and linked from
the methodology page; first revenue is recorded from at least one line; the
distribution channel has run for a full cycle.

---

## 7. Sequencing

The order matters more than the contents.

1. **Gate 12 first**, and not because the risk is acute today — because
   Gates 13–15 all make the admin app hold more value and take more traffic.
   Harden before you grow the target, not after.
2. **Gate 13 next.** It is the highest-leverage single piece of work in this
   document: one motion that serves verification, revenue and links
   simultaneously, and it is already specified and approved as Gate 8.
3. **Gate 14 next**, because coverage is the ceiling on everything downstream,
   and because outreach should be a habit before it is applied at scale.
4. **Gate 15 last**, because measurement is only worth wiring once there is
   enough surface to measure, and revenue is only worth optimising once there
   is something to convert.

Roughly: hardening is a contained piece of work; outreach is build-then-ongoing;
coverage is the long pole and the one that most benefits from a steady weekly
cadence rather than batches.

---

## 8. Decisions I need from you

1. **Revenue lines** (§5) — which are ruled in, which are ruled out. Affiliate
   in particular needs a yes/no and, if yes, a policy before any code.
2. **Distribution channel** (§4) — newsletter, social, syndication, or none.
   One, chosen deliberately.
3. **Coverage floor** — is ≥5 venues per state and territory the right target,
   or is a different shape better? WA-first is my recommendation either way.
4. **Admin hosting posture** — the app is public on Fly.io while TRD.md §2
   still says "runs on localhost only". Either the doc gets a dated exception
   recording the real posture, or the app moves behind a private network. The
   current state is neither.
5. **Gate numbering** — these are proposed as 12–15 alongside the E-series.
   Confirm before anything lands in CLAUDE.md.

---

## 9. What this review did not do

No code was written, no dependency added, no gate started. I did not run
`npm run build` or `/validate` (`site/node_modules` is absent in this
environment), so every claim above is drawn from reading the repository, not
from a live build or live traffic. I have no access to Search Console,
GoatCounter, Stripe or Netlify data — the "zero revenue" reading comes from all
36 published venues carrying `status: unclaimed`, which is evidence of no
completed claim, not a Stripe balance.
