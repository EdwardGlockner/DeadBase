# Retrieval eval set

A labelled set of 50 real coaching questions with known-good retrieval targets,
built for [#25](https://github.com/EdwardGlockner/DeadBase/issues/25) so that
[#17](https://github.com/EdwardGlockner/DeadBase/issues/17) can pick a retrieval
architecture on evidence rather than on argument.

- `retrieval-eval-set.json` — the set.
- `score.py` — the scorer (stdlib only; `python3 docs/eval/score.py --selftest`).

**Do not baseline the current implementation against this.** The FTS5 index over
2,226 wiki pages is being deleted by
[#16](https://github.com/EdwardGlockner/DeadBase/issues/16), and the two
hand-found failures this ticket originally named were voice-line hits that go
with it. The set scores whatever replaces it.

## What a target is

Not "which chunk of prose should come back" — that corpus is gone. A target is
**which entities and rows a question should resolve to**. Targets are flat
strings so scoring is set arithmetic:

| Form | Means | Example |
|---|---|---|
| `hero:<id>` | a hero in the asset projection | `hero:72` (Billy) |
| `item:<id>` | a shopable item in the projection | `item:1378931225` (Metal Skin) |
| `ability:<id>` | a hero ability | `ability:1080948381` (Fixation) |
| `analytics:<endpoint>?<params>` | an analytics snapshot row set | `analytics:hero-counter-stats?enemy_hero_id=1` |
| `player:<table>?<params>` | rows from the player's own history | `player:match_history?hero_id=72&window=20` |
| `asset:<family>@<version>` | a versioned asset snapshot, or `asset:diff@A..B` | `asset:diff@6684..6689` |
| `patch:<yyyy-mm-dd>` | a `/v2/patches` entry | `patch:2026-08-22` |
| `prose:<slug>` | a curated note | `prose:lane-phase` |
| `provenance:<facet>` | what our own store knows about itself | `provenance:sync_state` |

`*` globs, so `hero:*` matches any hero and `item:*?item_tier=5` any tier-5 item.

Each question splits its targets two ways:

- **`must`** — the answer is wrong without these. Recall is measured over them.
- **`may`** — legitimately supporting; retrieving them is neither rewarded nor
  punished. This is where #12 rule 1's "at most one personalised closing
  sentence" lives: the personal rows are `may`, the generic core is `must`.

Anything retrieved that is in neither bucket is **noise**.

## Deliberate inclusions

**12 of the 50 are `prose_gap: true`** — questions with no numeric answer
("how does the soul economy work", "when should I rotate out of lane"). #16
ships the prose corpus at **zero notes**, so on day one the correct behaviour is
to retrieve whatever rows exist and **name the missing surface** (#12 rule 5),
never to invent the mechanism. These twelve double as the initial backlog for the
prose corpus; they reference 8 distinct slugs:

`soul-economy`, `lane-phase`, `resistances`, `spirit-scaling`, `objectives`,
`jungle-farming`, `power-curves`, `bullet-resist-vs-gun-heroes`.

**5 patch-impact questions**, including `patch-03` and `patch-05`, which straddle
the 2026-08-22 boundary and require patch-stamping a player's stored matches
against the client-version timeline — #12's staleness guard as a computable fact.

**Entity resolution is tested in the question text, not in a separate field.**
`counter-03` says "Mo and Krill" (asset name: "Mo & Krill"), `counter-06` is
"grey talon vs haze who wins" with no capitals or punctuation, `patch-02`
abbreviates to "radiant regen", `build-03` lowercases "metal skin", and
`data-02` is missing an apostrophe.

**Direction matters and is scored.** `counter-01` asks who counters Infernus:
the target is `enemy_hero_id=1`, not `hero_id=1`. Reversing it answers the
opposite question with an equally plausible number — the failure mode #15 warned
about with unguarded text-to-SQL, in miniature.

## Scoring

```
python3 docs/eval/score.py predictions.json
```

`predictions.json` maps question id → a list of retrieved target ids, or
`{"targets": [...], "gap_reported": true}` for systems that signal a missing
surface.

| Metric | Definition |
|---|---|
| **must_recall** | mean over questions of (must targets hit / must targets) |
| **exact_rate** | share of questions with must_recall == 1.0 |
| **noise_rate** | mean over questions of (retrieved ids in neither bucket / retrieved) |
| **gap_detection** | over the 12 `prose_gap` questions, share where the run reported the gap |

No thresholds are set here. #17 compares architectures against each other on
these four numbers; #23 owns turning a chosen architecture's numbers into a
regression gate, along with tuning #12's claim floors (≥1 / ≥5 / ≥10) and
frequency bands (80 / 50 / 25 / 10), which this set does not attempt to fix.

**Latency is compared against ~10 ms, not 1.5 s.** #15 measured the old
per-query freshness check at 1,235 ms — ~99% of observed latency — and #16
retired it to a background job keyed on `client_version`.

## Provenance

Every hero id, item id, ability id, cost, tier and patch date was read from
deadlock-api on 2026-09-12 at `client_version` 6689 (`version_datetime`
2026-09-11T11:44:27), against `/v1/assets/heroes` (38 active heroes),
`/v1/assets/items` (173 shopable upgrades), the analytics endpoints named in the
targets, and `/v2/patches`. Nothing here is hand-written from memory — the same
rule #16 set for test fixtures, for the same reason #14 found the hard way.

Regenerate the entity facts by re-reading those endpoints; the set itself is
edited by hand.
