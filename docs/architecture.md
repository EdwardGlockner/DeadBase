# Architecture

## Product stance

Deadlock Coach is a coaching desk and strategy lab, not a thin chat shell over public stats.

The system is organized around evidence-backed artifacts and durable player memory.

## Layers

### 1. Ingestion layer

Purpose:

- fetch raw payloads from the public Deadlock API
- support later adapters for local exports, dumps, or manual uploads
- preserve request provenance and fetched timestamps

Initial connectors:

- patch feed
- leaderboard snapshots
- player match history
- per-match metadata hydration

Future connectors:

- bulk dump importer
- manual note uploader
- alternate cohort or tournament providers

### 2. Raw snapshot layer

Purpose:

- keep exact upstream payloads for replayability
- make patch and report generation reproducible
- retain data even when normalized models evolve

Filesystem shape:

```text
data/
  raw/
    deadlock_api/
      patches/
      leaderboard/
      players/
      matches/
      analytics/
```

Each snapshot gets:

- timestamped file path
- content hash
- request URL
- provider name
- entity type and entity key

All of that metadata is also registered in the warehouse.

### 3. Normalized warehouse

Primary file:

- `data/warehouse/coach.sqlite3`

Why SQLite first:

- zero extra dependency to bootstrap the repo
- easy local inspection during development
- enough for early coaching and reporting workflows
- patch snapshots, joins, and report lineage fit well at this stage

Core tables:

- `source_snapshot`
- `patch_event`
- `player_match`
- `match_metadata`
- `match_participant`
- `item_purchase`
- `stat_bucket`
- `leaderboard_snapshot_entry`
- `artifact_run`
- `analytics_snapshot`

This schema intentionally stores both normalized columns and raw JSON text for fields that may evolve upstream.

### 4. Local memory layer

Primary file:

- `data/memory/player_memory.sqlite3`

Purpose:

- player profile
- long-term goals
- recurring leaks
- preferred heroes and playstyle
- experiment records
- coach notes

Core tables:

- `player_profile`
- `saved_experiment`
- `coaching_note`
- `preference`

This separation keeps coaching memory distinct from fetched telemetry.

### 5. Artifact layer

Generated under:

- `artifacts/generated/`

First-class artifact types:

- weekly-coaching-report
- hero-dossier
- patch-adaptation-report
- pro-mirror-report
- build-experiment-report
- next-five-games-plan
- meta-shift-forensic-memo

Every artifact run should record:

- source snapshot IDs used
- patch context used
- generated timestamp
- output path
- generator version

### 6. Snapshot and versioning strategy

This is critical for the product.

Rules:

1. Raw responses are immutable snapshots.
2. Every normalized row points back to a `source_snapshot`.
3. Patch feed entries are stored independently from analysis runs.
4. Report generation stores the exact snapshot set it used.
5. Patch windows are app-owned labels derived from the patch feed and persisted in artifact metadata.

This makes it possible to answer:

- what changed before and after a patch
- which recommendation was generated from which evidence
- whether a build recommendation came from stale data

### 7. Caching strategy

- Raw payloads are cached by snapshot, not overwritten in place.
- Repeated fetches still create provenance records, but dedupe can be added later by content hash.
- Analytics endpoints with expensive filters should also be persisted as raw query snapshots under `data/raw/deadlock_api/analytics/`.
- Future HTTP cache metadata can be added under `data/cache/http/`.

## What the first scaffold deliberately does not do yet

- no UI
- no recommendation scoring model
- no patch-window inference engine
- no dump importer
- no report renderer beyond artifact registry and storage hooks

That is intentional. The first milestone is to make the data model and evidence trail solid enough that those features can be added without reworking the foundation.

