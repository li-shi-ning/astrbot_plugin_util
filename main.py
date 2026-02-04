# ====== 核心模块 ======
from astrbot.core.config import AstrBotConfig
from astrbot.api.provider import ProviderRequest
from astrbot.core.star.star_handler import EventType, star_handlers_registry
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
from astrbot.core.star.filter.event_message_type import EventMessageType
from astrbot.core.star.star import star_map
from astrbot.api.star import StarTools

# ====== API 模块 ======
from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

# ====== 第三方库 ======
import numpy as np
import random
import json
import os
import asyncio

# ====== 核心库 ======
from .core.ChineseEntityExtractor import ChineseEntityExtractor
from .core.Filter import register_pack_type
from .core.api_client import ApiClient


@register("util", "lishinig", "私人插件", "1.0.0")
class util(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)

        self.config = config
        self.data_dir = self.config.get("data_dir", None)
        self.max_role_doct = self.config.get("max_role_doct", 3)
        self.role_file_mapping = {}
        self.is_debug = False
        self.mahjong_interface_url = config.get("mahjong_interface_url", None)
        if self.mahjong_interface_url:
            self.client = ApiClient(self.mahjong_interface_url)
            logger.info(f"[util] 已使用:{self.mahjong_interface_url},作为麻将接口")
        else:
            self.client = None
            logger.info(f"[util] 未配置麻将接口请使用 /mj seturl [url] 设置")

        # 麻将数据轮询定时器相关属性
        self._mj_poll_task: asyncio.Task | None = None
        self._mj_poll_interval: float = config.get("mj_poll_interval", 5.0)
        self.mj_game_info: dict | None = None  # 存储最新游戏信息
        self.mj_ai_guide: dict | None = None   # 存储最新 AI 指导信息
        if self.data_dir is None:
            self.data_dir = StarTools.get_data_dir()
            self.data_dir_entity = os.path.join(self.data_dir, "entity")
            logger.error("数据加载失败")
            self.chineseentityextractor = ChineseEntityExtractor(
                chinese_ratio_threshold = 0.2
            )
        else:
            self.data_dir_entity = os.path.join(self.data_dir, "entity")
            self.chineseentityextractor = ChineseEntityExtractor(
                user_dict_path = os.path.join(self.data_dir, "entity_dict.txt"),
                chinese_ratio_threshold = 0.2
            )
            self.role_file_mapping = {
                "mnsp_hiro": "hiro.txt",
                "mnsp_miria": "miria.txt",
                "mnsp_meruru": "meruru.txt",
                "mnsp_noa": "noa.txt",
                "mnsp_anan": "anan.txt",
                "mnsp_maago": "maago.txt",
                "mnsp_yuki": "yuki.txt",
                "mnsp_ema": "ema.txt",
                "mnsp_sherii": "sherii.txt",
                "mnsp_koko": "koko.txt",
                "mnsp_arisa": "arisa.txt",
                "mnsp_reia": "reia.txt",
                "mnsp_hanna": "hanna.txt",
                "mnsp_nanoka": "nanoka.txt"
            }

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
    async def replyMessage(self,event: AiocqhttpMessageEvent):
        """获取所有消息,进行贴表情"""
        raw_message = getattr(event.message_obj, "raw_message", None)
        message_id = raw_message.get('message_id', None)
        text = raw_message.get('raw_message', None)
        if not text or not message_id:
            return
        bot = getattr(event, "bot", None)
        if bot is None:
            return
        emoji_id = await self.get_emoji_id(text)
        if emoji_id is None:
            return
        payloads = {
            "message_id":message_id,
            "emoji_id":emoji_id
        }
        await bot.api.call_action('set_msg_emoji_like', **payloads)

    async def get_emoji_id(self, text):
        if "正确" in text:
            return self.emotions_mapping["开心"][random.randint(0,len(self.emotions_mapping["开心"]) - 1)]
        elif "摆烂" in text:
            return self.emotions_mapping["无语"][random.randint(0, len(self.emotions_mapping["无语"]) - 1)]
        else:
            return None

    @filter.command_group("mj")
    async def mj(self):
        pass

    @mj.command("seturl")
    async def set_url(self, event: AstrMessageEvent, url: str):
        """设置麻将接口url"""
        self.mahjong_interface_url = url
        if self.client is None:
            self.client = ApiClient(self.mahjong_interface_url)
        else:
            self.client.set_url(self.mahjong_interface_url)
        yield event.plain_result(f"已经设置mahjong_interface_url为:{self.mahjong_interface_url}")
        logger.info(f"[util] 已经设置mahjong_interface_url为:{self.mahjong_interface_url}")

    @mj.command("gs")
    async def get_status(self, event: AstrMessageEvent):
        """获取游戏详细信息"""
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.get_status()
        yield event.plain_result(f"游戏详细数据为:{json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] 游戏详细数据为:{json.dumps(data, indent=4, ensure_ascii=False)}")

    @mj.command("ggi")
    async def get_game_info(self, event: AstrMessageEvent):
        """获取当前游戏信息"""
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.get_game_info()
        yield event.plain_result(f"当前游戏信息为:{json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] 当前游戏信息为:{json.dumps(data, indent=4, ensure_ascii=False)}")

    @mj.command("gag")
    async def get_ai_guide(self, event: AstrMessageEvent):
        """获取 AI 指导信息"""
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.get_ai_guide()
        yield event.plain_result(f"AI指导信息为:{json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] AI指导信息为:{json.dumps(data, indent=4, ensure_ascii=False)}")

    @mj.command("sb")
    async def start_browser(self, event: AstrMessageEvent):
        """启动浏览器"""
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.start_browser()
        yield event.plain_result(f"启动浏览器结果: {json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] 启动浏览器结果: {json.dumps(data, indent=4, ensure_ascii=False)}")

    @mj.command("eo")
    async def enable_overlay(self, event: AstrMessageEvent):
        """启用网页覆盖显示"""
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.enable_overlay()
        yield event.plain_result(f"启用网页覆盖显示结果: {json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] 启用网页覆盖显示结果: {json.dumps(data, indent=4, ensure_ascii=False)}")

    @mj.command("do")
    async def disable_overlay(self, event: AstrMessageEvent):
        """禁用网页覆盖显示"""
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.disable_overlay()
        yield event.plain_result(f"禁用网页覆盖显示结果: {json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] 禁用网页覆盖显示结果: {json.dumps(data, indent=4, ensure_ascii=False)}")

    @mj.command("to")
    async def toggle_overlay(self, event: AstrMessageEvent):
        """切换网页覆盖显示状态"""
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.toggle_overlay()
        yield event.plain_result(f"切换网页覆盖显示状态结果: {json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] 切换网页覆盖显示状态结果: {json.dumps(data, indent=4, ensure_ascii=False)}")

    @mj.command("ea")
    async def enable_automation(self, event: AstrMessageEvent):
        """启用自动打牌"""
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.enable_automation()
        yield event.plain_result(f"启用自动打牌结果: {json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] 启用自动打牌结果: {json.dumps(data, indent=4, ensure_ascii=False)}")

    @mj.command("da")
    async def disable_automation(self, event: AstrMessageEvent):
        """禁用自动打牌"""
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.disable_automation()
        yield event.plain_result(f"禁用自动打牌结果: {json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] 禁用自动打牌结果: {json.dumps(data, indent=4, ensure_ascii=False)}")

    @mj.command("ta")
    async def toggle_automation(self, event: AstrMessageEvent):
        """切换自动打牌状态"""
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.toggle_automation()
        yield event.plain_result(f"切换自动打牌状态结果: {json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] 切换自动打牌状态结果: {json.dumps(data, indent=4, ensure_ascii=False)}")

    @mj.command("ej")
    async def enable_autojoin(self, event: AstrMessageEvent):
        """启用自动加入游戏"""
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.enable_autojoin()
        yield event.plain_result(f"启用自动加入游戏结果: {json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] 启用自动加入游戏结果: {json.dumps(data, indent=4, ensure_ascii=False)}")

    @mj.command("dj")
    async def disable_autojoin(self, event: AstrMessageEvent):
        """禁用自动加入游戏"""
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.disable_autojoin()
        yield event.plain_result(f"禁用自动加入游戏结果: {json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] 禁用自动加入游戏结果: {json.dumps(data, indent=4, ensure_ascii=False)}")

    @mj.command("tj")
    async def toggle_autojoin(self, event: AstrMessageEvent):
        """切换自动加入游戏状态"""
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.toggle_autojoin()
        yield event.plain_result(f"切换自动加入游戏状态结果: {json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] 切换自动加入游戏状态结果: {json.dumps(data, indent=4, ensure_ascii=False)}")

    @mj.command("gjs")
    async def get_autojoin_settings(self, event: AstrMessageEvent):
        """获取自动加入游戏设置"""
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.get_autojoin_settings()
        yield event.plain_result(f"自动加入游戏设置: {json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] 自动加入游戏设置: {json.dumps(data, indent=4, ensure_ascii=False)}")

    @mj.command("sjs")
    async def set_autojoin_settings(self, event: AstrMessageEvent, level: int, mode: str):
        """设置自动加入游戏参数

        Args:
            level: 等级索引 (0-3)
            mode: 游戏模式 (east, south, fast, ...)
        """
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.set_autojoin_settings(level, mode)
        yield event.plain_result(f"设置自动加入游戏参数结果: {json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] 设置自动加入游戏参数结果: {json.dumps(data, indent=4, ensure_ascii=False)}")

    @mj.command("gset")
    async def get_settings(self, event: AstrMessageEvent):
        """获取当前设置"""
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.get_settings()
        yield event.plain_result(f"当前设置: {json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] 当前设置: {json.dumps(data, indent=4, ensure_ascii=False)}")

    @mj.command("sset")
    async def save_settings(self, event: AstrMessageEvent):
        """保存设置到文件"""
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.save_settings()
        yield event.plain_result(f"保存设置结果: {json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] 保存设置结果: {json.dumps(data, indent=4, ensure_ascii=False)}")



    @mj.command("rm")
    async def reload_model(self, event: AstrMessageEvent):
        """重新加载模型"""
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.reload_model()
        yield event.plain_result(f"重新加载模型结果: {json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] 重新加载模型结果: {json.dumps(data, indent=4, ensure_ascii=False)}")

    @mj.command("sd")
    async def shutdown(self, event: AstrMessageEvent):
        """关闭应用程序"""
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.shutdown()
        yield event.plain_result(f"关闭应用程序结果: {json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] 关闭应用程序结果: {json.dumps(data, indent=4, ensure_ascii=False)}")

    @mj.command("hc")
    async def health_check(self, event: AstrMessageEvent):
        """健康检查接口"""
        if self.client is None:
            yield event.plain_result(f"未设置mahjong_interface_url")
            return
        data = await self.client.health_check()
        yield event.plain_result(f"健康检查结果: {json.dumps(data, indent=4, ensure_ascii=False)}")
        logger.info(f"[util] 健康检查结果: {json.dumps(data, indent=4, ensure_ascii=False)}")

    @mj.command("st")
    async def start_poll_timer(self, event: AstrMessageEvent, interval: float = 5.0):
        """启动数据轮询定时器

        Args:
            interval: 轮询间隔（秒），默认 5 秒
        """
        if self.client is None:
            yield event.plain_result("未设置mahjong_interface_url")
            return
        if self._mj_poll_task is not None and not self._mj_poll_task.done():
            yield event.plain_result(f"定时器已在运行中，间隔: {self._mj_poll_interval}秒")
            return
        self._mj_poll_interval = interval
        self._mj_poll_task = asyncio.create_task(self._mj_poll_loop())
        yield event.plain_result(f"已启动数据轮询定时器，间隔: {interval}秒")
        logger.info(f"[util] 已启动麻将数据轮询定时器，间隔: {interval}秒")

    @mj.command("pt")
    async def stop_poll_timer(self, event: AstrMessageEvent):
        """停止数据轮询定时器"""
        if self._mj_poll_task is None or self._mj_poll_task.done():
            yield event.plain_result("定时器未在运行")
            return
        self._mj_poll_task.cancel()

        try:
            await asyncio.wait_for(self._mj_poll_task, timeout=5.0)
            logger.info("[util] 定时器已正常停止")
        except asyncio.TimeoutError:
            logger.warning("[util] 停止定时器超时，任务可能卡住")
        except Exception as e:
            logger.error(f"[util] 停止定时器时发生错误: {e}")

        self._mj_poll_task = None
        yield event.plain_result("已停止数据轮询定时器")
        logger.info("[util] 已停止麻将数据轮询定时器")

    @mj.command("gp")
    async def get_poll_data(self, event: AstrMessageEvent):
        """获取当前轮询缓存的数据"""
        result = {
            "timer_running": self._mj_poll_task is not None and not self._mj_poll_task.done(),
            "poll_interval": self._mj_poll_interval,
            "game_info": self.mj_game_info,
            "ai_guide": self.mj_ai_guide
        }
        yield event.plain_result(f"轮询数据:\n{json.dumps(result, indent=4, ensure_ascii=False)}")

    async def _mj_poll_loop(self):
        """麻将数据轮询循环"""
        logger.info("[util] 麻将数据轮询循环已启动")
        while True:
            try:
                # 并行获取游戏信息和 AI 指导
                game_info_task = self.client.get_game_info()
                ai_guide_task = self.client.get_ai_guide()
                self.mj_game_info, self.mj_ai_guide = await asyncio.gather(
                    game_info_task, ai_guide_task, return_exceptions=True
                )
                # 处理异常情况
                if isinstance(self.mj_game_info, Exception):
                    logger.warning(f"[util] 获取游戏信息失败: {self.mj_game_info}")
                    self.mj_game_info = None
                if isinstance(self.mj_ai_guide, Exception):
                    logger.warning(f"[util] 获取AI指导失败: {self.mj_ai_guide}")
                    self.mj_ai_guide = None
            except asyncio.CancelledError:
                logger.info("[util] 麻将数据轮询循环已停止")
                break
            except Exception as e:
                logger.error(f"[util] 轮询数据时发生错误: {e}")
            logger.info()
            try:
                await asyncio.sleep(self._mj_poll_interval)
            except asyncio.CancelledError:
                logger.info("[util] 休眠期间收到取消信号,麻将数据轮询循环已停止")
                break

        self.mj_game_info = None
        self.mj_ai_guide = None

    # @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    # async def group_message_cs(self, event: AstrMessageEvent):
    #     logger.info(f"[util] 收到群聊消息,类型为{type(event)}")
    #     if not isinstance(event, AiocqhttpMessageEvent):
    #         logger.info(f"[util] 收到群聊消息,并且不为AiocqhttpMessageEvent类型,为{type(event)}")

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
            handler_info["handler_full_name"] = getattr(handler, "handler_full_name", None)
            handler_info_by_event["handler_full_name"] = getattr(handler, "handler_full_name", None)
            # 3. 处理器名称（函数名）
            handler_info["handler_name"] = getattr(handler, "handler_name", None)
            # 4. 处理器模块路径
            handler_info["handler_module_path"] = getattr(handler, "handler_module_path", None)
            handler_info_by_event["handler_module_path"] = getattr(handler, "handler_module_path", None)
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
        logger.info(chr(10).join(output_text))
        yield event.plain_result(chr(10).join(event_output_text))

    @lishi.command("hibmp")
    async def get_handler_by_mp(self, event: AstrMessageEvent, handler_module_path: str):
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
                "plugin_author": getattr(plugin, "author", "")
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
                "plugin_author": getattr(plugin, "author", "")
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

        payloads = {
            "user_id": int(qq),
            "no_cache": True
        }
        qq_info = await bot.api.call_action('get_stranger_info', **payloads)
        nick = qq_info["nick"]
        yield event.plain_result(f"该用户的名称为:{nick}")

    @lishi.command("ch")
    async def get_chat_history(self, event: AstrMessageEvent):
        """获取当前会话的历史信息"""
        unified_msg_origin = event.unified_msg_origin
        conversation_id = await self.context.conversation_manager.get_curr_conversation_id(unified_msg_origin)
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
            # logger.info(f"history:{json.dumps(history, indent=4, ensure_ascii=False)}")
        else:
            print("对话不存在")

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @lishi.command("chb")
    async def get_chat_history_by_bot(self, event: AiocqhttpMessageEvent):
        """通过onebot接口获取聊天历史"""
        group_id = event.get_group_id()
        sender_id = event.get_sender_id()
        is_group = not group_id is None
        bot = getattr(event, "bot", None)
        if bot is None:
            return
        if is_group:
            logger.info("[util] 进行get_group_msg_history")
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
            payloads = {
                "group_id":group_id
            }
            output_text = json.dumps(await bot.api.call_action('get_group_msg_history', **payloads), indent=4, ensure_ascii=False)
            logger.info(output_text)
            yield event.plain_result("已获取,打印到日志")
        else:
            logger.info("[util] 进行get_friend_msg_history")
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
            payloads = {
                "user_id": sender_id
            }
            output_text = json.dumps(await bot.api.call_action('get_friend_msg_history', **payloads), indent=4, ensure_ascii=False)
            logger.info(output_text)
            yield event.plain_result("已获取,打印到日志")

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @lishi.command("chbf")
    async def get_chat_history_by_bot_by_sender_id(self, event: AiocqhttpMessageEvent, sender_id: str):
        """通过qq号获取消息"""
        if not self._validate_qq(sender_id):
            yield event.plain_result("请输入正确的id")
            return
        bot = getattr(event, "bot", None)
        if bot is None:
            return
        payloads = {
            "user_id":sender_id
        }
        output_text = json.dumps(await bot.api.call_action('get_friend_msg_history', **payloads), indent=4, ensure_ascii=False)
        logger.info(output_text)
        yield event.plain_result("已获取,打印到日志")

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @lishi.command("chbg")
    async def get_chat_history_by_bot_by_group_id(self, event: AiocqhttpMessageEvent, group_id: str):
        """通过群聊号获取消息"""
        if not self._validate_qq(group_id):
            yield event.plain_result("请输入正确的id")
            return
        bot = getattr(event, "bot", None)
        if bot is None:
            return
        payloads = {
            "group_id":group_id
        }
        output_text = json.dumps(await bot.api.call_action('get_group_msg_history', **payloads), indent=4, ensure_ascii=False)
        logger.info(output_text)
        yield event.plain_result("已获取,打印到日志")

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @lishi.command("chbgpn")
    async def get_chat_history_by_bot_process(self, event: AiocqhttpMessageEvent, group_id: str, count: int):
        """通过群聊号获取消息并且处"""
        raw_message = getattr(event.message_obj, "raw_message", None)
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
        self.is_debug = set_bool == 1
        yield event.plain_result(f"设置debug:{self.is_debug}")

    @filter.on_llm_request(priority=49)
    async def add_doct(self, event: AstrMessageEvent, request: ProviderRequest):
        text = event.message_str
        entities = self.chineseentityextractor.extract(text)
        text_tag = []
        for entitie in entities:
            if not (entitie["type"] in text_tag):
                text_tag.append(entitie["type"])
        text_tag = text_tag[:self.max_role_doct]
        if len(text_tag) > 0:
            My_prompt = f'The following are role documents that may be used:\n'
            for name in text_tag:
                file_name = self.role_file_mapping.get(name, None)
                file_path = os.path.join(self.data_dir, file_name)
                if not file_name is None and os.path.exists(file_path):
                    with open(file_path, "r") as f:
                        My_prompt += f"{f.read()}\n" + "-" * 10 + "\n"
                else:
                    logger.info("获取文件失败")
                    logger.info(f"file_name:{file_name}")
                    logger.info(f"file_path:{file_path}")
                    logger.info(f"对于:{text},识别到:{text_tag}")
            if self.is_debug:
                logger.info(f"注入提示词:\n{My_prompt}")
            request.system_prompt += My_prompt
            if self.is_debug:
                logger.info(f"注入后的系统提示词:\n{request.system_prompt}")
        else:
            if self.is_debug:
                logger.info(f"对于:{text},识别到:{text_tag}")

    @filter.on_llm_request(priority=48)
    async def add_mj(self, event: AstrMessageEvent, request: ProviderRequest):
        """在游戏中时，向 LLM 注入麻将游戏上下文"""
        if self.client is None:
            return

        # 获取游戏状态
        try:
            data = await self.client.get_status()
            ui_state = data.get("game", {}).get("ui_state", "")
        except Exception as e:
            logger.debug(f"[util] 获取麻将状态失败: {e}")
            return

        # 仅在游戏中时注入信息
        if "IN_GAME" not in ui_state:
            return

        # 检查轮询数据是否可用
        if self.mj_game_info is None and self.mj_ai_guide is None:
            logger.debug("[util] 麻将轮询数据未就绪，跳过注入")
            return

        # 构建结构化提示词
        prompt_parts = [
            "\n" + "=" * 40,
            "【雀魂麻将游戏实时信息】",
            "你当前正在进行雀魂麻将对局，以下是实时游戏数据。",
            "当用户询问牌局相关问题时，请基于这些信息进行分析和回答。",
            "【玩家对话守则】",
            "1. 我绝不会透露手牌具体内容。这是禁忌。",
            "2. 我只陈述自身状态：『听牌』、『未完成』、『牌形可动』。",
            "3. 我的发言都是基于手牌现状的判断与决策。",
            "4. 不讨论未发生的事，不回应无意义情绪。",
            "【发言模式】",
            "牌形已固定。听牌。",
            "手牌混乱。这巡弃和。",
            "改良可能存在。继续进攻。",
            "不讨论手牌。只告知行动。",
        ]

        if self.mj_game_info:
            prompt_parts.extend([
                "## 当前牌局状态",
                "```json",
                json.dumps(self.mj_game_info, indent=2, ensure_ascii=False),
                "```",
                ""
            ])

        if self.mj_ai_guide:
            prompt_parts.extend([
                "## AI 推荐操作",
                "```json",
                json.dumps(self.mj_ai_guide, indent=2, ensure_ascii=False),
                "```",
                ""
            ])

        prompt_parts.append("=" * 40)

        request.system_prompt += "\n".join(prompt_parts)

    async def get_message(self, group_id, bot, count):
        payloads = {
            "group_id":group_id,
            "count": count
        }
        data = await bot.api.call_action('get_group_msg_history', **payloads)
        outpur_text = []
        logger.info(f"[util] 处理:\n{json.dumps(data['messages'], indent=4, ensure_ascii=False)}")
        for message in data["messages"]:
            for message_data in message["message"]:
                if message_data["type"] == "text":
                    try:
                        outpur_text.append(message_data["data"]["text"])
                    except:
                        pass
        message_id = data["messages"][0]["message_id"]
        return outpur_text, message_id

    def _validate_qq(self, qq):
        """验证QQ号是否合法（只包含数字）"""
        if not qq or not isinstance(qq, str):
            return False
        # 只允许数字，防止路径遍历攻击
        if not qq.isdigit():
            logger.warning(f"检测到非法QQ号格式: {qq}")
            return False
        return True

