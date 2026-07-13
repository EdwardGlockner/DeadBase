from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deadlock_coach.agent_orchestration import build_response_envelope, build_evidence_bullets, build_prompt_support, enrich_reply_payload
from deadlock_coach.coach_service import AccountSummary, HeroPerformance, parse_context
from deadlock_coach.config import Settings
from deadlock_coach.storage import initialize_workspace, normalize_match_history, normalize_patch_feed, save_json_snapshot


class AgentOrchestrationTests(unittest.TestCase):
    def test_envelope_without_account_is_low_confidence_and_coach_led(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)

            envelope = build_response_envelope(settings, "What should I practice next?", parse_context({}))

        self.assertEqual(envelope.confidence.level, "low")
        self.assertEqual(envelope.structured_output.routing.family, "focus")
        self.assertEqual(envelope.trace.selected_specialists, ["coach_agent"])
        self.assertIsNotNone(envelope.structured_output.practice_plan)

    def test_envelope_without_account_routes_named_build_question_to_knowledge_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)

            envelope = build_response_envelope(settings, "What should I build on Lash?", parse_context({}))

        self.assertEqual(envelope.structured_output.routing.family, "timing")
        self.assertEqual(envelope.trace.selected_specialists, ["coach_agent"])
        self.assertIn("knowledge_base_lookup", envelope.structured_output.routing.tool_hints)

    def test_envelope_with_account_adds_kb_specialist_for_spike_question(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(project_root=root)
            initialize_workspace(settings)
            (root / "docs" / "knowledge" / "builds").mkdir(parents=True, exist_ok=True)
            (root / "docs" / "knowledge" / "builds" / "investment-families-and-spikes.md").write_text(
                "# Investment Families And Spikes\n\n- spike means a real in-game power jump\n",
                encoding="utf-8",
            )

            match_payload = [
                {
                    "match_id": 4101,
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
                "777-match-history",
                "https://api.deadlock-api.com/v1/players/777/match-history",
                match_payload,
            )
            normalize_match_history(settings, snapshot, 777, match_payload)

            envelope = build_response_envelope(
                settings,
                "what spike do i get first, 4.8k?",
                parse_context({"account_id": 777, "hero_name": "Billy", "window_matches": 10}),
            )

        self.assertEqual(envelope.structured_output.routing.family, "timing")
        self.assertEqual(envelope.trace.selected_specialists, ["coach_agent"])
        self.assertIn("knowledge_base_lookup", envelope.structured_output.routing.tool_hints)
        self.assertIn("build_analysis", envelope.structured_output.routing.tool_hints)
        self.assertTrue(any(item.source_type == "knowledge_base" for item in envelope.evidence_graph))
        self.assertTrue(any(step.name == "knowledge_retrieval" for step in envelope.trace.steps))

    def test_envelope_with_local_sample_returns_hero_diagnosis_and_telemetry_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)

            match_payload = [
                {
                    "match_id": 3001,
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
                    "match_id": 3002,
                    "hero_id": 1,
                    "hero_level": 25,
                    "start_time": 1783202184,
                    "game_mode": 1,
                    "match_mode": 4,
                    "player_team": 0,
                    "player_kills": 12,
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
                    "match_id": 3003,
                    "hero_id": 2,
                    "hero_level": 23,
                    "start_time": 1783115784,
                    "game_mode": 1,
                    "match_mode": 4,
                    "player_team": 0,
                    "player_kills": 7,
                    "player_deaths": 9,
                    "player_assists": 8,
                    "denies": 5,
                    "net_worth": 38100,
                    "last_hits": 205,
                    "team_abandoned": False,
                    "abandoned_time_s": None,
                    "match_duration_s": 2180,
                    "match_result": 0,
                    "won": False,
                },
                {
                    "match_id": 3004,
                    "hero_id": 1,
                    "hero_level": 24,
                    "start_time": 1783029384,
                    "game_mode": 1,
                    "match_mode": 4,
                    "player_team": 0,
                    "player_kills": 10,
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
            ]
            snapshot = save_json_snapshot(
                settings,
                "deadlock_api",
                "players",
                "777-match-history",
                "https://api.deadlock-api.com/v1/players/777/match-history",
                match_payload,
            )
            normalize_match_history(settings, snapshot, 777, match_payload)

            envelope = build_response_envelope(
                settings,
                "What heroes do I usually play?",
                parse_context({"account_id": 777, "player_label": "EEE", "window_matches": 10}),
            )

        self.assertEqual(envelope.structured_output.routing.family, "hero_overview")
        self.assertIsNotNone(envelope.structured_output.hero_pool)
        self.assertTrue(any(item.source_type == "player_telemetry" for item in envelope.evidence_graph))
        self.assertTrue(build_evidence_bullets(envelope))
        self.assertNotIn("Selected specialists:", build_prompt_support(envelope))

    def test_enrich_reply_payload_adds_contract_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            envelope = build_response_envelope(settings, "hello", parse_context({}))

        payload = enrich_reply_payload({"reply": "Hello", "source": "google_adk"}, envelope)
        self.assertIn("coach_answer", payload)
        self.assertIn("confidence", payload)
        self.assertIn("evidence_graph", payload)
        self.assertIn("structured_output", payload)
        self.assertIn("trace", payload)
        self.assertEqual(payload["coach_answer"]["headline"], "Hello")

    def test_reference_grounded_answer_without_player_sample_is_not_limited_sample(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            settings = Settings(project_root=root)
            initialize_workspace(settings)
            (root / "docs" / "knowledge" / "builds").mkdir(parents=True, exist_ok=True)
            (root / "docs" / "knowledge" / "builds" / "investment-spikes.md").write_text(
                "# Investment Spikes\n\nA 4.8k investment spike is a category-bar breakpoint, not just one item.\n",
                encoding="utf-8",
            )

            envelope = build_response_envelope(settings, "what does 4.8k investment mean?", parse_context({}))
            payload = enrich_reply_payload({"reply": "It means you hit the 4.8k category breakpoint.", "source": "google_adk"}, envelope)

        self.assertEqual(envelope.confidence.level, "medium")
        self.assertTrue(any(item.source_type == "knowledge_base" for item in envelope.evidence_graph))
        self.assertNotIn("caveat", payload["coach_answer"])

    def test_patch_question_uses_synced_patch_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            payload = [
                {
                    "title": "July 2026 Balance Update",
                    "source": "deadlock_api",
                    "pub_date": "2026-07-09T15:30:00Z",
                    "link": "https://example.com/patches/july-2026",
                    "guid": {"text": "patch-july-2026"},
                    "content": "Shiv: reduced spirit scaling. Billy: adjusted lane damage.",
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

            envelope = build_response_envelope(settings, "can you explain the latest patch and what happened to shiv?", parse_context({}))

        self.assertEqual(envelope.confidence.level, "medium")
        self.assertTrue(any(item.source_type == "patch_feed" for item in envelope.evidence_graph))
        self.assertTrue(any("Shiv" in item.detail for item in envelope.evidence_graph))

    def test_enrich_reply_payload_preserves_rich_build_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            envelope = build_response_envelope(settings, "what do i usually build?", parse_context({}))

        payload = enrich_reply_payload(
            {
                "reply": "On Billy, your most common build right now looks like this.",
                "source": "warehouse",
                "_coach_answer": {
                    "answer_type": "build",
                    "headline": "On Billy, your most common build right now looks like this.",
                    "build": {
                        "hero_name": "Billy",
                        "lane_early": ["Monster Rounds", "Close Quarters"],
                        "mid_game": ["Surge of Power", "Warp Stone"],
                        "stable_core": ["Surge of Power", "Warp Stone"],
                        "late_items": ["Point Blank"],
                        "t4_finishers": ["Unstoppable"],
                        "flex_items": ["Healbane"],
                        "late_branches": [],
                    },
                },
            },
            envelope,
        )

        self.assertEqual(payload["coach_answer"]["answer_type"], "build")
        self.assertEqual(payload["coach_answer"]["build"]["hero_name"], "Billy")
        self.assertEqual(payload["coach_answer"]["build"]["stable_core"], ["Surge of Power", "Warp Stone"])

    def test_enrich_reply_payload_does_not_add_generic_next_step_to_narrow_build_answers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            envelope = build_response_envelope(settings, "what items do i usually build on billy?", parse_context({}))

        payload = enrich_reply_payload({"reply": "On Billy, lane/early usually looks like Monster Rounds and Close Quarters.", "source": "google_adk"}, envelope)

        self.assertNotIn("next_step", payload["coach_answer"])

    def test_build_envelope_prefers_explicit_message_hero_over_context_hero(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)
            fake_summary = AccountSummary(
                account_id=777,
                total_matches=10,
                resolved_outcome_matches=10,
                unknown_outcome_matches=0,
                wins=6,
                losses=4,
                win_rate=60.0,
                avg_kills=10.0,
                avg_deaths=7.0,
                avg_assists=11.0,
                avg_net_worth=40000.0,
                latest_start_time=None,
                hero_performance=[
                    HeroPerformance(hero_id=1, games=5, resolved_games=5, wins=3, win_rate=60.0),
                    HeroPerformance(hero_id=2, games=5, resolved_games=5, wins=3, win_rate=60.0),
                ],
                item_timings=[],
                hydrated_match_count=0,
            )

            with patch("deadlock_coach.agent_orchestration.summarize_account", return_value=fake_summary), patch(
                "deadlock_coach.agent_orchestration.detect_hero_name_in_text",
                return_value="Billy",
            ), patch(
                "deadlock_coach.agent_orchestration.hero_label",
                side_effect=lambda _settings, hero_id: {1: "Billy", 2: "Shiv"}.get(hero_id, str(hero_id)),
            ), patch(
                "deadlock_coach.agent_orchestration._recent_item_paths_payload",
                return_value=[],
            ) as recent_paths_payload:
                build_response_envelope(
                    settings,
                    "what items do i usually build on billy?",
                    parse_context({"account_id": 777, "player_label": "EEE", "hero_name": "Shiv"}),
                )

        self.assertEqual(recent_paths_payload.call_args.kwargs["hero_name"], "Billy")

    def test_envelope_uses_history_for_global_followup_clarifier(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)

            envelope = build_response_envelope(
                settings,
                "no i mean for everyone",
                parse_context({"account_id": 777, "player_label": "EEE"}),
                history=[
                    {"role": "user", "text": "what hero has the highest win rate right now?"},
                    {"role": "assistant", "text": "Shiv has the highest win rate in your recent sample."},
                ],
            )

        self.assertEqual(envelope.structured_output.routing.family, "winrate")
        self.assertIn("global_hero_stats", envelope.structured_output.routing.tool_hints)
        self.assertNotIn("hero_pool_analysis", envelope.structured_output.routing.tool_hints)

    def test_factual_build_envelope_does_not_generate_generic_practice_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)

            envelope = build_response_envelope(
                settings,
                "what items do i usually build on billy?",
                parse_context({"account_id": 777, "player_label": "EEE"}),
            )

        self.assertIsNone(envelope.structured_output.practice_plan)
        self.assertIsNone(envelope.structured_output.artifact_outline)

    def test_global_popularity_envelope_stays_factual(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)

            envelope = build_response_envelope(
                settings,
                "what hero has the highest pickrate and winrate right now?",
                parse_context({"account_id": 777, "player_label": "EEE"}),
            )

        self.assertEqual(envelope.structured_output.routing.family, "global_popularity")
        self.assertIn("comparison_analyst", envelope.trace.selected_specialists)
        self.assertIsNotNone(envelope.structured_output.comparison)
        self.assertIsNone(envelope.structured_output.practice_plan)
        self.assertIsNone(envelope.structured_output.artifact_outline)

    def test_mirror_question_builds_comparison_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)

            envelope = build_response_envelope(
                settings,
                "compare my Billy to Eternus players",
                parse_context({"account_id": 777, "player_label": "EEE"}),
            )

        self.assertEqual(envelope.structured_output.routing.family, "mirror")
        self.assertIn("comparison_analyst", envelope.trace.selected_specialists)
        self.assertIsNotNone(envelope.structured_output.comparison)
        self.assertIn("Suggested specialists: comparison_analyst", build_prompt_support(envelope))


if __name__ == "__main__":
    unittest.main()
