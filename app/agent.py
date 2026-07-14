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
)

root_agent = coach_agent


app = App(
    root_agent=root_agent,
    name="app",
)
