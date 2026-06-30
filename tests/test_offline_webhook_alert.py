from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from core.offline_webhook_alert import (  # noqa: E402
    OFFLINE_WEBHOOK_EVENT,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    OfflineWebhookReceiveRule,
    build_offline_webhook_payload,
    build_webhook_headers,
    encode_webhook_payload,
    load_offline_webhook_receive_rules,
    load_offline_webhook_receiver_server,
    load_offline_webhook_senders,
    verify_webhook_signature,
)

import main  # noqa: E402
from main import util  # noqa: E402


OFFLINE_RAW_MESSAGE = {
    "time": 1782688326,
    "self_id": 3513785608,
    "post_type": "notice",
    "notice_type": "bot_offline",
    "user_id": 3513785608,
    "message": "login expired",
}


def test_loads_offline_webhook_sender_and_receiver_config():
    config = {
        "offline_webhook_senders": [
            {
                "name": "to-ni",
                "webhook_url": " http://127.0.0.1:8765/astrbot-util/offline ",
                "secret": " shared ",
                "timeout_seconds": 0,
                "retry_count": 20,
            }
        ],
        "offline_webhook_receiver": {
            "enable_offline_webhook_receiver": True,
            "listen_host": "0.0.0.0",
            "listen_port": 8765,
            "path": "astrbot-util/offline",
        },
        "offline_webhook_receive_rules": [
            {
                "name": "group",
                "secret": "shared",
                "platform_id": "ni",
                "message_type": "group",
                "session_id": "10001",
                "message_template": "Bot {self_id} offline",
                "at_targets": ["12345", "all", ""],
            }
        ],
    }

    senders = load_offline_webhook_senders(config)
    server = load_offline_webhook_receiver_server(config)
    rules = load_offline_webhook_receive_rules(config)

    assert senders[0].name == "to-ni"
    assert senders[0].webhook_url == "http://127.0.0.1:8765/astrbot-util/offline"
    assert senders[0].timeout_seconds == 1
    assert senders[0].retry_count == 10
    assert server.enabled is True
    assert server.path == "/astrbot-util/offline"
    assert rules[0].target_session == "ni:GroupMessage:10001"
    assert rules[0].at_targets == ("12345", "all")


def test_webhook_signature_roundtrip():
    payload = build_offline_webhook_payload(OFFLINE_RAW_MESSAGE)
    body = encode_webhook_payload(payload)
    timestamp = str(int(time.time()))
    headers = build_webhook_headers("secret", body, timestamp)

    assert verify_webhook_signature(
        secret="secret",
        body=body,
        timestamp=headers[TIMESTAMP_HEADER],
        signature=headers[SIGNATURE_HEADER],
    )
    assert not verify_webhook_signature(
        secret="wrong",
        body=body,
        timestamp=headers[TIMESTAMP_HEADER],
        signature=headers[SIGNATURE_HEADER],
    )


@pytest.mark.asyncio
async def test_handler_pushes_offline_webhooks(monkeypatch):
    pushed = []

    async def fake_send_offline_webhook(sender, payload):
        pushed.append((sender, payload))

    monkeypatch.setattr(main, "send_offline_webhook", fake_send_offline_webhook)
    plugin = util.__new__(util)
    plugin.offline_email_alert_config = SimpleNamespace(enabled=False)
    plugin.offline_webhook_senders = load_offline_webhook_senders(
        {
            "offline_webhook_senders": [
                {
                    "name": "to-ni",
                    "webhook_url": "http://127.0.0.1:8765/astrbot-util/offline",
                    "secret": "shared",
                }
            ]
        }
    )
    event = SimpleNamespace(
        message_obj=SimpleNamespace(raw_message=OFFLINE_RAW_MESSAGE),
    )

    await plugin.notify_bot_offline_email(event)

    assert len(pushed) == 1
    assert pushed[0][0].name == "to-ni"
    assert pushed[0][1]["event"] == OFFLINE_WEBHOOK_EVENT
    assert pushed[0][1]["self_id"] == "3513785608"


@pytest.mark.asyncio
async def test_receiver_accepts_signed_webhook_and_sends_message():
    sent = []

    async def send_message(session, chain):
        sent.append((session, chain))
        return True

    rule = OfflineWebhookReceiveRule(
        name="group",
        enabled=True,
        secret="shared",
        platform_id="ni",
        message_type="GroupMessage",
        session_id="10001",
        message_template="Bot {self_id} offline: {message}",
        at_targets=("12345",),
    )
    plugin = util.__new__(util)
    plugin.context = SimpleNamespace(send_message=send_message)
    plugin.offline_webhook_receive_rules = [rule]
    payload = build_offline_webhook_payload(OFFLINE_RAW_MESSAGE)
    body = encode_webhook_payload(payload)
    headers = build_webhook_headers("shared", body, str(int(time.time())))

    async def read():
        return body

    response = await plugin._handle_offline_webhook_request(
        SimpleNamespace(read=read, headers=headers)
    )

    assert response.status == 200
    assert json.loads(response.text)["sent"] == 1
    assert sent[0][0] == "ni:GroupMessage:10001"
    assert str(sent[0][1].chain[0].qq) == "12345"
    assert sent[0][1].chain[1].text == "\nBot 3513785608 offline: login expired"
