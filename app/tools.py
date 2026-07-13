from __future__ import annotations

from collections import Counter
from contextlib import closing
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from deadlock_coach.api import DeadlockApiClient
from deadlock_coach.analytics_service import (
    read_latest_global_hero_stats,
    read_latest_global_item_stats,
    read_latest_item_flow_summary,
    read_latest_player_performance_curve,
)
from deadlock_coach.asset_service import hero_label, item_asset, item_label, resolve_rank_badge_range
from deadlock_coach.agent_orchestration import build_response_envelope
from deadlock_coach.coach_service import DEFAULT_WINDOW_MATCHES, account_summary_payload, list_tracked_accounts, summarize_account
from deadlock_coach.config import Settings
from deadlock_coach.knowledge_base import query_local_knowledge_tables, retrieve_grounded_knowledge_context, search_local_knowledge
from deadlock_coach.runtime_context import ActiveCoachContext, get_active_coach_context
from deadlock_coach.storage import _connect


def _settings() -> Settings:
    return Settings.from_env()


def _knowledge_root() -> Path:
    return _settings().project_root / "docs" / "knowledge"


def _wiki_cache_root() -> Path:
    return _settings().cache_dir / "wiki"


WIKI_API_URL = "https://deadlock.wiki/api.php"
WIKI_USER_AGENT = "deadlock-coach/0.1 (local knowledge tooling)"
WIKI_PAGE_EXTRACT_MAX_AGE_S = 7 * 24 * 60 * 60
WIKI_CATEGORY_MAX_AGE_S = 24 * 60 * 60
HERO_CATEGORY_TITLE = "Category:Heroes"
ITEM_CATEGORY_TITLE = "Category:Items"

HERO_TITLE_ALIASES = {
    "the lash": "Lash",
    "lash": "Lash",
    "mo and krill": "Mo & Krill",
    "mo & krill": "Mo & Krill",
    "grey talon": "Grey Talon",
}

ITEM_TITLE_ALIASES = {
    "bullet lifesteal": "Bullet Lifesteal (item)",
}


def _iter_knowledge_files(root: Path, *, include_internal: bool = False) -> list[Path]:
    if not root.exists():
        return []

    paths: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt"}:
            continue
        relative = path.relative_to(root)
        if not include_internal and any(part.startswith("_") for part in relative.parts):
            continue
        paths.append(path)
    return paths

def _tool_context_text(tool_context: Any | None) -> str:
    if tool_context is None:
        return ""

    user_content = getattr(tool_context, "user_content", None)
    parts = getattr(user_content, "parts", None) or []
    texts = [str(getattr(part, "text", "") or "").strip() for part in parts if getattr(part, "text", None)]
    if texts:
        return "\n".join(texts)

    if isinstance(user_content, dict):
        dict_parts = user_content.get("parts") or []
        dict_texts = [str(part.get("text") or "").strip() for part in dict_parts if isinstance(part, dict) and part.get("text")]
        if dict_texts:
            return "\n".join(dict_texts)

    if isinstance(user_content, str):
        return user_content

    return ""


def _tool_context_explicitly_has_no_account(tool_context: Any | None) -> bool:
    text = _tool_context_text(tool_context).lower()
    return "no active player or account is selected" in text


def _context_from_tool_context(tool_context: Any | None) -> ActiveCoachContext | None:
    text = _tool_context_text(tool_context)
    if not text:
        return None

    account_match = re.search(r"Active account id:\s*(\d+)", text)
    player_match = re.search(r"Active player label:\s*(.+)", text)
    hero_match = re.search(r"Hero focus:\s*(.+)", text)
    window_match = re.search(r"Window:\s*last\s*(\d+)\s*matches", text)

    if not any((account_match, player_match, hero_match, window_match)):
        return None

    return ActiveCoachContext(
        account_id=int(account_match.group(1)) if account_match else None,
        player_label=player_match.group(1).strip() if player_match else None,
        hero_name=hero_match.group(1).strip() if hero_match else None,
        window_matches=int(window_match.group(1)) if window_match else None,
    )


def _resolved_active_context(tool_context: Any | None = None) -> ActiveCoachContext | None:
    return get_active_coach_context() or _context_from_tool_context(tool_context)


def _resolve_account_id(account_id: int | None = None, tool_context: Any | None = None) -> int:
    if account_id is not None:
        return account_id

    active_context = _resolved_active_context(tool_context)
    if active_context is not None and active_context.account_id is not None:
        return int(active_context.account_id)
    if _tool_context_explicitly_has_no_account(tool_context):
        raise ValueError("No active player or account is selected.")

    accounts = list_tracked_accounts(_settings())
    if not accounts:
        raise ValueError("No synced account is available yet. Sync a player account first.")
    if len(accounts) > 1:
        raise ValueError("Multiple synced accounts are available. Choose a specific player account first.")
    return int(accounts[0]["account_id"])


def _resolve_optional_account_id(account_id: int | None = None, tool_context: Any | None = None) -> int | None:
    if account_id is not None:
        return account_id

    active_context = _resolved_active_context(tool_context)
    if active_context is not None and active_context.account_id is not None:
        return int(active_context.account_id)
    if _tool_context_explicitly_has_no_account(tool_context):
        return None

    accounts = list_tracked_accounts(_settings())
    if len(accounts) == 1:
        return int(accounts[0]["account_id"])
    return None


def _summary_payload(
    account_id: int | None = None,
    window_matches: int = DEFAULT_WINDOW_MATCHES,
    tool_context: Any | None = None,
) -> dict[str, Any]:
    resolved_account_id = _resolve_account_id(account_id, tool_context=tool_context)
    summary = summarize_account(_settings(), resolved_account_id, window_matches=window_matches)
    if summary is None:
        raise ValueError(f"No recent local summary is available for account {resolved_account_id}.")
    return account_summary_payload(_settings(), summary)


def _account_resolution_error_payload(note: str) -> dict[str, Any]:
    accounts = list_tracked_accounts(_settings())
    status = (
        "account_selection_required"
        if len(accounts) > 1
        else "account_required"
    )
    return {
        "source": "local_sqlite",
        "available": False,
        "status": status,
        "account_id": None,
        "accounts": accounts,
        "note": note,
    }


def list_available_accounts() -> dict[str, Any]:
    """List synced player accounts available to the coach.

    Use this when the user asks which account is active or when the agent needs
    to know what local player data is available before answering.
    """

    accounts = list_tracked_accounts(_settings())
    return {
        "source": "local_sqlite",
        "accounts": accounts,
        "default_account_id": int(accounts[0]["account_id"]) if accounts else None,
    }


def get_player_profile(
    account_id: int | None = None,
    window_matches: int = DEFAULT_WINDOW_MATCHES,
    tool_context: Any | None = None,
) -> dict[str, Any]:
    """Return a recent local player snapshot for coaching.

    Use this for broad coaching questions about current form, win rate, K/D/A,
    recent sample size, or when a specialist agent needs the player's overall
    context before answering.
    """

    try:
        payload = _summary_payload(account_id=account_id, window_matches=window_matches, tool_context=tool_context)
    except ValueError as exc:
        return _account_resolution_error_payload(str(exc))
    return {
        "source": "local_sqlite",
        "available": True,
        "account_id": payload["account_id"],
        "window_matches": window_matches,
        "summary": payload,
    }


def _account_match_total(account_id: int) -> int | None:
    for account in list_tracked_accounts(_settings()):
        if int(account.get("account_id") or 0) == account_id:
            return int(account.get("matches") or 0)
    return None


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "page"


def _knowledge_heading(path: Path) -> str:
    body = path.read_text(encoding="utf-8")
    return next(
        (line.lstrip("#").strip() for line in body.splitlines() if line.strip().startswith("#")),
        path.stem.replace("-", " ").replace("_", " ").title(),
    )


def _clean_knowledge_line(line: str) -> str:
    cleaned = line.strip()
    if cleaned.startswith("-"):
        cleaned = cleaned[1:].strip()
    return cleaned


def _knowledge_content_lines(body: str) -> list[str]:
    lines: list[str] = []
    for raw_line in body.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        cleaned = _clean_knowledge_line(stripped)
        lowered = cleaned.lower()
        if not cleaned:
            continue
        if lowered == "imported reference":
            continue
        if lowered == "reference extract:":
            continue
        if lowered.startswith(("kind:", "source:", "url:", "imported_at:", "path:")):
            continue
        if lowered.startswith("use this when "):
            continue
        if cleaned.endswith(":") and len(cleaned.split()) <= 5:
            continue
        lines.append(cleaned)
    return lines


def _local_group_files(group: str) -> list[Path]:
    group_root = _knowledge_root() / group
    if not group_root.exists():
        return []
    return sorted(path for path in group_root.glob("*.md") if path.is_file())


def _import_group_files(group: str) -> list[Path]:
    group_root = _knowledge_root() / "_imports" / "wiki" / group
    if not group_root.exists():
        return []
    return sorted(path for path in group_root.glob("*.md") if path.is_file())


def _local_reference_titles(group: str) -> list[str]:
    return [_knowledge_heading(path) for path in _local_group_files(group) if path.stem != "index"]


def _import_reference_titles(group: str) -> list[str]:
    return [_knowledge_heading(path) for path in _import_group_files(group)]


def _local_reference_page(group: str, requested_title: str) -> dict[str, Any] | None:
    normalized_requested = requested_title.strip().casefold()
    if not normalized_requested:
        return None

    for path in _local_group_files(group):
        if path.stem == "index":
            continue
        heading = _knowledge_heading(path)
        if heading.casefold() != normalized_requested:
            continue

        body = path.read_text(encoding="utf-8")
        non_heading_lines = _knowledge_content_lines(body)
        excerpt = " ".join(non_heading_lines[:6]).strip()
        return {
            "title": heading,
            "pageid": None,
            "extract": excerpt[:420],
            "url": str(path.relative_to(_settings().project_root)),
        }

    return None


def _import_reference_page(group: str, requested_title: str) -> dict[str, Any] | None:
    normalized_requested = requested_title.strip().casefold()
    if not normalized_requested:
        return None

    for path in _import_group_files(group):
        heading = _knowledge_heading(path)
        if heading.casefold() != normalized_requested:
            continue

        body = path.read_text(encoding="utf-8")
        non_heading_lines = _knowledge_content_lines(body)
        excerpt = " ".join(non_heading_lines[:8]).strip()
        return {
            "title": heading,
            "pageid": None,
            "extract": excerpt[:560],
            "url": str(path.relative_to(_settings().project_root)),
        }

    return None


def _read_cached_json(path: Path, *, max_age_s: int) -> dict[str, Any] | None:
    if not path.exists():
        return None

    age_s = time.time() - path.stat().st_mtime
    if age_s > max_age_s:
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _write_cached_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _wiki_api_request(params: dict[str, Any], *, cache_key: str, max_age_s: int) -> dict[str, Any]:
    cache_path = _wiki_cache_root() / f"{cache_key}.json"
    cached = _read_cached_json(cache_path, max_age_s=max_age_s)
    if cached is not None:
        return cached

    query = urlencode({**params, "format": "json"}, doseq=True)
    request = Request(
        f"{WIKI_API_URL}?{query}",
        headers={
            "User-Agent": WIKI_USER_AGENT,
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=15) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))

    _write_cached_json(cache_path, payload)
    return payload


def _page_extract_from_payload(payload: dict[str, Any], *, requested_title: str) -> dict[str, Any] | None:
    pages = ((payload or {}).get("query") or {}).get("pages") or {}
    if not isinstance(pages, dict):
        return None

    requested_normalized = requested_title.strip().casefold()
    candidates = list(pages.values())
    exact = next(
        (
            page
            for page in candidates
            if str(page.get("title") or "").strip().casefold() == requested_normalized
        ),
        None,
    )
    page = exact or next((page for page in candidates if "missing" not in page), None)
    if not page or "missing" in page:
        return None

    return {
        "title": str(page.get("title") or requested_title),
        "pageid": page.get("pageid"),
        "extract": str(page.get("extract") or "").strip(),
        "url": f"https://deadlock.wiki/{str(page.get('title') or requested_title).replace(' ', '_')}",
    }


def _normalize_reference_title(title: str, alias_map: dict[str, str]) -> str:
    raw = title.strip()
    if not raw:
        return raw
    return alias_map.get(raw.casefold(), raw)


def _wiki_page_extract(title: str) -> dict[str, Any] | None:
    normalized_title = title.strip()
    if not normalized_title:
        return None

    payload = _wiki_api_request(
        {
            "action": "query",
            "prop": "extracts",
            "explaintext": 1,
            "exintro": 1,
            "titles": normalized_title,
        },
        cache_key=f"extract-{_slugify(normalized_title)}",
        max_age_s=WIKI_PAGE_EXTRACT_MAX_AGE_S,
    )
    return _page_extract_from_payload(payload, requested_title=normalized_title)


def _wiki_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    if not query.strip():
        return []

    payload = _wiki_api_request(
        {
            "action": "query",
            "list": "search",
            "srsearch": query.strip(),
            "srlimit": max(1, min(limit, 10)),
        },
        cache_key=f"search-{_slugify(query)}-{max(1, min(limit, 10))}",
        max_age_s=12 * 60 * 60,
    )
    rows = ((payload or {}).get("query") or {}).get("search") or []
    return [
        {
            "title": str(row.get("title") or ""),
            "pageid": row.get("pageid"),
            "snippet": re.sub(r"<[^>]+>", "", str(row.get("snippet") or "")).strip(),
            "url": f"https://deadlock.wiki/{str(row.get('title') or '').replace(' ', '_')}",
        }
        for row in rows
        if row.get("title")
    ]


def _should_keep_category_title(row: dict[str, Any], title: str) -> bool:
    return bool(
        title
        and row.get("ns", 0) == 0
        and "/" not in title
        and title not in {"Heroes", "Items"}
    )


def _wiki_category_members(category_title: str, limit: int = 200) -> list[str]:
    requested_limit = max(1, limit)
    page_size = 200
    continue_token: dict[str, Any] = {}
    titles: list[str] = []
    seen: set[str] = set()

    while True:
        batch_limit = min(page_size, requested_limit - len(titles))
        if batch_limit <= 0:
            break

        payload = _wiki_api_request(
            {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": category_title,
                "cmlimit": batch_limit,
                **continue_token,
            },
            cache_key=(
                f"category-{_slugify(category_title)}-{requested_limit}-"
                f"{_slugify(json.dumps(continue_token, sort_keys=True)) or 'start'}"
            ),
            max_age_s=WIKI_CATEGORY_MAX_AGE_S,
        )
        rows = ((payload or {}).get("query") or {}).get("categorymembers") or []
        for row in rows:
            title = str(row.get("title") or "")
            if not _should_keep_category_title(row, title) or title in seen:
                continue
            seen.add(title)
            titles.append(title)
            if len(titles) >= requested_limit:
                return titles

        next_continue = (payload or {}).get("continue") or {}
        if not next_continue:
            break
        continue_token = next_continue

    return titles


def get_hero_pool_analysis(
    account_id: int | None = None,
    window_matches: int = DEFAULT_WINDOW_MATCHES,
    full_sample: bool = False,
    tool_context: Any | None = None,
) -> dict[str, Any]:
    """Return the player's recent hero pool and hero usage mix.

    Use this for questions about what heroes the player usually plays, hero pool
    concentration, recent main hero, and hero-specific sample distribution.
    Set `full_sample=True` if the user is asking about all locally synced match
    history rather than just the current window.
    """

    try:
        resolved_account_id = _resolve_account_id(account_id, tool_context=tool_context)
    except ValueError as exc:
        return _account_resolution_error_payload(str(exc))
    effective_window = window_matches
    if full_sample:
        effective_window = max(_account_match_total(resolved_account_id) or window_matches, window_matches)

    payload = _summary_payload(account_id=resolved_account_id, window_matches=effective_window, tool_context=tool_context)
    hero_rows = payload.get("hero_performance", [])
    return {
        "source": "local_sqlite",
        "available": True,
        "account_id": payload["account_id"],
        "window_matches": effective_window,
        "sample_scope": "full_local_sample" if full_sample else "recent_window",
        "hero_pool": hero_rows,
        "top_hero": payload.get("focus", {}).get("top_hero"),
        "recent_form": payload.get("focus", {}).get("recent_form"),
    }


def _aggregate_item_timings_from_paths(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aggregate: dict[str, dict[str, Any]] = {}
    for match in matches:
        for item in match.get("items", []):
            label = str(item.get("item_label") or "").strip()
            item_id = item.get("item_id")
            if not label or item_id is None:
                continue

            current = aggregate.setdefault(
                label,
                {
                    "item_id": int(item_id),
                    "item_label": label,
                    "purchases": 0,
                    "total_bought_at_s": 0.0,
                },
            )
            current["purchases"] += 1
            current["total_bought_at_s"] += float(item.get("bought_at_s") or 0.0)

    rows = [
        {
            "item_id": row["item_id"],
            "item_label": row["item_label"],
            "purchases": row["purchases"],
            "avg_bought_at_s": row["total_bought_at_s"] / max(row["purchases"], 1),
        }
        for row in aggregate.values()
    ]
    rows.sort(key=lambda row: (-row["purchases"], row["avg_bought_at_s"], row["item_label"]))
    return rows


def _build_spine_from_paths(matches: list[dict[str, Any]], prefix_items: int = 3) -> list[str]:
    branch_counts = Counter(
        tuple(item.get("item_label") for item in match.get("items", [])[:prefix_items] if item.get("item_label"))
        for match in matches
        if match.get("items")
    )
    branch_counts.pop((), None)
    if not branch_counts:
        return []

    branch, _count = branch_counts.most_common(1)[0]
    return list(branch)


def get_build_analysis(
    account_id: int | None = None,
    hero_name: str | None = None,
    window_matches: int = DEFAULT_WINDOW_MATCHES,
    tool_context: Any | None = None,
) -> dict[str, Any]:
    """Return the player's recent build spine and item timing aggregates.

    Use this for build-path, first-item, item-timing, or repeat-item questions.
    If a hero is mentioned, pass `hero_name` so the result stays hero-specific.
    """

    try:
        payload = _summary_payload(account_id=account_id, window_matches=window_matches, tool_context=tool_context)
    except ValueError as exc:
        return _account_resolution_error_payload(str(exc))
    resolved_account_id = payload["account_id"]

    hero_filter = (hero_name or "").strip() or None
    if hero_filter:
        recent_paths = get_recent_item_paths(
            account_id=resolved_account_id,
            hero_name=hero_filter,
            window_matches=max(window_matches, 5),
            items_per_match=16,
            tool_context=tool_context,
        )
        matches = recent_paths.get("matches", [])
        if matches:
            item_rows = _aggregate_item_timings_from_paths(matches)
            build_spine = _build_spine_from_paths(matches) or [row["item_label"] for row in item_rows[:3]]
            top_item = item_rows[0] if item_rows else None
            return {
                "source": "local_sqlite",
                "available": True,
                "account_id": resolved_account_id,
                "window_matches": window_matches,
                "hero_filter": hero_filter,
                "matched_matches": len(matches),
                "item_timings": item_rows,
                "build_spine": build_spine,
                "top_item": top_item,
            }

    item_rows = payload.get("item_timings", [])
    spine = [row["item_label"] for row in item_rows[:3]]
    return {
        "source": "local_sqlite",
        "available": True,
        "account_id": resolved_account_id,
        "window_matches": window_matches,
        "hero_filter": hero_filter,
        "matched_matches": None,
        "item_timings": item_rows,
        "build_spine": spine,
        "top_item": payload.get("focus", {}).get("top_item"),
        "note": "No hero-specific build slice matched that filter." if hero_filter else None,
    }


def get_comparison_context(
    account_id: int | None = None,
    window_matches: int = DEFAULT_WINDOW_MATCHES,
    tool_context: Any | None = None,
) -> dict[str, Any]:
    """Return the local comparison anchor for later player-vs-meta analysis.

    Use this when the question is about stronger players, meta comparisons, or
    how the player's current hero/build should be compared externally.

    This prototype only returns the player's local comparison anchors. External
    cohort joins are intentionally deferred until statlocker and broader meta
    tooling are wired in.
    """

    resolved_account_id = _resolve_optional_account_id(account_id, tool_context=tool_context)
    if resolved_account_id is None:
        accounts = list_tracked_accounts(_settings())
        return {
            "source": "local_sqlite",
            "available": False,
            "account_id": None,
            "window_matches": window_matches,
            "top_hero": None,
            "top_item": None,
            "status": "account_selection_required",
            "accounts": accounts,
            "note": "Multiple synced accounts are available. Use the active player account before making a player-vs-meta comparison.",
        }

    payload = _summary_payload(account_id=resolved_account_id, window_matches=window_matches, tool_context=tool_context)
    return {
        "source": "local_sqlite",
        "available": True,
        "account_id": payload["account_id"],
        "window_matches": window_matches,
        "top_hero": payload.get("focus", {}).get("top_hero"),
        "top_item": payload.get("focus", {}).get("top_item"),
        "status": "external_meta_not_wired",
        "note": "Use these local anchors now; external cohort and pro comparison data will come from statlocker later.",
    }


def build_coaching_report(account_id: int | None = None, window_matches: int = DEFAULT_WINDOW_MATCHES) -> dict[str, Any]:
    """Assemble a compact coaching report from local evidence.

    Use this for 'what should I focus on', report generation, or experiment
    planning questions.
    """

    try:
        payload = _summary_payload(account_id=account_id, window_matches=window_matches, tool_context=tool_context)
    except ValueError as exc:
        return _account_resolution_error_payload(str(exc))
    hero = payload.get("focus", {}).get("top_hero")
    item = payload.get("focus", {}).get("top_item")

    keep = (
        f"Keep the pool narrow around {hero['hero_label']} for now."
        if hero
        else "Keep the pool narrow until a clear main hero emerges."
    )
    watch = (
        f"Watch whether {item['item_label']} is arriving on time."
        if item
        else "Watch whether your early build checkpoint is arriving on time."
    )
    test = (
        f"Run one small experiment around {item['item_label']} timing."
        if item
        else "Run one small build-timing experiment instead of changing everything at once."
    )

    return {
        "source": "local_sqlite",
        "account_id": payload["account_id"],
        "window_matches": window_matches,
        "report": {
            "keep": keep,
            "watch": watch,
            "test": test,
        },
        "summary": payload,
    }


def _format_reference_date(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    return f"{moment.strftime('%B')} {moment.day}, {moment.year}"


def _rank_scoped_min_matches(min_matches: int, rank_filter: Any | None) -> int:
    effective_min_matches = max(1, min_matches)
    if rank_filter is None or effective_min_matches < 100000:
        return effective_min_matches
    if rank_filter.min_badge == rank_filter.max_badge:
        return 1000
    return 10000


def _clean_reference_excerpt(text: str | None, *, max_chars: int = 280) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return ""
    return cleaned[:max_chars].rstrip()


def _strip_html(text: str | None) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", str(text or ""))
    cleaned = cleaned.replace("&quot;", '"').replace("&#39;", "'").replace("&amp;", "&")
    return re.sub(r"\s+", " ", cleaned).strip()


def _live_patch_matches(query: str, limit: int) -> list[dict[str, Any]]:
    settings = _settings()
    client = DeadlockApiClient(settings)
    _url, payload = client.fetch_json("/v2/patches")
    rows = payload if isinstance(payload, list) else []
    normalized_query = query.strip().casefold()
    matches: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "Untitled Patch").strip()
        excerpt = _clean_reference_excerpt(_strip_html(row.get("content")), max_chars=420)
        haystack = f"{title}\n{excerpt}".casefold()
        if normalized_query and normalized_query not in haystack:
            continue
        matches.append(
            {
                "source": str(row.get("source") or "deadlock_api_live"),
                "title": title,
                "published_at": row.get("pub_date"),
                "published_at_label": _format_reference_date(row.get("pub_date")),
                "link": str(row.get("link") or ""),
                "excerpt": excerpt,
            }
        )
        if len(matches) >= max(1, min(limit, 10)):
            break
    return matches


def _hero_stats_rows(
    limit: int,
    min_matches: int,
    min_average_badge: int | None = None,
    max_average_badge: int | None = None,
    rank_filter: str | None = None,
) -> dict[str, Any]:
    settings = _settings()
    client = DeadlockApiClient(settings)
    query_params = {
        "min_average_badge": min_average_badge,
        "max_average_badge": max_average_badge,
    }
    _url, payload = client.fetch_json("/v1/analytics/hero-stats", params=query_params)
    rows = payload if isinstance(payload, list) else []
    normalized: list[dict[str, Any]] = []
    total_matches = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        matches = int(row.get("matches") or 0)
        wins = int(row.get("wins") or 0)
        losses = int(row.get("losses") or 0)
        hero_id = int(row.get("hero_id") or 0)
        if matches <= 0 or hero_id <= 0:
            continue
        total_matches += matches
        normalized.append(
            {
                "hero_id": hero_id,
                "hero_label": hero_label(settings, hero_id, client=client),
                "matches": matches,
                "wins": wins,
                "losses": losses,
                "win_rate": round(100.0 * wins / max(matches, 1), 1),
            }
        )

    for row in normalized:
        row["pick_rate"] = round(100.0 * row["matches"] / max(total_matches, 1), 2)

    top_pickrate = sorted(
        normalized,
        key=lambda row: (-row["pick_rate"], -row["matches"], row["hero_label"]),
    )[: max(1, limit)]
    top_winrate = sorted(
        [row for row in normalized if row["matches"] >= max(1, min_matches)],
        key=lambda row: (-row["win_rate"], -row["matches"], row["hero_label"]),
    )[: max(1, limit)]
    return {
        "source": "deadlock_api_live",
        "time_window": "default_api_window",
        "sample_scope": "global_public_matches",
        "query_params": query_params,
        "total_hero_picks": total_matches,
        "top_pickrate": top_pickrate,
        "top_winrate": top_winrate,
        "min_matches_for_winrate": max(1, min_matches),
        "rank_filter": {
            "name": rank_filter,
            "min_average_badge": min_average_badge,
            "max_average_badge": max_average_badge,
            "scope_note": "Badge filters apply to the average badge across both teams in the match.",
        }
        if rank_filter or min_average_badge is not None or max_average_badge is not None
        else None,
    }


def _item_stats_rows(
    limit: int,
    min_matches: int,
    min_average_badge: int | None = None,
    max_average_badge: int | None = None,
    rank_filter: str | None = None,
) -> dict[str, Any]:
    settings = _settings()
    client = DeadlockApiClient(settings)
    params: dict[str, Any] = {}
    if min_average_badge is not None:
        params["min_average_badge"] = min_average_badge
    if max_average_badge is not None:
        params["max_average_badge"] = max_average_badge
    _url, payload = client.fetch_json("/v1/analytics/item-stats", params=params or None)
    rows = payload if isinstance(payload, list) else []
    normalized: list[dict[str, Any]] = []
    total_matches = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        matches = int(row.get("matches") or 0)
        wins = int(row.get("wins") or 0)
        losses = int(row.get("losses") or 0)
        item_id = int(row.get("item_id") or 0)
        if matches <= 0 or item_id <= 0:
            continue
        total_matches += matches
        normalized.append(
            {
                "item_id": item_id,
                "item_label": item_label(settings, item_id),
                "matches": matches,
                "wins": wins,
                "losses": losses,
                "purchases": None
                if row.get("purchases") is None and row.get("total_purchases") is None and row.get("item_purchases") is None
                else int(row.get("purchases") or row.get("total_purchases") or row.get("item_purchases") or 0),
                "players": None if row.get("players") is None and row.get("unique_players") is None else int(row.get("players") or row.get("unique_players") or 0),
                "avg_bought_at_s": None
                if row.get("avg_bought_at_s") is None and row.get("average_bought_at_s") is None and row.get("avg_purchase_time_s") is None
                else float(row.get("avg_bought_at_s") or row.get("average_bought_at_s") or row.get("avg_purchase_time_s") or 0.0),
                "win_rate": round(100.0 * wins / max(matches, 1), 1),
            }
        )

    for row in normalized:
        row["usage_share"] = round(100.0 * row["matches"] / max(total_matches, 1), 2)

    top_usage = sorted(
        normalized,
        key=lambda row: (-row["matches"], row["item_label"]),
    )[: max(1, limit)]
    top_winrate = sorted(
        [row for row in normalized if row["matches"] >= max(1, min_matches)],
        key=lambda row: (-row["win_rate"], -row["matches"], row["item_label"]),
    )[: max(1, limit)]
    return {
        "source": "deadlock_api_live",
        "time_window": "default_api_window",
        "sample_scope": "global_public_matches",
        "total_item_match_rows": total_matches,
        "top_usage": top_usage,
        "top_winrate": top_winrate,
        "min_matches_for_winrate": max(1, min_matches),
        "rank_filter": {
            "name": rank_filter,
            "min_average_badge": min_average_badge,
            "max_average_badge": max_average_badge,
            "scope_note": "Badge filters apply to the average badge across both teams in the match.",
        }
        if rank_filter or min_average_badge is not None or max_average_badge is not None
        else None,
    }


def _format_game_time_bucket(value: int) -> str:
    if value <= 100:
        return f"{value}%"
    minutes, seconds = divmod(max(value, 0), 60)
    return f"{minutes}:{seconds:02d}"


def _item_flow_rows(
    hero_name: str | None,
    stage_limit: int,
    transition_limit: int,
    min_matches: int,
    min_average_badge: int | None = None,
    max_average_badge: int | None = None,
    rank_filter: str | None = None,
) -> dict[str, Any]:
    settings = _settings()
    client = DeadlockApiClient(settings)
    params: dict[str, Any] = {"min_matches": max(1, min_matches)}
    if min_average_badge is not None:
        params["min_average_badge"] = min_average_badge
    if max_average_badge is not None:
        params["max_average_badge"] = max_average_badge
    if hero_name:
        from deadlock_coach.asset_service import resolve_hero_id

        hero_id = resolve_hero_id(settings, hero_name, client=client)
        if hero_id is None:
            raise ValueError(f"Unknown hero `{hero_name}`.")
        params["hero_id"] = hero_id

    _url, payload = client.fetch_json("/v1/analytics/item-flow-stats", params=params)
    if not isinstance(payload, dict):
        return {"source": "deadlock_api_live", "available": False, "error": "Unexpected item-flow response shape."}

    nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
    edges = payload.get("edges") if isinstance(payload.get("edges"), list) else []
    stages: dict[int, list[dict[str, Any]]] = {}
    for row in nodes:
        if not isinstance(row, dict):
            continue
        column = int(row.get("column") or 0)
        bucket = stages.setdefault(column, [])
        if len(bucket) >= max(1, stage_limit):
            continue
        item_id = int(row.get("item_id") or 0)
        matches = int(row.get("matches") or 0)
        wins = int(row.get("wins") or 0)
        if item_id <= 0 or matches <= 0:
            continue
        bucket.append(
            {
                "item_id": item_id,
                "item_label": item_label(settings, item_id, client=client),
                "matches": matches,
                "wins": wins,
                "losses": int(row.get("losses") or 0),
                "win_rate": round(100.0 * wins / max(matches, 1), 1),
                "adjusted_win_rate": None if row.get("adjusted_win_rate") is None else float(row.get("adjusted_win_rate")),
                "avg_net_worth_at_buy": None if row.get("avg_net_worth_at_buy") is None else float(row.get("avg_net_worth_at_buy")),
            }
        )

    top_transitions = []
    for row in sorted(
        [edge for edge in edges if isinstance(edge, dict)],
        key=lambda edge: (-int(edge.get("matches") or 0), int(edge.get("from_column") or 0)),
    )[: max(1, transition_limit)]:
        from_item_id = int(row.get("from_item_id") or 0)
        to_item_id = int(row.get("to_item_id") or 0)
        matches = int(row.get("matches") or 0)
        wins = int(row.get("wins") or 0)
        if from_item_id <= 0 or to_item_id <= 0 or matches <= 0:
            continue
        top_transitions.append(
            {
                "from_column": int(row.get("from_column") or 0),
                "from_item_id": from_item_id,
                "from_item_label": item_label(settings, from_item_id, client=client),
                "to_item_id": to_item_id,
                "to_item_label": item_label(settings, to_item_id, client=client),
                "matches": matches,
                "wins": wins,
                "losses": int(row.get("losses") or 0),
                "win_rate": round(100.0 * wins / max(matches, 1), 1),
            }
        )

    return {
        "source": "deadlock_api_live",
        "available": True,
        "time_window": "default_api_window",
        "hero_filter": hero_name,
        "rank_filter": {
            "name": rank_filter,
            "min_average_badge": min_average_badge,
            "max_average_badge": max_average_badge,
            "scope_note": "Badge filters apply to the average badge across both teams in the match.",
        }
        if rank_filter or min_average_badge is not None or max_average_badge is not None
        else None,
        "summary": payload.get("summary"),
        "baseline": payload.get("baseline"),
        "reached_per_column": payload.get("reached_per_column") or [],
        "stages": [
            {"column": column, "top_items": items}
            for column, items in sorted(stages.items(), key=lambda item: item[0])
        ],
        "top_transitions": top_transitions,
        "min_matches": max(1, min_matches),
    }


def _player_performance_curve_rows(account_id: int, resolution: int) -> dict[str, Any]:
    settings = _settings()
    client = DeadlockApiClient(settings)
    _url, payload = client.fetch_json(
        "/v1/analytics/player-performance-curve",
        params={"account_ids": [account_id], "resolution": max(0, min(resolution, 100))},
    )
    rows = payload if isinstance(payload, list) else []
    points = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        game_time = int(row.get("game_time") or 0)
        points.append(
            {
                "game_time": game_time,
                "game_time_label": _format_game_time_bucket(game_time),
                "net_worth_avg": None if row.get("net_worth_avg") is None else float(row.get("net_worth_avg")),
                "net_worth_std": None if row.get("net_worth_std") is None else float(row.get("net_worth_std")),
                "kills_avg": None if row.get("kills_avg") is None else float(row.get("kills_avg")),
                "kills_std": None if row.get("kills_std") is None else float(row.get("kills_std")),
                "deaths_avg": None if row.get("deaths_avg") is None else float(row.get("deaths_avg")),
                "deaths_std": None if row.get("deaths_std") is None else float(row.get("deaths_std")),
                "assists_avg": None if row.get("assists_avg") is None else float(row.get("assists_avg")),
                "assists_std": None if row.get("assists_std") is None else float(row.get("assists_std")),
            }
        )

    checkpoints = []
    if points:
        checkpoints.append(points[0])
        if len(points) > 2:
            checkpoints.append(points[len(points) // 2])
        if len(points) > 1:
            checkpoints.append(points[-1])
    deduped = []
    seen = set()
    for point in checkpoints:
        if point["game_time"] in seen:
            continue
        seen.add(point["game_time"])
        deduped.append(point)

    return {
        "source": "deadlock_api_live",
        "account_id": account_id,
        "resolution": max(0, min(resolution, 100)),
        "points": points,
        "checkpoints": deduped,
    }


def get_patch_context(query: str = "", limit: int = 3) -> dict[str, Any]:
    """Return locally synced patch-feed context for grounded patch answers.

    Use this when the user asks what changed in a patch, whether a patch claim
    is grounded in local data, or when the coach needs a local patch anchor
    before answering patch/meta questions.
    """

    settings = _settings()
    if not settings.warehouse_db_path.exists():
        try:
            matches = _live_patch_matches(query, limit)
        except RuntimeError as exc:
            return {
                "source": "local_sqlite",
                "available": False,
                "query": query,
                "matches": [],
                "note": f"No local warehouse exists yet, and live patch lookup failed: {exc}",
            }
        return {
            "source": "deadlock_api_live",
            "available": bool(matches),
            "query": query,
            "matches": matches,
            "note": None if matches else "Live patch feed returned no matching entries.",
        }

    search_query = query.strip()
    normalized_limit = max(1, min(limit, 10))
    with closing(_connect(settings.warehouse_db_path)) as connection:
        if search_query:
            pattern = f"%{search_query.lower()}%"
            rows = connection.execute(
                """
                SELECT
                    source,
                    title,
                    published_at,
                    link,
                    content_excerpt
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
                SELECT
                    source,
                    title,
                    published_at,
                    link,
                    content_excerpt
                FROM patch_event
                ORDER BY published_at DESC, title ASC
                LIMIT ?
                """,
                (normalized_limit,),
            ).fetchall()

    matches = [
        {
            "source": str(row["source"] or "unknown"),
            "title": str(row["title"] or "Untitled Patch"),
            "published_at": row["published_at"],
            "published_at_label": _format_reference_date(row["published_at"]),
            "link": str(row["link"] or ""),
            "excerpt": _clean_reference_excerpt(row["content_excerpt"]),
        }
        for row in rows
    ]
    if matches:
        return {
            "source": "local_sqlite",
            "available": True,
            "query": query,
            "matches": matches,
        }

    try:
        live_matches = _live_patch_matches(query, limit)
    except RuntimeError as exc:
        note = (
            f"No synced patch entries matched `{search_query}`, and live patch lookup failed: {exc}"
            if search_query
            else f"No synced patch events were found in the local warehouse, and live patch lookup failed: {exc}"
        )
        return {
            "source": "local_sqlite",
            "available": False,
            "query": query,
            "matches": [],
            "note": note,
        }

    if live_matches:
        return {
            "source": "deadlock_api_live",
            "available": True,
            "query": query,
            "matches": live_matches,
            "note": "Using the live patch feed because no local synced patch entry matched.",
        }

    note = (
        f"No synced patch entries matched `{search_query}`."
        if search_query
        else "No synced patch events were found in the local warehouse."
    )
    return {
        "source": "local_sqlite",
        "available": False,
        "query": query,
        "matches": [],
        "note": note,
    }


def get_global_hero_stats(limit: int = 5, min_matches: int = 100000, rank_name: str | None = None) -> dict[str, Any]:
    """Return a global hero pick-rate and win-rate snapshot.

    Use this for questions like "what hero has the highest pickrate right now",
    "highest winrate right now", or broad global meta questions that cannot be
    answered from one player's local matches.
    Pass `rank_name` to filter to a badge band like `Eternus` or a subtier
    slice like `Eternus 6`.
    """
    settings = _settings()
    rank_filter = resolve_rank_badge_range(settings, rank_name) if rank_name else None
    effective_min_matches = _rank_scoped_min_matches(min_matches, rank_filter)
    min_average_badge = rank_filter.min_badge if rank_filter is not None else None
    max_average_badge = rank_filter.max_badge if rank_filter is not None else None
    local_result = read_latest_global_hero_stats(
        settings,
        limit=max(1, min(limit, 10)),
        min_matches=effective_min_matches,
        min_average_badge=min_average_badge,
        max_average_badge=max_average_badge,
    )
    if local_result is not None:
        if rank_filter is not None:
            local_result["rank_filter"] = {
                "name": rank_filter.name,
                "tier": rank_filter.tier,
                "min_average_badge": rank_filter.min_badge,
                "max_average_badge": rank_filter.max_badge,
                "scope_note": "Badge filters apply to the average badge across both teams in the match.",
            }
        return local_result
    return _hero_stats_rows(
        limit=max(1, min(limit, 10)),
        min_matches=effective_min_matches,
        min_average_badge=min_average_badge,
        max_average_badge=max_average_badge,
        rank_filter=rank_filter.name if rank_filter is not None else None,
    )


def get_global_item_stats(limit: int = 5, min_matches: int = 100000, rank_name: str | None = None) -> dict[str, Any]:
    """Return a global item usage and win-rate snapshot.

    Use this for questions about which items are most common right now, which
    items are overperforming globally, or when current item-meta context helps
    frame a build discussion beyond one player's local sample.
    Pass `rank_name` to filter to a badge band like `Eternus` or `Eternus 6`.
    """
    settings = _settings()
    rank_filter = resolve_rank_badge_range(settings, rank_name) if rank_name else None
    effective_min_matches = _rank_scoped_min_matches(min_matches, rank_filter)
    min_average_badge = rank_filter.min_badge if rank_filter is not None else None
    max_average_badge = rank_filter.max_badge if rank_filter is not None else None
    local_result = read_latest_global_item_stats(
        settings,
        limit=max(1, min(limit, 10)),
        min_matches=effective_min_matches,
        min_average_badge=min_average_badge,
        max_average_badge=max_average_badge,
    )
    if local_result is not None:
        if rank_filter is not None:
            local_result["rank_filter"] = {
                "name": rank_filter.name,
                "tier": rank_filter.tier,
                "min_average_badge": rank_filter.min_badge,
                "max_average_badge": rank_filter.max_badge,
                "scope_note": "Badge filters apply to the average badge across both teams in the match.",
            }
        return local_result
    return _item_stats_rows(
        limit=max(1, min(limit, 10)),
        min_matches=effective_min_matches,
        min_average_badge=min_average_badge,
        max_average_badge=max_average_badge,
        rank_filter=rank_filter.name if rank_filter is not None else None,
    )


def get_global_item_flow(
    hero_name: str | None = None,
    stage_limit: int = 3,
    transition_limit: int = 6,
    min_matches: int = 20,
    rank_name: str | None = None,
) -> dict[str, Any]:
    """Return a global build-branch summary from item-flow analytics.

    Use this when the answer needs common stage-by-stage item branches or
    repeated transition patterns for a hero or the broader item ecosystem.
    Pass `rank_name` to focus the build flow on a stronger rank cohort like
    `Eternus 6`.
    """
    settings = _settings()
    rank_filter = resolve_rank_badge_range(settings, rank_name) if rank_name else None
    min_average_badge = rank_filter.min_badge if rank_filter is not None else None
    max_average_badge = rank_filter.max_badge if rank_filter is not None else None
    local_result = read_latest_item_flow_summary(
        settings,
        hero_name=hero_name,
        stage_limit=max(1, min(stage_limit, 5)),
        transition_limit=max(1, min(transition_limit, 10)),
        min_average_badge=min_average_badge,
        max_average_badge=max_average_badge,
    )
    if local_result is not None:
        if rank_filter is not None:
            local_result["rank_filter"] = {
                "name": rank_filter.name,
                "tier": rank_filter.tier,
                "min_average_badge": rank_filter.min_badge,
                "max_average_badge": rank_filter.max_badge,
                "scope_note": "Badge filters apply to the average badge across both teams in the match.",
            }
        return local_result
    try:
        return _item_flow_rows(
            hero_name=hero_name,
            stage_limit=max(1, min(stage_limit, 5)),
            transition_limit=max(1, min(transition_limit, 10)),
            min_matches=max(1, min_matches),
            min_average_badge=min_average_badge,
            max_average_badge=max_average_badge,
            rank_filter=rank_filter.name if rank_filter is not None else None,
        )
    except RuntimeError as exc:
        return {
            "source": "deadlock_api_live",
            "available": False,
            "hero_filter": hero_name,
            "rank_filter": (
                {
                    "name": rank_filter.name,
                    "tier": rank_filter.tier,
                    "min_average_badge": rank_filter.min_badge,
                    "max_average_badge": rank_filter.max_badge,
                    "scope_note": "Badge filters apply to the average badge across both teams in the match.",
                }
                if rank_filter is not None
                else None
            ),
            "note": f"Global item-flow analytics are temporarily unavailable for this query: {exc}",
            "stages": [],
            "top_transitions": [],
        }


def get_player_performance_curve(
    account_id: int | None = None,
    resolution: int = 10,
    tool_context: Any | None = None,
) -> dict[str, Any]:
    """Return a player's performance curve over game time.

    Use this when the answer needs to show where a player's games tend to swing
    over time rather than only giving flat recent aggregates.
    """

    try:
        resolved_account_id = _resolve_account_id(account_id, tool_context=tool_context)
    except ValueError as exc:
        return _account_resolution_error_payload(str(exc))
    local_result = read_latest_player_performance_curve(
        _settings(),
        account_id=resolved_account_id,
        resolution=max(0, min(resolution, 100)),
    )
    if local_result is not None:
        enriched = {
            **local_result,
            "checkpoints": [
                {
                    **point,
                    "game_time_label": _format_game_time_bucket(int(point["game_time"])),
                }
                for point in local_result.get("checkpoints", [])
            ],
        }
        return enriched
    return _player_performance_curve_rows(account_id=resolved_account_id, resolution=max(0, min(resolution, 100)))


def search_knowledge_base(query: str, limit: int = 3) -> dict[str, Any]:
    """Search the local Deadlock knowledge base.

    Use this when the user asks for theory, heuristics, matchup notes, coaching
    principles, or any guidance that may live in local knowledge files instead
    of player telemetry.
    """

    search_query = query.strip()
    if not search_query:
        return {"source": "knowledge_base", "matches": []}

    root = _knowledge_root()
    if not root.exists():
        return {
            "source": "knowledge_base",
            "matches": [],
            "note": "The knowledge-base folder exists conceptually but has not been filled with notes yet.",
        }

    return {
        "source": "knowledge_base",
        "query": query,
        "matches": search_local_knowledge(_settings(), search_query, limit=limit, source_filter="knowledge_base"),
    }


def retrieve_game_knowledge(query: str, limit: int = 4) -> dict[str, Any]:
    """Retrieve grounded Deadlock knowledge from local chunks, entities, and tables.

    Use this as the default KB tool for game-system, concept, hero, item, or
    patch-adjacent questions when the answer should be grounded in the local
    imported wiki/reference corpus instead of memory.
    """

    search_query = query.strip()
    if not search_query:
        return {
            "source": "knowledge_retriever",
            "query": query,
            "fact": None,
            "fact_source": None,
            "entities": [],
            "matches": [],
            "tables": [],
            "summary": "No query supplied.",
        }

    root = _knowledge_root()
    if not root.exists():
        return {
            "source": "knowledge_retriever",
            "query": query,
            "fact": None,
            "fact_source": None,
            "entities": [],
            "matches": [],
            "tables": [],
            "summary": "Knowledge base folder does not exist yet.",
        }

    result = retrieve_grounded_knowledge_context(_settings(), search_query, limit=max(1, min(limit, 8)))
    return {
        "source": "knowledge_retriever",
        **result,
    }


def list_knowledge_topics(limit: int = 24) -> dict[str, Any]:
    """List available local knowledge files so the coach can see what topics exist.

    Use this before claiming that the knowledge base covers a topic.
    """

    root = _knowledge_root()
    if not root.exists():
        return {"source": "knowledge_base", "topics": [], "note": "Knowledge base folder does not exist yet."}

    topics: list[dict[str, Any]] = []
    for path in _iter_knowledge_files(root):
        relative = path.relative_to(root)
        body = path.read_text(encoding="utf-8")
        first_heading = next(
            (line.lstrip("#").strip() for line in body.splitlines() if line.strip().startswith("#")),
            relative.stem.replace("-", " ").replace("_", " ").title(),
        )
        topics.append(
            {
                "path": str(relative),
                "title": first_heading,
                "group": relative.parts[0] if len(relative.parts) > 1 else "root",
            }
        )

    return {"source": "knowledge_base", "topics": topics[: max(1, limit)]}


def search_reference_imports(query: str, limit: int = 5) -> dict[str, Any]:
    """Search imported wiki reference files stored locally.

    Use this when local curated notes are too thin and you want file-based
    source material instead of a live reference call.
    """

    search_query = query.strip()
    if not search_query:
        return {"source": "knowledge_imports", "matches": []}

    root = _knowledge_root() / "_imports" / "wiki"
    if not root.exists():
        return {
            "source": "knowledge_imports",
            "matches": [],
            "note": "No imported wiki reference files exist yet. Run `deadlock-coach knowledge sync-wiki` first.",
        }

    return {
        "source": "knowledge_imports",
        "query": query,
        "matches": search_local_knowledge(_settings(), search_query, limit=limit, source_filter="knowledge_imports"),
    }


def query_reference_tables(query: str, limit: int = 3) -> dict[str, Any]:
    """Query local imported reference tables for exact numeric or comparative facts.

    Use this when the answer likely lives in a wiki table, such as boon scaling,
    investment thresholds, or hero/item comparison tables.
    """

    search_query = query.strip()
    if not search_query:
        return {"source": "knowledge_tables", "fact": None, "matches": []}

    result = query_local_knowledge_tables(_settings(), search_query, limit=limit)
    if result is None:
        return {"source": "knowledge_tables", "query": query, "fact": None, "matches": []}
    return {"source": "knowledge_tables", **result}


def list_reference_import_topics(limit: int = 60) -> dict[str, Any]:
    """List imported wiki reference files available locally."""

    root = _knowledge_root() / "_imports" / "wiki"
    if not root.exists():
        return {
            "source": "knowledge_imports",
            "topics": [],
            "note": "No imported wiki reference files exist yet.",
        }

    topics: list[dict[str, Any]] = []
    for path in _iter_knowledge_files(root, include_internal=True):
        relative = path.relative_to(root)
        body = path.read_text(encoding="utf-8")
        first_heading = next(
            (line.lstrip("#").strip() for line in body.splitlines() if line.strip().startswith("#")),
            relative.stem.replace("-", " ").replace("_", " ").title(),
        )
        topics.append(
            {
                "path": str(relative),
                "title": first_heading,
                "group": relative.parts[0] if len(relative.parts) > 1 else "root",
            }
        )

    return {"source": "knowledge_imports", "topics": topics[: max(1, limit)]}


def list_deadlock_reference_catalog(kind: str = "heroes", limit: int = 60) -> dict[str, Any]:
    """List reference page titles available from the Deadlock Wiki.

    Use this when the agent needs to know whether a hero or item likely has a
    public reference page before claiming that reference support exists.
    """

    normalized_kind = kind.strip().lower() if kind else "heroes"
    if normalized_kind not in {"heroes", "items"}:
        return {
            "source": "deadlock_wiki",
            "kind": normalized_kind,
            "available": False,
            "error": "Supported kinds are `heroes` and `items`.",
        }

    category_title = HERO_CATEGORY_TITLE if normalized_kind == "heroes" else ITEM_CATEGORY_TITLE
    try:
        titles = _wiki_category_members(category_title, limit=max(1, min(limit, 200)))
        source = "deadlock_wiki"
    except Exception as exc:  # pragma: no cover - network and upstream dependent
        group = "heroes" if normalized_kind == "heroes" else "items"
        titles = _import_reference_titles(group) or _local_reference_titles(group)
        source = "local_knowledge"
        if not titles:
            return {
                "source": "deadlock_wiki",
                "kind": normalized_kind,
                "available": False,
                "error": f"Reference catalog unavailable: {exc}",
            }

    return {
        "source": source,
        "kind": normalized_kind,
        "available": True,
        "titles": titles[: max(1, limit)],
    }


def search_deadlock_wiki(query: str, limit: int = 5) -> dict[str, Any]:
    """Search the Deadlock Wiki when the local knowledge base is too shallow.

    Use this as a secondary reference tool for hero, item, and systems theory.
    Prefer local curated notes first. Use this when the knowledge base does not
    yet contain enough distilled guidance.
    """

    search_query = query.strip()
    if not search_query:
        return {"source": "deadlock_wiki", "query": query, "available": False, "matches": []}

    try:
        matches = _wiki_search(search_query, limit=max(1, min(limit, 10)))
    except Exception as exc:  # pragma: no cover - network and upstream dependent
        local = search_knowledge_base(search_query, limit=max(1, min(limit, 10)))
        local_matches = []
        for match in local.get("matches", []):
            local_matches.append(
                {
                    "title": match["path"].split("/")[-1].replace(".md", "").replace("-", " ").title(),
                    "pageid": None,
                    "snippet": match["excerpt"],
                    "url": match["path"],
                }
            )
        if not local_matches:
            imported = search_reference_imports(search_query, limit=max(1, min(limit, 10)))
            local_matches = [
                {
                    "title": match["path"].split("/")[-1].replace(".md", "").replace("-", " ").title(),
                    "pageid": None,
                    "snippet": match["excerpt"],
                    "url": match["path"],
                }
                for match in imported.get("matches", [])
            ]
        if local_matches:
            return {
                "source": "local_knowledge",
                "query": query,
                "available": True,
                "matches": local_matches,
                "error": f"Wiki search unavailable: {exc}",
            }
        return {
            "source": "deadlock_wiki",
            "query": query,
            "available": False,
            "matches": [],
            "error": f"Wiki search unavailable: {exc}",
        }

    return {
        "source": "deadlock_wiki",
        "query": query,
        "available": True,
        "matches": matches,
    }


def get_hero_reference(hero_name: str) -> dict[str, Any]:
    """Fetch a compact Deadlock Wiki summary for a specific hero.

    Use this when the user asks about hero identity, role, or general hero
    reference material that is not purely from player telemetry.
    """

    normalized_title = _normalize_reference_title(hero_name, HERO_TITLE_ALIASES)
    if not normalized_title:
        return {"source": "deadlock_wiki", "kind": "hero", "available": False, "error": "Hero name is required."}

    try:
        page = _wiki_page_extract(normalized_title)
    except Exception as exc:  # pragma: no cover - network and upstream dependent
        local_page = _import_reference_page("heroes", normalized_title) or _local_reference_page("heroes", normalized_title)
        if local_page is not None:
            return {
                "source": "local_knowledge",
                "kind": "hero",
                "requested_title": normalized_title,
                "available": True,
                "page": local_page,
                "error": f"Hero wiki reference unavailable: {exc}",
            }
        return {
            "source": "deadlock_wiki",
            "kind": "hero",
            "requested_title": normalized_title,
            "available": False,
            "error": f"Hero reference unavailable: {exc}",
        }

    if page is None:
        local_page = _local_reference_page("heroes", normalized_title)
        if local_page is not None:
            return {
                "source": "local_knowledge",
                "kind": "hero",
                "requested_title": normalized_title,
                "available": True,
                "page": local_page,
            }
        return {
            "source": "deadlock_wiki",
            "kind": "hero",
            "requested_title": normalized_title,
            "available": False,
            "error": "No matching hero page was found.",
        }

    return {
        "source": "deadlock_wiki",
        "kind": "hero",
        "requested_title": normalized_title,
        "available": True,
        "page": page,
    }


def get_item_reference(item_name: str) -> dict[str, Any]:
    """Fetch a compact Deadlock Wiki summary for a specific item.

    Use this when the user asks about what an item is, item category/tier, or
    other item reference material that local telemetry cannot answer alone.
    """

    normalized_title = _normalize_reference_title(item_name, ITEM_TITLE_ALIASES)
    if not normalized_title:
        return {"source": "deadlock_wiki", "kind": "item", "available": False, "error": "Item name is required."}

    try:
        page = _wiki_page_extract(normalized_title)
    except Exception as exc:  # pragma: no cover - network and upstream dependent
        local_page = _import_reference_page("items", normalized_title) or _local_reference_page("items", normalized_title)
        if local_page is not None:
            return {
                "source": "local_knowledge",
                "kind": "item",
                "requested_title": normalized_title,
                "available": True,
                "page": local_page,
                "error": f"Item wiki reference unavailable: {exc}",
            }
        return {
            "source": "deadlock_wiki",
            "kind": "item",
            "requested_title": normalized_title,
            "available": False,
            "error": f"Item reference unavailable: {exc}",
        }

    if page is None:
        local_page = _local_reference_page("items", normalized_title)
        if local_page is not None:
            return {
                "source": "local_knowledge",
                "kind": "item",
                "requested_title": normalized_title,
                "available": True,
                "page": local_page,
            }
        return {
            "source": "deadlock_wiki",
            "kind": "item",
            "requested_title": normalized_title,
            "available": False,
            "error": "No matching item page was found.",
        }

    return {
        "source": "deadlock_wiki",
        "kind": "item",
        "requested_title": normalized_title,
        "available": True,
        "page": page,
    }


def get_recent_matches(
    account_id: int | None = None,
    window_matches: int = 5,
    tool_context: Any | None = None,
) -> dict[str, Any]:
    """Return recent matches with per-match detail for grounded coaching.

    Use this when the question needs match-by-match context instead of only aggregates.
    """

    resolved_account_id = _resolve_account_id(account_id, tool_context=tool_context)
    settings = _settings()
    if not settings.warehouse_db_path.exists():
        raise ValueError("No local warehouse exists yet. Sync a player account first.")

    with closing(_connect(settings.warehouse_db_path)) as connection:
        rows = connection.execute(
            """
            SELECT
                match_id,
                hero_id,
                start_time,
                kills,
                deaths,
                assists,
                net_worth,
                match_duration_s,
                won
            FROM player_match
            WHERE account_id = ?
            ORDER BY start_time DESC
            LIMIT ?
            """,
            (resolved_account_id, max(1, window_matches)),
        ).fetchall()

    matches = [
        {
            "match_id": int(row["match_id"]),
            "hero_id": int(row["hero_id"]) if row["hero_id"] is not None else None,
            "hero_label": hero_label(settings, row["hero_id"]),
            "start_time": row["start_time"],
            "won": bool(row["won"]),
            "kills": int(row["kills"] or 0),
            "deaths": int(row["deaths"] or 0),
            "assists": int(row["assists"] or 0),
            "net_worth": int(row["net_worth"] or 0),
            "match_duration_s": int(row["match_duration_s"] or 0),
        }
        for row in rows
    ]

    return {
        "source": "local_sqlite",
        "available": True,
        "account_id": resolved_account_id,
        "matches": matches,
    }


def get_recent_item_paths(
    account_id: int | None = None,
    hero_name: str | None = None,
    window_matches: int = 5,
    items_per_match: int = 5,
    tool_context: Any | None = None,
) -> dict[str, Any]:
    """Return recent per-match item sequences for detailed build coaching.

    Use this when aggregate item timing is not enough and the coach needs actual recent paths.
    """

    try:
        resolved_account_id = _resolve_account_id(account_id, tool_context=tool_context)
    except ValueError as exc:
        return _account_resolution_error_payload(str(exc))
    settings = _settings()
    recent = get_recent_matches(
        account_id=resolved_account_id,
        window_matches=max(window_matches, 1),
        tool_context=tool_context,
    )
    if not recent.get("available", True):
        return recent
    selected_matches = recent["matches"]

    if hero_name:
        lowered = hero_name.strip().casefold()
        selected_matches = [match for match in selected_matches if match["hero_label"].casefold() == lowered]

    selected_matches = selected_matches[: max(1, window_matches)]
    if not selected_matches:
        return {
            "source": "local_sqlite",
            "account_id": resolved_account_id,
            "matches": [],
            "note": "No recent matches matched that hero filter.",
        }

    match_ids = [match["match_id"] for match in selected_matches]
    placeholders = ", ".join("?" for _ in match_ids)
    with closing(_connect(settings.warehouse_db_path)) as connection:
        rows = connection.execute(
            f"""
            SELECT
                match_id,
                purchase_index,
                item_id,
                bought_at_s
            FROM item_purchase
            WHERE account_id = ?
              AND match_id IN ({placeholders})
            ORDER BY match_id DESC, purchase_index ASC, bought_at_s ASC
            """,
            [resolved_account_id, *match_ids],
        ).fetchall()

    grouped: dict[int, list[dict[str, Any]]] = {match_id: [] for match_id in match_ids}
    for row in rows:
        path_rows = grouped.setdefault(int(row["match_id"]), [])
        if len(path_rows) >= max(1, items_per_match):
            continue
        item_id = int(row["item_id"]) if row["item_id"] is not None else None
        asset = item_asset(settings, item_id)
        if asset.kind != "item":
            continue
        path_rows.append(
            {
                "purchase_index": int(row["purchase_index"] or 0),
                "item_id": item_id,
                "item_label": asset.label,
                "bought_at_s": float(row["bought_at_s"] or 0.0),
            }
        )

    return {
        "source": "local_sqlite",
        "account_id": resolved_account_id,
        "matches": [
            {
                **match,
                "items": grouped.get(match["match_id"], []),
            }
            for match in selected_matches
        ],
    }


def inspect_local_state(account_id: int | None = None, window_matches: int = DEFAULT_WINDOW_MATCHES) -> dict[str, Any]:
    """Return a compact combined snapshot for debugging and orchestration.

    Use this when the root coach needs one tool call to understand the current
    local player state before deciding which specialist route to use.
    """

    resolved_account_id = _resolve_optional_account_id(account_id)
    if resolved_account_id is None:
        return {
            "source": "local_sqlite",
            "account_id": None,
            "accounts": list_tracked_accounts(_settings()),
            "profile": None,
            "hero_pool": None,
            "builds": None,
        }

    profile = get_player_profile(account_id=resolved_account_id, window_matches=window_matches)
    hero_pool = get_hero_pool_analysis(account_id=resolved_account_id, window_matches=window_matches)
    builds = get_build_analysis(account_id=resolved_account_id, window_matches=window_matches)
    return {
        "source": "local_sqlite",
        "profile": profile,
        "hero_pool": hero_pool,
        "builds": builds,
    }


def route_coaching_request(message: str, account_id: int | None = None, hero_name: str | None = None, window_matches: int = DEFAULT_WINDOW_MATCHES) -> dict[str, Any]:
    """Route a coaching request to specialist analyses and return a typed plan.

    Use this first when the root coach needs a narrow orchestration decision
    before answering.
    """

    context = {
        "account_id": _resolve_optional_account_id(account_id),
        "hero_name": hero_name,
        "window_matches": window_matches,
    }
    from deadlock_coach.coach_service import parse_context

    envelope = build_response_envelope(_settings(), message, parse_context(context))
    return {
        "source": "orchestration",
        "routing": envelope.structured_output.routing.model_dump(mode="json"),
        "confidence": envelope.confidence.model_dump(mode="json"),
        "selected_specialists": envelope.trace.selected_specialists,
        "tool_hints": envelope.structured_output.routing.tool_hints,
    }


def _specialist_placeholder_payload(
    specialist_name: str,
    *,
    message: str = "",
    account_id: int | None = None,
    hero_name: str | None = None,
    window_matches: int = DEFAULT_WINDOW_MATCHES,
) -> dict[str, Any]:
    return {
        "source": "placeholder",
        "status": "inactive",
        "specialist": specialist_name,
        "message": (
            f"{specialist_name} is only a placeholder right now while Deadbase focuses on coach_agent. "
            "Use coach_agent plus the direct telemetry and knowledge-base tools instead."
        ),
        "request": {
            "message": message,
            "account_id": _resolve_optional_account_id(account_id),
            "hero_name": hero_name,
            "window_matches": window_matches,
        },
    }


def run_hero_analyst(message: str = "", account_id: int | None = None, hero_name: str | None = None, window_matches: int = DEFAULT_WINDOW_MATCHES) -> dict[str, Any]:
    """Placeholder specialist tool while coach_agent is the only active chat agent."""

    return _specialist_placeholder_payload(
        "run_hero_analyst",
        message=message,
        account_id=account_id,
        hero_name=hero_name,
        window_matches=window_matches,
    )


def run_build_analyst(message: str = "", account_id: int | None = None, hero_name: str | None = None, window_matches: int = DEFAULT_WINDOW_MATCHES) -> dict[str, Any]:
    """Placeholder specialist tool while coach_agent is the only active chat agent."""

    return _specialist_placeholder_payload(
        "run_build_analyst",
        message=message,
        account_id=account_id,
        hero_name=hero_name,
        window_matches=window_matches,
    )


def run_matchup_analyst(message: str = "", account_id: int | None = None, hero_name: str | None = None, window_matches: int = DEFAULT_WINDOW_MATCHES) -> dict[str, Any]:
    """Placeholder specialist tool while coach_agent is the only active chat agent."""

    return _specialist_placeholder_payload(
        "run_matchup_analyst",
        message=message,
        account_id=account_id,
        hero_name=hero_name,
        window_matches=window_matches,
    )


def run_report_writer(message: str = "", account_id: int | None = None, hero_name: str | None = None, window_matches: int = DEFAULT_WINDOW_MATCHES) -> dict[str, Any]:
    """Placeholder specialist tool while coach_agent is the only active chat agent."""

    return _specialist_placeholder_payload(
        "run_report_writer",
        message=message,
        account_id=account_id,
        hero_name=hero_name,
        window_matches=window_matches,
    )


def run_experiment_agent(message: str = "", account_id: int | None = None, hero_name: str | None = None, window_matches: int = DEFAULT_WINDOW_MATCHES) -> dict[str, Any]:
    """Placeholder specialist tool while coach_agent is the only active chat agent."""

    return _specialist_placeholder_payload(
        "run_experiment_agent",
        message=message,
        account_id=account_id,
        hero_name=hero_name,
        window_matches=window_matches,
    )


def run_vod_review_planner(message: str = "", account_id: int | None = None, hero_name: str | None = None, window_matches: int = DEFAULT_WINDOW_MATCHES) -> dict[str, Any]:
    """Placeholder specialist tool while coach_agent is the only active chat agent."""

    return _specialist_placeholder_payload(
        "run_vod_review_planner",
        message=message,
        account_id=account_id,
        hero_name=hero_name,
        window_matches=window_matches,
    )
