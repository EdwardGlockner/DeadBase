from __future__ import annotations

from contextlib import closing
from typing import Any

from deadlock_coach.analytics_service import window_label
from deadlock_coach.api import DeadlockApiClient
from deadlock_coach.config import Settings
from deadlock_coach.storage import _connect, infer_query_coverage, save_json_snapshot

HEROES_ASSETS_ENDPOINT = "/v1/assets/heroes"
HERO_STATS_ENDPOINT = "/v1/analytics/hero-stats"
ITEM_STATS_ENDPOINT = "/v1/analytics/item-stats"

RANKING_BASIS = "pick_share_lift"


def playable_hero_ids(payload: Any) -> list[int]:
    if not isinstance(payload, list):
        return []
    hero_ids = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        if row.get("player_selectable") is not True or row.get("disabled") is True:
            continue
        hero_id = row.get("id")
        if isinstance(hero_id, int):
            hero_ids.append(hero_id)
    return sorted(hero_ids)


def _item_matches_by_id(payload: Any) -> dict[int, int]:
    result: dict[int, int] = {}
    if not isinstance(payload, list):
        return result
    for row in payload:
        if not isinstance(row, dict):
            continue
        item_id = row.get("item_id")
        matches = row.get("matches")
        if isinstance(item_id, int) and isinstance(matches, int) and matches > 0:
            result[item_id] = matches
    return result


def sync_hero_signature(
    settings: Settings,
    client: DeadlockApiClient | None = None,
    patch_window_label: str | None = None,
    query_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Populate hero signatures: one item-stats request per playable hero plus
    one global baseline, with hero-stats supplying the true match denominators.

    Statistics are scoped to the configured recommendation bracket (ADR-0003)
    unless the caller overrides the badge params explicitly.
    """

    client = client or DeadlockApiClient(settings)
    params: dict[str, Any] = dict(query_params or {})
    if "min_average_badge" not in params:
        params["min_average_badge"] = settings.recommendation_min_badge
    coverage_start, coverage_end = infer_query_coverage(params)

    roster_url, roster_payload = client.fetch_json(HEROES_ASSETS_ENDPOINT)
    save_json_snapshot(settings, "deadlock_api", "assets", "heroes", roster_url, roster_payload)
    hero_ids = playable_hero_ids(roster_payload)

    hero_stats_url, hero_stats_payload = client.fetch_json(HERO_STATS_ENDPOINT, params=params)
    hero_stats_snapshot = save_json_snapshot(
        settings, "deadlock_api", "analytics", "hero-signature--hero-stats", hero_stats_url, hero_stats_payload
    )
    hero_matches_by_id: dict[int, int] = {}
    if isinstance(hero_stats_payload, list):
        for row in hero_stats_payload:
            if not isinstance(row, dict):
                continue
            hero_id = row.get("hero_id")
            matches = row.get("matches")
            if isinstance(hero_id, int) and isinstance(matches, int) and matches > 0:
                hero_matches_by_id[hero_id] = matches
    baseline_matches = sum(hero_matches_by_id.values())

    baseline_url, baseline_payload = client.fetch_json(ITEM_STATS_ENDPOINT, params=params)
    baseline_snapshot = save_json_snapshot(
        settings, "deadlock_api", "analytics", "hero-signature--baseline", baseline_url, baseline_payload
    )
    baseline_item_matches = _item_matches_by_id(baseline_payload)

    hero_item_rows: list[tuple[int, int, int, int, int, float, float, float]] = []
    for hero_id in hero_ids:
        hero_url, hero_payload = client.fetch_json(ITEM_STATS_ENDPOINT, params={**params, "hero_id": hero_id})
        hero_snapshot = save_json_snapshot(
            settings, "deadlock_api", "analytics", f"hero-signature--hero-{hero_id}", hero_url, hero_payload
        )
        hero_matches = hero_matches_by_id.get(hero_id)
        if hero_matches is None or hero_matches <= 0 or baseline_matches <= 0:
            continue
        for item_id, item_matches in _item_matches_by_id(hero_payload).items():
            # The share denominator is the hero's true match count from
            # hero-stats, never inferred from the most-purchased item.
            hero_share = 100.0 * item_matches / hero_matches
            global_share = 100.0 * baseline_item_matches.get(item_id, 0) / baseline_matches
            hero_item_rows.append(
                (
                    hero_snapshot.id,
                    hero_id,
                    item_id,
                    hero_matches,
                    item_matches,
                    hero_share,
                    global_share,
                    hero_share - global_share,
                )
            )

    with closing(_connect(settings.warehouse_db_path)) as connection:
        cursor = connection.execute(
            """
            INSERT INTO hero_signature_run (
                fetched_at,
                patch_window_label,
                coverage_start,
                coverage_end,
                min_average_badge,
                max_average_badge,
                baseline_snapshot_id,
                hero_stats_snapshot_id,
                baseline_matches
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hero_stats_snapshot.fetched_at,
                patch_window_label,
                coverage_start,
                coverage_end,
                params.get("min_average_badge"),
                params.get("max_average_badge"),
                baseline_snapshot.id,
                hero_stats_snapshot.id,
                baseline_matches,
            ),
        )
        run_id = int(cursor.lastrowid)
        connection.executemany(
            """
            INSERT INTO hero_signature_item (
                run_id, snapshot_id, hero_id, item_id, hero_matches, item_matches,
                hero_pick_share, global_pick_share, pick_share_lift
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(run_id, *row) for row in hero_item_rows],
        )
        connection.commit()

    return {
        "run_id": run_id,
        "fetched_at": hero_stats_snapshot.fetched_at,
        "patch_window_label": patch_window_label,
        "heroes_synced": len(hero_ids),
        "signature_rows": len(hero_item_rows),
        "baseline_matches": baseline_matches,
        "min_average_badge": params.get("min_average_badge"),
        "max_average_badge": params.get("max_average_badge"),
        "baseline_snapshot_id": baseline_snapshot.id,
        "hero_stats_snapshot_id": hero_stats_snapshot.id,
    }


def read_latest_hero_signature(settings: Settings, hero_id: int, limit: int = 10) -> dict[str, Any] | None:
    """Return the hero's signature from the latest sync run.

    Returns None when no run exists yet; once a run exists, a hero with no
    stored rows yields an explicit ``no_signature_for_hero`` payload.
    """

    if not settings.warehouse_db_path.exists():
        return None

    with closing(_connect(settings.warehouse_db_path)) as connection:
        run = connection.execute(
            """
            SELECT run_id, fetched_at, patch_window_label, coverage_start, coverage_end,
                   min_average_badge, max_average_badge, baseline_matches
            FROM hero_signature_run
            ORDER BY run_id DESC
            LIMIT 1
            """
        ).fetchone()
        if run is None:
            return None

        rows = connection.execute(
            """
            SELECT item_id, snapshot_id, hero_matches, item_matches,
                   hero_pick_share, global_pick_share, pick_share_lift
            FROM hero_signature_item
            WHERE run_id = ? AND hero_id = ?
            ORDER BY pick_share_lift DESC, item_matches DESC, item_id ASC
            LIMIT ?
            """,
            (int(run["run_id"]), hero_id, max(1, limit)),
        ).fetchall()

    patch_window = window_label(
        {
            "patch_window_label": run["patch_window_label"],
            "coverage_start": run["coverage_start"],
            "coverage_end": run["coverage_end"],
        }
    )
    rank_bracket = {
        "min_average_badge": None if run["min_average_badge"] is None else int(run["min_average_badge"]),
        "max_average_badge": None if run["max_average_badge"] is None else int(run["max_average_badge"]),
        "scope_note": "Badge filters apply to the average badge across both teams in the match.",
    }
    base = {
        "source": "local_warehouse",
        "kind": "hero_signature",
        "ranking_basis": RANKING_BASIS,
        "run_id": int(run["run_id"]),
        "fetched_at": run["fetched_at"],
        "patch_window": patch_window,
        "rank_bracket": rank_bracket,
        "hero_id": hero_id,
    }

    if not rows:
        return {
            **base,
            "available": False,
            "status": "no_signature_for_hero",
            "sample_size": {"hero_matches": 0, "baseline_matches": int(run["baseline_matches"])},
        }

    return {
        **base,
        "available": True,
        "sample_size": {
            "hero_matches": int(rows[0]["hero_matches"]),
            "baseline_matches": int(run["baseline_matches"]),
        },
        "signature": [
            {
                "item_id": int(row["item_id"]),
                "snapshot_id": int(row["snapshot_id"]),
                "item_matches": int(row["item_matches"]),
                "hero_matches": int(row["hero_matches"]),
                "hero_pick_share": round(float(row["hero_pick_share"]), 1),
                "global_pick_share": round(float(row["global_pick_share"]), 1),
                "pick_share_lift": round(float(row["pick_share_lift"]), 1),
            }
            for row in rows
        ],
    }
