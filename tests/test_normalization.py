from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock_coach.config import Settings
from deadlock_coach.storage import (
    build_query_fingerprint,
    infer_query_coverage,
    initialize_workspace,
    normalize_analytics_snapshot,
    normalize_hero_analytics_stats,
    normalize_item_flow_stats,
    normalize_item_analytics_stats,
    normalize_match_history,
    normalize_patch_feed,
    normalize_player_performance_curve,
    save_json_snapshot,
)


class NormalizationTests(unittest.TestCase):
    def test_patch_feed_and_match_history_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)

            patch_payload = [
                {
                    "source": "steam",
                    "title": "Minor Update - 07-01-2026",
                    "pub_date": "2026-07-01T22:54:59Z",
                    "link": "https://store.steampowered.com/news/app/1422450/view/example",
                    "guid": {"text": "patch-guid", "is_perma_link": True},
                    "content": "<p>Patch body</p>",
                }
            ]
            patch_snapshot = save_json_snapshot(
                settings,
                "deadlock_api",
                "patches",
                "unified-feed",
                "https://api.deadlock-api.com/v2/patches",
                patch_payload,
            )
            self.assertEqual(normalize_patch_feed(settings, patch_snapshot, patch_payload), 1)

            match_payload = [
                {
                    "match_id": 123,
                    "hero_id": 20,
                    "hero_level": 25,
                    "start_time": 1783288584,
                    "game_mode": 1,
                    "match_mode": 4,
                    "player_team": 0,
                    "player_kills": 9,
                    "player_deaths": 5,
                    "player_assists": 14,
                    "denies": 12,
                    "net_worth": 50921,
                    "last_hits": 244,
                    "team_abandoned": False,
                    "abandoned_time_s": None,
                    "match_duration_s": 2315,
                    "match_result": 1,
                    "won": True,
                }
            ]
            match_snapshot = save_json_snapshot(
                settings,
                "deadlock_api",
                "players",
                "42-match-history",
                "https://api.deadlock-api.com/v1/players/42/match-history",
                match_payload,
            )
            self.assertEqual(normalize_match_history(settings, match_snapshot, 42, match_payload), 1)

            connection = sqlite3.connect(settings.warehouse_db_path)
            patch_count = connection.execute("SELECT COUNT(*) FROM patch_event").fetchone()[0]
            match_count = connection.execute("SELECT COUNT(*) FROM player_match").fetchone()[0]
            connection.close()

            self.assertEqual(patch_count, 1)
            self.assertEqual(match_count, 1)

    def test_analytics_snapshot_is_persisted_with_query_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)

            payload = [{"hero_id": 72, "matches": 4000, "wins": 2200}]
            snapshot = save_json_snapshot(
                settings,
                "deadlock_api",
                "analytics",
                "v1__analytics__hero-stats--abc123",
                "https://api.deadlock-api.com/v1/analytics/hero-stats?hero_id=72&min_unix_timestamp=100",
                payload,
            )
            normalize_analytics_snapshot(
                settings,
                snapshot,
                endpoint="/v1/analytics/hero-stats",
                query_params={"hero_id": 72, "min_unix_timestamp": 100, "max_unix_timestamp": 200},
                patch_window_label="2026-06-30",
            )

            connection = sqlite3.connect(settings.warehouse_db_path)
            row = connection.execute(
                """
                SELECT endpoint, query_fingerprint, query_params_json, coverage_start, coverage_end, patch_window_label
                FROM analytics_snapshot
                WHERE snapshot_id = ?
                """,
                (snapshot.id,),
            ).fetchone()
            connection.close()

            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(row[0], "/v1/analytics/hero-stats")
            self.assertEqual(row[1], build_query_fingerprint({"hero_id": 72, "min_unix_timestamp": 100, "max_unix_timestamp": 200}))
            self.assertIn('"hero_id": 72', row[2])
            self.assertEqual(row[3], 100)
            self.assertEqual(row[4], 200)
            self.assertEqual(row[5], "2026-06-30")

    def test_infer_query_coverage_supports_multiple_timestamp_families(self) -> None:
        self.assertEqual(infer_query_coverage({"min_unix_timestamp": 10, "max_unix_timestamp": 20}), (10, 20))
        self.assertEqual(
            infer_query_coverage({"min_last_updated_unix_timestamp": 30, "max_last_updated_unix_timestamp": 40}),
            (30, 40),
        )
        self.assertEqual(
            infer_query_coverage({"min_published_unix_timestamp": 50, "max_published_unix_timestamp": 60}),
            (50, 60),
        )
        self.assertEqual(infer_query_coverage({"hero_id": 72}), (None, None))

    def test_hero_and_item_analytics_rows_are_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)

            hero_payload = [
                {"hero_id": 72, "bucket": 0, "matches": 120, "wins": 66, "losses": 54, "total_kills": 500},
            ]
            item_payload = [
                {"item_id": 401, "bucket": 0, "matches": 240, "wins": 132, "losses": 108, "purchases": 260, "avg_bought_at_s": 505.5},
            ]
            hero_snapshot = save_json_snapshot(
                settings,
                "deadlock_api",
                "analytics",
                "hero-stats",
                "https://api.deadlock-api.com/v1/analytics/hero-stats",
                hero_payload,
            )
            item_snapshot = save_json_snapshot(
                settings,
                "deadlock_api",
                "analytics",
                "item-stats",
                "https://api.deadlock-api.com/v1/analytics/item-stats",
                item_payload,
            )
            normalize_analytics_snapshot(settings, hero_snapshot, endpoint="/v1/analytics/hero-stats")
            normalize_analytics_snapshot(settings, item_snapshot, endpoint="/v1/analytics/item-stats")
            self.assertEqual(normalize_hero_analytics_stats(settings, hero_snapshot, hero_payload), 1)
            self.assertEqual(normalize_item_analytics_stats(settings, item_snapshot, item_payload), 1)

            connection = sqlite3.connect(settings.warehouse_db_path)
            hero_row = connection.execute(
                "SELECT hero_id, bucket, matches, wins, total_kills FROM hero_analytics_stat WHERE snapshot_id = ?",
                (hero_snapshot.id,),
            ).fetchone()
            item_row = connection.execute(
                "SELECT item_id, bucket, matches, wins, purchases, avg_bought_at_s FROM item_analytics_stat WHERE snapshot_id = ?",
                (item_snapshot.id,),
            ).fetchone()
            connection.close()

            self.assertEqual(hero_row, (72, "0", 120, 66, 500))
            self.assertEqual(item_row, (401, "0", 240, 132, 260, 505.5))

    def test_item_flow_and_player_curve_are_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)

            item_flow_payload = {
                "summary": {"wins": 10, "losses": 8, "matches": 18, "players": 12, "avg_net_worth": 21000.0, "avg_duration_s": 1800.0},
                "baseline": {"wins": 12, "losses": 10, "matches": 22, "players": 15, "avg_net_worth": 20000.0, "avg_duration_s": 1750.0},
                "reached_per_column": [22, 18, 12],
                "nodes": [
                    {"column": 0, "item_id": 401, "wins": 10, "losses": 8, "matches": 18, "players": 12, "adjusted_win_rate": 0.52, "avg_net_worth_at_buy": 4200.0},
                    {"column": 1, "item_id": 402, "wins": 8, "losses": 6, "matches": 14, "players": 11, "adjusted_win_rate": 0.55, "avg_net_worth_at_buy": 9800.0},
                ],
                "edges": [
                    {"from_column": 0, "from_item_id": 401, "to_item_id": 402, "wins": 8, "losses": 6, "matches": 14},
                ],
            }
            curve_payload = [
                {"game_time": 0, "net_worth_avg": 2100.0, "kills_avg": 0.3, "deaths_avg": 0.5, "assists_avg": 0.4},
                {"game_time": 50, "net_worth_avg": 22000.0, "kills_avg": 4.0, "deaths_avg": 4.5, "assists_avg": 5.2},
            ]
            flow_snapshot = save_json_snapshot(
                settings,
                "deadlock_api",
                "analytics",
                "item-flow",
                "https://api.deadlock-api.com/v1/analytics/item-flow-stats",
                item_flow_payload,
            )
            curve_snapshot = save_json_snapshot(
                settings,
                "deadlock_api",
                "analytics",
                "player-curve",
                "https://api.deadlock-api.com/v1/analytics/player-performance-curve",
                curve_payload,
            )
            normalize_analytics_snapshot(settings, flow_snapshot, endpoint="/v1/analytics/item-flow-stats")
            normalize_analytics_snapshot(settings, curve_snapshot, endpoint="/v1/analytics/player-performance-curve")
            flow_counts = normalize_item_flow_stats(settings, flow_snapshot, item_flow_payload)
            curve_count = normalize_player_performance_curve(settings, curve_snapshot, curve_payload)

            connection = sqlite3.connect(settings.warehouse_db_path)
            flow_summary = connection.execute(
                "SELECT scope, matches FROM item_flow_summary WHERE snapshot_id = ? ORDER BY scope ASC",
                (flow_snapshot.id,),
            ).fetchall()
            flow_node = connection.execute(
                "SELECT column_index, item_id, matches FROM item_flow_node WHERE snapshot_id = ? ORDER BY column_index ASC",
                (flow_snapshot.id,),
            ).fetchall()
            flow_edge = connection.execute(
                "SELECT from_column, from_item_id, to_item_id, matches FROM item_flow_edge WHERE snapshot_id = ?",
                (flow_snapshot.id,),
            ).fetchone()
            curve_rows = connection.execute(
                "SELECT game_time, net_worth_avg, kills_avg, assists_avg FROM player_performance_curve_point WHERE snapshot_id = ? ORDER BY game_time ASC",
                (curve_snapshot.id,),
            ).fetchall()
            connection.close()

            self.assertEqual(flow_counts, {"summaries": 2, "reached_columns": 3, "nodes": 2, "edges": 1})
            self.assertEqual(curve_count, 2)
            self.assertEqual(flow_summary, [("baseline", 22), ("summary", 18)])
            self.assertEqual(flow_node, [(0, 401, 18), (1, 402, 14)])
            self.assertEqual(flow_edge, (0, 401, 402, 14))
            self.assertEqual(curve_rows, [(0, 2100.0, 0.3, 0.4), (50, 22000.0, 4.0, 5.2)])


if __name__ == "__main__":
    unittest.main()
