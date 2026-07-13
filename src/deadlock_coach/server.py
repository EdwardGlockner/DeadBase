from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import json
import os
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from pydantic import ValidationError

from deadlock_coach.account_service import DEFAULT_HYDRATE_MATCHES, AccountCandidate, search_account_candidates, sync_account
from deadlock_coach.adk_chat import AdkChatUnavailableError, run_adk_chat
from deadlock_coach.agent_orchestration import build_response_envelope, enrich_reply_payload
from deadlock_coach.api_models import (
    AccountSearchResponse,
    AccountsResponse,
    ChatRequest,
    ChatResponse,
    RuntimeSettingsBootstrapResponse,
    ErrorResponse,
    HealthResponse,
    RecentMatchesResponse,
    SummaryRequest,
    SyncAccountRequest,
    TelemetryEventsResponse,
)
from deadlock_coach.coach_service import (
    DEFAULT_WINDOW_MATCHES,
    build_workspace_summary,
    json_dumps,
    list_tracked_accounts,
    parse_context,
    recent_matches_payload,
    summarize_account,
    utility_reply_for_message,
)
from deadlock_coach.config import Settings
from deadlock_coach.telemetry import emit_event, read_recent_events, traced_operation

ADK_CHAT_TIMEOUT_SECONDS = 35.0


def _resolve_dev_runtime_settings() -> RuntimeSettingsBootstrapResponse:
    proxy_url = os.environ.get("LITELLM_PROXY_URL", "").strip()
    if proxy_url:
        return RuntimeSettingsBootstrapResponse(
            provider="litellm_proxy",
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=(os.environ.get("LITELLM_PROXY_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip() or None,
        )

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if openai_key:
        return RuntimeSettingsBootstrapResponse(
            provider="openai",
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            api_key=openai_key,
        )

    gemini_key = (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip()
    if gemini_key:
        return RuntimeSettingsBootstrapResponse(
            provider="gemini_api",
            model=os.environ.get("GEMINI_MODEL", "gemini-flash-latest"),
            api_key=gemini_key,
        )

    return RuntimeSettingsBootstrapResponse(provider="openai", model="gpt-4o-mini", api_key=None)


def _build_adk_unavailable_reply(
    settings: Settings,
    *,
    message: str,
    context: Any,
    history: list[dict[str, Any]] | None,
    session_id: str | None,
    reason: str,
) -> dict[str, Any]:
    payload = {
        "insight": "Coach unavailable",
        "reply": (
            "The instruction-driven coach is unavailable right now, so I do not want to fake an answer. "
            "Fix the runtime issue and try the same question again."
        ),
        "evidence": [reason],
        "source": "adk_unavailable",
        "unavailable_reason": reason,
        "session_id": session_id,
        "context": asdict(context),
    }
    if context.account_id is not None:
        summary_payload = build_workspace_summary(
            settings,
            account_id=context.account_id,
            window_matches=context.window_matches,
        )
        payload["summary"] = summary_payload.get("account_summary")
    return enrich_reply_payload(payload, build_response_envelope(settings, message, context, history=history))


def _build_adk_reply(
    settings: Settings,
    *,
    message: str,
    context: Any,
    session_id: str | None,
    user_id: str,
    history: list[dict[str, Any]] | None,
    runtime_settings: dict[str, Any] | None,
) -> dict[str, Any]:
    utility_reply = utility_reply_for_message(message)
    if utility_reply is not None:
        utility_reply["session_id"] = session_id
        return enrich_reply_payload(utility_reply, build_response_envelope(settings, message, context, history=history))

    try:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            run_adk_chat,
            message,
            context,
            history=history,
            session_id=session_id,
            user_id=user_id,
            runtime_settings=runtime_settings,
        )
        try:
            reply = future.result(timeout=ADK_CHAT_TIMEOUT_SECONDS)
        except FutureTimeoutError as exc:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            raise AdkChatUnavailableError(
                f"ADK chat timed out after {ADK_CHAT_TIMEOUT_SECONDS:g} seconds."
            ) from exc
        except Exception:
            executor.shutdown(wait=True, cancel_futures=False)
            raise
        else:
            executor.shutdown(wait=True, cancel_futures=False)
        if context.account_id is not None:
            summary_payload = build_workspace_summary(
                settings,
                account_id=context.account_id,
                window_matches=context.window_matches,
            )
            reply["summary"] = summary_payload.get("account_summary")
        return reply
    except AdkChatUnavailableError as exc:
        return _build_adk_unavailable_reply(
            settings,
            message=message,
            context=context,
            history=history,
            session_id=session_id,
            reason=str(exc),
        )


def _request_id() -> str:
    return uuid4().hex


class DeadlockCoachApiServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], settings: Settings) -> None:
        self.settings = settings
        super().__init__(server_address, _build_handler(settings))


def _build_handler(settings: Settings) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "DeadlockCoachApi/0.1.0"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

        def _write_json(self, status: HTTPStatus, payload: Any) -> None:
            if hasattr(payload, "model_dump"):
                payload = payload.model_dump(mode="json", exclude_none=True)
            body = json_dumps(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> dict[str, Any]:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError("Expected a JSON request body.") from exc
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object body.")
            return payload

        def _write_error(self, status: HTTPStatus, message: str, request_id: str | None = None) -> None:
            self._write_json(status, ErrorResponse(error=message, request_id=request_id))

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._write_json(HTTPStatus.NO_CONTENT, {})

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            request_id = _request_id()

            try:
                with traced_operation(settings, "api.get", request_id=request_id, route=parsed.path, method="GET") as trace:
                    if parsed.path == "/api/health":
                        trace["status_code"] = HTTPStatus.OK
                        self._write_json(
                            HTTPStatus.OK,
                            HealthResponse(status="ok", service="deadlock-coach-api", request_id=request_id),
                        )
                        return

                    if parsed.path == "/api/accounts":
                        accounts = list_tracked_accounts(settings)
                        trace["status_code"] = HTTPStatus.OK
                        trace["account_count"] = len(accounts)
                        self._write_json(HTTPStatus.OK, AccountsResponse(accounts=accounts))
                        return

                    if parsed.path == "/api/dev/runtime-settings":
                        payload = _resolve_dev_runtime_settings()
                        trace["status_code"] = HTTPStatus.OK
                        trace["provider"] = payload.provider
                        trace["has_api_key"] = bool(payload.api_key)
                        self._write_json(HTTPStatus.OK, payload)
                        return

                    if parsed.path == "/api/telemetry/recent":
                        limit = int(query.get("limit", ["50"])[0])
                        payload = read_recent_events(settings, limit=limit)
                        trace["status_code"] = HTTPStatus.OK
                        trace["event_count"] = len(payload)
                        self._write_json(
                            HTTPStatus.OK,
                            TelemetryEventsResponse(events=payload, request_id=request_id),
                        )
                        return

                    if parsed.path == "/api/account-search":
                        search_query = str(query.get("q", [""])[0]).strip()
                        limit = int(query.get("limit", ["8"])[0])
                        results = search_account_candidates(settings, search_query, limit=limit)
                        trace["status_code"] = HTTPStatus.OK
                        trace["result_count"] = len(results)
                        self._write_json(
                            HTTPStatus.OK,
                            AccountSearchResponse(
                                query=search_query,
                                results=[asdict(item) for item in results],
                            ),
                        )
                        return

                    if parsed.path == "/api/summary":
                        raw_account_id = query.get("account_id", [None])[0]
                        window_matches = int(query.get("window_matches", [str(DEFAULT_WINDOW_MATCHES)])[0])
                        account_id = int(raw_account_id) if raw_account_id is not None else None
                        payload = build_workspace_summary(settings, account_id=account_id, window_matches=window_matches)
                        trace["status_code"] = HTTPStatus.OK
                        trace["has_account_summary"] = payload.get("account_summary") is not None
                        self._write_json(HTTPStatus.OK, payload)
                        return

                    if parsed.path == "/api/recent-matches":
                        raw_account_id = query.get("account_id", [None])[0]
                        if raw_account_id is None:
                            raise ValueError("`account_id` is required.")
                        window_matches = int(query.get("window_matches", [str(DEFAULT_WINDOW_MATCHES)])[0])
                        payload = recent_matches_payload(settings, int(raw_account_id), window_matches=window_matches)
                        if payload is None:
                            raise ValueError(f"No recent matches are available for account {raw_account_id}.")
                        trace["status_code"] = HTTPStatus.OK
                        trace["match_count"] = len(payload["matches"])
                        self._write_json(
                            HTTPStatus.OK,
                            RecentMatchesResponse(**payload, request_id=request_id),
                        )
                        return

                    trace["status_code"] = HTTPStatus.NOT_FOUND
                    self._write_error(HTTPStatus.NOT_FOUND, f"Unknown route: {parsed.path}", request_id=request_id)
            except ValueError as exc:
                self._write_error(HTTPStatus.BAD_REQUEST, str(exc), request_id=request_id)
            except ValidationError as exc:
                self._write_error(HTTPStatus.BAD_REQUEST, exc.errors()[0]["msg"], request_id=request_id)
            except Exception as exc:  # pragma: no cover - defensive API boundary
                emit_event(settings, "api.get.unhandled_error", request_id=request_id, route=parsed.path, error=str(exc))
                self._write_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc), request_id=request_id)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            request_id = _request_id()
            try:
                with traced_operation(settings, "api.post", request_id=request_id, route=parsed.path, method="POST") as trace:
                    if parsed.path == "/api/chat":
                        body = ChatRequest.model_validate(self._read_json_body())
                        context = parse_context(None if body.context is None else body.context.model_dump())
                        history = None if body.history is None else [turn.model_dump() for turn in body.history]
                        reply = _build_adk_reply(
                            settings,
                            message=body.message.strip(),
                            context=context,
                            session_id=None,
                            user_id="local-user",
                            history=history,
                            runtime_settings=None,
                        )
                        trace["status_code"] = HTTPStatus.OK
                        trace["source"] = reply.get("source")
                        trace["adk_unavailable"] = reply.get("source") == "adk_unavailable"
                        self._write_json(
                            HTTPStatus.OK,
                            ChatResponse(**reply, request_id=request_id),
                        )
                        return

                    if parsed.path == "/api/adk/chat":
                        body = ChatRequest.model_validate(self._read_json_body())
                        context = parse_context(None if body.context is None else body.context.model_dump())
                        history = None if body.history is None else [turn.model_dump() for turn in body.history]
                        session_id = body.session_id.strip() if body.session_id else None
                        user_id = body.user_id.strip() if body.user_id else "local-user"
                        runtime_settings = None if body.runtime_settings is None else body.runtime_settings.model_dump()

                        reply = _build_adk_reply(
                            settings,
                            message=body.message.strip(),
                            context=context,
                            session_id=session_id,
                            user_id=user_id,
                            history=history,
                            runtime_settings=runtime_settings,
                        )
                        trace["status_code"] = HTTPStatus.OK
                        trace["source"] = reply.get("source")
                        trace["adk_unavailable"] = reply.get("source") == "adk_unavailable"
                        self._write_json(
                            HTTPStatus.OK,
                            ChatResponse(**reply, request_id=request_id),
                        )
                        return

                    if parsed.path == "/api/accounts/sync":
                        body = SyncAccountRequest.model_validate(self._read_json_body())
                        profile_payload = body.profile
                        candidate = None
                        if isinstance(profile_payload, dict) and profile_payload.get("account_id") is not None:
                            candidate = AccountCandidate(
                                account_id=int(profile_payload["account_id"]),
                                persona_name=str(profile_payload.get("persona_name") or profile_payload.get("personaname") or f"Account {profile_payload['account_id']}"),
                                profile_url=profile_payload.get("profile_url"),
                                avatar_url=profile_payload.get("avatar_url"),
                                country_code=profile_payload.get("country_code"),
                                matches_played_last_30d=profile_payload.get("matches_played_last_30d"),
                                last_team_avg_badge=profile_payload.get("last_team_avg_badge"),
                            )

                        result = sync_account(
                            settings,
                            body.account_id,
                            hydrate_matches=int(body.hydrate_matches or DEFAULT_HYDRATE_MATCHES),
                            candidate=candidate,
                        )
                        accounts = list_tracked_accounts(settings)
                        trace["status_code"] = HTTPStatus.OK
                        trace["account_count"] = len(accounts)
                        self._write_json(
                            HTTPStatus.OK,
                            {
                                **result,
                                "accounts": accounts,
                                "request_id": request_id,
                            },
                        )
                        return

                    if parsed.path == "/api/summary":
                        body = SummaryRequest.model_validate(self._read_json_body())
                        context = parse_context(body.context.model_dump())
                        if context.account_id is None:
                            raise ValueError("`context.account_id` is required.")

                        summary_payload = build_workspace_summary(
                            settings,
                            account_id=context.account_id,
                            window_matches=context.window_matches,
                        )
                        summary_payload["request_id"] = request_id
                        trace["status_code"] = HTTPStatus.OK
                        trace["has_account_summary"] = summary_payload.get("account_summary") is not None
                        self._write_json(HTTPStatus.OK, summary_payload)
                        return

                    trace["status_code"] = HTTPStatus.NOT_FOUND
                    self._write_error(HTTPStatus.NOT_FOUND, f"Unknown route: {parsed.path}", request_id=request_id)
            except ValueError as exc:
                self._write_error(HTTPStatus.BAD_REQUEST, str(exc), request_id=request_id)
            except ValidationError as exc:
                self._write_error(HTTPStatus.BAD_REQUEST, exc.errors()[0]["msg"], request_id=request_id)
            except Exception as exc:  # pragma: no cover - defensive API boundary
                emit_event(settings, "api.post.unhandled_error", request_id=request_id, route=parsed.path, error=str(exc))
                self._write_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc), request_id=request_id)

    return Handler


def serve(settings: Settings, host: str = "127.0.0.1", port: int = 3000) -> None:
    server = DeadlockCoachApiServer((host, port), settings)
    print(f"Deadlock Coach API listening on http://{host}:{server.server_port}")
    print(
        "Available routes: GET /api/health, GET /api/accounts, GET /api/account-search, GET /api/recent-matches, "
        "GET|POST /api/summary, POST /api/chat, POST /api/adk/chat, POST /api/accounts/sync"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Deadlock Coach API...")
    finally:
        server.server_close()
