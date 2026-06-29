from __future__ import annotations

import sys
from email import message_from_string
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from core.offline_email_alert import (  # noqa: E402
    OFFLINE_EMAIL_SUBJECT,
    OfflineEmailAlertConfig,
    build_offline_email_alert_config,
    format_offline_email_content,
    is_bot_offline_notice,
    send_qq_email,
)

import main  # noqa: E402
from main import util  # noqa: E402


OFFLINE_RAW_MESSAGE = {
    "time": 1782688326,
    "self_id": 3513785608,
    "post_type": "notice",
    "notice_type": "bot_offline",
    "user_id": 3513785608,
    "tag": "下线通知",
    "message": "你的账号当前登录已失效，请重新登录。",
}


def test_detects_aiocqhttp_bot_offline_notice():
    assert is_bot_offline_notice(OFFLINE_RAW_MESSAGE) is True


@pytest.mark.parametrize(
    "raw_message",
    [
        {},
        None,
        {"post_type": "message", "notice_type": "bot_offline"},
        {"post_type": "notice", "notice_type": "group_increase"},
    ],
)
def test_ignores_non_offline_notice(raw_message):
    assert is_bot_offline_notice(raw_message) is False


def test_build_offline_email_alert_config_strips_values():
    config = build_offline_email_alert_config(
        {
            "enable_offline_email_alert": True,
            "sender": " sender@qq.com ",
            "QQ_password": " auth-code ",
            "receiver": " receiver@example.com ",
        }
    )

    assert config == OfflineEmailAlertConfig(
        enabled=True,
        sender="sender@qq.com",
        QQ_password="auth-code",
        receiver="receiver@example.com",
    )
    assert config.is_ready is True


def test_format_offline_email_content_contains_notice_fields():
    content = format_offline_email_content(OFFLINE_RAW_MESSAGE)

    assert "AstrBot 检测到 QQ 账号下线通知" in content
    assert "self_id: 3513785608" in content
    assert "你的账号当前登录已失效，请重新登录。" in content


def test_send_qq_email_uses_qq_smtp(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            calls.append(("quit",))

        def login(self, sender, password):
            calls.append(("login", sender, password))

        def sendmail(self, sender, receiver, message):
            calls.append(("sendmail", sender, receiver, message))

    monkeypatch.setattr("core.offline_email_alert.smtplib.SMTP_SSL", FakeSMTP)

    send_qq_email(
        sender="sender@qq.com",
        password="auth-code",
        receiver="receiver@example.com",
        subject=OFFLINE_EMAIL_SUBJECT,
        content="offline",
    )

    assert calls[0] == ("connect", "smtp.qq.com", 465)
    assert calls[1] == ("login", "sender@qq.com", "auth-code")
    assert calls[2][0:3] == ("sendmail", "sender@qq.com", "receiver@example.com")
    parsed_message = message_from_string(calls[2][3])
    assert parsed_message.get_payload(decode=True).decode("utf-8") == "offline"
    assert calls[3] == ("quit",)


@pytest.mark.asyncio
async def test_handler_sends_email_when_offline_notice_detected(monkeypatch):
    sent = []

    async def fake_send_qq_email_async(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(main, "send_qq_email_async", fake_send_qq_email_async)
    plugin = util.__new__(util)
    plugin.offline_email_alert_config = OfflineEmailAlertConfig(
        enabled=True,
        sender="sender@qq.com",
        QQ_password="auth-code",
        receiver="receiver@example.com",
    )
    event = SimpleNamespace(
        message_obj=SimpleNamespace(raw_message=OFFLINE_RAW_MESSAGE),
    )

    await plugin.notify_bot_offline_email(event)

    assert len(sent) == 1
    assert sent[0]["sender"] == "sender@qq.com"
    assert sent[0]["password"] == "auth-code"
    assert sent[0]["receiver"] == "receiver@example.com"
    assert sent[0]["subject"] == OFFLINE_EMAIL_SUBJECT
    assert "登录已失效" in sent[0]["content"]


@pytest.mark.asyncio
async def test_handler_skips_when_feature_disabled(monkeypatch):
    sent = []

    async def fake_send_qq_email_async(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr(main, "send_qq_email_async", fake_send_qq_email_async)
    plugin = util.__new__(util)
    plugin.offline_email_alert_config = OfflineEmailAlertConfig(
        enabled=False,
        sender="sender@qq.com",
        QQ_password="auth-code",
        receiver="receiver@example.com",
    )
    event = SimpleNamespace(
        message_obj=SimpleNamespace(raw_message=OFFLINE_RAW_MESSAGE),
    )

    await plugin.notify_bot_offline_email(event)

    assert sent == []
