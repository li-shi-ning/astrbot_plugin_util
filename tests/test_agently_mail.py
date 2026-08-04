from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from core.agently_mail import (  # noqa: E402
    AgentlyMailClient,
    AgentlyMailConfig,
    AgentlyMailError,
    AgentlyMailResult,
    PendingMailConfirmation,
    agently_mail_env,
    build_agently_mail_config,
    build_recipient_args,
    extract_first_url,
    load_pending_confirmations,
    parse_confirmation_token,
    save_pending_confirmations,
)
from main import util  # noqa: E402


class FakeMailClient:
    def __init__(self):
        self.calls = []
        self.confirm_calls = []

    async def first_step_write(self, action, args):
        self.calls.append((action, args))
        result = AgentlyMailResult(
            command=("agently-cli", *args),
            returncode=0,
            stdout='{"data":{"confirmation_token":"token-1"}}',
            stderr="",
        )
        pending = PendingMailConfirmation(
            token="token-1",
            action=action,
            command_args=tuple(args),
            summary="summary",
            created_at=1.0,
        )
        return result, pending

    async def confirm(self, pending):
        self.confirm_calls.append(pending)
        return AgentlyMailResult(
            command=("agently-cli", *pending.command_args, "--confirmation-token", pending.token),
            returncode=0,
            stdout="confirmed",
            stderr="",
        )


def make_plugin(config: AgentlyMailConfig, client=None):
    plugin = util.__new__(util)
    plugin.agently_mail_config = config
    plugin.agently_mail_client = client or FakeMailClient()
    plugin.agently_mail_pending_confirmations = {}
    plugin._saved = False

    def save():
        plugin._saved = True

    plugin._save_agently_mail_pending_confirmations = save
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


def test_parse_confirmation_token_from_nested_json_and_text():
    assert parse_confirmation_token('{"data":{"confirmation_token":"abc"}}') == "abc"
    assert parse_confirmation_token("confirmation_token: token-123") == "token-123"


def test_pending_confirmations_round_trip(tmp_path):
    path = tmp_path / "pending.json"
    pending = PendingMailConfirmation(
        token="token-1",
        action="发送邮件",
        command_args=("message", "+send", "--to", "a@example.com"),
        summary="summary",
        created_at=1.0,
    )

    save_pending_confirmations(path, {"token-1": pending})
    loaded = load_pending_confirmations(path)

    assert loaded["token-1"] == pending


@pytest.mark.asyncio
async def test_first_step_write_requires_confirmation_token(monkeypatch):
    client = AgentlyMailClient(AgentlyMailConfig(enabled=True))

    async def fake_run(args):
        return AgentlyMailResult(
            command=("agently-cli", *args),
            returncode=0,
            stdout="no token",
            stderr="",
        )

    monkeypatch.setattr(client, "run", fake_run)

    with pytest.raises(AgentlyMailError):
        await client.first_step_write("发送邮件", ["message", "+send"])


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
async def test_qqmail_send_message_creates_pending_confirmation():
    client = FakeMailClient()
    plugin = make_plugin(
        AgentlyMailConfig(
            enabled=True,
            enable_llm_tools=True,
            allow_write_operations=True,
        ),
        client,
    )

    result = await plugin.qqmail_send_message(
        make_event(),
        "a@example.com,b@example.com",
        "Hi",
        "Hello",
    )

    assert "confirmation_token: token-1" in result
    assert plugin.agently_mail_pending_confirmations["token-1"].action == "发送邮件"
    assert client.calls[0][1] == [
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
    assert plugin._saved is True


@pytest.mark.asyncio
async def test_qqmail_send_message_respects_write_tool_switch():
    plugin = make_plugin(
        AgentlyMailConfig(
            enabled=True,
            enable_llm_tools=True,
            allow_write_operations=False,
        )
    )

    result = await plugin.qqmail_send_message(make_event(), "a@example.com", "Hi", "Hello")

    assert "写操作已关闭" in result


@pytest.mark.asyncio
async def test_confirm_command_runs_pending_operation_and_removes_token():
    client = FakeMailClient()
    plugin = make_plugin(
        AgentlyMailConfig(
            enabled=True,
            admin_qqs=("10001",),
        ),
        client,
    )
    pending = PendingMailConfirmation(
        token="token-1",
        action="发送邮件",
        command_args=("message", "+send", "--to", "a@example.com"),
        summary="summary",
        created_at=1.0,
    )
    plugin.agently_mail_pending_confirmations["token-1"] = pending
    event = make_event("10001")

    await plugin.agently_mail_confirm_command(event, "token-1")

    assert client.confirm_calls == [pending]
    assert "token-1" not in plugin.agently_mail_pending_confirmations
    assert plugin._saved is True
    assert "已确认执行" in event.sent[0].chain[0].text


@pytest.mark.asyncio
async def test_confirm_command_rejects_non_admin():
    plugin = make_plugin(
        AgentlyMailConfig(
            enabled=True,
            admin_qqs=("10001",),
        )
    )
    event = make_event("10002")

    await plugin.agently_mail_confirm_command(event, "token-1")

    assert "仅允许已配置管理员" in event.sent[0].chain[0].text
