from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True, slots=True)
class ActiveCoachContext:
    account_id: int | None = None
    player_label: str | None = None
    hero_name: str | None = None
    window_matches: int | None = None


_ACTIVE_COACH_CONTEXT: ContextVar[ActiveCoachContext | None] = ContextVar(
    "deadlock_coach_active_context",
    default=None,
)
_ACTIVE_COACH_CONTEXT_FALLBACK: ActiveCoachContext | None = None


def get_active_coach_context() -> ActiveCoachContext | None:
    return _ACTIVE_COACH_CONTEXT.get() or _ACTIVE_COACH_CONTEXT_FALLBACK


@contextmanager
def use_active_coach_context(context: ActiveCoachContext | None) -> Iterator[None]:
    global _ACTIVE_COACH_CONTEXT_FALLBACK
    previous_fallback = _ACTIVE_COACH_CONTEXT_FALLBACK
    _ACTIVE_COACH_CONTEXT_FALLBACK = context
    token: Token[ActiveCoachContext | None] = _ACTIVE_COACH_CONTEXT.set(context)
    try:
        yield
    finally:
        _ACTIVE_COACH_CONTEXT.reset(token)
        _ACTIVE_COACH_CONTEXT_FALLBACK = previous_fallback
