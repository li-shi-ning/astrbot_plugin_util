from __future__ import annotations

import asyncio
import email
import imaplib
import smtplib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from email.header import decode_header, make_header
from email.header import Header
from email.mime.text import MIMEText
from email.message import Message
from typing import Any


OFFLINE_EMAIL_SUBJECT = "AstrBot bot account offline alert"
QQMAIL_TOOL_NAME = "qqmail"
QQMAIL_ACTIONS = {"status", "list", "read", "search", "send", "trash"}
QQ_IMAP_HOST = "imap.qq.com"
QQ_IMAP_PORT = 993
QQ_SMTP_HOST = "smtp.qq.com"
QQ_SMTP_PORT = 465


@dataclass(frozen=True)
class OfflineEmailAlertConfig:
    enabled: bool = False
    sender: str = ""
    QQ_password: str = ""
    receiver: str = ""

    @property
    def is_ready(self) -> bool:
        return bool(self.sender and self.QQ_password and self.receiver)

    @property
    def smtp_ready(self) -> bool:
        return bool(self.sender and self.QQ_password)


def build_offline_email_alert_config(
    section_config: Mapping[str, Any] | None,
) -> OfflineEmailAlertConfig:
    section_config = section_config or {}
    return OfflineEmailAlertConfig(
        enabled=bool(section_config.get("enable_offline_email_alert", False)),
        sender=str(section_config.get("sender", "")).strip(),
        QQ_password=str(section_config.get("QQ_password", "")).strip(),
        receiver=str(section_config.get("receiver", "")).strip(),
    )


@dataclass(frozen=True)
class QQMailToolConfig:
    enabled: bool = False
    sender: str = ""
    QQ_password: str = ""
    list_default_limit: int = 10

    @property
    def ready(self) -> bool:
        return bool(self.enabled and self.sender and self.QQ_password)


def build_qqmail_tool_config(
    section_config: Mapping[str, Any] | None,
) -> QQMailToolConfig:
    section_config = section_config or {}
    return QQMailToolConfig(
        enabled=bool(section_config.get("enable_qqmail_tool", False)),
        sender=str(section_config.get("sender", "")).strip(),
        QQ_password=str(section_config.get("QQ_password", "")).strip(),
        list_default_limit=_int_between(
            section_config.get("list_default_limit"),
            default=10,
            minimum=1,
            maximum=50,
        ),
    )


def _int_between(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def is_bot_offline_notice(raw_message: Any) -> bool:
    if not isinstance(raw_message, Mapping):
        return False

    if raw_message.get("post_type") != "notice":
        return False

    return raw_message.get("notice_type") == "bot_offline"


def format_offline_email_content(raw_message: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "AstrBot detected a bot account offline notice.",
            "",
            f"self_id: {raw_message.get('self_id', '')}",
            f"user_id: {raw_message.get('user_id', '')}",
            f"post_type: {raw_message.get('post_type', '')}",
            f"notice_type: {raw_message.get('notice_type', '')}",
            f"time: {raw_message.get('time', '')}",
            "",
            "Please check the AIOCQHTTP / NapCat login status as soon as possible.",
        ]
    )


def parse_email_addresses(values: list[str] | tuple[str, ...] | str | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        candidates = re.split(r"[,;\n]", values)
    else:
        candidates = [str(item) for item in values]
    return [item.strip() for item in candidates if item.strip()]


def send_qq_email(
    *,
    sender: str,
    password: str,
    receiver: str | list[str] | tuple[str, ...],
    subject: str,
    content: str,
    cc: str | list[str] | tuple[str, ...] = "",
    bcc: str | list[str] | tuple[str, ...] = "",
) -> None:
    to_addresses = parse_email_addresses(receiver)
    cc_addresses = parse_email_addresses(cc)
    bcc_addresses = parse_email_addresses(bcc)
    all_recipients = [*to_addresses, *cc_addresses, *bcc_addresses]
    if not all_recipients:
        raise ValueError("receiver is required")

    message = MIMEText(content, "plain", "utf-8")
    message["From"] = Header(sender)
    message["To"] = Header(", ".join(to_addresses))
    if cc_addresses:
        message["Cc"] = Header(", ".join(cc_addresses))
    message["Subject"] = Header(subject)

    with smtplib.SMTP_SSL(QQ_SMTP_HOST, QQ_SMTP_PORT) as smtp_obj:
        smtp_obj.login(sender, password)
        smtp_obj.sendmail(sender, all_recipients, message.as_string())


async def send_qq_email_async(
    *,
    sender: str,
    password: str,
    receiver: str | list[str] | tuple[str, ...],
    subject: str,
    content: str,
    cc: str | list[str] | tuple[str, ...] = "",
    bcc: str | list[str] | tuple[str, ...] = "",
) -> None:
    await asyncio.to_thread(
        send_qq_email,
        sender=sender,
        password=password,
        receiver=receiver,
        subject=subject,
        content=content,
        cc=cc,
        bcc=bcc,
    )


def decode_email_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def extract_plain_text(message: Message, *, max_chars: int = 6000) -> str:
    parts: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", "")).lower()
            if content_type != "text/plain" or "attachment" in disposition:
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            parts.append(payload.decode(charset, errors="replace"))
    else:
        payload = message.get_payload(decode=True)
        if payload is not None:
            charset = message.get_content_charset() or "utf-8"
            parts.append(payload.decode(charset, errors="replace"))

    text = "\n".join(part.strip() for part in parts if part.strip()).strip()
    if len(text) > max_chars:
        return text[:max_chars] + "\n...[已截断]"
    return text


def format_mail_header(uid: str, message: Message) -> str:
    subject = decode_email_header(message.get("Subject"))
    sender = decode_email_header(message.get("From"))
    date = decode_email_header(message.get("Date"))
    return "\n".join(
        [
            f"message_id: {uid}",
            f"from: {sender}",
            f"subject: {subject}",
            f"date: {date}",
        ]
    )


class QQMailClient:
    def __init__(self, *, sender: str, password: str):
        self.sender = sender
        self.password = password

    def _connect_imap(self) -> imaplib.IMAP4_SSL:
        client = imaplib.IMAP4_SSL(QQ_IMAP_HOST, QQ_IMAP_PORT)
        client.login(self.sender, self.password)
        return client

    def status(self) -> str:
        with self._connect_imap() as client:
            status, data = client.select("INBOX", readonly=True)
            if status != "OK":
                return "QQ邮箱状态检查失败：无法打开 INBOX。"
            count = data[0].decode("utf-8", errors="replace") if data else "0"
            return f"QQ邮箱 IMAP 登录成功。INBOX 邮件数量：{count}"

    def list_messages(self, limit: int) -> str:
        with self._connect_imap() as client:
            client.select("INBOX", readonly=True)
            status, data = client.uid("search", None, "ALL")
            if status != "OK" or not data:
                return "未找到邮件。"
            uids = data[0].split()
            selected_uids = list(reversed(uids[-max(1, min(limit, 50)) :]))
            lines: list[str] = []
            for uid_bytes in selected_uids:
                uid = uid_bytes.decode("ascii", errors="replace")
                status, fetched = client.uid(
                    "fetch",
                    uid,
                    "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])",
                )
                if status != "OK" or not fetched:
                    continue
                message = _message_from_fetch_response(fetched)
                if message is None:
                    continue
                lines.append(format_mail_header(uid, message))
            return "\n\n".join(lines) if lines else "未找到可读取的邮件。"

    def read_message(self, message_id: str, *, max_chars: int = 6000) -> str:
        message = self._fetch_message(message_id)
        if message is None:
            return f"未找到邮件：{message_id}"
        header = format_mail_header(message_id, message)
        body = extract_plain_text(message, max_chars=max_chars) or "<没有纯文本正文>"
        return f"{header}\n\nbody:\n{body}"

    def search_messages(self, query: str, limit: int) -> str:
        with self._connect_imap() as client:
            client.select("INBOX", readonly=True)
            escaped_query = query.replace("\\", "\\\\").replace('"', r"\"")
            status, data = client.uid("search", None, f'(TEXT "{escaped_query}")')
            if status != "OK" or not data or not data[0]:
                return "未搜索到匹配邮件。"
            uids = data[0].split()
            selected_uids = list(reversed(uids[-max(1, min(limit, 50)) :]))
            lines: list[str] = []
            for uid_bytes in selected_uids:
                uid = uid_bytes.decode("ascii", errors="replace")
                status, fetched = client.uid(
                    "fetch",
                    uid,
                    "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])",
                )
                if status != "OK" or not fetched:
                    continue
                message = _message_from_fetch_response(fetched)
                if message is None:
                    continue
                lines.append(format_mail_header(uid, message))
            return "\n\n".join(lines) if lines else "未搜索到可读取的匹配邮件。"

    def trash_message(self, message_id: str) -> str:
        with self._connect_imap() as client:
            client.select("INBOX", readonly=False)
            status, _ = client.uid("store", message_id, "+FLAGS", r"(\Deleted)")
            if status != "OK":
                return f"移动到废纸篓失败：{message_id}"
            client.expunge()
            return f"已移动到废纸篓：{message_id}"

    def _fetch_message(self, message_id: str) -> Message | None:
        with self._connect_imap() as client:
            client.select("INBOX", readonly=True)
            status, fetched = client.uid("fetch", message_id, "(RFC822)")
            if status != "OK" or not fetched:
                return None
            return _message_from_fetch_response(fetched)


def _message_from_fetch_response(fetched: list[Any]) -> Message | None:
    for item in fetched:
        if not isinstance(item, tuple) or len(item) < 2:
            continue
        payload = item[1]
        if isinstance(payload, bytes):
            return email.message_from_bytes(payload)
    return None


async def qqmail_status_async(*, sender: str, password: str) -> str:
    return await asyncio.to_thread(QQMailClient(sender=sender, password=password).status)


async def qqmail_list_async(*, sender: str, password: str, limit: int) -> str:
    return await asyncio.to_thread(
        QQMailClient(sender=sender, password=password).list_messages,
        limit,
    )


async def qqmail_read_async(
    *,
    sender: str,
    password: str,
    message_id: str,
) -> str:
    return await asyncio.to_thread(
        QQMailClient(sender=sender, password=password).read_message,
        message_id,
    )


async def qqmail_search_async(
    *,
    sender: str,
    password: str,
    query: str,
    limit: int,
) -> str:
    return await asyncio.to_thread(
        QQMailClient(sender=sender, password=password).search_messages,
        query,
        limit,
    )


async def qqmail_trash_async(
    *,
    sender: str,
    password: str,
    message_id: str,
) -> str:
    return await asyncio.to_thread(
        QQMailClient(sender=sender, password=password).trash_message,
        message_id,
    )
