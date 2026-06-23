from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GroupKeywordReply:
    enabled: bool
    keywords: tuple[str, ...]
    reply_lines: tuple[str, ...]

    def response_for(self, message: str) -> str | None:
        if not self.enabled or not message or not self.reply_lines:
            return None

        normalized_message = message.casefold()
        if not any(keyword.casefold() in normalized_message for keyword in self.keywords):
            return None
        return "\n".join(self.reply_lines)


def load_group_keyword_replies(
    config: Mapping[str, Any],
) -> dict[str, GroupKeywordReply]:
    raw_rules = config.get("group_keyword_replies", [])
    if not isinstance(raw_rules, list):
        return {}

    rules: dict[str, GroupKeywordReply] = {}
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, Mapping):
            continue

        group_id = str(raw_rule.get("group_id", "")).strip()
        if not group_id:
            continue

        rules[group_id] = GroupKeywordReply(
            enabled=bool(raw_rule.get("enabled", True)),
            keywords=_clean_string_list(raw_rule.get("keywords", [])),
            reply_lines=_clean_string_list(raw_rule.get("reply_lines", [])),
        )
    return rules


def _clean_string_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(text for item in value if (text := str(item).strip()))
