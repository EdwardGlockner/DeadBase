from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock_coach.message_hints import (
    effective_knowledge_query,
    looks_like_concept_clarifier,
    looks_like_full_history_request,
    normalized_message,
)


class MessageHintsTests(unittest.TestCase):
    def test_normalized_message_collapses_whitespace(self) -> None:
        self.assertEqual(normalized_message("  What   Do You Mean? "), "what do you mean?")

    def test_concept_clarifier_matches_short_follow_up_questions(self) -> None:
        self.assertTrue(looks_like_concept_clarifier("what do you mean?"))
        self.assertTrue(looks_like_concept_clarifier("why"))
        self.assertFalse(looks_like_concept_clarifier("what are boons?"))

    def test_full_history_request_detects_all_time_scope(self) -> None:
        self.assertTrue(looks_like_full_history_request("can you look at all games i have ever played"))
        self.assertTrue(looks_like_full_history_request("show the full history"))
        self.assertFalse(looks_like_full_history_request("what heroes do i usually play?"))

    def test_effective_knowledge_query_uses_previous_user_turn_for_clarifier(self) -> None:
        query = effective_knowledge_query(
            "what do you mean?",
            history=[
                {"role": "user", "text": "what spike do i get first, 4.8k?"},
                {"role": "assistant", "text": "some reply"},
            ],
        )

        self.assertEqual(query, "what spike do i get first, 4.8k?\nwhat do you mean?")

    def test_effective_knowledge_query_leaves_regular_questions_alone(self) -> None:
        self.assertEqual(
            effective_knowledge_query(
                "what are boons?",
                history=[{"role": "user", "text": "hello"}],
            ),
            "what are boons?",
        )


if __name__ == "__main__":
    unittest.main()
