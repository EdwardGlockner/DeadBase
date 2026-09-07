# Per-Player Data Correctness Audit

Audit date: September 7, 2026
Ticket: [#14 Audit per-player data correctness](https://github.com/EdwardGlockner/DeadBase/issues/14)
Scope: the per-player pull only — sync, warehouse, summary aggregation, and the
player-facing tools in `app/tools.py`. Global analytics surfaces are touched only where a
player-facing tool reads them.

**This document produces evidence, not repairs. Nothing was fixed.**

## Verdict

The coach's per-player numbers are wrong, and the biggest defect is not subtle: the field
the entire outcome model is built on does not exist upstream.

`player_match.won` is `NULL` for **100% of matches** ingested through the primary path,
because `/v1/players/{account_id}/match-history` has no `won` key. Every win rate,
every "resolved" count, and every reported match outcome therefore rests on the small
metadata-hydration subset (default 20 matches) instead of the full history — even though
the correct answer is sitting unread in two other fields of the same response.

Most of the defensive language in `app/instructions/coach_agent.md` maps to a specific
defect below. The prompt is compensating for the data layer.

## How this audit was run

There was no synced account in `data/` (the directory does not exist), so a warehouse was
built from **real upstream payloads** run through the repo's own ingestion code:

| Input | Source | Size |
| --- | --- | --- |
| Match history | `GET /v1/players/4028775/match-history` | 8,814 real rows |
| Match metadata | `GET /v1/matches/{id}/metadata` ×5 (104256780, 104252368, 104228639, 104224980, 104218198) | 1,836 item rows, 60 participants |
| Item assets | `GET /v1/assets/items` | 726 entries (389 ability, 251 upgrade, 86 weapon) |
| Hero assets | `GET /v1/assets/heroes` | full |
| Schema of record | `GET https://api.deadlock-api.com/openapi.json` → `PlayerMatchHistoryEntry` | — |

Account `4028775` is the highest-match-count account on
`/v1/analytics/scoreboards/players`. Payloads were fed to `normalize_match_history()` and
`normalize_match_metadata()` unmodified, then `summarize_account()`,
`account_summary_payload()`, `get_recent_matches()`, `get_recent_item_paths()`,
`get_build_analysis()` and `build_coaching_report()` were called against the result.

Findings marked **CONFIRMED** were observed running. Findings marked **SUSPECTED** are
static reading of a path this audit did not execute.

### Ground truth for "did the player win?"

Verified against live upstream, twice:

- ClickHouse `player_match_history` defines `won` as `match_result == player_team`.
  Sample rows: `match_result=0, player_team=Team1 → won=false`;
  `match_result=0, player_team=Team0 → won=true`.
- On the 411 rows of account 4028775's history that carry a scored
  `player_match_outcome` (1 = win, 2 = loss), `match_result == player_team` agrees with
  `player_match_outcome == 1` on **411 / 411**.

So the outcome is fully derivable from the REST response the sync already downloads and
stores. It is simply never derived.

---

## Defects

Ordered by how badly each one corrupts a coaching answer.

### 1. CONFIRMED — `won` is never populated; 100% of history is stored as "unresolved"

`src/deadlock_coach/storage.py:755` writes `row.get("won")` into `player_match.won`.

The live `/v1/players/{account_id}/match-history` response has **no `won` key**. Verified
against both the OpenAPI schema (`PlayerMatchHistoryEntry` properties: `match_result`,
`player_match_outcome`, `player_team`, … — no `won`) and 8,814 live rows
(`any('won' in r for r in rows) → False`).

Observed after ingesting the real payload:

```
total rows           8814
won IS NULL          8814
won IS NOT NULL         0
```

Two fields that *do* arrive are dropped on the floor:

- `match_result` — the winning team; `won = (match_result == player_team)`, exact on 411/411.
- `player_match_outcome` — upstream's own scoring (0 invalid, 1 win, 2 loss, 3 penalized,
  4 penalized party, 5 not scored). Not in `warehouse_schema.sql` at all.

**How it surfaces:** every downstream outcome number falls back to the metadata join, which
only covers hydrated matches. Win rate becomes a statement about 20 matches no matter what
window the user asked for (defect 2), and unhydrated matches are silently reported as
losses (defect 3).

**Severity: critical.** This is the root cause of most of the rest of this list.

### 2. CONFIRMED — win rate is pinned to the hydration window, not the requested window

`src/deadlock_coach/coach_service.py:1104-1148`. Because of defect 1, `resolved_won`
resolves only through `LEFT JOIN match_participant / match_metadata`, and metadata exists
only for the `hydrate_matches` most recent matches (`DEFAULT_HYDRATE_MATCHES = 20`,
`account_service.py:20`).

Observed with 5 hydrated matches out of 8,814:

| requested window | reported | actual (from `match_result`) |
| --- | --- | --- |
| 5 | 3-2 over 5 resolved, **60.0%** | 60.0% |
| 20 | 3-2 over 5 resolved, **60.0%** | **55.0%** |
| 30 | 3-2 over 5 resolved, **60.0%** | **56.7%** |
| 100 | 3-2 over 5 resolved, **60.0%** | **56.0%** |

The number never moves. In production with the default `hydrate_matches=20`, asking for a
100-match or `full_sample` window still yields a win rate computed from at most 20 matches,
labelled with the large `total_matches`.

**How it surfaces:** "your win rate over the last 50 games is 60%" when it is 56%, and any
trend claim ("you've been better lately") is a claim about a frozen 20-match slice.

**Severity: critical.**

### 3. CONFIRMED — `get_recent_matches()` reports unresolved matches as losses

`app/tools.py:1945`:

```python
"won": bool(row["won"]),
```

`row["won"]` is `NULL` for every match (defect 1), and `bool(None)` is `False`. There is no
`resolved` flag in the returned dict, so the caller cannot tell "lost" from "unknown".
`get_recent_item_paths()` (`app/tools.py:1963`) builds on the same rows and inherits it.

Observed on the 8 most recent real matches:

```
match 104256780  stored won=None  tool reports won=False  truth=True   <-- WRONG
match 104252368  stored won=None  tool reports won=False  truth=True   <-- WRONG
match 104228639  stored won=None  tool reports won=False  truth=True   <-- WRONG
match 104224980  stored won=None  tool reports won=False  truth=False
match 104218198  stored won=None  tool reports won=False  truth=False
match 104213064  stored won=None  tool reports won=False  truth=True   <-- WRONG
match 104101364  stored won=None  tool reports won=False  truth=True   <-- WRONG
match 104090372  stored won=None  tool reports won=False  truth=True   <-- WRONG
```

Six of eight actual wins are handed to the model as losses. The model is being told,
truthfully-formatted, that the player is on an 0-8 streak.

`coach_service._load_recent_matches()` (line 738) does this correctly — it returns
`None` for unresolved. Only the `app/tools.py` copy of the query is broken, and that is the
one the agent calls.

**How it surfaces:** fabricated losing streaks; "you've lost your last N games" as a premise
for the whole answer. This is precisely the incident behind *"treat unresolved or partially
hydrated outcomes as unknown, not as losses"* in `coach_agent.md`.

**Severity: critical.**

### 4. CONFIRMED — an empty resolved sample is reported as a 0.0% win rate

`src/deadlock_coach/coach_service.py:1248` and `:1260`:

```python
win_rate=float(summary_row["win_rate"] or 0.0)
win_rate=float(row["win_rate"] or 0.0)          # per hero
```

The SQL correctly returns `NULL` via `NULLIF(COUNT(resolved_won), 0)` (line 1141). Python
then converts `None` to `0.0` — indistinguishable from a genuine 0%.

Observed with hydration removed (the state of any account synced with
`--hydrate-matches 0`, or any window whose matches predate hydration):

```
resolved_outcome_matches: 0
wins / losses           : 0 / 0
win_rate GIVEN TO COACH : 0.0
hero rows               : [('Yamato', 17, 0, 0.0), ('Mo & Krill', 3, 0, 0.0)]
focus.top_hero          : {"hero_label": "Yamato", "games": 17, "resolved_games": 0,
                           "wins": 0, "win_rate": 0.0}
TRUE win rate over same 20 matches: 55.0%
```

`account_summary_payload` emits `win_rate: 0.0` next to `wins: 0, losses: 0` and a
`focus.top_hero` carrying `win_rate: 0.0`. Nothing in the payload marks it as absent.

**How it surfaces:** *"never claim a losing streak, 0% win rate, or failed hero/build
pattern unless the resolved sample actually supports it"* — this line exists because the
tool literally emits `0.0`.

**Severity: critical.**

### 5. CONFIRMED — a single resolved match becomes a confident per-hero win rate

Same code path. With 5 hydrated matches, window 30:

```
Yamato       games=25 resolved= 4 wins= 3 win_rate= 75.0
Mo & Krill   games= 5 resolved= 1 wins= 0 win_rate=  0.0
```

`Mo & Krill: 0.0%` is one lost game out of five played. `resolved_games` is present in the
payload, but the win rate is emitted with equal prominence and no minimum-sample gate — and
`_top_reliable_hero` (`coach_service.py:704`) *sorts by `win_rate` first*, so a 1-sample
100% hero outranks a 15-sample 60% hero.

**How it surfaces:** "you're 0% on Mo & Krill, drop it" from n=1. Same prompt line as
defect 4.

**Severity: high.**

### 6. CONFIRMED — `build_coaching_report()` raises `NameError` on every call

`app/tools.py:713-723`. The signature takes no `tool_context`, but line 721 passes one:

```python
def build_coaching_report(account_id: int | None = None, window_matches: int = DEFAULT_WINDOW_MATCHES) -> dict[str, Any]:
    try:
        payload = _summary_payload(account_id=account_id, window_matches=window_matches, tool_context=tool_context)
    except ValueError as exc:
```

Observed: `NameError: name 'tool_context' is not defined`. The `except ValueError` does not
catch it, so it escapes as a tool error.

**How it surfaces:** the "what should I focus on" / report lane never returns data. Whatever
the model says in that lane is unsourced.

**Severity: high** (and trivially fixable — flagged for a build ticket, not fixed here).

### 7. CONFIRMED — 47% of `item_purchase` rows are ability points, filtered only at read time

`src/deadlock_coach/storage.py:830-855` writes every entry of
`match_info.players[].items[]` into `item_purchase`. That array interleaves item purchases
with **ability point spends**, which carry ability ids in the same `item_id` field.

Observed across the 5 real matches (1,836 rows):

```
stored item_purchase rows by TRUE upstream type: {'ability': 866, 'upgrade': 970}
```

One real player's purchase array, in order: `Exploding Uppercut` (ability, t=21),
`Exploding Uppercut` (ability, t=48), `Extra Regen` (item, t=53), `Grapple Arm` (ability),
`Sticky Bomb` (ability), `Headshot Booster` (item)…

The warehouse is the shared substrate, and it has no `kind` column. Only two read paths
filter (`coach_service.py:667`, `app/tools.py:2027`), and both do it in Python by calling
the network-backed `item_asset()` per row. Any new query over `item_purchase` leaks
abilities by default.

**How it surfaces:** *"do not present an ability name … as an item/build checkpoint."*
Directly. And see defect 8 for the leak that survives the filter.

**Severity: high.**

### 8. CONFIRMED — abilities consume the item-timing candidate budget before being filtered

`src/deadlock_coach/coach_service.py:1195-1216` takes the top
`MAX_CANDIDATE_ITEM_TIMINGS = 30` rows `ORDER BY purchases DESC` from the unfiltered
`item_purchase` table. `_select_verified_item_timings()` (line 661) *then* drops the
non-items — after the `LIMIT` has already been spent.

Ability points are bought up to 5 times per match, so abilities dominate the ranking and sit
at the top of the candidate list. Observed:

```
candidates returned by LIMIT 30 : 30
non-item candidates dropped     : 8
surviving real item timings     : 22
distinct real item_ids available: 30
```

The eight most-repeated candidates are `Flying Slash x16`, `Power Slash x16`,
`Crimson Slash x15`, `Shadow Transformation x9`, `Scorn x4`, `Burrow x4`, `Sand Blast x4`,
`Combo x4` — all abilities. Eight real items the player actually bought are truncated out of
the timing list and can never reach the coach.

**How it surfaces:** "you don't build X" when the player builds X every game; item-timing
advice drawn from a silently truncated tail.

**Severity: high.**

### 9. CONFIRMED — three real purchasable items are classified as abilities and permanently dropped

`src/deadlock_coach/asset_service.py:236-252`. `_classify_item_payload()` ignores the
authoritative `type` field that the asset payload carries (`"upgrade"` / `"ability"` /
`"weapon"`) and infers the kind from the artwork URL instead:

```python
if payload.get("ability_type") or "/abilities/" in image or "/abilities/" in image_webp:
    return "ability"
```

Running the real classifier over all 726 live asset entries:

```
('upgrade', 'item')     248
('upgrade', 'ability')    3   <-- wrong
('ability', 'ability')  389
('weapon',  'ability')   81
('weapon',  'unknown')    5
```

The three misclassified upgrades reuse hero ability art:

| id | item | image path |
| --- | --- | --- |
| 600033864 | **Majestic Leap** | `/images/abilities/lash/lash_death_slam.png` |
| 2800629741 | **Magic Carpet** | `/images/abilities/kelvin/ice_path.png` |
| 3346798998 | **Endless Magazine** | `/images/abilities/wraith_daggers.png` |

Confirmed through the live code path: `item_asset(settings, 600033864)` →
`label='Majestic Leap', kind='ability'`.

Because both item read paths `continue` on `kind != "item"`, these vanish from every item
list, timing aggregate and build spine — and the item bought *after* Majestic Leap silently
moves up into its slot in the spine.

**How it surfaces:** Majestic Leap is a common mobility buy. The coach will assert a build
spine that omits it, and can recommend buying an item the player already buys every game.

**Severity: high.**

### 10. CONFIRMED — build spines are ordered by array index, not purchase time

`app/tools.py:2015` and `src/deadlock_coach/coach_service.py:831` both sort by
`purchase_index ASC` — the position in the upstream `items[]` array — which is **not**
monotonic in `game_time_s`.

Observed in the real payloads: 12 of 60 player-match item arrays have at least one adjacent
pair out of chronological order, e.g. index 26 at `game_time_s=1648` immediately before
index 27 at `game_time_s=1542`.

**How it surfaces:** "your third item is X" when X was bought fifth; build-order and timing
narratives built on a wrong sequence.

**Severity: medium-high.**

### 11. CONFIRMED — `get_build_analysis()` reports a sample size it did not use

`app/tools.py:648` sets `"matched_matches": len(matches)`, counting matches that matched the
hero filter — including those with **no item data at all** (unhydrated matches contribute an
empty `items` list, not an exclusion).

Observed, window 20, hero Yamato:

```
matched_matches: 17
build_spine    : ['Restorative Shot', 'Extra Regen', 'Mystic Shot']
top_item       : {"item_label": "Restorative Shot", "purchases": 4, ...}

per-match first-3 prefixes actually observed:
  104256780 ['Restorative Shot', 'Extra Regen', 'Mystic Shot']
  104252368 ['Restorative Shot', 'Extra Regen', 'Mystic Shot']
  104228639 ['Restorative Shot', 'Extra Regen', 'Mystic Shot']
  104224980 ['Restorative Shot', 'Extra Regen', 'Mystic Shot']
  104213064 []     <-- 13 more matches with no item data
  104101364 []
  ... (13 total empty)
```

The tool announces a 17-match sample for a 4-match finding. `top_item.purchases: 4` next to
`matched_matches: 17` is the only hint, and they are separate keys.

**How it surfaces:** "across your last 17 Yamato games your opener is …" — a 4× overstated
sample, which makes a weak pattern sound established.

**Severity: high.**

### 12. CONFIRMED — the build spine carries no support count

`app/tools.py:596-608`. `_build_spine_from_paths()` returns
`branch_counts.most_common(1)[0]` and **discards the count**:

```python
branch, _count = branch_counts.most_common(1)[0]
return list(branch)
```

With a small hero-filtered sample every match can have a distinct 3-item prefix, in which
case the "spine" is whatever one match did, returned with the same shape and confidence as a
20-match consensus. `coach_service._describe_branch_from_paths()` (line 870) computes the
identical thing and *does* return `(branch, count)` — the `app/tools.py` copy drops it.

Related, same function: the fallback when no branch is found
(`app/tools.py:641`) is `[row["item_label"] for row in item_rows[:3]]`, and
`_aggregate_item_timings_from_paths` sorts by `-purchases` first (line 592). So the fallback
"build spine" is a **frequency ranking presented as a purchase order**.

**How it surfaces:** an n=1 build path stated as the player's habit; a frequency list read
aloud as "first, then, then".

**Severity: high.**

### 13. CONFIRMED — the hero filter is applied *after* the window is truncated

`app/tools.py:1988-1993` and `src/deadlock_coach/coach_service.py:804-813`. Both fetch the
last N matches and *then* filter by hero, rather than fetching the last N matches on that
hero. A player with 25 Yamato games in their last 200 gets whatever subset falls inside the
window — and `get_build_analysis` narrows further with `max(window_matches, 5)`.

Combined with defect 11 this is how a hero-specific build answer ends up resting on 1-4
matches while claiming a much larger window.

**Severity: medium-high.**

### 14. CONFIRMED — `match_participant.won` is always NULL; outcome resolution rides entirely on the team join

`src/deadlock_coach/storage.py:822` reads `player.get("won")`. Real match metadata players
have no `won` key — their fields are `team`, `player_match_outcome`, `kills`, `deaths`, … .
Observed: `match_participant.won NULL: 60 / 60`.

Resolution therefore depends solely on `participant.team = metadata.winning_team`, which
does work (`team` is populated, 0/60 NULL). But note `match_info.match_outcome` is `0` in all
five real matches while `winning_team` is 0 or 1 — so `match_metadata.match_outcome` is a
constant-0 column that would silently produce wrong answers if anything ever read it as an
outcome. Meanwhile `players[].player_match_outcome`, which *is* authoritative, is not stored.

**Severity: medium** (currently latent; upgrades to critical the moment anyone trusts
`match_outcome`).

### 15. CONFIRMED — the test fixtures encode an API shape that does not exist

`tests/test_account_service.py:57` gives match-history rows a `"won": True` key and
`:79` gives metadata players `"player_team": 0, "won": True`. The live API has neither. The
suite therefore passes on exactly the payload shape that would make defects 1 and 14
invisible, and asserts nothing about the real one.

This also hides a live falsy-zero bug at `storage.py:821`:

```python
player.get("player_team") or player.get("team"),
```

With the fixture's `player_team: 0` this evaluates to `player.get("team")` → `None`, so
Team-0 participants land with `team = NULL`. Production is saved only by the accident that
the real API uses `team` and omits `player_team` entirely.

**Severity: medium** — a process defect that guarantees the above defects survive refactors.

### 16. CONFIRMED — `avg_bought_at_s` is always null for global item stats

`app/tools.py:1011-1013` and `src/deadlock_coach/storage.py:313-317` look for
`avg_bought_at_s`, `average_bought_at_s`, `avg_purchase_time_s`. The live
`/v1/analytics/item-stats` row keys are:

```
['avg_buy_time_relative', 'avg_buy_time_s', 'avg_sell_time_relative',
 'avg_sell_time_s', 'bucket', 'item_id', 'losses', 'matches', 'players', 'wins']
```

None of the three names is present, so `avg_bought_at_s` is `None` on every row and
`item_analytics_stat.avg_bought_at_s` / `.total_bought_at_s` are NULL for every snapshot.
`purchases` likewise (no such key upstream).

**How it surfaces:** the coach cannot compare the player's item timing against the global
timing, because the global timing is never read. Any such comparison it produces is invented.

**Severity: medium.**

### 17. CONFIRMED — the SQL backfill fabricates `match_result = 0`

`src/deadlock_coach/account_service.py:190`:

```python
"match_result": _coerce_int(row.get("match_result")) or 0,
```

The `player_match_by_match` query (line 155) explicitly selects
`CAST(NULL, 'Nullable(UInt8)') AS match_result`, so every backfilled row is written to the
`NOT NULL` `player_match.match_result` column as **0 — "Team 0 won"**. Half of those are
wrong. Lines 184 and 186 do the same for `denies` and `last_hits` (NULL → 0), which then
average into `avg_*` stats.

`match_result` has no reader today, which is exactly why this is dangerous: defect 1's
obvious fix is to derive `won = (match_result == player_team)`, and doing so would
immediately turn these fabricated zeros into confident wrong outcomes.

**Severity: medium now, critical on the day defect 1 is fixed.**

### 18. CONFIRMED — no match-mode or scored-match filtering anywhere

Nothing in `summarize_account()`, `_load_recent_matches()` or `get_recent_matches()` filters
on `game_mode`, `match_mode`, `team_abandoned`, `abandoned_time_s`, or
`player_match_outcome`. `_GAME_MODE_MAP` / `_MATCH_MODE_MAP` (`account_service.py:38-63`)
exist only to decode the SQL variant's strings.

Observed in the real history: 8,198 Unranked and 616 Ranked matches pooled into one win
rate. Upstream also emits `player_match_outcome = 5` ("not scored", 3 rows) and `3`
("penalized", 1 row) which are counted as normal games. Sandbox, CoopBot, HeroLabs and
Street Brawl would be pooled the same way.

**How it surfaces:** "your ranked win rate is X" is not a ranked win rate. Bot and sandbox
games would silently move it.

**Severity: medium.**

### 19. CONFIRMED — `sold_at_s = 0` means "never sold" but reads as "sold at 0:00"

`src/deadlock_coach/storage.py:853` stores `item.get("sold_time_s")` verbatim. Upstream uses
`0` as the sentinel for "not sold", not `NULL`. Observed: 1,497 rows at `sold_at_s = 0`, 339
at `> 0`, 0 NULL.

Separately, sold items are still counted as build checkpoints. In one real match the player
bought and later sold Sprint Boots (t=251, sold t=376), Headshot Booster (sold t=474) and
Spirit Strike (sold t=1232); all three appear in the item path as permanent purchases.

**How it surfaces:** a sold early item presented as part of the final build; any future
"did you sell this?" logic reading `sold_at_s > 0` will be right by accident and
`sold_at_s IS NOT NULL` will be wrong for everything.

**Severity: medium-low.**

### 20. CONFIRMED — hydration covers a vanishing fraction of history, and nothing says so

`DEFAULT_HYDRATE_MATCHES = 20` (`account_service.py:20`) against 8,814 history rows =
**0.23% coverage**. `sync_account()` (line 340-357) hydrates only the newest N.

Within a hydrated match the data is complete — all 5 real matches had 12/12 players with
`account_id`, items and stat buckets, so incompleteness is not per-match. It is entirely a
coverage problem, and coverage is where the aggregates get their outcomes.

`hydrated_match_count` *is* in the payload (`coach_service.py:958`), but it is a bare
integer next to `total_matches` with no ratio, and at `window_matches=5` it reads `5 / 5` —
looking like full coverage while 8,809 matches sit unhydrated behind it.

**Severity: medium.** Root enabler for defects 2, 3, 4, 5 and 11.

### 21. CONFIRMED — `focus.top_hero` is chosen by games played, ignoring whether it resolved

`src/deadlock_coach/coach_service.py:948` uses `_top_sample_hero()` (sorts by `games`), not
`_top_reliable_hero()` (line 704, prefers `resolved_games > 0`). Observed with zero
hydration, `focus.top_hero` is `{"hero_label": "Yamato", "games": 17, "resolved_games": 0,
"wins": 0, "win_rate": 0.0}`.

`get_comparison_context()` (`app/tools.py:670`) and `get_hero_pool_analysis()` (line 526)
both hand this straight to the model as the anchor for comparison and hero-pool advice.

**Severity: medium.**

### 22. SUSPECTED — asset-lookup failure silently empties every item surface

`asset_service.py:220-231`. `_load_item_payload()` swallows `RuntimeError` and returns
`None`, which `_classify_item_payload()` maps to `"unknown"`, which both read paths drop.
The lookup is one uncached HTTP call **per distinct item id** against
`/v1/assets/items/{id}`.

So a rate limit, an outage, or a new patch introducing unknown ids does not degrade the item
data — it deletes it, with no error and no note in the payload. The coach receives
`item_timings: []` and `build_spine: []` and cannot distinguish that from "this player has
no consistent build".

Not observed live (the audit pre-populated the asset cache to keep the run offline), but the
code path is unambiguous.

**Severity: medium-high if it fires.**

### 23. SUSPECTED — unresolvable ids reach the coach as `"Item 3862866912"`

`asset_service.py:255-268`. `item_asset()` falls back to `label = f"Item {item_id}"`. In the
two player-facing read paths this label is unreachable (those rows are dropped as
`"unknown"`), but `_item_stats_rows()` (`app/tools.py:1000`) and `_item_flow_rows()`
(line 1055) call `item_label()` with **no kind check**, so a failed asset lookup there
surfaces the raw id as an item name.

The upstream analytics feeds themselves are clean — `/v1/analytics/item-stats` returned 156
rows, all `type: upgrade`; `/v1/analytics/item-flow-stats` returned 596 nodes, all
`type: upgrade` — so this is a lookup-failure path, not a contamination path.

*"do not present an … unknown asset id … as an item/build checkpoint"* points here.

**Severity: medium.**

### 24. SUSPECTED — empty samples are floored into confident zeros rather than nulls

The `max(x, 1)` denominator guard appears at `app/tools.py:937, 942, 1014, 1019, 1105,
1132`, `analytics_service.py:148, 149, 223, 224, 340, 357`, and
`app/tools.py:588`. None can divide by zero — but each converts "no sample" into a
well-formed `0.0` that is typographically identical to a real measurement. Defect 4 is this
same pattern in the one place it was observed firing.

**Severity: low individually, systemic in aggregate.**

---

## Mapping to `app/instructions/coach_agent.md`

| Prompt guard | Defect |
| --- | --- |
| "treat unresolved or partially hydrated outcomes as unknown, not as losses" | 1, 3 |
| "never claim a losing streak, 0% win rate, or failed hero/build pattern unless the resolved sample actually supports it" | 3, 4, 5, 11, 12 |
| "do not present an ability name, unknown asset id, or obviously mixed-up label as an item/build checkpoint" | 7, 8, 9, 23 |

All three guards are compensating for defects that remain live in the data layer.

## Not investigated

This audit is partial. A later session should resume here:

- **`app/tools.py` lane routing** — `route_coaching_request` (line 2080), `inspect_local_state`
  (2051), `_resolve_account_id` / `_resolve_optional_account_id` (129, 147) and the
  `tool_context` regex parsing (104). Account misresolution would corrupt every number
  regardless of the defects above; not exercised.
- **`agent_orchestration.py` (1,007 lines)** — `build_response_envelope` and whatever
  evidence/citation shaping happens between the tool payloads and the model. Untouched.
- **`semantic_router.py` / `message_hints.py`** — which tool a question actually reaches.
- **`knowledge_base.py` (1,662 lines)** and the `docs/knowledge` retrieval path — a separate
  hallucination surface from the per-player pull, out of this ticket's scope but adjacent.
- **`get_player_performance_curve` (`app/tools.py:1479`)** and
  `_player_performance_curve_rows` (1161) — the `stat_bucket` consumer. `stat_bucket` was
  ingested and looks complete (8-12 buckets/player at ~180s cadence, last bucket at match
  end), but nothing that reads it was run.
- **`analytics_service.py` read-side** beyond the key-name check in defect 16; the
  `item_flow_*` and `hero_analytics_stat` normalizers were read, not executed.
- **The `_merge_match_history_rows` SQL-backfill path end-to-end** — defect 17 is a static
  reading of `account_service.py:190`. The backfill only fires when `/v1/sql` returns more
  rows than REST, which did not happen for the audited account, so the fabricated
  `match_result = 0` was never observed landing in the warehouse.
- **Defect 22 (asset-lookup failure) was deliberately not triggered** — the audit
  pre-populated the asset cache to stay offline. Hypothesis to test: pointing
  `DEADLOCK_API_BASE_URL` at an unreachable host should yield `item_timings: []` and
  `build_spine: []` with no error field.
- **Multi-account behaviour** — only one account was synced; `list_tracked_accounts`
  ordering and the account-selection payloads were not exercised.
- **`web/` and `server.py` surfaces** — only the agent tool path was audited.

## Reproduction

The audit harness lives outside the repo (scratch), but is reproducible in four steps:

1. `GET /v1/players/{account_id}/match-history` → feed verbatim to
   `storage.normalize_match_history()`.
2. `GET /v1/matches/{id}/metadata` for the newest 5 → feed verbatim to
   `storage.normalize_match_metadata()`.
3. Pre-populate `data/cache/assets/item-{id}.json` from `GET /v1/assets/items` to keep the
   run offline.
4. Call `summarize_account()`, `account_summary_payload()`, `get_recent_matches()`,
   `get_recent_item_paths()`, `get_build_analysis()`, `build_coaching_report()`.

Ground truth for every outcome assertion is `match_result == player_team`, cross-checked
against `player_match_outcome`.

## Sources

All primary, all fetched 2026-09-07:

- `https://api.deadlock-api.com/openapi.json` — `PlayerMatchHistoryEntry` schema
- `https://api.deadlock-api.com/v1/players/4028775/match-history` — 8,814 rows
- `https://api.deadlock-api.com/v1/matches/{104256780,104252368,104228639,104224980,104218198}/metadata`
- `https://api.deadlock-api.com/v1/assets/items` — 726 entries
- `https://api.deadlock-api.com/v1/assets/heroes`
- `https://api.deadlock-api.com/v1/analytics/item-stats`, `/hero-stats`, `/item-flow-stats`
- `https://api.deadlock-api.com/v1/sql` — `player_match_history` `won` / `match_result` /
  `player_team` semantics
- Repo source at `research/player-data-audit`
