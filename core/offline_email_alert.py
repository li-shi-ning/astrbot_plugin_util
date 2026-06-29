from __future__ import annotations

import asyncio
import smtplib
from collections.abc import Mapping
from dataclasses import dataclass
from email.header import Header
from email.mime.text import MIMEText
from typing import Any


OFFLINE_EMAIL_SUBJECT = "AstrBot QQ账号下线通知"


@dataclass(frozen=True)
class OfflineEmailAlertConfig:
    enabled: bool = False
    sender: str = ""
    QQ_password: str = ""
    receiver: str = ""

    @property
    def is_ready(self) -> bool:
        return bool(self.sender and self.QQ_password and self.receiver)


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


def is_bot_offline_notice(raw_message: Any) -> bool:
    if not isinstance(raw_message, Mapping):
        return False

    if raw_message.get("post_type") != "notice":
        return False

    return raw_message.get("notice_type") == "bot_offline"


def format_offline_email_content(raw_message: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "AstrBot 检测到 QQ 账号下线通知。",
            "",
            f"self_id: {raw_message.get('self_id', '')}",
            f"user_id: {raw_message.get('user_id', '')}",
            f"tag: {raw_message.get('tag', '')}",
            f"message: {raw_message.get('message', '')}",
            f"time: {raw_message.get('time', '')}",
            "",
            "请尽快检查 AIOCQHTTP / NapCat 登录状态。",
        ]
    )


def send_qq_email(
    *,
    sender: str,
    password: str,
    receiver: str,
    subject: str,
    content: str,
) -> None:
    message = MIMEText(content, "plain", "utf-8")
    message["From"] = Header(sender)
    message["To"] = Header(receiver)
    message["Subject"] = Header(subject)

    with smtplib.SMTP_SSL("smtp.qq.com", 465) as smtp_obj:
        smtp_obj.login(sender, password)
        smtp_obj.sendmail(sender, receiver, message.as_string())


async def send_qq_email_async(
    *,
    sender: str,
    password: str,
    receiver: str,
    subject: str,
    content: str,
) -> None:
    await asyncio.to_thread(
        send_qq_email,
        sender=sender,
        password=password,
        receiver=receiver,
        subject=subject,
        content=content,
    )
