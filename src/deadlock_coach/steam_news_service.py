from __future__ import annotations

from typing import Any

from deadlock_coach.api import DeadlockApiClient
from deadlock_coach.config import Settings
from deadlock_coach.storage import normalize_steam_patch_feed, save_json_snapshot

# Steam's news feed name that Deadlock's official patch notes are published under.
STEAM_ANNOUNCEMENTS_FEED = "steam_community_announcements"
# Tag Valve attaches to official patch-note posts, used to separate them from
# generic community announcements.
PATCH_NOTES_TAG = "patchnotes"


def _news_url(settings: Settings) -> str:
    return f"{settings.steam_api_base_url.rstrip('/')}/ISteamNews/GetNewsForApp/v2/"


def _is_patch_note(item: dict[str, Any]) -> bool:
    tags = item.get("tags")
    if isinstance(tags, list) and PATCH_NOTES_TAG in {str(tag).strip().lower() for tag in tags}:
        return True
    # Fall back to the announcements feed when tags are absent on older posts.
    return str(item.get("feedname") or "").strip().lower() == STEAM_ANNOUNCEMENTS_FEED


def fetch_steam_patch_notes(
    settings: Settings,
    *,
    count: int = 20,
    include_all_news: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    """Fetch Deadlock patch notes from the Steam ISteamNews endpoint.

    Returns the request URL and the list of newsitems. When `include_all_news`
    is False (the default), only official patch-note posts are kept. No Steam
    API key is required for this endpoint; if `steam_api_key` is configured it is
    sent for parity with key-gated Steam endpoints.
    """

    client = DeadlockApiClient(settings)
    params: dict[str, Any] = {
        "appid": settings.deadlock_app_id,
        "count": max(1, count),
        # maxlength=0 asks Steam for the full body text rather than a snippet.
        "maxlength": 0,
    }
    if settings.steam_api_key:
        params["key"] = settings.steam_api_key

    request_url, payload = client.fetch_json(_news_url(settings), params=params)
    newsitems = ((payload or {}).get("appnews") or {}).get("newsitems") or []
    if not isinstance(newsitems, list):
        newsitems = []

    if not include_all_news:
        newsitems = [item for item in newsitems if isinstance(item, dict) and _is_patch_note(item)]
    else:
        newsitems = [item for item in newsitems if isinstance(item, dict)]

    return request_url, newsitems


def sync_steam_patches(
    settings: Settings,
    *,
    count: int = 20,
    include_all_news: bool = False,
) -> dict[str, Any]:
    """Fetch official Deadlock patch notes from Steam and store them locally."""

    request_url, newsitems = fetch_steam_patch_notes(
        settings,
        count=count,
        include_all_news=include_all_news,
    )
    snapshot = save_json_snapshot(
        settings,
        "steam_news",
        "patches",
        str(settings.deadlock_app_id),
        request_url,
        newsitems,
    )
    stored = normalize_steam_patch_feed(settings, snapshot, newsitems)
    return {
        "source": "steam_news",
        "request_url": request_url,
        "app_id": settings.deadlock_app_id,
        "fetched_count": len(newsitems),
        "stored_count": stored,
        "include_all_news": include_all_news,
        "snapshot_path": str(snapshot.path),
    }
