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
