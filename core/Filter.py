from astrbot.core.star.filter import HandlerFilter
from astrbot.core.star.register.star_handler import get_handler_or_create
from astrbot.api.event import AstrMessageEvent
from astrbot.core.star.star_handler import EventType
from astrbot.core.config import AstrBotConfig

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
