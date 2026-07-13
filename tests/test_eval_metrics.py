from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from unittest import TestCase
from unittest.mock import patch
import os


_METRICS_PATH = Path(__file__).resolve().parent / "eval" / "metrics.py"
_SPEC = importlib.util.spec_from_file_location("deadlock_coach_eval_metrics", _METRICS_PATH)
assert _SPEC is not None and _SPEC.loader is not None
eval_metrics = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = eval_metrics
_SPEC.loader.exec_module(eval_metrics)


class EvalMetricsTests(TestCase):
    def setUp(self) -> None:
        eval_metrics._VERDICT_CACHE.clear()
        eval_metrics._WORKING_JUDGE_CONFIG = None
        eval_metrics._GCLOUD_PROJECT_CACHE = None

    def test_metric_falls_back_to_heuristics_when_judge_unavailable(self) -> None:
        instance = {
            "prompt": "what do people mean by 4.8k spirit?",
            "response": "It means 4.8k souls invested into the spirit bar, not just one item.",
            "rubrics": [
                {
                    "rubricContent": {
                        "textProperty": "Explains that 4.8k spirit means category-bar investment into spirit."
                    }
                }
            ],
            "agent_data": "knowledge_retrieval: table fact found",
        }

        with patch.object(eval_metrics, "_generate_judge_json", side_effect=RuntimeError("judge unavailable")):
            result = eval_metrics.custom_response_quality(instance)

        self.assertIsInstance(result["score"], int)
        self.assertGreaterEqual(result["score"], 1)
        self.assertIn("Heuristic fallback was used", result["explanation"])

    def test_metric_cache_reuses_single_verdict_across_metric_functions(self) -> None:
        instance = {
            "prompt": "what are boons?",
            "response": "Boons are soul-based level rewards that increase base stats as you level up.",
            "reference": "Boons are soul-based level rewards, not items.",
            "agent_data": "knowledge_retrieval: entity matches found",
        }

        call_count = 0

        def _fake_judge(_prompt: str) -> str:
            nonlocal call_count
            call_count += 1
            return """
            {
              "response_quality": {"score": 5, "explanation": "good"},
              "directness": {"score": 4, "explanation": "direct"},
              "factual_grounding": {"score": 5, "explanation": "grounded"},
              "uncertainty_behavior": {"score": 4, "explanation": "measured"},
              "formatting_quality": {"score": 4, "explanation": "clean"},
              "non_redundancy": {"score": 5, "explanation": "tight"}
            }
            """.strip()

        with patch.object(eval_metrics, "_generate_judge_json", side_effect=_fake_judge):
            quality = eval_metrics.custom_response_quality(instance)
            directness = eval_metrics.custom_directness(instance)
            grounding = eval_metrics.custom_factual_grounding(instance)

        self.assertEqual(call_count, 1)
        self.assertEqual(quality["score"], 5)
        self.assertEqual(directness["score"], 4)
        self.assertEqual(grounding["score"], 5)

    def test_eval_judge_prefers_explicit_eval_openai_over_general_proxy(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GOOGLE_CLOUD_PROJECT": "your-gcp-project-id",
                "GOOGLE_GENAI_USE_VERTEXAI": "true",
                "LITELLM_PROXY_URL": "https://proxy.example.com/v1",
                "LITELLM_PROXY_API_KEY": "proxy-key",
                "OPENAI_API_KEY": "general-openai-key",
                "EVAL_OPENAI_API_KEY": "eval-openai-key",
                "EVAL_OPENAI_MODEL": "gpt-4o-mini",
            },
            clear=True,
        ):
            config = eval_metrics._resolve_judge_config()

        self.assertEqual(config.provider, "openai")
        self.assertEqual(config.api_key, "eval-openai-key")
        self.assertEqual(config.model, "gpt-4o-mini")

    def test_eval_judge_prefers_general_openai_before_general_proxy_for_eval_runs(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GOOGLE_CLOUD_PROJECT": "your-gcp-project-id",
                "GOOGLE_GENAI_USE_VERTEXAI": "true",
                "LITELLM_PROXY_URL": "https://proxy.example.com/v1",
                "LITELLM_PROXY_API_KEY": "proxy-key",
                "OPENAI_API_KEY": "general-openai-key",
                "OPENAI_MODEL": "gpt-5.4",
            },
            clear=True,
        ):
            configs = eval_metrics._resolve_judge_configs()

        self.assertEqual(configs[0].provider, "openai")
        self.assertEqual(configs[0].api_key, "general-openai-key")
        self.assertEqual(configs[0].model, "gpt-5.4")
        self.assertEqual(configs[1].provider, "litellm_proxy")
        self.assertEqual(configs[1].api_base, "https://proxy.example.com/v1")
        self.assertEqual(configs[1].model, "openai/gpt-5.4")

    def test_eval_judge_uses_gcloud_default_project_when_env_has_placeholder(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GOOGLE_CLOUD_PROJECT": "your-gcp-project-id",
                "GOOGLE_GENAI_USE_VERTEXAI": "true",
            },
            clear=True,
        ):
            with patch.object(eval_metrics.subprocess, "run") as mock_run:
                mock_run.return_value.stdout = "real-project-123\n"
                mock_run.return_value.returncode = 0
                config = eval_metrics._resolve_judge_config()

        self.assertEqual(config.provider, "vertexai")
        self.assertEqual(config.project, "real-project-123")

    def test_eval_judge_explicit_provider_can_force_proxy(self) -> None:
        with patch.dict(
            os.environ,
            {
                "EVAL_JUDGE_PROVIDER": "litellm_proxy",
                "EVAL_LITELLM_PROXY_URL": "https://litellm-proxy.example.com/v1",
                "EVAL_LITELLM_PROXY_API_KEY": "eval-proxy-key",
                "EVAL_OPENAI_MODEL": "gpt-4o-mini",
            },
            clear=True,
        ):
            config = eval_metrics._resolve_judge_config()

        self.assertEqual(config.provider, "litellm_proxy")
        self.assertEqual(config.api_base, "https://litellm-proxy.example.com/v1")
        self.assertEqual(config.api_key, "eval-proxy-key")

    def test_generate_judge_json_falls_through_to_next_live_provider(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LITELLM_PROXY_URL": "https://proxy.example.com/v1",
                "LITELLM_PROXY_API_KEY": "proxy-key",
                "OPENAI_API_KEY": "general-openai-key",
                "OPENAI_MODEL": "gpt-5.4",
            },
            clear=True,
        ):
            attempted: list[str] = []

            def _fake_generate(config, _prompt: str) -> str:
                attempted.append(config.provider)
                if config.provider == "openai":
                    raise RuntimeError("direct openai failed")
                return '{"response_quality":{"score":5,"explanation":"good"},"directness":{"score":5,"explanation":"good"},"factual_grounding":{"score":5,"explanation":"good"},"uncertainty_behavior":{"score":5,"explanation":"good"},"formatting_quality":{"score":5,"explanation":"good"},"non_redundancy":{"score":5,"explanation":"good"}}'

            with patch.object(eval_metrics, "_generate_judge_json_for_config", side_effect=_fake_generate):
                payload = eval_metrics._generate_judge_json("test prompt")

        self.assertEqual(attempted, ["openai", "litellm_proxy"])
        self.assertIn('"score":5', payload)
        self.assertIsNotNone(eval_metrics._WORKING_JUDGE_CONFIG)
        self.assertEqual(eval_metrics._WORKING_JUDGE_CONFIG.provider, "litellm_proxy")
