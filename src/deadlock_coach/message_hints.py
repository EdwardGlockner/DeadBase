from __future__ import annotations


def normalized_message(message: str) -> str:
    return " ".join(message.lower().strip().split())


def looks_like_concept_clarifier(lowered: str) -> bool:
    return lowered in {
        "what do you mean",
        "what do you mean?",
        "what?",
        "why?",
        "why",
        "how so?",
        "how so",
    }


def looks_like_contextual_followup(lowered: str) -> bool:
    return lowered.startswith(
        (
            "no i mean",
            "i mean",
            "no, i mean",
            "what about",
            "and in",
            "and what about",
            "for everyone",
            "for eternus",
            "in eternus",
            "in phantom",
            "in ascendant",
            "in oracle",
            "in archon",
            "in emissary",
            "in ritualist",
            "in arcanist",
            "in alchemist",
            "in seeker",
            "in initiate",
        )
    )


def looks_like_full_history_request(lowered: str) -> bool:
    return any(
        phrase in lowered
        for phrase in (
            "all games i have ever played",
            "all games ive ever played",
            "all games i ever played",
            "all my games",
            "full history",
            "full local sample",
            "all-time",
            "all time",
        )
    )


def effective_knowledge_query(message: str, history: list[dict[str, object]] | None = None) -> str:
    lowered = normalized_message(message)
    if not looks_like_concept_clarifier(lowered) or not history:
        return message

    for turn in reversed(history):
        if turn.get("role") != "user":
            continue
        text = str(turn.get("text") or "").strip()
        if not text or normalized_message(text) == lowered:
            continue
        return f"{text}\n{message}"
    return message
