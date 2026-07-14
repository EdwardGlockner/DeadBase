from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock_coach.account_service import AccountCandidate, search_account_candidates, sync_account
from deadlock_coach.coach_service import list_tracked_accounts
from deadlock_coach.config import Settings
from deadlock_coach.storage import initialize_workspace


class FakeDeadlockApiClient:
    def fetch_json(self, path: str, params: dict | None = None):  # type: ignore[override]
        if path == "/v1/players/steam-search":
            return "https://api.deadlock-api.com/v1/players/steam-search", [
                {
                    "account_id": 44,
                    "personaname": "EEE",
                    "profileurl": "https://steamcommunity.com/profiles/44",
                    "countrycode": "SE",
                    "matches_played_last_30d": 90,
                    "last_team_avg_badge": 85,
                },
                {
                    "account_id": 45,
                    "personaname": "eee",
                    "profileurl": "https://steamcommunity.com/profiles/45",
                    "countrycode": "US",
                    "matches_played_last_30d": 12,
                    "last_team_avg_badge": 40,
                },
            ]
        if path == "/v1/players/44/match-history":
            return "https://api.deadlock-api.com/v1/players/44/match-history", [
                {
                    "match_id": 101,
                    "hero_id": 20,
                    "hero_level": 25,
                    "start_time": 1783288584,
                    "game_mode": 1,
                    "match_mode": 4,
                    "player_team": 0,
                    "player_kills": 12,
                    "player_deaths": 4,
                    "player_assists": 9,
                    "denies": 11,
                    "net_worth": 50210,
                    "last_hits": 240,
                    "team_abandoned": False,
                    "abandoned_time_s": None,
                    "match_duration_s": 2200,
                    "match_result": 1,
                    "won": True,
                }
            ]
        if path == "/v1/sql":
            query = str((params or {}).get("query") or "")
            if "player_match_history" in query:
                return "https://api.deadlock-api.com/v1/sql", []
            if "player_match_by_match" in query:
                return "https://api.deadlock-api.com/v1/sql", []
            return "https://api.deadlock-api.com/v1/sql", []
        if path == "/v1/matches/101/metadata":
            return "https://api.deadlock-api.com/v1/matches/101/metadata", {
                "match_info": {
                    "duration_s": 2200,
                    "winning_team": 0,
                    "match_outcome": 1,
                    "players": [
                        {
                            "player_slot": 0,
                            "account_id": 44,
                            "hero_id": 20,
                            "player_team": 0,
                            "won": True,
                            "items": [{"item_id": 5001, "game_time_s": 310}],
                            "stats": [
                                {
                                    "time_stamp_s": 600,
                                    "net_worth": 9100,
                                    "kills": 2,
                                    "deaths": 1,
                                    "assists": 3,
                                    "denies": 4,
                                    "creep_kills": 55,
                                    "player_damage": 8000,
                                    "player_damage_taken": 4600,
                                }
                            ],
                        }
                    ],
                }
            }
        raise AssertionError(f"Unexpected path: {path}")

    def build_url(self, path: str, params: dict | None = None) -> str:  # type: ignore[override]
        return f"https://api.deadlock-api.com{path}"


class FakeDeadlockApiClientWithSqlBackfill(FakeDeadlockApiClient):
    def fetch_json(self, path: str, params: dict | None = None):  # type: ignore[override]
        if path == "/v1/sql":
            query = str((params or {}).get("query") or "")
            if "player_match_history" in query:
                return "https://api.deadlock-api.com/v1/sql", [
                    {
                        "match_id": 202,
                        "account_id": 44,
                        "hero_id": 20,
                        "hero_level": 25,
                        "start_time": 1783388584,
                        "game_mode": "Normal",
                        "match_mode": "Ranked",
                        "player_team": "Team1",
                        "player_kills": 15,
                        "player_deaths": 6,
                        "player_assists": 8,
                        "denies": 10,
                        "net_worth": 53000,
                        "last_hits": 250,
                        "team_abandoned": False,
                        "abandoned_time_s": None,
                        "match_duration_s": 2300,
                        "match_result": 1,
                        "won": True,
                    },
                    {
                        "match_id": 101,
                        "account_id": 44,
                        "hero_id": 20,
                        "hero_level": 25,
                        "start_time": 1783288584,
                        "game_mode": "Normal",
                        "match_mode": "Ranked",
                        "player_team": "Team0",
                        "player_kills": 12,
                        "player_deaths": 4,
                        "player_assists": 9,
                        "denies": 11,
                        "net_worth": 50210,
                        "last_hits": 240,
                        "team_abandoned": False,
                        "abandoned_time_s": None,
                        "match_duration_s": 2200,
                        "match_result": 1,
                        "won": True,
                    },
                ]
            if "player_match_by_match" in query:
                return "https://api.deadlock-api.com/v1/sql", [
                    {
                        "match_id": 303,
                        "account_id": 44,
                        "hero_id": 21,
                        "hero_level": None,
                        "start_time": 1783488584,
                        "game_mode": "Normal",
                        "match_mode": "Unranked",
                        "player_team": "Team0",
                        "player_kills": 9,
                        "player_deaths": 7,
                        "player_assists": 11,
                        "denies": None,
                        "net_worth": 40123,
                        "last_hits": None,
                        "team_abandoned": None,
                        "abandoned_time_s": None,
                        "match_duration_s": 2100,
                        "match_result": None,
                        "won": False,
                    },
                    {
                        "match_id": 202,
                        "account_id": 44,
                        "hero_id": 20,
                        "hero_level": None,
                        "start_time": 1783388584,
                        "game_mode": "Normal",
                        "match_mode": "Ranked",
                        "player_team": "Team1",
                        "player_kills": 15,
                        "player_deaths": 6,
                        "player_assists": 8,
                        "denies": None,
                        "net_worth": 53000,
                        "last_hits": None,
                        "team_abandoned": None,
                        "abandoned_time_s": None,
                        "match_duration_s": 2300,
                        "match_result": None,
                        "won": True,
                    },
                ]
            return "https://api.deadlock-api.com/v1/sql", []
        if path == "/v1/matches/202/metadata":
            return "https://api.deadlock-api.com/v1/matches/202/metadata", {
                "match_info": {
                    "duration_s": 2300,
                    "winning_team": 1,
                    "match_outcome": 1,
                    "players": [],
                }
            }
        if path == "/v1/matches/303/metadata":
            return "https://api.deadlock-api.com/v1/matches/303/metadata", {
                "match_info": {
                    "duration_s": 2100,
                    "winning_team": 1,
                    "match_outcome": 1,
                    "players": [],
                }
            }
        return super().fetch_json(path, params=params)


class AccountServiceTests(unittest.TestCase):
    def test_search_candidates_prioritizes_exact_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)

            rows = search_account_candidates(settings, "EEE", client=FakeDeadlockApiClient())
            self.assertEqual(rows[0].account_id, 44)
            self.assertEqual(rows[0].persona_name, "EEE")

    def test_sync_account_persists_identity_and_match_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)

            result = sync_account(
                settings,
                44,
                hydrate_matches=1,
                candidate=AccountCandidate(
                    account_id=44,
                    persona_name="EEE",
                    profile_url="https://steamcommunity.com/profiles/44",
                    avatar_url=None,
                    country_code="SE",
                    matches_played_last_30d=90,
                    last_team_avg_badge=85,
                ),
                client=FakeDeadlockApiClient(),
            )

            self.assertEqual(result["match_history_rows"], 1)
            self.assertEqual(len(result["hydrated_matches"]), 1)

            tracked = list_tracked_accounts(settings)
            self.assertEqual(tracked[0]["label"], "EEE")
            self.assertEqual(tracked[0]["country_code"], "SE")

    def test_sync_account_uses_sql_backfill_when_it_expands_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)

            result = sync_account(
                settings,
                44,
                hydrate_matches=1,
                candidate=AccountCandidate(
                    account_id=44,
                    persona_name="EEE",
                    profile_url="https://steamcommunity.com/profiles/44",
                    avatar_url=None,
                    country_code="SE",
                    matches_played_last_30d=90,
                    last_team_avg_badge=85,
                ),
                client=FakeDeadlockApiClientWithSqlBackfill(),
            )

            self.assertEqual(result["match_history_source"], "sql_backfill")
            self.assertEqual(result["match_history_base_rows"], 1)
            self.assertEqual(result["match_history_sql_rows"], 2)
            self.assertEqual(result["match_history_sql_by_match_rows"], 2)
            self.assertEqual(result["match_history_available_rows"], 3)

            tracked = list_tracked_accounts(settings)
            self.assertEqual(tracked[0]["matches"], 3)


if __name__ == "__main__":
    unittest.main()
