from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ROLEPLAY_KNOWLEDGE_ROOT = Path("cs") / "output"
ROLEPLAY_KNOWLEDGE_TOOL_NAME = "search_roleplay_knowledge"


@dataclass(frozen=True)
class RoleplayKnowledgeConfig:
    enabled: bool = False
    max_results: int = 4
    max_chars_per_result: int = 900


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
    section = config.get("roleplay_knowledge", {})
    if not isinstance(section, Mapping):
        section = {}
    return RoleplayKnowledgeConfig(
        enabled=bool(section.get("enable_roleplay_knowledge_tool", False)),
        max_results=max(1, min(10, int(section.get("max_results", 4) or 4))),
        max_chars_per_result=max(
            200,
            min(4000, int(section.get("max_chars_per_result", 900) or 900)),
        ),
    )


class RoleplayKnowledgeBase:
    def __init__(self, documents: list[RoleplayKnowledgeDocument]):
        self.documents = documents

    @classmethod
    def from_root(cls, root: Path) -> "RoleplayKnowledgeBase":
        root = root.resolve()
        documents: list[RoleplayKnowledgeDocument] = []
        documents.extend(_load_documents(root, "ema", _ema_roots(root)))
        documents.extend(_load_documents(root, "hiro", _hiro_roots(root)))
        return cls(documents)

    def count(self, database: str | None = None) -> int:
        if database is None:
            return len(self.documents)
        return sum(1 for document in self.documents if document.database == database)

    def search(
        self,
        database: str,
        query: str,
        limit: int,
        max_chars_per_result: int,
    ) -> list[RoleplayKnowledgeSearchResult]:
        query = str(query or "").strip()
        if not query:
            return []

        terms = _query_terms(query)
        results: list[RoleplayKnowledgeSearchResult] = []
        for document in self.documents:
            if document.database != database:
                continue
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


def _ema_roots(root: Path) -> tuple[Path, ...]:
    return (
        root / "ema-roleplay",
        root / "艾玛提示词_13份",
        root / "魔女岛背景名词词典.md",
    )


def _hiro_roots(root: Path) -> tuple[Path, ...]:
    return (
        root / "hiro-roleplay",
        root / "希罗提示词_13份",
        root / "魔女岛背景名词词典.md",
    )


def _load_documents(
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
            seen.add(resolved)
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = path.read_text(encoding="utf-8-sig", errors="replace")
            documents.append(
                RoleplayKnowledgeDocument(
                    database=database,
                    title=_document_title(path, content),
                    source=_relative_source(root, path),
                    content=_strip_frontmatter(content).strip(),
                )
            )
    return documents


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


def _query_terms(query: str) -> list[str]:
    normalized = _normalize(query)
    terms = [term for term in re.split(r"\s+", normalized) if term]
    if normalized and normalized not in terms:
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
