from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

import astrbot.api.message_components as Comp
from astrbot.api import logger

GROUP_HISTORY_PREFIX = "群友史"
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


async def get_qq_nickname(qq_number: str) -> str:
    """Fetch a QQ nickname for forward nodes."""
    url = f"https://uapis.cn/api/v1/social/qq/userinfo?qq={qq_number}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                try:
                    data = await response.json()
                    logger.debug("[util] QQ昵称API返回: %s", data)
                    nickname = data.get("nickname")
                    if nickname:
                        return str(nickname)
                except Exception as exc:
                    logger.debug("[util] 解析昵称出错: %s", exc)
    return f"用户{qq_number}"


def is_group_history_request(message_text: str) -> bool:
    return message_text.startswith(GROUP_HISTORY_PREFIX)


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

                    if not prefix_skipped and GROUP_HISTORY_PREFIX in text:
                        prefix_pos = text.find(GROUP_HISTORY_PREFIX)
                        text = text[
                            prefix_pos + len(GROUP_HISTORY_PREFIX) :
                        ].lstrip()
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
    pattern = rf"{GROUP_HISTORY_PREFIX}((?:\s+\d+\s+[^|]+\|)+)"
    match = re.search(pattern, message_text)
    if not match:
        return None

    content = match.group(1).strip()
    return [
        {"text": segment.strip(), "images": []}
        for segment in content.split("|")
        if segment.strip()
    ]


async def build_group_history_nodes(
    segments: list[dict[str, Any]],
    nickname_resolver: Callable[[str], Awaitable[str]] = get_qq_nickname,
) -> list[Comp.Node]:
    nodes_list: list[Comp.Node] = []
    for segment in segments:
        text = segment["text"]
        images = segment["images"]

        match = re.match(r"^\s*(\d+)\s+(.*)", text)
        if not match:
            logger.debug("[util] 群友史段落格式错误，跳过: %s", text)
            continue

        qq_number, content = match.group(1), match.group(2).strip()
        nickname = await nickname_resolver(qq_number)
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
