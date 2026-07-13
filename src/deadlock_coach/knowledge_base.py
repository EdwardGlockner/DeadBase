from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
import time
from contextlib import closing
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from deadlock_coach.config import Settings


WIKI_API_URL = "https://deadlock.wiki/api.php"
WIKI_USER_AGENT = "deadlock-coach/0.1 (knowledge import)"
WIKI_PAGE_EXTRACT_MAX_AGE_S = 7 * 24 * 60 * 60
WIKI_CATEGORY_MAX_AGE_S = 24 * 60 * 60

HERO_CATEGORY_TITLE = "Category:Heroes"
ITEM_CATEGORY_TITLE = "Category:Items"
PAGE_NAMESPACE = 0

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

REFERENCE_KINDS = ("heroes", "items", "pages")

SEMANTIC_QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    "weapon": ("bullet", "bullet damage", "weapon damage"),
    "gun": ("bullet", "bullet damage", "weapon damage"),
    "investment": ("souls", "bonus"),
    "vitality": ("health",),
    "health": ("vitality",),
    "spirit": ("spirit power",),
}


class _WikiHtmlToMarkdownParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self._capture_tag: str | None = None
        self._capture_level: int | None = None
        self._capture_parts: list[str] = []
        self._ignore_depth = 0

        self._in_table = False
        self._table_caption: str = ""
        self._table_headers: list[str] = []
        self._table_rows: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell_is_header = False
        self._current_cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value for key, value in attrs}
        classes = str(attr_map.get("class") or "")
        if tag in {"script", "style"}:
            self._ignore_depth += 1
            return
        if "mw-editsection" in classes or "reference" in classes or "toc" in classes or "navbox" in classes:
            self._ignore_depth += 1
            return
        if self._ignore_depth > 0:
            return

        if tag in {"h2", "h3", "h4"}:
            self._capture_tag = tag
            self._capture_level = int(tag[1])
            self._capture_parts = []
            return
        if tag == "p":
            self._capture_tag = tag
            self._capture_parts = []
            return
        if tag == "li":
            self._capture_tag = tag
            self._capture_parts = []
            return
        if tag == "br" and self._capture_tag is not None:
            self._capture_parts.append(" ")
            return

        if tag == "table":
            self._in_table = True
            self._table_caption = ""
            self._table_headers = []
            self._table_rows = []
            return
        if not self._in_table:
            return
        if tag == "caption":
            self._capture_tag = tag
            self._capture_parts = []
            return
        if tag == "tr":
            self._current_row = []
            return
        if tag in {"th", "td"}:
            self._current_cell_is_header = tag == "th"
            self._current_cell_parts = []
            return

    def handle_endtag(self, tag: str) -> None:
        if self._ignore_depth > 0:
            if tag in {"script", "style", "span", "div", "nav", "aside", "section"}:
                self._ignore_depth -= 1
            return

        if tag in {"h2", "h3", "h4", "p", "li", "caption"} and self._capture_tag == tag:
            text = self._normalize("".join(self._capture_parts))
            if text:
                if tag in {"h2", "h3", "h4"}:
                    self.lines.append(f"{'#' * int(self._capture_level or 2)} {text}")
                elif tag == "li":
                    self.lines.append(f"- {text}")
                elif tag == "caption" and self._in_table:
                    self._table_caption = text
                else:
                    self.lines.append(text)
            self._capture_tag = None
            self._capture_level = None
            self._capture_parts = []
            return

        if not self._in_table:
            return
        if tag in {"th", "td"} and self._current_cell_parts is not None:
            text = self._normalize("".join(self._current_cell_parts))
            self._current_row.append(text)
            if self._current_cell_is_header and text and text not in self._table_headers:
                self._table_headers.append(text)
            self._current_cell_parts = None
            self._current_cell_is_header = False
            return
        if tag == "tr":
            row = [cell for cell in self._current_row if cell]
            if row:
                if row != self._table_headers:
                    self._table_rows.append(row)
            self._current_row = []
            return
        if tag == "table":
            self._flush_table()
            self._in_table = False
            return

    def handle_data(self, data: str) -> None:
        if self._ignore_depth > 0:
            return
        if self._current_cell_parts is not None and self._in_table:
            self._current_cell_parts.append(data)
        elif self._capture_tag is not None:
            self._capture_parts.append(data)

    def _normalize(self, text: str) -> str:
        return " ".join(text.replace("\xa0", " ").split()).strip()

    def _flush_table(self) -> None:
        if not self._table_headers and not self._table_rows:
            return
        if self._table_caption:
            self.lines.append(f"### {self._table_caption}")
        headers = self._table_headers or [f"Column {idx + 1}" for idx in range(max((len(row) for row in self._table_rows), default=0))]
        if headers:
            self.lines.append("| " + " | ".join(headers) + " |")
            self.lines.append("| " + " | ".join("---" for _ in headers) + " |")
            for row in self._table_rows:
                padded = row + [""] * max(0, len(headers) - len(row))
                self.lines.append("| " + " | ".join(padded[: len(headers)]) + " |")


def _wiki_html_to_markdown(html: str) -> str:
    parser = _WikiHtmlToMarkdownParser()
    parser.feed(html)
    return "\n\n".join(line for line in parser.lines if line.strip()).strip()


def curated_knowledge_root(settings: Settings) -> Path:
    return settings.project_root / "docs" / "knowledge"


def imported_knowledge_root(settings: Settings) -> Path:
    return curated_knowledge_root(settings) / "_imports" / "wiki"


def wiki_cache_root(settings: Settings) -> Path:
    return settings.cache_dir / "wiki"


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "page"


def _clean_knowledge_line(line: str) -> str:
    cleaned = line.strip()
    if cleaned.startswith("-"):
        cleaned = cleaned[1:].strip()
    return cleaned


def _clean_knowledge_content_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    cleaned = _clean_knowledge_line(stripped)
    lowered = cleaned.lower()
    if not cleaned:
        return None
    if lowered in {"imported reference", "reference extract:"}:
        return None
    if lowered.startswith(("kind:", "source:", "url:", "imported_at:", "path:")):
        return None
    if lowered.startswith(("deadlock wiki page", "local coaching note")):
        return None
    if lowered.startswith("use this when "):
        return None
    if cleaned.endswith(":") and len(cleaned.split()) <= 5:
        return None
    return cleaned


def knowledge_content_lines(body: str) -> list[str]:
    return [cleaned for line in body.splitlines() if (cleaned := _clean_knowledge_content_line(line))]


def knowledge_heading(path: Path, root: Path) -> str:
    body = path.read_text(encoding="utf-8")
    return next(
        (line.lstrip("#").strip() for line in body.splitlines() if line.strip().startswith("#")),
        path.relative_to(root).stem.replace("-", " ").replace("_", " ").title(),
    )


def knowledge_query_terms(query: str) -> list[str]:
    raw_terms = re.findall(r"[a-z0-9.]+", query.lower())
    terms: list[str] = []
    for raw_term in raw_terms:
        if len(raw_term) <= 2 and not any(char.isdigit() for char in raw_term):
            continue
        terms.append(raw_term)
        if raw_term.endswith("ies") and len(raw_term) > 4:
            terms.append(f"{raw_term[:-3]}y")
        elif raw_term.endswith("es") and len(raw_term) > 4:
            terms.append(raw_term[:-2])
        elif raw_term.endswith("s") and len(raw_term) > 4 and not raw_term.endswith("ss"):
            terms.append(raw_term[:-1])
    return list(dict.fromkeys(terms))


def _normalize_search_text(text: str) -> str:
    normalized = text.lower().replace("\xa0", " ")
    normalized = normalized.replace("‑", "-").replace("–", "-").replace("—", "-")
    normalized = normalized.replace(",", "")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _entity_variants(title: str) -> list[str]:
    normalized = _normalize_search_text(title)
    if not normalized:
        return []
    variants = {normalized}
    if normalized.startswith("the "):
        variants.add(normalized[4:])
    if "&" in normalized:
        variants.add(normalized.replace("&", "and"))
    if " and " in normalized:
        variants.add(normalized.replace(" and ", " & "))
    return [variant.strip() for variant in variants if variant.strip()]


def _query_term_variants(term: str) -> list[str]:
    lowered = term.lower().strip()
    if not lowered:
        return []

    variants = {lowered, lowered.replace(",", "")}
    match = re.fullmatch(r"(\d+(?:\.\d+)?)k", lowered.replace(",", ""))
    if match:
        raw_value = int(round(float(match.group(1)) * 1000))
        variants.add(str(raw_value))
        variants.add(f"{raw_value:,}".lower())
        variants.add(f"{raw_value / 1000:g}k")
    elif lowered.replace(",", "").isdigit():
        raw_value = int(lowered.replace(",", ""))
        variants.add(str(raw_value))
        variants.add(f"{raw_value:,}".lower())
        if raw_value >= 1000:
            variants.add(f"{raw_value / 1000:g}k")
    for alias in SEMANTIC_QUERY_ALIASES.get(lowered, ()):
        variants.add(alias.lower())
    return [variant for variant in variants if variant]


def _query_term_variant_map(query_terms: list[str]) -> dict[str, list[str]]:
    return {term: _query_term_variants(term) for term in query_terms}


def iter_knowledge_files(root: Path, *, include_internal: bool = False) -> list[Path]:
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


def knowledge_note_excerpt(settings: Settings, relative_path: str, *, max_lines: int = 5) -> str | None:
    path = settings.project_root / relative_path
    if not path.exists():
        return None
    lines = knowledge_content_lines(path.read_text(encoding="utf-8"))
    if not lines:
        return None
    return " ".join(lines[: max(1, max_lines)]).strip()


def _knowledge_group(relative: Path) -> str:
    return relative.parts[0] if len(relative.parts) > 1 else "root"


def _chunk_text(lines: list[str], *, lines_per_chunk: int = 6) -> list[str]:
    if not lines:
        return []
    chunks: list[str] = []
    for start in range(0, len(lines), max(1, lines_per_chunk)):
        chunk = " ".join(lines[start : start + max(1, lines_per_chunk)]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def _section_chunks(path: Path, root: Path, project_root: Path, *, imported: bool) -> list[dict[str, Any]]:
    body = path.read_text(encoding="utf-8")
    relative = path.relative_to(root)
    title = knowledge_heading(path, root)
    file_mtime_ns = path.stat().st_mtime_ns
    current_section = title
    section_lines: list[str] = []
    chunks: list[dict[str, Any]] = []

    def flush_section() -> None:
        if not section_lines:
            return
        for position, chunk in enumerate(_chunk_text(section_lines), start=1):
            chunks.append(
                {
                    "relative_path": str(path.relative_to(project_root)),
                    "source_type": "knowledge_imports" if imported else "knowledge_base",
                    "group_name": _knowledge_group(relative),
                    "title": title,
                    "section_title": current_section,
                    "body": chunk,
                    "file_mtime_ns": file_mtime_ns,
                    "chunk_position": position,
                }
            )

    for raw_line in body.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("#"):
            flush_section()
            section_lines = []
            level = len(stripped) - len(stripped.lstrip("#"))
            heading = stripped.lstrip("#").strip()
            if level == 1:
                title = heading or title
                current_section = title
            else:
                current_section = heading or current_section or title
            continue

        cleaned = _clean_knowledge_content_line(raw_line)
        if cleaned:
            section_lines.append(cleaned)

    flush_section()
    if chunks:
        return chunks

    return [
        {
            "relative_path": str(path.relative_to(project_root)),
            "source_type": "knowledge_imports" if imported else "knowledge_base",
            "group_name": _knowledge_group(relative),
            "title": title,
            "section_title": title,
            "body": "",
            "file_mtime_ns": file_mtime_ns,
            "chunk_position": 1,
        }
    ]


def _knowledge_index_signature(settings: Settings) -> str:
    entries: list[str] = []
    for root, include_internal in (
        (curated_knowledge_root(settings), False),
        (imported_knowledge_root(settings), True),
    ):
        for path in iter_knowledge_files(root, include_internal=include_internal):
            relative = path.relative_to(settings.project_root)
            entries.append(f"{relative}|{path.stat().st_mtime_ns}")
    digest = hashlib.sha256("\n".join(sorted(entries)).encode("utf-8")).hexdigest()
    return digest


def _ensure_knowledge_index(settings: Settings) -> None:
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    with closing(_connect(settings.knowledge_db_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS knowledge_index_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge_chunk (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                relative_path TEXT NOT NULL,
                source_type TEXT NOT NULL,
                group_name TEXT NOT NULL,
                title TEXT NOT NULL,
                section_title TEXT NOT NULL,
                body TEXT NOT NULL,
                file_mtime_ns INTEGER NOT NULL,
                chunk_position INTEGER NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunk_fts
            USING fts5(
                title,
                section_title,
                body,
                relative_path,
                content='',
                tokenize='porter unicode61'
            );
            """
        )

        current_signature = _knowledge_index_signature(settings)
        indexed_signature_row = connection.execute(
            "SELECT value FROM knowledge_index_meta WHERE key = 'signature'"
        ).fetchone()
        indexed_signature = str(indexed_signature_row["value"]) if indexed_signature_row is not None else None
        if indexed_signature == current_signature:
            return

        connection.execute("DELETE FROM knowledge_chunk")
        connection.execute("DROP TABLE IF EXISTS knowledge_chunk_fts")
        connection.execute(
            """
            CREATE VIRTUAL TABLE knowledge_chunk_fts
            USING fts5(
                title,
                section_title,
                body,
                relative_path,
                content='',
                tokenize='porter unicode61'
            )
            """
        )

        rows: list[dict[str, Any]] = []
        for root, include_internal, imported in (
            (curated_knowledge_root(settings), False, False),
            (imported_knowledge_root(settings), True, True),
        ):
            for path in iter_knowledge_files(root, include_internal=include_internal):
                rows.extend(_section_chunks(path, root, settings.project_root, imported=imported))

        for row in rows:
            cursor = connection.execute(
                """
                INSERT INTO knowledge_chunk (
                    relative_path,
                    source_type,
                    group_name,
                    title,
                    section_title,
                    body,
                    file_mtime_ns,
                    chunk_position
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["relative_path"],
                    row["source_type"],
                    row["group_name"],
                    row["title"],
                    row["section_title"],
                    row["body"],
                    row["file_mtime_ns"],
                    row["chunk_position"],
                ),
            )
            connection.execute(
                """
                INSERT INTO knowledge_chunk_fts (
                    rowid,
                    title,
                    section_title,
                    body,
                    relative_path
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    int(cursor.lastrowid),
                    row["title"],
                    row["section_title"],
                    row["body"],
                    row["relative_path"],
                ),
            )

        connection.execute(
            """
            INSERT INTO knowledge_index_meta(key, value)
            VALUES ('signature', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (current_signature,),
        )
        connection.commit()


def extract_knowledge_entities(
    settings: Settings,
    query: str,
    *,
    limit: int = 6,
    source_filter: str | None = None,
    group_filters: list[str] | None = None,
) -> list[dict[str, Any]]:
    normalized_query = _normalize_search_text(query)
    if not normalized_query:
        return []

    _ensure_knowledge_index(settings)
    source_clause = ""
    group_clause = ""
    params: list[Any] = []
    if source_filter is not None:
        source_clause = "WHERE source_type = ?"
        params.append(source_filter)
    if group_filters:
        prefix = "AND" if source_clause else "WHERE"
        placeholders = ", ".join("?" for _ in group_filters)
        group_clause = f" {prefix} group_name IN ({placeholders})"
        params.extend(group_filters)

    with closing(_connect(settings.knowledge_db_path)) as connection:
        rows = connection.execute(
            f"""
            SELECT DISTINCT relative_path, source_type, group_name, title
            FROM knowledge_chunk
            {source_clause}
            {group_clause}
            ORDER BY title ASC, relative_path ASC
            """,
            tuple(params),
        ).fetchall()

    matches: list[dict[str, Any]] = []
    for row in rows:
        title = str(row["title"] or "").strip()
        if not title:
            continue
        matched_variant = next((variant for variant in _entity_variants(title) if variant and variant in normalized_query), None)
        if matched_variant is None:
            continue
        score = float(len(matched_variant.split()) * 10)
        if _normalize_search_text(title) == matched_variant:
            score += 8.0
        matches.append(
            {
                "title": title,
                "relative_path": str(row["relative_path"] or ""),
                "source": str(row["source_type"] or "knowledge_base"),
                "group_name": str(row["group_name"] or "root"),
                "matched_variant": matched_variant,
                "score": score,
            }
        )

    matches.sort(key=lambda item: (-float(item["score"]), item["source"] != "knowledge_base", item["title"]))
    return matches[: max(1, limit)]


def _lookup_entity_chunks(
    settings: Settings,
    entities: list[dict[str, Any]],
    *,
    source_filter: str | None = None,
    group_filters: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not entities:
        return []

    _ensure_knowledge_index(settings)
    titles = [str(entity["title"]) for entity in entities if entity.get("title")]
    if not titles:
        return []

    placeholders = ", ".join("?" for _ in titles)
    params: list[Any] = [*titles]
    filters = [f"title IN ({placeholders})"]
    if source_filter is not None:
        filters.append("source_type = ?")
        params.append(source_filter)
    if group_filters:
        group_placeholders = ", ".join("?" for _ in group_filters)
        filters.append(f"group_name IN ({group_placeholders})")
        params.extend(group_filters)

    with closing(_connect(settings.knowledge_db_path)) as connection:
        rows = connection.execute(
            f"""
            SELECT relative_path, source_type, group_name, title, section_title, body, chunk_position
            FROM knowledge_chunk
            WHERE {' AND '.join(filters)}
            ORDER BY chunk_position ASC, relative_path ASC
            """,
            tuple(params),
        ).fetchall()

    entity_by_title = {str(entity["title"]): entity for entity in entities if entity.get("title")}
    best_by_title: dict[str, dict[str, Any]] = {}
    for row in rows:
        title = str(row["title"] or "")
        if title in best_by_title:
            continue
        entity = entity_by_title.get(title)
        if entity is None:
            continue
        best_by_title[title] = {
            "relative_path": str(row["relative_path"] or ""),
            "title": title,
            "section_title": str(row["section_title"] or title),
            "score": float(entity["score"]) + 25.0 - min(int(row["chunk_position"] or 1), 10),
            "excerpt": str(row["body"] or "")[:280],
            "source": str(row["source_type"] or "knowledge_base"),
            "imported": str(row["source_type"] or "knowledge_base") == "knowledge_imports",
            "entity_match": True,
        }
    return list(best_by_title.values())


def search_local_knowledge(
    settings: Settings,
    query: str,
    *,
    limit: int = 5,
    source_filter: str | None = None,
    group_filters: list[str] | None = None,
) -> list[dict[str, Any]]:
    normalized_query = query.strip()
    if not normalized_query:
        return []

    _ensure_knowledge_index(settings)
    query_terms = knowledge_query_terms(normalized_query)
    if not query_terms:
        return []

    term_variants = _query_term_variant_map(query_terms)

    match_expression = " OR ".join(f'"{term}"' for term in query_terms)
    if not match_expression:
        return []

    source_clause = ""
    group_clause = ""
    params: list[Any] = [match_expression]
    if source_filter is not None:
        source_clause = "AND kc.source_type = ?"
        params.append(source_filter)
    if group_filters:
        placeholders = ", ".join("?" for _ in group_filters)
        group_clause = f"AND kc.group_name IN ({placeholders})"
        params.extend(group_filters)
    params.append(max(limit * 12, 24))

    with closing(_connect(settings.knowledge_db_path)) as connection:
        rows = connection.execute(
            f"""
            SELECT
                kc.relative_path,
                kc.source_type,
                kc.group_name,
                kc.title,
                kc.section_title,
                kc.body,
                bm25(knowledge_chunk_fts, 8.0, 4.0, 1.0, 6.0) AS fts_score
            FROM knowledge_chunk_fts
            JOIN knowledge_chunk AS kc
              ON kc.id = knowledge_chunk_fts.rowid
            WHERE knowledge_chunk_fts MATCH ?
              {source_clause}
              {group_clause}
            ORDER BY fts_score
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()

    ranked: list[dict[str, Any]] = []
    lowered_query = normalized_query.lower()
    numeric_terms = [term for term in query_terms if any(char.isdigit() for char in term)]
    for row in rows:
        title = str(row["title"] or "")
        section_title = str(row["section_title"] or "")
        body = str(row["body"] or "")
        relative_path = str(row["relative_path"] or "")
        source_type = str(row["source_type"] or "knowledge_base")
        imported = source_type == "knowledge_imports"
        score = float(-(row["fts_score"] or 0.0))
        title_lowered = title.lower()
        section_lowered = section_title.lower()
        body_lowered = body.lower()
        relative_lowered = relative_path.lower()
        title_normalized = _normalize_search_text(title)
        section_normalized = _normalize_search_text(section_title)
        body_normalized = _normalize_search_text(body)
        relative_normalized = _normalize_search_text(relative_path)
        is_table_excerpt = "|" in body

        if not imported:
            score += 8.0
        if lowered_query in title_lowered:
            score += 12.0
        if lowered_query in section_lowered:
            score += 8.0
        if lowered_query in body_lowered:
            score += 5.0
        if lowered_query in relative_lowered:
            score += 10.0
        if relative_lowered.endswith("/index.md") or relative_lowered.endswith("index.md"):
            score -= 8.0
        if "/" in title and "/" not in lowered_query:
            score -= 6.0

        title_hits = 0
        section_hits = 0
        body_hits = 0
        for term in query_terms:
            term_pattern = rf"\b{re.escape(term)}\b"
            numeric_weight = 2.0 if term in numeric_terms else 1.0
            if re.search(term_pattern, title_lowered):
                title_hits += 1
                score += 6.0 * numeric_weight
            if re.search(term_pattern, section_lowered):
                section_hits += 1
                score += 3.0 * numeric_weight
            body_matches = len(re.findall(term_pattern, body_lowered))
            body_hits += body_matches
            score += float(body_matches) * numeric_weight
            for variant in term_variants.get(term, []):
                if variant and variant in title_normalized:
                    score += 5.0 * numeric_weight
                if variant and variant in section_normalized:
                    score += 3.0 * numeric_weight
                if variant and variant in body_normalized:
                    score += 2.0 * numeric_weight
                if variant and variant in relative_normalized:
                    score += 4.0 * numeric_weight
        if title_hits and title_hits == len(query_terms):
            score += 10.0
        if section_hits and section_hits == len(query_terms):
            score += 6.0
        coverage = title_hits + section_hits + min(body_hits, len(query_terms))
        score += min(coverage, len(query_terms)) * 1.5
        if is_table_excerpt and numeric_terms:
            matching_numeric_variants = sum(
                1
                for term in numeric_terms
                if any(variant in body_normalized or variant in section_normalized for variant in term_variants.get(term, []))
            )
            score += matching_numeric_variants * 10.0
        if imported and is_table_excerpt:
            score += 6.0

        ranked.append(
            {
                "relative_path": relative_path,
                "title": title,
                "section_title": section_title,
                "score": score,
                "excerpt": body[:280],
                "source": source_type,
                "imported": imported,
            }
        )

    ranked.sort(key=lambda item: (-item["score"], item["imported"], item["relative_path"], item["section_title"]))
    deduped: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for row in ranked:
        key = (row["relative_path"], row["section_title"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(row)
        if len(deduped) >= max(1, limit):
            break
    return deduped


def _markdown_table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_markdown_table_separator(cells: list[str]) -> bool:
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells if cell)


def _trim_empty_table_columns(headers: list[str], rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    trimmed_headers = list(headers)
    trimmed_rows = [list(row) for row in rows]
    while trimmed_headers and not trimmed_headers[-1] and all((len(row) < len(trimmed_headers) or not row[len(trimmed_headers) - 1]) for row in trimmed_rows):
        trimmed_headers.pop()
    normalized_rows: list[list[str]] = []
    for row in trimmed_rows:
        padded = row + [""] * max(0, len(trimmed_headers) - len(row))
        normalized_rows.append(padded[: len(trimmed_headers)])
    return trimmed_headers, normalized_rows


def _looks_like_duplicate_table_header(row: list[str], headers: list[str]) -> bool:
    if not row or not headers:
        return False
    normalized_row = [cell.casefold() for cell in row if cell]
    normalized_headers = [cell.casefold() for cell in headers if cell]
    return bool(normalized_row) and normalized_row == normalized_headers[: len(normalized_row)]


def _iter_knowledge_tables(settings: Settings) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    project_root = settings.project_root
    for root, include_internal, imported in (
        (curated_knowledge_root(settings), False, False),
        (imported_knowledge_root(settings), True, True),
    ):
        for path in iter_knowledge_files(root, include_internal=include_internal):
            relative_path = str(path.relative_to(project_root))
            body = path.read_text(encoding="utf-8")
            title = knowledge_heading(path, root)
            current_section = title
            lines = body.splitlines()
            index = 0
            while index < len(lines):
                stripped = lines[index].strip()
                if stripped.startswith("#"):
                    current_section = stripped.lstrip("#").strip() or current_section
                    index += 1
                    continue
                if not stripped.startswith("|"):
                    index += 1
                    continue

                table_lines: list[str] = []
                while index < len(lines):
                    current = lines[index].strip()
                    if current.startswith("|"):
                        table_lines.append(current)
                        index += 1
                        continue
                    if not current and index + 1 < len(lines) and lines[index + 1].strip().startswith("|"):
                        index += 1
                        continue
                    break
                if len(table_lines) < 2:
                    continue

                headers = _markdown_table_cells(table_lines[0])
                separator = _markdown_table_cells(table_lines[1])
                if not _is_markdown_table_separator(separator):
                    continue

                rows = [_markdown_table_cells(line) for line in table_lines[2:]]
                headers, rows = _trim_empty_table_columns(headers, rows)
                if rows and _looks_like_duplicate_table_header(rows[0], headers):
                    rows = rows[1:]
                if not headers or not rows:
                    continue

                tables.append(
                    {
                        "relative_path": relative_path,
                        "source": "knowledge_imports" if imported else "knowledge_base",
                        "imported": imported,
                        "title": title,
                        "section_title": current_section,
                        "headers": headers,
                        "rows": rows,
                    }
                )
    return tables


def _table_text(table: dict[str, Any]) -> str:
    row_text = " ".join(" ".join(row) for row in table["rows"][:8])
    return " ".join(
        [
            str(table["title"]),
            str(table["section_title"]),
            " ".join(str(header) for header in table["headers"]),
            row_text,
        ]
    ).strip()


def _term_hit_count(text: str, variants: dict[str, list[str]]) -> int:
    normalized = _normalize_search_text(text)
    hits = 0
    for options in variants.values():
        if any(option and option in normalized for option in options):
            hits += 1
    return hits


def search_local_knowledge_tables(
    settings: Settings,
    query: str,
    *,
    limit: int = 5,
    source_filter: str | None = None,
    group_filters: list[str] | None = None,
) -> list[dict[str, Any]]:
    normalized_query = query.strip()
    if not normalized_query:
        return []

    query_terms = knowledge_query_terms(normalized_query)
    if not query_terms:
        return []
    term_variants = _query_term_variant_map(query_terms)
    numeric_terms = [term for term in query_terms if any(char.isdigit() for char in term)]

    matches: list[dict[str, Any]] = []
    for table in _iter_knowledge_tables(settings):
        if source_filter is not None and table["source"] != source_filter:
            continue
        if group_filters and not table["imported"]:
            relative = Path(table["relative_path"])
            group_name = relative.parts[2] if len(relative.parts) > 2 else relative.parts[1] if len(relative.parts) > 1 else "root"
            if group_name not in group_filters:
                continue

        title_text = str(table["title"])
        section_text = str(table["section_title"])
        header_text = " ".join(table["headers"])
        row_text = " ".join(" ".join(row) for row in table["rows"][:6])
        full_row_text = " ".join(" ".join(row) for row in table["rows"])
        searchable = " ".join([title_text, section_text, header_text, row_text]).strip()
        header_scope = _normalize_search_text(" ".join([title_text, section_text, header_text]))
        score = float(_term_hit_count(title_text, term_variants) * 4)
        score += float(_term_hit_count(section_text, term_variants) * 7)
        score += float(_term_hit_count(header_text, term_variants) * 6)
        score += float(_term_hit_count(row_text, term_variants) * 1)
        if table["imported"]:
            score += 3.0
        if numeric_terms:
            normalized_searchable = _normalize_search_text(" ".join([title_text, section_text, header_text, full_row_text]))
            numeric_hits = 0
            for term in numeric_terms:
                if any(variant in normalized_searchable for variant in term_variants.get(term, [])):
                    numeric_hits += 1
            score += numeric_hits * 10.0
        lowered_query = normalized_query.lower()
        if any(term.startswith("boon") for term in query_terms) and "per boon" in header_scope:
            score += 10.0
        if any(term in {"weapon", "gun"} for term in query_terms) and any(
            hint in header_scope for hint in ("bullet damage", "weapon damage", "bullet")
        ):
            score += 8.0
        if "investment" in query_terms and "souls" in header_scope:
            score += 6.0
        if "update history" in _normalize_search_text(f"{title_text} {section_text}") and not any(
            hint in lowered_query for hint in ("update", "patch", "history", "change", "changed")
        ):
            score -= 25.0
        if [header.casefold() for header in table["headers"][:2]] == ["update", "changes"] and not any(
            hint in lowered_query for hint in ("update", "patch", "history", "change", "changed")
        ):
            score -= 20.0
        if score <= 0:
            continue

        matches.append(
            {
                **table,
                "score": score,
            }
        )

    matches.sort(key=lambda item: (-float(item["score"]), bool(item["imported"]), str(item["relative_path"]), str(item["section_title"])))
    return matches[: max(1, limit)]


def _best_table_value_column(headers: list[str], rows: list[list[str]], query_terms: list[str], term_variants: dict[str, list[str]]) -> int | None:
    best_index: int | None = None
    best_score = 0
    entity_headers = {"hero", "item", "name", "souls", "soul", "level", "row"}
    for index, header in enumerate(headers):
        header_normalized = _normalize_search_text(header)
        score = 0
        for term in query_terms:
            for variant in term_variants.get(term, []):
                if variant and variant in header_normalized:
                    score += 2
        if index > 0 and score > 0:
            score += 1
        if header_normalized in entity_headers:
            score -= 2
        non_empty_values = sum(1 for row in rows if index < len(row) and str(row[index]).strip())
        if non_empty_values == 0:
            score -= 4
        elif non_empty_values < max(1, len(rows) // 4):
            score -= 2
        if score > best_score:
            best_score = score
            best_index = index
    if best_index is not None:
        return best_index
    return 1 if len(headers) > 1 else None


def _row_best_numeric_value(row: list[str], index: int) -> float | None:
    if index >= len(row):
        return None
    matches = re.findall(r"-?\d+(?:\.\d+)?", row[index].replace(",", ""))
    if not matches:
        return None
    return float(matches[-1])


def query_local_knowledge_tables(
    settings: Settings,
    query: str,
    *,
    limit: int = 3,
    source_filter: str | None = "knowledge_imports",
    group_filters: list[str] | None = None,
) -> dict[str, Any] | None:
    normalized_query = query.strip()
    if not normalized_query:
        return None

    query_terms = knowledge_query_terms(normalized_query)
    if not query_terms:
        return None
    term_variants = _query_term_variant_map(query_terms)
    table_matches = search_local_knowledge_tables(
        settings,
        normalized_query,
        limit=max(1, limit),
        source_filter=source_filter,
        group_filters=group_filters,
    )
    if not table_matches:
        return None

    lowered_query = normalized_query.lower()
    numeric_terms = [term for term in query_terms if any(char.isdigit() for char in term)]
    wants_max = any(phrase in lowered_query for phrase in ("best", "highest", "most"))
    wants_min = any(phrase in lowered_query for phrase in ("lowest", "least", "worst"))
    best = table_matches[0]
    headers = list(best["headers"])
    rows = list(best["rows"])
    if not headers or not rows:
        return None

    value_index = _best_table_value_column(headers, rows, query_terms, term_variants)
    if value_index is None:
        return None
    label_index = 0

    fact: str | None = None
    selected_rows: list[list[str]] = []
    if numeric_terms:
        normalized_rows = [
            [cell, _normalize_search_text(cell)]
            for row in rows
            for cell in row
        ]
        del normalized_rows  # clarify intent for mypy-like readers
        matching_rows: list[list[str]] = []
        for row in rows:
            row_text = _normalize_search_text(" ".join(row))
            if all(any(variant in row_text for variant in term_variants.get(term, [])) for term in numeric_terms):
                matching_rows.append(row)
        if matching_rows:
            selected_rows = matching_rows[:2]
            row = matching_rows[0]
            label = row[label_index] if label_index < len(row) else headers[label_index]
            value = row[value_index] if value_index < len(row) else ""
            fact = f"In {best['section_title']}, the {label} row shows {headers[value_index]} {value}."

    if fact is None and (wants_max or wants_min):
        numeric_rows: list[tuple[float, list[str]]] = []
        for row in rows:
            numeric_value = _row_best_numeric_value(row, value_index)
            if numeric_value is None:
                continue
            numeric_rows.append((numeric_value, row))
        if numeric_rows:
            numeric_rows.sort(key=lambda item: item[0], reverse=not wants_min)
            top_value, top_row = numeric_rows[0]
            selected_rows = [row for _value, row in numeric_rows[:3]]
            label = top_row[label_index] if label_index < len(top_row) else headers[label_index]
            value = top_row[value_index] if value_index < len(top_row) else str(top_value)
            direction = "lowest" if wants_min else "highest"
            fact = f"In {best['section_title']}, {label} has the {direction} {headers[value_index]} at {value}."

    if fact is None:
        selected_rows = rows[: min(3, len(rows))]
        preview = " | ".join(headers[: min(4, len(headers))])
        fact = f"The strongest reference table match is {best['section_title']} with columns {preview}."

    return {
        "query": normalized_query,
        "fact": fact,
        "relative_path": best["relative_path"],
        "title": best["title"],
        "section_title": best["section_title"],
        "headers": headers,
        "rows": selected_rows,
        "matches": table_matches,
    }


def retrieve_grounded_knowledge_context(
    settings: Settings,
    query: str,
    *,
    limit: int = 4,
    source_filter: str | None = None,
    group_filters: list[str] | None = None,
    table_limit: int = 2,
) -> dict[str, Any]:
    normalized_query = query.strip()
    if not normalized_query:
        return {
            "query": query,
            "entities": [],
            "fact": None,
            "fact_source": None,
            "matches": [],
            "tables": [],
            "summary": "No query supplied.",
        }

    entities = extract_knowledge_entities(
        settings,
        normalized_query,
        limit=max(1, limit),
        source_filter=source_filter,
        group_filters=group_filters,
    )
    chunk_matches = search_local_knowledge(
        settings,
        normalized_query,
        limit=max(limit * 2, 6),
        source_filter=source_filter,
        group_filters=group_filters,
    )
    entity_matches = _lookup_entity_chunks(
        settings,
        entities,
        source_filter=source_filter,
        group_filters=group_filters,
    )
    table_result = query_local_knowledge_tables(
        settings,
        normalized_query,
        limit=max(1, table_limit),
        source_filter=source_filter if source_filter == "knowledge_imports" else "knowledge_imports",
        group_filters=group_filters,
    )

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for row in [*chunk_matches, *entity_matches]:
        key = (str(row["relative_path"]), str(row["section_title"]))
        existing = merged.get(key)
        if existing is None or float(row["score"]) > float(existing["score"]):
            merged[key] = dict(row)
        elif row.get("entity_match"):
            existing["entity_match"] = True

    if table_result is not None:
        fact_path = str(table_result["relative_path"])
        fact_section = str(table_result["section_title"])
        key = (fact_path, fact_section)
        if key in merged:
            merged[key]["score"] = float(merged[key]["score"]) + 12.0
        else:
            merged[key] = {
                "relative_path": fact_path,
                "title": str(table_result["title"]),
                "section_title": fact_section,
                "score": 40.0,
                "excerpt": str(table_result["fact"]),
                "source": "knowledge_imports",
                "imported": True,
                "entity_match": False,
            }

    ranked_matches = sorted(
        merged.values(),
        key=lambda item: (
            -float(item["score"]),
            item.get("source") != "knowledge_base",
            str(item["relative_path"]),
            str(item["section_title"]),
        ),
    )[: max(1, limit)]

    fact_source = None
    tables: list[dict[str, Any]] = []
    if table_result is not None:
        fact_source = {
            "relative_path": str(table_result["relative_path"]),
            "title": str(table_result["title"]),
            "section_title": str(table_result["section_title"]),
            "source": "knowledge_imports",
        }
        for table in list(table_result.get("matches", []))[: max(1, table_limit)]:
            tables.append(
                {
                    "relative_path": str(table["relative_path"]),
                    "title": str(table["title"]),
                    "section_title": str(table["section_title"]),
                    "source": str(table["source"]),
                    "score": float(table["score"]),
                    "headers": list(table["headers"]),
                    "rows": list(table["rows"][:2]),
                }
            )

    summary_parts: list[str] = []
    if table_result is not None and table_result.get("fact"):
        summary_parts.append("table fact found")
    if entities:
        summary_parts.append(f"{len(entities)} entity match{'es' if len(entities) != 1 else ''}")
    if ranked_matches:
        summary_parts.append(f"{len(ranked_matches)} chunk hit{'s' if len(ranked_matches) != 1 else ''}")
    summary = ", ".join(summary_parts) if summary_parts else "No grounded knowledge match found."

    return {
        "query": normalized_query,
        "entities": entities,
        "fact": None if table_result is None else table_result.get("fact"),
        "fact_source": fact_source,
        "matches": ranked_matches,
        "tables": tables,
        "summary": summary,
    }


def _normalize_title(title: str, alias_map: dict[str, str]) -> str:
    raw = title.strip()
    if not raw:
        return raw
    return alias_map.get(raw.casefold(), raw)


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


def _wiki_api_request(settings: Settings, params: dict[str, Any], *, cache_key: str, max_age_s: int) -> dict[str, Any]:
    cache_path = wiki_cache_root(settings) / f"{cache_key}.json"
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
    with urlopen(request, timeout=20) as response:  # noqa: S310
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

    title = str(page.get("title") or requested_title)
    return {
        "title": title,
        "pageid": page.get("pageid"),
        "extract": str(page.get("extract") or "").strip(),
        "url": f"https://deadlock.wiki/{title.replace(' ', '_')}",
    }


def _page_parse_from_payload(payload: dict[str, Any], *, requested_title: str) -> dict[str, Any] | None:
    parse = (payload or {}).get("parse") or {}
    if not isinstance(parse, dict):
        return None
    title = str(parse.get("title") or requested_title).strip() or requested_title
    html = str(((parse.get("text") or {}).get("*")) or "").strip()
    if not html:
        return None
    markdown = _wiki_html_to_markdown(html)
    if not markdown:
        return None
    return {
        "title": title,
        "pageid": parse.get("pageid"),
        "extract": markdown,
        "url": f"https://deadlock.wiki/{title.replace(' ', '_')}",
    }


def wiki_page_extract(settings: Settings, title: str) -> dict[str, Any] | None:
    normalized_title = title.strip()
    if not normalized_title:
        return None

    payload = _wiki_api_request(
        settings,
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


def wiki_page_parse(settings: Settings, title: str) -> dict[str, Any] | None:
    normalized_title = title.strip()
    if not normalized_title:
        return None

    payload = _wiki_api_request(
        settings,
        {
            "action": "parse",
            "page": normalized_title,
            "prop": "text",
        },
        cache_key=f"parse-{_slugify(normalized_title)}",
        max_age_s=WIKI_PAGE_EXTRACT_MAX_AGE_S,
    )
    return _page_parse_from_payload(payload, requested_title=normalized_title)


def _should_keep_category_title(row: dict[str, Any], title: str) -> bool:
    return bool(
        title
        and row.get("ns", 0) == 0
        and "/" not in title
        and title not in {"Heroes", "Items"}
    )


def _should_keep_allpages_title(row: dict[str, Any], title: str) -> bool:
    return bool(title and row.get("ns", PAGE_NAMESPACE) == PAGE_NAMESPACE)


def wiki_category_members(settings: Settings, category_title: str, limit: int | None = 200) -> list[str]:
    requested_limit = None if limit is None else max(1, limit)
    page_size = 200
    continue_token: dict[str, Any] = {}
    titles: list[str] = []
    seen: set[str] = set()

    while True:
        batch_limit = page_size if requested_limit is None else min(page_size, requested_limit - len(titles))
        if batch_limit <= 0:
            break

        payload = _wiki_api_request(
            settings,
            {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": category_title,
                "cmlimit": batch_limit,
                **continue_token,
            },
            cache_key=(
                f"category-{_slugify(category_title)}-"
                f"{'all' if requested_limit is None else requested_limit}-"
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
            if requested_limit is not None and len(titles) >= requested_limit:
                return titles

        next_continue = (payload or {}).get("continue") or {}
        if not next_continue:
            break
        continue_token = next_continue

    return titles


def wiki_all_pages(settings: Settings, limit: int | None = 500) -> list[str]:
    requested_limit = None if limit is None else max(1, limit)
    page_size = 500
    continue_token: dict[str, Any] = {}
    titles: list[str] = []
    seen: set[str] = set()

    while True:
        batch_limit = page_size if requested_limit is None else min(page_size, requested_limit - len(titles))
        if batch_limit <= 0:
            break

        payload = _wiki_api_request(
            settings,
            {
                "action": "query",
                "list": "allpages",
                "apnamespace": PAGE_NAMESPACE,
                "aplimit": batch_limit,
                **continue_token,
            },
            cache_key=(
                f"allpages-{PAGE_NAMESPACE}-"
                f"{'all' if requested_limit is None else requested_limit}-"
                f"{_slugify(json.dumps(continue_token, sort_keys=True)) or 'start'}"
            ),
            max_age_s=WIKI_CATEGORY_MAX_AGE_S,
        )
        rows = ((payload or {}).get("query") or {}).get("allpages") or []
        for row in rows:
            title = str(row.get("title") or "")
            if not _should_keep_allpages_title(row, title) or title in seen:
                continue
            seen.add(title)
            titles.append(title)
            if requested_limit is not None and len(titles) >= requested_limit:
                return titles

        next_continue = (payload or {}).get("continue") or {}
        if not next_continue:
            break
        continue_token = next_continue

    return titles


def _kind_metadata(kind: str) -> tuple[str, str | None, dict[str, str]]:
    normalized = kind.strip().lower()
    if normalized == "heroes":
        return ("heroes", HERO_CATEGORY_TITLE, HERO_TITLE_ALIASES)
    if normalized == "items":
        return ("items", ITEM_CATEGORY_TITLE, ITEM_TITLE_ALIASES)
    if normalized == "pages":
        return ("pages", None, {})
    supported = ", ".join(f"`{name}`" for name in REFERENCE_KINDS)
    raise ValueError(f"Supported knowledge import kinds are {supported}.")


def _render_import_markdown(kind: str, page: dict[str, Any]) -> str:
    imported_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return (
        f"# {page['title']}\n\n"
        f"Imported reference\n\n"
        f"- kind: {kind}\n"
        f"- source: Deadlock Wiki\n"
        f"- url: {page['url']}\n"
        f"- imported_at: {imported_at}\n\n"
        "Reference extract:\n\n"
        f"{page['extract']}\n"
    )


def _write_import_file(settings: Settings, kind: str, page: dict[str, Any], *, filename: str | None = None) -> Path:
    target_dir = imported_knowledge_root(settings) / kind
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / (filename or f"{_slugify(page['title'])}.md")
    target_path.write_text(_render_import_markdown(kind, page), encoding="utf-8")
    return target_path


def _write_manifest(settings: Settings, kind: str, imported: list[dict[str, Any]]) -> Path:
    target_dir = imported_knowledge_root(settings)
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = target_dir / f"{kind}-manifest.json"
    manifest_path.write_text(json.dumps(imported, ensure_ascii=True, indent=2), encoding="utf-8")
    return manifest_path


def sync_wiki_reference_files(
    settings: Settings,
    *,
    kind: str,
    titles: Iterable[str] | None = None,
    limit: int | None = 24,
) -> dict[str, Any]:
    normalized_kind, category_title, alias_map = _kind_metadata(kind)

    requested_titles = [title for title in (titles or []) if str(title).strip()]
    if requested_titles:
        normalized_titles = [_normalize_title(str(title), alias_map) for title in requested_titles]
    elif normalized_kind == "pages":
        normalized_titles = wiki_all_pages(settings, limit=limit)
    else:
        assert category_title is not None
        normalized_titles = wiki_category_members(settings, category_title, limit=limit)

    imported: list[dict[str, Any]] = []
    seen_output_paths: set[str] = set()
    for title in normalized_titles:
        page = wiki_page_parse(settings, title) if normalized_kind == "pages" else wiki_page_extract(settings, title)
        if page is None and normalized_kind == "pages":
            page = wiki_page_extract(settings, title)
        if page is None:
            imported.append({"title": title, "imported": False, "reason": "missing_page"})
            continue

        filename = None
        if normalized_kind == "pages":
            page_id = page.get("pageid")
            prefix = f"{page_id}-" if page_id is not None else ""
            filename = f"{prefix}{_slugify(page['title'])}.md"
            if filename in seen_output_paths:
                imported.append(
                    {
                        "title": page["title"],
                        "imported": False,
                        "reason": "duplicate_resolved_page",
                        "url": page["url"],
                    }
                )
                continue
            seen_output_paths.add(filename)
        output_path = _write_import_file(settings, normalized_kind, page, filename=filename)
        imported.append(
            {
                "title": page["title"],
                "imported": True,
                "path": str(output_path.relative_to(settings.project_root)),
                "url": page["url"],
            }
        )

    manifest_path = _write_manifest(settings, normalized_kind, imported)
    return {
        "kind": normalized_kind,
        "requested_count": len(normalized_titles),
        "imported_count": sum(1 for row in imported if row["imported"]),
        "manifest_path": str(manifest_path.relative_to(settings.project_root)),
        "pages": imported,
    }


def sync_reference_corpus(settings: Settings, *, include_pages: bool = False, page_limit: int | None = None) -> dict[str, Any]:
    hero_result = sync_wiki_reference_files(settings, kind="heroes", limit=None)
    item_result = sync_wiki_reference_files(settings, kind="items", limit=None)
    page_result = sync_wiki_reference_files(settings, kind="pages", limit=page_limit) if include_pages else None
    kinds: dict[str, dict[str, Any]] = {
        "heroes": {
            "imported_count": hero_result["imported_count"],
            "requested_count": hero_result["requested_count"],
            "manifest_path": hero_result["manifest_path"],
        },
        "items": {
            "imported_count": item_result["imported_count"],
            "requested_count": item_result["requested_count"],
            "manifest_path": item_result["manifest_path"],
        },
    }
    if page_result is not None:
        kinds["pages"] = {
            "imported_count": page_result["imported_count"],
            "requested_count": page_result["requested_count"],
            "manifest_path": page_result["manifest_path"],
        }
    return {
        "kinds": kinds,
        "imported_count": hero_result["imported_count"] + item_result["imported_count"] + (page_result["imported_count"] if page_result is not None else 0),
        "requested_count": hero_result["requested_count"] + item_result["requested_count"] + (page_result["requested_count"] if page_result is not None else 0),
    }
