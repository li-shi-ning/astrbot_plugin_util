from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import astrbot.api.message_components as Comp

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from main import FORWARD_NODES_BATCH_SIZE, util  # noqa: E402


def make_plugin() -> util:
    plugin = util.__new__(util)
    plugin.is_debug = False
    return plugin


def make_event(self_id: str = "10000"):
    sent = []

    async def send(chain):
        sent.append(chain)

    return SimpleNamespace(
        get_self_id=lambda: self_id,
        chain_result=lambda chain: SimpleNamespace(chain=chain),
        send=send,
        sent=sent,
    )


@pytest.mark.asyncio
async def test_forward_split_output_batches_nodes_at_platform_limit():
    plugin = make_plugin()
    event = make_event()
    output_lines = [f"第 {index} 段" for index in range(FORWARD_NODES_BATCH_SIZE * 2 + 5)]

    await plugin._send_split_lines_as_forward(event, output_lines)

    assert len(event.sent) == 3
    batch_sizes = [len(result.chain[0].nodes) for result in event.sent]
    assert batch_sizes == [
        FORWARD_NODES_BATCH_SIZE,
        FORWARD_NODES_BATCH_SIZE,
        5,
    ]
    assert all(isinstance(result.chain[0], Comp.Nodes) for result in event.sent)


@pytest.mark.asyncio
async def test_forward_split_output_skips_blank_lines_before_batching():
    plugin = make_plugin()
    event = make_event()
    output_lines = ["第一段", " ", "", "\n", "第二段"]

    await plugin._send_split_lines_as_forward(event, output_lines)

    assert len(event.sent) == 1
    nodes = event.sent[0].chain[0].nodes
    assert [node.content[0].text for node in nodes] == ["第一段", "第二段"]
