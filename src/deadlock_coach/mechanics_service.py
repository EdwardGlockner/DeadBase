from __future__ import annotations

import html
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from deadlock_coach.api import DeadlockApiClient
from deadlock_coach.config import Settings
from deadlock_coach.storage import SnapshotRecord, _json_dumps, save_json_snapshot

ITEM_ASSETS_ENDPOINT = "/v1/assets/items"

# Upstream descriptions embed inline SVG icons whose markup (path data, style
# attributes) runs to hundreds of characters per icon. The blocks must be
# removed wholesale — stripping tags alone would leak attribute-free text nodes
# nested inside them.
_SVG_BLOCK_RE = re.compile(r"<svg\b.*?</svg\s*>", re.IGNORECASE | re.DOTALL)
_SVG_SELF_CLOSED_RE = re.compile(r"<svg\b[^>]*/\s*>", re.IGNORECASE)
_MARKUP_TAG_RE = re.compile(r"<[^>]+>")


def sanitize_mechanics_text(text: Any) -> str:
    cleaned = str(text or "")
    cleaned = _SVG_BLOCK_RE.sub(" ", cleaned)
    cleaned = _SVG_SELF_CLOSED_RE.sub(" ", cleaned)
    cleaned = _MARKUP_TAG_RE.sub(" ", cleaned)
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _description_text(raw: Any) -> str:
    if isinstance(raw, dict):
        parts = [value for value in raw.values() if isinstance(value, str) and value.strip()]
        return sanitize_mechanics_text(" ".join(parts))
    return sanitize_mechanics_text(raw)


def _property_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_item_mechanics(settings: Settings, snapshot: SnapshotRecord, payload: Any) -> int:
    rows = payload if isinstance(payload, list) else []
    inserted = 0
    with closing(_connect(settings.warehouse_db_path)) as connection:
        connection.execute("DELETE FROM item_mechanic_property WHERE snapshot_id = ?", (snapshot.id,))
        connection.execute("DELETE FROM item_mechanic WHERE snapshot_id = ?", (snapshot.id,))
        for row in rows:
            if not isinstance(row, dict):
                continue
            if row.get("shopable") is not True:
                continue
            item_id = row.get("id")
            name = row.get("name")
            if not isinstance(item_id, int) or not isinstance(name, str) or not name.strip():
                continue
            connection.execute(
                """
                INSERT INTO item_mechanic (
                    snapshot_id,
                    item_id,
                    name,
                    item_tier,
                    cost,
                    item_slot_type,
                    is_active_item,
                    description,
                    raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.id,
                    item_id,
                    name.strip(),
                    row.get("item_tier") if isinstance(row.get("item_tier"), int) else None,
                    row.get("cost") if isinstance(row.get("cost"), int) else None,
                    str(row.get("item_slot_type")).strip() if isinstance(row.get("item_slot_type"), str) else None,
                    None if row.get("is_active_item") is None else int(bool(row.get("is_active_item"))),
                    _description_text(row.get("description")),
                    _json_dumps(row),
                ),
            )
            properties = row.get("properties")
            if isinstance(properties, dict):
                for property_key, property_value in properties.items():
                    if not isinstance(property_key, str) or not property_key.strip():
                        continue
                    detail = property_value if isinstance(property_value, dict) else {"value": property_value}
                    connection.execute(
                        """
                        INSERT INTO item_mechanic_property (
                            snapshot_id,
                            item_id,
                            property_key,
                            value,
                            label,
                            postfix,
                            css_class
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            snapshot.id,
                            item_id,
                            property_key.strip(),
                            _property_text(detail.get("value")),
                            _property_text(detail.get("label")),
                            _property_text(detail.get("postfix")),
                            _property_text(detail.get("css_class")),
                        ),
                    )
            inserted += 1
        connection.commit()
    return inserted


def sync_item_mechanics(settings: Settings, client: DeadlockApiClient | None = None) -> dict[str, Any]:
    client = client or DeadlockApiClient(settings)
    request_url, payload = client.fetch_json(ITEM_ASSETS_ENDPOINT)
    snapshot = save_json_snapshot(settings, "deadlock_api", "assets", "items", request_url, payload)
    items_stored = normalize_item_mechanics(settings, snapshot, payload)
    return {
        "endpoint": ITEM_ASSETS_ENDPOINT,
        "request_url": request_url,
        "snapshot_id": snapshot.id,
        "snapshot_path": str(snapshot.path),
        "fetched_at": snapshot.fetched_at,
        "items_stored": items_stored,
    }


def read_latest_item_mechanics(settings: Settings, item_name: str) -> dict[str, Any] | None:
    """Return the requested item's mechanics from the latest sync.

    Returns None when no item mechanics sync has been stored yet; once a sync
    exists, an unknown name yields an explicit ``item_not_found`` payload.
    """

    if not settings.warehouse_db_path.exists():
        return None

    with closing(_connect(settings.warehouse_db_path)) as connection:
        snapshot_row = connection.execute(
            """
            SELECT mechanic.snapshot_id, source.fetched_at
            FROM item_mechanic AS mechanic
            JOIN source_snapshot AS source
              ON source.id = mechanic.snapshot_id
            ORDER BY source.fetched_at DESC, mechanic.snapshot_id DESC
            LIMIT 1
            """
        ).fetchone()
        if snapshot_row is None:
            return None

        snapshot_id = int(snapshot_row["snapshot_id"])
        fetched_at = snapshot_row["fetched_at"]
        item_rows = connection.execute(
            """
            SELECT item_id, name, item_tier, cost, item_slot_type, is_active_item, description
            FROM item_mechanic
            WHERE snapshot_id = ?
            ORDER BY name ASC
            """,
            (snapshot_id,),
        ).fetchall()

        requested = str(item_name or "").strip()
        matched = _match_item_row(item_rows, requested)
        if matched is None:
            return {
                "source": "local_warehouse",
                "kind": "item_mechanics",
                "available": False,
                "status": "item_not_found",
                "requested_item": requested,
                "snapshot_id": snapshot_id,
                "fetched_at": fetched_at,
                "similar_items": _similar_names(item_rows, requested),
            }

        property_rows = connection.execute(
            """
            SELECT property_key, value, label, postfix, css_class
            FROM item_mechanic_property
            WHERE snapshot_id = ? AND item_id = ?
            ORDER BY property_key ASC
            """,
            (snapshot_id, int(matched["item_id"])),
        ).fetchall()

    is_active = matched["is_active_item"]
    return {
        "source": "local_warehouse",
        "kind": "item_mechanics",
        "available": True,
        "snapshot_id": snapshot_id,
        "fetched_at": fetched_at,
        "item": {
            "item_id": int(matched["item_id"]),
            "name": str(matched["name"]),
            "tier": None if matched["item_tier"] is None else int(matched["item_tier"]),
            "cost": None if matched["cost"] is None else int(matched["cost"]),
            "slot": matched["item_slot_type"],
            "activation": None if is_active is None else ("active" if int(is_active) else "passive"),
            "description": str(matched["description"] or ""),
            "properties": {
                str(row["property_key"]): {
                    "value": row["value"],
                    "label": row["label"],
                    "postfix": row["postfix"],
                    "css_class": row["css_class"],
                }
                for row in property_rows
            },
        },
    }


def _match_item_row(item_rows: list[sqlite3.Row], requested: str) -> sqlite3.Row | None:
    normalized = requested.casefold()
    if not normalized:
        return None
    for row in item_rows:
        if str(row["name"]).casefold() == normalized:
            return row
    contains = [row for row in item_rows if normalized in str(row["name"]).casefold()]
    if len(contains) == 1:
        return contains[0]
    return None


def _similar_names(item_rows: list[sqlite3.Row], requested: str, limit: int = 5) -> list[str]:
    tokens = [token for token in re.split(r"[^a-z0-9]+", requested.casefold()) if len(token) >= 3]
    if not tokens:
        return []
    matches = [
        str(row["name"])
        for row in item_rows
        if any(token in str(row["name"]).casefold() for token in tokens)
    ]
    return matches[:limit]


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection
