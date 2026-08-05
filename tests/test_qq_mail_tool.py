from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

import main  # noqa: E402
from core.offline_email_alert import (  # noqa: E402
    QQMailToolConfig,
    build_qqmail_tool_config,
    parse_email_addresses,
)
from main import util  # noqa: E402


def make_plugin(config: QQMailToolConfig):
    plugin = util.__new__(util)
    plugin.qqmail_tool_config = config
    return plugin


def make_event():
    return SimpleNamespace()


def test_build_qqmail_tool_config_is_independent_from_offline_alert():
    config = build_qqmail_tool_config(
        {
            "enable_qqmail_tool": True,
            "sender": " bot@qq.com ",
            "display_name": " 艾玛 ",
            "QQ_password": " auth-code ",
            "list_default_limit": 999,
        }
    )

    assert config.enabled is True
    assert config.sender == "bot@qq.com"
    assert config.display_name == "艾玛"
    assert config.QQ_password == "auth-code"
    assert config.list_default_limit == 50
    assert config.ready is True


def test_parse_email_addresses_splits_common_separators():
    assert parse_email_addresses("a@example.com, b@example.com;c@example.com\n d@example.com") == [
        "a@example.com",
        "b@example.com",
        "c@example.com",
        "d@example.com",
    ]


@pytest.mark.asyncio
async def test_qqmail_send_uses_independent_smtp_config(monkeypatch):
    sent = []

    async def fake_send_qq_email_async(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(main, "send_qq_email_async", fake_send_qq_email_async)
    plugin = make_plugin(
        QQMailToolConfig(
            enabled=True,
            sender="tool@qq.com",
            display_name="艾玛",
            QQ_password="tool-auth",
        )
    )

    result = await plugin.qqmail(
        make_event(),
        "send",
        to="a@example.com,b@example.com",
        subject="Hi",
        body="Hello",
        cc="c@example.com",
        bcc="d@example.com",
    )

    assert result == "QQ邮箱邮件已发送。"
    assert sent == [
        {
            "sender": "tool@qq.com",
            "password": "tool-auth",
            "receiver": "a@example.com,b@example.com",
            "subject": "Hi",
            "content": "Hello",
            "display_name": "艾玛",
            "cc": "c@example.com",
            "bcc": "d@example.com",
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "kwargs", "patched_name", "expected"),
    [
        ("list", {"limit": 2}, "qqmail_list_async", "list ok"),
        ("read", {"message_id": "1"}, "qqmail_read_async", "read ok"),
        ("search", {"query": "hello"}, "qqmail_search_async", "search ok"),
        ("trash", {"message_id": "1"}, "qqmail_trash_async", "trash ok"),
    ],
)
async def test_qqmail_dispatches_imap_actions(
    monkeypatch,
    action,
    kwargs,
    patched_name,
    expected,
):
    calls = []

    async def fake_action(**call_kwargs):
        calls.append(call_kwargs)
        return expected

    monkeypatch.setattr(main, patched_name, fake_action)
    plugin = make_plugin(
        QQMailToolConfig(
            enabled=True,
            sender="tool@qq.com",
            QQ_password="tool-auth",
            list_default_limit=10,
        )
    )

    result = await plugin.qqmail(make_event(), action, **kwargs)

    assert result == expected
    assert calls[0]["sender"] == "tool@qq.com"
    assert calls[0]["password"] == "tool-auth"


@pytest.mark.asyncio
async def test_qqmail_rejects_when_tool_disabled():
    plugin = make_plugin(QQMailToolConfig(enabled=False))

    result = await plugin.qqmail(
        make_event(),
        "send",
        to="a@example.com",
        subject="Hi",
        body="Hello",
    )

    assert "QQ邮箱工具已关闭" in result
