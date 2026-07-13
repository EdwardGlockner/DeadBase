from __future__ import annotations

import unittest

from pydantic import ValidationError

from deadlock_coach.api_models import ChatRequest, ChatResponse, RuntimeSettingsBootstrapResponse


class ApiModelsTests(unittest.TestCase):
    def test_chat_request_requires_non_empty_message(self) -> None:
        with self.assertRaises(ValidationError):
            ChatRequest.model_validate({"message": ""})

    def test_chat_request_accepts_runtime_settings(self) -> None:
        payload = ChatRequest.model_validate(
            {
                "message": "Hello",
                "runtime_settings": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "api_key": "sk-test",
                },
            }
        )

        self.assertEqual(payload.runtime_settings.provider, "openai")
        self.assertEqual(payload.runtime_settings.model, "gpt-4o-mini")
        self.assertEqual(payload.runtime_settings.api_key, "sk-test")

    def test_chat_response_preserves_unavailable_fields(self) -> None:
        response = ChatResponse(
            reply="Coach unavailable",
            source="adk_unavailable",
            unavailable_reason="vpn dropped",
            coach_answer={"answer_type": "general", "headline": "Coach unavailable"},
            evidence=["one"],
            request_id="req-123",
        )

        payload = response.model_dump(mode="json", exclude_none=True)

        self.assertEqual(payload["source"], "adk_unavailable")
        self.assertEqual(payload["unavailable_reason"], "vpn dropped")
        self.assertEqual(payload["coach_answer"]["answer_type"], "general")
        self.assertEqual(payload["request_id"], "req-123")

    def test_runtime_settings_bootstrap_response_accepts_dev_key(self) -> None:
        response = RuntimeSettingsBootstrapResponse(
            provider="openai",
            model="gpt-4o-mini",
            api_key="sk-test",
        )

        payload = response.model_dump(mode="json", exclude_none=True)

        self.assertEqual(payload["provider"], "openai")
        self.assertEqual(payload["model"], "gpt-4o-mini")
        self.assertEqual(payload["api_key"], "sk-test")


if __name__ == "__main__":
    unittest.main()
