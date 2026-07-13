from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import hashlib
import importlib
import os
from types import SimpleNamespace
from typing import Any

from dotenv import load_dotenv

from app.litellm_bootstrap import resolve_proxy_url
from deadlock_coach.asset_service import detect_hero_name_in_text
from deadlock_coach.agent_contracts import CoachResponseEnvelope
from deadlock_coach.agent_orchestration import build_prompt_support, build_response_envelope, enrich_reply_payload
from deadlock_coach.coach_service import CoachContext, DEFAULT_WINDOW_MATCHES
from deadlock_coach.config import Settings
from deadlock_coach.runtime_context import ActiveCoachContext, use_active_coach_context
from deadlock_coach.telemetry import emit_event


class AdkChatUnavailableError(RuntimeError):
    """Raised when the ADK-backed chat runtime cannot serve a request."""


@dataclass(slots=True)
class _AdkRuntime:
    runner: Any
    session_service: Any
    app_name: str
    root_agent_name: str
    genai_types: Any


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None


_runtime_cache: dict[tuple[str | None, str | None, str], _AdkRuntime] = {}


def _build_context_preamble(
    context: CoachContext | None,
    *,
    envelope: CoachResponseEnvelope | None = None,
    resolved_hero_name: str | None = None,
) -> str:
    information_need = envelope.structured_output.routing.information_need if envelope is not None else None
    include_player_context = bool(
        context is not None
        and (
            envelope is None
            or envelope.structured_output.routing.family in {"greeting", "clarify"}
            or (information_need is not None and information_need.needs_player_telemetry)
        )
    )

    if context is not None and not include_player_context:
        return (
            "Current workspace context:\n"
            "- A player may be selected in the workspace, but this question is not player-specific unless the user asks about their own games.\n\n"
        )

    if context is None:
        return "Current workspace context:\n- No active player or account is selected.\n\n"

    lines: list[str] = []
    has_explicit_context = any(
        value
        for value in (context.player_label, context.account_id, context.hero_name, context.hero_id)
    )
    if context.player_label:
        lines.append(f"Active player label: {context.player_label}")
    if context.account_id is not None:
        lines.append(f"Active account id: {context.account_id}")
    if resolved_hero_name:
        lines.append(f"Hero focus: {resolved_hero_name}")
    if context.window_matches and (has_explicit_context or context.window_matches != DEFAULT_WINDOW_MATCHES):
        lines.append(f"Window: last {context.window_matches} matches")

    if not lines:
        return "Current workspace context:\n- No active player or account is selected.\n\n"

    return "Current workspace context:\n" + "\n".join(f"- {line}" for line in lines) + "\n\n"


def _build_user_prompt(
    message: str,
    context: CoachContext | None,
    *,
    prompt_support: str = "",
    envelope: CoachResponseEnvelope | None = None,
) -> str:
    resolved_hero_name = context.hero_name if context is not None else None
    try:
        detected_hero_name = detect_hero_name_in_text(Settings.from_env(), message)
    except Exception:
        detected_hero_name = None
    if detected_hero_name:
        resolved_hero_name = detected_hero_name

    preamble = _build_context_preamble(context, envelope=envelope, resolved_hero_name=resolved_hero_name)
    support_block = f"{prompt_support.strip()}\n\n" if prompt_support.strip() else ""
    return f"{support_block}{preamble}User request:\n{message.strip()}"


def _text_from_event(event: Any) -> str:
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    chunks = [str(part.text).strip() for part in parts if getattr(part, "text", None)]
    return "\n".join(chunk for chunk in chunks if chunk).strip()


def _extract_reply_text(events: list[Any], root_agent_name: str) -> str:
    preferred = [
        _text_from_event(event)
        for event in events
        if getattr(event, "author", None) == root_agent_name and _text_from_event(event)
    ]
    if preferred:
        return preferred[-1]

    fallback = [
        _text_from_event(event)
        for event in events
        if getattr(event, "author", None) not in {"", "user"} and _text_from_event(event)
    ]
    if fallback:
        return fallback[-1]

    return ""


def _event_authors(events: list[Any]) -> list[str]:
    seen: list[str] = []
    for event in events:
        author = str(getattr(event, "author", "") or "").strip()
        if not author or author in {"user"} or author in seen:
            continue
        seen.append(author)
    return seen


def _missing_reply_error_message(runtime_settings: RuntimeSettings | None = None) -> str:
    provider = runtime_settings.provider if runtime_settings and runtime_settings.provider else None
    if provider == "litellm_proxy" or (provider is None and resolve_proxy_url()):
        return (
            "ADK chat reached the LiteLLM proxy path, but the model call failed before any reply came back. "
            "Check the backend logs first. The most likely causes are missing Cloud Run auth, a bad proxy key, or outbound connectivity issues."
        )
    if provider == "openai" or (provider is None and os.environ.get("OPENAI_API_KEY")):
        return (
            "ADK chat reached the OpenAI-backed model path, but the model call failed before any reply came back. "
            "Check the backend logs first. The most likely causes are an invalid `OPENAI_API_KEY` or outbound API connectivity issues."
        )
    if provider == "gemini_api" or (provider is None and (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))):
        return (
            "ADK chat reached the Gemini-backed model path, but the model call failed before any reply came back. "
            "Check the backend logs first for API-key or connectivity issues."
        )
    return "ADK chat did not return a coach reply yet. Check the agent logs and try again."


def _normalize_runtime_settings(payload: dict[str, Any] | None) -> RuntimeSettings:
    payload = payload or {}
    provider = str(payload.get("provider") or "").strip() or None
    model = str(payload.get("model") or "").strip() or None
    api_key = str(payload.get("api_key") or "").strip() or None
    return RuntimeSettings(provider=provider, model=model, api_key=api_key)


def _runtime_cache_key(runtime_settings: RuntimeSettings) -> tuple[str | None, str | None, str]:
    api_key_hash = hashlib.sha256((runtime_settings.api_key or "").encode("utf-8")).hexdigest()
    return (runtime_settings.provider, runtime_settings.model, api_key_hash)


@contextmanager
def _temporary_runtime_env(runtime_settings: RuntimeSettings):
    managed_keys = [
        "DEADLOCK_COACH_PROVIDER_OVERRIDE",
        "DEADLOCK_COACH_MODEL_OVERRIDE",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "LITELLM_PROXY_API_KEY",
    ]
    previous = {key: os.environ.get(key) for key in managed_keys}

    try:
        if runtime_settings.provider:
            os.environ["DEADLOCK_COACH_PROVIDER_OVERRIDE"] = runtime_settings.provider
        else:
            os.environ.pop("DEADLOCK_COACH_PROVIDER_OVERRIDE", None)

        if runtime_settings.model:
            os.environ["DEADLOCK_COACH_MODEL_OVERRIDE"] = runtime_settings.model
        else:
            os.environ.pop("DEADLOCK_COACH_MODEL_OVERRIDE", None)

        if runtime_settings.provider == "openai":
            if runtime_settings.api_key:
                os.environ["OPENAI_API_KEY"] = runtime_settings.api_key
            os.environ.pop("GOOGLE_API_KEY", None)
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("LITELLM_PROXY_API_KEY", None)
        elif runtime_settings.provider == "gemini_api":
            if runtime_settings.api_key:
                os.environ["GOOGLE_API_KEY"] = runtime_settings.api_key
                os.environ["GEMINI_API_KEY"] = runtime_settings.api_key
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.pop("LITELLM_PROXY_API_KEY", None)
        elif runtime_settings.provider == "litellm_proxy":
            if runtime_settings.api_key:
                os.environ["LITELLM_PROXY_API_KEY"] = runtime_settings.api_key
            os.environ.pop("GOOGLE_API_KEY", None)
            os.environ.pop("GEMINI_API_KEY", None)

        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _format_runtime_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.lower()

    if "no api key was provided" in lowered or "api key" in lowered and "openai" in lowered:
        return (
            "ADK chat is wired, but no supported model key is configured. "
            "Set `LITELLM_PROXY_URL` plus `LITELLM_PROXY_API_KEY` or `OPENAI_API_KEY` for a proxy-backed OpenAI model, "
            "`OPENAI_API_KEY` for direct OpenAI, or `GOOGLE_API_KEY` / `GEMINI_API_KEY` for Gemini, "
            "then restart the local API."
        )

    if exc.__class__.__name__ == "ModuleNotFoundError" or "no module named 'google'" in lowered:
        return (
            "ADK dependencies are not available in this Python environment. "
            "Start the backend with the project virtualenv, for example "
            "`.venv/bin/python -m deadlock_coach serve --host 127.0.0.1 --port 3000`."
        )

    return f"ADK chat failed: {message}"


def _load_runtime(runtime_settings: RuntimeSettings | None = None) -> _AdkRuntime:
    runtime_settings = runtime_settings or RuntimeSettings()
    cache_key = _runtime_cache_key(runtime_settings)
    if cache_key in _runtime_cache:
        return _runtime_cache[cache_key]

    load_dotenv()
    with _temporary_runtime_env(runtime_settings):
        has_proxy_config = bool(resolve_proxy_url())
        has_openai_key = bool(os.environ.get("OPENAI_API_KEY"))
        has_gemini_key = bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))
        has_vertex_runtime = bool(os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") or os.environ.get("GOOGLE_CLOUD_PROJECT"))
        if not has_proxy_config and not has_openai_key and not has_gemini_key and not has_vertex_runtime:
            raise AdkChatUnavailableError(
                "ADK chat is wired, but no supported model key is configured. "
                "Set `LITELLM_PROXY_URL` plus `LITELLM_PROXY_API_KEY` or `OPENAI_API_KEY` for a proxy-backed OpenAI model, "
                "`OPENAI_API_KEY` for direct OpenAI, or `GOOGLE_API_KEY` / `GEMINI_API_KEY` for Gemini, "
                "then restart the local API."
            )

        try:
            from google.adk.runners import Runner
            from google.genai import types

            import app.agent as agent_module
            import app.model_factory as model_factory_module
            from app.app_utils import services as adk_services

            importlib.reload(model_factory_module)
            agent_module = importlib.reload(agent_module)
            adk_app = agent_module.app
            root_agent = agent_module.root_agent
        except Exception as exc:  # pragma: no cover - depends on runtime env
            raise AdkChatUnavailableError(_format_runtime_error(exc)) from exc

        try:
            session_service = adk_services.get_session_service()
            runner = Runner(
                app=adk_app,
                session_service=session_service,
                artifact_service=adk_services.get_artifact_service(),
                auto_create_session=True,
            )
        except Exception as exc:  # pragma: no cover - depends on runtime env
            raise AdkChatUnavailableError(_format_runtime_error(exc)) from exc

    runtime = _AdkRuntime(
        runner=runner,
        session_service=session_service,
        app_name=adk_app.name,
        root_agent_name=root_agent.name,
        genai_types=types,
    )
    _runtime_cache[cache_key] = runtime
    return runtime


def run_adk_chat(
    message: str,
    context: CoachContext | None = None,
    *,
    history: list[dict[str, object]] | None = None,
    session_id: str | None = None,
    user_id: str = "local-user",
    runtime_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = Settings.from_env()
    normalized_runtime_settings = _normalize_runtime_settings(runtime_settings)
    orchestration = build_response_envelope(settings, message, context or CoachContext(), history=history)
    prompt_support = build_prompt_support(orchestration)
    telemetry_user = user_id or "local-user"
    emit_event(
        settings,
        "adk_chat.start",
        session_id=session_id,
        user_id=telemetry_user,
        has_context=context is not None,
        provider=normalized_runtime_settings.provider,
        model=normalized_runtime_settings.model,
        selected_specialists=orchestration.trace.selected_specialists,
        confidence=orchestration.confidence.level,
    )

    try:
        with _temporary_runtime_env(normalized_runtime_settings):
            runtime = _load_runtime(normalized_runtime_settings)
            session = (
                runtime.session_service.create_session_sync(
                    app_name=runtime.app_name,
                    user_id=user_id,
                    session_id=session_id,
                )
                if session_id is None
                else None
            )
            resolved_session_id = session_id or session.id
            prompt = _build_user_prompt(message, context, prompt_support=prompt_support, envelope=orchestration)
            request = runtime.genai_types.Content(
                role="user",
                parts=[runtime.genai_types.Part.from_text(text=prompt)],
            )
            active_context = ActiveCoachContext(
                account_id=context.account_id if context is not None else None,
                player_label=context.player_label if context is not None else None,
                hero_name=context.hero_name if context is not None else None,
                window_matches=context.window_matches if context is not None else None,
            )
            with use_active_coach_context(active_context):
                events = list(
                    runtime.runner.run(
                        user_id=user_id,
                        session_id=resolved_session_id,
                        new_message=request,
                    )
                )
    except Exception as exc:  # pragma: no cover - depends on runtime env
        emit_event(
            settings,
            "adk_chat.error",
            session_id=session_id,
            user_id=telemetry_user,
            error=str(exc),
        )
        raise AdkChatUnavailableError(_format_runtime_error(exc)) from exc

    reply = _extract_reply_text(events, runtime.root_agent_name)
    if not reply:
        emit_event(
            settings,
            "adk_chat.empty_reply",
            session_id=resolved_session_id,
            user_id=telemetry_user,
            event_count=len(events),
        )
        raise AdkChatUnavailableError(_missing_reply_error_message(normalized_runtime_settings))

    emit_event(
        settings,
        "adk_chat.finish",
        session_id=resolved_session_id,
        user_id=telemetry_user,
        event_count=len(events),
        root_agent=runtime.root_agent_name,
        selected_specialists=orchestration.trace.selected_specialists,
        confidence=orchestration.confidence.level,
        event_authors=_event_authors(events),
    )

    payload = {
        "reply": reply,
        "source": "google_adk",
        "session_id": resolved_session_id,
        "debug": {
            "event_count": len(events),
            "root_agent": runtime.root_agent_name,
            "event_authors": _event_authors(events),
        },
    }
    return enrich_reply_payload(payload, orchestration)


def _fake_event(author: str, text: str) -> Any:
    """Test helper for lightweight event-shape fixtures."""

    return SimpleNamespace(
        author=author,
        content=SimpleNamespace(parts=[SimpleNamespace(text=text)]),
    )
