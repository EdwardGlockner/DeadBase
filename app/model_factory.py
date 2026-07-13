from __future__ import annotations

import os
import subprocess
from typing import Any

from dotenv import load_dotenv
from app.litellm_bootstrap import bootstrap_litellm_proxy
from app.litellm_bootstrap import resolve_proxy_url


load_dotenv()

_PLACEHOLDER_PROJECTS = {"", "your-gcp-project-id"}
_GCLOUD_PROJECT_CACHE: str | None = None


def configured_model_override() -> str | None:
    model = os.environ.get("DEADLOCK_COACH_MODEL_OVERRIDE", "").strip()
    return model or None


def _gcloud_default_project() -> str:
    global _GCLOUD_PROJECT_CACHE

    if _GCLOUD_PROJECT_CACHE is not None:
        return _GCLOUD_PROJECT_CACHE

    try:
        result = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True,
            text=True,
            check=True,
        )
        project = result.stdout.strip()
    except Exception:
        project = ""

    _GCLOUD_PROJECT_CACHE = "" if project in {"", "(unset)"} else project
    return _GCLOUD_PROJECT_CACHE


def resolve_vertex_project() -> str | None:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    if project not in _PLACEHOLDER_PROJECTS:
        return project or None
    fallback = _gcloud_default_project()
    return fallback or None


def _vertex_enabled() -> bool:
    return bool(os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") or os.environ.get("GOOGLE_CLOUD_PROJECT"))


def _prepare_vertex_runtime() -> str | None:
    project = resolve_vertex_project()
    if project:
        os.environ["GOOGLE_CLOUD_PROJECT"] = project
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
    return project


def active_model_provider() -> str | None:
    if provider_override := os.environ.get("DEADLOCK_COACH_PROVIDER_OVERRIDE", "").strip():
        return provider_override
    if _vertex_enabled() and resolve_vertex_project():
        return "vertexai"
    if not resolve_proxy_url() and os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini_api"
    if resolve_proxy_url():
        return "litellm_proxy"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return None


def resolve_openai_model_name(*, via_proxy: bool) -> str:
    model = configured_model_override() or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    if via_proxy and "/" not in model:
        return f"openai/{model}"
    if not via_proxy and model.startswith("openai/"):
        return model.split("/", 1)[1]
    return model


def build_model() -> Any:
    provider = active_model_provider()
    if provider == "litellm_proxy":
        bootstrap_litellm_proxy()
        from google.adk.models import LiteLlm

        return LiteLlm(model=resolve_openai_model_name(via_proxy=True))

    if provider == "openai":
        from google.adk.labs.openai import OpenAILlm

        return OpenAILlm(model=resolve_openai_model_name(via_proxy=False))

    if provider in {"gemini_api", "vertexai"}:
        if provider == "vertexai":
            _prepare_vertex_runtime()
        from google.adk.models import Gemini
        from google.genai import types

        return Gemini(
            model=configured_model_override() or os.environ.get("GEMINI_MODEL", "gemini-flash-latest"),
            retry_options=types.HttpRetryOptions(attempts=3),
        )

    raise RuntimeError(
        "No supported LLM credentials are configured. "
        "Set `LITELLM_PROXY_URL` plus `LITELLM_PROXY_API_KEY` or `OPENAI_API_KEY` for a proxy-backed OpenAI model, "
        "`OPENAI_API_KEY` for direct OpenAI, or `GOOGLE_API_KEY` / `GEMINI_API_KEY` "
        "or Vertex AI environment variables for Gemini."
    )
