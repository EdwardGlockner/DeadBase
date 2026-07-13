# ruff: noqa
from __future__ import annotations

from google.adk.agents import Agent
from google.adk.apps import App

from app.instruction_loader import load_instruction
from app.model_factory import build_model
from app.tools import (
    get_build_analysis,
    get_comparison_context,
    get_global_hero_stats,
    get_global_item_flow,
    get_global_item_stats,
    get_hero_pool_analysis,
    get_hero_reference,
    get_item_reference,
    get_patch_context,
    get_player_performance_curve,
    get_player_profile,
    get_recent_item_paths,
    get_recent_matches,
    inspect_local_state,
    list_deadlock_reference_catalog,
    list_available_accounts,
    list_knowledge_topics,
    list_reference_import_topics,
    query_reference_tables,
    retrieve_game_knowledge,
    route_coaching_request,
    search_deadlock_wiki,
    search_reference_imports,
    search_knowledge_base,
)


MODEL = build_model()
CHAT_FORMATTING_RULES = load_instruction(
    __file__,
    "instructions/shared/chat_formatting_rules.md",
)
SPECIALIST_PLACEHOLDER = load_instruction(
    __file__,
    "instructions/shared/specialist_placeholder.md",
    CHAT_FORMATTING_RULES=CHAT_FORMATTING_RULES,
)
DATA_ANALYST_INSTRUCTION = load_instruction(
    __file__,
    "instructions/data_analyst.md",
    CHAT_FORMATTING_RULES=CHAT_FORMATTING_RULES,
)
KNOWLEDGE_ANALYST_INSTRUCTION = load_instruction(
    __file__,
    "instructions/knowledge_analyst.md",
    CHAT_FORMATTING_RULES=CHAT_FORMATTING_RULES,
)
COMPARISON_ANALYST_INSTRUCTION = load_instruction(
    __file__,
    "instructions/comparison_analyst.md",
    CHAT_FORMATTING_RULES=CHAT_FORMATTING_RULES,
)

def _placeholder_agent(name: str, description: str) -> Agent:
    return Agent(
        name=name,
        model=MODEL,
        description=description,
        instruction=SPECIALIST_PLACEHOLDER.replace("{{AGENT_NAME}}", name),
        tools=[inspect_local_state],
    )


def _internal_analyst(name: str, description: str, instruction: str, tools: list[object]) -> Agent:
    return Agent(
        name=name,
        model=MODEL,
        description=description,
        instruction=instruction,
        tools=tools,
        disallow_transfer_to_peers=True,
    )


data_analyst = _internal_analyst(
    "data_analyst",
    "Internal specialist for telemetry, analytics, build flow, and performance questions.",
    DATA_ANALYST_INSTRUCTION,
    [
        inspect_local_state,
        list_available_accounts,
        get_player_profile,
        get_recent_matches,
        get_hero_pool_analysis,
        get_build_analysis,
        get_recent_item_paths,
        get_comparison_context,
        get_global_hero_stats,
        get_global_item_stats,
        get_global_item_flow,
        get_player_performance_curve,
        retrieve_game_knowledge,
        search_knowledge_base,
        list_knowledge_topics,
        query_reference_tables,
        get_hero_reference,
        get_item_reference,
        get_patch_context,
        route_coaching_request,
    ],
)

knowledge_analyst = _internal_analyst(
    "knowledge_analyst",
    "Internal specialist for Deadlock concepts, KB grounding, and patch/reference questions.",
    KNOWLEDGE_ANALYST_INSTRUCTION,
    [
        inspect_local_state,
        list_knowledge_topics,
        retrieve_game_knowledge,
        search_knowledge_base,
        list_reference_import_topics,
        search_reference_imports,
        query_reference_tables,
        list_deadlock_reference_catalog,
        get_hero_reference,
        get_item_reference,
        get_patch_context,
        route_coaching_request,
    ],
)


player_profile_analyst = _placeholder_agent(
    "player_profile_analyst",
    "Placeholder only while Deadbase focuses on coach_agent.",
)
hero_pool_analyst = _placeholder_agent(
    "hero_pool_analyst",
    "Placeholder only while Deadbase focuses on coach_agent.",
)
build_analyst = _placeholder_agent(
    "build_analyst",
    "Placeholder only while Deadbase focuses on coach_agent.",
)
comparison_analyst = _internal_analyst(
    "comparison_analyst",
    "Internal specialist for player-vs-meta, rank, and pattern comparison questions.",
    COMPARISON_ANALYST_INSTRUCTION,
    [
        inspect_local_state,
        list_available_accounts,
        get_player_profile,
        get_hero_pool_analysis,
        get_build_analysis,
        get_recent_item_paths,
        get_comparison_context,
        get_global_hero_stats,
        get_global_item_stats,
        get_global_item_flow,
        get_player_performance_curve,
        retrieve_game_knowledge,
        search_knowledge_base,
        query_reference_tables,
        get_hero_reference,
        get_item_reference,
        get_patch_context,
        route_coaching_request,
    ],
)
matchup_analyst = _placeholder_agent(
    "matchup_analyst",
    "Placeholder only while Deadbase focuses on coach_agent.",
)
report_agent = _placeholder_agent(
    "report_agent",
    "Placeholder only while Deadbase focuses on coach_agent.",
)
experiment_agent = _placeholder_agent(
    "experiment_agent",
    "Placeholder only while Deadbase focuses on coach_agent.",
)
vod_review_planner = _placeholder_agent(
    "vod_review_planner",
    "Placeholder only while Deadbase focuses on coach_agent.",
)
knowledge_base_analyst = _placeholder_agent(
    "knowledge_base_analyst",
    "Placeholder only while Deadbase focuses on coach_agent.",
)


coach_agent = Agent(
    name="coach_agent",
    model=MODEL,
    description="Primary conversational Deadlock coaching agent.",
    instruction=load_instruction(
        __file__,
        "instructions/coach_agent.md",
        CHAT_FORMATTING_RULES=CHAT_FORMATTING_RULES,
    ),
    tools=[
        list_available_accounts,
        inspect_local_state,
        get_player_profile,
        get_recent_matches,
        get_hero_pool_analysis,
        get_build_analysis,
        get_recent_item_paths,
        get_comparison_context,
        get_global_hero_stats,
        get_global_item_stats,
        get_global_item_flow,
        get_player_performance_curve,
        retrieve_game_knowledge,
        search_knowledge_base,
        list_knowledge_topics,
        search_reference_imports,
        list_reference_import_topics,
        query_reference_tables,
        get_hero_reference,
        get_item_reference,
        get_patch_context,
        route_coaching_request,
    ],
    sub_agents=[data_analyst, knowledge_analyst, comparison_analyst],
)

root_agent = coach_agent


app = App(
    root_agent=root_agent,
    name="app",
)
