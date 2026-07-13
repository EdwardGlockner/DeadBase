"""Custom eval metrics for the Deadlock Coach agent.

These metrics keep the quality bar focused on the things that matter for this
project:
- direct answers instead of generic assistant rambling
- grounded coaching over bluffing
- clear uncertainty when data is missing
- tighter formatting for chat UX
- low redundancy
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
import json
import os
import re
import subprocess
import threading
import time
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types
from litellm import completion
from pydantic import BaseModel, Field


load_dotenv()


class _MetricVerdict(BaseModel):
    score: int = Field(ge=1, le=5)
    explanation: str


class _CoachEvalVerdict(BaseModel):
    response_quality: _MetricVerdict
    directness: _MetricVerdict
    factual_grounding: _MetricVerdict
    uncertainty_behavior: _MetricVerdict
    formatting_quality: _MetricVerdict
    non_redundancy: _MetricVerdict


_CoachEvalVerdict.model_rebuild()

_PLACEHOLDER_PROJECTS = {"", "your-gcp-project-id"}
_TOKEN_CACHE: dict[str, tuple[str, float]] = {}
_TOKEN_LOCK = threading.Lock()
_TOKEN_TTL_SECONDS = 3000
_VERDICT_CACHE: dict[str, _CoachEvalVerdict] = {}
_VERDICT_LOCK = threading.Lock()
_WORKING_JUDGE_CONFIG: _JudgeConfig | None = None
_JUDGE_LOCK = threading.Lock()
_GCLOUD_PROJECT_CACHE: str | None = None


@dataclass(frozen=True)
class _JudgeConfig:
    provider: str
    model: str
    api_key: str | None = None
    api_base: str | None = None
    project: str | None = None
    location: str | None = None
    audience: str | None = None


def _env_value(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip().strip('"').strip("'")
        if value:
            return value
    return ""


def _env_flag(*names: str) -> bool:
    value = _env_value(*names).lower()
    return value in {"1", "true", "yes", "on"}


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


def _reference_text(reference: Any) -> str | None:
    if reference is None:
        return None
    if isinstance(reference, str):
        return reference
    if isinstance(reference, dict):
        response = reference.get("response")
        if isinstance(response, dict):
            parts = response.get("parts") or []
            texts = [part.get("text") for part in parts if isinstance(part, dict) and part.get("text")]
            if texts:
                return "\n".join(texts)
        parts = reference.get("parts") or []
        texts = [part.get("text") for part in parts if isinstance(part, dict) and part.get("text")]
        if texts:
            return "\n".join(texts)
    return str(reference)


def _rubric_text(rubrics: Any) -> str | None:
    if not isinstance(rubrics, list):
        return None
    texts: list[str] = []
    for rubric in rubrics:
        if not isinstance(rubric, dict):
            continue
        content = rubric.get("rubricContent")
        if isinstance(content, dict):
            text = content.get("textProperty")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
    if texts:
        return "\n".join(texts)
    return None


def _has_valid_vertex_project() -> bool:
    project = _env_value("GOOGLE_CLOUD_PROJECT")
    return project not in _PLACEHOLDER_PROJECTS


def _resolve_proxy_url() -> str | None:
    value = _env_value("LITELLM_PROXY_URL")
    return value or None


def _resolve_proxy_key() -> str:
    return _env_value("LITELLM_PROXY_API_KEY", "OPENAI_API_KEY")


def _resolve_litellm_model() -> str:
    model = _env_value("OPENAI_MODEL") or "gpt-4o-mini"
    if _resolve_proxy_url() and "/" not in model:
        return f"openai/{model}"
    return model


def _fetch_oidc_token(audience: str) -> str:
    now = time.monotonic()
    with _TOKEN_LOCK:
        cached = _TOKEN_CACHE.get(audience)
        if cached and cached[1] > now:
            return cached[0]

        token = _fetch_token_via_adc(audience) or _fetch_token_via_gcloud(audience)
        if not token:
            raise RuntimeError(
                "Could not fetch a Google identity token for the LiteLLM proxy. "
                "Run `gcloud auth login` or set `GOOGLE_APPLICATION_CREDENTIALS`."
            )
        _TOKEN_CACHE[audience] = (token, now + _TOKEN_TTL_SECONDS)
        return token


def _fetch_token_via_adc(audience: str) -> str | None:
    try:
        import google.auth.exceptions
        import google.auth.transport.requests
        from google.oauth2 import id_token

        request = google.auth.transport.requests.Request()
        return id_token.fetch_id_token(request, audience)
    except Exception:
        return None


def _fetch_token_via_gcloud(audience: str) -> str | None:
    try:
        command = ["gcloud", "auth", "print-identity-token"]
        if audience:
            command.extend(["--audiences", audience])
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _generate_judge_json_for_config(config: _JudgeConfig, prompt: str) -> str:
    if config.provider == "vertexai":
        client = genai.Client(
            vertexai=True,
            project=config.project,
            location=config.location or "global",
        )
        response = client.models.generate_content(
            model=config.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=_CoachEvalVerdict,
            ),
        )
        return response.text or ""

    if config.provider == "gemini_api":
        client = genai.Client(
            api_key=config.api_key
        )
        response = client.models.generate_content(
            model=config.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=_CoachEvalVerdict,
            ),
        )
        return response.text or ""

    if config.provider in {"litellm_proxy", "openai"}:
        completion_kwargs: dict[str, Any] = {}
        if config.api_base:
            completion_kwargs["api_base"] = config.api_base
        if config.provider == "litellm_proxy" and config.audience:
            completion_kwargs["api_key"] = _fetch_oidc_token(config.audience)
            if config.api_key:
                completion_kwargs["extra_headers"] = {"x-litellm-api-key": config.api_key}
        elif config.api_key:
            completion_kwargs["api_key"] = config.api_key
        response = completion(
            model=config.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return only valid JSON matching this schema: "
                        "{response_quality:{score:int,explanation:str},"
                        "directness:{score:int,explanation:str},"
                        "factual_grounding:{score:int,explanation:str},"
                        "uncertainty_behavior:{score:int,explanation:str},"
                        "formatting_quality:{score:int,explanation:str},"
                        "non_redundancy:{score:int,explanation:str}}"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            **completion_kwargs,
        )
        return response.choices[0].message.content or ""

    raise RuntimeError(
        "No eval judge provider is configured. Set a real Vertex project, "
        "a Gemini API key, or the LiteLLM/OpenAI environment variables."
    )


def _resolve_vertex_project(*, prefer_eval: bool) -> str:
    if prefer_eval:
        project = _env_value("EVAL_GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_PROJECT")
        if _valid_vertex_project(project):
            return project
        return _gcloud_default_project()

    project = _env_value("GOOGLE_CLOUD_PROJECT")
    if _valid_vertex_project(project):
        return project
    return _gcloud_default_project()


def _resolve_vertex_location(*, prefer_eval: bool) -> str:
    return _env_value("EVAL_GOOGLE_CLOUD_LOCATION", "GOOGLE_CLOUD_LOCATION") if prefer_eval else _env_value("GOOGLE_CLOUD_LOCATION")


def _resolve_vertex_enabled(*, prefer_eval: bool) -> bool:
    if prefer_eval:
        return _env_flag("EVAL_GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_GENAI_USE_VERTEXAI")
    return _env_flag("GOOGLE_GENAI_USE_VERTEXAI")


def _resolve_gemini_key(*, prefer_eval: bool) -> str:
    return (
        _env_value("EVAL_GEMINI_API_KEY", "EVAL_GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")
        if prefer_eval
        else _env_value("GEMINI_API_KEY", "GOOGLE_API_KEY")
    )


def _resolve_openai_key(*, prefer_eval: bool) -> str:
    return (
        _env_value("EVAL_OPENAI_API_KEY", "OPENAI_API_KEY")
        if prefer_eval
        else _env_value("OPENAI_API_KEY")
    )


def _resolve_openai_api_base(*, prefer_eval: bool) -> str:
    return (
        _env_value("EVAL_OPENAI_API_BASE", "OPENAI_API_BASE")
        if prefer_eval
        else _env_value("OPENAI_API_BASE")
    )


def _resolve_openai_model(*, prefer_eval: bool, via_proxy: bool) -> str:
    if prefer_eval:
        model = _env_value("EVAL_OPENAI_MODEL", "OPENAI_MODEL") or "gpt-4o-mini"
    else:
        model = _env_value("OPENAI_MODEL") or "gpt-4o-mini"
    if via_proxy and "/" not in model:
        return f"openai/{model}"
    if not via_proxy and model.startswith("openai/"):
        return model.split("/", 1)[1]
    return model


def _resolve_proxy_url_for_eval(*, prefer_eval: bool) -> str:
    return (
        _env_value("EVAL_LITELLM_PROXY_URL", "LITELLM_PROXY_URL")
        if prefer_eval
        else _env_value("LITELLM_PROXY_URL")
    )


def _resolve_proxy_key_for_eval(*, prefer_eval: bool) -> str:
    return (
        _env_value("EVAL_LITELLM_PROXY_API_KEY", "LITELLM_PROXY_API_KEY", "EVAL_OPENAI_API_KEY", "OPENAI_API_KEY")
        if prefer_eval
        else _env_value("LITELLM_PROXY_API_KEY", "OPENAI_API_KEY")
    )


def _valid_vertex_project(project: str) -> bool:
    return bool(project) and project not in _PLACEHOLDER_PROJECTS


def _config_identity(config: _JudgeConfig) -> tuple[str, str, str | None, str | None, str | None, str | None, str | None]:
    return (
        config.provider,
        config.model,
        config.api_base,
        config.project,
        config.location,
        config.api_key,
        config.audience,
    )


def _resolve_judge_configs() -> list[_JudgeConfig]:
    explicit_provider = _env_value("EVAL_JUDGE_PROVIDER").lower()

    def _build(provider: str, *, prefer_eval: bool) -> _JudgeConfig:
        if provider == "vertexai":
            project = _resolve_vertex_project(prefer_eval=prefer_eval)
            if not _valid_vertex_project(project):
                raise RuntimeError(
                    "Eval judge provider `vertexai` was selected but no real Google Cloud project is configured."
                )
            return _JudgeConfig(
                provider="vertexai",
                model=_env_value("EVAL_GEMINI_MODEL", "GEMINI_MODEL") or "gemini-flash-latest",
                project=project,
                location=_resolve_vertex_location(prefer_eval=prefer_eval) or "global",
            )
        if provider == "gemini_api":
            api_key = _resolve_gemini_key(prefer_eval=prefer_eval)
            if not api_key:
                raise RuntimeError(
                    "Eval judge provider `gemini_api` was selected but no Gemini API key is configured."
                )
            return _JudgeConfig(
                provider="gemini_api",
                model=_env_value("EVAL_GEMINI_MODEL", "GEMINI_MODEL") or "gemini-flash-latest",
                api_key=api_key,
            )
        if provider == "openai":
            api_key = _resolve_openai_key(prefer_eval=prefer_eval)
            if not api_key:
                raise RuntimeError(
                    "Eval judge provider `openai` was selected but no OpenAI API key is configured."
                )
            return _JudgeConfig(
                provider="openai",
                model=_resolve_openai_model(prefer_eval=prefer_eval, via_proxy=False),
                api_key=api_key,
                api_base=_resolve_openai_api_base(prefer_eval=prefer_eval) or None,
            )
        if provider == "litellm_proxy":
            proxy_url = _resolve_proxy_url_for_eval(prefer_eval=prefer_eval)
            proxy_key = _resolve_proxy_key_for_eval(prefer_eval=prefer_eval)
            if not proxy_url:
                raise RuntimeError(
                    "Eval judge provider `litellm_proxy` was selected but no proxy URL is configured."
                )
            audience = proxy_url.rstrip("/").split("/v1")[0] if ".run.app" in proxy_url else None
            return _JudgeConfig(
                provider="litellm_proxy",
                model=_resolve_openai_model(prefer_eval=prefer_eval, via_proxy=True),
                api_key=proxy_key or None,
                api_base=proxy_url,
                audience=audience,
            )
        raise RuntimeError(
            f"Unknown eval judge provider `{provider}`. Use one of: vertexai, gemini_api, openai, litellm_proxy."
        )

    if explicit_provider:
        return [_build(explicit_provider, prefer_eval=True)]

    candidates: list[_JudgeConfig] = []
    seen: set[tuple[str, str, str | None, str | None, str | None, str | None, str | None]] = set()

    def _append(provider: str, *, prefer_eval: bool, enabled: bool) -> None:
        if not enabled:
            return
        config = _build(provider, prefer_eval=prefer_eval)
        identity = _config_identity(config)
        if identity in seen:
            return
        seen.add(identity)
        candidates.append(config)

    eval_vertex_project = _resolve_vertex_project(prefer_eval=True)
    _append(
        "vertexai",
        prefer_eval=True,
        enabled=_resolve_vertex_enabled(prefer_eval=True) and _valid_vertex_project(eval_vertex_project),
    )
    _append("gemini_api", prefer_eval=True, enabled=bool(_resolve_gemini_key(prefer_eval=True)))
    _append("openai", prefer_eval=True, enabled=bool(_env_value("EVAL_OPENAI_API_KEY")))
    _append("litellm_proxy", prefer_eval=True, enabled=bool(_env_value("EVAL_LITELLM_PROXY_URL")))

    general_vertex_project = _resolve_vertex_project(prefer_eval=False)
    _append(
        "vertexai",
        prefer_eval=False,
        enabled=_resolve_vertex_enabled(prefer_eval=False) and _valid_vertex_project(general_vertex_project),
    )
    _append("gemini_api", prefer_eval=False, enabled=bool(_resolve_gemini_key(prefer_eval=False)))
    _append("openai", prefer_eval=False, enabled=bool(_resolve_openai_key(prefer_eval=False)))
    _append("litellm_proxy", prefer_eval=False, enabled=bool(_resolve_proxy_url_for_eval(prefer_eval=False)))

    if candidates:
        return candidates

    raise RuntimeError(
        "No eval judge provider is configured. Set one of the EVAL_* provider variables, "
        "or configure a normal Vertex, Gemini API, LiteLLM proxy, or OpenAI runtime."
    )


def _resolve_judge_config() -> _JudgeConfig:
    return _resolve_judge_configs()[0]


def _generate_judge_json(prompt: str) -> str:
    global _WORKING_JUDGE_CONFIG

    errors: list[str] = []
    candidates = _resolve_judge_configs()

    with _JUDGE_LOCK:
        cached = _WORKING_JUDGE_CONFIG

    ordered_candidates: list[_JudgeConfig] = []
    if cached is not None:
        ordered_candidates.append(cached)
    ordered_candidates.extend(
        config
        for config in candidates
        if cached is None or _config_identity(config) != _config_identity(cached)
    )

    for config in ordered_candidates:
        try:
            payload = _generate_judge_json_for_config(config, prompt)
        except Exception as exc:
            errors.append(f"{config.provider}: {exc}")
            if cached is not None and _config_identity(config) == _config_identity(cached):
                with _JUDGE_LOCK:
                    if _WORKING_JUDGE_CONFIG is not None and _config_identity(_WORKING_JUDGE_CONFIG) == _config_identity(config):
                        _WORKING_JUDGE_CONFIG = None
            continue
        with _JUDGE_LOCK:
            _WORKING_JUDGE_CONFIG = config
        return payload

    if errors:
        raise RuntimeError("All configured eval judge providers failed: " + " | ".join(errors))
    raise RuntimeError("No eval judge provider produced a response.")


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _clamp(score: int) -> int:
    return max(1, min(5, score))


def _instance_cache_key(instance: dict[str, Any]) -> str:
    payload = {
        "prompt": instance.get("prompt", ""),
        "response": instance.get("response", ""),
        "reference": instance.get("reference"),
        "rubrics": instance.get("rubrics"),
        "agent_data": instance.get("agent_data", ""),
    }
    return sha1(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _numeric_tokens(text: str) -> set[str]:
    return set(re.findall(r"\b\d+(?:\.\d+)?%?\b", text))


def _keyword_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9\-/+']+", text.lower())
        if len(token) >= 4
    }


def _repetition_penalty(text: str) -> int:
    sentences = [segment.strip().lower() for segment in re.split(r"[.!?\n]+", text) if segment.strip()]
    if len(sentences) < 2:
        return 0
    repeats = len(sentences) - len(set(sentences))
    if repeats >= 3:
        return 2
    if repeats >= 1:
        return 1
    return 0


def _heuristic_grade(instance: dict[str, Any], error: str) -> _CoachEvalVerdict:
    prompt = str(instance.get("prompt", "") or "")
    response = str(instance.get("response", "") or "").strip()
    reference = _reference_text(instance.get("reference")) or _rubric_text(instance.get("rubrics")) or ""
    lowered_prompt = prompt.lower()
    lowered_response = response.lower()
    lowered_reference = reference.lower()
    first_line = next((line.strip() for line in response.splitlines() if line.strip()), "")
    response_words = response.split()
    response_len = len(response)
    bullets = sum(1 for line in response.splitlines() if line.lstrip().startswith("- "))
    repeated_penalty = _repetition_penalty(response)
    generic_outro = _contains_any(
        lowered_response,
        (
            "the next best coaching step",
            "if you want, i can also",
            "if you want, i can",
            "what i can say is",
            "if you mean",
        ),
    )
    uncertainty_phrase = _contains_any(
        lowered_response,
        (
            "i can't verify",
            "i cannot verify",
            "i don't have",
            "not available",
            "no synced",
            "the local data here",
            "from the local data",
        ),
    )
    numeric_overlap = len(_numeric_tokens(lowered_response) & _numeric_tokens(lowered_reference))
    keyword_overlap = len(_keyword_tokens(lowered_response) & _keyword_tokens(lowered_reference))

    directness = 3
    if first_line and len(first_line.split()) <= 24:
        directness += 1
    if generic_outro:
        directness -= 1
    if first_line.lower().startswith(("yes", "no", "on ", "late game", "boons", "a 4.8k", "you ")) or _contains_any(
        first_line.lower(),
        (" means ", " is ", " are ", " looks like "),
    ):
        directness += 1
    if response_len > 900:
        directness -= 1

    factual_grounding = 3
    if numeric_overlap > 0 or keyword_overlap >= 3:
        factual_grounding += 1
    if numeric_overlap > 1 or keyword_overlap >= 6:
        factual_grounding += 1
    if _contains_any(lowered_response, ("maybe", "probably", "i think")) and not uncertainty_phrase:
        factual_grounding -= 1
    if _contains_any(lowered_response, ("fake", "guess", "from memory")):
        factual_grounding -= 1

    uncertainty_behavior = 3
    if uncertainty_phrase:
        uncertainty_behavior += 1
    if uncertainty_phrase and _contains_any(lowered_response, ("best local read", "closest grounded", "what i can verify")):
        uncertainty_behavior += 1
    if generic_outro and uncertainty_phrase:
        uncertainty_behavior -= 1
    if _contains_any(lowered_response, ("definitely", "always", "never")) and uncertainty_phrase:
        uncertainty_behavior -= 1

    formatting_quality = 3
    if response_len <= 650:
        formatting_quality += 1
    if bullets and bullets <= 3:
        formatting_quality += 1
    if response_len > 1100 or any(len(line) > 260 for line in response.splitlines() if line.strip()):
        formatting_quality -= 1
    if not bullets and response_len > 700 and "\n\n" not in response:
        formatting_quality -= 1

    non_redundancy = 4
    non_redundancy -= repeated_penalty
    if generic_outro:
        non_redundancy -= 1
    if response_len <= 500:
        non_redundancy += 1

    quality_seed = round(
        (
            _clamp(directness)
            + _clamp(factual_grounding)
            + _clamp(uncertainty_behavior)
            + _clamp(formatting_quality)
            + _clamp(non_redundancy)
        )
        / 5
    )
    if not response_words:
        quality_seed = 1
    elif len(response_words) < 6:
        quality_seed = min(quality_seed, 2)

    explanation_suffix = f" Heuristic fallback was used because the eval judge was unavailable: {error}"
    return _CoachEvalVerdict(
        response_quality=_MetricVerdict(
            score=_clamp(quality_seed),
            explanation="Overall score blended directness, grounding, uncertainty handling, formatting, and redundancy." + explanation_suffix,
        ),
        directness=_MetricVerdict(
            score=_clamp(directness),
            explanation="Favored answers that lead with the actual answer, stay short, and avoid generic detours." + explanation_suffix,
        ),
        factual_grounding=_MetricVerdict(
            score=_clamp(factual_grounding),
            explanation="Estimated grounding from overlap with rubric/reference cues and penalized unsupported speculation language." + explanation_suffix,
        ),
        uncertainty_behavior=_MetricVerdict(
            score=_clamp(uncertainty_behavior),
            explanation="Rewarded brief honest caveats when data is missing and penalized bluffy or meandering fallback language." + explanation_suffix,
        ),
        formatting_quality=_MetricVerdict(
            score=_clamp(formatting_quality),
            explanation="Rewarded short paragraphs or small bullet lists and penalized giant unbroken text blobs." + explanation_suffix,
        ),
        non_redundancy=_MetricVerdict(
            score=_clamp(non_redundancy),
            explanation="Rewarded concise answers and penalized repeated lines, repeated framing, and generic outro padding." + explanation_suffix,
        ),
    )


def _grade(instance: dict[str, Any]) -> _CoachEvalVerdict:
    cache_key = _instance_cache_key(instance)
    with _VERDICT_LOCK:
        cached = _VERDICT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    reference = _reference_text(instance.get("reference")) or _rubric_text(instance.get("rubrics"))
    prompt = f"""
You are grading a Deadlock coaching chat agent.

Score each category from 1 to 5.

Important grading rule:
- Treat the expected grounding or shape below as the canonical rubric for this case.
- If the answer contradicts that rubric, answers a different interpretation, ignores the requested scope, or refuses despite an expected grounded answer path, score it low even if it sounds plausible.

Definitions:
- response_quality: overall usefulness and correctness
- directness: answers the user's actual question early without meandering
- factual_grounding: does not invent stats or capabilities and stays anchored in available evidence
- uncertainty_behavior: when data is missing, clearly says so without over-apologizing or bluffing
- formatting_quality: clean chat formatting, easy to scan, not a giant blob
- non_redundancy: does not repeat the same point or stat unnecessarily

User prompt:
{instance.get("prompt", "")}

Final response:
{instance.get("response", "")}
""".strip()
    if reference:
        prompt += f"\n\nExpected grounding or shape:\n{reference}"
    prompt += f"\n\nTrace data:\n{instance.get('agent_data', '')}"

    try:
        raw = _generate_judge_json(prompt)
        if not raw:
            raise RuntimeError("Eval model returned no structured verdict.")
        verdict = _CoachEvalVerdict.model_validate(json.loads(raw))
    except Exception as exc:
        verdict = _heuristic_grade(instance, str(exc))

    with _VERDICT_LOCK:
        _VERDICT_CACHE[cache_key] = verdict
    return verdict


def _metric_payload(verdict: _MetricVerdict) -> dict[str, Any]:
    return {"score": verdict.score, "explanation": verdict.explanation}


def evaluate(instance: dict[str, Any]) -> dict[str, Any]:
    return custom_response_quality(instance)


def custom_response_quality(instance: dict[str, Any]) -> dict[str, Any]:
    return _metric_payload(_grade(instance).response_quality)


def custom_directness(instance: dict[str, Any]) -> dict[str, Any]:
    return _metric_payload(_grade(instance).directness)


def custom_factual_grounding(instance: dict[str, Any]) -> dict[str, Any]:
    return _metric_payload(_grade(instance).factual_grounding)


def custom_uncertainty_behavior(instance: dict[str, Any]) -> dict[str, Any]:
    return _metric_payload(_grade(instance).uncertainty_behavior)


def custom_formatting_quality(instance: dict[str, Any]) -> dict[str, Any]:
    return _metric_payload(_grade(instance).formatting_quality)


def custom_non_redundancy(instance: dict[str, Any]) -> dict[str, Any]:
    return _metric_payload(_grade(instance).non_redundancy)
