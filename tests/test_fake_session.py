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
    get_qq_nickname,
    parse_group_history_components,
    parse_group_history_text,
)

from main import util  # noqa: E402


class FakeApi:
    def __init__(self, response=None):
        self.response = response if response is not None else {}
        self.calls = []

    async def call_action(self, action, **payloads):
        self.calls.append((action, payloads))
        return self.response


def make_event(message: str, components=None, bot=None):
    message_obj = SimpleNamespace(message=components or [])
    return SimpleNamespace(
        bot=bot,
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
    event = make_event("")

    async def fake_get_qq_nickname(event, qq: str) -> str:
        return f"昵称{qq}"

    nodes = await build_group_history_nodes(
        [
            {"text": "10001 你好", "images": []},
            {"text": "10002 世界", "images": []},
        ],
        event,
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

    async def fake_get_qq_nickname(event, qq: str) -> str:
        return f"昵称{qq}"

    monkeypatch.setattr(
        "main.get_qq_nickname",
        fake_get_qq_nickname,
    )

    results = await collect(
        plugin.on_group_history_request(
            make_event(
                "10001 你好 | 10002 世界",
                [
                    Comp.Plain("10001 你好 | 10002 世界"),
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


def test_parse_group_history_text_accepts_command_stripped_arguments():
    assert parse_group_history_text("10001 你好 | 10002 世界") == [
        {"text": "10001 你好", "images": []},
        {"text": "10002 世界", "images": []},
    ]


@pytest.mark.asyncio
async def test_build_group_history_nodes_deduplicates_nickname_lookup():
    event = make_event("")
    called_qq_numbers = []

    async def fake_get_qq_nickname(event, qq: str) -> str:
        called_qq_numbers.append(qq)
        return f"昵称{qq}"

    nodes = await build_group_history_nodes(
        [
            {"text": "10001 第一段", "images": []},
            {"text": "10001 第二段", "images": []},
            {"text": "10002 第三段", "images": []},
        ],
        event,
        fake_get_qq_nickname,
    )

    assert called_qq_numbers == ["10001", "10002"]
    assert [node.name for node in nodes] == ["昵称10001", "昵称10001", "昵称10002"]


@pytest.mark.asyncio
async def test_build_group_history_nodes_defaults_name_when_lookup_fails():
    event = make_event("")

    async def fake_get_qq_nickname(event, qq: str) -> None:
        return None

    nodes = await build_group_history_nodes(
        [{"text": "10001 你好", "images": []}],
        event,
        fake_get_qq_nickname,
    )

    assert nodes[0].name == "QQ用户"


@pytest.mark.asyncio
async def test_get_qq_nickname_uses_bot_stranger_info_api():
    api = FakeApi({"nick": "群友甲"})
    event = make_event("", bot=SimpleNamespace(api=api))

    nickname = await get_qq_nickname(event, "10001")

    assert nickname == "群友甲"
    assert api.calls == [
        (
            "get_stranger_info",
            {
                "user_id": 10001,
                "no_cache": True,
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_qq_nickname_returns_none_without_bot():
    assert await get_qq_nickname(make_event(""), "10001") is None


@pytest.mark.asyncio
async def test_group_history_request_reports_invalid_format():
    plugin = make_plugin()

    results = await collect(
        plugin.on_group_history_request(
            make_event("格式错误", [])
        )
    )

    assert results[0].message_str == GROUP_HISTORY_FORMAT_ERROR


@pytest.mark.asyncio
async def test_group_history_help_command():
    plugin = make_plugin()

    results = await collect(plugin.group_history_help_command(make_event("")))

    assert "群友史 QQ号 消息内容" in results[0].message_str
    assert results[0].message_str == GROUP_HISTORY_HELP_TEXT
