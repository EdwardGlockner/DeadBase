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


if __name__ == "__main__":
    unittest.main()
