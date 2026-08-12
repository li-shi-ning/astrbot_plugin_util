from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from main import util  # noqa: E402


class FakeAPI:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls = []

    async def call_action(self, action, **payloads):
        self.calls.append((action, payloads))
        if self.fail:
            raise RuntimeError("only group messages are supported")
        return {}


def make_plugin():
    plugin = util.__new__(util)

    async def get_emoji_id(text):
        return 123 if "正确" in text else None

    plugin.get_emoji_id = get_emoji_id
    return plugin


def make_event(raw_message, api):
    return SimpleNamespace(
        message_obj=SimpleNamespace(raw_message=raw_message),
        bot=SimpleNamespace(api=api),
    )


@pytest.mark.asyncio
async def test_emoji_reply_skips_private_messages():
    api = FakeAPI()
    plugin = make_plugin()
    event = make_event(
        {
            "message_type": "private",
            "message_id": 1,
            "raw_message": "正确",
        },
        api,
    )

    await plugin.replyMessage(event)

    assert api.calls == []


@pytest.mark.asyncio
async def test_emoji_reply_swallows_adapter_failure_for_group_messages():
    api = FakeAPI(fail=True)
    plugin = make_plugin()
    event = make_event(
        {
            "message_type": "group",
            "message_id": 1,
            "raw_message": "正确",
        },
        api,
    )

    await plugin.replyMessage(event)

    assert api.calls == [
        (
            "set_msg_emoji_like",
            {
                "message_id": 1,
                "emoji_id": 123,
            },
        )
    ]
