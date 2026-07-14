from __future__ import annotations

from dataclasses import dataclass

from deadlock_coach.agent_contracts import CapabilityMatch, InformationNeed, RoutingDecision
from deadlock_coach.message_hints import (
    looks_like_contextual_followup,
    looks_like_full_history_request,
    normalized_message,
)


@dataclass(frozen=True)
class CapabilityRule:
    capability: str
    analyst_lane: str
    priority: int
    families: tuple[str, ...]
    requires_account: bool = False
    requires_player_need: bool = False
    requires_knowledge: bool = False
    requires_global: bool = False
    requires_patch: bool = False
    requires_matchup: bool = False


CAPABILITY_RULES: tuple[CapabilityRule, ...] = (
    CapabilityRule("knowledge_base_lookup", "knowledge", 5, ("timing", "patches", "meta", "mirror", "matchups", "hero_review", "global_popularity", "general"), requires_knowledge=True),
    CapabilityRule("patch_context", "knowledge", 5, ("patches", "meta"), requires_patch=True),
    CapabilityRule("hero_pool_analysis", "data", 5, ("hero_overview", "reliable_hero", "winrate", "hero_review", "sample_window"), requires_account=True, requires_player_need=True),
    CapabilityRule("build_analysis", "data", 5, ("timing", "sample_window"), requires_account=True, requires_player_need=True),
    CapabilityRule("global_hero_stats", "data", 4, ("meta", "winrate", "mirror", "global_popularity"), requires_global=True),
    CapabilityRule("global_item_stats", "data", 4, ("meta", "timing", "mirror", "global_popularity"), requires_global=True),
    CapabilityRule("global_item_flow", "data", 4, ("meta", "timing"), requires_global=True),
    CapabilityRule("player_performance_curve", "data", 4, ("hero_review", "progress"), requires_account=True, requires_player_need=True),
    CapabilityRule("comparison_context", "data", 3, ("mirror", "global_popularity"), requires_account=True, requires_player_need=True),
    CapabilityRule("matchup_review", "matchup", 4, ("matchups", "mirror"), requires_matchup=True),
    CapabilityRule("practice_planning", "practice", 3, ("focus", "progress")),
    CapabilityRule("experiment_planning", "practice", 4, ("experiment",)),
    CapabilityRule("vod_review_planning", "practice", 3, ("matchups", "hero_review")),
)


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _previous_user_text(history: list[dict[str, object]] | None, current_lowered: str) -> str | None:
    if not history:
        return None
    for turn in reversed(history):
        if turn.get("role") != "user":
            continue
        text = normalized_message(str(turn.get("text") or ""))
        if not text or text == current_lowered:
            continue
        return text
    return None


def _routing_text(message: str, history: list[dict[str, object]] | None = None) -> str:
    lowered = normalized_message(message)
    if not looks_like_contextual_followup(lowered):
        return lowered
    previous = _previous_user_text(history, lowered)
    if not previous:
        return lowered
    return f"{previous} {lowered}".strip()


def infer_information_need(message: str, history: list[dict[str, object]] | None = None) -> InformationNeed:
    lowered = _routing_text(message, history)
    player_specific = _contains_any(
        lowered,
        (
            " i ",
            " my ",
            " me ",
            " am i ",
            " do i ",
            " have i ",
            " usually ",
            " my games",
            " my build",
            " my hero",
            " my pool",
            " for me",
        ),
    ) or lowered.startswith(("i ", "my ", "am i ", "do i ", "have i "))
    global_scope = _contains_any(
        lowered,
        (
            "for everyone",
            "global",
            "overall",
            "all players",
            "public matches",
            "meta",
            "in eternus",
            "in phantom",
            "in ascendant",
            "in oracle",
            "in archon",
            "in emissary",
            "in ritualist",
            "in arcanist",
            "in alchemist",
            "in seeker",
            "in initiate",
            "in obscurus",
        ),
    )

    if lowered in {"hi", "hello", "hey", "hej", "yo"} or lowered.startswith(("hi ", "hello ", "hey ", "hej ")):
        return InformationNeed(family="greeting", scope="general", subject="general")
    if lowered in {"what", "what?", "why", "why?", "help", "help?", "ok", "okay", "huh", "?"} or (len(lowered.split()) <= 3 and lowered.endswith("?")):
        return InformationNeed(family="clarify", scope="general", subject="general", reasoning_mode="clarify")
    if _contains_any(lowered, ("patch", "buff", "nerf", "changed this patch", "last patch", "latest patch")):
        return InformationNeed(
            family="patches",
            scope="knowledge",
            subject="patch",
            needs_knowledge_base=True,
            needs_patch_context=True,
        )
    if _contains_any(lowered, ("pickrate", "pick rate", "most popular", "most picked")) and _contains_any(lowered, ("winrate", "win rate")):
        return InformationNeed(
            family="global_popularity",
            scope="global",
            subject="meta",
            needs_global_analytics=True,
            needs_knowledge_base=True,
        )
    if _contains_any(lowered, ("meta", "strong right now", "good right now", "best heroes right now", "best hero right now")):
        return InformationNeed(
            family="meta",
            scope="mixed",
            subject="meta",
            needs_knowledge_base=True,
            needs_global_analytics=True,
            needs_patch_context=True,
        )
    if (
        (
            _contains_any(lowered, ("who do i play", "play most", "hero pool"))
            or ("what heroes" in lowered and "play" in lowered)
            or ("what hero" in lowered and "play" in lowered)
        )
        and "should i" not in lowered
        and "queue" not in lowered
        and "reliable" not in lowered
    ):
        return InformationNeed(
            family="hero_overview",
            scope="player_specific" if player_specific else "mixed",
            subject="hero_pool",
            prefers_full_history=looks_like_full_history_request(lowered),
            needs_player_telemetry=player_specific,
            needs_knowledge_base=not player_specific,
        )
    if _contains_any(lowered, ("queue", "reliable", "which hero")):
        return InformationNeed(
            family="reliable_hero",
            scope="player_specific" if player_specific else "mixed",
            subject="hero_pool",
            prefers_full_history=looks_like_full_history_request(lowered),
            needs_player_telemetry=player_specific,
        )
    if _contains_any(lowered, ("winrate", "win rate", "am i winning", "winning on", "winning with", "best win rate")):
        return InformationNeed(
            family="winrate",
            scope="player_specific" if player_specific and not global_scope else "global",
            subject="hero_pool" if player_specific and not global_scope else "meta",
            prefers_full_history=looks_like_full_history_request(lowered),
            needs_player_telemetry=player_specific and not global_scope,
            needs_global_analytics=global_scope or not player_specific,
        )
    if _contains_any(lowered, ("pro ", "pro?", "pros ", "high-mmr", "top players")) and _contains_any(
        lowered,
        (
            "build",
            "item",
            "buy",
            "what does",
            "what do",
        ),
    ) and "compare" not in lowered:
        return InformationNeed(
            family="timing",
            scope="global",
            subject="build",
            needs_global_analytics=True,
            needs_knowledge_base=True,
        )
    if _contains_any(lowered, ("branch", "test next", "next five", "experiment")):
        return InformationNeed(family="experiment", scope="player_specific" if player_specific else "general", subject="experiment", reasoning_mode="coach", needs_player_telemetry=player_specific)
    if _contains_any(lowered, ("compare", "top players", "high-mmr", "pro ", "pro?")):
        return InformationNeed(
            family="mirror",
            scope="mixed",
            subject="matchup",
            needs_global_analytics=True,
            needs_knowledge_base=True,
            needs_matchup_context=True,
        )
    if _contains_any(lowered, ("matchup", "worst against", "worst vs", "against ")) and "what do you mean" not in lowered:
        return InformationNeed(
            family="matchups",
            scope="mixed" if player_specific else "knowledge",
            subject="matchup",
            needs_knowledge_base=True,
            needs_matchup_context=True,
            needs_player_telemetry=player_specific,
        )
    if _contains_any(
        lowered,
        (
            "what should i build",
            "what should i buy",
            "should i build",
            "should i buy",
            "spike",
            "spikes",
            "4.8k",
            "6.4k",
            "3.2k",
            "timing",
            "lag",
            "item path",
            "build",
            "item",
            "later into the game",
            "later into games",
            "later in the game",
            "later into the games",
            "most popular build",
            "most common build",
            "popular build",
        ),
    ) or ("damage" in lowered and _contains_any(lowered, ("spirit", "vitality", "weapon"))) or ("investment" in lowered and _contains_any(lowered, ("spirit", "vitality", "weapon"))):
        return InformationNeed(
            family="timing",
            scope="player_specific" if player_specific else "global" if _contains_any(lowered, ("most popular build", "most common build", "popular build")) else "mixed",
            subject="build",
            needs_player_telemetry=player_specific,
            needs_global_analytics=not player_specific or _contains_any(lowered, ("most popular build", "most common build", "popular build")),
            needs_knowledge_base=True,
        )
    if _contains_any(lowered, ("focus", "practice", "what should i")):
        return InformationNeed(family="focus", scope="player_specific" if player_specific else "general", subject="practice", reasoning_mode="coach", needs_player_telemetry=player_specific)
    if _contains_any(lowered, ("breaking down", "underperform", "fall off")):
        return InformationNeed(
            family="hero_review",
            scope="player_specific" if player_specific else "mixed",
            subject="progress",
            reasoning_mode="coach",
            needs_player_telemetry=player_specific,
            needs_knowledge_base=True,
        )
    if _contains_any(lowered, ("improving", "progress")):
        return InformationNeed(family="progress", scope="player_specific" if player_specific else "general", subject="progress", reasoning_mode="coach", needs_player_telemetry=player_specific)
    if _contains_any(lowered, ("sample", "more matches", "200 matches")) and _contains_any(lowered, ("bigger", "larger", "wider", "more")):
        return InformationNeed(family="sample_window", scope="player_specific", subject="hero_pool", needs_player_telemetry=True)
    if _contains_any(lowered, ("most popular right now", "heroes are most popular", "popular heroes right now", "highest pickrate", "highest pick rate", "top pickrate", "top pick rate")):
        return InformationNeed(
            family="global_popularity",
            scope="global",
            subject="meta",
            needs_global_analytics=True,
            needs_knowledge_base=True,
        )
    if _contains_any(lowered, ("what is", "what are", "explain", "mean", "definition", "do you know")):
        return InformationNeed(
            family="general",
            scope="knowledge",
            subject="concept",
            needs_knowledge_base=True,
        )
    return InformationNeed(
        family="general",
        scope="player_specific" if player_specific else "general",
        subject="general",
        needs_player_telemetry=player_specific,
    )


def build_routing_decision(
    message: str,
    *,
    has_account: bool,
    history: list[dict[str, object]] | None = None,
) -> RoutingDecision:
    need = infer_information_need(message, history)
    matches: list[CapabilityMatch] = []
    for rule in CAPABILITY_RULES:
        if need.family not in rule.families:
            continue
        if rule.requires_account and not has_account:
            continue
        if rule.requires_player_need and not need.needs_player_telemetry:
            continue
        if rule.requires_knowledge and not need.needs_knowledge_base:
            continue
        if rule.requires_global and not need.needs_global_analytics:
            continue
        if rule.requires_patch and not need.needs_patch_context:
            continue
        if rule.requires_matchup and not need.needs_matchup_context:
            continue
        matches.append(
            CapabilityMatch(
                capability=rule.capability,
                analyst_lane=rule.analyst_lane,  # type: ignore[arg-type]
                priority=rule.priority,
                rationale=f"{rule.capability} supports the `{need.family}` information need.",
            )
        )

    if not has_account and need.family not in {"greeting", "clarify", "focus", "progress"} and need.needs_knowledge_base:
        if not any(match.capability == "knowledge_base_lookup" for match in matches):
            matches.insert(
                0,
                CapabilityMatch(
                    capability="knowledge_base_lookup",
                    analyst_lane="knowledge",
                    priority=5,
                    rationale="Without player telemetry, the coach should ground the answer in the local KB first.",
                )
            )

    matches.sort(key=lambda item: (-item.priority, item.capability))
    tool_hints: list[str] = []
    analyst_lanes: list[str] = []
    for match in matches:
        if match.capability not in tool_hints:
            tool_hints.append(match.capability)
        if match.analyst_lane != "coach" and match.analyst_lane not in analyst_lanes:
            analyst_lanes.append(match.analyst_lane)

    rationale = (
        "The root coach should stay conversational and pull only the narrowest supporting capability lanes."
        if has_account
        else "No active player telemetry is attached, so the root coach should lean on knowledge or global data lanes and avoid bluffing player-specific reads."
    )
    if need.needs_knowledge_base:
        rationale += " Start with the local KB before freeform theory when the answer is about game systems or concepts."

    specialists: list[str] = ["coach_agent"]

    return RoutingDecision(
        family=need.family,
        specialists=specialists,  # type: ignore[arg-type]
        analyst_lanes=analyst_lanes,  # type: ignore[arg-type]
        tool_hints=tool_hints,
        information_need=need,
        capability_matches=matches,
        rationale=rationale,
    )
