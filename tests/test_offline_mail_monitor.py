from __future__ import annotations

import sys
from email.message import EmailMessage
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from core.offline_mail_monitor import (  # noqa: E402
    OfflineMailAlert,
    OfflineMailMonitorSettings,
    describe_offline_mail_monitor,
    fetch_new_offline_alerts,
    fetch_new_offline_alerts_with_stats,
    format_offline_mail_alert_message,
    get_current_max_uid,
    is_offline_alert_message,
    load_offline_mail_monitor_settings,
    load_offline_mail_state,
    save_offline_mail_state,
)

import main  # noqa: E402
from main import util  # noqa: E402


def make_settings(**overrides) -> OfflineMailMonitorSettings:
    values = {
        "name": "li-monitor",
        "enabled": True,
        "platform_id": "li",
        "message_type": "GroupMessage",
        "session_id": "10001",
        "imap_host": "imap.qq.com",
        "imap_port": 993,
        "imap_timeout_seconds": 20,
        "username": "bot@qq.com",
        "password": "auth-code",
        "folder": "INBOX",
        "interval_seconds": 60,
        "subject_keywords": ("AstrBot bot account offline alert",),
        "body_keywords": ("notice_type: bot_offline",),
        "max_fetch_count": 20,
        "message_template": (
            "Detected bot account offline alert email.\n"
            "Monitor: {monitor}\n"
            "Mailbox: {mailbox}\n"
            "UID: {uid}\n"
            "Subject: {subject}\n"
            "From: {from_addr}\n"
            "Date: {date}"
        ),
        "at_targets": (),
    }
    values.update(overrides)
    return OfflineMailMonitorSettings(**values)


def make_email(subject: str, body: str) -> bytes:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = "sender@example.com"
    message["Date"] = "Tue, 30 Jun 2026 09:00:00 +0800"
    message.set_content(body)
    return message.as_bytes()


def test_loads_multiple_offline_mail_monitor_settings():
    settings = load_offline_mail_monitor_settings(
        {
            "offline_mail_monitors": [
                {
                    "name": "li",
                    "platform_id": "li",
                    "message_type": "group",
                    "session_id": "10001",
                    "username": "li@qq.com",
                    "password": "code",
                    "interval_seconds": 1,
                    "imap_timeout_seconds": 2,
                    "message_template": "Alert {monitor} {uid} {session}",
                    "at_targets": ["12345", "all", ""],
                },
                {
                    "name": "ni",
                    "enabled": False,
                    "platform_id": "ni",
                    "message_type": "private",
                    "session_id": "20002",
                    "username": "ni@qq.com",
                    "password": "code",
                },
            ]
        }
    )

    assert len(settings) == 2
    assert settings[0].target_session == "li:GroupMessage:10001"
    assert settings[0].interval_seconds == 10
    assert settings[0].imap_timeout_seconds == 3
    assert settings[0].message_template == "Alert {monitor} {uid} {session}"
    assert settings[0].at_targets == ("12345", "all")
    assert settings[1].enabled is False
    assert settings[1].target_session == "ni:FriendMessage:20002"


def test_offline_mail_state_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    save_offline_mail_state(path, {"a": 1, "b": 2})

    assert load_offline_mail_state(path) == {"a": 1, "b": 2}


def test_detects_offline_alert_by_subject_or_body():
    assert is_offline_alert_message(
        subject="AstrBot bot account offline alert",
        body="anything",
    )
    assert is_offline_alert_message(
        subject="normal",
        body="notice_type: bot_offline",
    )
    assert not is_offline_alert_message(subject="normal", body="hello")


def test_fetch_new_offline_alerts_filters_messages(monkeypatch):
    emails = {
        1: make_email("old", "notice_type: bot_offline"),
        2: make_email("normal", "hello"),
        3: make_email("AstrBot bot account offline alert", "offline"),
    }

    class FakeIMAP:
        def __init__(self, host, port, timeout=None):
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def login(self, username, password):
            self.username = username
            self.password = password

        def select(self, folder, readonly=True):
            self.folder = folder
            return "OK", []

        def uid(self, command, *args):
            if command == "search":
                range_text = args[-1]
                start_uid = int(str(range_text).split("UID ")[1].split(":")[0])
                uids = [str(uid).encode() for uid in emails if uid >= start_uid]
                return "OK", [b" ".join(uids)]
            if command == "fetch":
                uid = int(args[0])
                return "OK", [(b"RFC822", emails[uid])]
            raise AssertionError(command)

    monkeypatch.setattr("core.offline_mail_monitor.imaplib.IMAP4_SSL", FakeIMAP)

    alerts, max_seen_uid = fetch_new_offline_alerts(make_settings(), last_uid=1)

    assert max_seen_uid == 3
    assert [alert.uid for alert in alerts] == [3]
    assert alerts[0].subject == "AstrBot bot account offline alert"


def test_fetch_new_offline_alerts_with_stats_reports_counts(monkeypatch):
    emails = {
        2: make_email("normal", "hello"),
        3: make_email("AstrBot bot account offline alert", "offline"),
    }

    class FakeIMAP:
        def __init__(self, host, port, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def login(self, username, password):
            pass

        def select(self, folder, readonly=True):
            return "OK", []

        def uid(self, command, *args):
            if command == "search":
                return "OK", [b"2 3"]
            if command == "fetch":
                return "OK", [(b"RFC822", emails[int(args[0])])]
            raise AssertionError(command)

    monkeypatch.setattr("core.offline_mail_monitor.imaplib.IMAP4_SSL", FakeIMAP)

    result = fetch_new_offline_alerts_with_stats(make_settings(), last_uid=1)

    assert result.max_seen_uid == 3
    assert result.searched_uids == (2, 3)
    assert result.new_mail_count == 2
    assert result.fetched_count == 2
    assert result.alert_count == 1


def test_describe_offline_mail_monitor_masks_mailbox_and_omits_password():
    description = describe_offline_mail_monitor(make_settings())

    assert "bo***t@qq.com" in description
    assert "auth-code" not in description
    assert "timeout=20s" in description
    assert "target=li:GroupMessage:10001" in description


def test_get_current_max_uid(monkeypatch):
    class FakeIMAP:
        def __init__(self, host, port, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def login(self, username, password):
            pass

        def select(self, folder, readonly=True):
            return "OK", []

        def uid(self, command, *args):
            return "OK", [b"1 4 9"]

    monkeypatch.setattr("core.offline_mail_monitor.imaplib.IMAP4_SSL", FakeIMAP)

    assert get_current_max_uid(make_settings()) == 9


def test_format_offline_mail_alert_message_contains_target_fields():
    alert = OfflineMailAlert(
        uid=9,
        subject="AstrBot bot account offline alert",
        from_addr="sender@example.com",
        date="2026-06-30T09:00:00+08:00",
        body_preview="preview",
    )

    text = format_offline_mail_alert_message(alert, make_settings())

    assert "Detected bot account offline alert email." in text
    assert "Monitor: li-monitor" in text
    assert "UID: 9" in text


def test_format_offline_mail_alert_message_uses_custom_template():
    alert = OfflineMailAlert(
        uid=9,
        subject="AstrBot bot account offline alert",
        from_addr="sender@example.com",
        date="2026-06-30T09:00:00+08:00",
        body_preview="preview text",
    )
    settings = make_settings(
        message_template=(
            "custom {monitor} {uid} {subject} {session} {body_preview}"
        )
    )

    text = format_offline_mail_alert_message(alert, settings)

    assert text == (
        "custom li-monitor 9 AstrBot bot account offline alert "
        "li:GroupMessage:10001 preview text"
    )


def test_build_offline_mail_alert_components_supports_at_targets():
    components = util._build_offline_mail_alert_components(
        "hello",
        ("12345", "all"),
    )

    assert len(components) == 3
    assert str(components[0].qq) == "12345"
    assert components[1].qq == "all"
    assert components[2].text == "\nhello"


@pytest.mark.asyncio
async def test_plugin_check_sends_proactive_message(monkeypatch):
    sent = []
    saved = []

    async def send_message(session, chain):
        sent.append((session, chain))
        return True

    def fake_fetch(settings, last_uid):
        alerts = [
            OfflineMailAlert(
                uid=6,
                subject="AstrBot bot account offline alert",
                from_addr="sender@example.com",
                date="2026-06-30T09:00:00+08:00",
                body_preview="preview",
            )
        ]
        return SimpleNamespace(
            alerts=alerts,
            max_seen_uid=6,
            searched_uids=(6,),
            fetched_count=1,
            new_mail_count=1,
            alert_count=1,
        )

    def fake_save(path, state):
        saved.append(dict(state))

    monkeypatch.setattr(main, "fetch_new_offline_alerts_with_stats", fake_fetch)
    monkeypatch.setattr(main, "save_offline_mail_state", fake_save)
    plugin = util.__new__(util)
    plugin.context = SimpleNamespace(send_message=send_message)
    settings = make_settings(message_template="Alert UID {uid}", at_targets=("12345",))
    plugin.offline_mail_monitor_state = {settings.key: 5}

    await plugin._check_offline_mail_monitor(settings)

    assert plugin.offline_mail_monitor_state[settings.key] == 6
    assert saved[-1][settings.key] == 6
    assert sent[0][0] == "li:GroupMessage:10001"
    assert str(sent[0][1].chain[0].qq) == "12345"
    assert sent[0][1].chain[1].text == "\nAlert UID 6"
