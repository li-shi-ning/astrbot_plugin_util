from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.message_components import Poke, Plain
import astrbot.api.message_components as Comp
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import numpy as np

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
            0.1,   # 喵
            1.0,   # 哈气
            10.0,  # 反弹
        ])

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def getpoke(self, event: AstrMessageEvent):
        raw_message = getattr(event.message_obj, "raw_message", None)
        if (
            not raw_message or
            raw_message.get('post_type') != 'notice' or
            raw_message.get('notice_type') != 'notify' or
            raw_message.get('sub_type') != 'poke'
        ):
            return
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
            bot = getattr(event.message_obj, "bot", None)
            if bot is None:
                text = await self.weighted_random_choice(
                    self.poke_responses[:-1],
                    self.poke_weights[:-1]
                )
                logger.info(f"bot不是个人bot,期望发送text:{text}")
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
