from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


ConfidenceLevel = Literal["high", "medium", "low"]
CoachAnswerType = Literal["general", "build", "hero_pool", "matchup", "comparison", "practice", "experiment", "knowledge", "utility"]
AnalystLane = Literal["coach", "data", "knowledge", "matchup", "practice"]
EvidenceSourceType = Literal[
    "player_telemetry",
    "knowledge_base",
    "wiki_reference",
    "patch_feed",
    "external_stats",
    "agent_inference",
]
SpecialistName = Literal[
    "coach_agent",
]


class EvidenceRef(ContractModel):
    evidence_id: str
    source_type: EvidenceSourceType
    label: str
    detail: str
    reference: str | None = None
    trust: ConfidenceLevel = "medium"


class ConfidenceReport(ContractModel):
    level: ConfidenceLevel
    score: float = Field(ge=0.0, le=1.0)
    rationale: str


class HeroPerformanceLine(ContractModel):
    hero_label: str
    games: int = Field(ge=0)
    wins: int = Field(ge=0)
    win_rate: float = Field(ge=0.0, le=100.0)


class HeroPoolDiagnosis(ContractModel):
    focus_hero: str | None = None
    reliable_hero: str | None = None
    pool_shape: Literal["narrow", "balanced", "wide", "unknown"] = "unknown"
    summary: str
    next_step: str
    top_heroes: list[HeroPerformanceLine] = Field(default_factory=list)


class BuildTimingAudit(ContractModel):
    focus_item: str | None = None
    build_spine: list[str] = Field(default_factory=list)
    timing_assessment: str
    branch_signal: str
    recommended_adjustment: str


class CoachBuildBranch(ContractModel):
    late_items: list[str] = Field(default_factory=list)
    t4_finishers: list[str] = Field(default_factory=list)


class CoachBuildAnswer(ContractModel):
    hero_name: str | None = None
    lane_early: list[str] = Field(default_factory=list)
    mid_game: list[str] = Field(default_factory=list)
    stable_core: list[str] = Field(default_factory=list)
    late_items: list[str] = Field(default_factory=list)
    t4_finishers: list[str] = Field(default_factory=list)
    flex_items: list[str] = Field(default_factory=list)
    late_branches: list[CoachBuildBranch] = Field(default_factory=list)


class CoachAnswer(ContractModel):
    answer_type: CoachAnswerType
    headline: str
    supporting_points: list[str] = Field(default_factory=list)
    next_step: str | None = None
    caveat: str | None = None
    build: CoachBuildAnswer | None = None


class ComparisonAssessment(ContractModel):
    comparison_scope: Literal["player_vs_meta", "player_vs_rank", "player_vs_pattern", "global_meta"] = "global_meta"
    subject: str
    summary: str
    player_anchor: str | None = None
    external_anchor: str | None = None
    takeaway: str
    caveat: str | None = None


class MatchupAssessment(ContractModel):
    status: Literal["ready", "limited", "unavailable"] = "limited"
    summary: str
    next_step: str
    limitation: str | None = None


class PracticePlan(ContractModel):
    focus_area: str
    rationale: str
    drills: list[str] = Field(default_factory=list)


class ExperimentPlan(ContractModel):
    hypothesis: str
    success_metric: str
    sample_size_target: int = Field(ge=1)
    current_result: str
    next_action: Literal["keep", "stop", "revise", "start"]


class VodReviewPlan(ContractModel):
    review_target: str
    checkpoints: list[str] = Field(default_factory=list)
    success_criteria: str


class ArtifactSection(ContractModel):
    heading: str
    summary: str
    bullets: list[str] = Field(default_factory=list)


class ArtifactOutline(ContractModel):
    artifact_type: Literal["weekly_report", "build_audit", "hero_pool_review", "experiment_summary", "patch_adaptation_memo"]
    title: str
    sections: list[ArtifactSection] = Field(default_factory=list)


class InformationNeed(ContractModel):
    family: str
    scope: Literal["player_specific", "global", "knowledge", "mixed", "general"]
    subject: Literal["build", "hero_pool", "meta", "patch", "matchup", "concept", "practice", "progress", "experiment", "general"]
    reasoning_mode: Literal["answer", "clarify", "coach"] = "answer"
    prefers_full_history: bool = False
    needs_player_telemetry: bool = False
    needs_global_analytics: bool = False
    needs_knowledge_base: bool = False
    needs_patch_context: bool = False
    needs_matchup_context: bool = False


class CapabilityMatch(ContractModel):
    capability: str
    analyst_lane: AnalystLane
    priority: int = Field(ge=1, le=5)
    rationale: str


class RoutingDecision(ContractModel):
    family: str
    specialists: list[SpecialistName] = Field(default_factory=list)
    analyst_lanes: list[AnalystLane] = Field(default_factory=list)
    tool_hints: list[str] = Field(default_factory=list)
    information_need: InformationNeed | None = None
    capability_matches: list[CapabilityMatch] = Field(default_factory=list)
    rationale: str


class TraceStep(ContractModel):
    name: str
    kind: Literal["route", "retrieval", "synthesis"]
    status: Literal["ok", "limited", "skipped", "error"] = "ok"
    duration_ms: float = Field(ge=0.0)
    detail: str = ""
    tool_calls: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class TraceReport(ContractModel):
    selected_specialists: list[SpecialistName] = Field(default_factory=list)
    steps: list[TraceStep] = Field(default_factory=list)
    total_duration_ms: float = Field(ge=0.0)


class StructuredCoachOutput(ContractModel):
    routing: RoutingDecision
    comparison: ComparisonAssessment | None = None
    hero_pool: HeroPoolDiagnosis | None = None
    build_timing: BuildTimingAudit | None = None
    matchup: MatchupAssessment | None = None
    practice_plan: PracticePlan | None = None
    experiment_plan: ExperimentPlan | None = None
    vod_review: VodReviewPlan | None = None
    artifact_outline: ArtifactOutline | None = None


class CoachResponseEnvelope(ContractModel):
    confidence: ConfidenceReport
    evidence_graph: list[EvidenceRef] = Field(default_factory=list)
    structured_output: StructuredCoachOutput
    trace: TraceReport
