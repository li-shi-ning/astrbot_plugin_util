from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class GroupHistoryProfile:
    user_id: str
    nickname: str


HISTORY_EVENT_TEMPLATES = (
    "{name}路过群门口时，被群公告上的逗号绊了一跤，从此发明了先看三遍再发言的古训。",
    "{name}曾在深夜宣布要早睡，三分钟后又补了一句“最后看一眼”，史称最后亿眼之乱。",
    "{name}把一句“在吗”发出了千军万马的气势，群友沉默，机器人也假装断网。",
    "{name}曾试图用一个表情包解决所有问题，结果表情包太强，问题自己退群了。",
    "{name}在群里留下过一句高深莫测的话，后来没人看懂，但大家一致认为很有道理。",
    "{name}曾经打字打到一半突然消失，群史学家推测其被输入法召回修炼。",
    "{name}有一次精准踩中冷场中心，从此群里的空气都会主动给TA让路。",
    "{name}曾凭借一句随口吐槽，让群聊从平静水面变成大型考古现场。",
)

HISTORY_COMMENT_TEMPLATES = (
    "史官锐评：此人看似普通，实则每一句话都可能成为群聊遗址。",
    "史官锐评：证据不足，但味儿很对，建议列入群史观察对象。",
    "史官锐评：此事不可细究，细究就会变成新的史。",
    "史官锐评：今日一抽，抽中的不是人，是命运的褶皱。",
)


def normalize_group_history_members(raw_members: Any) -> tuple[GroupHistoryProfile, ...]:
    """Convert OneBot-style member payloads into stable history profiles."""
    if not isinstance(raw_members, list):
        return ()

    profiles: list[GroupHistoryProfile] = []
    seen: set[str] = set()
    for member in raw_members:
        if not isinstance(member, dict):
            continue
        user_id = str(member.get("user_id") or "").strip()
        if not user_id or not user_id.isdigit() or user_id in seen:
            continue
        nickname = _member_display_name(member, user_id)
        profiles.append(GroupHistoryProfile(user_id=user_id, nickname=nickname))
        seen.add(user_id)
    return tuple(profiles)


def filter_group_history_candidates(
    profiles: tuple[GroupHistoryProfile, ...],
    excluded_user_ids: set[str],
) -> tuple[GroupHistoryProfile, ...]:
    candidates = tuple(
        profile for profile in profiles if profile.user_id not in excluded_user_ids
    )
    return candidates or profiles


def select_daily_group_history_profile(
    profiles: tuple[GroupHistoryProfile, ...],
    group_id: str,
    today: date,
) -> GroupHistoryProfile | None:
    if not profiles:
        return None
    ordered_profiles = sorted(profiles, key=lambda profile: profile.user_id)
    rng = random.Random(_stable_seed("member", group_id, today.isoformat()))
    return ordered_profiles[rng.randrange(len(ordered_profiles))]


def build_daily_group_history_entries(
    profile: GroupHistoryProfile,
    group_id: str,
    today: date,
) -> tuple[str, ...]:
    rng = random.Random(
        _stable_seed("history", group_id, today.isoformat(), profile.user_id)
    )
    events = rng.sample(HISTORY_EVENT_TEMPLATES, k=3)
    comment = rng.choice(HISTORY_COMMENT_TEMPLATES)
    rendered_events = [
        template.format(name=profile.nickname) for template in events
    ]
    return (
        f"《{today.isoformat()} 群友史》",
        f"今日被命运翻牌：{profile.nickname}（{profile.user_id}）",
        f"起因：{rendered_events[0]}",
        f"经过：{rendered_events[1]}",
        f"结果：{rendered_events[2]}",
        comment,
    )


def _member_display_name(member: dict[str, Any], user_id: str) -> str:
    for key in ("card", "nickname", "name"):
        value = str(member.get(key) or "").strip()
        if value:
            return value
    return f"群友{user_id}"


def _stable_seed(*parts: str) -> int:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:16], 16)
