# Item Recommendations

> **Status: design, not implemented.** No code for this exists yet. This records the
> research and the decisions taken so far, so they are not rediscovered or reversed.

Design notes for the item recommendation system. Every figure here was measured on
2026-07-28 against the live Deadlock API; nothing is estimated.

See [ADR-0001](adr/0001-pick-share-lift-over-win-rate.md) for why ranking uses
pick-share lift, and [`CONTEXT.md`](../CONTEXT.md) for the vocabulary.

## The problem

Item advice has to work across an open-ended set of situations, not a fixed list:

- enemy sustains heavily → buy anti-heal *(lane matchup)*
- your ult keeps getting interrupted → buy Unstoppable *(own kit vulnerability)*
- Paradox into mobile heroes → the bomb build may be wrong *(build viability)*
- Dynamo on the enemy team, midboss contested soon → Unstoppable *(objective timing)*
- they bought a counter to you → buy the counter to that *(counter-counter)*
- Counterspell against ability-heavy enemies *(ability-class counter)*

Because the space cannot be enumerated, the system supplies **primitives the coach
composes per situation**, rather than precomputed answers to anticipated questions.

## Three layers

| layer | source | supplies | cost |
| --- | --- | --- | --- |
| Mechanics | `/v1/assets/items`, `/v1/assets/heroes` | the *because* — and prunes which pairs are worth testing | cached |
| Hero signature | `/v1/analytics/item-stats` | how each hero is built, independent of the enemy | 39 calls, ~40s |
| Reactions | `/v1/sql` | mined item→item counterplay | 2 req/min, 20/hr (10/min with a key) |

Mechanics proposes and explains; statistics ranks and prunes. **A recommendation
requires both.** Mechanics alone cannot tell "reduces *their* healing" from "boosts
*mine*"; statistics alone cannot tell counterplay from correlation.

## What the data supports

**Hero signature is the strongest signal available**, and it exists for every hero.
Lift over global pick-share, current patch, high badge:

```
Ivy         Extended Magazine +85   Titanic Magazine +85   Tesla Bullets +83
Venator     Hollow Point +85        Battle Vest +76        Ballistic Ench. +70
Lady Geist  Radiant Regen +81       Mystic Regen +77       Berserker +64
Vindicta    Sharpshooter +75        Long Range +73         High-Velocity +57
Seven       Escalating Exposure +61 Spirit Lifesteal +55   Mystic Vuln. +52
Paradox     Echo Shard +61          Slowing Hex +52        Headshot Booster +50
```

**Reactions are minable, not authored.** A query that was given no hypothesis
returned Unstoppable as the top Seven purchase when an enemy owns Knockdown:

```
enemy has NO Knockdown  →  Seven buys Unstoppable  31.9%   (n=228,606)
enemy HAS Knockdown     →  Seven buys Unstoppable  44.8%   (n=146,781)
                                                    +12.9pp
```

**Matchup lift is real but an order of magnitude weaker** than hero signature — Haze
into Abrams in lane: Weakening Headshot +3.5, Toxic Bullets +2.1.

## Constraints

**Live in-match telemetry is a dead end.** `/v1/matches/active` returns only
`account_id`, `hero_id`, `team` per player — no items, no clock (`duration_s` was null
across all 150 live matches sampled), and the pool is the in-game watch tab, capped at
200 matches. Real in-match state needs `/v1/matches/{id}/live/url` plus a Source 2
demo parser, rate-limited to **2 requests per hour**. Counter advice does not need it:
the enemy lineup is known at draft, and the player can state the situation in chat.

**Scope collapses fast.** Sample sizes for Haze vs Abrams, current patch, high badge:

| scope | denom | usable |
| --- | --- | --- |
| lane duel | 2,897 | yes — strongest lift |
| anywhere on enemy team | 8,234 | yes — lift roughly halves |
| 2-hero composition | 1,729 | marginal |
| 3-hero composition | 9 | no |
| 5-hero composition | 0 | no |

Team-composition advice can only ever be an aggregation of per-enemy results, never a
query.

**Patch windows trade freshness against sample.** Lift is stable from ~19 days out and
collapses at 7 (Weakening Headshot fell to +0.0, Crippling Headshot flipped to −1.5).
Policy: scope to the current patch when the sample clears roughly denom ≥ 2,500 and
n ≥ 250; otherwise widen to prior patches and **say so in the answer**. Mechanics are
always current regardless — only the ranking degrades.

**Asset freshness is currently wrong for this.** `asset_service.py` caches item and
hero assets on a 7-day TTL, but patches have shipped a day apart (06-30, 07-01). Item
properties must be invalidated when a new `patch_event` appears, otherwise the
mechanical layer — the half users will trust most — can be a week stale.

## Tool surface

The coach gets **primitives it composes per situation**, not answer-shaped tools:

| tool | returns |
| --- | --- |
| `get_hero_mechanics(hero)` | abilities with their properties — channel times, radii, heal factors |
| `get_item_mechanics(item)` | what an item does, in numbers |
| `find_items_by_effect(effect)` | items whose properties match an effect, e.g. "stun immunity" |
| `get_hero_item_stats(hero, ...)` | signature, matchup lift, and the player's own history |

A tool such as `get_counter_items(my_hero, enemy_hero)` was rejected. It expresses one
of the six scenario classes above and has nowhere to put the others — "midboss in 90
seconds" has no parameter to land in — so the surface would grow a tool per scenario,
each needing its own eval.

A convenience tool alongside the primitives was also rejected. Returning a confident
ranked answer makes it the cheapest call for the model, so it gets used for situations
it does not fit, silently discarding the situational context that made the question
worth asking. Every answer should be composed.

**Consequence:** answer quality moves from the data layer into
`app/instructions/coach_agent.md`. A wrong recommendation becomes a prompt problem
rather than a query problem, which is harder to isolate. Eval cases under `tests/eval`
need to cover several scenario classes, not only the lane matchup, or this shift goes
unmeasured.

## Where mechanics live

Mechanics are normalized into the warehouse rather than read from the per-item disk
cache in `asset_service`, following the existing
`source_snapshot → normalize_* → read_latest_*` pattern used by every other analytics
surface.

The disk cache stores one file per item *previously fetched*, which is adequate for
single lookups and wrong for the queries this design depends on. `find_items_by_effect`
must scan all items to answer, and mining prunes candidate pairs by matching properties
across both sides — both are scans or joins, and both would be either 173 cold HTTP
calls or silently incomplete against a partial cache.

Sync cost is small: `/v1/assets/items` returns all 726 entries (items, abilities,
weapons) in a single request, and `/v1/assets/heroes` likewise. Two calls, not one per
item.

Shape: roughly 173 shopable items and 200 abilities belonging to playable heroes, with
349 distinct item property keys and 1,281 distinct ability property keys. The long tail
of ability keys is plumbing (cooldowns, cast times, radii); only a minority carry threat
meaning.

Freshness is governed by patch detection, not a TTL — see the asset-freshness note under
Constraints.

## Rank scoping

Recommendations are sourced from **high badge (90+)**; the player's own bracket is used
only as the comparison. The gap between the two is the coaching content.

The two are not interchangeable. Rank-matched data describes what is *normal* at a
bracket, not what is *correct*. Measured for Haze into Abrams in lane, current patch:

| band | denom | Weakening HS | Crippling HS | Toxic Bullets |
| --- | --- | --- | --- | --- |
| badge 55–75 | 3,692 | **−0.6** | +0.0 | +2.6 |
| badge 90+ | 2,897 | **+2.0** | +0.5 | +2.4 |

Players below high badge largely do not adapt their anti-heal buys into a sustain
bruiser. A recommender ranking on the player's own bracket would conclude Weakening
Headshot is not a counter to Abrams, and hand the bracket's blind spot back as advice.

Sample size is not a reason to prefer either band — the lower bracket has *more* data,
not less.

## Post-match review

The recommendation layers describe what strong players do. Post-match review is the
only part that says whether *this* player does it, which makes it the one place a
recommendation can be checked against reality rather than assumed useful.

Form: compare the player's own purchases against the high-badge baseline for the
matchups they actually faced. *"You bought Toxic Bullets in 3 of 8 lanes against a
sustain hero; high-badge Hazes buy it in 11% of those lanes."* This is a join between
local `item_purchase` and the baselines the signature sync already produces — no new
upstream data.

`item_purchase` holds purchases for **all** players in a hydrated match, not just the
account being coached (195 distinct accounts across 20 matches). Enemy builds in the
player's own history are therefore available, enabling the personal form of a mined
reaction: *"they bought Knockdown in 6 of your last 20 games and you never answered
it."*

**Prerequisite: hydration coverage.** Match history currently runs well ahead of
hydration — 246 rows in `player_match` against 20 in `match_metadata`. Review quality
is bounded by the hydrated count, not the history count. `/v1/matches/metadata` accepts
bulk `match_ids` at 10 req/min, so backfilling the full history is a handful of
requests rather than one per match.

## Disclosure

Every statistic carries its patch window, rank bracket, and sample size. Below the
sample floor the coach declines to rank rather than reporting a weak number.

Attribution is not a caveat here, it is part of the claim. Under the rank decision
above, the *normal* case is a recommendation drawn from badge 90+ while the player sits
lower — so "44.8% of Sevens buy Unstoppable into Knockdown" is a statement about
high-badge players, and presenting it unattributed to a badge-64 player states
something different from what was measured. Disclosing only on degradation would
suppress exactly the common case.

Declining below the floor is warranted because thin samples have produced confident
reversals: Crippling Headshot moved from +1.4 to −1.5 on window width alone.

Mechanics need no attribution — "Knockdown applies stun, Unstoppable grants stun
immunity" holds at every bracket and patch. Answers should therefore lead with the
mechanism and follow with the evidence, so provenance attaches to the statistical half
only and does not bury the advice.

Unlike the other decisions recorded here, this one is presentation-layer and cheap to
revise; it does not constrain schema or tool signatures.

## Confounds already found

Three separate metrics have looked like signal and were not. Any new metric should be
assumed guilty until it has a matched baseline.

1. **Item win rate** — see ADR-0001.
2. **`min_enemy_networth` as a proxy for "enemy is fed"** — selects for long games.
   Top "counters" to a fed Haze came back as Refresher +33, Transcendent Cooldown +34,
   Boundless Spirit +25: tier 4/5 items everyone owns at 45 minutes. Controlling for
   duration recovers some real signal (Unstoppable +5.7, Indomitable +4.3) but
   residual own-networth correlation remains.
3. **Item→item reactions without duration control** — the Knockdown query also
   surfaced Boundless Spirit +9.0 and Refresher +7.4, because Knockdown is a late-tier
   item and its presence implies a longer game.

Fed-ness is best handled mechanically anyway: a fed Haze threatens the same way as a
poor one, so fed-ness raises the *urgency* of counters the mechanical layer already
identified, rather than changing which ones apply.

## Roadmap

**v1 — mechanics + hero signature.** Expose item and ability mechanics as coach
primitives (`get_hero_mechanics`, `get_item_mechanics`, `find_items_by_effect`), plus
the 39-call hero signature sync. This is the unblocker: the coach currently has lore
where it needs mechanics — its entire knowledge of Counterspell is *"a Tier 3 Vitality
Item that can be purchased from the Shop for 3,200."*

**v2 — mined reactions.** The `/v1/sql` pipeline, mechanics-pruned, with duration and
networth controls and significance testing. Materialised into the warehouse.

**Full picture — the goal, not optional.** The system is only useful at full coverage:

| dimension | v1 | full |
| --- | --- | --- |
| heroes | all 38 | all 38 |
| threat axes | sustain only | all ~8 — mobility, CC, burst, resist, … |
| reactions | none | ~40–60 reactive items × 173 × 38, mechanics-pruned |
| scope | hero-intrinsic | + lane duel, + anywhere-on-team |
| situational | none | midboss timing, fed-relative-to-me, objective state |

The situational dimension is already available: `match_player` exposes
`mid_boss.destroyed_time_s`, `objectives.*`, `death_details.*`, and
`stats.heal_prevented` — which measures anti-heal effectiveness *directly* rather than
inferring it from pick-share.

**Known blockers, all small:** obtain a `DEADLOCK_API_KEY` (30× SQL throughput — 20
req/hr → 10 req/min; already read at `config.py:71` and sent at `api.py:31`, but
missing from `.env.example`); build matched-baseline controls; add significance
testing.
