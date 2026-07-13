from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
import json
from contextlib import contextmanager
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.tools import (
    _resolve_account_id,
    _resolve_optional_account_id,
    get_player_profile,
    get_build_analysis,
    get_comparison_context,
    get_global_hero_stats,
    get_global_item_flow,
    get_global_item_stats,
    get_hero_pool_analysis,
    get_hero_reference,
    get_item_reference,
    get_patch_context,
    get_player_performance_curve,
    get_recent_item_paths,
    get_recent_matches,
    inspect_local_state,
    list_deadlock_reference_catalog,
    list_knowledge_topics,
    retrieve_game_knowledge,
    route_coaching_request,
    search_deadlock_wiki,
    search_knowledge_base,
    search_reference_imports,
)
from deadlock_coach.asset_service import ItemAsset
from deadlock_coach.config import Settings
from deadlock_coach.runtime_context import ActiveCoachContext, use_active_coach_context
from deadlock_coach.storage import _connect, initialize_workspace, normalize_match_history, normalize_patch_feed, save_json_snapshot


def fake_item_asset_factory(labels: dict[int, str]):
    return lambda _settings, item_id: ItemAsset(item_id=item_id, label=labels.get(item_id, str(item_id)), kind="item")


def write_knowledge_note(root: Path, relative_path: str, body: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


class _FakeToolContext:
    def __init__(self, text: str) -> None:
        self.user_content = type(
            "UserContent",
            (),
            {"parts": [type("Part", (), {"text": text})()]},
        )()


class AdkToolsTests(unittest.TestCase):
    class _FakeHttpResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self) -> "AdkToolsTests._FakeHttpResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    @contextmanager
    def _temporary_home(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            previous = os.environ.get("DEADLOCK_COACH_HOME")
            os.environ["DEADLOCK_COACH_HOME"] = tmpdir
            try:
                yield Path(tmpdir)
            finally:
                if previous is None:
                    os.environ.pop("DEADLOCK_COACH_HOME", None)
                else:
                    os.environ["DEADLOCK_COACH_HOME"] = previous

    def test_player_profile_requires_explicit_account_when_multiple_accounts_exist(self) -> None:
        with patch(
            "app.tools.list_tracked_accounts",
            return_value=[
                {"account_id": 101, "label": "EEE"},
                {"account_id": 202, "label": "Alt"},
            ],
        ):
            result = get_player_profile()

        self.assertFalse(result["available"])
        self.assertEqual(result["status"], "account_selection_required")
        self.assertEqual(len(result["accounts"]), 2)

    def test_comparison_context_returns_account_selection_state_when_multiple_accounts_exist(self) -> None:
        with patch(
            "app.tools.list_tracked_accounts",
            return_value=[
                {"account_id": 101, "label": "EEE"},
                {"account_id": 202, "label": "Alt"},
            ],
        ):
            result = get_comparison_context()

        self.assertEqual(result["status"], "account_selection_required")
        self.assertIsNone(result["account_id"])
        self.assertEqual(len(result["accounts"]), 2)

    def test_resolve_account_id_uses_active_runtime_account_context(self) -> None:
        with patch(
            "app.tools.list_tracked_accounts",
            return_value=[
                {"account_id": 101, "label": "EEE"},
                {"account_id": 202, "label": "Alt"},
            ],
        ):
            with use_active_coach_context(ActiveCoachContext(account_id=101, player_label="EEE", window_matches=20)):
                result = _resolve_account_id()

        self.assertEqual(result, 101)

    def test_resolve_optional_account_id_uses_active_runtime_account_context(self) -> None:
        with patch(
            "app.tools.list_tracked_accounts",
            return_value=[
                {"account_id": 101, "label": "EEE"},
                {"account_id": 202, "label": "Alt"},
            ],
        ):
            with use_active_coach_context(ActiveCoachContext(account_id=101, player_label="EEE", window_matches=20)):
                result = _resolve_optional_account_id()

        self.assertEqual(result, 101)

    def test_resolve_account_id_uses_tool_context_prompt_account(self) -> None:
        with patch(
            "app.tools.list_tracked_accounts",
            return_value=[
                {"account_id": 101, "label": "EEE"},
                {"account_id": 202, "label": "Alt"},
            ],
        ):
            result = _resolve_account_id(
                tool_context=_FakeToolContext(
                    "Current workspace context:\n- Active player label: EEE\n- Active account id: 101\n- Window: last 20 matches\n\nUser request:\nwhat do i usually build on billy?"
                )
            )

        self.assertEqual(result, 101)

    def test_resolve_account_id_respects_explicit_no_account_prompt_context(self) -> None:
        with patch(
            "app.tools.list_tracked_accounts",
            return_value=[
                {"account_id": 101, "label": "EEE"},
            ],
        ):
            with self.assertRaisesRegex(ValueError, "No active player or account is selected"):
                _resolve_account_id(
                    tool_context=_FakeToolContext(
                        "Current workspace context:\n- No active player or account is selected.\n\nUser request:\nwhat heroes do i usually play?"
                    )
                )

    def test_comparison_context_uses_active_runtime_account_context(self) -> None:
        with patch(
            "app.tools.list_tracked_accounts",
            return_value=[
                {"account_id": 101, "label": "EEE"},
                {"account_id": 202, "label": "Alt"},
            ],
        ), patch(
            "app.tools._summary_payload",
            return_value={
                "account_id": 101,
                "focus": {"top_hero": "Billy", "top_item": "Monster Rounds"},
            },
        ):
            with use_active_coach_context(ActiveCoachContext(account_id=101, player_label="EEE", window_matches=20)):
                result = get_comparison_context()

        self.assertEqual(result["account_id"], 101)
        self.assertEqual(result["top_hero"], "Billy")

    def test_player_profile_uses_tool_context_prompt_account(self) -> None:
        with patch(
            "app.tools.list_tracked_accounts",
            return_value=[
                {"account_id": 101, "label": "EEE"},
                {"account_id": 202, "label": "Alt"},
            ],
        ), patch(
            "app.tools._summary_payload",
            return_value={"account_id": 101},
        ) as summary_payload:
            result = get_player_profile(
                tool_context=_FakeToolContext(
                    "Current workspace context:\n- Active player label: EEE\n- Active account id: 101\n- Window: last 20 matches\n\nUser request:\nwhat heroes do i usually play?"
                )
            )

        self.assertEqual(result["account_id"], 101)
        self.assertEqual(summary_payload.call_args.kwargs["tool_context"].user_content.parts[0].text.splitlines()[1], "- Active player label: EEE")

    def test_route_coaching_request_stays_usable_without_selected_account(self) -> None:
        with patch(
            "app.tools.list_tracked_accounts",
            return_value=[
                {"account_id": 101, "label": "EEE"},
                {"account_id": 202, "label": "Alt"},
            ],
        ):
            result = route_coaching_request("What should I build on Lash?")

        self.assertEqual(result["routing"]["family"], "timing")
        self.assertEqual(result["selected_specialists"], ["coach_agent"])
        self.assertIn("knowledge", result["routing"]["analyst_lanes"])
        self.assertIn("knowledge_base_lookup", result["tool_hints"])

    def test_route_coaching_request_prioritizes_kb_for_spike_question_with_account(self) -> None:
        with self._temporary_home() as root:
            settings = Settings(project_root=root)
            initialize_workspace(settings)
            write_knowledge_note(
                root,
                "docs/knowledge/builds/investment-families-and-spikes.md",
                "# Investment Families And Spikes\n\n- spike means a real in-game power jump\n",
            )

            match_payload = [
                {
                    "match_id": 9101,
                    "hero_id": 72,
                    "hero_level": 24,
                    "start_time": 1783288584,
                    "game_mode": 1,
                    "match_mode": 4,
                    "player_team": 0,
                    "player_kills": 9,
                    "player_deaths": 8,
                    "player_assists": 11,
                    "denies": 7,
                    "net_worth": 40500,
                    "last_hits": 220,
                    "team_abandoned": False,
                    "abandoned_time_s": None,
                    "match_duration_s": 2200,
                    "match_result": 1,
                    "won": True,
                }
            ]
            snapshot = save_json_snapshot(
                settings,
                "deadlock_api",
                "players",
                "303017110-match-history",
                "https://api.deadlock-api.com/v1/players/303017110/match-history",
                match_payload,
            )
            normalize_match_history(settings, snapshot, 303017110, match_payload)

            result = route_coaching_request(
                "what spike do i get first, 4.8k?",
                account_id=303017110,
                hero_name="Billy",
            )

        self.assertEqual(result["routing"]["family"], "timing")
        self.assertEqual(result["selected_specialists"], ["coach_agent"])
        self.assertIn("data", result["routing"]["analyst_lanes"])
        self.assertIn("knowledge", result["routing"]["analyst_lanes"])
        self.assertIn("knowledge_base_lookup", result["tool_hints"])
        self.assertIn("build_analysis", result["tool_hints"])

    def test_inspect_local_state_returns_account_list_when_multiple_accounts_exist(self) -> None:
        accounts = [
            {"account_id": 101, "label": "EEE"},
            {"account_id": 202, "label": "Alt"},
        ]
        with patch("app.tools.list_tracked_accounts", return_value=accounts):
            result = inspect_local_state()

        self.assertIsNone(result["account_id"])
        self.assertEqual(result["accounts"], accounts)
        self.assertIsNone(result["profile"])

    def test_search_knowledge_base_returns_matching_excerpt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            knowledge_dir = root / "docs" / "knowledge"
            knowledge_dir.mkdir(parents=True)
            (knowledge_dir / "billy-notes.md").write_text(
                "# Billy\nBilly likes short trades into Shiv when you already have lane control.\n",
                encoding="utf-8",
            )

            previous = os.environ.get("DEADLOCK_COACH_HOME")
            os.environ["DEADLOCK_COACH_HOME"] = str(root)
            try:
                result = search_knowledge_base("Billy into Shiv", limit=2)
            finally:
                if previous is None:
                    os.environ.pop("DEADLOCK_COACH_HOME", None)
                else:
                    os.environ["DEADLOCK_COACH_HOME"] = previous

            self.assertEqual(result["source"], "knowledge_base")
            self.assertEqual(len(result["matches"]), 1)
            self.assertIn("Billy", result["matches"][0]["excerpt"])

    def test_retrieve_game_knowledge_returns_fact_entities_and_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            pages = root / "docs" / "knowledge" / "_imports" / "wiki" / "pages"
            fundamentals = root / "docs" / "knowledge" / "fundamentals"
            pages.mkdir(parents=True, exist_ok=True)
            fundamentals.mkdir(parents=True, exist_ok=True)
            (pages / "379-items.md").write_text(
                (
                    "# Items\n\n"
                    "### Item Type Bonuses by Souls\n\n"
                    "| Souls | Weapon | Vitality | Spirit |\n"
                    "| --- | --- | --- | --- |\n"
                    "| 6,400 | +54% | +42% | +45 |\n"
                ),
                encoding="utf-8",
            )
            (fundamentals / "investment-spikes.md").write_text(
                "# Investment Spikes\n\n- 4.8k is the standout category breakpoint.\n",
                encoding="utf-8",
            )

            previous = os.environ.get("DEADLOCK_COACH_HOME")
            os.environ["DEADLOCK_COACH_HOME"] = str(root)
            try:
                result = retrieve_game_knowledge("how much bonus spirit do you get after 6.4k investment")
            finally:
                if previous is None:
                    os.environ.pop("DEADLOCK_COACH_HOME", None)
                else:
                    os.environ["DEADLOCK_COACH_HOME"] = previous

            self.assertEqual(result["source"], "knowledge_retriever")
            self.assertIn("+45", str(result["fact"]))
            self.assertTrue(result["matches"])

    def test_search_reference_imports_strips_import_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            import_dir = root / "docs" / "knowledge" / "_imports" / "wiki" / "pages"
            import_dir.mkdir(parents=True)
            (import_dir / "799-boon.md").write_text(
                (
                    "# Boon\n\n"
                    "Imported reference\n\n"
                    "- kind: pages\n"
                    "- source: Deadlock Wiki\n"
                    "- url: https://deadlock.wiki/Boon\n"
                    "- imported_at: 2026-07-08T10:00:00Z\n\n"
                    "Reference extract:\n\n"
                    "Boons indicate the player's power level over the course of the match.\n"
                    "Players gain boons by gathering souls.\n"
                ),
                encoding="utf-8",
            )

            previous = os.environ.get("DEADLOCK_COACH_HOME")
            os.environ["DEADLOCK_COACH_HOME"] = str(root)
            try:
                result = search_reference_imports("what are boons", limit=2)
            finally:
                if previous is None:
                    os.environ.pop("DEADLOCK_COACH_HOME", None)
                else:
                    os.environ["DEADLOCK_COACH_HOME"] = previous

            self.assertEqual(result["source"], "knowledge_imports")
            self.assertEqual(len(result["matches"]), 1)
            self.assertIn("power level", result["matches"][0]["excerpt"])
            self.assertNotIn("kind:", result["matches"][0]["excerpt"])

    def test_get_patch_context_returns_local_synced_patch_matches(self) -> None:
        with self._temporary_home() as root:
            settings = Settings(project_root=root)
            initialize_workspace(settings)
            payload = [
                {
                    "source": "deadlock-api",
                    "title": "July Balance Update",
                    "pub_date": "2026-07-08T10:00:00Z",
                    "link": "https://example.com/patch/july-balance",
                    "guid": {"text": "patch-july-balance"},
                    "content": "Billy spirit scaling adjusted and several item tuning notes were included.",
                }
            ]
            snapshot = save_json_snapshot(
                settings,
                "deadlock_api",
                "patches",
                "unified-feed",
                "https://api.deadlock-api.com/v2/patches",
                payload,
            )
            normalize_patch_feed(settings, snapshot, payload)

            result = get_patch_context(query="Billy")

        self.assertTrue(result["available"])
        self.assertEqual(len(result["matches"]), 1)
        self.assertEqual(result["matches"][0]["title"], "July Balance Update")
        self.assertIn("Billy spirit scaling adjusted", result["matches"][0]["excerpt"])
        self.assertEqual(result["matches"][0]["published_at_label"], "July 8, 2026")

    def test_get_patch_context_falls_back_to_live_patch_feed(self) -> None:
        with self._temporary_home() as root:
            payload = [
                {
                    "source": "steam",
                    "title": "Minor Update - 07-01-2026",
                    "pub_date": "2026-07-01T22:54:59Z",
                    "link": "https://store.steampowered.com/news/app/1422450/view/demo",
                    "content": "<p>- Shiv: Slice and Dice now does spirit damage again</p>",
                }
            ]
            with patch("app.tools.DeadlockApiClient.fetch_json", return_value=("https://api.deadlock-api.com/v2/patches", payload)):
                result = get_patch_context(query="Shiv")

        self.assertTrue(result["available"])
        self.assertEqual(result["source"], "deadlock_api_live")
        self.assertEqual(result["matches"][0]["title"], "Minor Update - 07-01-2026")
        self.assertIn("Slice and Dice", result["matches"][0]["excerpt"])

    def test_get_global_hero_stats_returns_pickrate_and_winrate_leaders(self) -> None:
        payload = [
            {"hero_id": 1, "wins": 60, "losses": 40, "matches": 100},
            {"hero_id": 2, "wins": 88, "losses": 32, "matches": 120},
            {"hero_id": 3, "wins": 54, "losses": 36, "matches": 90},
        ]
        with self._temporary_home():
            with patch("app.tools.DeadlockApiClient.fetch_json", return_value=("https://api.deadlock-api.com/v1/analytics/hero-stats", payload)):
                with patch(
                    "app.tools.hero_label",
                    side_effect=lambda _settings, hero_id, client=None: {1: "Billy", 2: "Pocket", 3: "Shiv"}[hero_id],
                ):
                    result = get_global_hero_stats(limit=2, min_matches=50)

        self.assertEqual(result["source"], "deadlock_api_live")
        self.assertEqual(result["top_pickrate"][0]["hero_label"], "Pocket")
        self.assertEqual(result["top_winrate"][0]["hero_label"], "Pocket")
        self.assertAlmostEqual(result["top_winrate"][0]["win_rate"], 73.3, places=1)

    def test_get_global_hero_stats_prefers_local_snapshot_when_available(self) -> None:
        with self._temporary_home() as root:
            settings = Settings(project_root=root)
            initialize_workspace(settings)
            connection = _connect(settings.warehouse_db_path)
            connection.execute(
                """
                INSERT INTO source_snapshot (
                    id, provider, entity_type, entity_key, fetched_at, request_url, content_sha256, raw_path, content_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    "deadlock_api",
                    "analytics",
                    "hero-stats-default",
                    "2026-07-09T10:00:00+00:00",
                    "https://api.deadlock-api.com/v1/analytics/hero-stats",
                    "sha",
                    "data/raw/deadlock_api/analytics/hero-stats.json",
                    "application/json",
                ),
            )
            connection.execute(
                """
                INSERT INTO analytics_snapshot (
                    snapshot_id, endpoint, query_fingerprint, query_params_json, coverage_start, coverage_end, patch_window_label
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (1, "/v1/analytics/hero-stats", "fingerprint", "{}", None, None, None),
            )
            connection.execute(
                """
                INSERT INTO hero_analytics_stat (
                    snapshot_id, hero_id, bucket, matches, wins, losses, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (1, 1, "", 100, 60, 40, "{}"),
            )
            connection.execute(
                """
                INSERT INTO hero_analytics_stat (
                    snapshot_id, hero_id, bucket, matches, wins, losses, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (1, 2, "", 120, 88, 32, "{}"),
            )
            connection.commit()
            connection.close()

            with patch("deadlock_coach.analytics_service.hero_label", side_effect=lambda _settings, hero_id, client=None: {1: "Billy", 2: "Pocket"}[hero_id]):
                with patch("app.tools.DeadlockApiClient.fetch_json", side_effect=AssertionError("live fallback should not be used")):
                    result = get_global_hero_stats(limit=2, min_matches=50)

        self.assertEqual(result["source"], "local_sqlite")
        self.assertEqual(result["top_pickrate"][0]["hero_label"], "Pocket")

    def test_get_global_hero_stats_supports_rank_filter(self) -> None:
        payload = [
            {"hero_id": 1, "wins": 60, "losses": 40, "matches": 100},
            {"hero_id": 2, "wins": 88, "losses": 32, "matches": 120},
        ]
        with self._temporary_home():
            with patch(
                "app.tools.DeadlockApiClient.fetch_json",
                side_effect=[
                    ("https://statlocker.gg/api/info/ranks-full", [{"tier": 11, "name": "Eternus"}]),
                    ("https://api.deadlock-api.com/v1/analytics/hero-stats?min_average_badge=111&max_average_badge=116", payload),
                ],
            ) as fetch_mock:
                with patch(
                    "app.tools.hero_label",
                    side_effect=lambda _settings, hero_id, client=None: {1: "Billy", 2: "Pocket"}[hero_id],
                ):
                    result = get_global_hero_stats(limit=2, min_matches=50, rank_name="Eternus")

        self.assertEqual(result["source"], "deadlock_api_live")
        self.assertEqual(result["rank_filter"]["name"], "Eternus")
        self.assertEqual(result["rank_filter"]["min_average_badge"], 111)
        self.assertEqual(result["rank_filter"]["max_average_badge"], 116)
        self.assertEqual(fetch_mock.call_count, 2)

    def test_get_global_hero_stats_relaxes_default_winrate_threshold_for_rank_filter(self) -> None:
        payload = [
            {"hero_id": 1, "wins": 6000, "losses": 4000, "matches": 10000},
            {"hero_id": 2, "wins": 8800, "losses": 3200, "matches": 12000},
        ]
        with self._temporary_home():
            with patch(
                "app.tools.DeadlockApiClient.fetch_json",
                side_effect=[
                    ("https://statlocker.gg/api/info/ranks-full", [{"tier": 11, "name": "Eternus"}]),
                    ("https://api.deadlock-api.com/v1/analytics/hero-stats?min_average_badge=111&max_average_badge=116", payload),
                ],
            ):
                with patch(
                    "app.tools.hero_label",
                    side_effect=lambda _settings, hero_id, client=None: {1: "Billy", 2: "Pocket"}[hero_id],
                ):
                    result = get_global_hero_stats(rank_name="Eternus")

        self.assertEqual(result["top_winrate"][0]["hero_label"], "Pocket")
        self.assertEqual(result["min_matches_for_winrate"], 10000)

    def test_get_global_hero_stats_relaxes_default_winrate_threshold_more_for_rank_subtier_filter(self) -> None:
        payload = [
            {"hero_id": 1, "wins": 600, "losses": 400, "matches": 1000},
            {"hero_id": 2, "wins": 880, "losses": 320, "matches": 1200},
        ]
        with self._temporary_home():
            with patch(
                "app.tools.DeadlockApiClient.fetch_json",
                side_effect=[
                    ("https://statlocker.gg/api/info/ranks-full", [{"tier": 11, "name": "Eternus"}]),
                    ("https://api.deadlock-api.com/v1/analytics/hero-stats?min_average_badge=116&max_average_badge=116", payload),
                ],
            ):
                with patch(
                    "app.tools.hero_label",
                    side_effect=lambda _settings, hero_id, client=None: {1: "Billy", 2: "Pocket"}[hero_id],
                ):
                    result = get_global_hero_stats(rank_name="Eternus 6")

        self.assertEqual(result["top_winrate"][0]["hero_label"], "Pocket")
        self.assertEqual(result["min_matches_for_winrate"], 1000)

    def test_get_build_analysis_uses_deeper_item_paths_for_hero_slice(self) -> None:
        with patch("app.tools._summary_payload", return_value={"account_id": 303017110}):
            with patch("app.tools.get_recent_item_paths", return_value={"matches": []}) as recent_paths_mock:
                get_build_analysis(account_id=303017110, hero_name="Shiv", window_matches=20)

        self.assertEqual(recent_paths_mock.call_args.kwargs["items_per_match"], 16)

    def test_get_global_item_stats_returns_usage_and_winrate_leaders(self) -> None:
        payload = [
            {"item_id": 401, "wins": 132, "losses": 108, "matches": 240, "purchases": 260, "avg_bought_at_s": 505.5},
            {"item_id": 402, "wins": 120, "losses": 60, "matches": 180, "purchases": 200, "avg_bought_at_s": 820.0},
            {"item_id": 403, "wins": 70, "losses": 50, "matches": 120, "purchases": 130, "avg_bought_at_s": 910.0},
        ]
        with self._temporary_home():
            with patch("app.tools.DeadlockApiClient.fetch_json", return_value=("https://api.deadlock-api.com/v1/analytics/item-stats", payload)):
                with patch(
                    "app.tools.item_label",
                    side_effect=lambda _settings, item_id: {401: "Monster Rounds", 402: "Warp Stone", 403: "Healbane"}[item_id],
                ):
                    result = get_global_item_stats(limit=2, min_matches=100)

        self.assertEqual(result["source"], "deadlock_api_live")
        self.assertEqual(result["top_usage"][0]["item_label"], "Monster Rounds")
        self.assertEqual(result["top_winrate"][0]["item_label"], "Warp Stone")

    def test_get_global_item_stats_supports_rank_subtier_filter(self) -> None:
        payload = [
            {"item_id": 401, "wins": 132, "losses": 108, "matches": 240, "purchases": 260, "avg_bought_at_s": 505.5},
            {"item_id": 402, "wins": 120, "losses": 60, "matches": 180, "purchases": 200, "avg_bought_at_s": 820.0},
        ]
        with self._temporary_home():
            with patch(
                "app.tools.DeadlockApiClient.fetch_json",
                side_effect=[
                    ("https://statlocker.gg/api/info/ranks-full", [{"tier": 11, "name": "Eternus"}]),
                    ("https://api.deadlock-api.com/v1/analytics/item-stats?min_average_badge=116&max_average_badge=116", payload),
                ],
            ) as fetch_mock:
                with patch(
                    "app.tools.item_label",
                    side_effect=lambda _settings, item_id: {401: "Monster Rounds", 402: "Warp Stone"}[item_id],
                ):
                    result = get_global_item_stats(limit=2, min_matches=100, rank_name="Eternus 6")

        self.assertEqual(result["source"], "deadlock_api_live")
        self.assertEqual(result["rank_filter"]["name"], "Eternus 6")
        self.assertEqual(result["rank_filter"]["min_average_badge"], 116)
        self.assertEqual(result["rank_filter"]["max_average_badge"], 116)
        self.assertEqual(fetch_mock.call_count, 2)

    def test_get_global_item_flow_prefers_local_snapshot_when_available(self) -> None:
        with self._temporary_home() as root:
            settings = Settings(project_root=root)
            initialize_workspace(settings)
            connection = _connect(settings.warehouse_db_path)
            connection.execute(
                """
                INSERT INTO source_snapshot (
                    id, provider, entity_type, entity_key, fetched_at, request_url, content_sha256, raw_path, content_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    11,
                    "deadlock_api",
                    "analytics",
                    "item-flow-billy",
                    "2026-07-09T11:00:00+00:00",
                    "https://api.deadlock-api.com/v1/analytics/item-flow-stats?hero_id=72",
                    "sha",
                    "data/raw/deadlock_api/analytics/item-flow.json",
                    "application/json",
                ),
            )
            connection.execute(
                """
                INSERT INTO analytics_snapshot (
                    snapshot_id, endpoint, query_fingerprint, query_params_json, coverage_start, coverage_end, patch_window_label
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (11, "/v1/analytics/item-flow-stats", "fingerprint", '{"hero_id": 72}', None, None, None),
            )
            connection.execute(
                """
                INSERT INTO item_flow_summary (
                    snapshot_id, scope, wins, losses, matches, players, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (11, "summary", 10, 8, 18, 12, "{}"),
            )
            connection.execute(
                """
                INSERT INTO item_flow_summary (
                    snapshot_id, scope, wins, losses, matches, players, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (11, "baseline", 12, 10, 22, 15, "{}"),
            )
            connection.execute(
                """
                INSERT INTO item_flow_reach (
                    snapshot_id, column_index, reached_matches
                ) VALUES (?, ?, ?), (?, ?, ?)
                """,
                (11, 0, 22, 11, 1, 18),
            )
            connection.execute(
                """
                INSERT INTO item_flow_node (
                    snapshot_id, column_index, item_id, wins, losses, matches, players, adjusted_win_rate, avg_net_worth_at_buy, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    11, 0, 401, 10, 8, 18, 12, 0.52, 4200.0, "{}",
                    11, 1, 402, 8, 6, 14, 11, 0.55, 9800.0, "{}",
                ),
            )
            connection.execute(
                """
                INSERT INTO item_flow_edge (
                    snapshot_id, from_column, from_item_id, to_item_id, wins, losses, matches, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (11, 0, 401, 402, 8, 6, 14, "{}"),
            )
            connection.commit()
            connection.close()

            with patch("deadlock_coach.analytics_service.resolve_hero_id", return_value=72):
                with patch("deadlock_coach.analytics_service.item_label", side_effect=lambda _settings, item_id: {401: "Monster Rounds", 402: "Warp Stone"}[item_id]):
                    with patch("app.tools.DeadlockApiClient.fetch_json", side_effect=AssertionError("live fallback should not be used")):
                        result = get_global_item_flow(hero_name="Billy", stage_limit=2, transition_limit=3)

        self.assertEqual(result["source"], "local_sqlite")
        self.assertEqual(result["stages"][0]["top_items"][0]["item_label"], "Monster Rounds")
        self.assertEqual(result["top_transitions"][0]["to_item_label"], "Warp Stone")

    def test_get_global_item_flow_supports_rank_subtier_filter(self) -> None:
        payload = {
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
        }
        with self._temporary_home():
            with patch(
                "app.tools.DeadlockApiClient.fetch_json",
                side_effect=[
                    ("https://statlocker.gg/api/info/ranks-full", [{"tier": 11, "name": "Eternus"}]),
                    ("https://api.deadlock-api.com/v1/assets/heroes", [{"id": 72, "name": "Billy"}]),
                    (
                        "https://api.deadlock-api.com/v1/analytics/item-flow-stats?min_matches=20&min_average_badge=116&max_average_badge=116&hero_id=72",
                        payload,
                    ),
                ],
            ) as fetch_mock:
                with patch(
                    "app.tools.item_label",
                    side_effect=lambda _settings, item_id, client=None: {401: "Monster Rounds", 402: "Warp Stone"}[item_id],
                ):
                    result = get_global_item_flow(hero_name="Billy", rank_name="Eternus 6")

        self.assertEqual(result["source"], "deadlock_api_live")
        self.assertEqual(result["rank_filter"]["name"], "Eternus 6")
        self.assertEqual(result["rank_filter"]["min_average_badge"], 116)
        self.assertEqual(result["rank_filter"]["max_average_badge"], 116)
        self.assertEqual(fetch_mock.call_count, 3)

    def test_get_global_item_flow_fails_soft_when_live_endpoint_errors(self) -> None:
        with self._temporary_home():
            with patch("app.tools.read_latest_item_flow_summary", return_value=None):
                with patch("app.tools.DeadlockApiClient.fetch_json", side_effect=RuntimeError("upstream failed")):
                    result = get_global_item_flow()

        self.assertFalse(result["available"])
        self.assertIsNone(result["hero_filter"])
        self.assertIn("upstream failed", result["note"])

    def test_get_player_performance_curve_prefers_local_snapshot_when_available(self) -> None:
        with self._temporary_home() as root:
            settings = Settings(project_root=root)
            initialize_workspace(settings)
            connection = _connect(settings.warehouse_db_path)
            connection.execute(
                """
                INSERT INTO source_snapshot (
                    id, provider, entity_type, entity_key, fetched_at, request_url, content_sha256, raw_path, content_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    12,
                    "deadlock_api",
                    "analytics",
                    "player-curve-eee",
                    "2026-07-09T11:30:00+00:00",
                    "https://api.deadlock-api.com/v1/analytics/player-performance-curve?account_ids=303017110&resolution=10",
                    "sha",
                    "data/raw/deadlock_api/analytics/player-curve.json",
                    "application/json",
                ),
            )
            connection.execute(
                """
                INSERT INTO analytics_snapshot (
                    snapshot_id, endpoint, query_fingerprint, query_params_json, coverage_start, coverage_end, patch_window_label
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (12, "/v1/analytics/player-performance-curve", "fingerprint", '{"account_ids": [303017110], "resolution": 10}', None, None, None),
            )
            connection.execute(
                """
                INSERT INTO player_performance_curve_point (
                    snapshot_id, game_time, net_worth_avg, kills_avg, deaths_avg, assists_avg, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?), (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    12, 0, 2100.0, 0.3, 0.5, 0.4, "{}",
                    12, 50, 22000.0, 4.0, 4.5, 5.2, "{}",
                    12, 100, 44000.0, 8.6, 8.0, 13.4, "{}",
                ),
            )
            connection.commit()
            connection.close()

            with patch("app.tools.DeadlockApiClient.fetch_json", side_effect=AssertionError("live fallback should not be used")):
                result = get_player_performance_curve(account_id=303017110, resolution=10)

        self.assertEqual(result["source"], "local_sqlite")
        self.assertEqual([point["game_time_label"] for point in result["checkpoints"]], ["0%", "50%", "100%"])

    def test_list_knowledge_topics_returns_seeded_topics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            knowledge_dir = root / "docs" / "knowledge" / "heroes"
            knowledge_dir.mkdir(parents=True)
            (knowledge_dir / "lash.md").write_text("# Lash\nAggressive opener notes.\n", encoding="utf-8")

            previous = os.environ.get("DEADLOCK_COACH_HOME")
            os.environ["DEADLOCK_COACH_HOME"] = str(root)
            try:
                result = list_knowledge_topics(limit=10)
            finally:
                if previous is None:
                    os.environ.pop("DEADLOCK_COACH_HOME", None)
                else:
                    os.environ["DEADLOCK_COACH_HOME"] = previous

            self.assertEqual(result["source"], "knowledge_base")
            self.assertEqual(result["topics"][0]["group"], "heroes")
            self.assertEqual(result["topics"][0]["title"], "Lash")

    def test_list_deadlock_reference_catalog_filters_out_translations_and_index_pages(self) -> None:
        payload = {
            "query": {
                "categorymembers": [
                    {"title": "Heroes"},
                    {"title": "Lash"},
                    {"title": "Shiv/ru"},
                    {"title": "Billy"},
                ]
            }
        }
        with self._temporary_home():
            with patch("app.tools.urlopen", return_value=self._FakeHttpResponse(payload)):
                result = list_deadlock_reference_catalog("heroes", limit=10)

        self.assertTrue(result["available"])
        self.assertEqual(result["titles"], ["Lash", "Billy"])

    def test_get_hero_reference_returns_page_extract(self) -> None:
        payload = {
            "query": {
                "pages": {
                    "60": {
                        "pageid": 60,
                        "title": "Lash",
                        "extract": "Lash is a bruiser initiator.",
                    }
                }
            }
        }
        with self._temporary_home():
            with patch("app.tools.urlopen", return_value=self._FakeHttpResponse(payload)):
                result = get_hero_reference("the lash")

        self.assertTrue(result["available"])
        self.assertEqual(result["page"]["title"], "Lash")
        self.assertIn("bruiser initiator", result["page"]["extract"])

    def test_search_deadlock_wiki_strips_html_from_snippets(self) -> None:
        payload = {
            "query": {
                "search": [
                    {
                        "title": "Healing Rite",
                        "pageid": 435,
                        "snippet": "<span class='searchmatch'>Healing</span> sustain item",
                    }
                ]
            }
        }
        with self._temporary_home():
            with patch("app.tools.urlopen", return_value=self._FakeHttpResponse(payload)):
                result = search_deadlock_wiki("healing", limit=5)

        self.assertTrue(result["available"])
        self.assertEqual(result["matches"][0]["title"], "Healing Rite")
        self.assertEqual(result["matches"][0]["snippet"], "Healing sustain item")

    def test_get_item_reference_returns_page_extract(self) -> None:
        payload = {
            "query": {
                "pages": {
                    "435": {
                        "pageid": 435,
                        "title": "Healing Rite",
                        "extract": "Healing Rite is a Tier 1 Vitality item.",
                    }
                }
            }
        }
        with self._temporary_home():
            with patch("app.tools.urlopen", return_value=self._FakeHttpResponse(payload)):
                result = get_item_reference("Healing Rite")

        self.assertTrue(result["available"])
        self.assertEqual(result["page"]["title"], "Healing Rite")
        self.assertIn("Tier 1", result["page"]["extract"])

    def test_list_deadlock_reference_catalog_falls_back_to_imported_topics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            imported_dir = root / "docs" / "knowledge" / "_imports" / "wiki" / "heroes"
            imported_dir.mkdir(parents=True)
            (imported_dir / "lash.md").write_text("# Lash\nImported reference.\n", encoding="utf-8")
            (imported_dir / "shiv.md").write_text("# Shiv\nImported reference.\n", encoding="utf-8")

            with patch.dict(os.environ, {"DEADLOCK_COACH_HOME": str(root)}, clear=False):
                with patch("app.tools.urlopen", side_effect=RuntimeError("offline")):
                    result = list_deadlock_reference_catalog("heroes", limit=10)

        self.assertTrue(result["available"])
        self.assertEqual(result["source"], "local_knowledge")
        self.assertEqual(result["titles"], ["Lash", "Shiv"])

    def test_get_hero_reference_falls_back_to_imported_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            imported_dir = root / "docs" / "knowledge" / "_imports" / "wiki" / "heroes"
            imported_dir.mkdir(parents=True)
            (imported_dir / "haze.md").write_text(
                "# Haze\n\nImported reference\n\nReference extract:\n\nHaze is an assassin hero.\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"DEADLOCK_COACH_HOME": str(root)}, clear=False):
                with patch("app.tools.urlopen", side_effect=RuntimeError("offline")):
                    result = get_hero_reference("Haze")

        self.assertTrue(result["available"])
        self.assertEqual(result["source"], "local_knowledge")
        self.assertEqual(result["page"]["title"], "Haze")
        self.assertIn("assassin hero", result["page"]["extract"])

    def test_get_hero_pool_analysis_uses_recent_local_sample(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(project_root=root)
            initialize_workspace(settings)

            match_payload = [
                {
                    "match_id": 901,
                    "hero_id": 1,
                    "hero_level": 24,
                    "start_time": 1783288584,
                    "game_mode": 1,
                    "match_mode": 4,
                    "player_team": 0,
                    "player_kills": 9,
                    "player_deaths": 8,
                    "player_assists": 11,
                    "denies": 7,
                    "net_worth": 40500,
                    "last_hits": 220,
                    "team_abandoned": False,
                    "abandoned_time_s": None,
                    "match_duration_s": 2200,
                    "match_result": 0,
                    "won": False,
                },
                {
                    "match_id": 902,
                    "hero_id": 1,
                    "hero_level": 24,
                    "start_time": 1783202184,
                    "game_mode": 1,
                    "match_mode": 4,
                    "player_team": 0,
                    "player_kills": 11,
                    "player_deaths": 7,
                    "player_assists": 10,
                    "denies": 6,
                    "net_worth": 41500,
                    "last_hits": 228,
                    "team_abandoned": False,
                    "abandoned_time_s": None,
                    "match_duration_s": 2250,
                    "match_result": 1,
                    "won": True,
                },
                {
                    "match_id": 903,
                    "hero_id": 2,
                    "hero_level": 23,
                    "start_time": 1783115784,
                    "game_mode": 1,
                    "match_mode": 4,
                    "player_team": 0,
                    "player_kills": 8,
                    "player_deaths": 9,
                    "player_assists": 12,
                    "denies": 5,
                    "net_worth": 39900,
                    "last_hits": 210,
                    "team_abandoned": False,
                    "abandoned_time_s": None,
                    "match_duration_s": 2270,
                    "match_result": 0,
                    "won": False,
                },
            ]
            match_snapshot = save_json_snapshot(
                settings,
                "deadlock_api",
                "players",
                "901-match-history",
                "https://api.deadlock-api.com/v1/players/901/match-history",
                match_payload,
            )
            normalize_match_history(settings, match_snapshot, 901, match_payload)

            previous = os.environ.get("DEADLOCK_COACH_HOME")
            os.environ["DEADLOCK_COACH_HOME"] = str(root)
            try:
                with patch("deadlock_coach.coach_service.hero_label", side_effect=lambda _settings, hero_id: {1: "Billy", 2: "Shiv"}.get(hero_id, str(hero_id))):
                    result = get_hero_pool_analysis(account_id=901, window_matches=10)
            finally:
                if previous is None:
                    os.environ.pop("DEADLOCK_COACH_HOME", None)
                else:
                    os.environ["DEADLOCK_COACH_HOME"] = previous

            self.assertEqual(result["source"], "local_sqlite")
            self.assertEqual(result["hero_pool"][0]["hero_label"], "Billy")
            self.assertEqual(result["top_hero"]["hero_label"], "Billy")

    def test_get_hero_pool_analysis_can_expand_to_full_local_sample(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(project_root=root)
            initialize_workspace(settings)

            match_payload = [
                {
                    "match_id": 910,
                    "hero_id": 2,
                    "hero_level": 24,
                    "start_time": 1783288584,
                    "game_mode": 1,
                    "match_mode": 4,
                    "player_team": 0,
                    "player_kills": 9,
                    "player_deaths": 8,
                    "player_assists": 11,
                    "denies": 7,
                    "net_worth": 40500,
                    "last_hits": 220,
                    "team_abandoned": False,
                    "abandoned_time_s": None,
                    "match_duration_s": 2200,
                    "match_result": 0,
                    "won": False,
                },
                {
                    "match_id": 911,
                    "hero_id": 2,
                    "hero_level": 24,
                    "start_time": 1783202184,
                    "game_mode": 1,
                    "match_mode": 4,
                    "player_team": 0,
                    "player_kills": 7,
                    "player_deaths": 9,
                    "player_assists": 10,
                    "denies": 6,
                    "net_worth": 39500,
                    "last_hits": 205,
                    "team_abandoned": False,
                    "abandoned_time_s": None,
                    "match_duration_s": 2250,
                    "match_result": 0,
                    "won": False,
                },
                {
                    "match_id": 912,
                    "hero_id": 1,
                    "hero_level": 24,
                    "start_time": 1783115784,
                    "game_mode": 1,
                    "match_mode": 4,
                    "player_team": 0,
                    "player_kills": 6,
                    "player_deaths": 7,
                    "player_assists": 8,
                    "denies": 5,
                    "net_worth": 38100,
                    "last_hits": 198,
                    "team_abandoned": False,
                    "abandoned_time_s": None,
                    "match_duration_s": 2180,
                    "match_result": 1,
                    "won": True,
                },
                {
                    "match_id": 913,
                    "hero_id": 1,
                    "hero_level": 24,
                    "start_time": 1783029384,
                    "game_mode": 1,
                    "match_mode": 4,
                    "player_team": 0,
                    "player_kills": 8,
                    "player_deaths": 6,
                    "player_assists": 12,
                    "denies": 8,
                    "net_worth": 42900,
                    "last_hits": 232,
                    "team_abandoned": False,
                    "abandoned_time_s": None,
                    "match_duration_s": 2270,
                    "match_result": 1,
                    "won": True,
                },
                {
                    "match_id": 914,
                    "hero_id": 1,
                    "hero_level": 24,
                    "start_time": 1782942984,
                    "game_mode": 1,
                    "match_mode": 4,
                    "player_team": 0,
                    "player_kills": 10,
                    "player_deaths": 5,
                    "player_assists": 9,
                    "denies": 9,
                    "net_worth": 43800,
                    "last_hits": 236,
                    "team_abandoned": False,
                    "abandoned_time_s": None,
                    "match_duration_s": 2290,
                    "match_result": 1,
                    "won": True,
                },
            ]
            match_snapshot = save_json_snapshot(
                settings,
                "deadlock_api",
                "players",
                "915-match-history",
                "https://api.deadlock-api.com/v1/players/915/match-history",
                match_payload,
            )
            normalize_match_history(settings, match_snapshot, 915, match_payload)

            previous = os.environ.get("DEADLOCK_COACH_HOME")
            os.environ["DEADLOCK_COACH_HOME"] = str(root)
            try:
                with patch("deadlock_coach.coach_service.hero_label", side_effect=lambda _settings, hero_id: {1: "Pocket", 2: "Shiv"}.get(hero_id, str(hero_id))):
                    with patch("app.tools.hero_label", side_effect=lambda _settings, hero_id: {1: "Pocket", 2: "Shiv"}.get(hero_id, str(hero_id))):
                        result = get_hero_pool_analysis(account_id=915, window_matches=2, full_sample=True)
            finally:
                if previous is None:
                    os.environ.pop("DEADLOCK_COACH_HOME", None)
                else:
                    os.environ["DEADLOCK_COACH_HOME"] = previous

        self.assertEqual(result["sample_scope"], "full_local_sample")
        self.assertEqual(result["window_matches"], 5)
        self.assertEqual(result["hero_pool"][0]["hero_label"], "Pocket")

    def test_recent_match_tools_return_match_and_item_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(project_root=root)
            initialize_workspace(settings)

            match_payload = [
                {
                    "match_id": 910,
                    "hero_id": 1,
                    "hero_level": 24,
                    "start_time": 1783288584,
                    "game_mode": 1,
                    "match_mode": 4,
                    "player_team": 0,
                    "player_kills": 9,
                    "player_deaths": 8,
                    "player_assists": 11,
                    "denies": 7,
                    "net_worth": 40500,
                    "last_hits": 220,
                    "team_abandoned": False,
                    "abandoned_time_s": None,
                    "match_duration_s": 2200,
                    "match_result": 0,
                    "won": False,
                }
            ]
            match_snapshot = save_json_snapshot(
                settings,
                "deadlock_api",
                "players",
                "910-match-history",
                "https://api.deadlock-api.com/v1/players/910/match-history",
                match_payload,
            )
            normalize_match_history(settings, match_snapshot, 910, match_payload)

            connection = _connect(settings.warehouse_db_path)
            try:
                connection.execute(
                    """
                    INSERT INTO match_metadata (
                        match_id, duration_s, winning_team, match_outcome, snapshot_id, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (910, 2200, 1, 0, match_snapshot.id, "{}"),
                )
                connection.execute(
                    """
                    INSERT INTO item_purchase (
                        match_id, player_slot, purchase_index, account_id, item_id, upgrade_id,
                        bought_at_s, sold_at_s, imbued_ability_id, flags, upgrade_info, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (910, 0, 0, 910, 111, None, 300.0, None, None, None, None, "{}"),
                )
                connection.execute(
                    """
                    INSERT INTO item_purchase (
                        match_id, player_slot, purchase_index, account_id, item_id, upgrade_id,
                        bought_at_s, sold_at_s, imbued_ability_id, flags, upgrade_info, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (910, 0, 1, 910, 222, None, 620.0, None, None, None, None, "{}"),
                )
                connection.commit()
            finally:
                connection.close()

            previous = os.environ.get("DEADLOCK_COACH_HOME")
            os.environ["DEADLOCK_COACH_HOME"] = str(root)
            try:
                with patch(
                    "app.tools.hero_label",
                    side_effect=lambda _settings, hero_id: {1: "Billy"}.get(hero_id, str(hero_id)),
                ), patch(
                    "app.tools.item_asset",
                    side_effect=fake_item_asset_factory({111: "Rising Ram", 222: "Bashdown"}),
                ), patch(
                    "app.tools.item_label",
                    side_effect=lambda _settings, item_id: {111: "Rising Ram", 222: "Bashdown"}.get(item_id, str(item_id)),
                ):
                    matches = get_recent_matches(account_id=910, window_matches=3)
                    paths = get_recent_item_paths(account_id=910, hero_name="Billy", window_matches=3, items_per_match=3)
            finally:
                if previous is None:
                    os.environ.pop("DEADLOCK_COACH_HOME", None)
                else:
                    os.environ["DEADLOCK_COACH_HOME"] = previous

            self.assertEqual(matches["matches"][0]["hero_label"], "Billy")
            self.assertEqual(paths["matches"][0]["items"][0]["item_label"], "Rising Ram")

    def test_build_analysis_can_slice_to_a_specific_hero(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(project_root=root)
            initialize_workspace(settings)

            match_payload = [
                {
                    "match_id": 920,
                    "hero_id": 1,
                    "hero_level": 24,
                    "start_time": 1783288584,
                    "game_mode": 1,
                    "match_mode": 4,
                    "player_team": 0,
                    "player_kills": 9,
                    "player_deaths": 8,
                    "player_assists": 11,
                    "denies": 7,
                    "net_worth": 40500,
                    "last_hits": 220,
                    "team_abandoned": False,
                    "abandoned_time_s": None,
                    "match_duration_s": 2200,
                    "match_result": 0,
                    "won": False,
                },
                {
                    "match_id": 921,
                    "hero_id": 2,
                    "hero_level": 24,
                    "start_time": 1783202184,
                    "game_mode": 1,
                    "match_mode": 4,
                    "player_team": 0,
                    "player_kills": 7,
                    "player_deaths": 9,
                    "player_assists": 10,
                    "denies": 6,
                    "net_worth": 39500,
                    "last_hits": 205,
                    "team_abandoned": False,
                    "abandoned_time_s": None,
                    "match_duration_s": 2250,
                    "match_result": 0,
                    "won": False,
                },
            ]
            match_snapshot = save_json_snapshot(
                settings,
                "deadlock_api",
                "players",
                "920-match-history",
                "https://api.deadlock-api.com/v1/players/920/match-history",
                match_payload,
            )
            normalize_match_history(settings, match_snapshot, 920, match_payload)

            connection = _connect(settings.warehouse_db_path)
            try:
                connection.execute(
                    """
                    INSERT INTO match_metadata (
                        match_id, duration_s, winning_team, match_outcome, snapshot_id, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (920, 2200, 1, 0, match_snapshot.id, "{}"),
                )
                connection.execute(
                    """
                    INSERT INTO match_metadata (
                        match_id, duration_s, winning_team, match_outcome, snapshot_id, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (921, 2250, 1, 0, match_snapshot.id, "{}"),
                )
                connection.executemany(
                    """
                    INSERT INTO item_purchase (
                        match_id, player_slot, purchase_index, account_id, item_id, upgrade_id,
                        bought_at_s, sold_at_s, imbued_ability_id, flags, upgrade_info, raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (920, 0, 0, 920, 111, None, 300.0, None, None, None, None, "{}"),
                        (920, 0, 1, 920, 222, None, 620.0, None, None, None, None, "{}"),
                        (921, 0, 0, 920, 333, None, 410.0, None, None, None, None, "{}"),
                        (921, 0, 1, 920, 444, None, 700.0, None, None, None, None, "{}"),
                    ],
                )
                connection.commit()
            finally:
                connection.close()

            previous = os.environ.get("DEADLOCK_COACH_HOME")
            os.environ["DEADLOCK_COACH_HOME"] = str(root)
            try:
                with patch(
                    "app.tools.hero_label",
                    side_effect=lambda _settings, hero_id: {1: "Billy", 2: "Shiv"}.get(hero_id, str(hero_id)),
                ), patch(
                    "app.tools.item_asset",
                    side_effect=fake_item_asset_factory({111: "Rising Ram", 222: "Bashdown", 333: "Static Charge", 444: "Decay"}),
                ), patch(
                    "app.tools.item_label",
                    side_effect=lambda _settings, item_id: {111: "Rising Ram", 222: "Bashdown", 333: "Static Charge", 444: "Decay"}.get(item_id, str(item_id)),
                ):
                    result = get_build_analysis(account_id=920, hero_name="Billy", window_matches=10)
            finally:
                if previous is None:
                    os.environ.pop("DEADLOCK_COACH_HOME", None)
                else:
                    os.environ["DEADLOCK_COACH_HOME"] = previous

            self.assertEqual(result["hero_filter"], "Billy")
            self.assertEqual(result["matched_matches"], 1)
            self.assertEqual(result["build_spine"][:2], ["Rising Ram", "Bashdown"])
            self.assertEqual(result["item_timings"][0]["item_label"], "Rising Ram")


if __name__ == "__main__":
    unittest.main()
