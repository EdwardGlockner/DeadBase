from __future__ import annotations

import argparse
import json
from typing import Any

from deadlock_coach.api import DeadlockApiClient
from deadlock_coach.account_service import sync_account
from deadlock_coach.analytics_service import parse_cli_param, sync_analytics_query
from deadlock_coach.config import Settings
from deadlock_coach.data_surface import inspect_data_surface, list_artifacts
from deadlock_coach.knowledge_base import sync_reference_corpus, sync_wiki_reference_files
from deadlock_coach.server import serve
from deadlock_coach.steam_news_service import sync_steam_patches
from deadlock_coach.storage import (
    initialize_workspace,
    normalize_patch_feed,
    normalize_leaderboard,
    normalize_match_history,
    normalize_match_metadata,
    save_json_snapshot,
)


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deadlock-coach", description="Deadlock Coach local-first bootstrap CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("bootstrap", help="Create the local workspace and initialize SQLite stores")

    inspect_parser = subparsers.add_parser("inspect-data-surface", help="Print the audited public data surface")
    inspect_parser.add_argument("--json", action="store_true", help="Emit JSON instead of prose")

    artifacts_parser = subparsers.add_parser("list-artifacts", help="List first-class artifact types")
    artifacts_parser.add_argument("--json", action="store_true", help="Emit JSON instead of prose")

    sync_parser = subparsers.add_parser("sync", help="Fetch and store live upstream data")
    sync_subparsers = sync_parser.add_subparsers(dest="sync_command", required=True)

    sync_subparsers.add_parser("patches", help="Fetch the unified patch feed and store it locally")

    steam_patches_parser = sync_subparsers.add_parser(
        "steam-patches",
        help="Fetch official Deadlock patch notes from the Steam news API and store them locally",
    )
    steam_patches_parser.add_argument(
        "--count",
        type=int,
        default=20,
        help="How many recent news posts to request from Steam before filtering",
    )
    steam_patches_parser.add_argument(
        "--include-all-news",
        action="store_true",
        help="Store every news post, not just posts tagged as patch notes",
    )
    steam_patches_parser.add_argument("--json", action="store_true", help="Emit JSON instead of prose")

    leaderboard_parser = sync_subparsers.add_parser("leaderboard", help="Fetch a leaderboard snapshot")
    leaderboard_parser.add_argument(
        "--region",
        required=True,
        choices=["Europe", "Asia", "NAmerica", "SAmerica", "Oceania"],
        help="Leaderboard region expected by the Deadlock API",
    )

    player_parser = sync_subparsers.add_parser("player", help="Fetch player match history and hydrate recent matches")
    player_parser.add_argument("--account-id", type=int, required=True, help="Deadlock account ID")
    player_parser.add_argument(
        "--hydrate-matches",
        type=int,
        default=0,
        help="Number of recent matches to hydrate with /matches/{match_id}/metadata",
    )

    analytics_parser = sync_subparsers.add_parser("analytics", help="Fetch and store a raw analytics snapshot")
    analytics_parser.add_argument(
        "--endpoint",
        required=True,
        help="Analytics endpoint alias or full /v1/analytics/... path",
    )
    analytics_parser.add_argument(
        "--param",
        action="append",
        default=[],
        help="Analytics query param in key=value form. JSON arrays/objects/bools are supported.",
    )
    analytics_parser.add_argument(
        "--patch-window-label",
        default=None,
        help="Optional app-owned patch window label to store with the snapshot",
    )
    analytics_parser.add_argument("--json", action="store_true", help="Emit JSON instead of prose")

    knowledge_parser = subparsers.add_parser("knowledge", help="Manage the local knowledge base")
    knowledge_subparsers = knowledge_parser.add_subparsers(dest="knowledge_command", required=True)

    sync_wiki_parser = knowledge_subparsers.add_parser(
        "sync-wiki",
        help="Pull Deadlock Wiki reference pages into local markdown import files",
    )
    sync_wiki_parser.add_argument(
        "--kind",
        required=True,
        choices=["heroes", "items", "pages"],
        help="Which Deadlock Wiki slice to import",
    )
    sync_wiki_parser.add_argument(
        "--title",
        action="append",
        default=[],
        help="Specific title to import. Repeat to import multiple pages.",
    )
    sync_wiki_parser.add_argument(
        "--limit",
        type=int,
        default=24,
        help="How many pages to import when using a category sync",
    )
    sync_wiki_parser.add_argument(
        "--all",
        action="store_true",
        help="Import the full category instead of capping the number of pages",
    )
    sync_wiki_parser.add_argument("--json", action="store_true", help="Emit JSON instead of prose")

    sync_reference_parser = knowledge_subparsers.add_parser(
        "sync-reference",
        help="Pull the full hero and item reference corpus, with optional full-page wiki import",
    )
    sync_reference_parser.add_argument(
        "--include-pages",
        action="store_true",
        help="Also import the full wiki page namespace into `_imports/wiki/pages/`",
    )
    sync_reference_parser.add_argument(
        "--page-limit",
        type=int,
        default=None,
        help="Optional cap for page imports when using `--include-pages`",
    )
    sync_reference_parser.add_argument("--json", action="store_true", help="Emit JSON instead of prose")

    serve_parser = subparsers.add_parser("serve", help="Run the local Deadlock Coach backend API")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind")
    serve_parser.add_argument("--port", type=int, default=3000, help="Port to bind")

    return parser


def command_bootstrap(settings: Settings) -> int:
    initialize_workspace(settings)
    print(f"Initialized workspace under {settings.project_root}")
    print(f"Warehouse DB: {settings.warehouse_db_path}")
    print(f"Memory DB: {settings.memory_db_path}")
    return 0


def command_inspect_data_surface(as_json: bool) -> int:
    payload = inspect_data_surface()
    if as_json:
        _print_json(payload)
        return 0

    print(f"Audit date: {payload['audit_date']}")
    print("")
    print("Endpoints:")
    for item in payload["endpoints"]:
        print(f"- {item['name']} [{item['support']}] -> {item['path']}")
        print(f"  {item['purpose']} {item['notes']}")
    print("")
    print("Feature support:")
    for item in payload["feature_support"]:
        print(f"- {item['feature']} [{item['support']}]")
        print(f"  {item['summary']}")
    return 0


def command_list_artifacts(as_json: bool) -> int:
    artifacts = list_artifacts()
    if as_json:
        _print_json(artifacts)
        return 0

    for artifact in artifacts:
        print(f"- {artifact['label']} ({artifact['artifact_type']})")
        print(f"  Inputs: {', '.join(artifact['primary_inputs'])}")
        print(f"  Formats: {', '.join(artifact['output_formats'])}")
    return 0


def command_sync_patches(settings: Settings) -> int:
    client = DeadlockApiClient(settings)
    request_url, payload = client.fetch_json("/v2/patches")
    snapshot = save_json_snapshot(settings, "deadlock_api", "patches", "unified-feed", request_url, payload)
    count = normalize_patch_feed(settings, snapshot, payload)
    print(f"Stored {count} patch entries from {request_url}")
    print(f"Snapshot: {snapshot.path}")
    return 0


def command_sync_steam_patches(
    settings: Settings,
    count: int,
    include_all_news: bool,
    as_json: bool,
) -> int:
    result = sync_steam_patches(settings, count=count, include_all_news=include_all_news)
    if as_json:
        _print_json(result)
        return 0

    scope = "all news posts" if include_all_news else "patch-note posts"
    print(f"Stored {result['stored_count']} / {result['fetched_count']} {scope} from Steam app {result['app_id']}")
    print(f"Request: {result['request_url']}")
    print(f"Snapshot: {result['snapshot_path']}")
    return 0


def command_sync_leaderboard(settings: Settings, region: str) -> int:
    client = DeadlockApiClient(settings)
    request_url, payload = client.fetch_json(f"/v1/leaderboard/{region}")
    snapshot = save_json_snapshot(settings, "deadlock_api", "leaderboard", region, request_url, payload)
    count = normalize_leaderboard(settings, snapshot, region, payload)
    print(f"Stored {count} leaderboard entries for {region}")
    print(f"Snapshot: {snapshot.path}")
    return 0


def command_sync_player(settings: Settings, account_id: int, hydrate_matches: int) -> int:
    result = sync_account(settings, account_id, hydrate_matches=hydrate_matches)
    print(f"Stored {result['match_history_rows']} match-history rows for account {account_id}")
    for hydrated in result["hydrated_matches"]:
        print(
            f"Hydrated match {hydrated['match_id']}: "
            f"{hydrated['players']} players, {hydrated['items']} item purchases, {hydrated['stat_buckets']} stat buckets"
        )
    print(f"Hydrated {len(result['hydrated_matches'])} recent matches for account {account_id}")
    return 0


def command_sync_analytics(
    settings: Settings,
    endpoint: str,
    raw_params: list[str],
    patch_window_label: str | None,
    as_json: bool,
) -> int:
    query_params: dict[str, Any] = {}
    for raw_param in raw_params:
        key, value = parse_cli_param(raw_param)
        query_params[key] = value

    result = sync_analytics_query(
        settings,
        endpoint_name_or_path=endpoint,
        query_params=query_params,
        patch_window_label=patch_window_label,
    )

    if as_json:
        _print_json(result)
        return 0

    print(f"Stored analytics snapshot for {result['endpoint']}")
    print(f"Rows: {result['row_count']}")
    print(f"Snapshot: {result['snapshot_path']}")
    if result["query_params"]:
        print(f"Params: {json.dumps(result['query_params'], ensure_ascii=True, sort_keys=True)}")
    if patch_window_label:
        print(f"Patch window: {patch_window_label}")
    return 0


def command_knowledge_sync_wiki(
    settings: Settings,
    kind: str,
    titles: list[str],
    limit: int,
    sync_all: bool,
    as_json: bool,
) -> int:
    result = sync_wiki_reference_files(settings, kind=kind, titles=titles, limit=None if sync_all else limit)
    if as_json:
        _print_json(result)
        return 0

    print(f"Imported {result['imported_count']} / {result['requested_count']} {kind} pages")
    print(f"Manifest: {result['manifest_path']}")
    for page in result["pages"]:
        if page["imported"]:
            print(f"- {page['title']} -> {page['path']}")
        else:
            print(f"- {page['title']} -> skipped ({page['reason']})")
    return 0


def command_knowledge_sync_reference(settings: Settings, as_json: bool, include_pages: bool, page_limit: int | None) -> int:
    result = sync_reference_corpus(settings, include_pages=include_pages, page_limit=page_limit)
    if as_json:
        _print_json(result)
        return 0

    print(
        "Imported "
        f"{result['imported_count']} / {result['requested_count']} reference pages"
    )
    for kind, kind_result in result["kinds"].items():
        print(
            f"- {kind}: {kind_result['imported_count']} / {kind_result['requested_count']} "
            f"-> {kind_result['manifest_path']}"
        )
    return 0


def command_serve(settings: Settings, host: str, port: int) -> int:
    initialize_workspace(settings)
    serve(settings, host=host, port=port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = Settings.from_env()

    if args.command == "bootstrap":
        return command_bootstrap(settings)
    if args.command == "inspect-data-surface":
        return command_inspect_data_surface(args.json)
    if args.command == "list-artifacts":
        return command_list_artifacts(args.json)
    if args.command == "serve":
        return command_serve(settings, args.host, args.port)
    if args.command == "knowledge":
        if args.knowledge_command == "sync-wiki":
            return command_knowledge_sync_wiki(settings, args.kind, args.title, args.limit, args.all, args.json)
        if args.knowledge_command == "sync-reference":
            return command_knowledge_sync_reference(settings, args.json, args.include_pages, args.page_limit)
    if args.command == "sync":
        if args.sync_command == "patches":
            return command_sync_patches(settings)
        if args.sync_command == "steam-patches":
            return command_sync_steam_patches(settings, args.count, args.include_all_news, args.json)
        if args.sync_command == "leaderboard":
            return command_sync_leaderboard(settings, args.region)
        if args.sync_command == "player":
            return command_sync_player(settings, args.account_id, args.hydrate_matches)
        if args.sync_command == "analytics":
            return command_sync_analytics(settings, args.endpoint, args.param, args.patch_window_label, args.json)

    parser.error("Unknown command")
    return 2
