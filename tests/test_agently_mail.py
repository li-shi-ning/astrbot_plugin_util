from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from core.agently_mail import (  # noqa: E402
    AgentlyMailConfig,
    AgentlyMailResult,
    agently_mail_env,
    build_agently_mail_config,
    build_recipient_args,
    extract_first_url,
)
from main import util  # noqa: E402


class FakeMailClient:
    def __init__(self):
        self.calls = []

    async def run(self, args):
        self.calls.append(args)
        return AgentlyMailResult(
            command=("agently-cli", *args),
            returncode=0,
            stdout="sent",
            stderr="",
        )


def make_plugin(config: AgentlyMailConfig, client=None):
    plugin = util.__new__(util)
    plugin.agently_mail_config = config
    plugin.agently_mail_client = client or FakeMailClient()
    return plugin


def make_event(sender_id="10001"):
    sent = []

    async def send(chain):
        sent.append(chain)

    return SimpleNamespace(
        get_sender_id=lambda: sender_id,
        send=send,
        sent=sent,
        stop_event=lambda: None,
    )


def test_build_agently_mail_config_clamps_and_reads_admins():
    config = build_agently_mail_config(
        {
            "enable_agently_mail_feature": True,
            "cli_path": "agently-cli",
            "workspace": "mail-workspace",
            "timeout_seconds": 9999,
            "list_default_limit": 0,
            "enable_agently_mail_tools": True,
            "allow_write_operations": True,
            "admin_qqs": [" 10001 ", "", "10002"],
        }
    )

    assert config.enabled is True
    assert config.ready is True
    assert config.workspace == "mail-workspace"
    assert config.timeout_seconds == 600
    assert config.list_default_limit == 1
    assert config.enable_llm_tools is True
    assert config.allow_write_operations is True
    assert config.admin_qqs == ("10001", "10002")


def test_agently_mail_env_injects_workspace(monkeypatch):
    monkeypatch.delenv("AGENTLY_WORKSPACE", raising=False)

    env = agently_mail_env(AgentlyMailConfig(workspace="astrbot_plugin_util"))

    assert env["AGENTLY_WORKSPACE"] == "astrbot_plugin_util"


def test_recipient_args_repeat_flags_for_comma_separated_values():
    assert build_recipient_args("--to", "a@example.com, b@example.com;c@example.com") == [
        "--to",
        "a@example.com",
        "--to",
        "b@example.com",
        "--to",
        "c@example.com",
    ]


def test_extract_first_url_keeps_original_url_opaque():
    url = "https://agent.qq.com/oauth?client=a%2Fb&state=x-y"
    text = f"请打开 {url} 完成授权。"

    assert extract_first_url(text) == url


def test_agently_mail_admin_requires_configured_sender():
    plugin = make_plugin(
        AgentlyMailConfig(
            enabled=True,
            admin_qqs=("10001",),
        )
    )

    assert plugin._agently_mail_is_admin(make_event("10001")) is True
    assert plugin._agently_mail_is_admin(make_event("10002")) is False


@pytest.mark.asyncio
async def test_qqmail_aggregated_tool_splits_recipients():
    client = FakeMailClient()
    plugin = make_plugin(
        AgentlyMailConfig(
            enabled=True,
            enable_llm_tools=True,
            allow_write_operations=True,
        ),
        client,
    )

    result = await plugin.qqmail(
        make_event(),
        "send",
        to="a@example.com,b@example.com",
        subject="Hi",
        body="Hello",
    )

    assert "已执行" in result
    assert "sent" in result
    assert client.calls[0] == [
        "message",
        "+send",
        "--to",
        "a@example.com",
        "--to",
        "b@example.com",
        "--subject",
        "Hi",
        "--body",
        "Hello",
    ]


@pytest.mark.asyncio
async def test_qqmail_aggregated_tool_respects_write_tool_switch():
    plugin = make_plugin(
        AgentlyMailConfig(
            enabled=True,
            enable_llm_tools=True,
            allow_write_operations=False,
        )
    )

    result = await plugin.qqmail(
        make_event(),
        "send",
        to="a@example.com",
        subject="Hi",
        body="Hello",
    )

    assert "写操作已关闭" in result
