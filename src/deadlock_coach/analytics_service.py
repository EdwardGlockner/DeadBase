from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from deadlock_coach.asset_service import hero_label, item_label, resolve_hero_id
from deadlock_coach.api import DeadlockApiClient
from deadlock_coach.config import Settings
from deadlock_coach.storage import (
    build_query_fingerprint,
    normalize_analytics_snapshot,
    normalize_hero_analytics_stats,
    normalize_item_flow_stats,
    normalize_item_analytics_stats,
    normalize_player_performance_curve,
    save_json_snapshot,
)

SUPPORTED_ANALYTICS_ENDPOINTS = {
    "hero-stats": "/v1/analytics/hero-stats",
    "game-stats": "/v1/analytics/game-stats",
    "item-stats": "/v1/analytics/item-stats",
    "item-flow-stats": "/v1/analytics/item-flow-stats",
    "ability-order-stats": "/v1/analytics/ability-order-stats",
    "player-performance-curve": "/v1/analytics/player-performance-curve",
    "hero-counter-stats": "/v1/analytics/hero-counter-stats",
    "hero-synergy-stats": "/v1/analytics/hero-synergy-stats",
    "hero-comb-stats": "/v1/analytics/hero-comb-stats",
    "build-item-stats": "/v1/analytics/build-item-stats",
    "hero-ban-stats": "/v1/analytics/hero-ban-stats",
    "badge-distribution": "/v1/analytics/badge-distribution",
    "scoreboards/heroes": "/v1/analytics/scoreboards/heroes",
    "scoreboards/players": "/v1/analytics/scoreboards/players",
}


def resolve_analytics_endpoint(name_or_path: str) -> str:
    candidate = name_or_path.strip()
    if not candidate:
        raise ValueError("Analytics endpoint is required")
    if candidate in SUPPORTED_ANALYTICS_ENDPOINTS:
        return SUPPORTED_ANALYTICS_ENDPOINTS[candidate]
    if candidate.startswith("/v1/analytics/"):
        return candidate
    raise ValueError(f"Unsupported analytics endpoint: {name_or_path}")


def parse_cli_param(raw: str) -> tuple[str, Any]:
    key, separator, value = raw.partition("=")
    name = key.strip()
    if not separator or not name:
        raise ValueError(f"Expected analytics param in key=value form, got: {raw}")

    parsed = _parse_param_value(value.strip())
    return name, parsed


def sync_analytics_query(
    settings: Settings,
    endpoint_name_or_path: str,
    query_params: dict[str, Any] | None = None,
    patch_window_label: str | None = None,
    client: DeadlockApiClient | None = None,
) -> dict[str, Any]:
    endpoint = resolve_analytics_endpoint(endpoint_name_or_path)
    params = dict(query_params or {})
    client = client or DeadlockApiClient(settings)

    request_url, payload = client.fetch_json(endpoint, params=params)
    snapshot = save_json_snapshot(
        settings,
        "deadlock_api",
        "analytics",
        _analytics_entity_key(endpoint, params),
        request_url,
        payload,
    )
    normalize_analytics_snapshot(
        settings,
        snapshot,
        endpoint=endpoint,
        query_params=params,
        patch_window_label=patch_window_label,
    )
    normalized_rows = _normalize_supported_endpoint(settings, snapshot, endpoint, payload)

    return {
        "endpoint": endpoint,
        "request_url": request_url,
        "snapshot_id": snapshot.id,
        "snapshot_path": str(snapshot.path),
        "row_count": _payload_row_count(payload),
        "normalized_rows": normalized_rows,
        "query_params": params,
        "patch_window_label": patch_window_label,
    }


def read_latest_global_hero_stats(
    settings: Settings,
    limit: int = 5,
    min_matches: int = 100000,
    min_average_badge: int | None = None,
    max_average_badge: int | None = None,
) -> dict[str, Any] | None:
    required_params: dict[str, Any] = {}
    if min_average_badge is not None:
        required_params["min_average_badge"] = min_average_badge
    if max_average_badge is not None:
        required_params["max_average_badge"] = max_average_badge
    snapshot = _latest_snapshot(settings, "/v1/analytics/hero-stats", required_params=required_params)
    if snapshot is None:
        return None

    with closing(_connect(settings.warehouse_db_path)) as connection:
        rows = connection.execute(
            """
            SELECT hero_id, matches, wins, losses
            FROM hero_analytics_stat
            WHERE snapshot_id = ? AND matches > 0
            ORDER BY matches DESC, hero_id ASC
            """,
            (snapshot["snapshot_id"],),
        ).fetchall()

    if not rows:
        return None

    total_matches = sum(int(row["matches"]) for row in rows)
    normalized = []
    client = DeadlockApiClient(settings)
    for row in rows:
        hero_id = int(row["hero_id"])
        matches = int(row["matches"])
        wins = int(row["wins"] or 0)
        losses = int(row["losses"] or 0)
        normalized.append(
            {
                "hero_id": hero_id,
                "hero_label": hero_label(settings, hero_id, client=client),
                "matches": matches,
                "wins": wins,
                "losses": losses,
                "win_rate": round(100.0 * wins / max(matches, 1), 1),
                "pick_rate": round(100.0 * matches / max(total_matches, 1), 2),
            }
        )

    return {
        "source": "local_sqlite",
        "time_window": _window_label(snapshot),
        "sample_scope": "global_public_matches",
        "snapshot_id": snapshot["snapshot_id"],
        "fetched_at": snapshot["fetched_at"],
        "query_params": snapshot["query_params"],
        "total_hero_picks": total_matches,
        "top_pickrate": sorted(normalized, key=lambda row: (-row["pick_rate"], -row["matches"], row["hero_label"]))[: max(1, limit)],
        "top_winrate": sorted(
            [row for row in normalized if row["matches"] >= max(1, min_matches)],
            key=lambda row: (-row["win_rate"], -row["matches"], row["hero_label"]),
        )[: max(1, limit)],
        "min_matches_for_winrate": max(1, min_matches),
        "rank_filter": {
            "min_average_badge": min_average_badge,
            "max_average_badge": max_average_badge,
        }
        if min_average_badge is not None or max_average_badge is not None
        else None,
    }


def read_latest_global_item_stats(
    settings: Settings,
    limit: int = 5,
    min_matches: int = 100000,
    min_average_badge: int | None = None,
    max_average_badge: int | None = None,
) -> dict[str, Any] | None:
    required_params: dict[str, Any] = {}
    if min_average_badge is not None:
        required_params["min_average_badge"] = min_average_badge
    if max_average_badge is not None:
        required_params["max_average_badge"] = max_average_badge
    snapshot = _latest_snapshot(settings, "/v1/analytics/item-stats", required_params=required_params)
    if snapshot is None:
        return None

    with closing(_connect(settings.warehouse_db_path)) as connection:
        rows = connection.execute(
            """
            SELECT item_id, matches, wins, losses, purchases, players, avg_bought_at_s
            FROM item_analytics_stat
            WHERE snapshot_id = ? AND matches > 0
            ORDER BY matches DESC, item_id ASC
            """,
            (snapshot["snapshot_id"],),
        ).fetchall()

    if not rows:
        return None

    total_matches = sum(int(row["matches"]) for row in rows)
    normalized = []
    for row in rows:
        item_id = int(row["item_id"])
        matches = int(row["matches"])
        wins = int(row["wins"] or 0)
        losses = int(row["losses"] or 0)
        normalized.append(
            {
                "item_id": item_id,
                "item_label": item_label(settings, item_id),
                "matches": matches,
                "wins": wins,
                "losses": losses,
                "purchases": None if row["purchases"] is None else int(row["purchases"]),
                "players": None if row["players"] is None else int(row["players"]),
                "avg_bought_at_s": None if row["avg_bought_at_s"] is None else float(row["avg_bought_at_s"]),
                "win_rate": round(100.0 * wins / max(matches, 1), 1),
                "usage_share": round(100.0 * matches / max(total_matches, 1), 2),
            }
        )

    return {
        "source": "local_sqlite",
        "time_window": _window_label(snapshot),
        "sample_scope": "global_public_matches",
        "snapshot_id": snapshot["snapshot_id"],
        "fetched_at": snapshot["fetched_at"],
        "query_params": snapshot["query_params"],
        "total_item_match_rows": total_matches,
        "top_usage": sorted(normalized, key=lambda row: (-row["matches"], row["item_label"]))[: max(1, limit)],
        "top_winrate": sorted(
            [row for row in normalized if row["matches"] >= max(1, min_matches)],
            key=lambda row: (-row["win_rate"], -row["matches"], row["item_label"]),
        )[: max(1, limit)],
        "min_matches_for_winrate": max(1, min_matches),
        "rank_filter": {
            "min_average_badge": min_average_badge,
            "max_average_badge": max_average_badge,
        }
        if min_average_badge is not None or max_average_badge is not None
        else None,
    }


def read_latest_item_flow_summary(
    settings: Settings,
    hero_name: str | None = None,
    stage_limit: int = 3,
    transition_limit: int = 6,
    min_average_badge: int | None = None,
    max_average_badge: int | None = None,
) -> dict[str, Any] | None:
    hero_id = resolve_hero_id(settings, hero_name) if hero_name else None
    required_params: dict[str, Any] = {"hero_id": hero_id} if hero_id is not None else {}
    if min_average_badge is not None:
        required_params["min_average_badge"] = min_average_badge
    if max_average_badge is not None:
        required_params["max_average_badge"] = max_average_badge
    snapshot = _latest_snapshot(settings, "/v1/analytics/item-flow-stats", required_params=required_params)
    if snapshot is None:
        return None

    with closing(_connect(settings.warehouse_db_path)) as connection:
        summary_rows = connection.execute(
            """
            SELECT scope, wins, losses, matches, players, total_kills, total_deaths, total_assists, avg_net_worth, avg_duration_s
            FROM item_flow_summary
            WHERE snapshot_id = ?
            """,
            (snapshot["snapshot_id"],),
        ).fetchall()
        reach_rows = connection.execute(
            """
            SELECT column_index, reached_matches
            FROM item_flow_reach
            WHERE snapshot_id = ?
            ORDER BY column_index ASC
            """,
            (snapshot["snapshot_id"],),
        ).fetchall()
        node_rows = connection.execute(
            """
            SELECT column_index, item_id, wins, losses, matches, players, adjusted_win_rate, avg_net_worth_at_buy
            FROM item_flow_node
            WHERE snapshot_id = ?
            ORDER BY column_index ASC, matches DESC, item_id ASC
            """,
            (snapshot["snapshot_id"],),
        ).fetchall()
        edge_rows = connection.execute(
            """
            SELECT from_column, from_item_id, to_item_id, wins, losses, matches
            FROM item_flow_edge
            WHERE snapshot_id = ?
            ORDER BY matches DESC, from_column ASC, from_item_id ASC, to_item_id ASC
            LIMIT ?
            """,
            (snapshot["snapshot_id"], max(1, transition_limit)),
        ).fetchall()

    if not node_rows:
        return None

    summary_by_scope = {
        str(row["scope"]): {
            "wins": int(row["wins"] or 0),
            "losses": int(row["losses"] or 0),
            "matches": int(row["matches"] or 0),
            "players": None if row["players"] is None else int(row["players"]),
            "total_kills": None if row["total_kills"] is None else int(row["total_kills"]),
            "total_deaths": None if row["total_deaths"] is None else int(row["total_deaths"]),
            "total_assists": None if row["total_assists"] is None else int(row["total_assists"]),
            "avg_net_worth": None if row["avg_net_worth"] is None else float(row["avg_net_worth"]),
            "avg_duration_s": None if row["avg_duration_s"] is None else float(row["avg_duration_s"]),
        }
        for row in summary_rows
    }

    stage_map: dict[int, list[dict[str, Any]]] = {}
    for row in node_rows:
        column_index = int(row["column_index"])
        bucket = stage_map.setdefault(column_index, [])
        if len(bucket) >= max(1, stage_limit):
            continue
        matches = int(row["matches"] or 0)
        wins = int(row["wins"] or 0)
        bucket.append(
            {
                "item_id": int(row["item_id"]),
                "item_label": item_label(settings, int(row["item_id"])),
                "matches": matches,
                "wins": wins,
                "losses": int(row["losses"] or 0),
                "win_rate": round(100.0 * wins / max(matches, 1), 1),
                "players": None if row["players"] is None else int(row["players"]),
                "adjusted_win_rate": None if row["adjusted_win_rate"] is None else float(row["adjusted_win_rate"]),
                "avg_net_worth_at_buy": None if row["avg_net_worth_at_buy"] is None else float(row["avg_net_worth_at_buy"]),
            }
        )

    transitions = [
        {
            "from_column": int(row["from_column"]),
            "from_item_id": int(row["from_item_id"]),
            "from_item_label": item_label(settings, int(row["from_item_id"])),
            "to_item_id": int(row["to_item_id"]),
            "to_item_label": item_label(settings, int(row["to_item_id"])),
            "matches": int(row["matches"] or 0),
            "wins": int(row["wins"] or 0),
            "losses": int(row["losses"] or 0),
            "win_rate": round(100.0 * int(row["wins"] or 0) / max(int(row["matches"] or 0), 1), 1),
        }
        for row in edge_rows
    ]

    return {
        "source": "local_sqlite",
        "time_window": _window_label(snapshot),
        "sample_scope": "global_public_matches",
        "snapshot_id": snapshot["snapshot_id"],
        "fetched_at": snapshot["fetched_at"],
        "query_params": snapshot["query_params"],
        "hero_filter": hero_name if hero_id is not None else None,
        "rank_filter": {
            "min_average_badge": min_average_badge,
            "max_average_badge": max_average_badge,
        }
        if min_average_badge is not None or max_average_badge is not None
        else None,
        "summary": summary_by_scope.get("summary"),
        "baseline": summary_by_scope.get("baseline"),
        "reached_per_column": [int(row["reached_matches"]) for row in reach_rows],
        "stages": [
            {"column": column_index, "top_items": top_items}
            for column_index, top_items in sorted(stage_map.items(), key=lambda item: item[0])
        ],
        "top_transitions": transitions,
    }


def read_latest_player_performance_curve(
    settings: Settings,
    account_id: int,
    resolution: int = 10,
) -> dict[str, Any] | None:
    required_params = {"account_ids": [account_id], "resolution": resolution}
    snapshot = _latest_snapshot(settings, "/v1/analytics/player-performance-curve", required_params=required_params)
    if snapshot is None:
        return None

    with closing(_connect(settings.warehouse_db_path)) as connection:
        rows = connection.execute(
            """
            SELECT game_time, net_worth_avg, net_worth_std, kills_avg, kills_std, deaths_avg, deaths_std, assists_avg, assists_std
            FROM player_performance_curve_point
            WHERE snapshot_id = ?
            ORDER BY game_time ASC
            """,
            (snapshot["snapshot_id"],),
        ).fetchall()

    if not rows:
        return None

    points = [
        {
            "game_time": int(row["game_time"]),
            "net_worth_avg": None if row["net_worth_avg"] is None else float(row["net_worth_avg"]),
            "net_worth_std": None if row["net_worth_std"] is None else float(row["net_worth_std"]),
            "kills_avg": None if row["kills_avg"] is None else float(row["kills_avg"]),
            "kills_std": None if row["kills_std"] is None else float(row["kills_std"]),
            "deaths_avg": None if row["deaths_avg"] is None else float(row["deaths_avg"]),
            "deaths_std": None if row["deaths_std"] is None else float(row["deaths_std"]),
            "assists_avg": None if row["assists_avg"] is None else float(row["assists_avg"]),
            "assists_std": None if row["assists_std"] is None else float(row["assists_std"]),
        }
        for row in rows
    ]

    checkpoints: list[dict[str, Any]] = []
    if points:
        checkpoints.append(points[0])
        if len(points) > 2:
            checkpoints.append(points[len(points) // 2])
        if len(points) > 1:
            checkpoints.append(points[-1])
    deduped_checkpoints = []
    seen_times: set[int] = set()
    for point in checkpoints:
        game_time = int(point["game_time"])
        if game_time in seen_times:
            continue
        seen_times.add(game_time)
        deduped_checkpoints.append(point)

    return {
        "source": "local_sqlite",
        "time_window": _window_label(snapshot),
        "sample_scope": "player_specific_curve",
        "snapshot_id": snapshot["snapshot_id"],
        "fetched_at": snapshot["fetched_at"],
        "query_params": snapshot["query_params"],
        "account_id": account_id,
        "resolution": resolution,
        "points": points,
        "checkpoints": deduped_checkpoints,
    }


def _parse_param_value(value: str) -> Any:
    lowered = value.casefold()
    if lowered in {"true", "false", "null"}:
        return json.loads(lowered)
    if value.startswith("[") or value.startswith("{") or value.startswith('"'):
        return json.loads(value)
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?(?:\d+\.\d*|\d*\.\d+)", value):
        return float(value)
    return value


def _analytics_entity_key(endpoint: str, query_params: dict[str, Any]) -> str:
    endpoint_slug = endpoint.strip("/").replace("/", "__").replace("{", "").replace("}", "")
    suffix = build_query_fingerprint(query_params)[:12]
    return f"{endpoint_slug}--{suffix}"


def _payload_row_count(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        return 0 if not payload else 1
    return 0


def _normalize_supported_endpoint(settings: Settings, snapshot: Any, endpoint: str, payload: Any) -> int:
    if endpoint == "/v1/analytics/hero-stats":
        return normalize_hero_analytics_stats(settings, snapshot, payload)
    if endpoint == "/v1/analytics/item-stats":
        return normalize_item_analytics_stats(settings, snapshot, payload)
    if endpoint == "/v1/analytics/player-performance-curve":
        return normalize_player_performance_curve(settings, snapshot, payload)
    if endpoint == "/v1/analytics/item-flow-stats":
        counts = normalize_item_flow_stats(settings, snapshot, payload)
        return int(sum(counts.values()))
    return 0


def _latest_snapshot(settings: Settings, endpoint: str, required_params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not settings.warehouse_db_path.exists():
        return None
    with closing(_connect(settings.warehouse_db_path)) as connection:
        rows = connection.execute(
            """
            SELECT analytics.snapshot_id, analytics.query_params_json, analytics.coverage_start, analytics.coverage_end,
                   analytics.patch_window_label, source.fetched_at
            FROM analytics_snapshot AS analytics
            JOIN source_snapshot AS source
              ON source.id = analytics.snapshot_id
            WHERE analytics.endpoint = ?
            ORDER BY
                CASE WHEN analytics.query_params_json = '{}' THEN 0 ELSE 1 END,
                source.fetched_at DESC
            """,
            (endpoint,),
        ).fetchall()
    for row in rows:
        try:
            query_params = json.loads(row["query_params_json"] or "{}")
        except json.JSONDecodeError:
            query_params = {}
        if not _query_params_match(query_params, required_params or {}):
            continue
        return {
            "snapshot_id": int(row["snapshot_id"]),
            "query_params": query_params,
            "coverage_start": row["coverage_start"],
            "coverage_end": row["coverage_end"],
            "patch_window_label": row["patch_window_label"],
            "fetched_at": row["fetched_at"],
        }
    return None


def _window_label(snapshot: dict[str, Any]) -> str:
    if snapshot.get("patch_window_label"):
        return str(snapshot["patch_window_label"])
    start = snapshot.get("coverage_start")
    end = snapshot.get("coverage_end")
    if start is None and end is None:
        return "default_api_window"
    return f"{start or 'open'}:{end or 'open'}"


def _query_params_match(actual: dict[str, Any], required: dict[str, Any]) -> bool:
    for key, expected_value in required.items():
        if key not in actual:
            return False
        actual_value = actual[key]
        if isinstance(expected_value, list):
            if list(actual_value) != expected_value:
                return False
        elif actual_value != expected_value:
            return False
    return True


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection
