from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from deadlock_coach.config import Settings


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp_slug(moment: datetime | None = None) -> str:
    return (moment or _utc_now()).strftime("%Y%m%dT%H%M%SZ")


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)


def _safe_component(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value)


@dataclass(frozen=True)
class SnapshotRecord:
    id: int
    path: Path
    fetched_at: str
    request_url: str


def _read_schema(schema_name: str) -> str:
    schema_path = Path(__file__).with_name(schema_name)
    return schema_path.read_text(encoding="utf-8")


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    """Add a column to an existing table if a prior schema version lacked it.

    `CREATE TABLE IF NOT EXISTS` never alters an already-created table, so
    additive columns need this lightweight migration for local warehouses that
    predate the column.
    """

    existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def initialize_workspace(settings: Settings) -> None:
    for directory in (
        settings.raw_dir,
        settings.cache_dir / "http",
        settings.warehouse_dir,
        settings.memory_dir,
        settings.artifact_dir,
        settings.telemetry_dir,
        settings.artifact_dir / "weekly",
        settings.artifact_dir / "heroes",
        settings.artifact_dir / "patches",
        settings.artifact_dir / "experiments",
        settings.artifact_dir / "plans",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    with closing(_connect(settings.warehouse_db_path)) as connection:
        connection.executescript(_read_schema("warehouse_schema.sql"))
        _ensure_column(connection, "patch_event", "content_full", "TEXT")
        connection.commit()

    with closing(_connect(settings.memory_db_path)) as connection:
        connection.executescript(_read_schema("memory_schema.sql"))
        connection.commit()


def save_json_snapshot(
    settings: Settings,
    provider: str,
    entity_type: str,
    entity_key: str,
    request_url: str,
    payload: Any,
) -> SnapshotRecord:
    initialize_workspace(settings)

    fetched_at = _utc_now()
    fetched_at_iso = fetched_at.isoformat()
    raw_dir = settings.raw_dir / _safe_component(provider) / _safe_component(entity_type) / _safe_component(entity_key)
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{_timestamp_slug(fetched_at)}.json"
    body = _json_dumps(payload)
    path.write_text(body, encoding="utf-8")

    sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
    with closing(_connect(settings.warehouse_db_path)) as connection:
        cursor = connection.execute(
            """
            INSERT INTO source_snapshot (
                provider,
                entity_type,
                entity_key,
                fetched_at,
                request_url,
                content_sha256,
                raw_path,
                content_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provider,
                entity_type,
                entity_key,
                fetched_at_iso,
                request_url,
                sha256,
                str(path.relative_to(settings.project_root)),
                "application/json",
            ),
        )
        connection.commit()
        snapshot_id = int(cursor.lastrowid)

    return SnapshotRecord(id=snapshot_id, path=path, fetched_at=fetched_at_iso, request_url=request_url)


def build_query_fingerprint(query_params: dict[str, Any] | None) -> str:
    body = json.dumps(query_params or {}, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def infer_query_coverage(query_params: dict[str, Any] | None) -> tuple[int | None, int | None]:
    params = query_params or {}
    for start_key, end_key in (
        ("min_unix_timestamp", "max_unix_timestamp"),
        ("min_last_updated_unix_timestamp", "max_last_updated_unix_timestamp"),
        ("min_published_unix_timestamp", "max_published_unix_timestamp"),
    ):
        start = params.get(start_key)
        end = params.get(end_key)
        if start is not None or end is not None:
            return (
                None if start is None else int(start),
                None if end is None else int(end),
            )
    return None, None


def normalize_analytics_snapshot(
    settings: Settings,
    snapshot: SnapshotRecord,
    endpoint: str,
    query_params: dict[str, Any] | None = None,
    coverage_start: int | None = None,
    coverage_end: int | None = None,
    patch_window_label: str | None = None,
) -> None:
    if coverage_start is None and coverage_end is None:
        coverage_start, coverage_end = infer_query_coverage(query_params)

    with closing(_connect(settings.warehouse_db_path)) as connection:
        connection.execute(
            """
            INSERT INTO analytics_snapshot (
                snapshot_id,
                endpoint,
                query_fingerprint,
                query_params_json,
                coverage_start,
                coverage_end,
                patch_window_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(snapshot_id) DO UPDATE SET
                endpoint = excluded.endpoint,
                query_fingerprint = excluded.query_fingerprint,
                query_params_json = excluded.query_params_json,
                coverage_start = excluded.coverage_start,
                coverage_end = excluded.coverage_end,
                patch_window_label = excluded.patch_window_label
            """,
            (
                snapshot.id,
                endpoint,
                build_query_fingerprint(query_params),
                _json_dumps(query_params or {}),
                coverage_start,
                coverage_end,
                patch_window_label,
            ),
        )
        connection.commit()


def normalize_hero_analytics_stats(settings: Settings, snapshot: SnapshotRecord, payload: Any) -> int:
    rows = payload if isinstance(payload, list) else []
    inserted = 0
    with closing(_connect(settings.warehouse_db_path)) as connection:
        connection.execute("DELETE FROM hero_analytics_stat WHERE snapshot_id = ?", (snapshot.id,))
        for row in rows:
            if not isinstance(row, dict):
                continue
            hero_id = _coerce_int(row.get("hero_id"))
            matches = _coerce_int(row.get("matches"))
            if hero_id is None or matches is None or matches <= 0:
                continue
            bucket = _bucket_text(row.get("bucket"))
            connection.execute(
                """
                INSERT INTO hero_analytics_stat (
                    snapshot_id,
                    hero_id,
                    bucket,
                    matches,
                    wins,
                    losses,
                    total_kills,
                    total_deaths,
                    total_assists,
                    total_net_worth,
                    total_last_hits,
                    total_denies,
                    total_player_damage,
                    total_player_damage_taken,
                    total_boss_damage,
                    total_creep_damage,
                    total_neutral_damage,
                    total_max_health,
                    total_shots_hit,
                    total_shots_missed,
                    raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.id,
                    hero_id,
                    bucket,
                    matches,
                    _coerce_int(row.get("wins")) or 0,
                    _coerce_int(row.get("losses")) or 0,
                    _coerce_int(row.get("total_kills")),
                    _coerce_int(row.get("total_deaths")),
                    _coerce_int(row.get("total_assists")),
                    _coerce_int(row.get("total_net_worth")),
                    _coerce_int(row.get("total_last_hits")),
                    _coerce_int(row.get("total_denies")),
                    _coerce_int(row.get("total_player_damage")),
                    _coerce_int(row.get("total_player_damage_taken")),
                    _coerce_int(row.get("total_boss_damage")),
                    _coerce_int(row.get("total_creep_damage")),
                    _coerce_int(row.get("total_neutral_damage")),
                    _coerce_int(row.get("total_max_health")),
                    _coerce_int(row.get("total_shots_hit")),
                    _coerce_int(row.get("total_shots_missed")),
                    _json_dumps(row),
                ),
            )
            inserted += 1
        connection.commit()
    return inserted


def normalize_item_analytics_stats(settings: Settings, snapshot: SnapshotRecord, payload: Any) -> int:
    rows = payload if isinstance(payload, list) else []
    inserted = 0
    with closing(_connect(settings.warehouse_db_path)) as connection:
        connection.execute("DELETE FROM item_analytics_stat WHERE snapshot_id = ?", (snapshot.id,))
        for row in rows:
            if not isinstance(row, dict):
                continue
            item_id = _coerce_int(row.get("item_id"))
            matches = _coerce_int(row.get("matches"))
            if item_id is None or matches is None or matches <= 0:
                continue
            bucket = _bucket_text(row.get("bucket"))
            connection.execute(
                """
                INSERT INTO item_analytics_stat (
                    snapshot_id,
                    item_id,
                    bucket,
                    matches,
                    wins,
                    losses,
                    purchases,
                    players,
                    avg_bought_at_s,
                    total_bought_at_s,
                    raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.id,
                    item_id,
                    bucket,
                    matches,
                    _coerce_int(row.get("wins")) or 0,
                    _coerce_int(row.get("losses")) or 0,
                    _coerce_int(row.get("purchases") or row.get("total_purchases") or row.get("item_purchases")),
                    _coerce_int(row.get("players") or row.get("unique_players")),
                    _coerce_float(
                        row.get("avg_bought_at_s")
                        or row.get("average_bought_at_s")
                        or row.get("avg_purchase_time_s")
                    ),
                    _coerce_float(
                        row.get("total_bought_at_s")
                        or row.get("total_purchase_time_s")
                        or row.get("sum_bought_at_s")
                    ),
                    _json_dumps(row),
                ),
            )
            inserted += 1
        connection.commit()
    return inserted


def normalize_item_flow_stats(settings: Settings, snapshot: SnapshotRecord, payload: Any) -> dict[str, int]:
    if not isinstance(payload, dict):
        return {"summaries": 0, "reached_columns": 0, "nodes": 0, "edges": 0}

    nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
    edges = payload.get("edges") if isinstance(payload.get("edges"), list) else []
    reached_per_column = payload.get("reached_per_column") if isinstance(payload.get("reached_per_column"), list) else []
    counts = {"summaries": 0, "reached_columns": 0, "nodes": 0, "edges": 0}

    with closing(_connect(settings.warehouse_db_path)) as connection:
        connection.execute("DELETE FROM item_flow_summary WHERE snapshot_id = ?", (snapshot.id,))
        connection.execute("DELETE FROM item_flow_reach WHERE snapshot_id = ?", (snapshot.id,))
        connection.execute("DELETE FROM item_flow_node WHERE snapshot_id = ?", (snapshot.id,))
        connection.execute("DELETE FROM item_flow_edge WHERE snapshot_id = ?", (snapshot.id,))

        for scope in ("summary", "baseline"):
            summary = payload.get(scope)
            if not isinstance(summary, dict):
                continue
            connection.execute(
                """
                INSERT INTO item_flow_summary (
                    snapshot_id, scope, wins, losses, matches, players, total_kills, total_deaths,
                    total_assists, avg_net_worth, avg_duration_s, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.id,
                    scope,
                    _coerce_int(summary.get("wins")) or 0,
                    _coerce_int(summary.get("losses")) or 0,
                    _coerce_int(summary.get("matches")) or 0,
                    _coerce_int(summary.get("players")),
                    _coerce_int(summary.get("total_kills")),
                    _coerce_int(summary.get("total_deaths")),
                    _coerce_int(summary.get("total_assists")),
                    _coerce_float(summary.get("avg_net_worth")),
                    _coerce_float(summary.get("avg_duration_s")),
                    _json_dumps(summary),
                ),
            )
            counts["summaries"] += 1

        for index, value in enumerate(reached_per_column):
            reached_matches = _coerce_int(value)
            if reached_matches is None:
                continue
            connection.execute(
                """
                INSERT INTO item_flow_reach (snapshot_id, column_index, reached_matches)
                VALUES (?, ?, ?)
                """,
                (snapshot.id, index, reached_matches),
            )
            counts["reached_columns"] += 1

        for row in nodes:
            if not isinstance(row, dict):
                continue
            column_index = _coerce_int(row.get("column"))
            item_id = _coerce_int(row.get("item_id"))
            matches = _coerce_int(row.get("matches"))
            if column_index is None or item_id is None or matches is None or matches <= 0:
                continue
            connection.execute(
                """
                INSERT INTO item_flow_node (
                    snapshot_id, column_index, item_id, wins, losses, matches, players,
                    total_kills, total_deaths, total_assists, adjusted_win_rate,
                    avg_net_worth_at_buy, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.id,
                    column_index,
                    item_id,
                    _coerce_int(row.get("wins")) or 0,
                    _coerce_int(row.get("losses")) or 0,
                    matches,
                    _coerce_int(row.get("players")),
                    _coerce_int(row.get("total_kills")),
                    _coerce_int(row.get("total_deaths")),
                    _coerce_int(row.get("total_assists")),
                    _coerce_float(row.get("adjusted_win_rate")),
                    _coerce_float(row.get("avg_net_worth_at_buy")),
                    _json_dumps(row),
                ),
            )
            counts["nodes"] += 1

        for row in edges:
            if not isinstance(row, dict):
                continue
            from_column = _coerce_int(row.get("from_column"))
            from_item_id = _coerce_int(row.get("from_item_id"))
            to_item_id = _coerce_int(row.get("to_item_id"))
            matches = _coerce_int(row.get("matches"))
            if from_column is None or from_item_id is None or to_item_id is None or matches is None or matches <= 0:
                continue
            connection.execute(
                """
                INSERT INTO item_flow_edge (
                    snapshot_id, from_column, from_item_id, to_item_id, wins, losses, matches, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.id,
                    from_column,
                    from_item_id,
                    to_item_id,
                    _coerce_int(row.get("wins")) or 0,
                    _coerce_int(row.get("losses")) or 0,
                    matches,
                    _json_dumps(row),
                ),
            )
            counts["edges"] += 1

        connection.commit()
    return counts


def normalize_player_performance_curve(settings: Settings, snapshot: SnapshotRecord, payload: Any) -> int:
    rows = payload if isinstance(payload, list) else []
    inserted = 0
    with closing(_connect(settings.warehouse_db_path)) as connection:
        connection.execute("DELETE FROM player_performance_curve_point WHERE snapshot_id = ?", (snapshot.id,))
        for row in rows:
            if not isinstance(row, dict):
                continue
            game_time = _coerce_int(row.get("game_time"))
            if game_time is None:
                continue
            connection.execute(
                """
                INSERT INTO player_performance_curve_point (
                    snapshot_id, game_time, net_worth_avg, net_worth_std, kills_avg, kills_std,
                    deaths_avg, deaths_std, assists_avg, assists_std, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.id,
                    game_time,
                    _coerce_float(row.get("net_worth_avg")),
                    _coerce_float(row.get("net_worth_std")),
                    _coerce_float(row.get("kills_avg")),
                    _coerce_float(row.get("kills_std")),
                    _coerce_float(row.get("deaths_avg")),
                    _coerce_float(row.get("deaths_std")),
                    _coerce_float(row.get("assists_avg")),
                    _coerce_float(row.get("assists_std")),
                    _json_dumps(row),
                ),
            )
            inserted += 1
        connection.commit()
    return inserted


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bucket_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def normalize_patch_feed(settings: Settings, snapshot: SnapshotRecord, payload: list[dict[str, Any]]) -> int:
    with closing(_connect(settings.warehouse_db_path)) as connection:
        for entry in payload:
            guid = entry.get("guid") or {}
            content = entry.get("content") or ""
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            patch_id = f"{entry.get('source', 'unknown')}::{guid.get('text') or entry.get('link') or entry.get('title')}"
            _upsert_patch_event(
                connection,
                patch_id=patch_id,
                source=entry.get("source", "unknown"),
                title=entry.get("title", "Untitled Patch"),
                published_at=entry.get("pub_date"),
                link=entry.get("link"),
                source_guid=guid.get("text"),
                content_hash=content_hash,
                snapshot_id=snapshot.id,
                content=content,
            )
        connection.commit()
    return len(payload)


def _upsert_patch_event(
    connection: sqlite3.Connection,
    *,
    patch_id: str,
    source: str,
    title: str,
    published_at: str | None,
    link: str | None,
    source_guid: str | None,
    content_hash: str,
    snapshot_id: int,
    content: str,
) -> None:
    connection.execute(
        """
        INSERT INTO patch_event (
            patch_id,
            source,
            title,
            published_at,
            link,
            source_guid,
            content_hash,
            snapshot_id,
            content_excerpt,
            content_full
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(patch_id) DO UPDATE SET
            title = excluded.title,
            published_at = excluded.published_at,
            link = excluded.link,
            source_guid = excluded.source_guid,
            content_hash = excluded.content_hash,
            snapshot_id = excluded.snapshot_id,
            content_excerpt = excluded.content_excerpt,
            content_full = excluded.content_full
        """,
        (
            patch_id,
            source,
            title,
            published_at or "",
            link or "",
            source_guid,
            content_hash,
            snapshot_id,
            content[:280],
            content,
        ),
    )


def normalize_steam_patch_feed(
    settings: Settings,
    snapshot: SnapshotRecord,
    newsitems: list[dict[str, Any]],
) -> int:
    """Store Steam ISteamNews patch notes in the shared patch_event table.

    Steam newsitems use a different shape than the community patch feed
    (`gid`/`date`/`contents` instead of `guid`/`pub_date`/`content`), so they are
    mapped here and stored with `source="steam"` and full body text.
    """

    stored = 0
    with closing(_connect(settings.warehouse_db_path)) as connection:
        for entry in newsitems:
            gid = str(entry.get("gid") or "").strip()
            if not gid:
                continue
            content = str(entry.get("contents") or "")
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            published_at = _steam_epoch_to_iso(entry.get("date"))
            _upsert_patch_event(
                connection,
                patch_id=f"steam::{gid}",
                source="steam",
                title=str(entry.get("title") or "Untitled Patch"),
                published_at=published_at,
                link=str(entry.get("url") or ""),
                source_guid=gid,
                content_hash=content_hash,
                snapshot_id=snapshot.id,
                content=content,
            )
            stored += 1
        connection.commit()
    return stored


def _steam_epoch_to_iso(value: Any) -> str:
    """Convert a Steam unix-epoch `date` into an ISO-8601 UTC string.

    patch_event.published_at is stored as ISO text (the community feed already
    stores RSS `pub_date` strings), so Steam's integer epoch is normalized to
    match and keep `ORDER BY published_at DESC` meaningful.
    """

    try:
        epoch = int(value)
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def normalize_leaderboard(
    settings: Settings,
    snapshot: SnapshotRecord,
    region: str,
    payload: dict[str, Any],
) -> int:
    entries = payload.get("entries") or []
    with closing(_connect(settings.warehouse_db_path)) as connection:
        connection.execute("DELETE FROM leaderboard_snapshot_entry WHERE snapshot_id = ?", (snapshot.id,))
        for entry in entries:
            connection.execute(
                """
                INSERT INTO leaderboard_snapshot_entry (
                    snapshot_id,
                    region,
                    rank,
                    account_name,
                    candidate_account_ids_json,
                    top_hero_ids_json,
                    badge_level,
                    ranked_rank,
                    ranked_subrank
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.id,
                    region,
                    entry.get("rank"),
                    entry.get("account_name", ""),
                    _json_dumps(entry.get("possible_account_ids") or []),
                    _json_dumps(entry.get("top_hero_ids") or []),
                    entry.get("badge_level"),
                    entry.get("ranked_rank"),
                    entry.get("ranked_subrank"),
                ),
            )
        connection.commit()
    return len(entries)


def normalize_match_history(
    settings: Settings,
    snapshot: SnapshotRecord,
    account_id: int,
    payload: list[dict[str, Any]],
) -> int:
    with closing(_connect(settings.warehouse_db_path)) as connection:
        for row in payload:
            connection.execute(
                """
                INSERT INTO player_match (
                    match_id,
                    account_id,
                    hero_id,
                    hero_level,
                    start_time,
                    game_mode,
                    match_mode,
                    player_team,
                    kills,
                    deaths,
                    assists,
                    denies,
                    net_worth,
                    last_hits,
                    team_abandoned,
                    abandoned_time_s,
                    match_duration_s,
                    match_result,
                    won,
                    snapshot_id,
                    raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(match_id, account_id) DO UPDATE SET
                    hero_id = excluded.hero_id,
                    hero_level = excluded.hero_level,
                    start_time = excluded.start_time,
                    game_mode = excluded.game_mode,
                    match_mode = excluded.match_mode,
                    player_team = excluded.player_team,
                    kills = excluded.kills,
                    deaths = excluded.deaths,
                    assists = excluded.assists,
                    denies = excluded.denies,
                    net_worth = excluded.net_worth,
                    last_hits = excluded.last_hits,
                    team_abandoned = excluded.team_abandoned,
                    abandoned_time_s = excluded.abandoned_time_s,
                    match_duration_s = excluded.match_duration_s,
                    match_result = excluded.match_result,
                    won = excluded.won,
                    snapshot_id = excluded.snapshot_id,
                    raw_json = excluded.raw_json
                """,
                (
                    row.get("match_id"),
                    account_id,
                    row.get("hero_id"),
                    row.get("hero_level"),
                    row.get("start_time"),
                    row.get("game_mode"),
                    row.get("match_mode"),
                    row.get("player_team"),
                    row.get("player_kills"),
                    row.get("player_deaths"),
                    row.get("player_assists"),
                    row.get("denies"),
                    row.get("net_worth"),
                    row.get("last_hits"),
                    None if row.get("team_abandoned") is None else int(bool(row.get("team_abandoned"))),
                    row.get("abandoned_time_s"),
                    row.get("match_duration_s"),
                    row.get("match_result"),
                    row.get("won"),
                    snapshot.id,
                    _json_dumps(row),
                ),
            )
        connection.commit()
    return len(payload)


def normalize_match_metadata(settings: Settings, snapshot: SnapshotRecord, match_id: int, payload: dict[str, Any]) -> dict[str, int]:
    match_info = payload.get("match_info") or {}
    players = match_info.get("players") or []
    item_count = 0
    stat_count = 0

    with closing(_connect(settings.warehouse_db_path)) as connection:
        connection.execute(
            """
            INSERT INTO match_metadata (
                match_id,
                duration_s,
                winning_team,
                match_outcome,
                snapshot_id,
                raw_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
                duration_s = excluded.duration_s,
                winning_team = excluded.winning_team,
                match_outcome = excluded.match_outcome,
                snapshot_id = excluded.snapshot_id,
                raw_json = excluded.raw_json
            """,
            (
                match_id,
                match_info.get("duration_s"),
                match_info.get("winning_team"),
                match_info.get("match_outcome"),
                snapshot.id,
                _json_dumps(payload),
            ),
        )
        connection.execute("DELETE FROM match_participant WHERE match_id = ?", (match_id,))
        connection.execute("DELETE FROM item_purchase WHERE match_id = ?", (match_id,))
        connection.execute("DELETE FROM stat_bucket WHERE match_id = ?", (match_id,))

        for player in players:
            player_slot = int(player.get("player_slot", -1))
            account_id = player.get("account_id")
            connection.execute(
                """
                INSERT INTO match_participant (
                    match_id,
                    player_slot,
                    account_id,
                    hero_id,
                    team,
                    won,
                    raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    match_id,
                    player_slot,
                    account_id,
                    player.get("hero_id"),
                    player.get("player_team") or player.get("team"),
                    None if player.get("won") is None else int(bool(player.get("won"))),
                    _json_dumps(player),
                ),
            )

            for purchase_index, item in enumerate(player.get("items") or []):
                connection.execute(
                    """
                    INSERT INTO item_purchase (
                        match_id,
                        player_slot,
                        purchase_index,
                        account_id,
                        item_id,
                        upgrade_id,
                        bought_at_s,
                        sold_at_s,
                        imbued_ability_id,
                        flags,
                        upgrade_info,
                        raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        match_id,
                        player_slot,
                        purchase_index,
                        account_id,
                        item.get("item_id"),
                        item.get("upgrade_id"),
                        item.get("game_time_s"),
                        item.get("sold_time_s"),
                        item.get("imbued_ability_id"),
                        item.get("flags"),
                        item.get("upgrade_info"),
                        _json_dumps(item),
                    ),
                )
                item_count += 1

            for bucket_index, bucket in enumerate(player.get("stats") or []):
                connection.execute(
                    """
                    INSERT INTO stat_bucket (
                        match_id,
                        player_slot,
                        bucket_index,
                        account_id,
                        time_stamp_s,
                        net_worth,
                        kills,
                        deaths,
                        assists,
                        denies,
                        creep_kills,
                        player_damage,
                        player_damage_taken,
                        raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        match_id,
                        player_slot,
                        bucket_index,
                        account_id,
                        bucket.get("time_stamp_s"),
                        bucket.get("net_worth"),
                        bucket.get("kills"),
                        bucket.get("deaths"),
                        bucket.get("assists"),
                        bucket.get("denies"),
                        bucket.get("creep_kills"),
                        bucket.get("player_damage"),
                        bucket.get("player_damage_taken"),
                        _json_dumps(bucket),
                    ),
                )
                stat_count += 1
        connection.commit()

    return {"players": len(players), "items": item_count, "stat_buckets": stat_count}
