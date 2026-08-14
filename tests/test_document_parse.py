from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from core.document_parse import (  # noqa: E402
    DOCUMENT_PARSE_DISABLED_MESSAGE,
    DOCUMENT_PARSE_UNKNOWN_FILE_MESSAGE,
    DocumentCandidate,
    DocumentParseConfig,
    DocumentParseRegistry,
    build_document_parse_config,
    build_document_file_id,
    collect_document_candidates,
    format_available_files,
    format_parsed_document,
    parse_local_document,
)
from main import util  # noqa: E402


class FakeFile:
    type = "File"

    def __init__(self, name: str, path: Path):
        self.name = name
        self.path = path

    async def get_file(self):
        return str(self.path)


def make_event_with_file(file_component=None):
    chain = []
    if file_component is not None:
        chain.append(SimpleNamespace(type="Reply", chain=[file_component]))
    return SimpleNamespace(message_obj=SimpleNamespace(message=chain))


def make_plugin(config: DocumentParseConfig | None = None) -> util:
    plugin = util.__new__(util)
    plugin.document_parse_config = config or DocumentParseConfig(enabled=True)
    plugin.document_parse_registry = DocumentParseRegistry(PLUGIN_ROOT / ".test_document_parse")
    return plugin


def test_build_document_parse_config_bounds_values():
    config = build_document_parse_config(
        {
            "enable_document_parse_tool": True,
            "max_output_chars": 999999,
            "max_file_mb": 0,
        }
    )

    assert config.enabled is True
    assert config.max_output_chars == 60000
    assert config.max_file_mb == 1


@pytest.mark.asyncio
async def test_collect_document_candidates_reads_quoted_file(tmp_path):
    path = tmp_path / "paper.pdf"
    path.write_text("placeholder", encoding="utf-8")
    event = make_event_with_file(FakeFile("paper.pdf", path))

    candidates = await collect_document_candidates(event)

    assert len(candidates) == 1
    assert candidates[0].name == "paper.pdf"
    assert candidates[0].path == path.resolve()


def test_parse_local_document_falls_back_to_plain_text(tmp_path):
    path = tmp_path / "note.md"
    path.write_text("# Title\n\nhello world", encoding="utf-8")

    parsed = parse_local_document(path, max_output_chars=12)
    formatted = format_parsed_document(parsed)

    assert parsed.name == "note.md"
    assert parsed.content.startswith("# Title")
    assert parsed.truncated is True
    assert "内容已截断" in formatted


@pytest.mark.asyncio
async def test_document_registry_registers_file_id_and_reads_markdown_lines(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("line 1\nline 2\nline 3", encoding="utf-8")
    registry = DocumentParseRegistry(tmp_path / "cache")
    event = make_event_with_file(FakeFile("note.txt", path))
    config = DocumentParseConfig(enabled=True, max_output_chars=12000)

    entries = await registry.register_event_files(event, config=config)
    available_files = format_available_files(entries)
    result = registry.read_markdown_lines(
        entries[0].file_id,
        start_line=2,
        line_count=1,
        max_output_chars=12000,
        config=config,
    )

    assert entries[0].file_id == build_document_file_id(
        DocumentCandidate(name="note.txt", path=path.resolve())
    )
    assert entries[0].markdown_path.is_file()
    assert f'file_id="{entries[0].file_id}"' in available_files
    assert "行范围：2-2/3" in result
    assert "2: line 2" in result


@pytest.mark.asyncio
async def test_parse_document_tool_reads_registered_file_id(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("hello document", encoding="utf-8")
    plugin = make_plugin(DocumentParseConfig(enabled=True, max_output_chars=12000))
    plugin.document_parse_registry = DocumentParseRegistry(tmp_path / "cache")
    event = make_event_with_file(FakeFile("note.txt", path))
    entries = await plugin.document_parse_registry.register_event_files(
        event,
        config=plugin.document_parse_config,
    )

    result = await plugin.parse_document(
        event,
        file_id=entries[0].file_id,
        start_line=1,
        line_count=20,
    )

    assert "文件：note.txt" in result
    assert "1: hello document" in result


@pytest.mark.asyncio
async def test_document_files_are_injected_into_llm_request(tmp_path):
    path = tmp_path / "paper.txt"
    path.write_text("paper content", encoding="utf-8")
    plugin = make_plugin(DocumentParseConfig(enabled=True, max_output_chars=12000))
    plugin.document_parse_registry = DocumentParseRegistry(tmp_path / "cache")
    event = make_event_with_file(FakeFile("paper.txt", path))
    req = SimpleNamespace(extra_user_content_parts=[])

    await plugin._inject_document_files_for_llm(event, req)

    assert len(req.extra_user_content_parts) == 1
    text = req.extra_user_content_parts[0].text
    assert "<available_files>" in text
    assert "paper.txt" in text
    assert "file_" in text
    assert "parse_document(file_id, start_line, line_count)" in text


@pytest.mark.asyncio
async def test_parse_document_tool_reports_disabled(tmp_path):
    plugin = make_plugin(DocumentParseConfig(enabled=False))

    result = await plugin.parse_document(make_event_with_file(), file_id="file_missing")

    assert result == DOCUMENT_PARSE_DISABLED_MESSAGE


@pytest.mark.asyncio
async def test_parse_document_tool_reports_unknown_file_id():
    plugin = make_plugin(DocumentParseConfig(enabled=True))

    result = await plugin.parse_document(make_event_with_file(), file_id="file_missing")

    assert result == DOCUMENT_PARSE_UNKNOWN_FILE_MESSAGE


def test_document_registry_cleanup_removes_unaccessed_markdown(tmp_path):
    registry = DocumentParseRegistry(tmp_path / "cache", ttl_seconds=1800)
    source_path = tmp_path / "note.txt"
    source_path.write_text("hello", encoding="utf-8")
    candidate = DocumentCandidate(name="note.txt", path=source_path.resolve())
    entry = registry.register_candidate(candidate)
    entry.markdown_path.parent.mkdir(parents=True, exist_ok=True)
    entry.markdown_path.write_text("hello", encoding="utf-8")
    entry.last_accessed_at = 1000

    registry.cleanup_expired(now=1000 + 1801)

    assert entry.file_id not in registry.entries
    assert not entry.markdown_path.exists()
