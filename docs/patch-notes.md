# Patch Notes (Steam ISteamNews)

Deadbase can ground the coach in **official Deadlock patch notes** pulled from
Valve's Steam news API. This lets the coach answer questions like *"what changed
in the last patch?"* or *"any recent Abrams changes?"* from real IceFrog notes
instead of the model's memory.

## Source

- **Endpoint:** `GET https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/`
- **App:** Deadlock, Steam AppID `1422450`
- **Auth:** none required. The endpoint is public. `STEAM_API_KEY` is optional and
  is only sent if set (useful later for key-gated Steam endpoints).
- **Filtering:** only posts tagged `patchnotes` (or, as a fallback, posts in the
  `steam_community_announcements` feed) are kept. General announcements are
  skipped unless you pass `--include-all-news`.

Patch notes are **public announcements**, cached **locally only** (in your own
SQLite warehouse). Nothing is uploaded or shared. Use is governed by the
[Steam API Terms of Use](https://steamcommunity.com/dev); an occasional local
sync of public data for a personal tool is well within normal use.

## How it works

```
deadlock-coach sync steam-patches
        │
        ├─ 1. GET Steam news for appid 1422450 (maxlength=0 -> full body)
        ├─ 2. Keep only posts tagged "patchnotes"
        ├─ 3. Upsert each into the patch_event table (dedup by Steam gid)
        └─ 4. Report how many were stored

chat time:
   coach ──calls──> get_patch_context() ──reads──> patch_event ──> grounded answer
```

Key points:

- **Manual, pull-on-demand.** Nothing syncs automatically — not on server start,
  not when you open a chat. Data is fetched **only** when you run
  `sync steam-patches`, and it persists in `data/warehouse/coach.sqlite3` until
  you re-sync or delete the DB. It goes stale until you refresh it.
- **Deduplicated.** Rows are keyed on the Steam `gid`, so re-running the sync
  updates existing entries in place rather than creating duplicates.
- **Full body stored.** Steam's full note text is stored in
  `patch_event.content_full`; the older 280-char `content_excerpt` is retained
  for backwards compatibility.
- **Shared table, multiple sources.** Steam notes (`source = "steam"`) live in
  the same `patch_event` table as the community `deadlock-api` feed
  (`sync patches`). The coach's `get_patch_context` tool reads whichever entries
  are most recent, so both sources coexist — Steam as the authoritative official
  source, the community feed as a fallback.

## Syncing

Pull the latest official patch notes (Windows / PowerShell):

```powershell
$env:PYTHONPATH = "src"
.venv\Scripts\python.exe -m deadlock_coach sync steam-patches
```

macOS / Linux:

```bash
PYTHONPATH=src .venv/bin/python -m deadlock_coach sync steam-patches
```

Options:

- `--count N` — how many recent news posts to request before filtering
  (default 20).
- `--include-all-news` — store every news post, not just patch-note posts.
- `--json` — emit a JSON result summary instead of prose.

Example output:

```
Stored 10 / 10 patch-note posts from Steam app 1422450
Request: https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=1422450&count=20&maxlength=0
Snapshot: .../data/raw/steam_news/patches/1422450/<timestamp>.json
```

> After syncing, the running backend does **not** need a restart — the coach
> reads the DB live at chat time. (A restart is only needed if you changed
> Python code, not data.)

### Keeping it fresh

There is no automatic scheduling. To keep patch notes current, re-run
`sync steam-patches` after each new patch. If you want this automated later,
wire a scheduled job (Windows Task Scheduler, cron, or the repo's `/schedule`
cloud agent) to run the command — e.g. daily.

## What changed in the codebase

| File | Change |
|---|---|
| `src/deadlock_coach/config.py` | Added `steam_api_base_url`, `deadlock_app_id`, optional `steam_api_key` to `Settings` (env-overridable via `STEAM_API_BASE_URL`, `DEADLOCK_APP_ID`, `STEAM_API_KEY`). |
| `src/deadlock_coach/warehouse_schema.sql` | Added `content_full TEXT` to `patch_event`. |
| `src/deadlock_coach/storage.py` | `_ensure_column` migration (adds `content_full` to pre-existing DBs), `normalize_steam_patch_feed()`, shared `_upsert_patch_event()` helper, epoch→ISO date normalization. |
| `src/deadlock_coach/steam_news_service.py` | **New.** `fetch_steam_patch_notes()` + `sync_steam_patches()` — fetch, filter to `patchnotes`, snapshot, and store. |
| `src/deadlock_coach/cli.py` | New `sync steam-patches` subcommand. |
| `app/tools.py` | `get_patch_context` now returns full patch bodies (`body` field, BBCode/HTML cleaned into a scannable change list, up to ~20k chars; a `truncated` flag + `note` warn the coach when a very large patch is cut so it never presents a partial list as complete). Search ranks patches by query-token overlap (title weighted above body) instead of a brittle full-string `LIKE`, so noisy or partial queries still find the right patch. |
| `tests/test_normalization.py` | Tests for Steam normalization and idempotent re-sync. |

## Configuration

All optional; defaults work out of the box. Set in `.env` only to override:

```
# STEAM_API_KEY=...            # optional; not needed for patch notes
# DEADLOCK_APP_ID=1422450      # override the Steam AppID
# STEAM_API_BASE_URL=https://api.steampowered.com
```
