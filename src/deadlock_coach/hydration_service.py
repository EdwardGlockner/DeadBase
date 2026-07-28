from __future__ import annotations

from contextlib import closing
from typing import Any

from deadlock_coach.api import DeadlockApiClient
from deadlock_coach.config import Settings
from deadlock_coach.storage import (
    _connect,
    initialize_workspace,
    normalize_match_metadata,
    save_json_snapshot,
)

BULK_MATCH_METADATA_ENDPOINT = "/v1/matches/metadata"
DEFAULT_BATCH_SIZE = 100


def pending_match_ids(settings: Settings) -> list[int]:
    """Match ids present in stored history but not yet hydrated, newest first.

    Newest-first means an interrupted backfill has already covered the matches
    most likely to matter for coaching.
    """

    if not settings.warehouse_db_path.exists():
        return []
    with closing(_connect(settings.warehouse_db_path)) as connection:
        rows = connection.execute(
            """
            SELECT match_id, MAX(start_time) AS latest_start
            FROM player_match
            WHERE match_id NOT IN (SELECT match_id FROM match_metadata)
            GROUP BY match_id
            ORDER BY latest_start DESC, match_id DESC
            """
        ).fetchall()
    return [int(row["match_id"]) for row in rows]


def backfill_match_metadata(
    settings: Settings,
    client: DeadlockApiClient | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_requests: int | None = None,
) -> dict[str, Any]:
    """Hydrate stored match history through the bulk metadata endpoint.

    Resumable by construction: the pending set is recomputed from the
    warehouse on every run, so already-hydrated matches are never re-requested
    and an interrupted run continues where it stopped. Each match is
    normalized in its own transaction, so a failed or partial bulk response
    never leaves a match half-written.
    """

    initialize_workspace(settings)
    client = client or DeadlockApiClient(settings)
    batch_size = max(1, batch_size)

    pending = pending_match_ids(settings)
    hydrated = 0
    requests_made = 0
    unresolved: list[int] = []
    error: str | None = None

    for start in range(0, len(pending), batch_size):
        if max_requests is not None and requests_made >= max_requests:
            break
        batch = pending[start : start + batch_size]
        try:
            request_url, payload = client.fetch_json(
                BULK_MATCH_METADATA_ENDPOINT, params={"match_ids": batch}
            )
        except RuntimeError as exc:
            error = str(exc)
            break
        requests_made += 1
        snapshot = save_json_snapshot(
            settings,
            "deadlock_api",
            "matches",
            f"bulk-{batch[0]}-{batch[-1]}",
            request_url,
            payload,
        )

        returned: dict[int, dict[str, Any]] = {}
        for entry in payload if isinstance(payload, list) else []:
            if not isinstance(entry, dict):
                continue
            wrapped = entry if "match_info" in entry else {"match_info": entry}
            match_info = wrapped.get("match_info") or {}
            match_id = match_info.get("match_id")
            if isinstance(match_id, int):
                returned[match_id] = wrapped

        for match_id in batch:
            entry = returned.get(match_id)
            if entry is None:
                unresolved.append(match_id)
                continue
            normalize_match_metadata(settings, snapshot, match_id, entry)
            hydrated += 1

    return {
        "pending_before": len(pending),
        "hydrated": hydrated,
        "remaining": len(pending_match_ids(settings)),
        "requests_made": requests_made,
        "unresolved_match_ids": unresolved,
        "batch_size": batch_size,
        "error": error,
    }
