from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import astrbot.api.message_components as Comp

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from core.love_message import (  # noqa: E402
    format_love_message,
    load_love_messages,
)

from main import LOVE_MESSAGES_PATH, PLUGIN_ROOT, util  # noqa: E402


def make_event(
    *,
    group_id: str | None = "20002",
    self_id: str = "90000",
    sender_id: str = "10001",
    sender_name: str = "发送者",
    messages=None,
):
    message_obj = SimpleNamespace(
        message=messages or [],
        raw_message={"self_id": self_id},
    )
    return SimpleNamespace(
        get_group_id=lambda: group_id,
        get_self_id=lambda: self_id,
        get_sender_id=lambda: sender_id,
        get_sender_name=lambda: sender_name,
        get_messages=lambda: message_obj.message,
        message_obj=message_obj,
        plain_result=lambda text: SimpleNamespace(message_str=text),
        chain_result=lambda chain: SimpleNamespace(chain=chain),
    )


async def collect(generator):
    return [item async for item in generator]


def make_plugin(messages=("不要抱怨，抱我。",)) -> util:
    plugin = util.__new__(util)
    plugin.love_messages = messages
    return plugin


def test_loads_non_empty_lines_from_love_message_file(tmp_path):
    path = tmp_path / "love_messages.txt"
    path.write_text("第一句。\n\n 第二句。 \n", encoding="utf-8")

    assert load_love_messages(path) == ("第一句。", "第二句。")


def test_bundled_love_message_path_is_absolute_and_cwd_independent(
    monkeypatch,
    tmp_path,
):
    monkeypatch.chdir(tmp_path)

    assert PLUGIN_ROOT.is_absolute()
    assert LOVE_MESSAGES_PATH.is_absolute()
    assert LOVE_MESSAGES_PATH == PLUGIN_ROOT / "core" / "love_messages.txt"
    assert len(load_love_messages(LOVE_MESSAGES_PATH)) == 359


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("不要抱怨，抱我。", "不要抱怨，抱我。喵"),
        ("已经有喵", "已经有喵"),
        ("", ""),
    ],
)
def test_formats_love_message(message, expected):
    assert format_love_message(message) == expected


@pytest.mark.asyncio
async def test_command_uses_explicit_qq(monkeypatch):
    plugin = make_plugin()
    monkeypatch.setattr(
        "main.choose_love_message",
        lambda messages: messages[0],
    )

    results = await collect(
        plugin.send_random_love_message(make_event(), "10002")
    )

    assert len(results) == 1
    assert str(results[0].chain[0].qq) == "10002"
    assert results[0].chain[1].text == " 不要抱怨，抱我。喵"


@pytest.mark.asyncio
async def test_command_uses_last_non_bot_mention(monkeypatch):
    plugin = make_plugin()
    monkeypatch.setattr("main.choose_love_message", lambda messages: messages[0])
    event = make_event(
        messages=[
            Comp.At(qq="90000", name="机器人"),
            Comp.At(qq="10002", name="目标一"),
            Comp.At(qq="10003", name="目标二"),
        ]
    )

    results = await collect(plugin.send_random_love_message(event))

    assert str(results[0].chain[0].qq) == "10003"


@pytest.mark.asyncio
async def test_command_defaults_to_sender_when_target_missing(monkeypatch):
    plugin = make_plugin()
    monkeypatch.setattr("main.choose_love_message", lambda messages: messages[0])

    results = await collect(plugin.send_random_love_message(make_event()))

    assert str(results[0].chain[0].qq) == "10001"


def test_invalid_explicit_qq_falls_back_to_sender():
    plugin = make_plugin()

    target_id, target_name = plugin._resolve_love_message_target(
        make_event(),
        "not-a-qq",
    )

    assert target_id == "10001"
    assert target_name == "发送者"
