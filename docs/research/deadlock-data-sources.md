# Deadlock data sources: what exists, from whom, under what terms

Research date: 2026-09-07. Resolves issue
[#13](https://github.com/EdwardGlockner/DeadBase/issues/13).

Every claim below is tagged:

- **[V]** verified this session against a primary source (the provider's own spec,
  source code, ToS text, or a live API response). The exact request is given so it
  can be re-run.
- **[I]** inferred from a primary source but not directly stated by it.
- **[O]** open question — could not be established. Not guessed.

`docs/data-surface.md` is the prior pass. Section 7 lists, item by item, where it is
now wrong or stale.

---

## 0. Executive summary

1. **The licensing story is not uniform, and the sharpest constraint is the wiki.**
   The Deadlock Wiki is **CC BY-NC-SA 4.0** — *NonCommercial*. The repo has already
   imported 2,226 wiki pages into `docs/knowledge/_imports/wiki/` with no attribution
   or licence notice anywhere in the tree. A paid subscription tier and NC are in
   direct tension. This is the one finding that should change a plan.
2. **`deadlocked.wiki` — named in the ticket as a known source — is not a wiki.**
   It is a parked domain that 302s to an ad/survey network. The real wiki is
   `deadlock.wiki`, which the repo already uses.
3. **deadlock-api publishes no terms of service and no data licence.** The MIT licence
   in its OpenAPI `info.license` covers the *server source code*, not the data. There
   is a GDPR deletion mechanism players can invoke, which propagates a real obligation
   onto anything we cache.
4. **Steam's Web API ToU is the binding constraint on player data**, and it contains a
   clause most people miss: *"You will only retrieve Steam Data about a Steam end user
   as requested by the end user."*
5. **The upstream surface is much larger than `docs/data-surface.md` records** — 118
   OpenAPI paths, of which the doc lists ~25. Entirely missing: the whole
   `/v1/assets/*` family (33 paths, patch-versioned back 806 client versions), a
   GraphQL endpoint, a demo-file SQL query service, an MCP server, and a ~381 GB
   public Parquet snapshot bucket.
6. **Statlocker should probably be dropped as a dependency.** The single call the repo
   makes to it is to a path Statlocker's own `robots.txt` disallows, and the same data
   is now served first-party by deadlock-api.

---

## 1. deadlock-api (`api.deadlock-api.com`)

The primary source is the live OpenAPI document:

```
curl https://api.deadlock-api.com/openapi.json     # 372 KB, OpenAPI 3.1.0
```

### 1.1 Scale of the surface

**[V]** 118 paths. By group:

| group | paths | group | paths |
| --- | --- | --- | --- |
| `/v1/assets` | 33 | `/v1/leaderboard` | 4 |
| `/v1/analytics` | 20 | `/v1/servers` | 4 |
| `/v1/matches` | 20 | `/v1/builds` | 3 |
| `/v1/players` | 20 | `/v1/sql` | 3 |
| `/v1/commands` | 4 | `/v1/info`, `/v1/patches` | 2 each |
| | | `/v1/feedback`, `/v1/graphql`, `/v2/patches` | 1 each |

### 1.2 Auth and cost

**[V]** Two security schemes, both optional: `X-API-KEY` header or `api_key` query
param (`components.securitySchemes` in the OpenAPI doc). Every read endpoint answers
unauthenticated — every response quoted in this document was fetched with no key.

**[V]** A key changes rate limits only, not entitlements. The `api_keys` table
(`tools/migrations/postgres/00_create_api_key_table.sql` in the deadlock-api monorepo)
carries `data_access`, `disabled`, `esports_ingest` flags plus a companion
`api_key_limits(key, path, rate_limit, rate_period)` table — so per-key limits are
**configurable per path**, and the "Key" column in the published docs is a default,
not a guarantee.

**[V]** Money: the deadlock-api Patreon tier starts at **$1.50/month**
(`https://deadlock-api.com/patron`). Its own comparison table lists *"Full API access"*
and *"Match history & stats"* under **both** Free and Patron. What Patron buys is
ingestion priority, not API access:

> Dedicated queue with reserved resources · Faster data updates · Full match history
> from first to last game · Up to 50 prioritized accounts · Swap accounts anytime ·
> Accurate rank data from Steam

**[I]** That "up to 50 prioritized accounts" cap is a product-shaping constraint: a
public free tier with more than 50 tracked players cannot promise everyone fresh
match history at the $1.50 tier.

**[O]** How an `X-API-KEY` is obtained, what it costs, and whether a Patreon
subscription includes one. Nothing in the OpenAPI doc, the monorepo README, or the
website says. The API's only listed contact is a Discord
(`https://discord.gg/XMF9Xrgfqu`, from `info.contact`).

### 1.3 Rate limits (verbatim from endpoint descriptions)

**[V]** All limits below are transcribed from the OpenAPI `description` of each path.
The API enforces three independent buckets — per-IP, per-key, and a global bucket
shared by *all* callers.

| endpoint | IP | with key | global |
| --- | --- | --- | --- |
| all 20 `/v1/analytics/*` (**shared** bucket) | 200/min | 400/min | 2000/min |
| `/v1/sql` | 2/min, 20/hr | 10/min | 30/min |
| `/v1/sql/tables`, `/v1/sql/tables/{t}/schema` | 10/min | — | 60/min |
| `POST /v1/graphql` | 10/min | 10/10s | 100/min |
| `/v1/matches/metadata` (bulk) | 10/min | 10/10s | 100/min |
| `/v1/matches/{id}/metadata` | cache 100/s · S3 100/10s · Steam 3/hr | cache 100/s · S3 100/s · Steam 300/hr | cache 100/s · S3 700/s · Steam 1500/hr |
| `/v1/players/{id}/match-history` | 100/s; bot-friend 10/hr; `force_refetch` 1/hr | —; bot-friend 300/hr; `force_refetch` 5/hr | bot-friend 1500/hr |
| `/v1/players/{id}/account-stats`, `/card` | 5/min | 20/min & 800/hr | 200/min |
| `/v1/builds/{hero}/{build}`, `/by-author/{id}` | 20/min | 100/min | 500/min |
| `POST /v1/matches/demo/query` | 20/hr | 200/hr | 400/hr |
| `/v1/matches/{id}/live/url` | 6/hr | 20/10m, 100/hr | 100/10m, 500/hr |
| `/v1/matches/{id}/salts` | DB 100/s · Steam 10/30min | DB — · Steam 10/min | Steam 10/10s |
| `/v1/players/steam` (refresh) | 3/min + 15/hr | 10/min + 60/hr | 30/min + 200/hr |
| everything else (`/v1/builds` search, leaderboards, `/v2/patches`, `/v1/matches/active`, `/v1/players/hero-stats`, …) | 100/s | — | — |

**[V]** The 429 body is machine-readable and states the quota it tripped, so a client
can back off precisely. Observed:

```json
{"status":429,"error":{"type":"IP","quota":{"limit":2,"period":60},
 "requests":2,"remaining":0,"next_request_in":47}}
```

**[V]** The `/v1/analytics/*` bucket being **shared across all twenty endpoints** is
not obvious and matters for a batch snapshot job: 200 req/min is the budget for hero
stats *plus* item stats *plus* everything else combined, per IP.

### 1.4 Entities and fields

**Analytics (20 paths).** `hero-stats`, `game-stats`, `item-stats`,
`item-flow-stats`, `item-permutation-stats`, `ability-order-stats`,
`build-item-stats`, `hero-build-stats/{hero_id}`, `hero-ban-stats`,
`hero-comb-stats`, `hero-counter-stats`, `hero-synergy-stats`,
`badge-distribution`, `kill-death-stats`, `lane-matchup-stats`, `lane-soul-curve`,
`player-performance-curve`, `player-stats/metrics`, `scoreboards/heroes`,
`scoreboards/players`.

**[V]** Server-side cache TTLs are documented per endpoint and are **not uniform** —
`item-stats` caches for **6 hours**, while `build-item-stats`, `hero-ban-stats`,
`hero-build-stats`, `hero-comb-stats`, `hero-counter-stats`, `hero-synergy-stats`,
`player-performance-curve` and `player-stats/metrics` cache for **1 hour**, keyed on
the exact query-parameter combination. Polling faster than that returns the same bytes.

**[V]** Two analytics endpoints carry an explicit instability warning and must not be
built on without a fallback:

> **⚠️ Subject to change:** This endpoint is newly added and not yet stable. Its
> parameters, response fields and semantics may change or be removed without notice.

That warning is on `/v1/analytics/lane-matchup-stats` and
`/v1/analytics/lane-soul-curve`.

**[V]** `item-flow-stats` exposes an `adjusted_win_rate` per node — the item's win rate
standardised to the stage's net-worth-at-buy distribution, because "players who are
already ahead have more souls and buy items sooner, raw win rate is heavily confounded
by wealth". That is a confounder the endpoint already corrects for.

**[V]** `badge-distribution` has a semantic trap: `total_matches` counts matches by
*average badge*, while `unique_players` counts players by the rank Valve reported at
the end of their latest ranked match — and `unique_players` **ignores the
`match_mode` filter entirely**, always looking at ranked matches only.

**[V]** `player-stats/metrics` quantiles are DDSketch approximations with a maximum
relative error of 0.01 — not exact.

**[V]** `hero-ban-stats` excludes matches where ban extraction failed (empty
`banned_hero_ids`) — a silent, unquantified selection effect.

**Assets (33 paths) — entirely absent from `docs/data-surface.md`.**
`/v1/assets/{heroes,items,ranks,ranked-seasons,accolades,build-tags,loot-tables,
npc-units,misc-entities,generic-data,colors,fonts,icons,images,sounds,map,
client-versions,steam-info}` plus by-name/by-id/by-slot/by-type variants.

**[V]** These are parsed from the patch's own KV3 source files — the game's ground
truth, not a community transcription. `GET /v1/assets/heroes` returns 57 heroes,
1.42 MB, with per-hero `starting_stats`, `scaling_stats`, `level_info`,
`standard_level_up_upgrades`, `item_slot_info`, `cost_bonuses`, `purchase_bonuses`,
`shop_stat_display`, `complexity`, `physics`, `items`, `colors`, `images`, `tags`.

**[V]** Assets are **patch-versioned**: `GET /v1/assets/client-versions` returns **806
versions**, from 5044 to 6684, and most asset endpoints take a `client_version`
parameter. `GET /v1/assets/steam-info` reports the latest as
`client_version 6684, version_datetime 2026-08-22T10:38:36`, matching the newest Steam
patch note exactly. This is a first-class patch-diffing surface that already exists
upstream — "what changed in Hero X between patch A and patch B" is answerable without
any local snapshotting.

**Players (20 paths).** `/v1/players/{id}/match-history`, `/enemy-stats`,
`/mate-stats`, `/rank`, `/rank/image`, `/account-stats`†, `/card`†,
`/v1/players/hero-stats`, `/v1/players/steam`, `/v1/players/steam-search`,
`/v1/players/rank/image`. († Patreon + bot-friend gated.)

**[V] Six player endpoints are now deprecated** and `docs/data-surface.md` still lists
three of them as fully available. Verbatim from the spec:

> **Batch MMR (Deprecated).** Deprecated. The MMR estimate is gone, this now returns
> the rank Valve reported for each player at the end of their latest ranked match.
> Use `/v1/players/{account_id}/rank` instead.

The deprecated set: `/v1/players/mmr`, `/v1/players/mmr/{hero_id}`,
`/v1/players/mmr/distribution`, `/v1/players/mmr/distribution/{hero_id}`,
`/v1/players/{id}/mmr-history`, `/v1/players/{id}/mmr-history/{hero_id}`,
`/v1/players/{id}/rank-predict`, and the two `rank-predict/image` aliases.
Replacements: `/v1/players/{id}/rank`, `/v1/analytics/badge-distribution`, or the
`ranked_display_badge` / `ranked_delta` fields on match history.

**[V]** Ranks are no longer modelled. `/v1/players/{id}/rank` returns the rank Valve
reported at the end of the player's latest ranked match. Eternus subranks are
percentile cuts Valve recomputes daily. Unranked/placement players return
`badge=rank=subrank=0` (Obscurus) with `last_match=null`.

**Matches (20 paths).** Beyond metadata: `/v1/matches/active` (**capped at the top 200
matches**, because it is scraped from the in-game watch tab), `/v1/matches/live/urls`,
`/v1/matches/recently-fetched`, custom-lobby creation, and the demo-query service.

**[V] The demo-query service is new and absent from `docs/data-surface.md`.**
`GET /v1/matches/demo/schema` returns the queryable schema of a match's demo file —
"every entity and event table with its columns and Arrow types".
`POST /v1/matches/demo/query` submits SQL against a demo file; it is asynchronous
because "the work (download + decompress + parse + query) takes ~55s", returns a
`job_id`, and the result is a public Parquet or `.ndjson.zst` artifact.
`GET /v1/matches/demo/live/query` streams the same over SSE against a **live**
broadcast. This is per-match sub-event granularity — positions, individual events —
that no other surface exposes.

**Patches.** `/v2/patches` (unified forum + Steam), `/v1/patches` (deprecated, forum
RSS only), `/v1/patches/big-days`.

**Builds.** `/v1/builds` (search the crawled DB, 100 req/s), plus
`/v1/builds/{hero_id}/{build_id}` and `/v1/builds/by-author/{account_id}` which fetch
**live from the Deadlock Game Coordinator** and upsert into the DB — so a build that
has never been crawled is still reachable.

### 1.5 The SQL surface

**[V]** `GET /v1/sql/tables` currently exposes **13 tables**:

```
active_matches, demo_player, heroes, item_cohort_stats_net_worth_agg_v2,
item_cohort_stats_time_agg_v2, items, match_player, match_salts, player_card,
player_match_by_match, player_match_history, player_match_roster, player_match_stats
```

**[V]** `GET /v1/info` reports **28** tables in the database. The 15 not exposed to SQL
include `steam_profiles`, `leaderboard`, `hero_leaderboard`, `hero_stats_agg`,
`item_stats_agg`, `pending_matches`, `accounts_to_update`, `request_logs`.

**[V]** `SELECT count() FROM steam_profiles` returns
`{"status":400,"error":"Query execution failed. Check your SQL syntax and try again."}`.
**[I]** The route runs against a `ch_client_restricted` ClickHouse client
(`api/src/routes/v1/sql/route.rs`), and `/v1/sql/tables` is literally
`SELECT name FROM system.tables WHERE database='default' AND name NOT LIKE '%inner%'
AND engine != 'MaterializedView'` — so the 13-table list *is* the restricted user's
grant set, and the other 15 are ungranted rather than hidden.

**[V]** The query validator (same file) is a regex allowlist, not a parser:

- must start with `SELECT` or `WITH`;
- `system.*` is blocked (`\bsystem\s*\.\s*\w+`);
- these table functions are blocked: `url, file, remote, remoteSecure, input, cluster,
  clusterAllReplicas, mysql, postgresql, s3, s3Cluster, hdfs, jdbc, odbc, executable,
  mongo, sqlite, azureBlobStorage`;
- `INTO OUTFILE` blocked; comments stripped; `;` removed before execution.

Response `format` is `json` or `ndjson`.

**[V]** `match_player` now has **202 columns**, not the 186 recorded in the
`docs/data-surface.md` addendum. Columns added since: `banned_hero_ids`,
`hero_build_id`, `pregame_hero_id`, `demo_processed`, `abilities`, `final_stats`,
`upgrades.{item_id,game_time_s,sold_time_s,net_worth_at_buy}`,
`accolades.{accolade_id,accolade_stat_value,accolade_threshold_achieved}`, `mvp_rank`,
`player_tracked_stats`, `average_badge`, `ranked_type`, `rank_interval`,
`player_rank_initial_display_rank`, `player_rank_initial_flat_progress`,
`player_rank_final_flat_progress`, `player_rank_initial_calibration_games`,
`player_rank_initial_demotion_protection_games`, `player_rank_initial_win_streak`,
`hero_xp_rewards.{hero_id,xp_grant,reason}`, `first_mid_boss_time_s`,
`first_objective_destroyed_time_s`.

`pregame_hero_id` is worth calling out: **[V]** per the metadata endpoint docs it is
"the hero the player had locked before the pre-game swap window", so
`pregame_hero_id != hero_id` identifies a counter-pick swap — a signal the analytics
endpoints do not expose at all.

**[V]** Table volumes from `GET /v1/info`: `match_player` 334,125,374 rows
(1.87 TB compressed / 5.22 TB uncompressed), `player_match_history` 474,289,804 rows,
`player_match_roster` 465,253,353 rows, `active_matches` 328,409,814 rows,
`steam_profiles` 3,836,751 rows.

### 1.6 GraphQL — absent from `docs/data-surface.md`

**[V]** `POST /v1/graphql` with `{"query":"..."}`; a GraphiQL playground is served on
`GET`. Introspection returns six root fields:

| field | description (verbatim) | args |
| --- | --- | --- |
| `matches` | Match-grouped query — one node per match_id with players aggregated. | where, order_by, order_direction, limit, offset |
| `match_players` | Player-row query — one node per (match_id, account_id). | same |
| `match_history` | Player match history — one node per (account_id, match_id), from the stored `player_match_history` table (no on-demand Steam fetch). | same |
| `heroes` | All heroes for the given client version (defaults to latest), localized to `language`. Sourced from the versioned assets, not ClickHouse. | client_version, language |
| `items` | All items (abilities, weapons, upgrades) for the given client version. | client_version, language |
| `ranks` | All rank tiers for the given client version. | client_version, language |

**[I]** This is the sweet spot between the analytics endpoints and `/v1/sql`: it reaches
the same `match_player` grain with `where`/`order_by`/`limit`/`offset`, at **10 req/min
per IP** instead of `/v1/sql`'s 2 req/min — 5× the throughput, without needing an API
key. Worth evaluating before investing further in `/v1/sql` mining.

### 1.7 Bulk dumps, and an MCP server

**[V]** `https://deadlock-api.com/data-dumps` (page title *"MCP & Data Dumps"*) points
at a public S3-compatible bucket, `https://s3-cache.deadlock-api.com/db-snapshot`,
listable anonymously:

```
curl "https://s3-cache.deadlock-api.com/db-snapshot?list-type=2&max-keys=200"
```

**[V]** 147 objects, **~381 GB total**. Each table is published as a `.parquet` plus a
`.sql` schema file. Largest: `player_match_roster.parquet` 27.6 GB,
`player_match_stats.parquet` 15.6 GB, `player_match_history.parquet` 12.2 GB.
`match_player` is sharded into 105 files (`match_player/match_player_0..104.parquet`)
— shards 0–91 were last written 2026-07-11 and are effectively frozen history, while
92–104 are appended over time (104 written 2026-09-07T14:18Z). There is a DuckLake
catalog at `public/db_snapshot.ducklake`.

**[V]** Refresh cadence, read from `LastModified` on 2026-09-07: most tables were
rewritten that same day between 08:10Z and 14:18Z, several within the hour. **[I]** So
the "daily snapshots" framing on the page understates it; per-table refresh looks
roughly hourly for small tables.

**[V] The dump bucket is a *broader* surface than `/v1/sql`.** It contains tables the
SQL endpoint refuses: `hero_leaderboard.parquet` (87 MB), `leaderboard.parquet`,
`steam_profile_observed_names.parquet` (66 MB), `accounts_to_update.parquet` (86 MB),
`pending_matches.parquet`, `match_salts_rebuilt.parquet`. `steam_profile_observed_names`
in particular is historical Steam persona names — real personal data, freely
downloadable, and worth a deliberate decision before ingesting.

**[V]** There is also a hosted MCP server, quoted verbatim from the page:

> **MCP URL** `https://api.deadlock-api.com/v1/mcp` — Connect your AI assistant and ask
> questions about the data in plain language. The server is read-only, free, and needs
> no account or API key. It exposes every table in the snapshot and updates itself with
> each dump.

**[I]** "Every table in the snapshot" is a broader grant than `/v1/sql`'s 13, since the
snapshot contains 20+. Not probed this session (it rejects plain GET with 405, as
expected for streamable-HTTP MCP).

### 1.8 Freshness

**[V]** `GET /v1/info` reports `fetched_matches_per_day: 67745` and
`user_ingested_matches_last24h: 67745`. **[I]** The two being identical suggests
ingestion is entirely user-driven (submitted salts / prioritised accounts) rather than
an exhaustive crawl — which is consistent with the Patreon "prioritized fetching"
product and means **coverage is a biased sample of the playerbase, not a census**.

**[V]** `GET /v1/info/health` returns `{"services":{"clickhouse":true,"postgres":true,
"redis":true}}` — a cheap, unrate-limited liveness probe (100 req/s) worth wiring into
our sync jobs.

**[V]** Leaderboards: *"Valve updates the leaderboard once per hour."* Polling faster
is wasted.

### 1.9 Licensing and terms — the honest answer

**[V]** `info.license` in the OpenAPI doc is
`{"name":"MIT","url":"https://github.com/deadlock-api/deadlock-api/blob/master/LICENSE"}`,
and that file is a standard MIT licence, `Copyright (c) 2026 Deadlock API`. **[I]** MIT
is a *software* licence and the URL points at the server repo — it governs the code,
not the match data the service returns. Reading it as a data licence would be a
mistake.

**[V]** There is **no terms-of-service and no data-licence page**. `/terms`, `/tos`
and `/privacy` on deadlock-api.com all return 404. The only legal-ish text on the site
is the disclaimer, verbatim from `info.description`:

> _deadlock-api.com is not endorsed by Valve and does not reflect the views or opinions
> of Valve or anyone officially involved in producing or managing Valve properties.
> Valve and all associated properties are trademarks or registered trademarks of Valve
> Corporation_

**[V]** `https://deadlock-api.com/data-privacy` exists and describes a GDPR mechanism.
Verbatim:

> **Request Data Deletion** — Remove all your personal data from our systems. This will
> permanently delete all data associated with your Steam account **and block future API
> requests**, including: Match history and statistics · Profile information · Ranking
> data · Any stored preferences.
> ⚠️ Warning: This action is permanent and cannot be undone.

Processing is stated as 24–48 hours; contact `info@deadlock-api.com`.

**[I]** This has a direct consequence for us. If we cache player-level data and an
upstream player exercises deletion, deadlock-api forgets them but **our cache does
not**. Serving that stale data to a public tier would leave us holding personal data
the source has been ordered to erase, with no notification channel telling us. Any
player-level cache needs its own TTL and its own deletion path; a periodic
re-validation against upstream (a deleted account starts erroring) is the only
detection mechanism visible.

**[O] What we are actually permitted to store, cache, and serve.** No published grant
exists. Absent terms, the *upstream* licence chain governs, and that chain runs back to
Valve (§3). **This should be settled by asking the maintainer in the project Discord
before the paid tier ships**, not inferred. It is the single highest-value unresolved
item in this survey.

---

## 2. Statlocker (`statlocker.gg`)

### 2.1 What the repo uses today

**[V]** Exactly one call, at `src/deadlock_coach/asset_service.py:92`:

```python
_, payload = client.fetch_json("https://statlocker.gg/api/info/ranks-full")
```

**[V]** It returns 37 KB of rank tiers — `tier`, `name`, `color`, and image URLs. Those
image URLs point at **`assets-bucket.deadlock-api.com`**. Statlocker is republishing
deadlock-api's own asset CDN.

**[V]** deadlock-api now serves the same thing first-party at `GET /v1/assets/ranks`
("the 12 player ranks (tier, localized name, badge image URLs, hex color)"), plus
`/v1/assets/ranks/{tier}` and a rendered `/v1/assets/ranks/{tier}/{subrank}/image`.

**[I] Recommendation: replace the Statlocker call with `/v1/assets/ranks`.** It removes
a third-party dependency, removes the robots.txt problem below, and gains
patch-versioning. This is a one-line change with no downside I could find.

### 2.2 Auth

**[V]** Statlocker's API is key-gated with one open subtree. `/api/docs`, `/api/info`,
`/api/v1`, `/api/heroes` and `/api/openapi.json` all return
`401 {"error": "Missing API key", "message": "Provide a valid API key in the X-API-Key header"}`.
But `/api/info/ranks-full` and `/api/info/heroes` return 200 with no key.

**[O]** Whether the open `/api/info/*` routes are intentionally public or an oversight.
**[O]** How to obtain a Statlocker API key, and what it costs — there is no public
signup page, and `/api/docs` is itself behind the key.

### 2.3 Terms — and a robots.txt problem

**[V]** No terms page: `statlocker.gg/terms` and `/privacy` both 404, and neither
appears in `sitemap.xml` (which lists 60+ URLs). No licence statement was found
anywhere reachable without JavaScript.

**[V]** `statlocker.gg/robots.txt` opens with a binding preamble and a Cloudflare
content-signal block:

> As a condition of accessing this website, you agree to abide by the following content
> signals. […] ANY RESTRICTIONS EXPRESSED VIA CONTENT SIGNALS ARE EXPRESS RESERVATIONS
> OF RIGHTS UNDER ARTICLE 4 OF THE EUROPEAN UNION DIRECTIVE 2019/790 ON COPYRIGHT AND
> RELATED RIGHTS IN THE DIGITAL SINGLE MARKET.
>
> ```
> User-agent: *
> Content-Signal: search=yes,ai-train=no,use=reference
> Allow: /
> ```

**[V]** Further down, the site's own block:

```
User-agent: *
Allow: /
Disallow: /admin/
Disallow: /api/
Disallow: /monitoring/
```

**[V] `Disallow: /api/` covers the exact path the repo fetches.** Our client sends
`User-Agent: deadlock-coach/0.1.0` (`src/deadlock_coach/api.py:31`), which matches
`User-agent: *`.

**[V]** The file also contradicts itself on AI crawlers: the Cloudflare-managed block
has `User-agent: ClaudeBot / Disallow: /`, `GPTBot / Disallow: /`,
`Google-Extended / Disallow: /`; the site's own block below then has
`User-agent: ClaudeBot / Allow: /`, `GPTBot / Allow: /`, `Google-Extended / Allow: /`
under the comment *"AI Crawlers - Allow AI models to learn about Statlocker so they can
recommend us for Deadlock questions"*. **[I]** Two groups with the same user-agent token
is undefined behaviour in the robots spec; a crawler could justifiably take either. The
`ai-train=no` content signal is unambiguous, however, and applies to everyone.

**[I]** `ai-train=no, use=reference` reads as: do not train on this, but AI systems may
consume it as a reference at answer time. Retrieval-style use is signalled as
acceptable; building a model or a derived corpus is not. Either way, `Disallow: /api/`
means we should not be programmatically fetching `/api/*` at all.

**[V]** Statlocker is also fronted by Cloudflare and rejects non-browser fetches from
some clients (WebFetch on `statlocker.gg/community-tools` returned 403). **[I]** Any
production dependency on it is fragile independent of the licensing question.

---

## 3. Steam / Valve

### 3.1 What is reachable

**[V]** `ISteamNews/GetNewsForApp/v2/` works **without an API key**:

```
https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=1422450&count=100&maxlength=0
```

Item fields: `appid, author, contents, date, feed_type, feedlabel, feedname, gid,
is_external_url, tags, title, url`.

**[V] The feed is mostly press, not Valve.** Over `count=100`, the composition is:

| feedname | items |
| --- | --- |
| PC Gamer | 40 |
| **steam_community_announcements** | **32** |
| PCGamesN | 24 |
| GamingOnLinux | 4 |

**[V] This is a live bug in `src/deadlock_coach/steam_news_service.py`.** It calls with
`count=20` and no `feeds` parameter, so ~2/3 of the 20 items fetched are gaming-press
articles. Worse, `tags` is **absent entirely** from items in the unfiltered response, so
the `PATCH_NOTES_TAG` check never fires and everything falls through to the
`feedname == "steam_community_announcements"` branch — which keeps untagged
announcements too (e.g. *"Matchmaking Update"*, 2026-07-30, has `tags: None`).

**[V]** Adding `&feeds=steam_community_announcements` fixes both: the response then
contains only Valve posts **and** `tags` appears, correctly carrying `["patchnotes"]`.
Concrete recommendation: pass `feeds=steam_community_announcements`, and raise `count`,
since only ~1/3 of an unfiltered page is usable.

**[V]** Some tagged posts carry moderation noise alongside `patchnotes`, e.g.
`["patchnotes","mod_reviewed","ModAct_1751692459_1783626536_0","mod_require_rereview"]`
— so the tag check must be membership, not equality. The current code already does
membership; this is a note for anyone tightening it.

**[V]** Official patch cadence, from the announcements feed: 2026-08-22, 2026-08-12,
2026-07-30, 2026-07-28, 2026-07-09, 2026-07-01, 2026-06-30, 2026-06-12, 2026-06-04,
2026-05-31 — roughly every 1–3 weeks, irregular. Feed history reaches back to
2025-01-17 within `count=100`.

**[V]** The official forum RSS
(`https://forums.playdeadlock.com/forums/changelog.10/index.rss`) is **not fetchable
server-side**: it 307s into a `/.stile/challenge` JS interstitial titled *"Checking your
browser"*, for both curl and browser user-agents. **[I]** This is a real argument for
depending on deadlock-api's `/v2/patches` rather than reading the forum ourselves —
they have solved a challenge we would otherwise have to.

**[V]** `SteamTracking/GameTracking-Deadlock` on GitHub (not
`SteamDatabase/GameTracking-Deadlock`) tracks the game's shipped files;
`pushed_at: 2026-08-22T21:44:55Z`, matching the latest patch. **[V] It has no licence
file** (`license: null` via the GitHub API), so it is all-rights-reserved by default.

### 3.2 Terms of use — the binding text

**[V]** `https://steamcommunity.com/dev/apiterms`, "Last updated July 2010". The
clauses that bear on a public free tier plus paid subscriptions, verbatim:

**The grant (§2):**

> Subject to these Terms of Use, you may access the Steam Web API, implement the Steam
> Web API in your Application, and **distribute Steam Data to end users for their
> personal use via your Application**, all in accordance with the Steam Web API
> documentation.

**The clause that constrains the product most (§2):**

> **You will only retrieve Steam Data about a Steam end user as requested by the end
> user.**

**[I]** This is narrower than it first reads. It permits pulling a user's own data when
they ask. It does not obviously permit harvesting arbitrary leaderboard players'
histories to build a "pro mirror" cohort, nor pre-warming caches for players who have
not asked. Note also that deadlock-api itself operates under this clause, and its
"prioritized fetching" product — where a *player* pays to have their *own* account
fetched — is exactly the shape §2 describes.

**Storage and privacy (§2):**

> You will post a privacy policy regarding the use of nonpublic end user data
> (including such Steam Data), and you will treat the Steam Data consistent with that
> policy. […] You will inform the end user about any Steam Data you will store, and you
> will store the Steam Data in a country (or countries) identified in your privacy
> policy.

**[I]** Storing and caching are permitted, conditionally: we need a published privacy
policy that names what we store and the countries we store it in. A public tier without
one is out of compliance.

**Presentation (§2):**

> You may not present the Steam Data (or permit the Steam Data to be presented) so that
> it appears (a) that your Application is endorsed or affiliated with Valve or Steam, or
> (b) to be available from a third party.

**Rate limit (§2):**

> You are limited to one hundred thousand (100,000) calls to the Steam Web API per day.

**Attribution (§3):**

> You agree, and Valve grants you a license, to implement the Valve name(s), logo(s),
> and links to Valve (the "Valve Brand & Links") on any Web page incorporating the Steam
> Web API and/or Steam Data […] You shall not tag links to Valve hereunder with a
> "nofollow" attribute or otherwise prevent or discourage search engines from following
> or scoring the link.

**Ownership (§9):**

> The Steam Web API, Steam Data, and Valve Brand & Links are the property of Valve, and
> subject to the intellectual property rights of Valve and its licensors. […] All rights
> not explicitly granted are reserved.

**[V] Money is not addressed.** Nothing in the ToU prohibits charging for an
Application, and no clause restricts commercial use. **[I]** So a paid tier is not
forbidden on its face — but the §2 grant is only to distribute Steam Data *to end users
for their personal use*, and §9 reserves everything not granted. Selling access to
aggregated Steam Data as a dataset is a different act from letting a paying user see
their own stats, and only the latter is clearly inside the grant.

**[V]** §11 (Termination) requires, on termination, "deleting all copies of the Steam
Data" — worth knowing before building a warehouse we cannot rebuild.

**[O]** Whether these terms bind us when we call `ISteamNews` **without** a key. §2's
restrictions attach to a licensee with a key ("your API key sign up form", "keep your
Steam Web API key confidential"), but §1 defines the Steam Web APIs generally.
**[I]** The prudent reading is that they apply. Note we currently call ISteamNews
keylessly (`steam_news_service.py`), and `STEAM_API_KEY` is commented out in
`.env.example`.

**[I]** Also relevant: nearly all of our player data arrives via deadlock-api, not
directly from Valve. deadlock-api is the Steam licensee for those calls, we are its
downstream — and deadlock-api publishes no terms passing anything on to us. That gap
(§1.9) and this clause are the same open question seen from two sides.

---

## 4. The Deadlock Wiki

### 4.1 First: `deadlocked.wiki` is not the wiki

**[V]** The ticket names `deadlocked.wiki` as a known source. It is a parked domain
running an ad/survey redirector:

```
$ curl -sSI https://deadlocked.wiki/
HTTP/1.1 302 Found
location: http://survey-smiles.com
server: Cowboy
set-cookie: sid=...; domain=.deadlocked.wiki; expires=Sat, 25 Sep 2094 ...
```

With a curl user-agent it 302s to `ww80.deadlocked.wiki/?subid1=<uuid>`; with a browser
user-agent, to `survey-smiles.com`. **Do not fetch it from anything.** The real wiki is
`deadlock.wiki`, which is what the repo already uses
(`src/deadlock_coach/knowledge_base.py:19`, `app/tools.py:43`).

### 4.2 What it is

**[V]** `GET https://deadlock.wiki/api.php?action=query&meta=siteinfo&siprop=general|
rightsinfo|statistics&format=json&formatversion=2`:

- sitename `The Deadlock Wiki`, generator **MediaWiki 1.46.0**, `articlepath: /$1`,
  `scriptpath: ""` (so the API is at `/api.php`, as the repo has it).
- statistics: **56,816 pages, 880 articles, 133,209 edits, 52,568 images, 3,455 users,
  213 active users, 4 admins**.
- 70 extensions installed, including **CirrusSearch** (Elasticsearch-backed search),
  **Scribunto**, **Bucket** (structured data), **TextExtracts**, **DynamicPageList4**,
  **Kartographer**.

**[V]** Standard MediaWiki limits apply: `action=paraminfo` on `query+categorymembers`
reports `limit` `max: 500` for anonymous callers, `highmax: 5000` for accounts with
`apihighlimits`. No key is needed to read. **[O]** Whether the wiki imposes any
additional per-IP throttling beyond MediaWiki defaults.

**[V]** It is behind Cloudflare, and the challenge is **user-agent sensitive**: a
default `curl/8.x` user-agent gets a 403 managed challenge on `/api.php`, while both a
browser UA and our own `deadlock-coach/0.1.0` get 200. **[I]** Our client is fine
today, but this is a silent-breakage risk — a UA change or a Cloudflare policy change
would take out wiki ingestion with a 403 that looks like nothing else in the stack.

**[V]** There is no real `robots.txt`; `/robots.txt` resolves to a MediaWiki article
titled "Robots.txt" (because `articlepath` is `/$1`). Pages carry
`<meta name="robots" content="noindex,nofollow,max-image-preview:standard">`.

### 4.3 Licence — the sharpest constraint in this survey

**[V] CC BY-NC-SA 4.0.** Confirmed from two independent primary sources on the wiki
itself.

From the MediaWiki API `rightsinfo`:

```json
{"url":"https://creativecommons.org/licenses/by-nc-sa/4.0/",
 "text":"Creative Commons Attribution-NonCommercial-ShareAlike"}
```

From the `<head>` of every rendered page:

```html
<link rel="license" href="https://creativecommons.org/licenses/by-nc-sa/4.0/">
```

What the three terms mean for this project:

- **BY** — attribution is required on any reuse, including excerpts an agent quotes.
- **NC** — *"You may not use the material for commercial purposes."* CC defines
  commercial as "primarily intended for or directed toward commercial advantage or
  monetary compensation". **A paid subscription tier that serves wiki-derived content
  is squarely what NC prohibits.** A free tier is much easier to defend.
- **SA** — adaptations must be shared under the same licence. **[I]** If wiki text is
  transformed into our knowledge base and that knowledge base is distributed, SA
  arguably reaches it.

**[V] Current exposure.** The repo has already imported the wiki in bulk:

| location | files |
| --- | --- |
| `docs/knowledge/_imports/wiki/pages/` | 1,991 |
| `docs/knowledge/_imports/wiki/items/` | 178 |
| `docs/knowledge/_imports/wiki/heroes/` | 57 |

with `pages-manifest.json` recording each page's source URL. **[V]** A grep for
`CC BY|creative commons|BY-NC-SA|noncommercial|attribution` across the repo returns **no
licence notice and no attribution** for any of it.

**[I]** Three things follow, in order of urgency:

1. Add attribution and the licence notice to `docs/knowledge/_imports/wiki/` now. That
   is cheap and satisfies BY regardless of what else is decided.
2. Decide, before the paid tier ships, whether wiki-derived content is served to paying
   users at all. The options are: keep wiki content free-tier-only; replace it with
   `/v1/assets/*` (which is parsed from the game's own KV3 files and carries no wiki
   licence — see §1.4); or ask the wiki's admins for a licence exception.
3. **[I]** Option two is more attractive than it sounds. Hero stats, ability data, item
   costs and scaling all come from `/v1/assets/*` at higher fidelity and versioned per
   patch. What the wiki uniquely holds is lore and prose — the part least load-bearing
   for a coach.

**[O]** Whether an NC exception is obtainable. The wiki has 4 admins; no contact route
was pursued this session.

**[O]** The upstream status of the wiki's own content. Much of it derives from Valve's
game files, so the wiki's CC BY-NC-SA grant over *those* facts is itself questionable —
but that is not a defence we should build a business on.

---

## 5. Other sources found (not named in the ticket)

**[V]** deadlock-api's Patreon page names its downstream consumers: *"Data is upstreamed
to Statlocker, Tracklock, Lockblaze, or your favorite stat tracking site."*

| source | status |
| --- | --- |
| `tracklock.gg` | **[V]** live; `robots.txt` is a 53-byte AmazonAdBot stub with no general restriction. **[O]** No API investigated. |
| `deadlocklabs.gg` | **[V]** live; `robots.txt` has `Disallow: /api/` and `Disallow: /player/` for every user-agent including GPTBot/ClaudeBot. Same posture as Statlocker: the API is off-limits to crawlers. |
| `lockblaze.com` | **[V]** returned HTTP 429 on `robots.txt` — rate-limited before any assessment. **[O]** Not evaluated. |
| `SteamTracking/GameTracking-Deadlock` | **[V]** tracks shipped game files, pushed 2026-08-22. **No licence** (all rights reserved by default). |
| `SteamDatabase/Protobufs` | **[V]** referenced repeatedly by deadlock-api for decoding its `/raw` protobuf endpoints. |

**[I]** All three community trackers are downstream of deadlock-api. There is no
independent second source for Deadlock match data — deadlock-api is a **single point of
failure** for the entire product, and the whole ecosystem shares that dependency.

---

## 6. What we call today

From `src/deadlock_coach/` and `app/tools.py`:

| call site | endpoint |
| --- | --- |
| `cli.py:198`, `app/tools.py:873` | `/v2/patches` |
| `cli.py:226` | `/v1/leaderboard/{region}` |
| `account_service.py:330`, `:365` | `/v1/players/{id}/match-history`, `/v1/matches/{id}/metadata` |
| `account_service.py:115`, `:347` | `/v1/sql` |
| `account_service.py:225`, `:302` | `/v1/players/steam-search`, `/v1/players/steam` |
| `analytics_service.py:24-37` | 14 of the 20 `/v1/analytics/*` endpoints |
| `asset_service.py:69`, `:239` | `/v1/assets/heroes`, `/v1/assets/items/{id}` |
| `asset_service.py:92` | **`https://statlocker.gg/api/info/ranks-full`** ← §2 |
| `steam_news_service.py` | `ISteamNews/GetNewsForApp/v2/` ← §3.1 |
| `knowledge_base.py:19`, `app/tools.py:43` | `https://deadlock.wiki/api.php` ← §4 |

Not called at all: `/v1/graphql`, the demo-query service, the dump bucket, the MCP
server, `/v1/assets/client-versions` (and versioned asset queries generally),
`/v1/players/{id}/rank`, `/v1/analytics/lane-*`, `/v1/matches/metadata` (bulk).

**[V]** `DEADLOCK_API_KEY` is read at `config.py:71` and sent as `X-API-KEY` at
`api.py:31`, but is **still absent from `.env.example`** — the addendum in
`docs/data-surface.md` flagged this and it has not been fixed. Given §1.3 it is worth
up to 5× on `/v1/sql` and 2× on analytics, for no code change.

---

## 7. Corrections to `docs/data-surface.md`

Verified against the live spec this session. Note the version in this worktree may be
one revision behind `main`.

**Now wrong:**

1. **`/v1/players/{account_id}/mmr-history`, `/v1/players/{account_id}/mmr-history/
   {hero_id}` and `/v1/players/mmr/{hero_id}` are listed under "Fully available now".
   All three are deprecated.** The spec says the MMR estimate no longer exists. Use
   `/v1/players/{id}/rank`, `/v1/analytics/badge-distribution`, or match history's
   `ranked_display_badge` / `ranked_delta`.
2. **"`match_player` holds one row per player per match across 186 columns" — it is now
   202.** The added columns include `hero_build_id`, `pregame_hero_id`,
   `banned_hero_ids`, `accolades.*`, `upgrades.*`, `abilities`, `mvp_rank`,
   `average_badge` and nine `player_rank_*` fields.
3. **"SQL catalog and schema inspection … heavily rate limited"** — `/v1/sql/tables` and
   `/v1/sql/tables/{t}/schema` are 10 req/min per IP, not heavily limited. It is
   `/v1/sql` itself that is 2 req/min. The `data_surface.py:114` `sql_catalog`
   `EndpointSpec` note repeats this and should be corrected too.
4. **`inspect_data_surface()` reports `"audit_date": "2026-07-07"`
   (`data_surface.py:212`) while the doc header says July 9, 2026.** Both are two
   months stale; the code and doc also disagree with each other.

**Now incomplete — significant surfaces the doc omits entirely:**

5. The whole `/v1/assets/*` family — 33 paths, parsed from the game's own KV3 files,
   versioned across 806 client versions. Directly relevant to the "patch adaptation"
   work the doc says needs local snapshotting; much of it does not.
6. `POST /v1/graphql` — filterable `match_player`-grain access at 10 req/min/IP, 5×
   `/v1/sql`.
7. The demo-query service (`/v1/matches/demo/{query,schema,live/query}`) — sub-event
   granularity available nowhere else.
8. The S3 dump bucket at `https://s3-cache.deadlock-api.com/db-snapshot` — the doc links
   only the HTML page. ~381 GB of Parquet, refreshed sub-daily, containing **more tables
   than `/v1/sql` exposes**.
9. The hosted MCP server at `https://api.deadlock-api.com/v1/mcp`.
10. `/v1/analytics/lane-matchup-stats`, `/lane-soul-curve` (both flagged unstable
    upstream), `/kill-death-stats`, `/item-permutation-stats`; `/v1/patches/big-days`;
    `/v1/matches/active`; `/v1/players/hero-stats`; `/v1/servers`.
11. Per-endpoint cache TTLs (1h and 6h) and the **shared** analytics rate-limit bucket.
    Both change how a snapshot job should be written.
12. Licensing and ToS are not discussed anywhere in the doc. Given §4.3, that is the
    most consequential omission.

**Confirmed still accurate:** the `/v1/sql` and `/v1/matches/metadata` rate-limit table
in the addendum; the Patreon/bot-friend gating of `/account-stats` and `/card`; the
match-history bot-friend caveat; `DEADLOCK_API_KEY` missing from `.env.example`.

---

## 8. Known gaps and unreliability

| # | issue | evidence |
| --- | --- | --- |
| 1 | Ingestion is user-driven, so match coverage is a **biased sample**, not a census. | `/v1/info`: `fetched_matches_per_day` == `user_ingested_matches_last24h` == 67,745 **[I]** |
| 2 | Full, current match history requires the account to be friends with a bot; otherwise only stored ClickHouse history. | match-history endpoint description **[V]** |
| 3 | `/v1/matches/active` is capped at the **top 200** matches (scraped from the watch tab). | endpoint description **[V]** |
| 4 | `/v1/patches/big-days` is **manually maintained and stale** — newest entry `2026-03-11`, six months old, despite patches on 2026-08-22 etc. | live response vs. Steam feed **[V]** |
| 5 | `/v2/patches` returns only **30 entries** (20 forum + 10 Steam). It is a rolling window, not an archive — we must snapshot to retain history. | live response **[V]** |
| 6 | Forum entries in `/v2/patches` carry misleading dates: an entry titled *"06-30-2026 Update"* has `pub_date 2026-07-28T20:28:07Z`. **[I]** The RSS date tracks thread activity, not the patch. Key patch windows off Steam `date` or `/v1/assets/steam-info` `version_datetime`, not forum `pub_date`. | live response **[V]** |
| 7 | `hero-ban-stats` silently drops matches where ban extraction failed. | endpoint description **[V]** |
| 8 | `badge-distribution`'s `unique_players` ignores `match_mode` and always reads ranked. | endpoint description **[V]** |
| 9 | `player-stats/metrics` quantiles are DDSketch approximations (≤0.01 relative error). | endpoint description **[V]** |
| 10 | `lane-matchup-stats` and `lane-soul-curve` may change or be removed **without notice**. | endpoint description **[V]** |
| 11 | Many matches have no stored salts, so metadata/demo is unavailable for them. | `/v1/matches/{id}/salts` description: *"we currently fetch many matches without salts"* **[V]** |
| 12 | `hero_build_id` is the build selected **at match start** and ignores in-match changes. | metadata endpoint description **[V]** |
| 13 | deadlock.wiki's Cloudflare challenge is user-agent sensitive; a default `curl` UA gets 403. | direct test **[V]** |
| 14 | The official forum RSS is behind a JS challenge and unfetchable server-side. | direct test **[V]** |
| 15 | Statlocker is Cloudflare-fronted and rejects some non-browser clients (403). | direct test **[V]** |
| 16 | Upstream GDPR deletion silently invalidates anything we cached about that player. | `/data-privacy` **[V]**, consequence **[I]** |
| 17 | deadlock-api is a **single point of failure**; every other tracker is downstream of it. | Patreon page **[V]**, conclusion **[I]** |

---

## 9. Open questions, in priority order

1. **[O] What does deadlock-api permit us to store, cache, and serve — especially to
   paying users?** No ToS exists. Must be asked in their Discord
   (`https://discord.gg/XMF9Xrgfqu`) and the answer recorded. Blocks the paid tier.
2. **[O] Does CC BY-NC-SA 4.0 permit wiki-derived content behind a paid tier?** On its
   face, no. Decide: free-tier-only, replace with `/v1/assets/*`, or seek an exception
   from the wiki's admins.
3. **[O] Do Steam's API terms bind us when calling `ISteamNews` without a key?**
   Assume yes; the privacy-policy and Valve-attribution obligations (§3.2) are cheap to
   satisfy either way.
4. **[O] How is a `DEADLOCK_API_KEY` obtained, and what does it cost?** Undocumented.
   Worth up to 5× on `/v1/sql`.
5. **[O] Does §2's "only retrieve Steam Data about a Steam end user as requested by the
   end user" prohibit a pro-mirror cohort built from leaderboard accounts?** Affects a
   planned feature directly.
6. **[O] Are Statlocker's open `/api/info/*` routes intentional, and can a key be
   obtained?** Moot if we switch to `/v1/assets/ranks`, which we should.
7. **[O] What does the MCP server at `/v1/mcp` actually expose, and under what limits?**
   "Every table in the snapshot" would be broader than `/v1/sql`'s 13.
8. **[O] Does the wiki throttle beyond MediaWiki defaults?** Not established.
9. **[O] `lockblaze.com` was not assessed** (HTTP 429 on first contact).

---

## Appendix: reproducing this

```bash
curl https://api.deadlock-api.com/openapi.json                  # 118 paths, limits, licence
curl https://api.deadlock-api.com/v1/info                       # table sizes, ingest rate
curl https://api.deadlock-api.com/v1/sql/tables                 # the 13 queryable tables
curl https://api.deadlock-api.com/v1/sql/tables/match_player/schema   # 202 columns
curl https://api.deadlock-api.com/v1/assets/client-versions     # 806 versions
curl https://api.deadlock-api.com/v1/assets/steam-info          # latest patch build + date
curl -X POST https://api.deadlock-api.com/v1/graphql \
  -H 'Content-Type: application/json' \
  -d '{"query":"{__schema{queryType{fields{name description}}}}"}'
curl "https://s3-cache.deadlock-api.com/db-snapshot?list-type=2&max-keys=200"
curl "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=1422450&count=100&maxlength=0&feeds=steam_community_announcements"
curl -A 'deadlock-coach/0.1.0' "https://deadlock.wiki/api.php?action=query&meta=siteinfo&siprop=general%7Crightsinfo%7Cstatistics&format=json&formatversion=2"
curl https://statlocker.gg/robots.txt
curl https://steamcommunity.com/dev/apiterms
```
