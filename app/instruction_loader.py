from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_instruction(anchor: str | Path, filename: str, **replacements: str) -> str:
    base = Path(anchor).resolve().parent
    path = (base / filename).resolve()
    if not path.is_relative_to(base):
        raise ValueError(
            f"Instruction filename must not escape the anchor directory: {filename}"
        )
    if not path.is_file():
        raise FileNotFoundError(f"Instruction file not found: {path}")
    body = path.read_text(encoding="utf-8").strip()
    for key, value in replacements.items():
        body = body.replace(f"{{{{{key}}}}}", value.strip())
    logger.info("Loaded instruction file %s (%d chars)", filename, len(body))
    return body.strip()
