from __future__ import annotations

import imaplib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from email import message_from_bytes
from email.header import decode_header
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any


DEFAULT_OFFLINE_MAIL_SUBJECT_KEYWORDS = ("AstrBot bot account offline alert",)
DEFAULT_OFFLINE_MAIL_BODY_KEYWORDS = (
    "bot account offline notice",
    "notice_type: bot_offline",
)


@dataclass(frozen=True)
class OfflineMailMonitorSettings:
    name: str
    enabled: bool
    platform_id: str
    message_type: str
    session_id: str
    imap_host: str
    imap_port: int
    username: str
    password: str
    folder: str
    interval_seconds: int
    subject_keywords: tuple[str, ...]
    body_keywords: tuple[str, ...]
    max_fetch_count: int

    @property
    def key(self) -> str:
        raw_key = self.name or (
            f"{self.username}:{self.folder}:"
            f"{self.platform_id}:{self.message_type}:{self.session_id}"
        )
        return re.sub(r"[^A-Za-z0-9_.:@-]+", "_", raw_key).strip("_")

    @property
    def is_ready(self) -> bool:
        return bool(
            self.platform_id
            and self.message_type
            and self.session_id
            and self.imap_host
            and self.username
            and self.password
        )

    @property
    def target_session(self) -> str:
        return f"{self.platform_id}:{self.message_type}:{self.session_id}"


@dataclass(frozen=True)
class OfflineMailAlert:
    uid: int
    subject: str
    from_addr: str
    date: str
    body_preview: str


def load_offline_mail_monitor_settings(config: Mapping[str, Any]) -> list[OfflineMailMonitorSettings]:
    raw_items = config.get("offline_mail_monitors", [])
    if not isinstance(raw_items, list):
        return []

    settings: list[OfflineMailMonitorSettings] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, Mapping):
            continue
        settings.append(_build_settings(item, index))
    return settings


def _build_settings(item: Mapping[str, Any], index: int) -> OfflineMailMonitorSettings:
    subject_keywords = _string_tuple(
        item.get("subject_keywords"),
        DEFAULT_OFFLINE_MAIL_SUBJECT_KEYWORDS,
    )
    body_keywords = _string_tuple(
        item.get("body_keywords"),
        DEFAULT_OFFLINE_MAIL_BODY_KEYWORDS,
    )
    return OfflineMailMonitorSettings(
        name=str(item.get("name", "")).strip() or f"offline-mail-monitor-{index}",
        enabled=bool(item.get("enabled", True)),
        platform_id=str(item.get("platform_id", "")).strip(),
        message_type=_normalize_message_type(item.get("message_type")),
        session_id=str(item.get("session_id", "")).strip(),
        imap_host=str(item.get("imap_host", "imap.qq.com")).strip() or "imap.qq.com",
        imap_port=_bounded_int(item.get("imap_port", 993), 1, 65535, 993),
        username=str(item.get("username", "")).strip(),
        password=str(item.get("password", "")).strip(),
        folder=str(item.get("folder", "INBOX")).strip() or "INBOX",
        interval_seconds=_bounded_int(item.get("interval_seconds", 60), 10, 86400, 60),
        subject_keywords=subject_keywords,
        body_keywords=body_keywords,
        max_fetch_count=_bounded_int(item.get("max_fetch_count", 20), 1, 200, 20),
    )


def _normalize_message_type(value: Any) -> str:
    raw_value = str(value or "GroupMessage").strip()
    lowered = raw_value.lower()
    if lowered in {"group", "groupmessage", "群聊"}:
        return "GroupMessage"
    if lowered in {"private", "privatemessage", "friend", "friendmessage", "私聊"}:
        return "FriendMessage"
    return raw_value


def _bounded_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _string_tuple(value: Any, default: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(value, list):
        return tuple(default)
    return tuple(str(item).strip() for item in value if str(item).strip())


def load_offline_mail_state(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    try:
        raw_state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw_state, Mapping):
        return {}
    state: dict[str, int] = {}
    for key, value in raw_state.items():
        try:
            state[str(key)] = max(0, int(value))
        except (TypeError, ValueError):
            continue
    return state


def save_offline_mail_state(path: Path, state: Mapping[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(state), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def get_current_max_uid(settings: OfflineMailMonitorSettings) -> int:
    with _login(settings) as mailbox:
        _select_folder(mailbox, settings.folder)
        _, data = mailbox.uid("search", None, "ALL")
        return _max_uid_from_search_data(data)


def fetch_new_offline_alerts(
    settings: OfflineMailMonitorSettings,
    last_uid: int,
) -> tuple[list[OfflineMailAlert], int]:
    with _login(settings) as mailbox:
        _select_folder(mailbox, settings.folder)
        _, data = mailbox.uid("search", None, f"UID {last_uid + 1}:*")
        uids = _uids_from_search_data(data)
        if not uids:
            return [], last_uid

        uids = uids[-settings.max_fetch_count :]
        alerts: list[OfflineMailAlert] = []
        max_seen_uid = max(last_uid, max(uids))
        for uid in uids:
            status, fetch_data = mailbox.uid("fetch", str(uid), "(RFC822)")
            if status != "OK":
                continue
            raw_email = _raw_email_from_fetch_data(fetch_data)
            if raw_email is None:
                continue
            message = message_from_bytes(raw_email)
            alert = _alert_from_message(uid, message, settings)
            if alert is not None:
                alerts.append(alert)
        return alerts, max_seen_uid


def is_offline_alert_message(
    *,
    subject: str,
    body: str,
    subject_keywords: Sequence[str] = DEFAULT_OFFLINE_MAIL_SUBJECT_KEYWORDS,
    body_keywords: Sequence[str] = DEFAULT_OFFLINE_MAIL_BODY_KEYWORDS,
) -> bool:
    normalized_subject = subject.lower()
    normalized_body = body.lower()
    return any(keyword.lower() in normalized_subject for keyword in subject_keywords) or any(
        keyword.lower() in normalized_body for keyword in body_keywords
    )


def format_offline_mail_alert_message(alert: OfflineMailAlert, settings: OfflineMailMonitorSettings) -> str:
    return (
        "Detected bot account offline alert email.\n"
        f"Monitor: {settings.name}\n"
        f"Mailbox: {settings.username}\n"
        f"UID: {alert.uid}\n"
        f"Subject: {alert.subject or '(no subject)'}\n"
        f"From: {alert.from_addr or '(unknown)'}\n"
        f"Date: {alert.date or '(unknown)'}"
    )


def _login(settings: OfflineMailMonitorSettings) -> imaplib.IMAP4_SSL:
    mailbox = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
    mailbox.login(settings.username, settings.password)
    return mailbox


def _select_folder(mailbox: imaplib.IMAP4_SSL, folder: str) -> None:
    status, _ = mailbox.select(folder, readonly=True)
    if status != "OK":
        raise RuntimeError(f"failed to select mailbox folder: {folder}")


def _uids_from_search_data(data: list[bytes] | tuple[bytes, ...]) -> list[int]:
    if not data:
        return []
    raw_uids = data[0]
    if not raw_uids:
        return []
    return [int(uid) for uid in raw_uids.split() if uid.isdigit()]


def _max_uid_from_search_data(data: list[bytes] | tuple[bytes, ...]) -> int:
    uids = _uids_from_search_data(data)
    return max(uids) if uids else 0


def _raw_email_from_fetch_data(fetch_data: list[Any] | tuple[Any, ...]) -> bytes | None:
    for item in fetch_data:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
            return item[1]
    return None


def _alert_from_message(
    uid: int,
    message: Message,
    settings: OfflineMailMonitorSettings,
) -> OfflineMailAlert | None:
    subject = _decode_mime_header(message.get("Subject", ""))
    body = _extract_text_body(message)
    if not is_offline_alert_message(
        subject=subject,
        body=body,
        subject_keywords=settings.subject_keywords,
        body_keywords=settings.body_keywords,
    ):
        return None

    return OfflineMailAlert(
        uid=uid,
        subject=subject,
        from_addr=_decode_mime_header(message.get("From", "")),
        date=_normalize_date(message.get("Date", "")),
        body_preview=_collapse_preview(body),
    )


def _decode_mime_header(value: str) -> str:
    parts: list[str] = []
    for payload, charset in decode_header(value):
        if isinstance(payload, bytes):
            parts.append(payload.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(payload)
    return "".join(parts).strip()


def _extract_text_body(message: Message) -> str:
    if message.is_multipart():
        parts: list[str] = []
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_content_type() != "text/plain":
                continue
            parts.append(_decode_part_payload(part))
        return "\n".join(parts)
    return _decode_part_payload(message)


def _decode_part_payload(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        raw_payload = part.get_payload()
        return raw_payload if isinstance(raw_payload, str) else ""
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def _normalize_date(value: str) -> str:
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError, IndexError):
        return value


def _collapse_preview(value: str, limit: int = 200) -> str:
    collapsed = " ".join(value.split())
    return collapsed[:limit]
