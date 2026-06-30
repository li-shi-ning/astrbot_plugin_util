from __future__ import annotations

import sys
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from core.roleplay_knowledge import (  # noqa: E402
    ROLEPLAY_KNOWLEDGE_TOOL_NAME,
    RoleplayKnowledgeBase,
    format_roleplay_search_results,
    load_roleplay_knowledge_config,
    select_roleplay_database,
)
from main import ROLEPLAY_KNOWLEDGE_DB_PATH, ROLEPLAY_KNOWLEDGE_ROOT, util  # noqa: E402


class FakeToolSet:
    def __init__(self, names: list[str]):
        self.tools = [SimpleNamespace(name=name) for name in names]

    def names(self):
        return [tool.name for tool in self.tools]


def test_roleplay_knowledge_config_bounds_values():
    config = load_roleplay_knowledge_config(
        {
            "roleplay_knowledge": {
                "enable_roleplay_knowledge_tool": True,
                "max_results": 99,
                "max_chars_per_result": 50,
            }
        }
    )

    assert config.enabled is True
    assert config.max_results == 10
    assert config.max_chars_per_result == 200


def test_roleplay_knowledge_selects_database_by_platform_id():
    assert select_roleplay_database("ni") == "ema"
    assert select_roleplay_database("NI") == "ema"
    assert select_roleplay_database("li") == "hiro"
    assert select_roleplay_database(None) == "hiro"


def test_roleplay_knowledge_builds_sqlite_database(tmp_path):
    db_path = tmp_path / "roleplay_knowledge.sqlite3"
    knowledge_base = RoleplayKnowledgeBase.from_root(ROLEPLAY_KNOWLEDGE_ROOT, db_path)

    assert db_path.exists()
    assert knowledge_base.db_path == db_path.resolve()
    with sqlite3.connect(db_path) as connection:
        ema_count = connection.execute(
            "SELECT COUNT(*) FROM documents WHERE database = 'ema'"
        ).fetchone()[0]
        hiro_count = connection.execute(
            "SELECT COUNT(*) FROM documents WHERE database = 'hiro'"
        ).fetchone()[0]

    assert ema_count > 0
    assert hiro_count > 0


def test_roleplay_knowledge_searches_split_databases(tmp_path):
    knowledge_base = RoleplayKnowledgeBase.from_root(
        ROLEPLAY_KNOWLEDGE_ROOT,
        tmp_path / "roleplay_knowledge.sqlite3",
    )

    ema_results = knowledge_base.search("ema", "小笨狗", limit=3, max_chars_per_result=500)
    hiro_results = knowledge_base.search("hiro", "希罗 正确", limit=3, max_chars_per_result=500)

    assert knowledge_base.count("ema") > 0
    assert knowledge_base.count("hiro") > 0
    assert ema_results
    assert all(result.document.database == "ema" for result in ema_results)
    assert hiro_results
    assert all(result.document.database == "hiro" for result in hiro_results)


@pytest.mark.asyncio
async def test_roleplay_knowledge_tool_uses_ema_for_ni(tmp_path):
    plugin = util.__new__(util)
    plugin.roleplay_knowledge_config = load_roleplay_knowledge_config(
        {
            "roleplay_knowledge": {
                "enable_roleplay_knowledge_tool": True,
                "max_results": 2,
                "max_chars_per_result": 400,
            }
        }
    )
    plugin.roleplay_knowledge_base = RoleplayKnowledgeBase.from_root(
        ROLEPLAY_KNOWLEDGE_ROOT,
        tmp_path / "roleplay_knowledge.sqlite3",
    )
    event = SimpleNamespace(get_platform_id=lambda: "ni")

    result = await plugin.search_roleplay_knowledge(event, "艾玛", 2)

    assert "roleplay_database: ema" in result
    assert "matches:" in result


def test_roleplay_knowledge_db_path_uses_plugin_data_directory():
    assert ROLEPLAY_KNOWLEDGE_DB_PATH.name == "roleplay_knowledge.sqlite3"
    assert ROLEPLAY_KNOWLEDGE_DB_PATH.parent.name == "roleplay_knowledge"


def test_format_roleplay_search_results_reports_empty_matches():
    result = format_roleplay_search_results("hiro", "不存在的检索词", [])

    assert "roleplay_database: hiro" in result
    assert "No matching roleplay knowledge was found." in result


@pytest.mark.asyncio
async def test_roleplay_knowledge_tool_is_removed_when_disabled():
    plugin = util.__new__(util)
    plugin.is_debug = False
    plugin.remove_history_read_tool_before_llm = False
    plugin.enable_let_li_speak_tool = False
    plugin.roleplay_knowledge_config = SimpleNamespace(enabled=False)
    plugin.enable_history_chunking_feature = False
    plugin._scoped_request_history_cache = {}
    req = SimpleNamespace(
        func_tool=FakeToolSet([ROLEPLAY_KNOWLEDGE_TOOL_NAME, "read_current_history"]),
        contexts=[],
    )
    event = SimpleNamespace(
        get_platform_id=lambda: "li",
        unified_msg_origin="aiocqhttp:GroupMessage:10001",
    )

    await plugin.apply_history_tool_config(event, req)

    assert ROLEPLAY_KNOWLEDGE_TOOL_NAME not in req.func_tool.names()
    assert "read_current_history" in req.func_tool.names()
