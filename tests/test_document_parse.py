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
    DOCUMENT_PARSE_MISSING_FILE_MESSAGE,
    DocumentParseConfig,
    build_document_parse_config,
    collect_document_candidates,
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
    return plugin


def test_build_document_parse_config_bounds_values():
    config = build_document_parse_config(
        {
            "enable_document_parse_tool": True,
            "max_output_chars": 999999,
            "max_file_mb": 0,
            "allow_local_paths": True,
        }
    )

    assert config.enabled is True
    assert config.max_output_chars == 60000
    assert config.max_file_mb == 1
    assert config.allow_local_paths is True


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
async def test_parse_document_tool_reads_first_current_file(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("hello document", encoding="utf-8")
    plugin = make_plugin(DocumentParseConfig(enabled=True, max_output_chars=12000))
    event = make_event_with_file(FakeFile("note.txt", path))

    result = await plugin.parse_document(event)

    assert "文件：note.txt" in result
    assert "hello document" in result


@pytest.mark.asyncio
async def test_parse_document_tool_reports_disabled(tmp_path):
    plugin = make_plugin(DocumentParseConfig(enabled=False))

    result = await plugin.parse_document(make_event_with_file())

    assert result == DOCUMENT_PARSE_DISABLED_MESSAGE


@pytest.mark.asyncio
async def test_parse_document_tool_reports_missing_file():
    plugin = make_plugin(DocumentParseConfig(enabled=True))

    result = await plugin.parse_document(make_event_with_file())

    assert result == DOCUMENT_PARSE_MISSING_FILE_MESSAGE
