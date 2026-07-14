from __future__ import annotations

from pathlib import Path
import sqlite3
from time import perf_counter
from typing import Any
from contextlib import closing

from deadlock_coach.agent_contracts import (
    ArtifactOutline,
    ArtifactSection,
    BuildTimingAudit,
    ComparisonAssessment,
    CoachAnswer,
    CoachResponseEnvelope,
    ConfidenceReport,
    EvidenceRef,
    ExperimentPlan,
    HeroPerformanceLine,
    HeroPoolDiagnosis,
    MatchupAssessment,
    PracticePlan,
    StructuredCoachOutput,
    TraceReport,
    TraceStep,
    VodReviewPlan,
    RoutingDecision,
)
from deadlock_coach.asset_service import detect_hero_name_in_text, hero_label, item_label
from deadlock_coach.coach_service import (
    _build_walkthrough,
    _build_walkthrough_from_paths,
    CoachContext,
    _build_spine_labels,
    _describe_branch_from_paths,
    _format_time_seconds,
    _format_item_phase_summary,
    _item_phase_label,
    _knowledge_matches,
    _knowledge_matches_for_queries,
    _load_recent_matches,
    _match_hero_from_message,
    _recent_item_paths_payload,
    _resolved_record_text,
    _summary_outcome_evidence,
    _top_reliable_hero,
    _top_sample_hero,
    list_tracked_accounts,
    summarize_account,
)
from deadlock_coach.config import Settings
from deadlock_coach.knowledge_base import knowledge_content_lines, retrieve_grounded_knowledge_context
from deadlock_coach.message_hints import effective_knowledge_query
from deadlock_coach.semantic_router import build_routing_decision


def _slugify(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")


def _knowledge_excerpt(path: Path) -> str:
    body = path.read_text(encoding="utf-8")
    lines = knowledge_content_lines(body)
    return " ".join(lines[:5]).strip()


def _knowledge_path(settings: Settings, group: str, title: str, *, imported: bool = False) -> Path | None:
    slug = _slugify(title)
    if imported:
        candidate = settings.project_root / "docs" / "knowledge" / "_imports" / "wiki" / group / f"{slug}.md"
    else:
        candidate = settings.project_root / "docs" / "knowledge" / group / f"{slug}.md"
    return candidate if candidate.exists() else None


def _knowledge_note(settings: Settings, relative_path: str) -> Path | None:
    candidate = settings.project_root / relative_path
    return candidate if candidate.exists() else None


def _knowledge_queries(
    message: str,
    *,
    history: list[dict[str, object]] | None = None,
    focus_hero_name: str | None = None,
    item_labels: list[str] | None = None,
) -> list[str]:
    base_query = effective_knowledge_query(message, history)
    trimmed_labels = [label for label in list(item_labels or []) if label][:3]
    queries = [base_query]
    if focus_hero_name:
        queries.append(" ".join([base_query, focus_hero_name]).strip())
    if trimmed_labels:
        queries.append(" ".join([base_query, *trimmed_labels]).strip())
    if focus_hero_name and trimmed_labels:
        queries.append(" ".join([base_query, focus_hero_name, *trimmed_labels]).strip())
    return [query for index, query in enumerate(queries) if query and query not in queries[:index]]


def _knowledge_group_filters(family: str) -> list[str] | None:
    filters_by_family = {
        "timing": ["builds", "fundamentals", "glossary", "heroes", "items"],
        "patches": ["patches", "fundamentals", "heroes", "items"],
        "meta": ["patches", "fundamentals", "heroes", "items"],
        "mirror": ["heroes", "items", "fundamentals", "matchups"],
        "matchups": ["matchups", "heroes", "fundamentals"],
        "hero_review": ["heroes", "fundamentals", "builds"],
        "global_popularity": ["patches", "heroes", "fundamentals"],
    }
    return filters_by_family.get(family)


def _summary_window(
    settings: Settings,
    account_id: int | None,
    family: str,
    *,
    prefers_full_history: bool,
    default_window: int,
) -> int:
    if account_id is None:
        return default_window
    if family not in {"hero_overview", "reliable_hero", "winrate"}:
        return default_window
    if not prefers_full_history:
        return default_window

    for account in list_tracked_accounts(settings):
        if int(account.get("account_id") or 0) == account_id:
            return max(int(account.get("matches") or 0), default_window)
    return default_window


def _patch_queries(
    message: str,
    *,
    history: list[dict[str, object]] | None = None,
    focus_hero_name: str | None = None,
) -> list[str]:
    queries: list[str] = []
    if focus_hero_name:
        queries.append(focus_hero_name.strip())
    normalized = effective_knowledge_query(message, history).strip()
    if normalized:
        queries.append(normalized)
    queries.append("")
    deduped: list[str] = []
    for query in queries:
        if query in deduped:
            continue
        deduped.append(query)
    return deduped


def _resolved_focus_hero_name(settings: Settings, message: str, context: CoachContext) -> str | None:
    explicit_hero_name = detect_hero_name_in_text(settings, message)
    if explicit_hero_name:
        return explicit_hero_name
    return context.hero_name


def _patch_matches(settings: Settings, queries: list[str], *, limit: int = 2) -> list[dict[str, str]]:
    if not settings.warehouse_db_path.exists():
        return []

    with closing(sqlite3.connect(settings.warehouse_db_path)) as connection:
        connection.row_factory = sqlite3.Row
        for query in queries:
            normalized_limit = max(1, min(limit, 5))
            if query.strip():
                pattern = f"%{query.lower()}%"
                rows = connection.execute(
                    """
                    SELECT title, published_at, link, content_excerpt
                    FROM patch_event
                    WHERE lower(title) LIKE ?
                       OR lower(coalesce(content_excerpt, '')) LIKE ?
                    ORDER BY published_at DESC, title ASC
                    LIMIT ?
                    """,
                    (pattern, pattern, normalized_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT title, published_at, link, content_excerpt
                    FROM patch_event
                    ORDER BY published_at DESC, title ASC
                    LIMIT ?
                    """,
                    (normalized_limit,),
                ).fetchall()
            if not rows:
                continue
            return [
                {
                    "title": str(row["title"] or "Untitled Patch"),
                    "published_at": str(row["published_at"] or ""),
                    "link": str(row["link"] or ""),
                    "excerpt": " ".join(str(row["content_excerpt"] or "").split()),
                }
                for row in rows
            ]
    return []


def _confidence(
    summary: Any,
    evidence_graph: list[EvidenceRef],
    *,
    player_summary_expected: bool,
    routing: RoutingDecision,
) -> ConfidenceReport:
    player_evidence = [item for item in evidence_graph if item.source_type == "player_telemetry"]
    reference_evidence = [
        item
        for item in evidence_graph
        if item.source_type in {"knowledge_base", "wiki_reference", "patch_feed", "external_stats"}
    ]
    if summary is None:
        if not player_summary_expected and (
            reference_evidence
            or (
                routing.information_need is not None
                and routing.information_need.scope in {"knowledge", "global"}
            )
            or routing.family in {"patches", "meta", "global_popularity"}
        ):
            return ConfidenceReport(
                level="medium",
                score=0.7,
                rationale="The answer is grounded in reference or global data rather than a local player sample.",
            )
        return ConfidenceReport(
            level="low",
            score=0.24 if reference_evidence else 0.12,
            rationale="No synced player sample is available, so the answer can only lean on reference material and inference.",
        )

    if (
        summary.total_matches >= 8
        and summary.hydrated_match_count >= 1
        and summary.resolved_outcome_matches >= 5
        and len(player_evidence) >= 3
    ):
        return ConfidenceReport(
            level="high",
            score=0.88,
            rationale="Recent player-specific data is available with multiple telemetry signals and at least one hydrated match.",
        )
    if summary.total_matches >= 4 and len(player_evidence) >= 2:
        return ConfidenceReport(
            level="medium",
            score=0.63,
            rationale="There is enough local player evidence to guide the answer, but the sample is still narrow or only partly hydrated.",
        )
    return ConfidenceReport(
        level="low",
        score=0.34,
        rationale="The local player sample is too thin for strong coaching confidence, so the answer should be treated as directional.",
    )


def build_evidence_bullets(envelope: CoachResponseEnvelope, limit: int = 4) -> list[str]:
    return [item.detail for item in envelope.evidence_graph[: max(1, limit)]]


def _coach_answer_type_for_family(family: str, source: str) -> str:
    if source == "utility":
        return "utility"
    mapping = {
        "timing": "build",
        "patches": "knowledge",
        "meta": "comparison",
        "hero_overview": "hero_pool",
        "reliable_hero": "hero_pool",
        "winrate": "hero_pool",
        "hero_review": "hero_pool",
        "focus": "practice",
        "progress": "practice",
        "experiment": "experiment",
        "matchups": "matchup",
        "mirror": "comparison",
        "global_popularity": "comparison",
        "greeting": "general",
        "clarify": "general",
    }
    return mapping.get(family, "knowledge" if source == "knowledge_base" else "general")


def _coach_answer_next_step(envelope: CoachResponseEnvelope) -> str | None:
    structured = envelope.structured_output
    family = structured.routing.family
    if family not in {"focus", "progress", "experiment"}:
        return None
    if structured.practice_plan is not None:
        return structured.practice_plan.rationale
    if structured.experiment_plan is not None:
        return structured.experiment_plan.hypothesis
    if structured.hero_pool is not None:
        return structured.hero_pool.next_step
    if structured.matchup is not None:
        return structured.matchup.next_step
    if structured.build_timing is not None:
        return structured.build_timing.recommended_adjustment
    if structured.vod_review is not None:
        return structured.vod_review.success_criteria
    return None


def _coach_answer_from_reply(reply: dict[str, Any], envelope: CoachResponseEnvelope) -> CoachAnswer:
    family = envelope.structured_output.routing.family
    source = str(reply.get("source") or "")
    draft = reply.pop("_coach_answer", None)
    if draft is not None:
        if isinstance(draft, CoachAnswer):
            return draft
        return CoachAnswer.model_validate(draft)

    headline = str(reply.get("reply") or "").strip() or "No reply returned."
    player_specific = envelope.structured_output.routing.information_need is not None and (
        envelope.structured_output.routing.information_need.scope == "player_specific"
    )
    caveat = envelope.confidence.rationale if envelope.confidence.level == "low" and player_specific else None
    return CoachAnswer(
        answer_type=_coach_answer_type_for_family(family, source),
        headline=headline,
        supporting_points=[],
        next_step=_coach_answer_next_step(envelope),
        caveat=caveat,
    )


def build_prompt_support(envelope: CoachResponseEnvelope) -> str:
    family = envelope.structured_output.routing.family
    information_need = envelope.structured_output.routing.information_need
    lines = [
        "Backend context and guardrails:",
        f"- Question family hint: {family}",
    ]
    if information_need is not None:
        lines.append(
            f"- Information need: subject={information_need.subject}, scope={information_need.scope}, mode={information_need.reasoning_mode}"
        )
    if envelope.structured_output.routing.analyst_lanes:
        lines.append(f"- Suggested internal lanes: {', '.join(envelope.structured_output.routing.analyst_lanes)}")
    if envelope.structured_output.routing.tool_hints:
        lines.append(f"- Suggested tool lanes: {', '.join(envelope.structured_output.routing.tool_hints)}")
    if envelope.confidence.level == "low" and (
        information_need is None or information_need.scope == "player_specific"
    ):
        lines.append(f"- Evidence is thin: {envelope.confidence.rationale}")

    has_player_telemetry = any(item.source_type == "player_telemetry" for item in envelope.evidence_graph)
    has_kb_support = any(item.source_type in {"knowledge_base", "wiki_reference"} for item in envelope.evidence_graph)
    if has_player_telemetry:
        lines.append("- Local player telemetry exists. Use tools for exact stats instead of paraphrasing this block.")
    if has_kb_support:
        lines.append("- Relevant local KB or imported reference support exists. Look it up directly before answering theory questions.")
    if family == "timing" and "global_item_flow" in envelope.structured_output.routing.tool_hints:
        lines.append("- For pro, top-player, or high-MMR build questions, prefer the strongest grounded rank-scoped build-flow proxy first, usually Eternus 6 when available.")
    if family == "timing":
        lines.append("- Keep build-phase language focused on lane/early, mid, and late. If the user asked for T4s, name only verified T4 finishers.")
    if family in {"patches", "meta", "global_popularity"}:
        lines.append("- For global or rank-scoped meta questions, answer the exact requested scope first and avoid padding with unrelated local-player alternatives.")

    lines.append("- This block is only context, not a finished answer.")
    lines.append("Answer the user's question directly. Prefer tool use over repeating backend summaries. Do not mention internal routing, JSON, or backend orchestration.")
    return "\n".join(lines)


def build_response_envelope(
    settings: Settings,
    message: str,
    context: CoachContext,
    history: list[dict[str, object]] | None = None,
) -> CoachResponseEnvelope:
    started = perf_counter()
    evidence_graph: list[EvidenceRef] = []
    steps: list[TraceStep] = []

    def add_evidence(source_type: str, label: str, detail: str, *, reference: str | None = None, trust: str = "medium") -> str:
        evidence_id = f"ev_{len(evidence_graph) + 1}"
        evidence_graph.append(
            EvidenceRef(
                evidence_id=evidence_id,
                source_type=source_type,  # type: ignore[arg-type]
                label=label,
                detail=detail,
                reference=reference,
                trust=trust,  # type: ignore[arg-type]
            )
        )
        return evidence_id

    route_started = perf_counter()
    routing = build_routing_decision(message, has_account=context.account_id is not None, history=history)
    family = routing.family
    requested_hero_name = _resolved_focus_hero_name(settings, message, context)
    needs_player_summary = bool(
        context.account_id is not None
        and (
            family == "clarify"
            or (routing.information_need is not None and routing.information_need.needs_player_telemetry)
        )
    )
    window_matches = _summary_window(
        settings,
        context.account_id,
        family,
        prefers_full_history=bool(routing.information_need and routing.information_need.prefers_full_history),
        default_window=context.window_matches,
    )
    summary = summarize_account(settings, context.account_id, window_matches) if needs_player_summary and context.account_id is not None else None
    if needs_player_summary and summary is None and context.account_id is not None:
        routing = build_routing_decision(message, has_account=False, history=history)
    steps.append(
        TraceStep(
                name="route_request",
                kind="route",
                duration_ms=round((perf_counter() - route_started) * 1000, 2),
                detail=(
                    f"Message family `{family}` will be handled by coach_agent"
                    + (
                        f" using {', '.join(routing.tool_hints)}"
                        + (
                            f" through {', '.join(routing.analyst_lanes)} lanes."
                            if routing.analyst_lanes
                            else "."
                        )
                        if routing.tool_hints
                        else " without extra tool hints."
                    )
                ),
            )
        )

    hero_pool: HeroPoolDiagnosis | None = None
    comparison: ComparisonAssessment | None = None
    build_timing: BuildTimingAudit | None = None
    matchup: MatchupAssessment | None = None
    practice_plan: PracticePlan | None = None
    experiment_plan: ExperimentPlan | None = None
    vod_review: VodReviewPlan | None = None
    artifact_outline: ArtifactOutline | None = None

    if summary is not None:
        player_step_started = perf_counter()
        top_hero = _top_sample_hero(summary)
        top_item = summary.item_timings[0] if summary.item_timings else None
        player_evidence_ids = [
            add_evidence(
                "player_telemetry",
                "Recent sample",
                f"{summary.total_matches} tracked matches are available in the current local window.",
                trust="high" if summary.total_matches >= 8 else "medium",
            ),
            add_evidence(
                "player_telemetry",
                "KDA line",
                f"Average K/D/A is {summary.avg_kills:.1f}/{summary.avg_deaths:.1f}/{summary.avg_assists:.1f}.",
                trust="medium",
            ),
        ]
        for outcome_detail in _summary_outcome_evidence(summary):
            player_evidence_ids.append(
                add_evidence(
                    "player_telemetry",
                    "Outcome coverage",
                    outcome_detail,
                    trust="medium",
                )
            )
        if top_hero is not None:
            player_evidence_ids.append(
                add_evidence(
                    "player_telemetry",
                    "Top hero",
                    (
                        f"{hero_label(settings, top_hero.hero_id)} leads the recent sample with {top_hero.games} games and a {_resolved_record_text(top_hero.wins, top_hero.resolved_games)}."
                        if top_hero.resolved_games > 0
                        else f"{hero_label(settings, top_hero.hero_id)} leads the recent sample with {top_hero.games} games, but verified outcomes are still thin."
                    ),
                    trust="high" if top_hero.games >= 4 else "medium",
                )
            )
        if top_item is not None:
            player_evidence_ids.append(
                add_evidence(
                    "player_telemetry",
                    "Recurring item",
                    f"{item_label(settings, top_item.item_id)} is showing up repeatedly in the {_item_phase_label(top_item.avg_bought_at_s)} game.",
                    trust="medium",
                )
            )

        steps.append(
            TraceStep(
                name="load_player_summary",
                kind="retrieval",
                duration_ms=round((perf_counter() - player_step_started) * 1000, 2),
                detail="Loaded the recent player summary and the strongest repeat hero/item signals.",
                tool_calls=["summarize_account"],
                evidence_ids=player_evidence_ids,
            )
        )

    if "knowledge_base_lookup" in routing.tool_hints:
        knowledge_step_started = perf_counter()
        evidence_queries = _knowledge_queries(
            message,
            history=history,
            focus_hero_name=requested_hero_name,
            item_labels=[item_label(settings, row.item_id) for row in summary.item_timings[:2]] if summary is not None and family == "timing" else None,
        )
        group_filters = _knowledge_group_filters(family)
        retrieval = None
        knowledge_evidence_ids: list[str] = []
        for evidence_query in evidence_queries:
            retrieval = retrieve_grounded_knowledge_context(
                settings,
                evidence_query,
                limit=3,
                group_filters=group_filters,
            )
            if retrieval.get("fact") or retrieval.get("matches"):
                break
        if retrieval is not None and retrieval.get("fact") and retrieval.get("fact_source") is not None:
            fact_source = retrieval["fact_source"]
            knowledge_evidence_ids.append(
                add_evidence(
                "wiki_reference",
                f"{fact_source['section_title']} table",
                str(retrieval["fact"]),
                reference=str(fact_source["relative_path"]),
                trust="high",
            )
            )
        concept_matches = [] if retrieval is None else list(retrieval.get("matches", []))
        if not concept_matches:
            concept_matches = _knowledge_matches_for_queries(
                settings,
                evidence_queries,
                limit=2,
                group_filters=group_filters,
            )
            if not concept_matches and group_filters is not None:
                concept_matches = _knowledge_matches_for_queries(settings, evidence_queries, limit=2)
        for match in concept_matches[:2]:
            knowledge_evidence_ids.append(
                add_evidence(
                    "wiki_reference" if match["imported"] else "knowledge_base",
                    f"{match['title']} note",
                    match["excerpt"],
                    reference=match["relative_path"],
                    trust="high",
                )
            )
        retrieval_summary = (
            str(retrieval.get("summary") or "").strip()
            if retrieval is not None
            else "No grounded knowledge match found."
        )
        steps.append(
            TraceStep(
                name="knowledge_retrieval",
                kind="retrieval",
                status="ok" if knowledge_evidence_ids else "limited",
                duration_ms=round((perf_counter() - knowledge_step_started) * 1000, 2),
                detail=retrieval_summary or "No grounded knowledge match found.",
                tool_calls=["retrieve_game_knowledge"],
                evidence_ids=knowledge_evidence_ids,
            )
        )

    if "patch_context" in routing.tool_hints:
        patch_step_started = perf_counter()
        patch_evidence_ids: list[str] = []
        patch_matches = _patch_matches(
            settings,
            _patch_queries(message, history=history, focus_hero_name=requested_hero_name),
            limit=2,
        )
        for match in patch_matches:
            published_label = match["published_at"][:10] if match["published_at"] else "unknown date"
            detail = (
                f"{match['title']} ({published_label}): {match['excerpt']}"
                if match["excerpt"]
                else f"{match['title']} ({published_label})."
            )
            patch_evidence_ids.append(
                add_evidence(
                    "patch_feed",
                    "Patch note",
                    detail,
                    reference=match["link"] or None,
                    trust="high",
                )
            )
        steps.append(
            TraceStep(
                name="patch_context",
                kind="retrieval",
                status="ok" if patch_evidence_ids else "limited",
                duration_ms=round((perf_counter() - patch_step_started) * 1000, 2),
                detail=(
                    f"Loaded {len(patch_evidence_ids)} synced patch notes."
                    if patch_evidence_ids
                    else "No synced patch notes matched the request."
                ),
                tool_calls=["patch_event"],
                evidence_ids=patch_evidence_ids,
            )
        )

    if family in {"mirror", "global_popularity"} or (family == "meta" and "global_hero_stats" in routing.tool_hints):
        specialist_started = perf_counter()
        top_hero_name = hero_label(settings, summary.hero_performance[0].hero_id) if summary is not None and summary.hero_performance else None
        top_item_name = item_label(settings, summary.item_timings[0].item_id) if summary is not None and summary.item_timings else None
        information_need = routing.information_need
        if information_need is not None and information_need.scope == "global":
            comparison_scope = "global_meta"
        elif information_need is not None and any(rank in message.lower() for rank in ("eternus", "phantom", "ascendant", "oracle", "archon", "emissary", "ritualist", "arcanist", "alchemist", "seeker", "initiate", "obscurus")):
            comparison_scope = "player_vs_rank"
        elif summary is not None:
            comparison_scope = "player_vs_meta"
        else:
            comparison_scope = "global_meta"

        comparison = ComparisonAssessment(
            comparison_scope=comparison_scope,  # type: ignore[arg-type]
            subject=(
                "hero win-rate and popularity context"
                if family in {"global_popularity", "meta", "winrate"}
                else "player-vs-pattern comparison"
            ),
            summary=(
                f"Use {top_hero_name or 'the current hero or build'} as the local reference point, then compare it against broader hero, rank, or build context."
                if summary is not None and family == "mirror"
                else "Answer from broader global or rank-scoped context first, then only add the player side if the question actually asks for it."
            ),
            player_anchor=(
                f"Current local reference point: {top_hero_name}" + (f" with {top_item_name} as a repeated build checkpoint." if top_item_name else ".")
                if summary is not None
                else None
            ),
            external_anchor=(
                "Use global hero stats, item stats, item flow, and rank filters for the external side."
                if any(tool in routing.tool_hints for tool in {"global_hero_stats", "global_item_stats", "global_item_flow"})
                else "External comparison data is still thin, so keep the comparison narrow."
            ),
            takeaway=(
                "Lead with the mismatch or alignment between the local pattern and the broader context."
                if family == "mirror"
                else "Lead with the broader comparison result, then add local context only if it clarifies the answer."
            ),
            caveat=(
                "Pro-level mirror data is still thinner than the global hero and item context."
                if "comparison_context" in routing.tool_hints
                else None
            ),
        )
        steps.append(
            TraceStep(
                name="comparison_capability",
                kind="synthesis",
                duration_ms=round((perf_counter() - specialist_started) * 1000, 2),
                detail=comparison.summary,
                tool_calls=[tool for tool in routing.tool_hints if tool in {"comparison_context", "global_hero_stats", "global_item_stats", "global_item_flow"}],
            )
        )

    if "hero_pool_analysis" in routing.tool_hints and summary is not None:
        specialist_started = perf_counter()
        focus_hero = _match_hero_from_message(settings, summary, message, context) or _top_sample_hero(summary)
        reliable_hero = _top_reliable_hero(summary)
        top_heroes = [
            HeroPerformanceLine(
                hero_label=hero_label(settings, hero.hero_id),
                games=hero.games,
                wins=hero.wins,
                win_rate=hero.win_rate,
            )
            for hero in summary.hero_performance[:3]
        ]
        top_ratio = (focus_hero.games / summary.total_matches) if focus_hero and summary.total_matches else 0.0
        pool_shape = "narrow" if top_ratio >= 0.5 else "balanced" if top_ratio >= 0.34 else "wide"
        focus_hero_name = hero_label(settings, focus_hero.hero_id) if focus_hero else None
        hero_evidence_ids: list[str] = []
        if focus_hero_name:
            hero_evidence_ids.append(
                add_evidence(
                    "agent_inference",
                    "Hero diagnosis",
                    f"The current coaching read is centered on {focus_hero_name} because it owns the heaviest recent volume.",
                    trust="medium",
                )
            )
            curated_path = _knowledge_path(settings, "heroes", focus_hero_name)
            if curated_path is not None:
                hero_evidence_ids.append(
                    add_evidence(
                        "knowledge_base",
                        f"{focus_hero_name} coaching note",
                        _knowledge_excerpt(curated_path),
                        reference=str(curated_path.relative_to(settings.project_root)),
                        trust="medium",
                    )
                )
            imported_path = _knowledge_path(settings, "heroes", focus_hero_name, imported=True)
            if imported_path is not None:
                hero_evidence_ids.append(
                    add_evidence(
                        "wiki_reference",
                        f"{focus_hero_name} reference import",
                        _knowledge_excerpt(imported_path),
                        reference=str(imported_path.relative_to(settings.project_root)),
                        trust="low",
                    )
                )

        hero_pool = HeroPoolDiagnosis(
            focus_hero=focus_hero_name,
            reliable_hero=hero_label(settings, reliable_hero.hero_id) if reliable_hero else focus_hero_name,
            pool_shape=pool_shape,
            summary=(
                f"{focus_hero_name or 'The recent main hero'} is the clearest current read, "
                f"and the pool looks {pool_shape} across the active sample."
            ),
            next_step=(
                "Keep the pool narrow until timing and fight quality stabilize."
                if pool_shape in {"narrow", "balanced"}
                else "Reduce hero spread before changing multiple build branches at once."
            ),
            top_heroes=top_heroes,
        )
        steps.append(
            TraceStep(
                name="hero_pool_capability",
                kind="synthesis",
                duration_ms=round((perf_counter() - specialist_started) * 1000, 2),
                detail=hero_pool.summary,
                tool_calls=["hero_label", "_top_sample_hero"],
                evidence_ids=hero_evidence_ids,
            )
        )

    if "build_analysis" in routing.tool_hints and summary is not None:
        specialist_started = perf_counter()
        matched_hero = _match_hero_from_message(settings, summary, message, context)
        focus_hero_name = requested_hero_name or (hero_label(settings, matched_hero.hero_id) if matched_hero else None) or (hero_pool.focus_hero if hero_pool else None)
        recent_paths = _recent_item_paths_payload(
            settings,
            summary.account_id,
            hero_name=focus_hero_name,
            window_matches=20 if focus_hero_name else 8,
            items_per_match=16 if focus_hero_name else 5,
        )
        branch, branch_count = _describe_branch_from_paths(recent_paths)
        build_spine = branch or _build_spine_labels(settings, summary)
        top_item = summary.item_timings[0] if summary.item_timings else None
        focus_item_name = item_label(settings, top_item.item_id) if top_item else None
        phase_summary = _format_item_phase_summary(settings, summary.item_timings)
        build_walkthrough = _build_walkthrough_from_paths(recent_paths) if recent_paths else _build_walkthrough(settings, summary.item_timings)
        timing_assessment = (
            f"Usual build read: {build_walkthrough['summary']}."
            if top_item is not None
            else "There is not enough item timing data yet to name a reliable build checkpoint."
        )
        build_evidence_ids: list[str] = []
        if focus_item_name:
            curated_path = _knowledge_path(settings, "items", focus_item_name)
            if curated_path is not None:
                build_evidence_ids.append(
                    add_evidence(
                        "knowledge_base",
                        f"{focus_item_name} item note",
                        _knowledge_excerpt(curated_path),
                        reference=str(curated_path.relative_to(settings.project_root)),
                        trust="medium",
                    )
                )
            imported_path = _knowledge_path(settings, "items", focus_item_name, imported=True)
            if imported_path is not None:
                build_evidence_ids.append(
                    add_evidence(
                        "wiki_reference",
                        f"{focus_item_name} reference import",
                        _knowledge_excerpt(imported_path),
                        reference=str(imported_path.relative_to(settings.project_root)),
                        trust="low",
                    )
                )
        build_timing = BuildTimingAudit(
            focus_item=focus_item_name,
            build_spine=build_spine,
            timing_assessment=timing_assessment,
            branch_signal=(
                f"The cleanest repeated lane/early opener is {' -> '.join(build_spine)} across {branch_count} recent matches."
                if build_spine and branch_count > 1
                else f"No single opening branch repeats enough yet; the better read is the usual lane/early-to-late walkthrough: {build_walkthrough['summary']}."
            ),
            recommended_adjustment=(
                "Read it as lane/early, mid, and late, with a stable core plus flex slots around it."
                if focus_item_name
                else "Hydrate more matches before making a strong build-path call."
            ),
        )
        steps.append(
            TraceStep(
                name="build_capability",
                kind="synthesis",
                duration_ms=round((perf_counter() - specialist_started) * 1000, 2),
                detail=build_timing.timing_assessment,
                tool_calls=["_recent_item_paths_payload", "_describe_branch_from_paths"],
                evidence_ids=build_evidence_ids,
            )
        )

    if "matchup_review" in routing.tool_hints:
        specialist_started = perf_counter()
        if summary is None:
            matchup = MatchupAssessment(
                status="unavailable",
                summary="No player-specific matchup view is available yet because no account is synced.",
                next_step="Sync a player account and hydrate a few matches before using matchup coaching.",
                limitation="No local telemetry available.",
            )
            status = "limited"
        elif summary.hydrated_match_count < 1:
            matchup = MatchupAssessment(
                status="limited",
                summary="The local backend can frame matchup questions, but matchup joins are still thin without hydrated match metadata.",
                next_step="Hydrate more matches and use the selected hero as the first matchup reference point.",
                limitation="Hydrated match count is still too low for strong matchup claims.",
            )
            status = "limited"
        else:
            matchup = MatchupAssessment(
                status="ready",
                summary="There is enough hydrated metadata to start narrow matchup reviews, but the strongest current use is still hero-specific replay and fight-sequence review.",
                next_step="Use one hero and one recurring lane/fight failure as the next matchup deep dive.",
            )
            status = "ok"
        steps.append(
            TraceStep(
                name="matchup_capability",
                kind="synthesis",
                status=status,
                duration_ms=round((perf_counter() - specialist_started) * 1000, 2),
                detail=matchup.summary,
                tool_calls=["summarize_account"],
            )
        )

    if family in {"focus", "progress", "experiment", "hero_review", "mirror", "matchups"}:
        specialist_started = perf_counter()
        focus_area = "stabilize hero and build patterns" if summary is not None else "general coaching mode"
        if family in {"timing", "experiment"}:
            focus_area = "stabilize one build checkpoint"
        elif family in {"hero_overview", "reliable_hero", "hero_review", "winrate"}:
            focus_area = "tighten hero-pool signal"
        elif family in {"patches", "meta"}:
            focus_area = "separate grounded local reads from global meta claims"
        elif family in {"mirror", "matchups"}:
            focus_area = "narrow the comparison lens"

        practice_plan = PracticePlan(
            focus_area=focus_area,
            rationale=(
                "Pick the next smallest test that gives you a clearer read."
                if summary is not None
                else "Keep the recommendation narrow and practical."
            ),
            drills=[
                "Pick one hero or one build branch for the next block.",
                "Check whether the intended first spike arrived on time before judging the fight.",
                "Write down one keep, one stop, and one next test after the session.",
            ],
        )
        steps.append(
            TraceStep(
                name="coach_agent",
                kind="synthesis",
                duration_ms=round((perf_counter() - specialist_started) * 1000, 2),
                detail=f"Prepared a coaching plan focused on {practice_plan.focus_area}.",
                tool_calls=["routing", "practice_plan"],
            )
        )

    if "experiment_planning" in routing.tool_hints:
        specialist_started = perf_counter()
        focus_hero_name = requested_hero_name or (hero_pool.focus_hero if hero_pool else None) or "the current main hero"
        focus_item_name = build_timing.focus_item if build_timing else "the first real build spike"
        experiment_plan = ExperimentPlan(
            hypothesis=f"If you keep {focus_hero_name} stable and clean up {focus_item_name}, your next block should produce a more reliable coaching signal.",
            success_metric="Improved timing consistency plus cleaner fight selection over the next sample block.",
            sample_size_target=5,
            current_result="No active tracked experiment yet.",
            next_action="start",
        )
        steps.append(
            TraceStep(
                name="experiment_capability",
                kind="synthesis",
                duration_ms=round((perf_counter() - specialist_started) * 1000, 2),
                detail="Drafted a narrow next experiment instead of a full rebuild.",
                tool_calls=["experiment_plan"],
            )
        )

    if "vod_review_planning" in routing.tool_hints:
        specialist_started = perf_counter()
        focus_hero_name = requested_hero_name or (hero_pool.focus_hero if hero_pool else None) or "the current hero"
        vod_review = VodReviewPlan(
            review_target=f"{focus_hero_name} review block",
            checkpoints=[
                "Opening lane plan and first two reset timings.",
                "Whether the first real spike was bought before the first forced fight.",
                "Which engages or trades were taken without enough follow-up.",
            ],
            success_criteria="You can point to one repeated decision error before blaming mechanics.",
        )
        steps.append(
            TraceStep(
                name="vod_review_capability",
                kind="synthesis",
                duration_ms=round((perf_counter() - specialist_started) * 1000, 2),
                detail=f"Built a VOD review checklist for {focus_hero_name}.",
                tool_calls=["vod_review_plan"],
            )
        )

    if family in {"focus", "progress", "experiment", "hero_review"}:
        artifact_type = (
            "experiment_summary"
            if family == "experiment"
            else "weekly_report"
        )
        title = {
            "experiment_summary": "Next Experiment Brief",
            "weekly_report": "Coaching Brief",
        }[artifact_type]
        artifact_outline = ArtifactOutline(
            artifact_type=artifact_type,  # type: ignore[arg-type]
            title=title,
            sections=[
                ArtifactSection(
                    heading="Bottom line",
                    summary=practice_plan.rationale if practice_plan is not None else "Current coaching read.",
                    bullets=build_evidence_bullets(
                        CoachResponseEnvelope(
                            confidence=ConfidenceReport(level="low", score=0.0, rationale=""),
                            evidence_graph=evidence_graph,
                            structured_output=StructuredCoachOutput(routing=routing),
                            trace=TraceReport(selected_specialists=[], steps=[], total_duration_ms=0.0),
                        ),
                        limit=3,
                    ),
                ),
                ArtifactSection(
                    heading="Next action",
                    summary=(experiment_plan.hypothesis if experiment_plan is not None else "Keep the next test narrow."),
                    bullets=(practice_plan.drills[:2] if practice_plan is not None else []),
                ),
            ],
        )

    envelope = CoachResponseEnvelope(
        confidence=_confidence(
            summary,
            evidence_graph,
            player_summary_expected=needs_player_summary,
            routing=routing,
        ),
        evidence_graph=evidence_graph,
        structured_output=StructuredCoachOutput(
            routing=routing,
            comparison=comparison,
            hero_pool=hero_pool,
            build_timing=build_timing,
            matchup=matchup,
            practice_plan=practice_plan,
            experiment_plan=experiment_plan,
            vod_review=vod_review,
            artifact_outline=artifact_outline,
        ),
        trace=TraceReport(
            selected_specialists=routing.specialists,
            steps=steps,
            total_duration_ms=round((perf_counter() - started) * 1000, 2),
        ),
    )
    return envelope


def enrich_reply_payload(reply: dict[str, Any], envelope: CoachResponseEnvelope, *, preserve_insight: bool = True) -> dict[str, Any]:
    payload = dict(reply)
    if preserve_insight and payload.get("insight") is None:
        payload["insight"] = ""
    payload["evidence"] = payload.get("evidence") or build_evidence_bullets(envelope)
    payload["coach_answer"] = _coach_answer_from_reply(payload, envelope).model_dump(mode="json", exclude_none=True)
    payload["confidence"] = envelope.confidence.model_dump(mode="json")
    payload["evidence_graph"] = [item.model_dump(mode="json") for item in envelope.evidence_graph]
    payload["structured_output"] = envelope.structured_output.model_dump(mode="json", exclude_none=True)
    payload["trace"] = envelope.trace.model_dump(mode="json")
    return payload
