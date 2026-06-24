from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import astrbot.api.message_components as Comp

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from core.group_history import (  # noqa: E402
    GROUP_HISTORY_FORMAT_ERROR,
    GROUP_HISTORY_HELP_TEXT,
    build_group_history_nodes,
    parse_group_history_components,
)

from main import util  # noqa: E402


def make_event(message: str, components=None):
    message_obj = SimpleNamespace(message=components or [])
    return SimpleNamespace(
        message_str=message,
        message_obj=message_obj,
        plain_result=lambda text: SimpleNamespace(message_str=text),
        chain_result=lambda chain: SimpleNamespace(chain=chain),
    )


async def collect(generator):
    return [item async for item in generator]


def make_plugin() -> util:
    return util.__new__(util)


@pytest.mark.asyncio
async def test_parse_message_components_splits_segments_and_keeps_image_position():
    image = Comp.Image(file="", url="https://example.com/a.jpg")
    message_obj = SimpleNamespace(
        message=[
            Comp.Plain("群友史 10001 第一段"),
            image,
            Comp.Plain(" | 10002 第二段"),
        ]
    )

    segments = parse_group_history_components(message_obj)

    assert segments == [
        {"text": "10001 第一段 ", "images": ["https://example.com/a.jpg"]},
        {"text": " 10002 第二段", "images": []},
    ]


@pytest.mark.asyncio
async def test_build_group_history_nodes():
    async def fake_get_qq_nickname(qq: str) -> str:
        return f"昵称{qq}"

    nodes = await build_group_history_nodes(
        [
            {"text": "10001 你好", "images": []},
            {"text": "10002 世界", "images": []},
        ],
        fake_get_qq_nickname,
    )

    assert len(nodes) == 2
    assert nodes[0].uin == "10001"
    assert nodes[0].name == "昵称10001"
    assert nodes[0].content[0].text == "你好"
    assert nodes[1].uin == "10002"
    assert nodes[1].content[0].text == "世界"


@pytest.mark.asyncio
async def test_group_history_request_builds_forward_nodes(monkeypatch):
    plugin = make_plugin()

    async def fake_get_qq_nickname(qq: str) -> str:
        return f"昵称{qq}"

    monkeypatch.setattr(
        "main.get_qq_nickname",
        fake_get_qq_nickname,
    )

    results = await collect(
        plugin.on_group_history_request(
            make_event(
                "群友史 10001 你好 | 10002 世界",
                [
                    Comp.Plain("群友史 10001 你好 | 10002 世界"),
                ],
            )
        )
    )

    assert len(results) == 1
    nodes = results[0].chain[0].nodes
    assert len(nodes) == 2
    assert nodes[0].uin == "10001"
    assert nodes[0].name == "昵称10001"
    assert nodes[0].content[0].text == "你好"
    assert nodes[1].uin == "10002"
    assert nodes[1].content[0].text == "世界"


@pytest.mark.asyncio
async def test_legacy_fake_message_request_is_ignored():
    plugin = make_plugin()

    results = await collect(
        plugin.on_group_history_request(
            make_event(
                "伪造消息 10001 你好 | 10002 世界",
                [
                    Comp.Plain("伪造消息 10001 你好 | 10002 世界"),
                ],
            )
        )
    )

    assert results == []


@pytest.mark.asyncio
async def test_group_history_request_ignores_unrelated_messages():
    plugin = make_plugin()

    results = await collect(plugin.on_group_history_request(make_event("普通消息")))

    assert results == []


@pytest.mark.asyncio
async def test_group_history_request_reports_invalid_format():
    plugin = make_plugin()

    results = await collect(
        plugin.on_group_history_request(
            make_event("群友史 格式错误", [])
        )
    )

    assert results[0].message_str == GROUP_HISTORY_FORMAT_ERROR


@pytest.mark.asyncio
async def test_group_history_help_command():
    plugin = make_plugin()

    results = await collect(plugin.group_history_help_command(make_event("")))

    assert "群友史 QQ号 消息内容" in results[0].message_str
    assert results[0].message_str == GROUP_HISTORY_HELP_TEXT
