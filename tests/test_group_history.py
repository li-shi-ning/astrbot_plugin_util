from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from core.group_history import (  # noqa: E402
    GroupHistoryProfile,
    build_daily_group_history_entries,
    filter_group_history_candidates,
    normalize_group_history_members,
    select_daily_group_history_profile,
)

from main import util  # noqa: E402


class FakeApi:
    def __init__(self, members):
        self.members = members
        self.calls = []

    async def call_action(self, action, **payload):
        self.calls.append((action, payload))
        return self.members


def make_event(
    *,
    group_id: str | None = "20002",
    sender_id: str = "10001",
    sender_name: str = "发送者",
    self_id: str = "90000",
    members=None,
):
    api = FakeApi(members if members is not None else [])
    message_obj = SimpleNamespace(raw_message={"self_id": self_id}, message=[])
    return SimpleNamespace(
        bot=SimpleNamespace(api=api),
        get_group_id=lambda: group_id,
        get_sender_id=lambda: sender_id,
        get_sender_name=lambda: sender_name,
        get_self_id=lambda: self_id,
        message_obj=message_obj,
        plain_result=lambda text: SimpleNamespace(message_str=text),
        chain_result=lambda chain: SimpleNamespace(chain=chain),
    )


async def collect(generator):
    return [item async for item in generator]


def make_plugin() -> util:
    return util.__new__(util)


def test_normalizes_group_members_and_prefers_card_name():
    profiles = normalize_group_history_members(
        [
            {"user_id": 10001, "card": "群名片", "nickname": "昵称"},
            {"user_id": "10002", "card": "", "nickname": "备用昵称"},
            {"user_id": "bad", "nickname": "跳过"},
            {"user_id": "10001", "nickname": "重复"},
        ]
    )

    assert profiles == (
        GroupHistoryProfile("10001", "群名片"),
        GroupHistoryProfile("10002", "备用昵称"),
    )


def test_daily_selection_is_stable_and_order_independent():
    today = date(2026, 6, 24)
    first = (
        GroupHistoryProfile("10002", "二号"),
        GroupHistoryProfile("10001", "一号"),
    )
    second = tuple(reversed(first))

    assert select_daily_group_history_profile(first, "20002", today) == (
        select_daily_group_history_profile(second, "20002", today)
    )


def test_candidate_filter_excludes_bot_when_possible():
    profiles = (
        GroupHistoryProfile("90000", "机器人"),
        GroupHistoryProfile("10001", "群友"),
    )

    assert filter_group_history_candidates(profiles, {"90000"}) == (
        GroupHistoryProfile("10001", "群友"),
    )


def test_history_entries_are_stable_for_same_day():
    profile = GroupHistoryProfile("10001", "群友甲")

    assert build_daily_group_history_entries(
        profile,
        "20002",
        date(2026, 6, 24),
    ) == build_daily_group_history_entries(
        profile,
        "20002",
        date(2026, 6, 24),
    )


@pytest.mark.asyncio
async def test_command_sends_forward_nodes_from_group_members():
    plugin = make_plugin()
    event = make_event(
        members=[
            {"user_id": "90000", "nickname": "机器人"},
            {"user_id": "10001", "card": "群友甲"},
        ]
    )

    results = await collect(plugin.send_daily_group_history(event))

    assert len(results) == 1
    nodes = results[0].chain[0].nodes
    assert len(nodes) == 6
    assert nodes[0].uin == "10001"
    assert "群友史" in nodes[0].content[0].text
    assert event.bot.api.calls[0][0] == "get_group_member_list"
    assert event.bot.api.calls[0][1]["group_id"] == 20002


@pytest.mark.asyncio
async def test_command_falls_back_to_sender_when_member_list_is_empty():
    plugin = make_plugin()
    event = make_event(members=[])

    results = await collect(plugin.send_daily_group_history(event))

    nodes = results[0].chain[0].nodes
    assert nodes[0].uin == "10001"
    assert "发送者" in nodes[1].content[0].text


@pytest.mark.asyncio
async def test_command_rejects_private_chat():
    plugin = make_plugin()

    results = await collect(
        plugin.send_daily_group_history(make_event(group_id=None))
    )

    assert results[0].message_str == "群友史只能在群聊里生成。"
