from __future__ import annotations

import argparse
import re
import smtplib
import ssl
from datetime import datetime
from email.header import Header
from email.mime.text import MIMEText
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PLUGIN_ROOT / "cs" / "QQ_mailbox" / "text.yaml"
OFFLINE_ALERT_SUBJECT = "AstrBot bot account offline alert"


def read_simple_yaml(path: Path) -> dict[str, str]:
    config: dict[str, str] = {}
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$", line)
        if not match:
            continue
        key, value = match.groups()
        config[key] = value.strip().strip("'").strip('"')
    return config


def mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    if not domain:
        return "***"
    if len(name) <= 2:
        return f"{name[:1]}***@{domain}"
    return f"{name[:2]}***{name[-1:]}@{domain}"


def send_email(
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
    message["Subject"] = Header(subject, "utf-8")

    with smtplib.SMTP_SSL(
        "smtp.qq.com",
        465,
        timeout=30,
        context=ssl.create_default_context(),
    ) as smtp:
        smtp.login(sender, password)
        smtp.sendmail(sender, receiver, message.as_string())


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a QQ SMTP test email.")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Config file path. Default: cs/QQ_mailbox/text.yaml",
    )
    parser.add_argument(
        "--subject",
        default="AstrBot util email test",
        help="Email subject.",
    )
    parser.add_argument(
        "--content",
        default="",
        help="Email body. If empty, a default English body is used.",
    )
    parser.add_argument(
        "--offline-alert",
        action="store_true",
        help="Send an email that matches offline_mail_monitors default keywords.",
    )
    args = parser.parse_args()

    config_path = Path(args.config).expanduser().resolve()
    config = read_simple_yaml(config_path)
    sender = config.get("sender", "").strip()
    password = config.get("QQ_password", "").strip()
    receiver = config.get("receiver", "").strip()
    missing = [
        name
        for name, value in (
            ("sender", sender),
            ("QQ_password", password),
            ("receiver", receiver),
        )
        if not value
    ]
    if missing:
        raise SystemExit(f"Missing required config field(s): {', '.join(missing)}")

    subject = args.subject
    if args.offline_alert and subject == "AstrBot util email test":
        subject = OFFLINE_ALERT_SUBJECT

    content = args.content
    if not content and args.offline_alert:
        content = (
            "AstrBot detected a bot account offline notice.\n\n"
            "self_id: test-bot\n"
            "user_id: test-bot\n"
            "post_type: notice\n"
            "notice_type: bot_offline\n"
            f"time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            "Please check the AIOCQHTTP / NapCat login status as soon as possible."
        )
    elif not content:
        content = (
            "This is an AstrBot util email test.\n\n"
            f"Sent at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            "If you receive this message, the QQ SMTP configuration is working."
        )
    send_email(
        sender=sender,
        password=password,
        receiver=receiver,
        subject=subject,
        content=content,
    )
    mode = "offline-alert" if args.offline_alert else "normal"
    print(f"sent ok [{mode}]: {mask_email(sender)} -> {mask_email(receiver)}")


if __name__ == "__main__":
    main()
