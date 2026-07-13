from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from deadlock_coach.account_service import DEFAULT_HYDRATE_MATCHES
from deadlock_coach.agent_contracts import CoachAnswer, ConfidenceReport, EvidenceRef, StructuredCoachOutput, TraceReport
from deadlock_coach.coach_service import DEFAULT_WINDOW_MATCHES


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class CoachContextPayload(ApiModel):
    account_id: int | None = None
    hero_id: int | None = None
    hero_name: str | None = None
    player_label: str | None = None
    window_matches: int | None = DEFAULT_WINDOW_MATCHES


class ChatHistoryTurn(ApiModel):
    role: Literal["user", "assistant"]
    text: str = ""
    insight: str | None = None
    confidence: ConfidenceReport | None = None


class RuntimeSettingsPayload(ApiModel):
    provider: Literal["openai", "gemini_api", "litellm_proxy"] | None = None
    model: str | None = None
    api_key: str | None = None


class RuntimeSettingsBootstrapResponse(ApiModel):
    provider: Literal["openai", "gemini_api", "litellm_proxy"] | None = None
    model: str | None = None
    api_key: str | None = None


class ChatRequest(ApiModel):
    message: str = Field(min_length=1)
    context: CoachContextPayload | None = None
    history: list[ChatHistoryTurn] | None = None
    session_id: str | None = None
    user_id: str | None = None
    runtime_settings: RuntimeSettingsPayload | None = None


class SummaryRequest(ApiModel):
    context: CoachContextPayload


class AccountSearchResponse(ApiModel):
    query: str
    results: list[dict[str, Any]]


class AccountsResponse(ApiModel):
    accounts: list[dict[str, Any]]


class RecentMatchesResponse(ApiModel):
    account_id: int
    window_matches: int
    matches: list[dict[str, Any]]
    request_id: str | None = None


class HealthResponse(ApiModel):
    status: Literal["ok"]
    service: str
    request_id: str | None = None


class TelemetryEventsResponse(ApiModel):
    events: list[dict[str, Any]] = Field(default_factory=list)
    request_id: str | None = None


class ErrorResponse(ApiModel):
    error: str
    request_id: str | None = None


class ChatResponse(ApiModel):
    insight: str = ""
    reply: str
    coach_answer: CoachAnswer | None = None
    evidence: list[str] = Field(default_factory=list)
    confidence: ConfidenceReport | None = None
    evidence_graph: list[EvidenceRef] = Field(default_factory=list)
    structured_output: StructuredCoachOutput | None = None
    trace: TraceReport | None = None
    source: str
    session_id: str | None = None
    unavailable_reason: str | None = None
    summary: dict[str, Any] | None = None
    context: dict[str, Any] | None = None
    debug: dict[str, Any] | None = None
    request_id: str | None = None


class SyncAccountRequest(ApiModel):
    account_id: int
    hydrate_matches: int | None = DEFAULT_HYDRATE_MATCHES
    profile: dict[str, Any] | None = None
