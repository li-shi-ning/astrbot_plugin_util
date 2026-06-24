from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

import astrbot.api.message_components as Comp
from astrbot.api import logger

GROUP_HISTORY_HELP_COMMAND = "群友史帮助"
GROUP_HISTORY_FORMAT_ERROR = (
    "格式错误，请使用：群友史 QQ号 内容 | QQ号 内容 | ..."
)
GROUP_HISTORY_EMPTY_ERROR = "未能解析出任何有效的消息节点"
GROUP_HISTORY_HELP_TEXT = """📱 群友史聊天记录构造说明 📱

【基本格式】
群友史 QQ号 消息内容 | QQ号 消息内容 | ...

【带图片的格式】
- 在任意消息段中添加图片，图片将只出现在它所在的消息段
- 例如: 群友史 123456 看我的照片[图片] | 654321 好漂亮啊
- 在这个例子中，图片只会出现在第一个人的消息中

【注意事项】
- 每个消息段之间用"|"分隔
- 每个消息段的格式必须是"QQ号 消息内容"
- 图片会根据它在消息中的位置分配到对应的消息段
"""


async def get_qq_nickname(event: Any, qq: str) -> str | None:
    """Fetch a QQ nickname from the active platform bot."""
    bot = getattr(event, "bot", None)
    if bot is None:
        return None

    payloads = {
        "user_id": int(qq),
        "no_cache": True,
    }
    try:
        qq_info = await bot.api.call_action("get_stranger_info", **payloads)
    except Exception as exc:
        logger.debug("[util] 获取QQ昵称失败: %s", exc)
        return None
    if not isinstance(qq_info, dict):
        return None
    return qq_info.get("nick", None)


def parse_group_history_components(message_obj: Any) -> list[dict[str, Any]]:
    """Parse message components and attach images to their text segment."""
    segments: list[dict[str, Any]] = []
    current_segment: dict[str, Any] = {"text": "", "images": []}
    segment_started = False

    try:
        prefix_skipped = False

        if hasattr(message_obj, "message"):
            for comp in message_obj.message:
                if isinstance(comp, Comp.Plain):
                    text = comp.text

                    if not prefix_skipped and "群友史" in text:
                        prefix_pos = text.find("群友史")
                        text = text[prefix_pos + len("群友史") :].lstrip()
                        prefix_skipped = True

                    if "|" in text:
                        parts = text.split("|")

                        current_segment["text"] += parts[0]
                        segment_started = True

                        if current_segment["text"].strip():
                            segments.append(current_segment)

                        for index in range(1, len(parts) - 1):
                            segments.append({"text": parts[index], "images": []})

                        if len(parts) > 1:
                            current_segment = {"text": parts[-1], "images": []}
                            segment_started = True
                    else:
                        current_segment["text"] += text
                        segment_started = True

                elif isinstance(comp, Comp.Image) and hasattr(comp, "url") and comp.url:
                    if segment_started:
                        current_segment["images"].append(comp.url)
                        logger.debug("[util] 将图片 %s 添加到当前段落", comp.url)

            if current_segment["text"].strip():
                segments.append(current_segment)

        logger.debug("[util] 群友史解析完成，共有 %s 个段落", len(segments))
    except Exception as exc:
        logger.error("[util] 解析群友史组件出错: %s", exc)
        segments = []

    return segments


def parse_group_history_text(message_text: str) -> list[dict[str, Any]] | None:
    content = message_text.strip()
    if content.startswith("群友史"):
        content = content[len("群友史") :].strip()

    if not content:
        return None

    segments = [
        {"text": segment.strip(), "images": []}
        for segment in content.split("|")
        if segment.strip()
    ]
    if not any(re.match(r"^\s*\d+\s+.*", segment["text"]) for segment in segments):
        return None
    return segments


async def build_group_history_nodes(
    segments: list[dict[str, Any]],
    event: Any,
    nickname_resolver: Callable[[Any, str], Awaitable[str | None]] = get_qq_nickname,
) -> list[Comp.Node]:
    parsed_segments: list[tuple[str, str, list[str]]] = []
    qq_numbers: list[str] = []
    seen_qq_numbers: set[str] = set()

    for segment in segments:
        text = segment["text"]
        match = re.match(r"^\s*(\d+)\s+(.*)", text)
        if not match:
            logger.debug("[util] 群友史段落格式错误，跳过: %s", text)
            continue

        qq_number, content = match.group(1), match.group(2).strip()
        parsed_segments.append((qq_number, content, segment["images"]))
        if qq_number not in seen_qq_numbers:
            seen_qq_numbers.add(qq_number)
            qq_numbers.append(qq_number)

    nicknames: dict[str, str] = {}
    for qq_number in qq_numbers:
        nickname = await nickname_resolver(event, qq_number)
        nicknames[qq_number] = nickname or "QQ用户"

    nodes_list: list[Comp.Node] = []
    for qq_number, content, images in parsed_segments:
        nickname = nicknames[qq_number]
        node_content = [Comp.Plain(content)]

        for img_url in images:
            try:
                node_content.append(Comp.Image.fromURL(img_url))
                logger.debug("[util] 为QQ %s 添加图片: %s", qq_number, img_url)
            except Exception as exc:
                logger.debug("[util] 添加图片到群友史节点失败: %s", exc)

        nodes_list.append(
            Comp.Node(
                uin=int(qq_number),
                name=nickname,
                content=node_content,
            )
        )

    return nodes_list
