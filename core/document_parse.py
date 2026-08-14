from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DOCUMENT_PARSE_TOOL_NAME = "parse_document"
DOCUMENT_PARSE_MISSING_FILE_MESSAGE = "当前消息或引用消息中没有可解析的文件。"
DOCUMENT_PARSE_DISABLED_MESSAGE = "文档解析工具已关闭。"
DOCUMENT_PARSE_PATH_DISABLED_MESSAGE = "文档解析工具未允许读取显式本地路径。"
DOCUMENT_PARSE_MARKITDOWN_MISSING_MESSAGE = (
    "MarkItDown 未安装，且当前文件类型没有可用兜底解析器。"
)
DOCUMENT_PARSE_UNKNOWN_FILE_MESSAGE = "未找到这个 file_id。请使用当前消息中列出的 file_id。"
DOCUMENT_PARSE_CACHE_TTL_SECONDS = 30 * 60


@dataclass(frozen=True)
class DocumentParseConfig:
    enabled: bool = False
    max_output_chars: int = 12000
    max_file_mb: int = 30


@dataclass(frozen=True)
class DocumentCandidate:
    name: str
    path: Path


@dataclass
class DocumentRegistryEntry:
    file_id: str
    name: str
    source_path: Path
    markdown_path: Path
    last_accessed_at: float


@dataclass(frozen=True)
class ParsedDocument:
    name: str
    path: Path
    content: str
    truncated: bool = False


def build_document_parse_config(section_config: dict[str, Any]) -> DocumentParseConfig:
    return DocumentParseConfig(
        enabled=bool(section_config.get("enable_document_parse_tool", False)),
        max_output_chars=_bounded_int(
            section_config.get("max_output_chars"),
            default=12000,
            minimum=1000,
            maximum=60000,
        ),
        max_file_mb=_bounded_int(
            section_config.get("max_file_mb"),
            default=30,
            minimum=1,
            maximum=200,
        ),
    )


class DocumentParseRegistry:
    def __init__(
        self,
        cache_dir: Path,
        *,
        ttl_seconds: int = DOCUMENT_PARSE_CACHE_TTL_SECONDS,
    ) -> None:
        self.cache_dir = cache_dir.resolve()
        self.ttl_seconds = ttl_seconds
        self.entries: dict[str, DocumentRegistryEntry] = {}

    async def register_event_files(
        self,
        event: Any,
        *,
        config: DocumentParseConfig,
    ) -> list[DocumentRegistryEntry]:
        self.cleanup_expired()
        candidates = await collect_document_candidates(event)
        entries = []
        for candidate in candidates:
            entry = self.register_candidate(candidate)
            self.ensure_markdown(entry, config=config)
            entries.append(entry)
        return entries

    def register_candidate(self, candidate: DocumentCandidate) -> DocumentRegistryEntry:
        file_id = build_document_file_id(candidate)
        markdown_path = self.cache_dir / f"{file_id}.md"
        entry = DocumentRegistryEntry(
            file_id=file_id,
            name=candidate.name,
            source_path=candidate.path,
            markdown_path=markdown_path,
            last_accessed_at=time.time(),
        )
        self.entries[file_id] = entry
        return entry

    def read_markdown_lines(
        self,
        file_id: str,
        *,
        start_line: int,
        line_count: int,
        max_output_chars: int,
        config: DocumentParseConfig,
    ) -> str:
        self.cleanup_expired()
        entry = self.entries.get(str(file_id or "").strip())
        if entry is None:
            return DOCUMENT_PARSE_UNKNOWN_FILE_MESSAGE

        entry.last_accessed_at = time.time()
        self.ensure_markdown(entry, config=config)
        lines = entry.markdown_path.read_text(encoding="utf-8", errors="replace").splitlines()
        total_lines = len(lines)
        start_line = max(1, int(start_line or 1))
        line_count = max(1, min(500, int(line_count or 120)))

        if start_line > total_lines:
            return (
                f"文件：{entry.name}\n"
                f"file_id：{entry.file_id}\n"
                f"总行数：{total_lines}\n\n"
                "请求的 start_line 超出文件范围。"
            )

        end_line = min(total_lines, start_line + line_count - 1)
        selected = lines[start_line - 1 : end_line]
        body = "\n".join(
            f"{line_number}: {line}"
            for line_number, line in enumerate(selected, start=start_line)
        )
        truncated_by_chars = False
        if len(body) > max_output_chars:
            body = body[:max_output_chars].rstrip()
            truncated_by_chars = True

        notes = []
        if end_line < total_lines:
            notes.append(f"继续读取请调用 start_line={end_line + 1}。")
        if truncated_by_chars:
            notes.append("本次内容因 max_output_chars 被截断，请减少 line_count 后重试。")

        note_text = "\n".join(notes)
        return "\n".join(
            part
            for part in [
                f"文件：{entry.name}",
                f"file_id：{entry.file_id}",
                f"行范围：{start_line}-{end_line}/{total_lines}",
                "",
                body or "[未提取到可读文本]",
                "",
                note_text,
            ]
            if part != ""
        )

    def ensure_markdown(
        self,
        entry: DocumentRegistryEntry,
        *,
        config: DocumentParseConfig,
    ) -> Path:
        if entry.markdown_path.is_file():
            markdown_mtime = entry.markdown_path.stat().st_mtime
            source_mtime = entry.source_path.stat().st_mtime
            if markdown_mtime >= source_mtime:
                return entry.markdown_path

        parsed = parse_local_document(
            entry.source_path,
            name=entry.name,
            max_output_chars=10**9,
            max_file_mb=config.max_file_mb,
        )
        entry.markdown_path.parent.mkdir(parents=True, exist_ok=True)
        entry.markdown_path.write_text(parsed.content, encoding="utf-8")
        return entry.markdown_path

    def cleanup_expired(self, *, now: float | None = None) -> None:
        now = now or time.time()
        expired_ids = [
            file_id
            for file_id, entry in self.entries.items()
            if now - entry.last_accessed_at > self.ttl_seconds
        ]
        for file_id in expired_ids:
            entry = self.entries.pop(file_id, None)
            if entry is None:
                continue
            try:
                if entry.markdown_path.is_file():
                    entry.markdown_path.unlink()
            except OSError:
                pass


def build_document_file_id(candidate: DocumentCandidate) -> str:
    stat = candidate.path.stat()
    payload = "|".join(
        [
            candidate.name,
            str(candidate.path),
            str(stat.st_size),
            str(stat.st_mtime_ns),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"file_{digest}"


def format_available_files(entries: list[DocumentRegistryEntry]) -> str:
    if not entries:
        return ""
    lines = [
        "<available_files>",
        "The current or quoted message contains readable files. Use parse_document(file_id, start_line, line_count) to read the converted Markdown content.",
    ]
    for entry in entries:
        lines.append(
            f'- file_id="{entry.file_id}" name="{entry.name}"'
        )
    lines.append("</available_files>")
    return "\n".join(lines)


async def collect_document_candidates(event: Any) -> list[DocumentCandidate]:
    candidates: list[DocumentCandidate] = []
    seen: set[Path] = set()
    for component in _iter_message_components(event):
        if not _is_file_component(component):
            continue
        path_text = await _get_component_file_path(component)
        if not path_text:
            continue
        path = Path(path_text).expanduser().resolve()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        candidates.append(
            DocumentCandidate(
                name=str(getattr(component, "name", "") or path.name),
                path=path,
            )
        )
    return candidates


def parse_local_document(
    path: Path | str,
    *,
    name: str = "",
    max_output_chars: int = 12000,
    max_file_mb: int = 30,
) -> ParsedDocument:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"文件不存在：{resolved}")

    size_limit = max_file_mb * 1024 * 1024
    file_size = resolved.stat().st_size
    if file_size > size_limit:
        raise ValueError(f"文件过大：{file_size} bytes，限制 {max_file_mb} MB。")

    content = _convert_with_markitdown(resolved)
    if content is None:
        content = _convert_with_fallback(resolved)
    if content is None:
        raise RuntimeError(DOCUMENT_PARSE_MARKITDOWN_MISSING_MESSAGE)

    content = _normalize_content(content)
    truncated = False
    if len(content) > max_output_chars:
        content = content[:max_output_chars].rstrip()
        truncated = True

    return ParsedDocument(
        name=name or resolved.name,
        path=resolved,
        content=content,
        truncated=truncated,
    )


def format_parsed_document(document: ParsedDocument) -> str:
    suffix = "\n\n[内容已截断，请按需继续读取或让用户缩小范围。]" if document.truncated else ""
    return "\n".join(
        [
            f"文件：{document.name}",
            f"路径：{document.path}",
            "",
            document.content or "[未提取到可读文本]",
            suffix,
        ]
    ).rstrip()


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _iter_message_components(event: Any):
    message_obj = getattr(event, "message_obj", None)
    roots = [
        getattr(message_obj, "message", None),
        getattr(message_obj, "chain", None),
        getattr(event, "message", None),
        getattr(event, "message_chain", None),
    ]
    for root in roots:
        yield from _walk_components(root, seen=set())


def _walk_components(value: Any, *, seen: set[int]):
    if value is None:
        return
    value_id = id(value)
    if value_id in seen:
        return
    seen.add(value_id)

    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _walk_components(item, seen=seen)
        return

    yield value
    for attr in ("chain", "content", "nodes"):
        child = getattr(value, attr, None)
        if child is not None:
            yield from _walk_components(child, seen=seen)


def _is_file_component(component: Any) -> bool:
    component_type = str(getattr(component, "type", "") or "").lower()
    return component_type.endswith("file") or hasattr(component, "get_file")


async def _get_component_file_path(component: Any) -> str:
    get_file = getattr(component, "get_file", None)
    if callable(get_file):
        try:
            return str(await get_file())
        except TypeError:
            return str(await get_file(False))

    for attr in ("file", "file_", "path"):
        value = getattr(component, attr, "")
        if value:
            return _path_from_value(str(value))
    return ""


def _path_from_value(value: str) -> str:
    if value.startswith("file://"):
        parsed = urlparse(value)
        return parsed.path.lstrip("/") if parsed.netloc else parsed.path
    return value


def _convert_with_markitdown(path: Path) -> str | None:
    try:
        from markitdown import MarkItDown
    except Exception:
        return None

    converter = MarkItDown()
    if hasattr(converter, "convert_local"):
        result = converter.convert_local(str(path))
    else:
        result = converter.convert(str(path))
    return str(getattr(result, "text_content", "") or result or "")


def _convert_with_fallback(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf_text(path)
    if suffix in {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".xml", ".html", ".htm"}:
        return path.read_text(encoding="utf-8", errors="replace")
    return None


def _extract_pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(f"## Page {page_number}\n\n{text}".strip())
    return "\n\n".join(pages)


def _normalize_content(content: str) -> str:
    return str(content or "").replace("\r\n", "\n").replace("\r", "\n").strip()
