from __future__ import annotations

import json
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from deadlock_coach.api import DeadlockApiClient
from deadlock_coach.asset_service import rank_badge_label
from deadlock_coach.config import Settings
from deadlock_coach.storage import (
    _connect,
    initialize_workspace,
    normalize_match_history,
    normalize_match_metadata,
    save_json_snapshot,
)

DEFAULT_HYDRATE_MATCHES = 20


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AccountCandidate:
    account_id: int
    persona_name: str
    profile_url: str | None
    avatar_url: str | None
    country_code: str | None
    matches_played_last_30d: int | None
    last_team_avg_badge: int | None
    last_team_avg_rank: str | None = None


_GAME_MODE_MAP = {
    "Invalid": 0,
    "Normal": 1,
    "OneVsOneTest": 2,
    "Sandbox": 3,
    "StreetBrawl": 4,
    "ExploreNYC": 5,
    "INTERNAL": 6,
}

_MATCH_MODE_MAP = {
    "Invalid": 0,
    "Unranked": 1,
    "PrivateLobby": 2,
    "CoopBot": 3,
    "Ranked": 4,
    "ServerTest": 5,
    "Tutorial": 6,
    "HeroLabs": 7,
    "Calibration": 8,
}

_PLAYER_TEAM_MAP = {
    "Team0": 0,
    "Team1": 1,
    "Spectator": 16,
}


def _normalize_candidate(settings: Settings, payload: dict[str, Any]) -> AccountCandidate:
    last_team_avg_badge = (
        None
        if payload.get("last_team_avg_badge") is None
        else int(payload.get("last_team_avg_badge"))
    )
    return AccountCandidate(
        account_id=int(payload["account_id"]),
        persona_name=str(payload.get("personaname") or payload.get("persona_name") or f"Account {payload['account_id']}"),
        profile_url=payload.get("profileurl") or payload.get("profile_url"),
        avatar_url=payload.get("avatarfull") or payload.get("avatar_url") or payload.get("avatarmedium") or payload.get("avatar"),
        country_code=payload.get("countrycode") or payload.get("country_code"),
        matches_played_last_30d=(
            None
            if payload.get("matches_played_last_30d") is None
            else int(payload.get("matches_played_last_30d"))
        ),
        last_team_avg_badge=last_team_avg_badge,
        last_team_avg_rank=rank_badge_label(settings, last_team_avg_badge),
    )


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_sql_flag(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1"}:
            return 1
        if normalized in {"false", "0"}:
            return 0
    return _coerce_int(value)


def _fetch_sql_rows(client: DeadlockApiClient, query: str) -> list[dict[str, Any]] | None:
    try:
        _, payload = client.fetch_json("/v1/sql", params={"query": query, "format": "json"})
    except RuntimeError:
        return None
    if not isinstance(payload, list):
        return None
    return [row for row in payload if isinstance(row, dict)]


def _fetch_sql_match_history(
    client: DeadlockApiClient,
    account_id: int,
) -> list[dict[str, Any]] | None:
    query = (
        "SELECT "
        "match_id, account_id, hero_id, hero_level, toUnixTimestamp(start_time) AS start_time, "
        "game_mode, match_mode, player_team, player_kills, player_deaths, player_assists, "
        "denies, net_worth, last_hits, team_abandoned, abandoned_time_s, match_duration_s, "
        "match_result, won "
        f"FROM player_match_history WHERE account_id = {account_id} ORDER BY start_time DESC"
    )
    return _fetch_sql_rows(client, query)


def _fetch_sql_match_by_match(
    client: DeadlockApiClient,
    account_id: int,
) -> list[dict[str, Any]] | None:
    query = (
        "SELECT "
        "match_id, account_id, hero_id, "
        "CAST(NULL, 'Nullable(UInt8)') AS hero_level, "
        "toUnixTimestamp(start_time) AS start_time, "
        "game_mode, match_mode, player_team, player_kills, player_deaths, player_assists, "
        "CAST(NULL, 'Nullable(UInt32)') AS denies, "
        "net_worth, "
        "CAST(NULL, 'Nullable(UInt32)') AS last_hits, "
        "CAST(NULL, 'Nullable(Bool)') AS team_abandoned, "
        "CAST(NULL, 'Nullable(UInt32)') AS abandoned_time_s, "
        "match_duration_s, "
        "CAST(NULL, 'Nullable(UInt8)') AS match_result, "
        "won "
        f"FROM player_match_by_match WHERE account_id = {account_id} ORDER BY start_time DESC"
    )
    return _fetch_sql_rows(client, query)


def _normalize_sql_match_history_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        match_id = _coerce_int(row.get("match_id"))
        account_id = _coerce_int(row.get("account_id"))
        hero_id = _coerce_int(row.get("hero_id"))
        start_time = _coerce_int(row.get("start_time"))
        if match_id is None or account_id is None or hero_id is None or start_time is None:
            continue

        normalized.append(
            {
                "match_id": match_id,
                "account_id": account_id,
                "hero_id": hero_id,
                "hero_level": _coerce_int(row.get("hero_level")),
                "start_time": start_time,
                "game_mode": _GAME_MODE_MAP.get(str(row.get("game_mode")), _coerce_int(row.get("game_mode")) or 0),
                "match_mode": _MATCH_MODE_MAP.get(str(row.get("match_mode")), _coerce_int(row.get("match_mode")) or 0),
                "player_team": _PLAYER_TEAM_MAP.get(str(row.get("player_team")), _coerce_int(row.get("player_team")) or 0),
                "player_kills": _coerce_int(row.get("player_kills")) or 0,
                "player_deaths": _coerce_int(row.get("player_deaths")) or 0,
                "player_assists": _coerce_int(row.get("player_assists")) or 0,
                "denies": _coerce_int(row.get("denies")) or 0,
                "net_worth": _coerce_int(row.get("net_worth")) or 0,
                "last_hits": _coerce_int(row.get("last_hits")) or 0,
                "team_abandoned": _coerce_sql_flag(row.get("team_abandoned")),
                "abandoned_time_s": _coerce_int(row.get("abandoned_time_s")),
                "match_duration_s": _coerce_int(row.get("match_duration_s")) or 0,
                "match_result": _coerce_int(row.get("match_result")) or 0,
                "won": None if row.get("won") is None else bool(_coerce_sql_flag(row.get("won"))),
            }
        )
    return normalized


def _merge_match_history_rows(*payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[int, dict[str, Any]] = {}
    for payload in payloads:
        for row in payload:
            match_id = _coerce_int(row.get("match_id"))
            start_time = _coerce_int(row.get("start_time"))
            if match_id is None or start_time is None or match_id in merged:
                continue
            merged[match_id] = row
    return sorted(
        merged.values(),
        key=lambda row: (_coerce_int(row.get("start_time")) or 0, _coerce_int(row.get("match_id")) or 0),
        reverse=True,
    )


def search_account_candidates(
    settings: Settings,
    search_query: str,
    limit: int = 8,
    client: DeadlockApiClient | None = None,
) -> list[AccountCandidate]:
    query = search_query.strip()
    if not query:
        return []

    client = client or DeadlockApiClient(settings)
    _, payload = client.fetch_json(
        "/v1/players/steam-search",
        params={
            "search_query": query,
            "limit": max(1, min(limit, 25)),
        },
    )
    if not isinstance(payload, list):
        raise RuntimeError("Expected a list of player search results from /v1/players/steam-search")

    exact_matches: list[AccountCandidate] = []
    fuzzy_matches: list[AccountCandidate] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("account_id") is None:
            continue
        candidate = _normalize_candidate(settings, item)
        if candidate.persona_name.casefold() == query.casefold():
            exact_matches.append(candidate)
        else:
            fuzzy_matches.append(candidate)

    def _sort_key(candidate: AccountCandidate) -> tuple[int, int, str]:
        return (
            -(candidate.matches_played_last_30d or 0),
            -(candidate.last_team_avg_badge or 0),
            candidate.persona_name.casefold(),
        )

    return sorted(exact_matches, key=_sort_key) + sorted(fuzzy_matches, key=_sort_key)


def upsert_linked_account(settings: Settings, candidate: AccountCandidate, raw_profile: dict[str, Any] | None = None) -> None:
    initialize_workspace(settings)
    with closing(_connect(settings.memory_db_path)) as connection:
        connection.execute(
            """
            INSERT INTO linked_account (
                account_id,
                persona_name,
                profile_url,
                avatar_url,
                country_code,
                matches_played_last_30d,
                last_team_avg_badge,
                raw_json,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                persona_name = excluded.persona_name,
                profile_url = excluded.profile_url,
                avatar_url = excluded.avatar_url,
                country_code = excluded.country_code,
                matches_played_last_30d = excluded.matches_played_last_30d,
                last_team_avg_badge = excluded.last_team_avg_badge,
                raw_json = excluded.raw_json,
                updated_at = excluded.updated_at
            """,
            (
                candidate.account_id,
                candidate.persona_name,
                candidate.profile_url,
                candidate.avatar_url,
                candidate.country_code,
                candidate.matches_played_last_30d,
                candidate.last_team_avg_badge,
                "{}" if raw_profile is None else json.dumps(raw_profile, ensure_ascii=True, sort_keys=True),
                _utc_now_iso(),
            ),
        )
        connection.commit()


def fetch_account_profile(
    settings: Settings,
    account_id: int,
    client: DeadlockApiClient | None = None,
) -> AccountCandidate | None:
    client = client or DeadlockApiClient(settings)
    _, payload = client.fetch_json("/v1/players/steam", params={"account_ids": [account_id]})
    rows = payload if isinstance(payload, list) else [payload]
    for row in rows:
        if isinstance(row, dict) and row.get("account_id") == account_id:
            return _normalize_candidate(settings, row)
    return None


def sync_account(
    settings: Settings,
    account_id: int,
    hydrate_matches: int = DEFAULT_HYDRATE_MATCHES,
    candidate: AccountCandidate | None = None,
    client: DeadlockApiClient | None = None,
) -> dict[str, Any]:
    initialize_workspace(settings)
    client = client or DeadlockApiClient(settings)

    resolved_candidate = candidate
    if resolved_candidate is None:
        try:
            resolved_candidate = fetch_account_profile(settings, account_id, client=client)
        except RuntimeError:
            resolved_candidate = None

    if resolved_candidate is not None:
        upsert_linked_account(settings, resolved_candidate, raw_profile=asdict(resolved_candidate))

    request_url, payload = client.fetch_json(f"/v1/players/{account_id}/match-history")
    match_history_payload = payload if isinstance(payload, list) else []
    snapshot = save_json_snapshot(settings, "deadlock_api", "players", f"{account_id}-match-history", request_url, match_history_payload)
    match_history_rows = normalize_match_history(settings, snapshot, account_id, match_history_payload)

    sql_rows = _fetch_sql_match_history(client, account_id)
    sql_payload = _normalize_sql_match_history_rows(sql_rows or [])
    sql_by_match_rows = _fetch_sql_match_by_match(client, account_id)
    sql_by_match_payload = _normalize_sql_match_history_rows(sql_by_match_rows or [])
    merged_payload = _merge_match_history_rows(match_history_payload, sql_payload, sql_by_match_payload)
    using_sql_backfill = len(merged_payload) > len(match_history_payload)
    if using_sql_backfill:
        sql_snapshot = save_json_snapshot(
            settings,
            "deadlock_api",
            "players_sql",
            f"{account_id}-player-match-history",
            client.build_url("/v1/sql", params={"query": "player_match_history", "format": "json"}),
            merged_payload,
        )
        match_history_rows = normalize_match_history(settings, sql_snapshot, account_id, merged_payload)
        effective_payload = merged_payload
    else:
        effective_payload = match_history_payload

    seen_match_ids: list[int] = []
    for row in effective_payload:
        match_id = row.get("match_id")
        if isinstance(match_id, int) and match_id not in seen_match_ids:
            seen_match_ids.append(match_id)
        if len(seen_match_ids) >= max(0, hydrate_matches):
            break

    hydrated_matches: list[dict[str, Any]] = []
    for match_id in seen_match_ids:
        metadata_url, metadata_payload = client.fetch_json(f"/v1/matches/{match_id}/metadata")
        metadata_snapshot = save_json_snapshot(
            settings,
            "deadlock_api",
            "matches",
            str(match_id),
            metadata_url,
            metadata_payload,
        )
        counts = normalize_match_metadata(settings, metadata_snapshot, match_id, metadata_payload)
        hydrated_matches.append({"match_id": match_id, **counts})

    return {
        "account": None if resolved_candidate is None else asdict(resolved_candidate),
        "account_id": account_id,
        "match_history_rows": match_history_rows,
        "match_history_source": "sql_backfill" if using_sql_backfill else "match_history",
        "match_history_available_rows": len(effective_payload),
        "match_history_base_rows": len(match_history_payload),
        "match_history_sql_rows": len(sql_payload),
        "match_history_sql_by_match_rows": len(sql_by_match_payload),
        "hydrated_matches": hydrated_matches,
    }
