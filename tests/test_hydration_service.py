from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock_coach.config import Settings
from deadlock_coach.hydration_service import backfill_match_metadata, pending_match_ids
from deadlock_coach.storage import (
    _connect,
    initialize_workspace,
    normalize_match_history,
    normalize_match_metadata,
    save_json_snapshot,
)

COACHED_ACCOUNT = 44
OPPONENT_ACCOUNT = 77


def _history_row(match_id: int, start_time: int) -> dict:
    return {
        "match_id": match_id,
        "hero_id": 20,
        "hero_level": 25,
        "start_time": start_time,
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


def _metadata_entry(match_id: int) -> dict:
    return {
        "match_info": {
            "match_id": match_id,
            "duration_s": 2200,
            "winning_team": 0,
            "match_outcome": 1,
            "players": [
                {
                    "player_slot": 0,
                    "account_id": COACHED_ACCOUNT,
                    "hero_id": 20,
                    "player_team": 0,
                    "won": True,
                    "items": [{"item_id": 5001, "game_time_s": 310}],
                    "stats": [],
                },
                {
                    "player_slot": 6,
                    "account_id": OPPONENT_ACCOUNT,
                    "hero_id": 31,
                    "player_team": 1,
                    "won": False,
                    "items": [{"item_id": 6002, "game_time_s": 480}],
                    "stats": [],
                },
            ],
        }
    }


class FakeBulkMetadataClient:
    """Serves the bulk metadata endpoint for a fixed set of known matches."""

    def __init__(self, known_match_ids: set[int] | None = None, fail_after_requests: int | None = None) -> None:
        self.known_match_ids = known_match_ids
        self.requested_batches: list[list[int]] = []
        self.fail_after_requests = fail_after_requests

    def fetch_json(self, path: str, params: dict | None = None):
        if path != "/v1/matches/metadata":
            raise AssertionError(f"Unexpected path: {path}")
        if self.fail_after_requests is not None and len(self.requested_batches) >= self.fail_after_requests:
            raise RuntimeError("simulated upstream failure")
        match_ids = [int(match_id) for match_id in (params or {}).get("match_ids", [])]
        self.requested_batches.append(match_ids)
        served = [
            _metadata_entry(match_id)
            for match_id in match_ids
            if self.known_match_ids is None or match_id in self.known_match_ids
        ]
        return "https://api.deadlock-api.com/v1/matches/metadata", served


class RefusingClient:
    def fetch_json(self, path: str, params: dict | None = None):
        raise AssertionError("no upstream request expected when everything is hydrated")


class HydrationServiceTests(unittest.TestCase):
    def _seed_history(self, settings: Settings, match_ids: list[int]) -> None:
        snapshot = save_json_snapshot(
            settings,
            "deadlock_api",
            "players",
            f"{COACHED_ACCOUNT}-match-history",
            "https://api.deadlock-api.com/v1/players/44/match-history",
            [],
        )
        rows = [_history_row(match_id, start_time=1783288584 + index) for index, match_id in enumerate(match_ids)]
        normalize_match_history(settings, snapshot, COACHED_ACCOUNT, rows)

    def _hydrate_directly(self, settings: Settings, match_id: int) -> None:
        snapshot = save_json_snapshot(
            settings,
            "deadlock_api",
            "matches",
            str(match_id),
            f"https://api.deadlock-api.com/v1/matches/{match_id}/metadata",
            {},
        )
        normalize_match_metadata(settings, snapshot, match_id, _metadata_entry(match_id))

    def _hydrated_match_ids(self, settings: Settings) -> set[int]:
        with closing(_connect(settings.warehouse_db_path)) as connection:
            rows = connection.execute("SELECT match_id FROM match_metadata").fetchall()
        return {int(row["match_id"]) for row in rows}

    def test_backfill_hydrates_pending_matches_in_bulk(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            self._seed_history(settings, [101, 102, 103, 104, 105])
            self._hydrate_directly(settings, 101)

            client = FakeBulkMetadataClient()
            result = backfill_match_metadata(settings, client=client)

            self.assertEqual(result["pending_before"], 4)
            self.assertEqual(result["hydrated"], 4)
            self.assertEqual(result["remaining"], 0)
            self.assertEqual(result["requests_made"], 1)
            self.assertIsNone(result["error"])

            # The already-hydrated match must not be re-requested.
            requested = [match_id for batch in client.requested_batches for match_id in batch]
            self.assertNotIn(101, requested)
            self.assertEqual(sorted(requested), [102, 103, 104, 105])
            self.assertEqual(self._hydrated_match_ids(settings), {101, 102, 103, 104, 105})

            # Hydrated detail includes purchases for every player in the match,
            # not only the coached account.
            with closing(_connect(settings.warehouse_db_path)) as connection:
                purchase_accounts = connection.execute(
                    "SELECT DISTINCT account_id FROM item_purchase WHERE match_id = 102"
                ).fetchall()
            self.assertEqual(
                {int(row["account_id"]) for row in purchase_accounts},
                {COACHED_ACCOUNT, OPPONENT_ACCOUNT},
            )

    def test_backfill_second_run_makes_no_upstream_requests(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            self._seed_history(settings, [101, 102])
            backfill_match_metadata(settings, client=FakeBulkMetadataClient())

            result = backfill_match_metadata(settings, client=RefusingClient())

            self.assertEqual(result["pending_before"], 0)
            self.assertEqual(result["hydrated"], 0)
            self.assertEqual(result["remaining"], 0)
            self.assertEqual(result["requests_made"], 0)

    def test_backfill_chunks_ids_into_bulk_batches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            self._seed_history(settings, [101, 102, 103, 104, 105])

            client = FakeBulkMetadataClient()
            result = backfill_match_metadata(settings, client=client, batch_size=2)

            self.assertEqual(result["requests_made"], 3)
            self.assertEqual([len(batch) for batch in client.requested_batches], [2, 2, 1])
            self.assertEqual(result["hydrated"], 5)

    def test_backfill_resumes_after_interruption_without_restarting(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            self._seed_history(settings, [101, 102, 103, 104, 105])

            first_client = FakeBulkMetadataClient()
            first = backfill_match_metadata(settings, client=first_client, batch_size=2, max_requests=1)
            self.assertEqual(first["hydrated"], 2)
            self.assertEqual(first["remaining"], 3)

            second_client = FakeBulkMetadataClient()
            second = backfill_match_metadata(settings, client=second_client, batch_size=2)

            self.assertEqual(second["hydrated"], 3)
            self.assertEqual(second["remaining"], 0)
            already_hydrated = {match_id for batch in first_client.requested_batches for match_id in batch}
            requested_again = [match_id for batch in second_client.requested_batches for match_id in batch]
            self.assertFalse(already_hydrated.intersection(requested_again))

    def test_backfill_reports_matches_missing_from_bulk_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            self._seed_history(settings, [101, 102, 103])

            client = FakeBulkMetadataClient(known_match_ids={101, 103})
            result = backfill_match_metadata(settings, client=client)

            self.assertEqual(result["hydrated"], 2)
            self.assertEqual(result["unresolved_match_ids"], [102])
            self.assertEqual(result["remaining"], 1)
            # The missing match must not be half-written.
            self.assertEqual(self._hydrated_match_ids(settings), {101, 103})
            with closing(_connect(settings.warehouse_db_path)) as connection:
                purchases = connection.execute(
                    "SELECT COUNT(*) AS purchase_count FROM item_purchase WHERE match_id = 102"
                ).fetchone()
            self.assertEqual(int(purchases["purchase_count"]), 0)

    def test_backfill_stops_on_upstream_error_and_keeps_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            self._seed_history(settings, [101, 102, 103, 104, 105])

            client = FakeBulkMetadataClient(fail_after_requests=1)
            result = backfill_match_metadata(settings, client=client, batch_size=2)

            self.assertEqual(result["hydrated"], 2)
            self.assertEqual(result["remaining"], 3)
            self.assertIn("simulated upstream failure", str(result["error"]))
            self.assertEqual(len(self._hydrated_match_ids(settings)), 2)

    def test_pending_match_ids_orders_newest_history_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            self._seed_history(settings, [101, 102, 103])

            pending = pending_match_ids(settings)

            # Seeded start_time increases with list position, so 103 is newest.
            self.assertEqual(pending, [103, 102, 101])


if __name__ == "__main__":
    unittest.main()
