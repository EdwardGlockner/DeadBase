from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from deadlock_coach.config import Settings


LOGGER = logging.getLogger("deadlock_coach.telemetry")


def new_request_id() -> str:
    return uuid4().hex


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def emit_event(settings: Settings, event_type: str, **payload: Any) -> dict[str, Any]:
    event = {
        "ts": time.time(),
        "event_type": event_type,
        **payload,
    }
    path = settings.telemetry_events_path
    _ensure_parent(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")
    LOGGER.info("%s", json.dumps(event, ensure_ascii=True, sort_keys=True))
    return event


def read_recent_events(settings: Settings, *, limit: int = 50) -> list[dict[str, Any]]:
    path = settings.telemetry_events_path
    if not path.exists():
        return []

    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if limit <= 0:
        return events
    return events[-limit:]


@contextmanager
def traced_operation(
    settings: Settings,
    event_type: str,
    *,
    request_id: str,
    **payload: Any,
) -> Iterator[dict[str, Any]]:
    started_at = time.perf_counter()
    emit_event(settings, f"{event_type}.start", request_id=request_id, **payload)
    state: dict[str, Any] = {"request_id": request_id}
    try:
        yield state
    except Exception as exc:
        emit_event(
            settings,
            f"{event_type}.error",
            request_id=request_id,
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            error=str(exc),
            **payload,
        )
        raise
    else:
        emit_event(
            settings,
            f"{event_type}.finish",
            request_id=request_id,
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            **payload,
            **{key: value for key, value in state.items() if key != "request_id"},
        )
