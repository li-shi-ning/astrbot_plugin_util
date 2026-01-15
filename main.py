# ====== 核心模块 ======
from astrbot.core.config import AstrBotConfig
from astrbot.core.star.filter import HandlerFilter
from astrbot.core.star.register.star_handler import get_handler_or_create
from astrbot.core.star.star_handler import EventType
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent

# ====== API 模块 ======
from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

# ====== 第三方库 ======
import numpy as np
import random

class PackTypeFilter(HandlerFilter):
    """检查戳一戳事件"""
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        raw_message = getattr(event.message_obj, "raw_message", None)
        if not isinstance(raw_message, dict):
            return False
        return raw_message.get('sub_type') == 'poke'

def register_pack_type(**kwargs):
    """注册一个 PackTypeFilter"""
    def decorator(awaitable):
        handler_md = get_handler_or_create(awaitable, EventType.AdapterMessageEvent)
        handler_md.event_filters.append(
            PackTypeFilter(),
        )
        return awaitable
    return decorator

class StrictPokeFilter(HandlerFilter):
    """严格检查AIOCQHTTP平台的戳一戳事件"""
    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        raw_message = getattr(event.message_obj, "raw_message", None)
        if not isinstance(raw_message, dict):
            return False
        return (
                raw_message.get('post_type') == 'notice' and
                raw_message.get('notice_type') == 'notify' and
                raw_message.get('sub_type') == 'poke'
        )

def register_strict_pack_type(**kwargs):
    """注册一个 StrictPokeFilter"""
    def decorator(awaitable):
        handler_md = get_handler_or_create(awaitable, EventType.AdapterMessageEvent)
        handler_md.event_filters.append(
            StrictPokeFilter(),
        )
        return awaitable
    return decorator

@register("util", "lishinig", "私人插件", "1.0.0")
class util(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.poke_responses = np.array([
            "请勿随意触碰。作为向导，我建议你保持适当的距离。",
            "（微微后退一步）这种接触并不符合'正确'的社交礼仪。",
            "你寻求我的注意吗？那么，请用言语而非动作表达。",
            "在里账号迷宫中，每个动作都应有其意义。你的目的是？",
            "（冷静注视）你的行为暴露了轻率。这需要修正。",
            "我仍在引导你。但触碰，并非必要的交流方式。",
            "若你感到迷茫，我可以指引。但请停止无意义的动作。",
            "（整理衣襟）秩序，体现在每一个细节中。包括适当的距离。",
            "你的行为，与迷宫的混沌同样需要被净化。",
            "触碰无法触及真理。让我们用理性的对话代替。",
            "喵~",
            "哈!",
            "pack"
        ])

        self.poke_weights = np.array([
            8.0,   # 礼仪纠正
            9.5,   # 评判纠正（最高）
            7.0,   # 引导交流
            8.5,   # 质询目的
            9.0,   # 行为修正
            7.5,   # 引导职责
            6.5,   # 提供指引
            8.0,   # 秩序强调
            8.5,   # 净化理念
            7.0,   # 理性倡导
            5.0,   # 喵
            6.0,   # 哈气
            10.0,  # 反弹
        ])

        self.emotions_mapping = {
            "开心": [2, 74, 109, 272, 295, 305, 318, 319, 324, 339],
            "得意": [4, 16, 28, 29, 99, 101, 178, 269, 270, 277, 283, 299, 307, 336, 426],
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
            "无聊": [8, 25, 285, 293]
        }

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @register_pack_type()
    async def poke(self, event: AiocqhttpMessageEvent):
        raw_message = getattr(event.message_obj, "raw_message", None)
        bot_id = raw_message.get('self_id', None)
        sender_id = raw_message.get('user_id', None)
        target_id = raw_message.get('target_id', None)
        group_id = raw_message.get('group_id', None)
        if not bot_id or not sender_id or not target_id or str(target_id) != str(bot_id):
            return
        text = await self.weighted_random_choice(
            self.poke_responses,
            self.poke_weights
        )
        logger.info(f"检测到戳一戳,期望发送text:{text}")
        if text == "pack":
            payloads = {"user_id": sender_id}
            if group_id:
                payloads["group_id"] = group_id
            bot = getattr(event, "bot", None)
            if bot is None:
                text = await self.weighted_random_choice(
                    self.poke_responses[:-1],
                    self.poke_weights[:-1]
                )
                logger.info(f"bot不是AIOCQHTTP,期望发送text:{text}")
                yield event.plain_result(text)
            else:
                await bot.api.call_action('send_poke', **payloads)
        else:
            yield event.plain_result(text)

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

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    async def replyMessage(self,event: AiocqhttpMessageEvent,):
        message = event.get_messages()[0]
        message_id = getattr(message, "id", None)
        text = getattr(message, "text", None)
        if not text or not message_id:
            return

        bot = getattr(event, "bot", None)
        if bot is None:
            return
        logger.info(f"[util] 接收到:{text},准备处理")
        if "正确" in text:
            emoji_id = self.emotions_mapping["开心"][random.randint(0,len(self.emotions_mapping["开心"]) - 1)]
        elif "摆烂" in text:
            emoji_id = self.emotions_mapping["无语"][random.randint(0, len(self.emotions_mapping["无语"]) - 1)]
        else:
            return

        payloads = {
            "message_id":message_id,
            "emoji_id":emoji_id
        }
        logger.info(f"[util] 接收到:{text},准备emoji_like,payloads:{payloads}")
        await bot.api.call_action('set_msg_emoji_like', **payloads)
