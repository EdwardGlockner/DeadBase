from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.model_factory import active_model_provider
from app.model_factory import configured_model_override
from app.model_factory import resolve_openai_model_name
from app.model_factory import resolve_vertex_project


class ModelFactoryTests(unittest.TestCase):
    def setUp(self) -> None:
        import app.model_factory as model_factory

        model_factory._GCLOUD_PROJECT_CACHE = None

    def test_prefers_openai_when_openai_key_exists(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "GOOGLE_API_KEY": "google-key",
            },
            clear=True,
        ):
            self.assertEqual(active_model_provider(), "openai")

    def test_prefers_vertex_when_available_even_if_proxy_url_exists(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "LITELLM_PROXY_URL": "https://proxy.example.com/v1",
                "GOOGLE_GENAI_USE_VERTEXAI": "true",
                "GOOGLE_CLOUD_PROJECT": "demo-project",
            },
            clear=True,
        ):
            self.assertEqual(active_model_provider(), "vertexai")

    def test_uses_proxy_when_vertex_is_not_available(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "LITELLM_PROXY_URL": "https://proxy.example.com/v1",
            },
            clear=True,
        ):
            self.assertEqual(active_model_provider(), "litellm_proxy")

    def test_detects_gemini_api_keys(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": "gem-key"}, clear=True):
            self.assertEqual(active_model_provider(), "gemini_api")

    def test_detects_vertex_runtime(self) -> None:
        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "demo-project"}, clear=True):
            self.assertEqual(active_model_provider(), "vertexai")

    def test_resolve_vertex_project_falls_back_to_gcloud_config(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GOOGLE_CLOUD_PROJECT": "your-gcp-project-id",
                "GOOGLE_GENAI_USE_VERTEXAI": "true",
            },
            clear=True,
        ):
            with patch("app.model_factory.subprocess.run") as mock_run:
                mock_run.return_value.stdout = "real-project-123\n"
                mock_run.return_value.returncode = 0
                self.assertEqual(resolve_vertex_project(), "real-project-123")
                self.assertEqual(active_model_provider(), "vertexai")

    def test_prefers_explicit_provider_override(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DEADLOCK_COACH_PROVIDER_OVERRIDE": "gemini_api",
                "OPENAI_API_KEY": "test-key",
                "LITELLM_PROXY_URL": "https://proxy.example.com/v1",
            },
            clear=True,
        ):
            self.assertEqual(active_model_provider(), "gemini_api")

    def test_returns_none_without_provider_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(active_model_provider())

    def test_reads_model_override_when_present(self) -> None:
        with patch.dict(os.environ, {"DEADLOCK_COACH_MODEL_OVERRIDE": "gpt-4o"}, clear=True):
            self.assertEqual(configured_model_override(), "gpt-4o")

    def test_prefixes_openai_model_name_for_proxy(self) -> None:
        with patch.dict(os.environ, {"OPENAI_MODEL": "gpt-4o-mini"}, clear=True):
            self.assertEqual(resolve_openai_model_name(via_proxy=True), "openai/gpt-4o-mini")

    def test_strips_openai_prefix_for_direct_model(self) -> None:
        with patch.dict(os.environ, {"OPENAI_MODEL": "openai/gpt-4o-mini"}, clear=True):
            self.assertEqual(resolve_openai_model_name(via_proxy=False), "gpt-4o-mini")

    def test_uses_model_override_for_direct_openai(self) -> None:
        with patch.dict(os.environ, {"DEADLOCK_COACH_MODEL_OVERRIDE": "openai/gpt-4o"}, clear=True):
            self.assertEqual(resolve_openai_model_name(via_proxy=False), "gpt-4o")


if __name__ == "__main__":
    unittest.main()
