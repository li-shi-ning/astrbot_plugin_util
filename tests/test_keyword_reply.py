from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from core.keyword_reply import (  # noqa: E402
    GroupKeywordReply,
    load_group_keyword_replies,
)

from main import util  # noqa: E402


def make_event(
    *,
    group_id: str | None = "20002",
    message: str = "播放 AIZO",
):
    return SimpleNamespace(
        message_str=message,
        get_group_id=lambda: group_id,
        get_message_outline=lambda: message,
        plain_result=lambda text: SimpleNamespace(message_str=text),
    )


async def collect_async_results(generator):
    return [item async for item in generator]


def make_plugin(rules: dict[str, GroupKeywordReply]) -> util:
    plugin = util.__new__(util)
    plugin.group_keyword_replies = rules
    return plugin


def test_loads_only_explicit_group_rules_without_global_fallback():
    rules = load_group_keyword_replies(
        {
            "global_keyword_reply": {
                "enabled": True,
                "keywords": ["全局"],
                "reply_lines": ["不应生效"],
            },
            "group_keyword_replies": [
                {
                    "group_id": "20002",
                    "enabled": True,
                    "keywords": ["Aizo", ""],
                    "reply_lines": ["第一句", "第二句", "  "],
                }
            ],
        }
    )

    assert set(rules) == {"20002"}
    assert rules["20002"].keywords == ("Aizo",)
    assert rules["20002"].reply_lines == ("第一句", "第二句")


def test_duplicate_group_uses_last_configuration():
    rules = load_group_keyword_replies(
        {
            "group_keyword_replies": [
                {"group_id": "20002", "keywords": ["旧"], "reply_lines": ["旧台词"]},
                {
                    "group_id": "20002",
                    "enabled": False,
                    "keywords": ["新"],
                    "reply_lines": ["新台词"],
                },
            ]
        }
    )

    assert rules["20002"].enabled is False
    assert rules["20002"].keywords == ("新",)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("请播放 AIZO", "第一句\n第二句\n第三句\n第四句"),
        ("没有命中", None),
        ("", None),
    ],
)
def test_response_for_matches_case_insensitively(message, expected):
    settings = GroupKeywordReply(
        enabled=True,
        keywords=("aizo",),
        reply_lines=("第一句", "第二句", "第三句", "第四句"),
    )

    assert settings.response_for(message) == expected


def test_disabled_or_incomplete_rule_never_replies():
    disabled = GroupKeywordReply(False, ("aizo",), ("台词",))
    no_keywords = GroupKeywordReply(True, (), ("台词",))
    no_lines = GroupKeywordReply(True, ("aizo",), ())

    assert disabled.response_for("aizo") is None
    assert no_keywords.response_for("aizo") is None
    assert no_lines.response_for("aizo") is None


@pytest.mark.asyncio
async def test_handler_replies_only_in_configured_enabled_group():
    plugin = make_plugin(
        {
            "20002": GroupKeywordReply(
                enabled=True,
                keywords=("aizo",),
                reply_lines=("第一句", "第二句"),
            ),
            "30003": GroupKeywordReply(
                enabled=False,
                keywords=("aizo",),
                reply_lines=("不应发送",),
            ),
        }
    )

    matched = await collect_async_results(
        plugin.reply_group_keyword(make_event(group_id="20002"))
    )
    unconfigured = await collect_async_results(
        plugin.reply_group_keyword(make_event(group_id="99999"))
    )
    disabled = await collect_async_results(
        plugin.reply_group_keyword(make_event(group_id="30003"))
    )
    private = await collect_async_results(
        plugin.reply_group_keyword(make_event(group_id=None))
    )

    assert [item.message_str for item in matched] == ["第一句\n第二句"]
    assert unconfigured == []
    assert disabled == []
    assert private == []
