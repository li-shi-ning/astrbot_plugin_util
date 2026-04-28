# ====== 核心模块 ======
import asyncio
import json
import random
import re
import traceback

import aiohttp

# ====== 第三方库 ======
import numpy as np

import astrbot.api.message_components as Comp
from astrbot.api import logger

# ====== API 模块 ======
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, register
from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import EventType, star_handlers_registry

# ====== 核心库 ======
from .core.Filter import register_pack_type


@register("util", "lishinig", "私人插件", "1.0.0")
class util(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)

        self.config = config
        self.is_debug = False
        self.poke_responses = np.array(
            [
                # 正常态
                "别碰我。保持距离。",
                "想引起我的注意，就开口。",
                "如果有事，直接说。",
                "别用这种方式交流。",
                "我在听。你可以说了。",
                "先说明目的。",
                # 轻微不耐烦
                "（微微后退）这种举动不合适。",
                "你太轻率了。收敛一点。",
                "我会继续引导你，但别再碰我。",
                "（整理衣襟）距离感也是秩序的一部分。",
                "少用动作试探。用话说清楚。",
                "如果你很迷茫，就直接问。别乱碰。",
                # 高压态
                "手拿开。现在。",
                "先想清楚你在做什么。",
                "这种行为只会让场面更混乱。",
                "别让我重复。停止这种动作。",
                "你的判断有问题。立刻修正。",
                "再碰一次，我会默认你在挑衅。",
                "先停下。然后解释你的目的。",
                # 保留项
                "喵~",
                "哈!",
                "pack",
            ]
        )

        self.poke_weights = np.array(
            [
                # 正常态
                7.5,
                7.0,
                6.8,
                7.2,
                6.5,
                7.0,
                # 轻微不耐烦
                8.8,
                9.2,
                8.0,
                8.3,
                7.8,
                7.2,
                # 高压态
                8.5,
                8.8,
                8.6,
                9.0,
                9.2,
                8.4,
                8.7,
                # 保留项
                5.0,  # 喵
                6.0,  # 哈气
                10.0,  # 反弹
            ]
        )

        self.emotions_mapping = {
            "开心": [2, 74, 109, 272, 295, 305, 318, 319, 324, 339],
            "得意": [
                4,
                16,
                28,
                29,
                99,
                101,
                178,
                269,
                270,
                277,
                283,
                299,
                307,
                336,
                426,
            ],
            "害羞": [6, 20, 21],
            "难过": [5, 34, 35, 36, 37, 173, 264, 265, 267, 425],
            "纠结": [106, 176, 262, 263, 270],
            "生气": [11, 26, 31, 105],
            "惊讶": [3, 325],
            "疑惑": [32, 268],
            "恳求": [111, 353],
            "可怕": [1, 286],
            "尴尬": [100, 306, 342, 344, 347],
            "无语": [46, 97, 181, 271, 281, 284, 287, 312, 352, 357, 427],
            "恶心": [19, 59, 323],
            "无聊": [8, 25, 285, 293],
        }

        self.tts_id = {
            "ema": "486bd7ee-a273-4e3d-a02a-e0dfc880cbe2",
            "hiro": "a9a59749-1904-4136-a409-5e4aea7d4e0d",
        }
        self.no_split_keywords = ("zssm", "这是什么", "hyw", "何意味")

        self.enable_history_message_chunking = config.get(
            "enable_history_message_chunking",
            True,
        )
        self.history_message_chunk_length = max(
            1,
            int(config.get("history_message_chunk_length", 100)),
        )
        self.enable_history_read_tool = config.get("enable_history_read_tool", True)
        self.history_read_tool_default_count = max(
            1,
            int(config.get("history_read_tool_default_count", 6)),
        )
        self.enable_human_like_stream_delay = config.get(
            "enable_human_like_stream_delay",
            True,
        )
        self.enable_llm_request_debug_log = config.get(
            "enable_llm_request_debug_log",
            False,
        )
        self.enable_final_history_log = config.get("enable_final_history_log", False)
        self._scoped_request_history_cache: dict[str, list[str]] = {}
        self.stream_delay_min_seconds = max(
            0.0,
            float(config.get("stream_delay_min_seconds", 0.35)),
        )
        self.stream_delay_max_seconds = max(
            self.stream_delay_min_seconds,
            float(config.get("stream_delay_max_seconds", 1.2)),
        )

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @register_pack_type()
    async def poke(self, event: AiocqhttpMessageEvent):
        """对戳一戳事件进行响应"""
        raw_message = getattr(event.message_obj, "raw_message", None)
        bot_id = raw_message.get("self_id", None)
        sender_id = raw_message.get("user_id", None)
        target_id = raw_message.get("target_id", None)
        group_id = raw_message.get("group_id", None)
        if (
            not bot_id
            or not sender_id
            or not target_id
            or str(target_id) != str(bot_id)
        ):
            return
        text = await self.weighted_random_choice(self.poke_responses, self.poke_weights)
        logger.info(f"检测到戳一戳，期望发送文本:{text}")
        if text == "pack":
            payloads = {"user_id": sender_id}
            if group_id:
                payloads["group_id"] = group_id
            bot = getattr(event, "bot", None)
            if bot is None:
                text = await self.weighted_random_choice(
                    self.poke_responses[:-1], self.poke_weights[:-1]
                )
                logger.info(f"机器人不是AIOCQHTTP，期望发送文本:{text}")
                yield event.plain_result(text)
            else:
                await bot.api.call_action("send_poke", **payloads)
        else:
            yield event.plain_result(text)

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    async def replyMessage(self, event: AiocqhttpMessageEvent):
        """获取所有消息，进行贴表情"""
        raw_message = getattr(event.message_obj, "raw_message", None)
        message_id = raw_message.get("message_id", None)
        text = raw_message.get("raw_message", None)
        if not text or not message_id:
            return
        bot = getattr(event, "bot", None)
        if bot is None:
            return
        emoji_id = await self.get_emoji_id(text)
        if emoji_id is None:
            return
        payloads = {"message_id": message_id, "emoji_id": emoji_id}
        await bot.api.call_action("set_msg_emoji_like", **payloads)

    @filter.command_group("lishi")
    async def lishi(self):
        pass

    @lishi.command("ah")
    async def get_all_handler(self, event: AstrMessageEvent):
        """获取所有处理器的详细信息"""
        output_text = []
        event_output_text = []

        # 遍历所有消息事件处理器
        for handler in star_handlers_registry.get_handlers_by_event_type(
            EventType.AdapterMessageEvent,
            plugins_name=None,  # None表示获取所有插件，不进行过滤
        ):
            # 创建一个字典来存储所有属性
            handler_info = {}
            handler_info_by_event = {}

            # 1. 事件类型
            handler_info["event_type"] = getattr(handler, "event_type", None)
            # 2. 处理器完整名称（格式：模块名_函数名）
            handler_info["handler_full_name"] = getattr(
                handler, "handler_full_name", None
            )
            handler_info_by_event["handler_full_name"] = getattr(
                handler, "handler_full_name", None
            )
            # 3. 处理器名称（函数名）
            handler_info["handler_name"] = getattr(handler, "handler_name", None)
            # 4. 处理器模块路径
            handler_info["handler_module_path"] = getattr(
                handler, "handler_module_path", None
            )
            handler_info_by_event["handler_module_path"] = getattr(
                handler, "handler_module_path", None
            )
            # 5. 处理器描述信息
            handler_info["desc"] = getattr(handler, "desc", "")
            # 6. 处理器是否启用
            handler_info["enabled"] = getattr(handler, "enabled", True)
            # 7. 额外配置（如优先级等）
            handler_info["extras_configs"] = getattr(handler, "extras_configs", {})
            # 8. 事件过滤器列表
            event_filters = getattr(handler, "event_filters", [])
            handler_info["event_filters_count"] = len(event_filters)
            handler_info["event_filters"] = []

            output_text.append(str(handler_info))
            event_output_text.append(str(handler_info_by_event))
        logger.info("\n".join(output_text))
        yield event.plain_result("\n".join(event_output_text))

    @lishi.command("hibmp")
    async def get_handler_by_mp(
        self, event: AstrMessageEvent, handler_module_path: str
    ):
        """根据插件路径获取所有插件"""
        if handler_module_path is None:
            yield event.plain_result("找不到")
            return
        plugin_info = {}
        if handler_module_path in star_map:
            plugin = star_map[handler_module_path]
            plugin_info = {
                "plugin_name": getattr(plugin, "name", "unknown"),
                "plugin_desc": getattr(plugin, "desc", ""),
                "plugin_version": getattr(plugin, "version", ""),
                "plugin_author": getattr(plugin, "author", ""),
            }
        yield event.plain_result(str(plugin_info))

    @lishi.command("hibfn")
    async def get_handler_by_fn(self, event: AstrMessageEvent, full_name: str):
        """根据插件方法完整路径获取所有插件"""
        handler = star_handlers_registry.get_handler_by_full_name(full_name)
        handler_module_path = getattr(handler, "handler_module_path", None)
        if handler_module_path is None:
            yield event.plain_result("找不到")
            return
        plugin_info = {}
        if handler_module_path in star_map:
            plugin = star_map[handler_module_path]
            plugin_info = {
                "plugin_name": getattr(plugin, "name", "unknown"),
                "plugin_desc": getattr(plugin, "desc", ""),
                "plugin_version": getattr(plugin, "version", ""),
                "plugin_author": getattr(plugin, "author", ""),
            }
        yield event.plain_result(str(plugin_info))

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @lishi.command("kh")
    async def get_qq_info(self, event: AiocqhttpMessageEvent, qq: str):
        """获取一个陌生qq账号信息"""
        bot = getattr(event, "bot", None)
        if bot is None:
            return

        if not self._validate_qq(qq):
            yield event.plain_result("QQ号格式错误，请使用纯数字")
            return

        payloads = {"user_id": int(qq), "no_cache": True}
        qq_info = await bot.api.call_action("get_stranger_info", **payloads)
        nick = qq_info["nick"]
        yield event.plain_result(f"该用户的名称为:{nick}")

    @lishi.command("ch")
    async def get_chat_history(self, event: AstrMessageEvent):
        """获取当前会话的历史信息"""
        unified_msg_origin = event.unified_msg_origin
        conversation_id = (
            await self.context.conversation_manager.get_curr_conversation_id(
                unified_msg_origin
            )
        )
        conv = await self.context.conversation_manager.get_conversation(
            unified_msg_origin=unified_msg_origin,
            conversation_id=conversation_id,
        )
        if conv:
            history = json.loads(conv.history) if conv.history else []

            output_text = ""
            output_text += f"对话标题: {conv.platform_id}\n"
            output_text += f"对话创建时间: {conv.created_at}\n"
            output_text += f"对话历史长度: {len(history)}"
            yield event.plain_result(output_text)

            logger.info(f"对话标题: {conv.platform_id}")
            logger.info(f"对话创建时间: {conv.created_at}")
            # logger.info(f"历史记录:{json.dumps(history, indent=4, ensure_ascii=False)}")
        else:
            print("对话不存在")

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @lishi.command("chb")
    async def get_chat_history_by_bot(self, event: AiocqhttpMessageEvent):
        """通过onebot接口获取聊天历史"""
        group_id = event.get_group_id()
        sender_id = event.get_sender_id()
        is_group = group_id is not None
        bot = getattr(event, "bot", None)
        if bot is None:
            return
        if is_group:
            logger.info("[util] 进行获取群消息历史")
            """
            获取群消息历史记录
            终结点：/get_group_msg_history

            参数
            字段	类型	说明
            message_seq	int64	起始消息序号, 可通过 get_msg 获得
            group_id	int64	群号

            响应数据
            字段	类型	说明
            messages	Message[]	从起始序号开始的前19条消息
            """
            payloads = {"group_id": group_id}
            output_text = json.dumps(
                await bot.api.call_action("get_group_msg_history", **payloads),
                indent=4,
                ensure_ascii=False,
            )
            logger.info(output_text)
            yield event.plain_result("已获取，打印到日志")
        else:
            logger.info("[util] 进行获取私聊消息历史")
            """
            get_friend_msg_history - 获取私聊历史记录 normal

            参数
            字段名	数据类型	默认值	说明
            user_id	string	-	QQ 号
            message_seq	string	'0'	起始信息
            count	number	20	数量
            reverseOrder	boolean	false	倒序

            响应数据
            字段名	数据类型	说明
            messages	message[]	消息数组,参考 onebot11
            """
            payloads = {"user_id": sender_id}
            output_text = json.dumps(
                await bot.api.call_action("get_friend_msg_history", **payloads),
                indent=4,
                ensure_ascii=False,
            )
            logger.info(output_text)
            yield event.plain_result("已获取，打印到日志")

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @lishi.command("chbf")
    async def get_chat_history_by_bot_by_sender_id(
        self, event: AiocqhttpMessageEvent, sender_id: str
    ):
        """通过qq号获取消息"""
        if not self._validate_qq(sender_id):
            yield event.plain_result("请输入正确的id")
            return
        bot = getattr(event, "bot", None)
        if bot is None:
            return
        payloads = {"user_id": sender_id}
        output_text = json.dumps(
            await bot.api.call_action("get_friend_msg_history", **payloads),
            indent=4,
            ensure_ascii=False,
        )
        logger.info(output_text)
        yield event.plain_result("已获取，打印到日志")

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @lishi.command("chbg")
    async def get_chat_history_by_bot_by_group_id(
        self, event: AiocqhttpMessageEvent, group_id: str
    ):
        """通过群聊号获取消息"""
        if not self._validate_qq(group_id):
            yield event.plain_result("请输入正确的id")
            return
        bot = getattr(event, "bot", None)
        if bot is None:
            return
        payloads = {"group_id": group_id}
        output_text = json.dumps(
            await bot.api.call_action("get_group_msg_history", **payloads),
            indent=4,
            ensure_ascii=False,
        )
        logger.info(output_text)
        yield event.plain_result("已获取，打印到日志")

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @lishi.command("chbgpn")
    async def get_chat_history_by_bot_process(
        self, event: AiocqhttpMessageEvent, group_id: str, count: int
    ):
        """通过群聊号获取消息并处理"""
        if not self._validate_qq(group_id):
            yield event.plain_result("请输入正确的id")
            return
        bot = getattr(event, "bot", None)
        if bot is None:
            return
        outpur_text, message_id = await self.get_message(group_id, bot, count)
        yield event.plain_result(f"{count}条聊天记录已获取")
        logger.info(f"{count}条聊天记录已获取\n" + "\n---\n".join(outpur_text))

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @lishi.command("setd")
    async def set_debug(self, event: AiocqhttpMessageEvent, set_bool: int):
        """是否开启debug"""
        self.is_debug = set_bool == 1
        yield event.plain_result(f"设置debug:{self.is_debug}")

    @lishi.command("gin")
    async def get_info_number(
        self, event: AiocqhttpMessageEvent, qq: str, group_id: str | None = None
    ):
        """获取一个群聊qq账号信息"""
        if group_id is None:
            group_id = event.get_group_id()
            if group_id is None:
                yield event.plain_result("请在群聊里面使用，或输入group_id")
                return
        else:
            group_id = str(group_id)
            group_id = group_id.strip()

        if not self._validate_qq(qq):
            yield event.plain_result("请输入正确的qq")
            return

        if not self._validate_qq(group_id):
            logger.debug(f"[util] 群组ID:{group_id}")
            yield event.plain_result("请输入正确的group_id")
            return

        bot = getattr(event, "bot", None)
        if bot is None:
            return

        if not self._validate_qq(qq):
            yield event.plain_result("QQ号格式错误，请使用纯数字")
            return

        payloads = {"group_id": int(group_id), "user_id": int(qq), "no_cache": True}
        qq_info = await bot.api.call_action("get_group_member_info", **payloads)
        logger.info(json.dumps(qq_info, indent=2, ensure_ascii=False))
        yield event.plain_result(json.dumps(qq_info))

    # 自建tts服务
    @filter.command("t2s")
    async def use_tts(self, event: AiocqhttpMessageEvent):
        logger.debug(f"[utrl] event.message_str:{event.message_str}")
        guess_text = self.extract_and_sanitize_input(event.message_str, "t2s")
        logger.debug(f"[utrl] guess_text:{guess_text}")
        payload = {
            "text": guess_text,
            "reference_id": self.tts_id["hiro"],
            "language": "Japanese",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://tts.lishining.top/generate",
                    json=payload,
                    timeout=600,
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
        except Exception as e:
            logger.error(f"[utrl] e:{e}")
            logger.error(traceback.format_exc())
            logger.error(f"[utrl] payload:{payload}")
            data = {}
        audio_url = data.get("audio_url", None)
        if audio_url is None:
            yield event.plain_result("服务器错误,请稍后再试")
            logger.error(f"[util] 发送失败,data:{data}")
            return
        chain = [
            Comp.Record.fromURL(str(audio_url)),
        ]
        yield event.chain_result(chain)

    @filter.command("et2s")
    async def use_etts(self, event: AiocqhttpMessageEvent):
        logger.debug(f"[utrl] event.message_str:{event.message_str}")
        guess_text = self.extract_and_sanitize_input(event.message_str, "t2s")
        logger.debug(f"[utrl] guess_text:{guess_text}")
        payload = {
            "text": guess_text,
            "reference_id": self.tts_id["ema"],
            "language": "Japanese",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://tts.lishining.top/generate",
                    json=payload,
                    timeout=600,
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
        except Exception as e:
            logger.error(f"[utrl] e:{e}")
            logger.error(traceback.format_exc())
            logger.error(f"[utrl] payload:{payload}")
            data = {}
        audio_url = data.get("audio_url", None)
        if audio_url is None:
            yield event.plain_result("服务器错误,请稍后再试")
            logger.error(f"[util] 发送失败,data:{data}")
            return
        chain = [
            Comp.Record.fromURL(str(audio_url)),
        ]
        yield event.chain_result(chain)

    @filter.on_llm_request(priority=-5000)
    async def apply_history_tool_config(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
    ):
        original_entries = self._build_current_request_history(req.contexts)
        has_chunked_history = self._current_request_has_chunked_history(
            original_entries
        )
        req.contexts = self._rewrite_request_contexts(
            req.contexts,
            add_history_tool_hint=self.enable_history_read_tool and has_chunked_history,
        )
        scoped_entries = self._build_current_request_history(req.contexts)
        self._scoped_request_history_cache[self._request_scope_cache_key(event)] = (
            scoped_entries
        )

    @filter.on_llm_request(priority=-10000)
    async def log_final_llm_request(
        self, event: AstrMessageEvent, req: ProviderRequest
    ):
        """Log the final ProviderRequest before sending it to the model."""
        if not self.enable_final_history_log and not self.enable_llm_request_debug_log:
            return

        if self.enable_final_history_log:
            logger.info(
                "[util] final model input history:\n"
                f"{self._json_dumps_for_log(req.contexts)}"
            )

        if self.enable_llm_request_debug_log:
            metadata = self._provider_request_metadata_without_prompts(req)
            logger.info(
                "[util] final ProviderRequest metadata without prompts:\n"
                f"{self._json_dumps_for_log(metadata)}"
            )

    @filter.llm_tool(name="read_current_history")
    async def read_current_history(
        self,
        event: AstrMessageEvent,
        count: int = 6,
        page: int = 1,
    ):
        """Read the current session's conversation history in a human-readable format.

        Args:
            count(int): Number of history entries to read from the selected page.
            page(int): Page number of the current session history. Starts from 1.
        """
        if not self.enable_history_read_tool:
            return "The history reading tool is disabled by configuration."

        count = max(1, count or self.history_read_tool_default_count)
        page = max(1, page or 1)
        contexts = self._scoped_request_history_cache.get(
            self._request_scope_cache_key(event),
            [],
        )
        if not contexts:
            return "No current-request history is available for this session."

        total_pages = max((len(contexts) + count - 1) // count, 1)
        start = (page - 1) * count
        end = start + count
        page_contexts = contexts[start:end]
        if not page_contexts:
            return "The requested page is out of range for the current request."

        lines = [
            "scope: current_request_only",
            f"page: {page}/{max(total_pages, 1)}",
            f"entries: {len(page_contexts)}",
            "",
        ]
        lines.extend(self._format_history_entries(page_contexts))
        return "\n".join(lines)

    @filter.on_decorating_result()
    async def split_llm_result_before_send(self, event: AstrMessageEvent):
        """在发送消息前分段发送 LLM 结果，避免阻断历史保存。"""
        result = event.get_result()
        if not result or not result.chain or not result.is_model_result():
            return

        if self._should_skip_llm_split(event.message_str):
            if self.is_debug:
                logger.info(
                    f"[util] 命中免切割关键词，跳过输出切割: {event.message_str}"
                )
            return

        if not all(isinstance(comp, Comp.Plain) for comp in result.chain):
            if self.is_debug:
                logger.info("[util] LLM结果包含非文本消息段，跳过输出切割")
            return

        text = "".join(comp.text for comp in result.chain)
        if self.is_debug:
            logger.info(f"[util] 原始LLM响应:\n{text}")

        output_lines = self._smart_split_text(text)
        if len(output_lines) <= 1:
            return

        if self.is_debug:
            logger.info(
                f"[util] 智能分割完成，行数={len(output_lines)}, 行内容={json.dumps(output_lines, ensure_ascii=False)}"
            )
        for line in output_lines:
            if self.is_debug:
                logger.info(f"[util] 发送分割后的行: {line}")
            await event.send(event.plain_result(line))
            await self._sleep_like_human_chat(line)
        event.clear_result()

    def _provider_request_metadata_without_prompts(
        self,
        req: ProviderRequest,
    ) -> dict:
        tool_names = None
        if req.func_tool and hasattr(req.func_tool, "names"):
            try:
                tool_names = req.func_tool.names()
            except Exception:
                tool_names = str(req.func_tool)

        return {
            "session_id": getattr(req, "session_id", None),
            "model": getattr(req, "model", None),
            "image_urls": getattr(req, "image_urls", None),
            "audio_urls": getattr(req, "audio_urls", None),
            "extra_user_content_parts": getattr(
                req,
                "extra_user_content_parts",
                None,
            ),
            "func_tool_names": tool_names,
            "conversation_id": (
                getattr(req.conversation, "cid", None)
                if getattr(req, "conversation", None)
                else None
            ),
            "tool_calls_result": getattr(req, "tool_calls_result", None),
        }

    def _json_dumps_for_log(self, value) -> str:
        return json.dumps(
            self._make_json_safe(value),
            indent=2,
            ensure_ascii=False,
        )

    def _make_json_safe(self, value):
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(key): self._make_json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._make_json_safe(item) for item in value]
        if hasattr(value, "model_dump"):
            return self._make_json_safe(value.model_dump())
        if hasattr(value, "__dict__"):
            return self._make_json_safe(vars(value))
        return str(value)

    async def get_message(self, group_id, bot, count):
        payloads = {"group_id": group_id, "count": count}
        data = await bot.api.call_action("get_group_msg_history", **payloads)
        outpur_text = []
        logger.info(
            f"[util] 处理:\n{json.dumps(data['messages'], indent=4, ensure_ascii=False)}"
        )
        for message in data["messages"]:
            for message_data in message["message"]:
                if message_data["type"] == "text":
                    try:
                        outpur_text.extend(
                            self._chunk_history_message(message_data["data"]["text"])
                        )
                    except (KeyError, TypeError):
                        pass
        message_id = data["messages"][0]["message_id"]
        return outpur_text, message_id

    def _chunk_history_message(self, text: str) -> list[str]:
        if not text:
            return [""]
        if not self.enable_history_message_chunking:
            return [text]
        if len(text) <= self.history_message_chunk_length:
            return [text]
        return [
            text[i : i + self.history_message_chunk_length]
            for i in range(0, len(text), self.history_message_chunk_length)
        ]

    def _format_history_entries(self, entries: list[str]) -> list[str]:
        formatted_entries: list[str] = []
        for entry_index, entry in enumerate(entries, start=1):
            chunks = self._chunk_history_message(entry)
            if len(chunks) == 1:
                formatted_entries.append(f"[{entry_index}] {chunks[0]}")
                continue
            for chunk_index, chunk in enumerate(chunks, start=1):
                formatted_entries.append(f"[{entry_index}.{chunk_index}] {chunk}")
        return formatted_entries

    def _current_request_has_chunked_history(self, entries: list[str]) -> bool:
        if not self.enable_history_message_chunking:
            return False

        for entry in entries:
            if len(self._chunk_history_message(entry)) > 1:
                return True
        return False

    def _request_scope_cache_key(self, event: AstrMessageEvent) -> str:
        return str(event.unified_msg_origin)

    def _chunked_history_tool_hint(self) -> str:
        return (
            "[历史消息切割提示]\n"
            "本轮请求中有较长的历史消息已被分段切割。"
            "如果你需要确认被切割前后的上下文，可以主动调用 read_current_history 工具读取当前请求中的历史片段。"
            "该工具只返回本轮 req.contexts 中已有的内容，不会额外读取或引入其他记忆。"
        )

    def _rewrite_request_contexts(
        self,
        contexts: list,
        add_history_tool_hint: bool = False,
    ):
        if not isinstance(contexts, list):
            return contexts

        rewritten_contexts = []
        hint_added = False
        for context in contexts:
            if not isinstance(context, dict):
                rewritten_contexts.append(context)
                continue

            rewritten_context = dict(context)
            rewritten_content, added_hint = self._rewrite_context_content(
                context.get("content"),
                add_history_tool_hint and not hint_added,
            )
            rewritten_context["content"] = rewritten_content
            hint_added = hint_added or added_hint
            rewritten_contexts.append(rewritten_context)

        return rewritten_contexts

    def _rewrite_context_content(
        self,
        content,
        add_history_tool_hint: bool = False,
    ):
        if isinstance(content, str):
            chunks = self._chunk_history_message(content)
            if len(chunks) == 1:
                return content, False
            if add_history_tool_hint:
                chunks.append(self._chunked_history_tool_hint())
                return "\n".join(chunks), True
            return "\n".join(chunks), False

        if not isinstance(content, list):
            return content, False

        rewritten_content = []
        hint_added = False
        for item in content:
            if not isinstance(item, dict):
                rewritten_content.append(item)
                continue

            item_type = item.get("type")
            if item_type != "text":
                rewritten_content.append(dict(item))
                continue

            text = item.get("text")
            if not isinstance(text, str):
                rewritten_content.append(dict(item))
                continue

            chunks = self._chunk_history_message(text)
            if len(chunks) == 1:
                rewritten_content.append(dict(item))
                continue

            for chunk in chunks:
                rewritten_item = dict(item)
                rewritten_item["text"] = chunk
                rewritten_content.append(rewritten_item)

            if add_history_tool_hint and not hint_added:
                hint_item = dict(item)
                hint_item["text"] = self._chunked_history_tool_hint()
                rewritten_content.append(hint_item)
                hint_added = True

        return rewritten_content, hint_added

    def _build_current_request_history(self, contexts: list) -> list[str]:
        if not isinstance(contexts, list):
            return []

        entries: list[str] = []
        for context in contexts:
            if not isinstance(context, dict):
                continue
            content = context.get("content")
            if isinstance(content, str):
                if content.strip():
                    entries.append(content)
                continue
            if not isinstance(content, list):
                continue
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") != "text":
                    continue
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    entries.append(text)
        return entries

    def _smart_split_text(self, text: str) -> list[str]:
        """清理LLM输出并将其分割成自然行"""
        cleaned_text = self._strip_llm_markdown(text)
        if self.is_debug:
            logger.info(f"[util] 清理后的文本:\n{cleaned_text}")
        if not cleaned_text:
            if self.is_debug:
                logger.info("[util] 清理后的文本为空，跳过发送")
            return []

        lines: list[str] = []
        buffer: list[str] = []
        bracket_stack: list[str] = []
        quote_stack: list[str] = []
        opening_brackets = {
            "[": "]",
            "(": ")",
            "\uff08": "\uff09",
            "\u3010": "\u3011",
            "\u300c": "\u300d",
            "{": "}",
            "\u300a": "\u300b",
            "<": ">",
        }
        opening_quotes = {
            '"': '"',
            "\u201c": "\u201d",
            "\u2018": "\u2019",
            "\uff02": "\uff02",
        }
        closing_quotes = set(opening_quotes.values())
        split_punctuation = {
            "\u3002",
            "\uff01",
            "\uff1f",
            "\uff1b",
            "!",
            "?",
            ";",
            "\u2026",
        }

        for char in cleaned_text:
            closed_quote = False
            if quote_stack:
                if char == quote_stack[-1]:
                    quote_stack.pop()
                    closed_quote = True
            elif char in opening_quotes:
                quote_stack.append(opening_quotes[char])
            elif char in opening_brackets:
                bracket_stack.append(opening_brackets[char])
            elif bracket_stack and char == bracket_stack[-1]:
                bracket_stack.pop()

            buffer.append(char)
            candidate = "".join(buffer).strip()
            should_split_after_quote = (
                closed_quote
                and len(candidate) >= 2
                and candidate[-1] in closing_quotes
                and candidate[-2] in split_punctuation
            )
            if (
                not bracket_stack
                and not quote_stack
                and (char in split_punctuation or should_split_after_quote)
            ):
                if candidate:
                    lines.append(candidate)
                buffer = []

        tail = "".join(buffer).strip()
        if tail:
            lines.append(tail)

        if self.is_debug:
            logger.info(
                f"[util] 规范化前分割，行数={len(lines)}, 行内容={json.dumps(lines, ensure_ascii=False)}"
            )

        return self._normalize_output_lines(lines)

    async def _sleep_like_human_chat(self, text: str) -> None:
        if not self.enable_human_like_stream_delay:
            return
        if not text:
            return

        base_delay = random.uniform(
            self.stream_delay_min_seconds,
            self.stream_delay_max_seconds,
        )
        length_bonus = min(len(text) / 120.0, 0.9)
        punctuation_bonus = 0.0
        if any(char in text for char in "。！？!?；;"):
            punctuation_bonus += 0.12
        if any(char in text for char in "…~"):
            punctuation_bonus += 0.08

        delay_seconds = min(base_delay + length_bonus + punctuation_bonus, 2.8)
        if self.is_debug:
            logger.info(
                f"[util] 模拟真人聊天间隔: delay={delay_seconds:.2f}s, text={text}"
            )
        await asyncio.sleep(delay_seconds)

    def _strip_llm_markdown(self, text: str) -> str:
        """从LLM输出中移除常见的markdown包装，同时保留可读文本"""
        if not text:
            if self.is_debug:
                logger.info("[util] 在markdown清理前收到空文本")
            return ""

        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        text = re.sub(r"```(?:\w+)?\n?", "", text)
        text = text.replace("```", "")
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"(?m)^\s*(?:---+|\*\*\*+|___+)\s*$", "", text)
        text = re.sub(r"(?<!\*)\*\*(.*?)\*\*(?!\*)", r"\1", text)
        text = re.sub(r"(?<!_)__(.*?)__(?!_)", r"\1", text)
        text = re.sub(r"(?<!\*)\*(.*?)\*(?!\*)", r"\1", text)
        text = re.sub(r"(?<!_)_(.*?)_(?!_)", r"\1", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"\n{2,}", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\s*\n\s*", "\n", text)
        return text.strip()

    def _normalize_output_lines(self, lines: list[str]) -> list[str]:
        """丢弃空片段并避免只有标点的行"""
        normalized_lines: list[str] = []
        punctuation_only_pattern = re.compile(
            r"^[\s\.,\uFF0C\u3002\uFF01\uFF1F\uFF1B\uFF1A\u3001\u2026~]+$"
        )
        markdown_only_pattern = re.compile(r"^\s*(?:[-*_`~#>\|]+\s*)+$")

        for line in lines:
            line = line.strip()
            if not line:
                if self.is_debug:
                    logger.info("[util] 跳过空分割行")
                continue

            if markdown_only_pattern.fullmatch(line):
                if self.is_debug:
                    logger.info(f"[util] 跳过仅markdown行: {line}")
                continue

            if punctuation_only_pattern.fullmatch(line):
                if normalized_lines:
                    normalized_lines[-1] += line
                    if self.is_debug:
                        logger.info(f"[util] 将仅标点行合并到前一行: {line}")
                elif self.is_debug:
                    logger.info(f"[util] 丢弃没有接收者的前导仅标点行: {line}")
                continue

            normalized_lines.append(line)

        while normalized_lines and punctuation_only_pattern.fullmatch(
            normalized_lines[-1]
        ):
            if self.is_debug:
                logger.info(f"[util] 丢弃尾部的仅标点行: {normalized_lines[-1]}")
            normalized_lines.pop()

        if self.is_debug:
            logger.info(
                f"[util] 规范化完成，行数={len(normalized_lines)}, 行内容={json.dumps(normalized_lines, ensure_ascii=False)}"
            )

        return normalized_lines

    def _should_skip_llm_split(self, text: str | None) -> bool:
        if not text:
            return False
        normalized_text = text.lower()
        return any(keyword in normalized_text for keyword in self.no_split_keywords)

    def _validate_qq(self, qq):
        """验证QQ号是否合法（只包含数字）"""
        if not qq or not isinstance(qq, str):
            return False
        # 只允许数字，防止路径遍历攻击
        if not qq.isdigit():
            logger.warning(f"检测到非法QQ号格式: {qq}")
            return False
        return True

    async def get_emoji_id(self, text):
        if "正确" in text:
            return self.emotions_mapping["开心"][
                random.randint(0, len(self.emotions_mapping["开心"]) - 1)
            ]
        elif "摆烂" in text:
            return self.emotions_mapping["无语"][
                random.randint(0, len(self.emotions_mapping["无语"]) - 1)
            ]
        else:
            return None

    async def weighted_random_choice(self, elements, weights):
        """
        加权随机选择函数
        参数:
        elements: 元素序列
        weights: 权重序列
        返回:
        随机选择的元素
        """
        # 如果已经是numpy数组，直接使用
        if isinstance(weights, np.ndarray):
            probs = weights / weights.sum()
            idx = np.random.choice(len(elements), p=probs)
        else:
            # 转换为numpy数组处理
            weights_arr = np.array(weights, dtype=np.float64)
            probs = weights_arr / weights_arr.sum()
            idx = np.random.choice(len(elements), p=probs)
        return elements[idx] if not isinstance(elements, np.ndarray) else elements[idx]

    def extract_and_sanitize_input(self, text: str, keyword: str) -> str:
        if not text or not keyword:
            return ""
        pattern = rf"{re.escape(keyword)}\s*(.*)"
        match = re.search(pattern, text)
        if not match:
            return ""
        user_input = match.group(1).strip()

        # 不清理，只做长度限制
        if len(user_input) > 200:
            user_input = user_input[:200]

        return user_input
