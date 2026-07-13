from __future__ import annotations

from dataclasses import dataclass
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any, Literal

from deadlock_coach.api import DeadlockApiClient
from deadlock_coach.config import Settings

_CACHE_TTL = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class ItemAsset:
    item_id: int | None
    label: str
    kind: Literal["item", "ability", "unknown"]


@dataclass(frozen=True, slots=True)
class ItemFacts:
    item_id: int | None
    label: str
    kind: Literal["item", "ability", "unknown"]
    tier: int | None
    cost: int | None
    slot: str | None


@dataclass(frozen=True, slots=True)
class RankBadgeRange:
    name: str
    tier: int
    min_badge: int
    max_badge: int


def _assets_dir(settings: Settings) -> Path:
    path = settings.cache_dir / "assets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return datetime.now(timezone.utc) - modified <= _CACHE_TTL


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")


def _load_heroes(settings: Settings, client: DeadlockApiClient | None = None) -> dict[int, str]:
    cache_path = _assets_dir(settings) / "heroes.json"
    payload: Any
    if _is_fresh(cache_path):
        payload = _read_json(cache_path)
    else:
        client = client or DeadlockApiClient(settings)
        _, payload = client.fetch_json("/v1/assets/heroes")
        _write_json(cache_path, payload)

    if not isinstance(payload, list):
        return {}
    result: dict[int, str] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        hero_id = row.get("id")
        name = row.get("name")
        if isinstance(hero_id, int) and isinstance(name, str) and name.strip():
            result[hero_id] = name.strip()
    return result


def _load_ranks(settings: Settings, client: DeadlockApiClient | None = None) -> dict[str, RankBadgeRange]:
    cache_path = _assets_dir(settings) / "ranks.json"
    payload: Any
    if _is_fresh(cache_path):
        payload = _read_json(cache_path)
    else:
        client = client or DeadlockApiClient(settings)
        _, payload = client.fetch_json("https://statlocker.gg/api/info/ranks-full")
        _write_json(cache_path, payload)

    if not isinstance(payload, list):
        return {}

    result: dict[str, RankBadgeRange] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        tier = row.get("tier")
        name = row.get("name")
        if not isinstance(tier, int) or not isinstance(name, str) or not name.strip():
            continue
        if tier <= 0:
            min_badge = 0
            max_badge = 0
        else:
            min_badge = tier * 10 + 1
            max_badge = tier * 10 + 6
        normalized_name = name.strip().casefold()
        result[normalized_name] = RankBadgeRange(
            name=name.strip(),
            tier=tier,
            min_badge=min_badge,
            max_badge=max_badge,
        )
    return result


def hero_label(settings: Settings, hero_id: int | None, client: DeadlockApiClient | None = None) -> str:
    if hero_id is None:
        return "Unknown hero"
    try:
        heroes = _load_heroes(settings, client=client)
    except RuntimeError:
        heroes = {}
    return heroes.get(hero_id, f"Hero {hero_id}")


def detect_hero_name_in_text(settings: Settings, text: str | None, client: DeadlockApiClient | None = None) -> str | None:
    normalized_text = str(text or "").strip().casefold()
    if not normalized_text:
        return None
    try:
        heroes = _load_heroes(settings, client=client)
    except RuntimeError:
        heroes = {}

    labels = sorted(
        {
            str(label).strip()
            for label in heroes.values()
            if isinstance(label, str) and str(label).strip()
        },
        key=len,
        reverse=True,
    )
    for label in labels:
        pattern = rf"(?<![a-z0-9]){re.escape(label.casefold())}(?![a-z0-9])"
        if re.search(pattern, normalized_text):
            return label
    return None


def resolve_hero_id(settings: Settings, hero_name: str | None, client: DeadlockApiClient | None = None) -> int | None:
    normalized = str(hero_name or "").strip().casefold()
    if not normalized:
        return None
    try:
        heroes = _load_heroes(settings, client=client)
    except RuntimeError:
        heroes = {}
    for hero_id, label in heroes.items():
        if str(label).strip().casefold() == normalized:
            return hero_id
    return None


def resolve_rank_badge_range(
    settings: Settings,
    rank_name: str | None,
    client: DeadlockApiClient | None = None,
) -> RankBadgeRange | None:
    normalized = str(rank_name or "").strip().casefold()
    if not normalized:
        return None
    try:
        ranks = _load_ranks(settings, client=client)
    except RuntimeError:
        ranks = {}
    exact = ranks.get(normalized)
    if exact is not None:
        return exact

    subtier_match = re.fullmatch(r"(.+?)\s+([1-6])", normalized)
    if subtier_match is None:
        return None

    base_name = subtier_match.group(1).strip()
    base_rank = ranks.get(base_name)
    if base_rank is None or base_rank.tier <= 0:
        return None

    subtier = int(subtier_match.group(2))
    badge_value = base_rank.tier * 10 + subtier
    return RankBadgeRange(
        name=f"{base_rank.name} {subtier}",
        tier=base_rank.tier,
        min_badge=badge_value,
        max_badge=badge_value,
    )


def _load_item_payload(settings: Settings, item_id: int, client: DeadlockApiClient | None = None) -> Any:
    cache_path = _assets_dir(settings) / f"item-{item_id}.json"
    try:
        if _is_fresh(cache_path):
            return _read_json(cache_path)

        client = client or DeadlockApiClient(settings)
        _, payload = client.fetch_json(f"/v1/assets/items/{item_id}")
        _write_json(cache_path, payload)
        return payload
    except RuntimeError:
        return None


def _classify_item_payload(payload: Any) -> Literal["item", "ability", "unknown"]:
    if not isinstance(payload, dict):
        return "unknown"

    image = str(payload.get("image") or "")
    image_webp = str(payload.get("image_webp") or "")
    if payload.get("ability_type") or "/abilities/" in image or "/abilities/" in image_webp:
        return "ability"

    if (
        payload.get("cost") is not None
        or payload.get("item_slot_type") is not None
        or payload.get("item_tier") is not None
        or "is_active_item" in payload
    ):
        return "item"

    return "unknown"


def item_asset(settings: Settings, item_id: int | None, client: DeadlockApiClient | None = None) -> ItemAsset:
    if item_id is None:
        return ItemAsset(item_id=None, label="Unknown item", kind="unknown")

    payload = _load_item_payload(settings, item_id, client=client)
    label = f"Item {item_id}"
    if isinstance(payload, dict):
        name = payload.get("name")
        if isinstance(name, str) and name.strip():
            label = name.strip()

    return ItemAsset(
        item_id=item_id,
        label=label,
        kind=_classify_item_payload(payload),
    )


def item_label(settings: Settings, item_id: int | None, client: DeadlockApiClient | None = None) -> str:
    return item_asset(settings, item_id, client=client).label


def item_facts(settings: Settings, item_id: int | None, client: DeadlockApiClient | None = None) -> ItemFacts:
    if item_id is None:
        return ItemFacts(item_id=None, label="Unknown item", kind="unknown", tier=None, cost=None, slot=None)

    payload = _load_item_payload(settings, item_id, client=client)
    asset = item_asset(settings, item_id, client=client)
    tier = None
    cost = None
    slot = None
    if isinstance(payload, dict):
        raw_tier = payload.get("item_tier")
        raw_cost = payload.get("cost")
        raw_slot = payload.get("item_slot_type")
        tier = int(raw_tier) if isinstance(raw_tier, int) else None
        cost = int(raw_cost) if isinstance(raw_cost, int) else None
        slot = str(raw_slot).strip() if isinstance(raw_slot, str) and raw_slot.strip() else None

    return ItemFacts(
        item_id=item_id,
        label=asset.label,
        kind=asset.kind,
        tier=tier,
        cost=cost,
        slot=slot,
    )


def item_tier(settings: Settings, item_id: int | None, client: DeadlockApiClient | None = None) -> int | None:
    return item_facts(settings, item_id, client=client).tier
