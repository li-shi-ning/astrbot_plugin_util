from __future__ import annotations

import re
import sqlite3
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROLEPLAY_KNOWLEDGE_TOOL_NAME = "search_roleplay_knowledge"
ROLEPLAY_KNOWLEDGE_DB_FILENAME = "roleplay_knowledge.sqlite3"
SCHEMA_VERSION = 1
EMA_PROMPT_PREFIX = "\u827e\u739b"
HIRO_PROMPT_PREFIX = "\u5e0c\u7f57"
PUBLIC_BACKGROUND_FILENAME = "\u9b54\u5973\u5c9b\u80cc\u666f\u540d\u8bcd\u8bcd\u5178.md"

CHARACTER_SKILL_REFERENCES = {
    "\u6a31\u7fbd\u827e\u739b": ("Ema", "ema.md"),
    "\u4e8c\u9636\u5802\u5e0c\u7f57": ("Hiro", "hiro.md"),
    "\u7d2b\u85e4\u4e9a\u91cc\u6c99": ("Alisa", "arisa.md"),
    "\u590f\u76ee\u5b89\u5b89": ("AnAn", "anan.md"),
    "\u57ce\u5d0e\u8bfa\u4e9a": ("Noah", "noa.md"),
    "\u83b2\u89c1\u857e\u96c5": ("Leia", "reia.md"),
    "\u4f50\u4f2f\u7c73\u8389\u4e9a": ("Miria", "miria.md"),
    "\u5b9d\u751f\u739b\u683c": ("Margo", "maago.md"),
    "\u9ed1\u90e8\u5948\u53f6\u9999": ("Nanoka", "nanoka.md"),
    "\u6a58\u96ea\u8389": ("Sherry", "sherii.md"),
    "\u8fdc\u91ce\u6c49\u5a1c": ("Hanna", "hanna.md"),
    "\u6cfd\u6e21\u53ef\u53ef": ("Coco", "koko.md"),
    "\u51b0\u4e0a\u6885\u9732\u9732": ("Meruru", "meruru.md"),
}


@dataclass(frozen=True)
class RoleplayKnowledgeConfig:
    enabled: bool = False
    max_results: int = 4
    max_chars_per_result: int = 900
    deduplicate_turns: int = 5


@dataclass(frozen=True)
class RoleplayKnowledgeDocument:
    database: str
    title: str
    source: str
    content: str


@dataclass(frozen=True)
class RoleplayKnowledgeSearchResult:
    document: RoleplayKnowledgeDocument
    score: int
    snippet: str


def load_roleplay_knowledge_config(config: Mapping[str, Any]) -> RoleplayKnowledgeConfig:
    section: Mapping[str, Any] = config
    if "enable_roleplay_knowledge_tool" not in section:
        nested_section = section.get("roleplay_knowledge", {})
        section = nested_section if isinstance(nested_section, Mapping) else {}
    if not isinstance(section, Mapping):
        section = {}
    return RoleplayKnowledgeConfig(
        enabled=bool(section.get("enable_roleplay_knowledge_tool", False)),
        max_results=max(1, min(10, int(section.get("max_results", 4) or 4))),
        max_chars_per_result=max(
            200,
            min(4000, int(section.get("max_chars_per_result", 900) or 900)),
        ),
        deduplicate_turns=max(
            0,
            min(50, int(section.get("deduplicate_turns", 5) or 0)),
        ),
    )


class RoleplayKnowledgeBase:
    def __init__(self, db_path: Path, base_dir: Path | None = None):
        self.db_path = Path(db_path)
        if str(self.db_path) != ":memory:":
            if not self.db_path.is_absolute() and base_dir is not None:
                self.db_path = Path(base_dir) / self.db_path
            self.db_path = self.db_path.resolve()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @classmethod
    def from_root(
        cls,
        root: Path,
        db_path: Path | None = None,
        base_dir: Path | None = None,
    ) -> "RoleplayKnowledgeBase":
        if db_path is None:
            db_file = tempfile.NamedTemporaryFile(
                prefix="astrbot_roleplay_knowledge_",
                suffix=".sqlite3",
                delete=False,
            )
            db_file.close()
            db_path = Path(db_file.name)
        knowledge_base = cls(db_path, base_dir=base_dir)
        knowledge_base.rebuild_from_root(root)
        return knowledge_base

    def rebuild_from_root(self, root: Path) -> None:
        root = root.resolve()
        documents = _load_documents(root)
        with self._connect() as connection:
            connection.execute("DELETE FROM documents")
            connection.executemany(
                """
                INSERT INTO documents(database, title, source, content)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        document.database,
                        document.title,
                        document.source,
                        document.content,
                    )
                    for document in documents
                ],
            )
            connection.execute(
                """
                INSERT INTO metadata(key, value)
                VALUES ('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(SCHEMA_VERSION),),
            )
            connection.execute(
                """
                INSERT INTO metadata(key, value)
                VALUES ('source_root', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(root),),
            )

    def count(self, database: str | None = None) -> int:
        with self._connect() as connection:
            if database is None:
                row = connection.execute("SELECT COUNT(*) FROM documents").fetchone()
            else:
                row = connection.execute(
                    "SELECT COUNT(*) FROM documents WHERE database = ?",
                    (database,),
                ).fetchone()
        return int(row[0]) if row else 0

    def search(
        self,
        database: str,
        query: str,
        limit: int,
        max_chars_per_result: int,
        exclude_sources: set[str] | None = None,
    ) -> list[RoleplayKnowledgeSearchResult]:
        query = str(query or "").strip()
        if not query:
            return []

        terms = _query_terms(query)
        sql, parameters = _search_sql(database, terms)
        results: list[RoleplayKnowledgeSearchResult] = []
        with self._connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()

        for row in rows:
            source = str(row["source"])
            if exclude_sources and source in exclude_sources:
                continue
            document = RoleplayKnowledgeDocument(
                database=str(row["database"]),
                title=str(row["title"]),
                source=source,
                content=str(row["content"]),
            )
            score = _score_document(document, terms)
            if score <= 0:
                continue
            results.append(
                RoleplayKnowledgeSearchResult(
                    document=document,
                    score=score,
                    snippet=_build_snippet(document.content, terms, max_chars_per_result),
                )
            )

        results.sort(
            key=lambda item: (
                item.score,
                -len(item.document.source),
                item.document.title,
            ),
            reverse=True,
        )
        return results[: max(1, limit)]

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    database TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL,
                    content TEXT NOT NULL,
                    UNIQUE(database, source)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_roleplay_documents_database
                ON documents(database)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path))
        connection.row_factory = sqlite3.Row
        return connection


def select_roleplay_database(platform_id: str | None) -> str:
    return "ema" if str(platform_id or "").lower() == "ni" else "hiro"


def format_roleplay_search_results(
    database: str,
    query: str,
    results: list[RoleplayKnowledgeSearchResult],
) -> str:
    if not results:
        return (
            f"roleplay_database: {database}\n"
            f"query: {query}\n"
            "No matching roleplay knowledge was found."
        )

    lines = [
        f"roleplay_database: {database}",
        f"query: {query}",
        f"matches: {len(results)}",
        "",
    ]
    for index, result in enumerate(results, start=1):
        lines.extend(
            [
                f"[{index}] {result.document.title}",
                f"source: {result.document.source}",
                f"score: {result.score}",
                result.snippet,
                "",
            ]
        )
    return "\n".join(lines).strip()


def _load_documents(root: Path) -> list[RoleplayKnowledgeDocument]:
    documents: list[RoleplayKnowledgeDocument] = []
    documents.extend(_load_documents_for_database(root, "ema", _ema_roots(root)))
    documents.extend(_load_documents_for_database(root, "hiro", _hiro_roots(root)))
    return documents


def _ema_roots(root: Path) -> tuple[Path, ...]:
    return _matching_roots(root, directory_prefix=EMA_PROMPT_PREFIX, include_common=True)


def _hiro_roots(root: Path) -> tuple[Path, ...]:
    return _matching_roots(root, directory_prefix=HIRO_PROMPT_PREFIX, include_common=True)


def _matching_roots(
    root: Path,
    directory_prefix: str,
    include_common: bool,
) -> tuple[Path, ...]:
    paths: list[Path] = []
    if not root.exists():
        return ()
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        if path.is_dir() and path.name.startswith(directory_prefix):
            paths.append(path)
        elif include_common and path.is_file() and path.suffix.lower() == ".md":
            paths.append(path)
    return tuple(paths)


def _load_documents_for_database(
    root: Path,
    database: str,
    include_roots: tuple[Path, ...],
) -> list[RoleplayKnowledgeDocument]:
    documents: list[RoleplayKnowledgeDocument] = []
    seen: set[Path] = set()
    for include_root in include_roots:
        if not include_root.exists():
            continue
        paths = [include_root] if include_root.is_file() else sorted(include_root.rglob("*.md"))
        for path in paths:
            resolved = path.resolve()
            if resolved in seen or not resolved.is_file() or path.suffix.lower() != ".md":
                continue
            if include_root.is_dir() and path.name.startswith("01_"):
                continue
            seen.add(resolved)
            content = _read_markdown(path)
            content = _augment_roleplay_prompt_content(root, database, path, content)
            documents.append(
                RoleplayKnowledgeDocument(
                    database=database,
                    title=_document_title(path, content),
                    source=_relative_source(root, path),
                    content=_strip_frontmatter(content).strip(),
                )
            )
    return documents


def _augment_roleplay_prompt_content(
    root: Path,
    database: str,
    path: Path,
    content: str,
) -> str:
    target_name = _target_name_from_prompt_filename(path)
    if not target_name:
        return content

    skill_sections = _skill_sections_for_target(root, database, target_name)
    if not skill_sections:
        return content

    return "\n\n".join(
        [
            content.strip(),
            "## Skill 资料补充",
            *skill_sections,
        ]
    )


def _target_name_from_prompt_filename(path: Path) -> str | None:
    match = re.search(r"\u5bf9(.+?)\u7684\u8ba4\u77e5", path.stem)
    if not match:
        return None
    return match.group(1).strip() or None


def _skill_sections_for_target(root: Path, database: str, target_name: str) -> list[str]:
    reference = CHARACTER_SKILL_REFERENCES.get(target_name)
    if reference is None:
        return []

    section_name, hiro_character_file = reference
    roleplay_dir = root / ("ema-roleplay" if database == "ema" else "hiro-roleplay")
    sections: list[str] = []
    if database == "ema":
        sections.extend(
            _markdown_named_section(roleplay_dir / "SKILL.md", section_name, level=3)
        )
    else:
        character_path = roleplay_dir / "references" / "characters" / hiro_character_file
        if character_path.exists():
            sections.append(_strip_frontmatter(_read_markdown(character_path)).strip())

    sections.extend(
        _markdown_named_section(
            roleplay_dir / "references" / "cast-style-notes.md",
            section_name,
            level=2,
        )
    )
    return [section for section in sections if section.strip()]


def _markdown_named_section(path: Path, section_name: str, level: int) -> list[str]:
    if not path.exists():
        return []
    content = _strip_frontmatter(_read_markdown(path))
    heading_prefix = "#" * level
    next_heading_pattern = re.compile(rf"^#{{1,{level}}}\s+", flags=re.MULTILINE)
    heading_pattern = re.compile(
        rf"^{re.escape(heading_prefix)}\s+{re.escape(section_name)}\s*$",
        flags=re.MULTILINE,
    )
    match = heading_pattern.search(content)
    if not match:
        return []
    next_match = next_heading_pattern.search(content, match.end())
    end = next_match.start() if next_match else len(content)
    return [content[match.start() : end].strip()]


def _read_markdown(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig", errors="replace")


def _document_title(path: Path, content: str) -> str:
    for line in _strip_frontmatter(content).splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or path.stem
    return path.stem


def _relative_source(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _strip_frontmatter(content: str) -> str:
    if not content.startswith("---"):
        return content
    match = re.match(r"\A---\s*\n.*?\n---\s*\n?", content, flags=re.DOTALL)
    if not match:
        return content
    return content[match.end() :]


def _search_sql(database: str, terms: list[str]) -> tuple[str, list[str]]:
    clauses = ["database = ?"]
    parameters = [database]
    term_clauses: list[str] = []
    for term in terms:
        term_clauses.append("(title LIKE ? OR source LIKE ? OR content LIKE ?)")
        like_term = f"%{term}%"
        parameters.extend([like_term, like_term, like_term])
    if term_clauses:
        clauses.append("(" + " OR ".join(term_clauses) + ")")
    return (
        "SELECT database, title, source, content FROM documents WHERE "
        + " AND ".join(clauses),
        parameters,
    )


def _query_terms(query: str) -> list[str]:
    normalized = _normalize(query)
    terms = [term for term in re.split(r"\s+", normalized) if term]
    if normalized and normalized not in terms and not re.search(r"\s", normalized):
        terms.append(normalized)
    if len(terms) == 1 and len(terms[0]) >= 4:
        compact = terms[0]
        terms.extend(
            compact[index : index + 2]
            for index in range(0, len(compact) - 1)
            if not compact[index : index + 2].isspace()
        )
    deduped: list[str] = []
    for term in terms:
        if term and term not in deduped:
            deduped.append(term)
    return deduped


def _score_document(document: RoleplayKnowledgeDocument, terms: list[str]) -> int:
    haystack = _normalize(
        f"{document.title}\n{document.source}\n{document.content}"
    )
    title = _normalize(f"{document.title}\n{document.source}")
    score = 0
    for term in terms:
        if not term:
            continue
        title_hits = title.count(term)
        content_hits = haystack.count(term)
        if content_hits:
            score += 100
        score += title_hits * 20 + content_hits
    return score


def _build_snippet(content: str, terms: list[str], max_chars: int) -> str:
    normalized_content = _normalize(content)
    first_match = -1
    for term in terms:
        index = normalized_content.find(term)
        if index >= 0 and (first_match < 0 or index < first_match):
            first_match = index

    if first_match < 0:
        snippet = content[:max_chars]
    else:
        start = max(first_match - max_chars // 4, 0)
        end = min(start + max_chars, len(content))
        snippet = content[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."

    return _collapse_blank_lines(snippet.strip())


def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text)


def _normalize(text: str) -> str:
    return str(text or "").casefold()
