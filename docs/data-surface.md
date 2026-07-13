# Data Surface Audit

Audit date: July 9, 2026

This document reflects the public Deadlock data surface inspected before implementing ingestion. The goal is to design the coach around real inputs, not assumed ones.

## Sources inspected

- [Deadlock API homepage](https://deadlock-api.com/)
- [Deadlock API OpenAPI spec](https://api.deadlock-api.com/openapi.json)
- [Deadlock API SQL table catalog](https://api.deadlock-api.com/v1/sql/tables)
- [Deadlock API unified patch feed](https://api.deadlock-api.com/v2/patches)
- [Deadlock API data dumps page](https://deadlock-api.com/data-dumps)
- [Deadlock API GitHub monorepo](https://github.com/deadlock-api/deadlock-api)
- [Deadlock API generated clients repo](https://github.com/deadlock-api/openapi-clients)

## Confirmed public inputs

### Fully available now

- Player match history: `/v1/players/{account_id}/match-history`
- Match metadata: `/v1/matches/{match_id}/metadata`
- Hero analytics: `/v1/analytics/hero-stats`
- Game analytics: `/v1/analytics/game-stats`
- Item analytics: `/v1/analytics/item-stats`
- Item flow analytics: `/v1/analytics/item-flow-stats`
- Ability order analytics: `/v1/analytics/ability-order-stats`
- Build item analytics: `/v1/analytics/build-item-stats`
- Hero build analytics: `/v1/analytics/hero-build-stats/{hero_id}`
- Hero ban analytics: `/v1/analytics/hero-ban-stats`
- Hero combination analytics: `/v1/analytics/hero-comb-stats`
- Hero counter analytics: `/v1/analytics/hero-counter-stats`
- Hero synergy analytics: `/v1/analytics/hero-synergy-stats`
- Badge distribution analytics: `/v1/analytics/badge-distribution`
- Player performance curve: `/v1/analytics/player-performance-curve`
- Player stats metrics: `/v1/analytics/player-stats/metrics`
- Hero scoreboard: `/v1/analytics/scoreboards/heroes`
- Player scoreboard: `/v1/analytics/scoreboards/players`
- Unified patch feed: `/v2/patches`
- Leaderboards: `/v1/leaderboard/{region}`
- Hero-specific leaderboards: `/v1/leaderboard/{region}/{hero_id}`
- Public build search: `/v1/builds`
- Player enemy stats: `/v1/players/{account_id}/enemy-stats`
- Player mate stats: `/v1/players/{account_id}/mate-stats`
- Player MMR history: `/v1/players/{account_id}/mmr-history`
- Hero MMR history: `/v1/players/{account_id}/mmr-history/{hero_id}`
- Batch hero MMR: `/v1/players/mmr/{hero_id}`
- SQL catalog and schema inspection: `/v1/sql/tables`, `/v1/sql/tables/{table}/schema`
- Database dumps for offline analysis: [data dumps](https://deadlock-api.com/data-dumps)

### Partially available or constrained

- Account stats: `/v1/players/{account_id}/account-stats`
  - Patreon/bot-friend gated, so public access is not universal.
- Player card: `/v1/players/{account_id}/card`
  - Also Patreon/bot-friend gated, so it cannot anchor the core product path.
- High-MMR player resolution
  - Leaderboards expose `possible_account_ids`, which is useful but sometimes ambiguous.
- Full match-history coverage
  - The live API notes that `/v1/players/{account_id}/match-history` is only guaranteed to be full and most up to date when the account is friends with one of the API bots. Otherwise it falls back to stored ClickHouse history.
- Patch-over-patch analytics
  - The API exposes timestamps broadly, but not every endpoint is patch-keyed. We need our own patch windows and snapshots.
- Pro mirror cohorts
  - Buildable from leaderboard candidates plus match history and metadata, but cohort resolution is an app concern.
- Matchup and cohort baselines
  - Supported by hero/item analytics and filters, but not already assembled into a coaching baseline model.
- Manual notes and goal tracking
  - Not provided upstream; must be local product memory.

### Missing or app-owned

- Durable player goals and preferences
- Experiment hypotheses and notes
- Reproducible report history
- Patch-adaptation verdicts for the player's hero pool
- Explanations for stale habits or timing misses
- Clean player-to-pro identity mapping confidence model

## Feature support matrix

| Product capability | Status | Why |
| --- | --- | --- |
| Personal player model | Partial | Public match history and metadata cover outcomes, heroes, timings, and trends, but long-term memory is app-owned. |
| Pro / high-MMR build comparator | Partial | Leaderboards plus match metadata support this, but account resolution and cohort selection need local logic. |
| Meta shift forensics | Partial | Patch notes and analytics are available; patch-version baselining and causal comparison must be built locally. |
| Recommendation engine | Partial | Inputs exist, but synthesis and explainability are product logic. |
| Weekly coaching report | Full app-side | Raw ingredients exist; report generation is our responsibility. |
| Hero Lab | Full app-side | Match history, metadata, analytics, and leaderboards are enough for a strong first version. |
| Patch adaptation report | Full app-side | Requires local snapshots keyed to patch windows. |
| Build experiment tracker | Full app-side | Needs local experiment memory linked to subsequent matches. |
| Manual goals / notes | Planned locally | No upstream equivalent. |

## Important implementation implications

1. We should ingest and snapshot patch notes ourselves.
2. We should persist raw match metadata because it contains item purchases and stat buckets that are expensive to reconstruct later.
3. We should version our own analytical runs by patch window and snapshot set.
4. We should separate local memory from public telemetry so preferences and coaching goals stay durable even if the upstream shape changes.

## Current repo coverage gap

As of July 9, 2026, the repo still only normalizes and exposes a narrow slice of the available public surface:

- normalized today:
  - patch feed
  - leaderboard snapshots
  - player match history
  - per-match metadata hydration
- only lightly exposed to the coach today:
  - live patch feed fallback
  - live global hero stats
- available upstream but still missing in our ingestion and warehouse flow:
  - game analytics
  - item analytics and item-flow analytics snapshots
  - ability-order analytics
  - hero counter / synergy / combination analytics
  - hero build analytics and build-item analytics
  - badge distribution and scoreboard endpoints
  - player enemy / mate / MMR helper endpoints
  - versioned asset and generic-data ingestion for more reliable game-mechanics grounding

That means most current product misses are not because the upstream API lacks data. They are mostly because we have not yet turned those surfaces into durable local evidence the coach can query reliably.
