from __future__ import annotations

import unittest
from unittest.mock import patch

from deadlock_coach.adk_chat import (
    _build_context_preamble,
    _build_user_prompt,
    _extract_reply_text,
    _fake_event,
    _format_runtime_error,
    _missing_reply_error_message,
)
from deadlock_coach.coach_service import CoachContext


class AdkChatTests(unittest.TestCase):
    def test_extract_reply_prefers_root_agent_output(self) -> None:
        events = [
            _fake_event("build_capability", "Intermediary capability note."),
            _fake_event("coach_agent", "Final coach answer."),
        ]

        reply = _extract_reply_text(events, "coach_agent")

        self.assertEqual(reply, "Final coach answer.")

    def test_build_user_prompt_includes_context_lines(self) -> None:
        context = CoachContext(
            account_id=303017110,
            player_label="EEE",
            hero_name="Lash",
            window_matches=10,
        )

        prompt = _build_user_prompt("What should I practice?", context)

        self.assertIn("Active player label: EEE", prompt)
        self.assertIn("Active account id: 303017110", prompt)
        self.assertIn("Hero focus: Lash", prompt)
        self.assertIn("Window: last 10 matches", prompt)
        self.assertTrue(prompt.endswith("What should I practice?"))

    def test_build_user_prompt_prefers_explicit_message_hero_over_stale_context_hero(self) -> None:
        context = CoachContext(
            account_id=303017110,
            player_label="EEE",
            hero_name="Shiv",
            window_matches=10,
        )

        with patch("deadlock_coach.adk_chat.detect_hero_name_in_text", return_value="Billy"):
            prompt = _build_user_prompt("What does pros build on Billy?", context)

        self.assertIn("Hero focus: Billy", prompt)
        self.assertNotIn("Hero focus: Shiv", prompt)

    def test_build_context_preamble_marks_missing_player_context(self) -> None:
        preamble = _build_context_preamble(CoachContext())

        self.assertIn("No active player or account is selected", preamble)

    def test_format_runtime_error_for_missing_api_key(self) -> None:
        message = _format_runtime_error(ValueError("No API key was provided."))

        self.assertIn("LITELLM_PROXY_URL", message)
        self.assertIn("GOOGLE_API_KEY", message)

    def test_missing_reply_message_mentions_proxy_when_proxy_is_configured(self) -> None:
        with patch("deadlock_coach.adk_chat.resolve_proxy_url", return_value="https://proxy.example.com/v1"):
            self.assertIn("LiteLLM proxy", _missing_reply_error_message())


if __name__ == "__main__":
    unittest.main()
