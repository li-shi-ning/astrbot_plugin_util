from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import aiohttp


OFFLINE_WEBHOOK_EVENT = "bot_offline"
SIGNATURE_HEADER = "X-AstrBot-Util-Signature"
TIMESTAMP_HEADER = "X-AstrBot-Util-Timestamp"
DEFAULT_WEBHOOK_PATH = "/astrbot-util/offline"
DEFAULT_WEBHOOK_MESSAGE_TEMPLATE = (
    "Detected bot account offline alert.\n"
    "Bot: {self_id}\n"
    "User: {user_id}\n"
    "Platform: {platform}\n"
    "Message: {message}"
)


@dataclass(frozen=True)
class OfflineWebhookSenderSettings:
    name: str
    enabled: bool
    webhook_url: str
    secret: str
    timeout_seconds: int
    retry_count: int

    @property
    def is_ready(self) -> bool:
        return bool(self.webhook_url and self.secret)


@dataclass(frozen=True)
class OfflineWebhookReceiverServerSettings:
    enabled: bool
    listen_host: str
    listen_port: int
    path: str


@dataclass(frozen=True)
class OfflineWebhookReceiveRule:
    name: str
    enabled: bool
    secret: str
    platform_id: str
    message_type: str
    session_id: str
    message_template: str
    at_targets: tuple[str, ...]

    @property
    def is_ready(self) -> bool:
        return bool(self.secret and self.platform_id and self.message_type and self.session_id)

    @property
    def target_session(self) -> str:
        return f"{self.platform_id}:{self.message_type}:{self.session_id}"


def load_offline_webhook_senders(config: Mapping[str, Any]) -> list[OfflineWebhookSenderSettings]:
    raw_items = config.get("offline_webhook_senders", [])
    if not isinstance(raw_items, list):
        return []
    return [
        _build_sender_settings(item, index)
        for index, item in enumerate(raw_items, start=1)
        if isinstance(item, Mapping)
    ]


def load_offline_webhook_receiver_server(
    config: Mapping[str, Any],
) -> OfflineWebhookReceiverServerSettings:
    section = config.get("offline_webhook_receiver", {})
    if not isinstance(section, Mapping):
        section = {}
    path = str(section.get("path", DEFAULT_WEBHOOK_PATH)).strip() or DEFAULT_WEBHOOK_PATH
    if not path.startswith("/"):
        path = f"/{path}"
    return OfflineWebhookReceiverServerSettings(
        enabled=bool(section.get("enable_offline_webhook_receiver", False)),
        listen_host=str(section.get("listen_host", "127.0.0.1")).strip() or "127.0.0.1",
        listen_port=_bounded_int(section.get("listen_port", 8765), 1, 65535, 8765),
        path=path,
    )


def load_offline_webhook_receive_rules(config: Mapping[str, Any]) -> list[OfflineWebhookReceiveRule]:
    raw_items = config.get("offline_webhook_receive_rules", [])
    if not isinstance(raw_items, list):
        return []
    return [
        _build_receive_rule(item, index)
        for index, item in enumerate(raw_items, start=1)
        if isinstance(item, Mapping)
    ]


def build_offline_webhook_payload(raw_message: Mapping[str, Any]) -> dict[str, Any]:
    timestamp = int(time.time())
    return {
        "event": OFFLINE_WEBHOOK_EVENT,
        "self_id": str(raw_message.get("self_id", "")),
        "user_id": str(raw_message.get("user_id", "")),
        "platform": "aiocqhttp",
        "message": str(raw_message.get("message", "")),
        "notice_type": str(raw_message.get("notice_type", "")),
        "post_type": str(raw_message.get("post_type", "")),
        "source_time": raw_message.get("time", ""),
        "timestamp": timestamp,
    }


def encode_webhook_payload(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sign_webhook_body(secret: str, body: bytes, timestamp: str) -> str:
    message = timestamp.encode("utf-8") + b"." + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def build_webhook_headers(secret: str, body: bytes, timestamp: str | None = None) -> dict[str, str]:
    timestamp = timestamp or str(int(time.time()))
    return {
        "Content-Type": "application/json; charset=utf-8",
        TIMESTAMP_HEADER: timestamp,
        SIGNATURE_HEADER: sign_webhook_body(secret, body, timestamp),
    }


def verify_webhook_signature(
    *,
    secret: str,
    body: bytes,
    timestamp: str,
    signature: str,
    max_skew_seconds: int = 300,
) -> bool:
    if not secret or not timestamp or not signature:
        return False
    try:
        parsed_timestamp = int(timestamp)
    except ValueError:
        return False
    if max_skew_seconds > 0 and abs(int(time.time()) - parsed_timestamp) > max_skew_seconds:
        return False
    expected = sign_webhook_body(secret, body, timestamp)
    return hmac.compare_digest(expected, signature)


def parse_webhook_payload(body: bytes) -> dict[str, Any]:
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("webhook payload must be a JSON object")
    return payload


def format_offline_webhook_message(
    payload: Mapping[str, Any],
    rule: OfflineWebhookReceiveRule,
) -> str:
    values = {
        "event": str(payload.get("event", "")),
        "self_id": str(payload.get("self_id", "")),
        "user_id": str(payload.get("user_id", "")),
        "platform": str(payload.get("platform", "")),
        "message": str(payload.get("message", "")),
        "notice_type": str(payload.get("notice_type", "")),
        "post_type": str(payload.get("post_type", "")),
        "source_time": str(payload.get("source_time", "")),
        "timestamp": str(payload.get("timestamp", "")),
        "rule": rule.name,
        "session": rule.target_session,
    }
    try:
        return rule.message_template.format(**values)
    except (KeyError, IndexError, ValueError):
        return DEFAULT_WEBHOOK_MESSAGE_TEMPLATE.format(**values)


async def send_offline_webhook(
    settings: OfflineWebhookSenderSettings,
    payload: Mapping[str, Any],
) -> None:
    body = encode_webhook_payload(payload)
    headers = build_webhook_headers(settings.secret, body)
    timeout = aiohttp.ClientTimeout(total=settings.timeout_seconds)
    attempts = max(1, settings.retry_count + 1)
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(settings.webhook_url, data=body, headers=headers) as response:
                    response.raise_for_status()
                    await response.text()
                    return
        except Exception as exc:  # pragma: no cover - retry path is covered via caller tests.
            last_error = exc
    if last_error is not None:
        raise last_error


def _build_sender_settings(
    item: Mapping[str, Any],
    index: int,
) -> OfflineWebhookSenderSettings:
    return OfflineWebhookSenderSettings(
        name=str(item.get("name", "")).strip() or f"offline-webhook-sender-{index}",
        enabled=bool(item.get("enabled", True)),
        webhook_url=str(item.get("webhook_url", "")).strip(),
        secret=str(item.get("secret", "")).strip(),
        timeout_seconds=_bounded_int(item.get("timeout_seconds", 10), 1, 120, 10),
        retry_count=_bounded_int(item.get("retry_count", 2), 0, 10, 2),
    )


def _build_receive_rule(
    item: Mapping[str, Any],
    index: int,
) -> OfflineWebhookReceiveRule:
    return OfflineWebhookReceiveRule(
        name=str(item.get("name", "")).strip() or f"offline-webhook-rule-{index}",
        enabled=bool(item.get("enabled", True)),
        secret=str(item.get("secret", "")).strip(),
        platform_id=str(item.get("platform_id", "")).strip(),
        message_type=_normalize_message_type(item.get("message_type")),
        session_id=str(item.get("session_id", "")).strip(),
        message_template=str(
            item.get("message_template", DEFAULT_WEBHOOK_MESSAGE_TEMPLATE)
            or DEFAULT_WEBHOOK_MESSAGE_TEMPLATE
        ),
        at_targets=_string_tuple(item.get("at_targets"), ()),
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
