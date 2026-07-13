from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock_coach.analytics_service import (
    parse_cli_param,
    read_latest_global_hero_stats,
    read_latest_global_item_stats,
    read_latest_item_flow_summary,
    read_latest_player_performance_curve,
    resolve_analytics_endpoint,
    sync_analytics_query,
)
from deadlock_coach.config import Settings
from deadlock_coach.storage import initialize_workspace


class _FakeClient:
    def __init__(self, expected_path: str, payload: object) -> None:
        self.expected_path = expected_path
        self.payload = payload
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    def fetch_json(self, path: str, params: dict[str, object] | None = None) -> tuple[str, object]:
        self.calls.append((path, params))
        if path != self.expected_path:
            raise AssertionError(f"Unexpected path: {path}")
        return f"https://api.deadlock-api.com{path}", self.payload


class AnalyticsServiceTests(unittest.TestCase):
    def test_parse_cli_param_coerces_supported_value_types(self) -> None:
        self.assertEqual(parse_cli_param("hero_id=72"), ("hero_id", 72))
        self.assertEqual(parse_cli_param("limit=10.5"), ("limit", 10.5))
        self.assertEqual(parse_cli_param("only_latest=true"), ("only_latest", True))
        self.assertEqual(parse_cli_param("range=null"), ("range", None))
        self.assertEqual(parse_cli_param('account_ids=[1,2,3]'), ("account_ids", [1, 2, 3]))
        self.assertEqual(parse_cli_param("bucket=start_time_week"), ("bucket", "start_time_week"))

    def test_resolve_analytics_endpoint_supports_alias_and_path(self) -> None:
        self.assertEqual(resolve_analytics_endpoint("hero-stats"), "/v1/analytics/hero-stats")
        self.assertEqual(resolve_analytics_endpoint("/v1/analytics/item-stats"), "/v1/analytics/item-stats")
        with self.assertRaisesRegex(ValueError, "Unsupported analytics endpoint"):
            resolve_analytics_endpoint("/v1/players/steam-search")

    def test_sync_analytics_query_persists_snapshot_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            client = _FakeClient(
                "/v1/analytics/hero-stats",
                [{"hero_id": 72, "matches": 1200, "wins": 700}],
            )

            result = sync_analytics_query(
                settings,
                endpoint_name_or_path="hero-stats",
                query_params={"hero_id": 72, "min_unix_timestamp": 100, "max_unix_timestamp": 200},
                patch_window_label="2026-06-30",
                client=client,
            )

            self.assertEqual(client.calls, [("/v1/analytics/hero-stats", {"hero_id": 72, "min_unix_timestamp": 100, "max_unix_timestamp": 200})])
            self.assertEqual(result["endpoint"], "/v1/analytics/hero-stats")
            self.assertEqual(result["row_count"], 1)
            self.assertEqual(result["normalized_rows"], 1)

            connection = sqlite3.connect(settings.warehouse_db_path)
            source_row = connection.execute(
                "SELECT provider, entity_type, entity_key, request_url FROM source_snapshot WHERE id = ?",
                (result["snapshot_id"],),
            ).fetchone()
            analytics_row = connection.execute(
                """
                SELECT endpoint, coverage_start, coverage_end, patch_window_label
                FROM analytics_snapshot
                WHERE snapshot_id = ?
                """,
                (result["snapshot_id"],),
            ).fetchone()
            connection.close()

            self.assertIsNotNone(source_row)
            self.assertIsNotNone(analytics_row)
            assert source_row is not None
            assert analytics_row is not None
            self.assertEqual(source_row[0], "deadlock_api")
            self.assertEqual(source_row[1], "analytics")
            self.assertIn("v1__analytics__hero-stats--", source_row[2])
            self.assertTrue(source_row[3].startswith("https://api.deadlock-api.com/v1/analytics/hero-stats"))
            self.assertEqual(analytics_row[0], "/v1/analytics/hero-stats")
            self.assertEqual(analytics_row[1], 100)
            self.assertEqual(analytics_row[2], 200)
            self.assertEqual(analytics_row[3], "2026-06-30")

    def test_sync_item_stats_query_normalizes_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            client = _FakeClient(
                "/v1/analytics/item-stats",
                [{"item_id": 401, "bucket": 0, "matches": 240, "wins": 132, "losses": 108, "purchases": 260}],
            )

            result = sync_analytics_query(
                settings,
                endpoint_name_or_path="item-stats",
                query_params={},
                client=client,
            )

            connection = sqlite3.connect(settings.warehouse_db_path)
            row = connection.execute(
                "SELECT item_id, matches, wins, purchases FROM item_analytics_stat WHERE snapshot_id = ?",
                (result["snapshot_id"],),
            ).fetchone()
            connection.close()

            self.assertEqual(result["normalized_rows"], 1)
            self.assertEqual(row, (401, 240, 132, 260))

    def test_read_latest_global_hero_stats_prefers_local_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            client = _FakeClient(
                "/v1/analytics/hero-stats",
                [
                    {"hero_id": 1, "matches": 100, "wins": 60, "losses": 40},
                    {"hero_id": 2, "matches": 120, "wins": 88, "losses": 32},
                ],
            )
            sync_analytics_query(settings, "hero-stats", query_params={}, client=client)

            with patch("deadlock_coach.analytics_service.hero_label", side_effect=lambda _settings, hero_id, client=None: {1: "Billy", 2: "Pocket"}[hero_id]):
                result = read_latest_global_hero_stats(settings, limit=2, min_matches=50)

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["source"], "local_sqlite")
            self.assertEqual(result["top_pickrate"][0]["hero_label"], "Pocket")
            self.assertEqual(result["top_winrate"][0]["hero_label"], "Pocket")

    def test_read_latest_global_item_stats_prefers_local_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            client = _FakeClient(
                "/v1/analytics/item-stats",
                [
                    {"item_id": 401, "matches": 240, "wins": 132, "losses": 108, "purchases": 260, "avg_bought_at_s": 505.5},
                    {"item_id": 402, "matches": 180, "wins": 120, "losses": 60, "purchases": 200, "avg_bought_at_s": 820.0},
                ],
            )
            sync_analytics_query(settings, "item-stats", query_params={}, client=client)

            with patch("deadlock_coach.analytics_service.item_label", side_effect=lambda _settings, item_id: {401: "Monster Rounds", 402: "Warp Stone"}[item_id]):
                result = read_latest_global_item_stats(settings, limit=2, min_matches=50)

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["source"], "local_sqlite")
            self.assertEqual(result["top_usage"][0]["item_label"], "Monster Rounds")
            self.assertEqual(result["top_winrate"][0]["item_label"], "Warp Stone")

    def test_read_latest_global_item_stats_prefers_rank_filtered_local_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            client = _FakeClient(
                "/v1/analytics/item-stats",
                [
                    {"item_id": 401, "matches": 240, "wins": 132, "losses": 108, "purchases": 260, "avg_bought_at_s": 505.5},
                    {"item_id": 402, "matches": 180, "wins": 120, "losses": 60, "purchases": 200, "avg_bought_at_s": 820.0},
                ],
            )
            sync_analytics_query(
                settings,
                "item-stats",
                query_params={"min_average_badge": 116, "max_average_badge": 116},
                client=client,
            )

            with patch("deadlock_coach.analytics_service.item_label", side_effect=lambda _settings, item_id: {401: "Monster Rounds", 402: "Warp Stone"}[item_id]):
                result = read_latest_global_item_stats(
                    settings,
                    limit=2,
                    min_matches=50,
                    min_average_badge=116,
                    max_average_badge=116,
                )

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["source"], "local_sqlite")
            self.assertEqual(result["rank_filter"]["min_average_badge"], 116)
            self.assertEqual(result["rank_filter"]["max_average_badge"], 116)

    def test_read_latest_item_flow_summary_prefers_matching_local_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            client = _FakeClient(
                "/v1/analytics/item-flow-stats",
                {
                    "summary": {"wins": 10, "losses": 8, "matches": 18, "players": 12, "avg_net_worth": 21000.0, "avg_duration_s": 1800.0},
                    "baseline": {"wins": 12, "losses": 10, "matches": 22, "players": 15, "avg_net_worth": 20000.0, "avg_duration_s": 1750.0},
                    "reached_per_column": [22, 18],
                    "nodes": [
                        {"column": 0, "item_id": 401, "wins": 10, "losses": 8, "matches": 18, "players": 12, "adjusted_win_rate": 0.52, "avg_net_worth_at_buy": 4200.0},
                        {"column": 1, "item_id": 402, "wins": 8, "losses": 6, "matches": 14, "players": 11, "adjusted_win_rate": 0.55, "avg_net_worth_at_buy": 9800.0},
                    ],
                    "edges": [
                        {"from_column": 0, "from_item_id": 401, "to_item_id": 402, "wins": 8, "losses": 6, "matches": 14},
                    ],
                },
            )
            sync_analytics_query(settings, "item-flow-stats", query_params={"hero_id": 72}, client=client)

            with patch("deadlock_coach.analytics_service.resolve_hero_id", return_value=72):
                with patch("deadlock_coach.analytics_service.item_label", side_effect=lambda _settings, item_id: {401: "Monster Rounds", 402: "Warp Stone"}[item_id]):
                    result = read_latest_item_flow_summary(settings, hero_name="Billy", stage_limit=2, transition_limit=3)

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["source"], "local_sqlite")
            self.assertEqual(result["hero_filter"], "Billy")
            self.assertEqual(result["stages"][0]["top_items"][0]["item_label"], "Monster Rounds")
            self.assertEqual(result["top_transitions"][0]["to_item_label"], "Warp Stone")

    def test_read_latest_item_flow_summary_prefers_rank_filtered_local_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            client = _FakeClient(
                "/v1/analytics/item-flow-stats",
                {
                    "summary": {"wins": 10, "losses": 8, "matches": 18, "players": 12},
                    "baseline": {"wins": 12, "losses": 10, "matches": 22, "players": 15},
                    "reached_per_column": [22, 18],
                    "nodes": [
                        {"column": 0, "item_id": 401, "wins": 10, "losses": 8, "matches": 18},
                        {"column": 1, "item_id": 402, "wins": 8, "losses": 6, "matches": 14},
                    ],
                    "edges": [
                        {"from_column": 0, "from_item_id": 401, "to_item_id": 402, "wins": 8, "losses": 6, "matches": 14},
                    ],
                },
            )
            sync_analytics_query(
                settings,
                "item-flow-stats",
                query_params={"hero_id": 72, "min_average_badge": 116, "max_average_badge": 116},
                client=client,
            )

            with patch("deadlock_coach.analytics_service.resolve_hero_id", return_value=72):
                with patch("deadlock_coach.analytics_service.item_label", side_effect=lambda _settings, item_id: {401: "Monster Rounds", 402: "Warp Stone"}[item_id]):
                    result = read_latest_item_flow_summary(
                        settings,
                        hero_name="Billy",
                        stage_limit=2,
                        transition_limit=3,
                        min_average_badge=116,
                        max_average_badge=116,
                    )

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["source"], "local_sqlite")
            self.assertEqual(result["rank_filter"]["min_average_badge"], 116)
            self.assertEqual(result["rank_filter"]["max_average_badge"], 116)

    def test_read_latest_player_performance_curve_prefers_matching_local_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            client = _FakeClient(
                "/v1/analytics/player-performance-curve",
                [
                    {"game_time": 0, "net_worth_avg": 2100.0, "kills_avg": 0.3, "deaths_avg": 0.5, "assists_avg": 0.4},
                    {"game_time": 50, "net_worth_avg": 22000.0, "kills_avg": 4.0, "deaths_avg": 4.5, "assists_avg": 5.2},
                    {"game_time": 100, "net_worth_avg": 44000.0, "kills_avg": 8.6, "deaths_avg": 8.0, "assists_avg": 13.4},
                ],
            )
            sync_analytics_query(settings, "player-performance-curve", query_params={"account_ids": [303017110], "resolution": 10}, client=client)

            result = read_latest_player_performance_curve(settings, account_id=303017110, resolution=10)

            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["source"], "local_sqlite")
            self.assertEqual(result["account_id"], 303017110)
            self.assertEqual([point["game_time"] for point in result["checkpoints"]], [0, 50, 100])


if __name__ == "__main__":
    unittest.main()
