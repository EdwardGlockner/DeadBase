from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EndpointSpec:
    name: str
    path: str
    method: str
    support: str
    purpose: str
    notes: str


@dataclass(frozen=True)
class FeatureSupport:
    feature: str
    support: str
    summary: str


@dataclass(frozen=True)
class ArtifactSpec:
    artifact_type: str
    label: str
    primary_inputs: tuple[str, ...]
    output_formats: tuple[str, ...]


ENDPOINTS = (
    EndpointSpec(
        name="patch_feed",
        path="/v2/patches",
        method="GET",
        support="full",
        purpose="Patch notes and patch-window anchoring.",
        notes="Unified forum plus Steam feed. Use local snapshots to create before/after patch comparisons.",
    ),
    EndpointSpec(
        name="player_match_history",
        path="/v1/players/{account_id}/match-history",
        method="GET",
        support="full",
        purpose="Player match history backbone for long-term coaching.",
        notes="Publicly useful today. Good for hero pool, result streaks, and longitudinal trend baselines.",
    ),
    EndpointSpec(
        name="match_metadata",
        path="/v1/matches/{match_id}/metadata",
        method="GET",
        support="full",
        purpose="Per-match roster context, item purchases, death details, and stat buckets.",
        notes="Critical for power-spike timing, build branches, and richer coaching explanations.",
    ),
    EndpointSpec(
        name="hero_analytics",
        path="/v1/analytics/hero-stats",
        method="GET",
        support="full",
        purpose="Hero performance trends by time and cohort filters.",
        notes="Use with patch windows for meta shift forensics.",
    ),
    EndpointSpec(
        name="item_analytics",
        path="/v1/analytics/item-stats",
        method="GET",
        support="full",
        purpose="Item-level performance and timing context.",
        notes="Good for stale-build detection and cohort comparisons.",
    ),
    EndpointSpec(
        name="item_flow_analytics",
        path="/v1/analytics/item-flow-stats",
        method="GET",
        support="full",
        purpose="Build branch and transition analysis.",
        notes="Useful for Pro Mirror and build experiment reporting.",
    ),
    EndpointSpec(
        name="ability_order_analytics",
        path="/v1/analytics/ability-order-stats",
        method="GET",
        support="full",
        purpose="Skill order and progression baselines.",
        notes="Lets the coach flag outdated upgrade orders after balance changes.",
    ),
    EndpointSpec(
        name="leaderboard",
        path="/v1/leaderboard/{region}",
        method="GET",
        support="partial",
        purpose="High-MMR cohort discovery.",
        notes="Exposes candidate account IDs, but account resolution may need confidence scoring.",
    ),
    EndpointSpec(
        name="build_search",
        path="/v1/builds",
        method="GET",
        support="partial",
        purpose="Public build ecosystem reference.",
        notes="Helpful context, but not a replacement for real match-derived build behavior.",
    ),
    EndpointSpec(
        name="account_stats",
        path="/v1/players/{account_id}/account-stats",
        method="GET",
        support="partial",
        purpose="Additional player stats for some accounts.",
        notes="Bot-friend and Patreon gated, so this cannot be assumed in the core product flow.",
    ),
    EndpointSpec(
        name="sql_catalog",
        path="/v1/sql/tables",
        method="GET",
        support="partial",
        purpose="Schema discovery and offline-analysis hints.",
        notes="Useful for future adapters and warehouse planning, but heavily rate limited.",
    ),
    EndpointSpec(
        name="database_dumps",
        path="https://deadlock-api.com/data-dumps",
        method="GET",
        support="partial",
        purpose="Bulk offline analysis and backfill path.",
        notes="Strong future adapter target once we need broader backfills or deeper historical coverage.",
    ),
)


FEATURE_SUPPORT = (
    FeatureSupport(
        feature="personal_player_model",
        support="partial",
        summary="Telemetry is available, but durable goals, preferences, and leak tracking are local product memory.",
    ),
    FeatureSupport(
        feature="pro_high_mmr_build_comparator",
        support="partial",
        summary="Buildable today from leaderboard, match history, and metadata, with local cohort logic.",
    ),
    FeatureSupport(
        feature="meta_shift_forensics",
        support="partial",
        summary="Patch notes and analytics are available, but patch-aware baselining must be built locally.",
    ),
    FeatureSupport(
        feature="recommendation_engine",
        support="partial",
        summary="Upstream provides evidence, not the synthesis, prioritization, or coaching explanations.",
    ),
    FeatureSupport(
        feature="hero_lab",
        support="full_app_side",
        summary="Enough public data exists now to produce a strong first version once we model it locally.",
    ),
    FeatureSupport(
        feature="patch_adaptation_report",
        support="full_app_side",
        summary="Requires local patch snapshotting and before/after comparisons, not new upstream endpoints.",
    ),
    FeatureSupport(
        feature="build_experiment_tracker",
        support="full_app_side",
        summary="Needs local experiment memory linked to later matches.",
    ),
)


ARTIFACTS = (
    ArtifactSpec(
        artifact_type="weekly-coaching-report",
        label="Coaching Brief",
        primary_inputs=("player_match_history", "match_metadata", "player_memory"),
        output_formats=("md", "json"),
    ),
    ArtifactSpec(
        artifact_type="hero-dossier",
        label="Hero Dossier",
        primary_inputs=("player_match_history", "match_metadata", "hero_analytics", "item_analytics"),
        output_formats=("md", "json"),
    ),
    ArtifactSpec(
        artifact_type="patch-adaptation-report",
        label="Patch Adaptation Report",
        primary_inputs=("patch_feed", "hero_analytics", "item_analytics", "player_memory"),
        output_formats=("md", "json"),
    ),
    ArtifactSpec(
        artifact_type="pro-mirror-report",
        label="Pro Mirror Report",
        primary_inputs=("leaderboard", "match_metadata", "item_flow_analytics"),
        output_formats=("md", "json"),
    ),
    ArtifactSpec(
        artifact_type="build-experiment-report",
        label="Build Experiment Report",
        primary_inputs=("player_match_history", "match_metadata", "player_memory"),
        output_formats=("md", "json"),
    ),
    ArtifactSpec(
        artifact_type="next-five-games-plan",
        label="Next 5 Games Plan",
        primary_inputs=("player_match_history", "patch_feed", "player_memory"),
        output_formats=("md", "json"),
    ),
)


def inspect_data_surface() -> dict[str, object]:
    return {
        "audit_date": "2026-07-07",
        "endpoints": [asdict(item) for item in ENDPOINTS],
        "feature_support": [asdict(item) for item in FEATURE_SUPPORT],
    }


def list_artifacts() -> list[dict[str, object]]:
    return [asdict(item) for item in ARTIFACTS]
