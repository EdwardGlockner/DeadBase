from __future__ import annotations

import json
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from deadlock_coach.api import DeadlockApiClient
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


def _normalize_candidate(payload: dict[str, Any]) -> AccountCandidate:
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
        last_team_avg_badge=(
            None
            if payload.get("last_team_avg_badge") is None
            else int(payload.get("last_team_avg_badge"))
        ),
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
        candidate = _normalize_candidate(item)
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
            return _normalize_candidate(row)
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
    snapshot = save_json_snapshot(settings, "deadlock_api", "players", f"{account_id}-match-history", request_url, payload)
    match_history_rows = normalize_match_history(settings, snapshot, account_id, payload)

    seen_match_ids: list[int] = []
    for row in payload:
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
        "hydrated_matches": hydrated_matches,
    }
