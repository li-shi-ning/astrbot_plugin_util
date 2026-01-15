# ====== 核心模块 ======
from astrbot.core.config import AstrBotConfig
from astrbot.core.star.filter import HandlerFilter
from astrbot.core.star.register.star_handler import get_handler_or_create
from astrbot.core.star.star_handler import EventType, star_handlers_registry
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
from astrbot.core.star.star import star_map

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
    async def replyMessage(self,event: AiocqhttpMessageEvent):
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

    @filter.command_group("lishi")
    async def lishi(self):
        pass

    @lishi.command("ah")
    async def get_all_handler(self, event: AstrMessageEvent):
        "获取所有处理器的详细信息"
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

"""

for handler in star_handlers_registry.get_handlers_by_event_type(
    EventType.AdapterMessageEvent,
    plugins_name=None,
):
    print(handler.handler_full_name)

@dataclass
class StarHandlerMetadata(Generic[H]):
    "描述一个 Star 所注册的某一个 Handler。"

    event_type: EventType
    "Handler 的事件类型"

    handler_full_name: str
    '''格式为 f"{handler.__module__}_{handler.__name__}"'''

    handler_name: str
    "Handler 的名字，也就是方法名"

    handler_module_path: str
    "Handler 所在的模块路径。"

    handler: H
    "Handler 的函数对象，应当是一个异步函数"

    event_filters: list[HandlerFilter]
    "一个适配器消息事件过滤器，用于描述这个 Handler 能够处理、应该处理的适配器消息事件"

    desc: str = ""
    "Handler 的描述信息"

    extras_configs: dict = field(default_factory=dict)
    "插件注册的一些其他的信息, 如 priority 等"

    enabled: bool = True

    def __lt__(self, other: StarHandlerMetadata):
        "定义小于运算符以支持优先队列"
        return self.extras_configs.get("priority", 0) < other.extras_configs.get(
            "priority",
            0,
        )

@li.command("ah")
async def get_all_handler(self, event: AstrMessageEvent):
    "获取所有处理器的详细信息"
    output_text = []
    
    # 遍历所有消息事件处理器
    for handler in star_handlers_registry.get_handlers_by_event_type(
            EventType.AdapterMessageEvent,
            plugins_name=None,  # None表示获取所有插件，不进行过滤
    ):
        # 创建一个字典来存储所有属性
        handler_info = {}
        
        # 1. 事件类型
        handler_info["event_type"] = getattr(handler, "event_type", None)
        
        # 2. 处理器完整名称（格式：模块名_函数名）
        handler_info["handler_full_name"] = getattr(handler, "handler_full_name", None)
        
        # 3. 处理器名称（函数名）
        handler_info["handler_name"] = getattr(handler, "handler_name", None)
        
        # 4. 处理器模块路径
        handler_info["handler_module_path"] = getattr(handler, "handler_module_path", None)
        
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
        
        # 详细记录每个过滤器的信息
        for i, filter_obj in enumerate(event_filters):
            filter_info = {
                "index": i,
                "type": type(filter_obj).__name__,
                "module": filter_obj.__class__.__module__,
                "attributes": {}
            }
            
            # 尝试获取过滤器的一些常见属性
            for attr_name in dir(filter_obj):
                if not attr_name.startswith("_"):  # 排除私有属性
                    try:
                        attr_value = getattr(filter_obj, attr_name)
                        # 过滤掉方法、模块等复杂对象，只保留简单类型
                        if not callable(attr_value) and not isinstance(attr_value, type):
                            # 简化复杂对象的显示
                            if hasattr(attr_value, "__name__"):
                                filter_info["attributes"][attr_name] = f"<{attr_value.__name__}>"
                            elif hasattr(attr_value, "__class__"):
                                filter_info["attributes"][attr_name] = f"<{attr_value.__class__.__name__}>"
                            else:
                                filter_info["attributes"][attr_name] = str(attr_value)
                    except:
                        continue
            
            handler_info["event_filters"].append(filter_info)
        
        # 9. 获取处理器函数对象的详细信息
        handler_func = getattr(handler, "handler", None)
        if handler_func:
            handler_info["handler_function"] = {
                "name": handler_func.__name__,
                "module": handler_func.__module__ if hasattr(handler_func, "__module__") else "unknown",
                "qualname": handler_func.__qualname__ if hasattr(handler_func, "__qualname__") else "unknown",
                "is_coroutine": asyncio.iscoroutinefunction(handler_func),
                "signature": str(inspect.signature(handler_func)) if hasattr(inspect, "signature") else "unknown"
            }
        
        # 10. 根据 extras_configs 获取优先级
        handler_info["priority"] = handler_info["extras_configs"].get("priority", 0)
        
        # 11. 从 star_map 获取插件信息
        plugin_info = {}
        if handler_info["handler_module_path"] in star_map:
            plugin = star_map[handler_info["handler_module_path"]]
            plugin_info = {
                "plugin_name": getattr(plugin, "name", "unknown"),
                "plugin_desc": getattr(plugin, "desc", ""),
                "plugin_version": getattr(plugin, "version", ""),
                "plugin_author": getattr(plugin, "author", "")
            }
        handler_info["plugin_info"] = plugin_info
        
        # 格式化输出
        output = [
            "=" * 80,
            f"处理器: {handler_info['handler_full_name']}",
            f"状态: {'✅ 启用' if handler_info['enabled'] else '❌ 禁用'}",
            f"优先级: {handler_info['priority']}",
            f"事件类型: {handler_info['event_type']}",
            f"处理器名称: {handler_info['handler_name']}",
            f"模块路径: {handler_info['handler_module_path']}",
            f"描述: {handler_info['desc']}",
        ]
        
        # 添加插件信息
        if plugin_info:
            output.append(f"插件: {plugin_info['plugin_name']} v{plugin_info['plugin_version']}")
            output.append(f"插件作者: {plugin_info['plugin_author']}")
            output.append(f"插件描述: {plugin_info['plugin_desc']}")
        
        # 添加处理器函数信息
        if "handler_function" in handler_info:
            func_info = handler_info["handler_function"]
            output.append(f"函数: {func_info['name']}")
            output.append(f"协程函数: {'是' if func_info['is_coroutine'] else '否'}")
            output.append(f"签名: {func_info['signature']}")
        
        # 添加过滤器信息
        output.append(f"过滤器数量: {handler_info['event_filters_count']}")
        for filter_info in handler_info["event_filters"]:
            output.append(f"  [{filter_info['index']}] {filter_info['type']}")
            if filter_info["attributes"]:
                for attr_name, attr_value in filter_info["attributes"].items():
                    output.append(f"    {attr_name}: {attr_value}")
        
        # 添加额外配置
        if handler_info["extras_configs"]:
            output.append("额外配置:")
            for key, value in handler_info["extras_configs"].items():
                if key != "priority":  # 优先级已单独显示
                    output.append(f"  {key}: {value}")
        
        output_text.append("\n".join(output))
    
    # 统计信息
    total_handlers = len(output_text)
    output_text.insert(0, f"共找到 {total_handlers} 个处理器")
    
    # 发送结果（分页处理，避免消息过长）
    full_output = "\n\n".join(output_text)
    
    # 如果输出太长，分开发送
    max_length = 2000  # 消息平台限制
    if len(full_output) > max_length:
        # 分开发送每个处理器的信息
        for i, handler_output in enumerate(output_text[1:], 1):  # 跳过统计信息
            await event.send(f"处理器 {i}/{total_handlers}:\n{handler_output}")
    else:
        await event.send(full_output)
"""