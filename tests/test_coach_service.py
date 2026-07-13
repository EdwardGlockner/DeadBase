from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock_coach.coach_service import (
    _build_walkthrough_from_paths,
    _walkthrough_reply_lines,
    account_summary_payload,
    normalize_reply_text,
    parse_context,
    summarize_account,
    utility_reply_for_message,
)
from deadlock_coach.config import Settings
from deadlock_coach.storage import initialize_workspace, normalize_match_history, normalize_match_metadata, save_json_snapshot


class CoachServiceTests(unittest.TestCase):
    def test_utility_reply_handles_day_question(self) -> None:
        reply = utility_reply_for_message("what day is it")

        self.assertIsNotNone(reply)
        self.assertEqual(reply["insight"], "Utility reply")
        self.assertEqual(reply["source"], "utility")
        self.assertIn("Today is", reply["reply"])

    def test_normalize_reply_text_breaks_inline_bullets_into_lines(self) -> None:
        text = (
            "Yes. From that 200-match view: - Most played heroes: Pocket 37, Shiv 27, Billy 26 "
            "- Common build spine showing up: Monster Rounds -> Close Quarters -> Stalker"
        )

        normalized = normalize_reply_text(text)

        self.assertIn("view:\n- Most played heroes", normalized)
        self.assertIn("\n- Common build spine showing up", normalized)

    def test_build_walkthrough_from_paths_preserves_split_late_branches(self) -> None:
        paths = [
            {
                "items": [
                    {"item_label": "Monster Rounds", "item_tier": 1},
                    {"item_label": "Close Quarters", "item_tier": 1},
                    {"item_label": "Stalker", "item_tier": 2},
                    {"item_label": "Slowing Bullets", "item_tier": 2},
                    {"item_label": "Surge of Power", "item_tier": 3},
                    {"item_label": "Warp Stone", "item_tier": 3},
                    {"item_label": "Point Blank", "item_tier": 3},
                    {"item_label": "Unstoppable", "item_tier": 4},
                ]
            },
            {
                "items": [
                    {"item_label": "Monster Rounds", "item_tier": 1},
                    {"item_label": "Close Quarters", "item_tier": 1},
                    {"item_label": "Healbane", "item_tier": 2},
                    {"item_label": "Stalker", "item_tier": 2},
                    {"item_label": "Surge of Power", "item_tier": 3},
                    {"item_label": "Warp Stone", "item_tier": 3},
                    {"item_label": "Point Blank", "item_tier": 3},
                    {"item_label": "Unstoppable", "item_tier": 4},
                ]
            },
            {
                "items": [
                    {"item_label": "Monster Rounds", "item_tier": 1},
                    {"item_label": "Close Quarters", "item_tier": 1},
                    {"item_label": "Stalker", "item_tier": 2},
                    {"item_label": "Slowing Bullets", "item_tier": 2},
                    {"item_label": "Warp Stone", "item_tier": 3},
                    {"item_label": "Surge of Power", "item_tier": 3},
                    {"item_label": "Spirit Snatch", "item_tier": 3},
                    {"item_label": "Boundless Spirit", "item_tier": 4},
                ]
            },
            {
                "items": [
                    {"item_label": "Monster Rounds", "item_tier": 1},
                    {"item_label": "Close Quarters", "item_tier": 1},
                    {"item_label": "Extra Spirit", "item_tier": 1},
                    {"item_label": "Slowing Bullets", "item_tier": 2},
                    {"item_label": "Warp Stone", "item_tier": 3},
                    {"item_label": "Surge of Power", "item_tier": 3},
                    {"item_label": "Spirit Snatch", "item_tier": 3},
                    {"item_label": "Boundless Spirit", "item_tier": 4},
                ]
            },
        ]

        walkthrough = _build_walkthrough_from_paths(paths)

        self.assertEqual(walkthrough["core_items"], ["Surge of Power", "Warp Stone"])
        self.assertEqual(len(walkthrough["late_alternatives"]), 2)
        self.assertIn("Late game usually splits two ways", walkthrough["summary"])
        self.assertIn("Point Blank", walkthrough["summary"])
        self.assertIn("Spirit Snatch", walkthrough["summary"])
        self.assertIn("Unstoppable", walkthrough["summary"])
        self.assertIn("Boundless Spirit", walkthrough["summary"])
        self.assertIn("T4 finishers", " ".join(_walkthrough_reply_lines(walkthrough)))

    def test_build_walkthrough_does_not_promote_tier_two_item_to_late_game(self) -> None:
        paths = [
            {
                "items": [
                    {"item_label": "Monster Rounds", "item_tier": 1},
                    {"item_label": "Close Quarters", "item_tier": 1},
                    {"item_label": "Surge of Power", "item_tier": 3},
                    {"item_label": "Warp Stone", "item_tier": 3},
                    {"item_label": "Healbane", "item_tier": 2},
                    {"item_label": "Unstoppable", "item_tier": 4},
                ]
            },
            {
                "items": [
                    {"item_label": "Monster Rounds", "item_tier": 1},
                    {"item_label": "Close Quarters", "item_tier": 1},
                    {"item_label": "Surge of Power", "item_tier": 3},
                    {"item_label": "Warp Stone", "item_tier": 3},
                    {"item_label": "Healbane", "item_tier": 2},
                    {"item_label": "Boundless Spirit", "item_tier": 4},
                ]
            },
        ]

        walkthrough = _build_walkthrough_from_paths(paths)

        self.assertNotIn("Healbane", walkthrough["late_items"])
        self.assertNotIn("Healbane", walkthrough["late_finishers"])
        self.assertIn("Unstoppable", walkthrough["late_finishers"])

    def test_account_summary_payload_uses_local_warehouse(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)

            match_payload = [
                {
                    "match_id": 102,
                    "hero_id": 21,
                    "hero_level": 22,
                    "start_time": 1783202184,
                    "game_mode": 1,
                    "match_mode": 4,
                    "player_team": 1,
                    "player_kills": 6,
                    "player_deaths": 7,
                    "player_assists": 10,
                    "denies": 8,
                    "net_worth": 42100,
                    "last_hits": 201,
                    "team_abandoned": False,
                    "abandoned_time_s": None,
                    "match_duration_s": 2315,
                    "match_result": 0,
                    "won": False,
                }
            ]
            match_snapshot = save_json_snapshot(
                settings,
                "deadlock_api",
                "players",
                "77-match-history",
                "https://api.deadlock-api.com/v1/players/77/match-history",
                match_payload,
            )
            normalize_match_history(settings, match_snapshot, 77, match_payload)

            metadata_payload = {
                "match_info": {"duration_s": 2315, "winning_team": 0, "match_outcome": 1},
                "players": [
                    {
                        "player_slot": 1,
                        "account_id": 77,
                        "hero_id": 21,
                        "player_team": 1,
                        "won": False,
                        "items": [{"item_id": 4001, "game_time_s": 420}],
                    }
                ],
            }
            metadata_snapshot = save_json_snapshot(
                settings,
                "deadlock_api",
                "matches",
                "102-metadata",
                "https://api.deadlock-api.com/v1/matches/102/metadata",
                metadata_payload,
            )
            normalize_match_metadata(settings, metadata_snapshot, 102, metadata_payload)

            summary = summarize_account(settings, 77, 20)
            self.assertIsNotNone(summary)

            with patch("deadlock_coach.coach_service.hero_label", return_value="Lash"):
                payload = account_summary_payload(settings, summary)

        self.assertEqual(payload["account_id"], 77)
        self.assertEqual(payload["total_matches"], 1)
        self.assertEqual(payload["hydrated_match_count"], 1)
        self.assertEqual(payload["focus"]["top_hero"]["hero_label"], "Lash")

    def test_parse_context_applies_defaults(self) -> None:
        context = parse_context({"window_matches": 0, "hero_name": "Billy"})

        self.assertEqual(context.hero_name, "Billy")
        self.assertEqual(context.window_matches, 20)


if __name__ == "__main__":
    unittest.main()
