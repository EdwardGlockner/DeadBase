from __future__ import annotations

import unittest

from deadlock_coach.semantic_router import build_routing_decision, infer_information_need


class SemanticRouterTests(unittest.TestCase):
    def test_infer_build_question_as_mixed_build_need(self) -> None:
        need = infer_information_need("what items do i usually build on billy?")

        self.assertEqual(need.family, "timing")
        self.assertEqual(need.subject, "build")
        self.assertEqual(need.scope, "player_specific")
        self.assertTrue(need.needs_knowledge_base)
        self.assertFalse(need.needs_global_analytics)

    def test_infer_concept_question_prefers_knowledge_base(self) -> None:
        need = infer_information_need("do you know what boons are?")

        self.assertEqual(need.family, "general")
        self.assertEqual(need.subject, "concept")
        self.assertEqual(need.scope, "knowledge")
        self.assertTrue(need.needs_knowledge_base)

    def test_full_history_hero_question_marks_full_history_preference(self) -> None:
        need = infer_information_need("can you look at all games i have ever played, what heroes do i usually play?")

        self.assertEqual(need.family, "hero_overview")
        self.assertTrue(need.prefers_full_history)

    def test_build_routing_with_account_adds_data_and_knowledge_lanes(self) -> None:
        routing = build_routing_decision("what spike do i get first, 4.8k?", has_account=True)

        self.assertEqual(routing.family, "timing")
        self.assertIn("build_analysis", routing.tool_hints)
        self.assertIn("knowledge_base_lookup", routing.tool_hints)
        self.assertIn("data", routing.analyst_lanes)
        self.assertIn("knowledge", routing.analyst_lanes)

    def test_build_routing_without_account_stays_grounded(self) -> None:
        routing = build_routing_decision("what should i build on lash?", has_account=False)

        self.assertEqual(routing.family, "timing")
        self.assertNotIn("build_analysis", routing.tool_hints)
        self.assertIn("knowledge_base_lookup", routing.tool_hints)
        self.assertIn("knowledge", routing.analyst_lanes)

    def test_global_winrate_followup_uses_previous_question_context(self) -> None:
        routing = build_routing_decision(
            "no i mean for everyone",
            has_account=True,
            history=[
                {"role": "user", "text": "what hero has the highest win rate right now?"},
                {"role": "assistant", "text": "Shiv has the highest win rate in your sample."},
            ],
        )

        self.assertEqual(routing.family, "winrate")
        self.assertIn("global_hero_stats", routing.tool_hints)
        self.assertNotIn("hero_pool_analysis", routing.tool_hints)

    def test_popular_hero_build_question_prefers_global_item_flow(self) -> None:
        routing = build_routing_decision("what is the most popular build on shiv?", has_account=True)

        self.assertEqual(routing.family, "timing")
        self.assertIn("global_item_flow", routing.tool_hints)
        self.assertNotIn("build_analysis", routing.tool_hints)

    def test_pickrate_and_winrate_question_routes_to_global_meta(self) -> None:
        routing = build_routing_decision("what hero has the highest pickrate and winrate right now?", has_account=True)

        self.assertEqual(routing.family, "global_popularity")
        self.assertIn("global_hero_stats", routing.tool_hints)
        self.assertNotIn("hero_pool_analysis", routing.tool_hints)
        self.assertIn("comparison_analyst", routing.specialists)

    def test_compare_question_routes_to_comparison_specialist(self) -> None:
        routing = build_routing_decision("compare my Billy to Eternus players", has_account=True)

        self.assertEqual(routing.family, "mirror")
        self.assertIn("comparison_analyst", routing.specialists)

    def test_pro_build_question_prefers_global_build_flow_over_comparison(self) -> None:
        routing = build_routing_decision("what does pros build on billy?", has_account=True)

        self.assertEqual(routing.family, "timing")
        self.assertIn("global_item_flow", routing.tool_hints)
        self.assertIn("global_item_stats", routing.tool_hints)
        self.assertNotIn("comparison_analyst", routing.specialists)
        self.assertNotIn("build_analysis", routing.tool_hints)

    def test_latest_patch_question_routes_to_patch_context(self) -> None:
        routing = build_routing_decision("can you explain the latest patch for me?", has_account=True)

        self.assertEqual(routing.family, "patches")
        self.assertIn("patch_context", routing.tool_hints)


if __name__ == "__main__":
    unittest.main()
