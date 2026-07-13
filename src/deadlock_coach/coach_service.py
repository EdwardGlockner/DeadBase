from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
import re
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from deadlock_coach.asset_service import detect_hero_name_in_text, hero_label, item_asset, item_label, item_tier
from deadlock_coach.config import Settings
from deadlock_coach.knowledge_base import knowledge_content_lines, knowledge_note_excerpt, knowledge_query_terms, search_local_knowledge
from deadlock_coach.message_hints import normalized_message

DEFAULT_WINDOW_MATCHES = 20
MAX_CANDIDATE_ITEM_TIMINGS = 30


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "page"


@dataclass(frozen=True)
class CoachContext:
    account_id: int | None = None
    hero_id: int | None = None
    hero_name: str | None = None
    player_label: str | None = None
    window_matches: int = DEFAULT_WINDOW_MATCHES


@dataclass(frozen=True)
class HeroPerformance:
    hero_id: int
    games: int
    resolved_games: int
    wins: int
    win_rate: float


@dataclass(frozen=True)
class ItemTiming:
    item_id: int
    purchases: int
    avg_bought_at_s: float


@dataclass(frozen=True)
class RecentMatch:
    match_id: int
    hero_id: int
    start_time: int | None
    won: bool | None
    kills: int
    deaths: int
    assists: int
    net_worth: int
    match_duration_s: int


@dataclass(frozen=True)
class AccountSummary:
    account_id: int
    total_matches: int
    resolved_outcome_matches: int
    unknown_outcome_matches: int
    wins: int
    losses: int
    win_rate: float
    avg_kills: float
    avg_deaths: float
    avg_assists: float
    avg_net_worth: float
    latest_start_time: int | None
    hero_performance: list[HeroPerformance]
    item_timings: list[ItemTiming]
    hydrated_match_count: int


def _format_time_seconds(value: float) -> str:
    seconds = max(int(round(value)), 0)
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes}:{remainder:02d}"


def _item_phase_label(value: float) -> str:
    seconds = max(float(value or 0.0), 0.0)
    if seconds < 8 * 60:
        return "early"
    if seconds < 18 * 60:
        return "mid"
    return "late"


def _phase_sort_key(phase: str) -> int:
    return {"early": 0, "mid": 1, "late": 2}.get(phase, 99)


def _item_phase_summary(settings: Settings, items: list[ItemTiming]) -> list[tuple[str, list[str]]]:
    grouped: dict[str, list[str]] = {"early": [], "mid": [], "late": []}
    for item in sorted(items, key=lambda row: (row.avg_bought_at_s, -row.purchases, row.item_id)):
        tier = item_tier(settings, item.item_id)
        phase = (
            "early"
            if tier in {1, 2}
            else "mid"
            if tier == 3
            else "late"
            if tier == 4
            else _item_phase_label(item.avg_bought_at_s)
        )
        label = item_label(settings, item.item_id)
        if label not in grouped[phase]:
            grouped[phase].append(label)

    return [(phase, labels) for phase, labels in sorted(grouped.items(), key=lambda entry: _phase_sort_key(entry[0])) if labels]


def _format_item_phase_summary(settings: Settings, items: list[ItemTiming]) -> str:
    phases = _item_phase_summary(settings, items)
    if not phases:
        return "No verified build phases yet."

    parts: list[str] = []
    for phase, labels in phases:
        phase_name = "early core" if phase == "early" else "midgame pivots" if phase == "mid" else "late anchors"
        parts.append(f"{phase_name}: {', '.join(labels[:3])}")
    return "; ".join(parts)


def _labels_for_phase(settings: Settings, items: list[ItemTiming], phase: str, limit: int = 2) -> list[str]:
    labels: list[str] = []
    for item in sorted(items, key=lambda row: (row.avg_bought_at_s, -row.purchases, row.item_id)):
        tier = item_tier(settings, item.item_id)
        derived_phase = (
            "early"
            if tier in {1, 2}
            else "mid"
            if tier == 3
            else "late"
            if tier == 4
            else _item_phase_label(item.avg_bought_at_s)
        )
        if derived_phase != phase:
            continue
        label = item_label(settings, item.item_id)
        if label in labels:
            continue
        labels.append(label)
        if len(labels) >= max(1, limit):
            break
    return labels


def _join_labels(labels: list[str]) -> str:
    cleaned = [label for label in labels if label]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


def _dedupe_preserving_order(labels: list[str]) -> list[str]:
    deduped: list[str] = []
    for label in labels:
        if label and label not in deduped:
            deduped.append(label)
    return deduped


def _knowledge_note_excerpt(settings: Settings, relative_path: str, *, max_lines: int = 5) -> str | None:
    return knowledge_note_excerpt(settings, relative_path, max_lines=max_lines)


def _knowledge_matches(
    settings: Settings,
    query: str,
    *,
    limit: int = 3,
    group_filters: list[str] | None = None,
) -> list[dict[str, Any]]:
    matches = search_local_knowledge(settings, query, limit=limit, group_filters=group_filters)
    hydrated: list[dict[str, Any]] = []
    for match in matches:
        hydrated.append(
            {
                **match,
                "path": settings.project_root / match["relative_path"],
            }
        )
    return hydrated


def _knowledge_matches_for_queries(
    settings: Settings,
    queries: list[str],
    *,
    limit: int = 5,
    group_filters: list[str] | None = None,
) -> list[dict[str, Any]]:
    ranked: dict[tuple[str, str], dict[str, Any]] = {}
    for raw_query in queries:
        query = str(raw_query or "").strip()
        if not query:
            continue
        for match in _knowledge_matches(settings, query, limit=limit, group_filters=group_filters):
            key = (str(match.get("relative_path") or ""), str(match.get("section_title") or ""))
            existing = ranked.get(key)
            if existing is None or float(match.get("score") or 0.0) > float(existing.get("score") or 0.0):
                ranked[key] = match

    ordered = sorted(
        ranked.values(),
        key=lambda item: (
            -float(item.get("score") or 0.0),
            bool(item.get("imported")),
            str(item.get("relative_path") or ""),
            str(item.get("section_title") or ""),
        ),
    )
    return ordered[: max(1, limit)]


def _knowledge_note_path(settings: Settings, group: str, title: str, *, imported: bool = False) -> Path | None:
    if not title:
        return None
    base = settings.project_root / "docs" / "knowledge"
    if imported:
        base = base / "_imports" / "wiki"
    candidate = base / group / f"{_slugify(title)}.md"
    return candidate if candidate.exists() else None


def _knowledge_summary_lines(path: Path, query: str, *, max_lines: int = 3) -> list[str]:
    query_terms = knowledge_query_terms(query)
    body = path.read_text(encoding="utf-8")
    bullet_lines = [
        line
        for line in knowledge_content_lines(body)
        if line and not line.endswith(":")
    ]
    if bullet_lines:
        relevant = [line for line in bullet_lines if any(term in line.lower() for term in query_terms)]
        selected = _dedupe_preserving_order([*relevant, *bullet_lines])[: max(1, max_lines)]
        if selected:
            return selected

    lines = knowledge_content_lines(body)
    relevant = [line for line in lines if any(term in line.lower() for term in query_terms)]
    return _dedupe_preserving_order([*relevant, *lines])[: max(1, max_lines)]


def _build_walkthrough(settings: Settings, items: list[ItemTiming]) -> dict[str, str | list[str]]:
    lane_early = _labels_for_phase(settings, items, "early", limit=5)
    mid_items = _labels_for_phase(settings, items, "mid", limit=3)
    late_items = _labels_for_phase(settings, items, "late", limit=3)

    parts: list[str] = []
    if lane_early:
        parts.append(f"lane/early usually looks like {_join_labels(lane_early)}")
    if mid_items:
        parts.append(f"mid game most often moves into {_join_labels(mid_items)}")
    if late_items:
        parts.append(f"late game you usually end up on {_join_labels(late_items)}")

    return {
        "lane_early": lane_early,
        "mid_items": mid_items,
        "late_items": late_items,
        "summary": ". ".join(part[:1].upper() + part[1:] for part in parts if part).strip(),
    }


def _format_late_alternative(alternative: dict[str, Any]) -> str:
    late_items = list(alternative.get("late_items") or [])
    late_finishers = list(alternative.get("late_finishers") or [])
    if late_items and late_finishers:
        return f"add {_join_labels(late_items)}, then cap the build with {_join_labels(late_finishers)} as the T4 finisher"
    if late_items:
        return f"add {_join_labels(late_items)}"
    if late_finishers:
        return f"cap the build with {_join_labels(late_finishers)} as the T4 finisher"
    return ""


def _walkthrough_reply_lines(walkthrough: dict[str, Any]) -> list[str]:
    lane_early = list(walkthrough.get("lane_early") or [])
    mid_items = list(walkthrough.get("mid_items") or [])
    core_items = list(walkthrough.get("core_items") or [])
    late_items = list(walkthrough.get("late_items") or [])
    late_finishers = list(walkthrough.get("late_finishers") or [])
    late_alternatives = list(walkthrough.get("late_alternatives") or [])
    situational_items = list(walkthrough.get("situational_items") or [])

    lines: list[str] = []
    if lane_early:
        lines.append(f"Lane/early usually looks like {_join_labels(lane_early)}.")
    if core_items:
        lines.append(f"Your stable core most often settles into {_join_labels(core_items)}.")
    elif mid_items:
        lines.append(f"Mid game most often moves into {_join_labels(mid_items)}.")
    if len(late_alternatives) >= 2:
        first_alt = _format_late_alternative(late_alternatives[0])
        second_alt = _format_late_alternative(late_alternatives[1])
        if first_alt and second_alt:
            lines.append(f"Late game usually splits two ways: one line {first_alt}; the other {second_alt}.")
        unique_finishers = _dedupe_preserving_order(
            [
                label
                for alternative in late_alternatives[:2]
                for label in list(alternative.get("late_finishers") or [])
            ]
        )
        if unique_finishers:
            lines.append(f"Your main true late/T4 finishers there are usually {_join_labels(unique_finishers[:3])}.")
    elif late_items:
        late_line = f"Late game you usually add {_join_labels(late_items)}"
        if late_finishers:
            late_line += f", then cap the build with {_join_labels(late_finishers)} as the T4 finisher"
        lines.append(f"{late_line}.")
        if late_finishers:
            lines.append(f"Your main true late/T4 finishers are usually {_join_labels(late_finishers)}.")
    elif late_finishers:
        lines.append(f"Your main true late/T4 finishers are usually {_join_labels(late_finishers)}.")
    if situational_items:
        lines.append(f"The most common flexes around that are {_join_labels(situational_items)}.")
    return lines


def _rank_path_labels(bucket: dict[str, dict[str, float]], limit: int) -> list[str]:
    rows = []
    for label, stats in bucket.items():
        average_position = stats["position_total"] / stats["count"] if stats["count"] else 0.0
        rows.append((label, stats["count"], average_position))
    rows.sort(key=lambda row: (-row[1], row[2], row[0]))
    return [label for label, _count, _average_position in rows[: max(1, limit)]]


def _rank_path_label_rows(bucket: dict[str, dict[str, float]]) -> list[tuple[str, float, float]]:
    rows: list[tuple[str, float, float]] = []
    for label, stats in bucket.items():
        average_position = stats["position_total"] / stats["count"] if stats["count"] else 0.0
        rows.append((label, float(stats["count"]), average_position))
    rows.sort(key=lambda row: (-row[1], row[2], row[0]))
    return rows


def _build_walkthrough_from_paths_simple(paths: list[dict[str, Any]]) -> dict[str, str | list[str]]:
    aggregates: dict[str, dict[str, dict[str, float]]] = {
        "lane_early": {},
        "mid_items": {},
        "late_items": {},
        "late_finishers": {},
    }
    for path in paths:
        for index, item in enumerate(path.get("items", [])):
            label = str(item.get("item_label") or "").strip()
            if not label:
                continue
            tier = item.get("item_tier")
            if tier == 1:
                band = "lane_early"
            elif tier == 2:
                band = "lane_early"
            elif tier == 3:
                band = "mid_items"
            elif tier == 4:
                band = "late_finishers"
            elif isinstance(tier, int) and tier >= 5:
                band = "late_items"
            elif tier is None:
                if index < 4:
                    band = "lane_early"
                else:
                    continue
            else:
                continue
            entry = aggregates[band].setdefault(label, {"count": 0.0, "position_total": 0.0})
            entry["count"] += 1.0
            entry["position_total"] += float(index)

    lane_early = _rank_path_labels(aggregates["lane_early"], limit=5)
    core_items = _rank_path_labels(aggregates["mid_items"], limit=3)
    mid_items = core_items[:2]
    late_items = [label for label in _rank_path_labels(aggregates["late_items"], limit=3) if label not in core_items]
    late_finishers = [label for label in _rank_path_labels(aggregates["late_finishers"], limit=2) if label not in late_items]

    parts: list[str] = []
    if lane_early:
        parts.append(f"lane/early usually looks like {_join_labels(lane_early)}")
    if mid_items:
        parts.append(f"mid game most often moves into {_join_labels(mid_items)}")
    if late_items:
        late_line = f"late game you usually add {_join_labels(late_items)}"
        if late_finishers:
            late_line += f", then finish with {_join_labels(late_finishers)}"
        parts.append(late_line)
    elif late_finishers:
        parts.append(f"your most common true late finishers are {_join_labels(late_finishers)}")

    return {
        "lane_early": lane_early,
        "mid_items": mid_items,
        "core_items": core_items,
        "late_items": late_items,
        "late_finishers": late_finishers,
        "summary": ". ".join(part[:1].upper() + part[1:] for part in parts if part).strip(),
    }


def _build_walkthrough_from_paths(paths: list[dict[str, Any]]) -> dict[str, Any]:
    if not paths:
        return {
            "lane_start": [],
            "lane_fill": [],
            "core_items": [],
            "late_items": [],
            "late_finishers": [],
            "late_alternatives": [],
            "situational_items": [],
            "summary": "",
        }

    tiered_item_count = sum(1 for path in paths for item in path.get("items", []) if isinstance(item.get("item_tier"), int))
    total_item_count = sum(len(path.get("items", [])) for path in paths)
    if total_item_count <= 0 or tiered_item_count < max(4, total_item_count // 2):
        return _build_walkthrough_from_paths_simple(paths)

    opening_bucket: dict[str, dict[str, float]] = {}
    lane_fill_bucket: dict[str, dict[str, float]] = {}
    core_first_bucket: dict[str, dict[str, float]] = {}
    core_second_bucket: dict[str, dict[str, float]] = {}
    core_third_bucket: dict[str, dict[str, float]] = {}
    late_bucket: dict[str, dict[str, float]] = {}
    late_finisher_bucket: dict[str, dict[str, float]] = {}
    flex_bucket: dict[str, dict[str, float]] = {}

    def _add(bucket: dict[str, dict[str, float]], label: str, position: int) -> None:
        entry = bucket.setdefault(label, {"count": 0.0, "position_total": 0.0})
        entry["count"] += 1.0
        entry["position_total"] += float(position)

    core_ready_paths = 0
    for path in paths:
        items = path.get("items", [])
        for index, item in enumerate(items[:2]):
            label = str(item.get("item_label") or "").strip()
            if label:
                _add(opening_bucket, label, index)

        first_core_index = next((index for index, item in enumerate(items) if isinstance(item.get("item_tier"), int) and item["item_tier"] >= 3), None)
        if first_core_index is None:
            continue
        core_ready_paths += 1

        for index, item in enumerate(items[2:first_core_index], start=2):
            label = str(item.get("item_label") or "").strip()
            if label:
                _add(lane_fill_bucket, label, index)
            if label and item.get("item_tier") == 2:
                _add(flex_bucket, label, index)

        core_labels = [
            str(item.get("item_label") or "").strip()
            for item in items[first_core_index:]
            if isinstance(item.get("item_tier"), int) and item["item_tier"] >= 3 and str(item.get("item_label") or "").strip()
        ]
        if core_labels:
            _add(core_first_bucket, core_labels[0], first_core_index)
        if len(core_labels) > 1:
            _add(core_second_bucket, core_labels[1], first_core_index + 1)
        if len(core_labels) > 2:
            _add(core_third_bucket, core_labels[2], first_core_index + 2)
        late_core_labels: list[str] = []
        late_finisher_labels: list[str] = []
        for offset, item in enumerate(items[first_core_index + 2 :], start=first_core_index + 2):
            label = str(item.get("item_label") or "").strip()
            if not label:
                continue
            tier = item.get("item_tier")
            if tier == 4:
                late_finisher_labels.append(label)
                _add(late_finisher_bucket, label, offset)
            elif isinstance(tier, int) and tier >= 3:
                late_core_labels.append(label)
                _add(late_bucket, label, offset)
            elif tier == 2:
                _add(flex_bucket, label, offset)

        if not late_core_labels and not late_finisher_labels:
            for offset, label in enumerate(core_labels[2:], start=first_core_index + 2):
                _add(late_bucket, label, offset)

    if core_ready_paths < max(2, len(paths) // 2):
        return _build_walkthrough_from_paths_simple(paths)

    lane_start = _rank_path_labels(opening_bucket, limit=2)
    lane_fill = [label for label in _rank_path_labels(lane_fill_bucket, limit=4) if label not in lane_start][:3]
    lane_early = _dedupe_preserving_order(lane_start + lane_fill)

    core_items: list[str] = []
    stable_core_threshold = max(2, (core_ready_paths + 1) // 2)
    strong_third_core_threshold = max(3, stable_core_threshold + 1)
    for bucket_index, ranked_bucket in enumerate(
        (
            _rank_path_label_rows(core_first_bucket),
            _rank_path_label_rows(core_second_bucket),
            _rank_path_label_rows(core_third_bucket),
        )
    ):
        for label, count, _average_position in ranked_bucket:
            required_count = strong_third_core_threshold if bucket_index == 2 else stable_core_threshold
            if count < required_count or label in core_items:
                continue
            core_items.append(label)
            break

    if len(core_items) < 2:
        for ranked_bucket in (
            _rank_path_label_rows(core_first_bucket),
            _rank_path_label_rows(core_second_bucket),
            _rank_path_label_rows(core_third_bucket),
        ):
            for label, _count, _average_position in ranked_bucket:
                if label in core_items:
                    continue
                core_items.append(label)
                break
            if len(core_items) >= 2:
                break

    if len(core_items) < 3:
        for label, count, _average_position in _rank_path_label_rows(core_third_bucket):
            if label in core_items or count < strong_third_core_threshold:
                continue
            core_items.append(label)
            if len(core_items) >= 3:
                break

    late_items = [label for label in _rank_path_labels(late_bucket, limit=5) if label not in core_items][:3]
    late_finishers = [label for label in _rank_path_labels(late_finisher_bucket, limit=4) if label not in core_items and label not in late_items][:3]
    late_alternative_rows: list[dict[str, Any]] = []
    if core_items:
        alternative_bucket: dict[tuple[tuple[str, ...], tuple[str, ...]], dict[str, Any]] = {}
        required_core_labels = core_items[:2] if len(core_items) >= 2 else core_items[:1]
        for path in paths:
            items = path.get("items", [])
            if not items:
                continue
            core_anchor_indexes: list[int] = []
            for core_label in required_core_labels:
                found_index = next(
                    (
                        index
                        for index in range(len(items))
                        if str(items[index].get("item_label") or "").strip() == core_label
                    ),
                    None,
                )
                if found_index is None:
                    core_anchor_indexes = []
                    break
                core_anchor_indexes.append(found_index)
            if not core_anchor_indexes:
                continue

            branch_late_items: list[str] = []
            branch_late_finishers: list[str] = []
            for item in items[max(core_anchor_indexes) + 1 :]:
                label = str(item.get("item_label") or "").strip()
                if not label or label in core_items:
                    continue
                tier = item.get("item_tier")
                if tier == 4:
                    if label not in branch_late_finishers:
                        branch_late_finishers.append(label)
                elif isinstance(tier, int) and tier >= 3:
                    if label not in branch_late_items:
                        branch_late_items.append(label)

            branch_late_items = branch_late_items[:2]
            branch_late_finishers = branch_late_finishers[:2]
            if not branch_late_items and not branch_late_finishers:
                continue

            signature = (tuple(branch_late_items), tuple(branch_late_finishers))
            entry = alternative_bucket.setdefault(
                signature,
                {
                    "late_items": branch_late_items,
                    "late_finishers": branch_late_finishers,
                    "count": 0,
                },
            )
            entry["count"] += 1

        late_branch_threshold = max(2, core_ready_paths // 3)
        late_alternative_rows = [
            row
            for row in sorted(
                alternative_bucket.values(),
                key=lambda row: (-int(row["count"]), -len(row["late_items"]) - len(row["late_finishers"]), tuple(row["late_items"]), tuple(row["late_finishers"])),
            )
            if int(row["count"]) >= late_branch_threshold
        ][:2]

    situational_items = [
        label
        for label in _rank_path_labels(flex_bucket, limit=8)
        if label not in lane_early and label not in core_items and label not in late_items and label not in late_finishers
    ][:2]

    parts: list[str] = []
    if lane_early:
        parts.append(f"lane/early usually looks like {_join_labels(lane_early)}")
    if core_items:
        mid_line = f"mid game most often turns into {_join_labels(core_items)}"
        if len(core_items) >= 2:
            mid_line += "; that is the most stable core in the sample"
        parts.append(mid_line)
    if len(late_alternative_rows) >= 2:
        first_alt = _format_late_alternative(late_alternative_rows[0])
        second_alt = _format_late_alternative(late_alternative_rows[1])
        if first_alt and second_alt:
            parts.append(f"late game usually splits two ways: one line {first_alt}; the other {second_alt}")
    elif late_items:
        late_line = f"late game you usually add {_join_labels(late_items)}"
        if late_finishers:
            late_line += f", then cap the build with {_join_labels(late_finishers)} as the T4 finisher"
        parts.append(late_line)
    elif late_finishers:
        parts.append(f"your most common true late finishers are {_join_labels(late_finishers)}")
    if situational_items:
        parts.append(f"the most common situational flexes around that core are {_join_labels(situational_items)}")

    return {
        "lane_start": lane_start,
        "lane_fill": lane_fill,
        "lane_early": lane_early,
        "core_items": core_items,
        "late_items": late_items,
        "late_finishers": late_finishers,
        "late_alternatives": late_alternative_rows,
        "situational_items": situational_items,
        "summary": ". ".join(part[:1].upper() + part[1:] for part in parts if part).strip(),
    }


def _select_verified_item_timings(settings: Settings, rows: list[sqlite3.Row]) -> list[ItemTiming]:
    selected: list[ItemTiming] = []

    for row in rows:
        item_id = int(row["item_id"]) if row["item_id"] is not None else None
        asset = item_asset(settings, item_id)
        if asset.kind != "item" or item_id is None:
            continue

        timing = ItemTiming(
            item_id=item_id,
            purchases=int(row["purchases"]),
            avg_bought_at_s=float(row["avg_bought_at_s"] or 0.0),
        )
        selected.append(timing)

    return sorted(selected, key=lambda item: (item.avg_bought_at_s, -item.purchases, item.item_id))


def _resolved_record_text(wins: int, resolved_games: int) -> str | None:
    if resolved_games <= 0:
        return None
    return f"{wins}-{max(resolved_games - wins, 0)} over {resolved_games} resolved matches"


def _summary_outcome_evidence(summary: AccountSummary) -> list[str]:
    if summary.resolved_outcome_matches <= 0:
        return [f"Outcome data is still unresolved for all {summary.total_matches} tracked matches in this local window."]

    evidence = [
        f"Verified results: {summary.wins}-{summary.losses} over {summary.resolved_outcome_matches} resolved matches ({summary.win_rate:.1f}% win rate).",
    ]
    if summary.unknown_outcome_matches > 0:
        evidence.append(f"Outcome data is still missing for {summary.unknown_outcome_matches} of the {summary.total_matches} tracked matches.")
    return evidence


def _top_sample_hero(summary: AccountSummary) -> HeroPerformance | None:
    if not summary.hero_performance:
        return None
    return max(summary.hero_performance, key=lambda item: (item.games, item.win_rate, item.wins, -item.hero_id))


def _top_reliable_hero(summary: AccountSummary) -> HeroPerformance | None:
    if not summary.hero_performance:
        return None
    resolved = [item for item in summary.hero_performance if item.resolved_games > 0]
    if resolved:
        return max(resolved, key=lambda item: (item.win_rate, item.resolved_games, item.games, item.wins, -item.hero_id))
    return _top_sample_hero(summary)


def _match_hero_from_message(settings: Settings, summary: AccountSummary, message: str, context: CoachContext) -> HeroPerformance | None:
    lowered = message.lower()
    explicit_hero_name = detect_hero_name_in_text(settings, message)
    if explicit_hero_name:
        requested = explicit_hero_name.lower()
        for hero in summary.hero_performance:
            if hero_label(settings, hero.hero_id).lower() == requested:
                return hero

    if context.hero_name:
        requested = context.hero_name.lower()
        for hero in summary.hero_performance:
            if hero_label(settings, hero.hero_id).lower() == requested:
                return hero

    for hero in summary.hero_performance:
        if hero_label(settings, hero.hero_id).lower() in lowered:
            return hero
    return None


def _build_spine_labels(settings: Settings, summary: AccountSummary, limit: int = 3) -> list[str]:
    return [item_label(settings, item.item_id) for item in summary.item_timings[:limit]]


def _load_recent_matches(settings: Settings, account_id: int, window_matches: int) -> list[RecentMatch]:
    if not settings.warehouse_db_path.exists():
        return []

    with closing(_connect(settings.warehouse_db_path)) as connection:
        rows = connection.execute(
            """
            WITH recent AS (
                SELECT *
                FROM player_match
                WHERE account_id = ?
                ORDER BY start_time DESC
                LIMIT ?
            )
            SELECT
                recent.match_id,
                recent.hero_id,
                recent.start_time,
                COALESCE(
                    recent.won,
                    CASE
                        WHEN participant.team IS NOT NULL AND metadata.winning_team IS NOT NULL
                        THEN CASE WHEN participant.team = metadata.winning_team THEN 1 ELSE 0 END
                        ELSE NULL
                    END
                ) AS resolved_won,
                recent.kills,
                recent.deaths,
                recent.assists,
                recent.net_worth,
                recent.match_duration_s
            FROM recent
            LEFT JOIN match_participant AS participant
                ON participant.match_id = recent.match_id
               AND participant.account_id = recent.account_id
            LEFT JOIN match_metadata AS metadata
                ON metadata.match_id = recent.match_id
            """,
            (account_id, max(1, window_matches)),
        ).fetchall()

    return [
        RecentMatch(
            match_id=int(row["match_id"]),
            hero_id=int(row["hero_id"]) if row["hero_id"] is not None else 0,
            start_time=row["start_time"],
            won=None if row["resolved_won"] is None else bool(row["resolved_won"]),
            kills=int(row["kills"] or 0),
            deaths=int(row["deaths"] or 0),
            assists=int(row["assists"] or 0),
            net_worth=int(row["net_worth"] or 0),
            match_duration_s=int(row["match_duration_s"] or 0),
        )
        for row in rows
    ]


def _recent_item_paths_payload(
    settings: Settings,
    account_id: int,
    *,
    hero_name: str | None = None,
    window_matches: int = 5,
    items_per_match: int = 5,
) -> list[dict[str, Any]]:
    recent_matches = _load_recent_matches(settings, account_id, max(1, window_matches))
    selected_matches = recent_matches

    if hero_name:
        lowered = hero_name.strip().casefold()
        selected_matches = [
            match
            for match in recent_matches
            if hero_label(settings, match.hero_id).casefold() == lowered
        ]

    selected_matches = selected_matches[: max(1, window_matches)]
    if not selected_matches:
        return []

    match_ids = [match.match_id for match in selected_matches]
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
            [account_id, *match_ids],
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
                "item_tier": item_tier(settings, item_id),
                "bought_at_s": float(row["bought_at_s"] or 0.0),
            }
        )

    return [
        {
            "match_id": match.match_id,
            "hero_id": match.hero_id,
            "hero_label": hero_label(settings, match.hero_id),
            "won": match.won,
            "kills": match.kills,
            "deaths": match.deaths,
            "assists": match.assists,
            "items": grouped.get(match.match_id, []),
        }
        for match in selected_matches
    ]


def _describe_branch_from_paths(paths: list[dict[str, Any]], prefix_items: int = 3) -> tuple[list[str], int]:
    branch_counts = Counter(
        tuple(item["item_label"] for item in path["items"][:prefix_items] if item.get("item_label"))
        for path in paths
        if path.get("items")
    )
    branch_counts.pop((), None)
    if not branch_counts:
        return ([], 0)

    branch, count = branch_counts.most_common(1)[0]
    return (list(branch), count)


def normalize_reply_text(text: str) -> str:
    normalized = str(text or "").replace("\r", "").strip()
    if not normalized:
        return ""

    normalized = re.sub(r":\s+-\s+", ":\n- ", normalized)
    normalized = re.sub(r"([.?!])\s+-\s+(?=[A-Z0-9])", r"\1\n- ", normalized)
    normalized = re.sub(r"\s+-\s+(?=[A-Z][A-Za-z0-9 /'()]{0,40}:)", "\n- ", normalized)
    normalized = re.sub(r"([.?!])\s+(\d+\.\s+)", r"\1\n\2", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _utility_reply(message: str) -> dict[str, Any] | None:
    lowered = normalized_message(message)
    now = datetime.now().astimezone()

    if "what day is it" in lowered or "what date is it" in lowered or lowered in {"date?", "day?"}:
        return {
            "insight": "Utility reply",
            "reply": normalize_reply_text(f"Today is {now.strftime('%A, %B')} {now.day}, {now.year}."),
            "evidence": [],
            "source": "utility",
            "context": {},
        }

    if "what time is it" in lowered or lowered in {"time?", "time"}:
        return {
            "insight": "Utility reply",
            "reply": normalize_reply_text(f"It is {now.strftime('%H:%M %Z')} right now."),
            "evidence": [],
            "source": "utility",
            "context": {},
        }

    return None


def utility_reply_for_message(message: str) -> dict[str, Any] | None:
    return _utility_reply(message)


def account_summary_payload(settings: Settings, summary: AccountSummary) -> dict[str, Any]:
    hero_rows = [
        {
            "hero_id": item.hero_id,
            "hero_label": hero_label(settings, item.hero_id),
            "games": item.games,
            "resolved_games": item.resolved_games,
            "wins": item.wins,
            "win_rate": item.win_rate,
        }
        for item in summary.hero_performance
    ]
    item_rows = [
        {
            "item_id": item.item_id,
            "item_label": item_label(settings, item.item_id),
            "purchases": item.purchases,
            "avg_bought_at_s": item.avg_bought_at_s,
        }
        for item in summary.item_timings
    ]

    top_hero_source = _top_sample_hero(summary)
    top_hero = next((row for row in hero_rows if top_hero_source and row["hero_id"] == top_hero_source.hero_id), None)
    top_item = item_rows[0] if item_rows else None

    return {
        "account_id": summary.account_id,
        "total_matches": summary.total_matches,
        "resolved_outcome_matches": summary.resolved_outcome_matches,
        "unknown_outcome_matches": summary.unknown_outcome_matches,
        "wins": summary.wins,
        "losses": summary.losses,
        "win_rate": summary.win_rate,
        "avg_kills": summary.avg_kills,
        "avg_deaths": summary.avg_deaths,
        "avg_assists": summary.avg_assists,
        "avg_net_worth": summary.avg_net_worth,
        "latest_start_time": summary.latest_start_time,
        "hydrated_match_count": summary.hydrated_match_count,
        "hero_performance": hero_rows,
        "item_timings": item_rows,
        "focus": {
            "top_hero": top_hero,
            "top_item": top_item,
            "recent_form": (
                "limited"
                if summary.resolved_outcome_matches < max(3, min(summary.total_matches, 5))
                else "stabilize" if summary.win_rate < 45 else "push"
            ),
        },
    }


def recent_matches_payload(settings: Settings, account_id: int, window_matches: int = DEFAULT_WINDOW_MATCHES) -> dict[str, Any] | None:
    matches = _load_recent_matches(settings, account_id, max(1, window_matches))
    if not matches:
        return None

    matches = [
        {
            "match_id": match.match_id,
            "hero_id": match.hero_id,
            "hero_label": hero_label(settings, match.hero_id),
            "start_time": match.start_time,
            "won": match.won,
            "kills": match.kills,
            "deaths": match.deaths,
            "assists": match.assists,
            "net_worth": match.net_worth,
            "match_duration_s": match.match_duration_s,
        }
        for match in matches
    ]

    return {
        "account_id": account_id,
        "window_matches": max(1, window_matches),
        "matches": matches,
    }


def parse_context(payload: dict[str, Any] | None) -> CoachContext:
    payload = payload or {}

    def _parse_int(value: Any) -> int | None:
        if value in ("", None):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    window_matches = _parse_int(payload.get("window_matches")) or DEFAULT_WINDOW_MATCHES
    if window_matches <= 0:
        window_matches = DEFAULT_WINDOW_MATCHES

    return CoachContext(
        account_id=_parse_int(payload.get("account_id")),
        hero_id=_parse_int(payload.get("hero_id")),
        hero_name=(str(payload.get("hero_name")).strip() or None) if payload.get("hero_name") is not None else None,
        player_label=(str(payload.get("player_label")).strip() or None) if payload.get("player_label") is not None else None,
        window_matches=window_matches,
    )


def list_tracked_accounts(settings: Settings) -> list[dict[str, Any]]:
    if not settings.warehouse_db_path.exists() and not settings.memory_db_path.exists():
        return []

    with closing(_connect(settings.warehouse_db_path)) as connection:
        linked_account_ref = """
            (
                SELECT
                    NULL AS account_id,
                    NULL AS persona_name,
                    NULL AS profile_url,
                    NULL AS avatar_url,
                    NULL AS country_code,
                    NULL AS matches_played_last_30d,
                    NULL AS last_team_avg_badge
                WHERE 0
            )
        """
        if settings.memory_db_path.exists():
            connection.execute("ATTACH DATABASE ? AS memory_db", (str(settings.memory_db_path),))
            linked_account_ref = "memory_db.linked_account"

        rows = connection.execute(
            f"""
            WITH tracked AS (
                SELECT account_id FROM player_match
                UNION
                SELECT account_id FROM {linked_account_ref}
            ),
            aggregates AS (
                SELECT
                    account_id,
                    COUNT(*) AS matches,
                    MAX(start_time) AS latest_start_time
                FROM player_match
                GROUP BY account_id
            )
            SELECT
                tracked.account_id AS account_id,
                COALESCE(aggregates.matches, 0) AS matches,
                aggregates.latest_start_time AS latest_start_time,
                linked_account.persona_name AS persona_name,
                linked_account.profile_url AS profile_url,
                linked_account.avatar_url AS avatar_url,
                linked_account.country_code AS country_code,
                linked_account.matches_played_last_30d AS matches_played_last_30d,
                linked_account.last_team_avg_badge AS last_team_avg_badge
            FROM tracked
            LEFT JOIN aggregates ON aggregates.account_id = tracked.account_id
            LEFT JOIN {linked_account_ref} AS linked_account ON linked_account.account_id = tracked.account_id
            ORDER BY latest_start_time DESC, matches DESC, tracked.account_id ASC
            """
        ).fetchall()

    return [
        {
            "account_id": int(row["account_id"]),
            "matches": int(row["matches"]),
            "latest_start_time": row["latest_start_time"],
            "label": row["persona_name"] or f"Account {int(row['account_id'])}",
            "persona_name": row["persona_name"],
            "profile_url": row["profile_url"],
            "avatar_url": row["avatar_url"],
            "country_code": row["country_code"],
            "matches_played_last_30d": row["matches_played_last_30d"],
            "last_team_avg_badge": row["last_team_avg_badge"],
        }
        for row in rows
    ]


def summarize_account(settings: Settings, account_id: int, window_matches: int = DEFAULT_WINDOW_MATCHES) -> AccountSummary | None:
    if not settings.warehouse_db_path.exists():
        return None

    with closing(_connect(settings.warehouse_db_path)) as connection:
        summary_row = connection.execute(
            """
            WITH recent AS (
                SELECT *
                FROM player_match
                WHERE account_id = ?
                ORDER BY start_time DESC
                LIMIT ?
            ),
            resolved_recent AS (
                SELECT
                    recent.*,
                    COALESCE(
                        recent.won,
                        CASE
                            WHEN participant.team IS NOT NULL AND metadata.winning_team IS NOT NULL
                            THEN CASE WHEN participant.team = metadata.winning_team THEN 1 ELSE 0 END
                            ELSE NULL
                        END
                    ) AS resolved_won
                FROM recent
                LEFT JOIN match_participant AS participant
                    ON participant.match_id = recent.match_id
                   AND participant.account_id = recent.account_id
                LEFT JOIN match_metadata AS metadata
                    ON metadata.match_id = recent.match_id
            )
            SELECT
                COUNT(*) AS total_matches,
                COUNT(resolved_won) AS resolved_outcome_matches,
                COALESCE(SUM(CASE WHEN resolved_won = 1 THEN 1 ELSE 0 END), 0) AS wins,
                COALESCE(SUM(CASE WHEN resolved_won = 0 THEN 1 ELSE 0 END), 0) AS losses,
                ROUND(100.0 * COALESCE(SUM(CASE WHEN resolved_won = 1 THEN 1 ELSE 0 END), 0) / NULLIF(COUNT(resolved_won), 0), 1) AS win_rate,
                ROUND(AVG(kills), 1) AS avg_kills,
                ROUND(AVG(deaths), 1) AS avg_deaths,
                ROUND(AVG(assists), 1) AS avg_assists,
                ROUND(AVG(net_worth), 1) AS avg_net_worth,
                MAX(start_time) AS latest_start_time
            FROM resolved_recent
            """,
            (account_id, window_matches),
        ).fetchone()

        if summary_row is None or int(summary_row["total_matches"]) == 0:
            return None

        hero_rows = connection.execute(
            """
            WITH recent AS (
                SELECT *
                FROM player_match
                WHERE account_id = ?
                ORDER BY start_time DESC
                LIMIT ?
            ),
            resolved_recent AS (
                SELECT
                    recent.*,
                    COALESCE(
                        recent.won,
                        CASE
                            WHEN participant.team IS NOT NULL AND metadata.winning_team IS NOT NULL
                            THEN CASE WHEN participant.team = metadata.winning_team THEN 1 ELSE 0 END
                            ELSE NULL
                        END
                    ) AS resolved_won
                FROM recent
                LEFT JOIN match_participant AS participant
                    ON participant.match_id = recent.match_id
                   AND participant.account_id = recent.account_id
                LEFT JOIN match_metadata AS metadata
                    ON metadata.match_id = recent.match_id
            )
            SELECT
                hero_id,
                COUNT(*) AS games,
                COUNT(resolved_won) AS resolved_games,
                COALESCE(SUM(CASE WHEN resolved_won = 1 THEN 1 ELSE 0 END), 0) AS wins,
                ROUND(100.0 * COALESCE(SUM(CASE WHEN resolved_won = 1 THEN 1 ELSE 0 END), 0) / NULLIF(COUNT(resolved_won), 0), 1) AS win_rate
            FROM resolved_recent
            GROUP BY hero_id
            ORDER BY games DESC, resolved_games DESC, wins DESC, hero_id ASC
            LIMIT 5
            """,
            (account_id, window_matches),
        ).fetchall()

        item_rows = connection.execute(
            """
            WITH recent_matches AS (
                SELECT match_id
                FROM player_match
                WHERE account_id = ?
                ORDER BY start_time DESC
                LIMIT ?
            )
            SELECT
                item_id,
                COUNT(*) AS purchases,
                ROUND(AVG(bought_at_s), 1) AS avg_bought_at_s
            FROM item_purchase
            WHERE account_id = ?
              AND match_id IN (SELECT match_id FROM recent_matches)
            GROUP BY item_id
            ORDER BY purchases DESC, avg_bought_at_s ASC, item_id ASC
            LIMIT ?
            """,
            (account_id, window_matches, account_id, MAX_CANDIDATE_ITEM_TIMINGS),
        ).fetchall()

        hydrated_match_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM match_metadata
                WHERE match_id IN (
                    SELECT match_id
                    FROM player_match
                    WHERE account_id = ?
                    ORDER BY start_time DESC
                    LIMIT ?
                )
                """,
                (account_id, window_matches),
            ).fetchone()[0]
        )

    verified_item_timings = _select_verified_item_timings(settings, item_rows)

    return AccountSummary(
        account_id=account_id,
        total_matches=int(summary_row["total_matches"]),
        resolved_outcome_matches=int(summary_row["resolved_outcome_matches"] or 0),
        unknown_outcome_matches=max(
            int(summary_row["total_matches"]) - int(summary_row["resolved_outcome_matches"] or 0),
            0,
        ),
        wins=int(summary_row["wins"]),
        losses=int(summary_row["losses"]),
        win_rate=float(summary_row["win_rate"] or 0.0),
        avg_kills=float(summary_row["avg_kills"] or 0.0),
        avg_deaths=float(summary_row["avg_deaths"] or 0.0),
        avg_assists=float(summary_row["avg_assists"] or 0.0),
        avg_net_worth=float(summary_row["avg_net_worth"] or 0.0),
        latest_start_time=summary_row["latest_start_time"],
        hero_performance=[
            HeroPerformance(
                hero_id=int(row["hero_id"]),
                games=int(row["games"]),
                resolved_games=int(row["resolved_games"] or 0),
                wins=int(row["wins"]),
                win_rate=float(row["win_rate"] or 0.0),
            )
            for row in hero_rows
        ],
        item_timings=verified_item_timings,
        hydrated_match_count=hydrated_match_count,
    )


def build_workspace_summary(settings: Settings, account_id: int | None = None, window_matches: int = DEFAULT_WINDOW_MATCHES) -> dict[str, Any]:
    payload = {"tracked_accounts": list_tracked_accounts(settings)}
    if account_id is not None:
        summary = summarize_account(settings, account_id, window_matches)
        payload["account_summary"] = None if summary is None else account_summary_payload(settings, summary)
        payload["selected_account"] = next(
            (account for account in payload["tracked_accounts"] if int(account["account_id"]) == account_id),
            None,
        )
    return payload


def json_dumps(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True).encode("utf-8")
