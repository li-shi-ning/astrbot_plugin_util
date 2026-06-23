from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class GroupKeywordVoice:
    enabled: bool
    keywords: tuple[str, ...]
    audio_directory: str

    def directory_for(self, message: str) -> str | None:
        if not self.enabled or not message or not self.audio_directory:
            return None

        normalized_message = message.casefold()
        if not any(keyword.casefold() in normalized_message for keyword in self.keywords):
            return None
        return self.audio_directory


def load_group_keyword_voices(
    config: Mapping[str, Any],
) -> dict[str, GroupKeywordVoice]:
    raw_rules = config.get("group_keyword_voices", [])
    if not isinstance(raw_rules, list):
        return {}

    rules: dict[str, GroupKeywordVoice] = {}
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, Mapping):
            continue

        group_id = str(raw_rule.get("group_id", "")).strip()
        if not group_id:
            continue

        rules[group_id] = GroupKeywordVoice(
            enabled=bool(raw_rule.get("enabled", True)),
            keywords=_clean_string_list(raw_rule.get("keywords", [])),
            audio_directory=str(raw_rule.get("audio_directory", "") or "").strip(),
        )
    return rules


def _clean_string_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(text for item in value if (text := str(item).strip()))
