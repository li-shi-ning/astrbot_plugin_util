# ====== 核心模块 ======
import asyncio
import json
import random
import re
import traceback
import uuid
from collections import deque
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

# ====== 第三方库 ======
import numpy as np
from aiohttp import web

import astrbot.api.message_components as Comp
from astrbot.api import logger

# ====== API 模块 ======
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, register
from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import EventType, star_handlers_registry
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

# ====== 核心库 ======
try:
    from .core.Filter import register_pack_type
    from .core.ai_voice import (
        AI_VOICE_TOOL_NAME,
        AiVoiceClient,
        AiVoiceError,
        build_ai_voice_config,
    )
    from .core.group_history import (
        GROUP_HISTORY_EMPTY_ERROR,
        GROUP_HISTORY_FORMAT_ERROR,
        GROUP_HISTORY_HELP_COMMAND,
        GROUP_HISTORY_HELP_TEXT,
        build_group_history_nodes,
        get_qq_nickname,
        parse_group_history_components,
        parse_group_history_text,
    )
    from .core.document_parse import (
        DOCUMENT_PARSE_DISABLED_MESSAGE,
        DOCUMENT_PARSE_MISSING_FILE_MESSAGE,
        DOCUMENT_PARSE_PATH_DISABLED_MESSAGE,
        DOCUMENT_PARSE_TOOL_NAME,
        build_document_parse_config,
        collect_document_candidates,
        format_parsed_document,
        parse_local_document,
    )
    from .core.keyword_voice import load_group_keyword_voices
    from .core.love_message import (
        choose_love_message,
        format_love_message,
        load_love_messages,
    )
    from .core.music_search import (
        MUSIC_AUDIO_UNAVAILABLE_MESSAGE,
        MUSIC_DETAIL_ERROR_MESSAGE,
        MUSIC_LOGIN_API_ERROR_MESSAGE,
        MUSIC_LOGIN_EXPIRED_MESSAGE,
        MUSIC_LOGIN_NO_COOKIE_MESSAGE,
        MUSIC_LOGIN_QR_MESSAGE,
        MUSIC_LOGIN_SUCCESS_MESSAGE,
        MUSIC_LOGIN_TIMEOUT_MESSAGE,
        MUSIC_SEARCH_API_ERROR_MESSAGE,
        MUSIC_SEARCH_DISABLED_MESSAGE,
        MUSIC_SEARCH_EMPTY_MESSAGE,
        MUSIC_SEARCH_USAGE,
        MUSIC_SELECTION_EXPIRED_MESSAGE,
        MUSIC_SELECTION_INVALID_MESSAGE,
        NeteaseMusicAPI,
        PendingMusicSelection,
        build_music_config,
        format_search_results,
        format_song_detail,
        load_persisted_music_cookie,
        pending_selection_is_expired,
        save_persisted_music_cookie,
        save_qr_image,
    )
    from .core.offline_email_alert import (
        OFFLINE_EMAIL_SUBJECT,
        QQMAIL_ACTIONS,
        QQMAIL_TOOL_NAME,
        build_offline_email_alert_config,
        build_qqmail_tool_config,
        format_offline_email_content,
        is_bot_offline_notice,
        parse_email_addresses,
        qqmail_list_async,
        qqmail_read_async,
        qqmail_search_async,
        qqmail_trash_async,
        send_qq_email_async,
    )
    from .core.offline_webhook_alert import (
        OFFLINE_WEBHOOK_EVENT,
        SIGNATURE_HEADER,
        TIMESTAMP_HEADER,
        build_offline_webhook_payload,
        format_offline_webhook_message,
        load_offline_webhook_receive_rules,
        load_offline_webhook_receiver_server,
        load_offline_webhook_senders,
        parse_webhook_payload,
        send_offline_webhook,
        verify_webhook_signature,
    )
    from .core.roleplay_knowledge import (
        ROLEPLAY_KNOWLEDGE_TOOL_NAME,
        RoleplayKnowledgeBase,
        ROLEPLAY_KNOWLEDGE_DB_FILENAME,
        format_roleplay_search_results,
        load_roleplay_knowledge_config,
        select_roleplay_database,
    )
except ImportError:
    from core.Filter import register_pack_type
    from core.ai_voice import (
        AI_VOICE_TOOL_NAME,
        AiVoiceClient,
        AiVoiceError,
        build_ai_voice_config,
    )
    from core.group_history import (
        GROUP_HISTORY_EMPTY_ERROR,
        GROUP_HISTORY_FORMAT_ERROR,
        GROUP_HISTORY_HELP_COMMAND,
        GROUP_HISTORY_HELP_TEXT,
        build_group_history_nodes,
        get_qq_nickname,
        parse_group_history_components,
        parse_group_history_text,
    )
    from core.document_parse import (
        DOCUMENT_PARSE_DISABLED_MESSAGE,
        DOCUMENT_PARSE_MISSING_FILE_MESSAGE,
        DOCUMENT_PARSE_PATH_DISABLED_MESSAGE,
        DOCUMENT_PARSE_TOOL_NAME,
        build_document_parse_config,
        collect_document_candidates,
        format_parsed_document,
        parse_local_document,
    )
    from core.keyword_voice import load_group_keyword_voices
    from core.love_message import (
        choose_love_message,
        format_love_message,
        load_love_messages,
    )
    from core.music_search import (
        MUSIC_AUDIO_UNAVAILABLE_MESSAGE,
        MUSIC_DETAIL_ERROR_MESSAGE,
        MUSIC_LOGIN_API_ERROR_MESSAGE,
        MUSIC_LOGIN_EXPIRED_MESSAGE,
        MUSIC_LOGIN_NO_COOKIE_MESSAGE,
        MUSIC_LOGIN_QR_MESSAGE,
        MUSIC_LOGIN_SUCCESS_MESSAGE,
        MUSIC_LOGIN_TIMEOUT_MESSAGE,
        MUSIC_SEARCH_API_ERROR_MESSAGE,
        MUSIC_SEARCH_DISABLED_MESSAGE,
        MUSIC_SEARCH_EMPTY_MESSAGE,
        MUSIC_SEARCH_USAGE,
        MUSIC_SELECTION_EXPIRED_MESSAGE,
        MUSIC_SELECTION_INVALID_MESSAGE,
        NeteaseMusicAPI,
        PendingMusicSelection,
        build_music_config,
        format_search_results,
        format_song_detail,
        load_persisted_music_cookie,
        pending_selection_is_expired,
        save_persisted_music_cookie,
        save_qr_image,
    )
    from core.offline_email_alert import (
        OFFLINE_EMAIL_SUBJECT,
        QQMAIL_ACTIONS,
        QQMAIL_TOOL_NAME,
        build_offline_email_alert_config,
        build_qqmail_tool_config,
        format_offline_email_content,
        is_bot_offline_notice,
        parse_email_addresses,
        qqmail_list_async,
        qqmail_read_async,
        qqmail_search_async,
        qqmail_trash_async,
        send_qq_email_async,
    )
    from core.offline_webhook_alert import (
        OFFLINE_WEBHOOK_EVENT,
        SIGNATURE_HEADER,
        TIMESTAMP_HEADER,
        build_offline_webhook_payload,
        format_offline_webhook_message,
        load_offline_webhook_receive_rules,
        load_offline_webhook_receiver_server,
        load_offline_webhook_senders,
        parse_webhook_payload,
        send_offline_webhook,
        verify_webhook_signature,
    )
    from core.roleplay_knowledge import (
        ROLEPLAY_KNOWLEDGE_TOOL_NAME,
        RoleplayKnowledgeBase,
        ROLEPLAY_KNOWLEDGE_DB_FILENAME,
        format_roleplay_search_results,
        load_roleplay_knowledge_config,
        select_roleplay_database,
    )


SUPPORTED_KEYWORD_VOICE_SUFFIXES = {
    ".amr",
    ".m4a",
    ".mp3",
    ".ogg",
    ".silk",
    ".wav",
}

PLUGIN_ROOT = Path(__file__).resolve().parent
LOVE_MESSAGES_PATH = (PLUGIN_ROOT / "core" / "love_messages.txt").resolve()
PLUGIN_DATA_DIR = (Path(get_astrbot_plugin_data_path()) / "astrbot_plugin_util").resolve()
NETEASE_LOGIN_DATA_DIR = (PLUGIN_DATA_DIR / "netease_login").resolve()
NETEASE_COOKIE_PATH = (NETEASE_LOGIN_DATA_DIR / "cookie.json").resolve()
AI_VOICE_DATA_DIR = (PLUGIN_DATA_DIR / "ai_voice").resolve()
ROLEPLAY_KNOWLEDGE_ROOT = (PLUGIN_ROOT / "cs" / "output").resolve()
ROLEPLAY_KNOWLEDGE_DB_RELATIVE_PATH = (
    Path("roleplay_knowledge") / ROLEPLAY_KNOWLEDGE_DB_FILENAME
)
ROLEPLAY_KNOWLEDGE_DB_PATH = ROLEPLAY_KNOWLEDGE_DB_RELATIVE_PATH
FORWARD_NODES_BATCH_SIZE = 100
NETEASE_MUSIC_TOOL_NAME = "netease_music"


@register("util", "lishinig", "私人插件", "1.6.45")
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

        self.ema_poke_responses = [
            # 正常态
            "诶？怎么了？",
            "啊、我在。",
            "嗯？有什么事吗？",
            "……你找我？",
            "欸、等一下——",
            "啊，对不起，我是不是走神了。",
            # 轻微不耐烦
            "那个……是我做错什么了吗？",
            "能不能先告诉我发生了什么……",
            "我、我在听，真的在听。",
            "对不起，我再认真一点。",
            "你生气了吗？",
            "不要不说话……",
            # 高压态
            "对不起、对不起，我真的不是故意的——",
            "你是不是讨厌我了？",
            "不要丢下我……",
            "我会改的，告诉我哪里不对。",
            "求你了，别这样看着我。",
            "我真的不想再被丢下了。",
            "哪怕再给我一次机会也好……",
            # 保留项
            "喵~",
            "……嗯，我还在。",
            "pack",
        ]

        self.ema_poke_weights = np.array(
            [
                # 正常态
                7.0,
                6.5,
                6.0,
                5.5,
                6.5,
                5.0,
                # 轻微不耐烦
                8.0,
                7.5,
                7.0,
                6.5,
                7.0,
                5.0,
                # 高压态
                9.0,
                8.5,
                8.0,
                7.5,
                7.0,
                8.0,
                7.5,
                # 保留项
                4.0,  # 喵
                5.0,  # 还在
                5.0,  # 眼泪
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

        self.no_split_keywords = ("zssm", "这是什么")

        def config_section(name: str) -> dict:
            value = config.get(name, {})
            return dict(value) if isinstance(value, Mapping) else {}

        def config_value(section_config: dict, key: str, default):
            if key in section_config:
                return section_config.get(key, default)
            return config.get(key, default)

        history_config = config_section("history_chunking")
        stream_config = config_section("stream_output")
        debug_config = config_section("debug_logging")
        li_config = config_section("li_handoff")
        group_history_config = config_section("group_history")
        music_search_config = config_section("music_search")
        ai_voice_config = config_section("ai_voice")
        offline_email_alert_config = config_section("offline_email_alert")
        qq_mail_tool_config = config_section("qq_mail_tool")
        roleplay_knowledge_config = config_section("roleplay_knowledge")
        document_parse_config = config_section("document_parse")

        self.enable_history_chunking_feature = config_value(
            history_config,
            "enable_history_chunking_feature",
            True,
        )
        self.enable_history_message_chunking = config_value(
            history_config,
            "enable_history_message_chunking",
            True,
        )
        self.history_message_chunk_length = max(
            1,
            int(config_value(history_config, "history_message_chunk_length", 100)),
        )
        self.enable_history_read_tool = config_value(
            history_config,
            "enable_history_read_tool",
            True,
        )
        self.remove_history_read_tool_before_llm = config_value(
            history_config,
            "remove_history_read_tool_before_llm",
            False,
        )
        self.history_read_tool_default_count = max(
            1,
            int(config_value(history_config, "history_read_tool_default_count", 6)),
        )
        self.enable_human_like_stream_delay = config_value(
            stream_config,
            "enable_human_like_stream_delay",
            True,
        )
        self.enable_forward_when_too_long = config_value(
            stream_config,
            "enable_forward_when_too_long",
            False,
        )
        self.forward_text_length_threshold = max(
            1,
            int(config_value(stream_config, "forward_text_length_threshold", 200)),
        )
        self.enable_forward_when_too_many_segments = config_value(
            stream_config,
            "enable_forward_when_too_many_segments",
            False,
        )
        self.forward_segment_count_threshold = max(
            1,
            int(config_value(stream_config, "forward_segment_count_threshold", 5)),
        )
        self.enable_llm_request_debug_log = config_value(
            debug_config,
            "enable_llm_request_debug_log",
            False,
        )
        self.enable_final_history_log = config_value(
            debug_config,
            "enable_final_history_log",
            False,
        )
        self.enable_full_provider_request_log = config_value(
            debug_config,
            "enable_full_provider_request_log",
            False,
        )
        self._scoped_request_history_cache: dict[str, list[str]] = {}
        self.stream_delay_min_seconds = max(
            0.0,
            float(config_value(stream_config, "stream_delay_min_seconds", 0.35)),
        )
        self.stream_delay_max_seconds = max(
            self.stream_delay_min_seconds,
            float(config_value(stream_config, "stream_delay_max_seconds", 1.2)),
        )
        self.enable_let_li_speak_tool = config_value(
            li_config,
            "enable_let_li_speak_tool",
            True,
        )
        self.li_platform_id = (
            config_value(li_config, "li_platform_id", "").strip() or None
        )
        self.enable_group_history_feature = config_value(
            group_history_config,
            "enable_group_history_feature",
            True,
        )
        self.roleplay_knowledge_config = load_roleplay_knowledge_config(
            roleplay_knowledge_config
        )
        self.roleplay_knowledge_base = RoleplayKnowledgeBase.from_root(
            ROLEPLAY_KNOWLEDGE_ROOT,
            ROLEPLAY_KNOWLEDGE_DB_RELATIVE_PATH,
            base_dir=PLUGIN_ROOT,
        )
        roleplay_db_path = self.roleplay_knowledge_base.db_path
        roleplay_db_exists = roleplay_db_path.exists()
        roleplay_db_size = roleplay_db_path.stat().st_size if roleplay_db_exists else 0
        logger.info(
            "[util] roleplay knowledge DB ready: "
            f"enabled={self.roleplay_knowledge_config.enabled}, "
            f"db_path={roleplay_db_path}, "
            f"db_exists={roleplay_db_exists}, "
            f"db_size={roleplay_db_size}, "
            f"source_root={ROLEPLAY_KNOWLEDGE_ROOT}, "
            f"source_exists={self.roleplay_knowledge_base.last_source_exists}, "
            f"source_markdown_count={self.roleplay_knowledge_base.last_source_markdown_count}, "
            f"rebuild_loaded={self.roleplay_knowledge_base.last_rebuild_document_count}, "
            f"rebuild_skipped={self.roleplay_knowledge_base.last_rebuild_skipped}, "
            f"total={self.roleplay_knowledge_base.count()}, "
            f"ema={self.roleplay_knowledge_base.count('ema')}, "
            f"hiro={self.roleplay_knowledge_base.count('hiro')}"
        )
        self._roleplay_knowledge_turn_index = 0
        self._roleplay_knowledge_recent_sources: dict[
            str, deque[tuple[int, str]]
        ] = {}
        self.offline_email_alert_config = build_offline_email_alert_config(
            offline_email_alert_config
        )
        self.qqmail_tool_config = build_qqmail_tool_config(qq_mail_tool_config)
        self.document_parse_config = build_document_parse_config(document_parse_config)
        self.offline_webhook_senders = load_offline_webhook_senders(config)
        self.offline_webhook_receiver_server = load_offline_webhook_receiver_server(
            config
        )
        self.offline_webhook_receive_rules = load_offline_webhook_receive_rules(config)
        self._offline_webhook_runner: web.AppRunner | None = None
        self.ai_voice_config = build_ai_voice_config(ai_voice_config)
        self.ai_voice_client = AiVoiceClient(self.ai_voice_config, AI_VOICE_DATA_DIR)
        logger.info(
            "[util] ai voice tool: "
            f"enabled={self.ai_voice_config.enabled}, "
            f"ready={self.ai_voice_config.ready}, "
            f"api_base_url={self.ai_voice_config.api_base_url}, "
            f"audio_id_configured={bool(self.ai_voice_config.audio_id)}, "
            f"token_configured={bool(self.ai_voice_config.token)}, "
            f"model={self.ai_voice_config.model}, "
            f"audio_format={self.ai_voice_config.audio_format}, "
            f"sample_rate={self.ai_voice_config.sample_rate}, "
            f"language={self.ai_voice_config.language or '<auto>'}, "
            f"instruction_configured={bool(self.ai_voice_config.instruction)}, "
            f"max_text_chars={self.ai_voice_config.max_text_chars}, "
            f"max_instruction_chars={self.ai_voice_config.max_instruction_chars}"
        )
        logger.info(
            "[util] QQ mail tool: "
            f"enabled={self.qqmail_tool_config.enabled}, "
            f"ready={self.qqmail_tool_config.ready}, "
            f"sender_configured={bool(self.qqmail_tool_config.sender)}, "
            f"display_name_configured={bool(self.qqmail_tool_config.display_name)}, "
            f"password_configured={bool(self.qqmail_tool_config.QQ_password)}, "
            f"default_limit={self.qqmail_tool_config.list_default_limit}"
        )
        self.music_search_config = build_music_config(music_search_config)
        persisted_music_cookie = load_persisted_music_cookie(NETEASE_COOKIE_PATH)
        if persisted_music_cookie:
            self.music_search_config = replace(
                self.music_search_config,
                cookie=persisted_music_cookie,
            )
        self.music_pending_selections: dict[str, PendingMusicSelection] = {}
        self.music_song_cache: dict[str, list[dict]] = {}
        self.group_keyword_voices = load_group_keyword_voices(config)
        self.love_messages = load_love_messages(LOVE_MESSAGES_PATH)
        self._li_takeover_next_turn_keys: set[str] = set()
        self._li_reply_capture_futures: dict[str, asyncio.Future[str]] = {}

    async def initialize(self) -> None:
        await self._start_offline_webhook_receiver()

    async def terminate(self) -> None:
        await self._stop_offline_webhook_receiver()

    async def _start_offline_webhook_receiver(self) -> None:
        settings = self.offline_webhook_receiver_server
        if not settings.enabled:
            return

        ready_rules = [
            rule
            for rule in self.offline_webhook_receive_rules
            if rule.enabled and rule.is_ready
        ]
        if not ready_rules:
            logger.warning("[util] 离线 webhook 接收端已开启，但没有可用接收规则。")
            return

        app = web.Application()
        app.router.add_post(settings.path, self._handle_offline_webhook_request)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, settings.listen_host, settings.listen_port)
        await site.start()
        self._offline_webhook_runner = runner
        logger.info(
            "[util] 离线 webhook 接收端已启动: http://%s:%s%s rules=%s",
            settings.listen_host,
            settings.listen_port,
            settings.path,
            len(ready_rules),
        )

    async def _stop_offline_webhook_receiver(self) -> None:
        if self._offline_webhook_runner is None:
            return
        await self._offline_webhook_runner.cleanup()
        self._offline_webhook_runner = None
        logger.info("[util] 离线 webhook 接收端已停止。")

    async def _handle_offline_webhook_request(self, request: web.Request) -> web.Response:
        body = await request.read()
        timestamp = request.headers.get(TIMESTAMP_HEADER, "")
        signature = request.headers.get(SIGNATURE_HEADER, "")
        matched_rules = [
            rule
            for rule in self.offline_webhook_receive_rules
            if rule.enabled
            and rule.is_ready
            and verify_webhook_signature(
                secret=rule.secret,
                body=body,
                timestamp=timestamp,
                signature=signature,
            )
        ]
        if not matched_rules:
            logger.warning("[util] 离线 webhook 接收端拒绝请求：签名无效。")
            return web.json_response({"ok": False, "error": "invalid signature"}, status=401)

        try:
            payload = parse_webhook_payload(body)
        except Exception:
            logger.warning("[util] 离线 webhook 接收端拒绝请求：JSON 无效。")
            return web.json_response({"ok": False, "error": "invalid json"}, status=400)

        if payload.get("event") != OFFLINE_WEBHOOK_EVENT:
            return web.json_response({"ok": True, "ignored": True})

        sent_count = 0
        for rule in matched_rules:
            message = format_offline_webhook_message(payload, rule)
            components = self._build_offline_webhook_components(
                message,
                rule.at_targets,
            )
            try:
                sent = await self.context.send_message(
                    rule.target_session,
                    MessageChain(components),
                )
            except Exception as exc:
                logger.error(
                    "[util] 离线 webhook 接收端主动发送失败: rule=%s target=%s error=%s",
                    rule.name,
                    rule.target_session,
                    exc,
                    exc_info=True,
                )
                continue
            if sent:
                sent_count += 1
                logger.info(
                    "[util] 离线 webhook 接收端已发送提醒: rule=%s target=%s self_id=%s",
                    rule.name,
                    rule.target_session,
                    payload.get("self_id", ""),
                )
            else:
                logger.warning(
                    "[util] 离线 webhook 接收端未找到目标机器人: rule=%s target=%s",
                    rule.name,
                    rule.target_session,
                )

        return web.json_response({"ok": True, "matched": len(matched_rules), "sent": sent_count})

    @staticmethod
    def _build_offline_webhook_components(
        message: str,
        at_targets: tuple[str, ...],
    ) -> list:
        components = []
        for target in at_targets:
            normalized_target = str(target).strip()
            if not normalized_target:
                continue
            if normalized_target.lower() == "all":
                components.append(Comp.AtAll())
            else:
                components.append(Comp.At(qq=normalized_target))
        if components:
            components.append(Comp.Plain("\n" + message))
        else:
            components.append(Comp.Plain(message))
        return components

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP, priority=10000)
    @filter.event_message_type(filter.EventMessageType.ALL, priority=10000)
    async def notify_bot_offline_email(self, event: AiocqhttpMessageEvent):
        """Send an email alert when AIOCQHTTP reports that the bot account is offline."""
        raw_message = getattr(event.message_obj, "raw_message", None)
        if not is_bot_offline_notice(raw_message):
            return

        if self.offline_email_alert_config.enabled:
            if not self.offline_email_alert_config.is_ready:
                logger.warning("[util] 账号下线邮件通知配置不完整，已跳过发送。")
            else:
                try:
                    await send_qq_email_async(
                        sender=self.offline_email_alert_config.sender,
                        password=self.offline_email_alert_config.QQ_password,
                        receiver=self.offline_email_alert_config.receiver,
                        subject=OFFLINE_EMAIL_SUBJECT,
                        content=format_offline_email_content(raw_message),
                    )
                    logger.info(
                        "[util] 已发送账号下线邮件通知: self_id=%s user_id=%s",
                        raw_message.get("self_id", ""),
                        raw_message.get("user_id", ""),
                    )
                except Exception as exc:
                    logger.error("[util] 账号下线邮件通知发送失败: %s", exc)

        await self._send_offline_webhook_alerts(raw_message)

    async def _send_offline_webhook_alerts(self, raw_message: Mapping[str, Any]) -> None:
        senders = [
            sender
            for sender in getattr(self, "offline_webhook_senders", [])
            if sender.enabled and sender.is_ready
        ]
        if not senders:
            return

        payload = build_offline_webhook_payload(raw_message)
        for sender in senders:
            try:
                await send_offline_webhook(sender, payload)
            except Exception as exc:
                logger.error(
                    "[util] 离线 webhook 推送失败: sender=%s url=%s error=%s",
                    sender.name,
                    sender.webhook_url,
                    exc,
                    exc_info=True,
                )
                continue
            logger.info(
                "[util] 已推送离线 webhook: sender=%s url=%s self_id=%s",
                sender.name,
                sender.webhook_url,
                payload.get("self_id", ""),
            )

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    async def handoff_next_ni_turn_to_li(self, event: AiocqhttpMessageEvent):
        """Forward the next ni message to Li after let_li_speak is used."""
        if not self.enable_let_li_speak_tool:
            return

        if event.get_platform_id() != "ni":
            return

        takeover_key = self._li_takeover_key(event)
        if takeover_key not in self._li_takeover_next_turn_keys:
            return

        if not event.is_at_or_wake_command:
            return

        current_message = event.message_str or event.get_message_outline() or ""
        if not current_message.strip():
            return

        self._li_takeover_next_turn_keys.discard(takeover_key)
        content = self._build_li_takeover_content(event)
        ok, error_message, _ = await self._dispatch_li_native_content(event, content)
        if not ok:
            logger.warning(
                "[util] handoff_next_ni_turn_to_li: failed to dispatch Li event: %s",
                error_message,
            )
            event.should_call_llm(True)
            event.stop_event()
            yield event.plain_result(error_message)
            return

        event.should_call_llm(True)
        event.stop_event()
        logger.info(
            "[util] handoff_next_ni_turn_to_li: Li took over ni turn %s",
            takeover_key,
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
        platform_id = getattr(getattr(event, "platform_meta", None), "id", None)

        if platform_id == "ni":
            responses = self.ema_poke_responses
            weights = self.ema_poke_weights
        else:
            responses = self.poke_responses
            weights = self.poke_weights

        if (
            not bot_id
            or not sender_id
            or not target_id
            or str(target_id) != str(bot_id)
        ):
            return
        text = await self.weighted_random_choice(responses, weights)
        logger.info(f"检测到戳一戳，期望发送文本:{text}")
        if text == "pack":
            payloads = {"user_id": sender_id}
            if group_id:
                payloads["group_id"] = group_id
            bot = getattr(event, "bot", None)
            if bot is None:
                text = await self.weighted_random_choice(responses[:-1], weights[:-1])
                logger.info(f"机器人不是AIOCQHTTP，期望发送文本:{text}")
                yield event.plain_result(text)
            else:
                await bot.api.call_action("send_poke", **payloads)
        else:
            yield event.plain_result(text)

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.command("土味情话")
    async def send_random_love_message(
        self,
        event: AiocqhttpMessageEvent,
        qq: str = "",
    ):
        """使用 /土味情话 [QQ号|@用户] 向目标发送随机情话。"""
        if not self.love_messages:
            logger.warning("[util] 土味情话词库为空")
            return

        target_id, _ = self._resolve_love_message_target(event, qq)
        if not target_id:
            yield event.plain_result("未找到有效目标喵。")
            return

        message = choose_love_message(self.love_messages)
        if message is None:
            logger.warning("[util] 无法从土味情话词库选择内容")
            return

        output = format_love_message(message)
        if not output:
            return

        yield event.chain_result(
            [
                Comp.At(qq=target_id),
                Comp.Plain(f" {output}"),
            ]
        )

    def _resolve_love_message_target(
        self,
        event: AstrMessageEvent,
        qq: str = "",
    ) -> tuple[str | None, str | None]:
        """显式QQ优先，其次@目标，最后回退到发送者。"""
        qq_candidate = str(qq or "").strip()
        if qq_candidate:
            if self._validate_qq(qq_candidate):
                return qq_candidate, None
            logger.warning("[util] 土味情话显式QQ参数无效: %s", qq_candidate)

        mention_targets = self._extract_love_message_mentions(event)
        if mention_targets["non_bot"]:
            return mention_targets["non_bot"][-1]
        if mention_targets["bot"]:
            return mention_targets["bot"][-1]

        sender_id = str(event.get_sender_id() or "").strip()
        if self._validate_qq(sender_id):
            return sender_id, event.get_sender_name() or None
        return None, None

    def _extract_love_message_mentions(
        self,
        event: AstrMessageEvent,
    ) -> dict[str, list[tuple[str, str | None]]]:
        self_ids = self._love_message_bot_ids(event)
        targets: dict[str, list[tuple[str, str | None]]] = {
            "non_bot": [],
            "bot": [],
        }
        for component in event.get_messages():
            if not isinstance(component, Comp.At):
                continue
            mentioned_id = str(component.qq or "").strip()
            if (
                not mentioned_id
                or mentioned_id.casefold() == "all"
                or not self._validate_qq(mentioned_id)
            ):
                continue
            mentioned_name = str(getattr(component, "name", "") or "").strip() or None
            key = "bot" if mentioned_id in self_ids else "non_bot"
            targets[key].append((mentioned_id, mentioned_name))
        return targets

    @staticmethod
    def _love_message_bot_ids(event: AstrMessageEvent) -> set[str]:
        self_ids: set[str] = set()
        self_id = str(event.get_self_id() or "").strip()
        if self_id:
            self_ids.add(self_id)
        raw_message = getattr(event.message_obj, "raw_message", None)
        if isinstance(raw_message, dict) and raw_message.get("self_id"):
            self_ids.add(str(raw_message["self_id"]))
        return self_ids

    @filter.command("网易云登录", alias={"音乐登录", "点歌登录"})
    async def login_netease_music_command(self, event: AstrMessageEvent):
        """Send a NetEase Cloud Music QR code and persist the returned cookie."""
        event.stop_event()
        api = self._music_api()
        try:
            login = await api.create_qr_login()
            qr_path = save_qr_image(
                login.qr_image,
                NETEASE_LOGIN_DATA_DIR,
                login.key,
            )
        except Exception as exc:
            logger.warning("[util] 网易云扫码登录二维码生成失败: %s", exc)
            await event.send(MessageChain([Comp.Plain(MUSIC_LOGIN_API_ERROR_MESSAGE)]))
            return

        await event.send(MessageChain([Comp.Image.fromFileSystem(str(qr_path))]))
        await event.send(MessageChain([Comp.Plain(MUSIC_LOGIN_QR_MESSAGE)]))

        deadline = asyncio.get_running_loop().time() + 120
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(3)
            try:
                status = await api.check_qr_login(login.key)
            except Exception as exc:
                logger.warning("[util] 网易云扫码登录状态检查失败: %s", exc)
                await event.send(MessageChain([Comp.Plain(MUSIC_LOGIN_API_ERROR_MESSAGE)]))
                return

            if status.code == 803:
                if not status.cookie:
                    await event.send(MessageChain([Comp.Plain(MUSIC_LOGIN_NO_COOKIE_MESSAGE)]))
                    return
                self._save_music_cookie(status.cookie)
                await event.send(MessageChain([Comp.Plain(MUSIC_LOGIN_SUCCESS_MESSAGE)]))
                return

            if status.code == 800:
                await event.send(MessageChain([Comp.Plain(MUSIC_LOGIN_EXPIRED_MESSAGE)]))
                return

        await event.send(MessageChain([Comp.Plain(MUSIC_LOGIN_TIMEOUT_MESSAGE)]))

    @filter.command("点歌", alias={"music", "听歌", "网易云"})
    async def search_music_command(self, event: AstrMessageEvent, keyword: str = ""):
        """Search music and wait for a numeric selection."""
        keyword = self._music_search_keyword_from_event(event, keyword)
        yield event.plain_result(await self._search_music_and_cache(event, keyword))

    @filter.regex(r"^\d+$", priority=999)
    async def select_music_command(self, event: AstrMessageEvent):
        """Handle numeric selection after /点歌."""
        session_id = event.get_session_id()
        selection = self.music_pending_selections.get(session_id)
        if selection is None:
            return

        if pending_selection_is_expired(
            selection,
            now=asyncio.get_running_loop().time(),
        ):
            self._remove_music_selection(session_id, selection.cache_key)
            yield event.plain_result(MUSIC_SELECTION_EXPIRED_MESSAGE)
            return

        try:
            selected_index = int(str(event.message_str).strip())
        except ValueError:
            return

        result = await self._select_cached_music(event, selected_index, stop_event=True)
        if result != "点歌已发送。":
            yield event.plain_result(result)

    async def _send_music_record(self, event: AstrMessageEvent, audio_url: str) -> None:
        logger.info("[util] 准备发送点歌音频: %s", audio_url)
        try:
            await event.send(MessageChain([Comp.Record.fromURL(audio_url)]))
        except Exception as exc:
            logger.error("[util] 点歌音频发送失败: %s", exc, exc_info=True)
            await event.send(
                MessageChain(
                    [
                        Comp.Plain(
                            f"音频发送失败，请点击播放链接：{audio_url}",
                        )
                    ]
                )
            )

    async def _search_music_and_cache(
        self,
        event: AstrMessageEvent,
        keyword: str,
    ) -> str:
        if not self.music_search_config.enabled:
            return MUSIC_SEARCH_DISABLED_MESSAGE

        keyword = str(keyword or "").strip()
        if not keyword:
            return MUSIC_SEARCH_USAGE

        api = self._music_api()
        try:
            songs = await api.search_songs(
                keyword,
                self.music_search_config.search_limit,
            )
        except Exception as exc:
            logger.warning("[util] 音乐搜索失败: %s", exc)
            return MUSIC_SEARCH_API_ERROR_MESSAGE

        if not songs:
            return MUSIC_SEARCH_EMPTY_MESSAGE

        session_id = event.get_session_id()
        cache_key = f"{session_id}:{uuid.uuid4().hex}"
        self.music_song_cache[cache_key] = songs
        self.music_pending_selections[session_id] = PendingMusicSelection(
            cache_key=cache_key,
            expires_at=asyncio.get_running_loop().time()
            + self.music_search_config.selection_timeout_seconds,
        )

        return format_search_results(keyword, songs)

    async def _select_cached_music(
        self,
        event: AstrMessageEvent,
        selected_index: int,
        *,
        stop_event: bool = False,
    ) -> str:
        session_id = event.get_session_id()
        selection = self.music_pending_selections.get(session_id)
        if selection is None:
            return "没有待选择的点歌结果，请先搜索歌曲。"

        if pending_selection_is_expired(
            selection,
            now=asyncio.get_running_loop().time(),
        ):
            self._remove_music_selection(session_id, selection.cache_key)
            return MUSIC_SELECTION_EXPIRED_MESSAGE

        songs = self.music_song_cache.get(selection.cache_key, [])
        if not 1 <= selected_index <= len(songs):
            return MUSIC_SELECTION_INVALID_MESSAGE

        if stop_event:
            stop_getter = getattr(event, "stop_event", None)
            if callable(stop_getter):
                stop_getter()

        self._remove_music_selection(session_id, selection.cache_key)
        selected_song = songs[selected_index - 1]
        song_id = selected_song.get("id")

        api = self._music_api()
        try:
            song_detail = await api.get_song_detail(song_id)
            if not song_detail:
                return MUSIC_DETAIL_ERROR_MESSAGE
            audio_url = await api.get_audio_url(
                song_id,
                self.music_search_config.quality,
                self.music_search_config.cookie,
            )
        except Exception as exc:
            logger.warning("[util] 获取音乐详情失败: %s", exc)
            return MUSIC_DETAIL_ERROR_MESSAGE

        if not audio_url:
            return MUSIC_AUDIO_UNAVAILABLE_MESSAGE

        detail_text, cover_url, audio_url = format_song_detail(
            song_detail,
            audio_url,
            self.music_search_config.quality,
        )
        components: list[Any] = [Comp.Plain(detail_text)]
        if cover_url:
            components.append(Comp.Image.fromURL(cover_url))
        logger.info("[util] 准备发送点歌信息: song_id=%s, cover=%s", song_id, bool(cover_url))
        await event.send(MessageChain(components))
        await self._send_music_record(event, audio_url)
        return "点歌已发送。"

    def _music_api(self) -> NeteaseMusicAPI:
        return NeteaseMusicAPI(self.music_search_config.api_base_url)

    def _music_search_keyword_from_event(
        self,
        event: AstrMessageEvent,
        keyword: str = "",
    ) -> str:
        outline_getter = getattr(event, "get_message_outline", None)
        outline = outline_getter() if callable(outline_getter) else ""
        message = str(getattr(event, "message_str", "") or outline or "").strip()
        for command in ("点歌", "music", "听歌", "网易云"):
            match = re.match(rf"^/?{re.escape(command)}(?:\s+|$)(.*)$", message)
            if match:
                return match.group(1).strip()
        return str(keyword or "").strip()

    def _save_music_cookie(self, cookie: str) -> None:
        save_persisted_music_cookie(cookie, NETEASE_COOKIE_PATH)
        self.music_search_config = replace(self.music_search_config, cookie=cookie)

    def _remove_music_selection(self, session_id: str, cache_key: str) -> None:
        self.music_pending_selections.pop(session_id, None)
        self.music_song_cache.pop(cache_key, None)

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.command("群友史")
    async def on_group_history_request(self, event: AiocqhttpMessageEvent):
        """构造群友史聊天记录。"""
        if not self.enable_group_history_feature:
            yield event.plain_result("群友史功能已关闭。")
            return

        message_text = event.message_str

        segments = parse_group_history_components(event.message_obj)
        if not segments:
            segments = parse_group_history_text(message_text)
            if segments is None:
                yield event.plain_result(GROUP_HISTORY_FORMAT_ERROR)
                return

        nodes_list = await build_group_history_nodes(segments, event, get_qq_nickname)
        if nodes_list:
            yield event.chain_result([Comp.Nodes(nodes=nodes_list)])
        else:
            yield event.plain_result(GROUP_HISTORY_EMPTY_ERROR)

    @filter.command(GROUP_HISTORY_HELP_COMMAND)
    async def group_history_help_command(self, event: AstrMessageEvent):
        """显示群友史聊天记录构造说明。"""
        yield event.plain_result(GROUP_HISTORY_HELP_TEXT)

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    async def reply_group_keyword_voice(self, event: AiocqhttpMessageEvent):
        """按分群配置检测关键词并发送语音。"""
        group_id = str(event.get_group_id() or "").strip()
        if not group_id:
            return

        group_rules = self.group_keyword_voices.get(group_id, ())
        if not group_rules:
            return

        message = event.message_str or event.get_message_outline() or ""
        for settings in group_rules:
            configured_directory = settings.directory_for(message)
            if configured_directory is None:
                continue

            audio_directory = Path(configured_directory).expanduser()
            audio_path = self._first_audio_in_directory(audio_directory)
            if audio_path is None:
                logger.warning(
                    "[util] 群 %s 命中关键词语音配置，但目录无有效语音文件: %s",
                    group_id,
                    audio_directory,
                )
                continue

            logger.info(
                "[util] 群 %s 命中关键词语音配置: %s",
                group_id,
                audio_path,
            )
            yield event.chain_result(
                [Comp.Record.fromFileSystem(str(audio_path.resolve()))]
            )
            return

    @staticmethod
    def _first_audio_in_directory(audio_directory: Path) -> Path | None:
        if not audio_directory.is_dir():
            return None
        candidates = sorted(
            (
                path
                for path in audio_directory.iterdir()
                if path.is_file()
                and path.suffix.casefold() in SUPPORTED_KEYWORD_VOICE_SUFFIXES
            ),
            key=lambda path: path.name.casefold(),
        )
        return candidates[0] if candidates else None

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    async def replyMessage(self, event: AiocqhttpMessageEvent):
        """获取所有消息，进行贴表情"""
        raw_message = getattr(event.message_obj, "raw_message", None)
        if not isinstance(raw_message, dict):
            return
        if raw_message.get("message_type") != "group":
            return
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
        try:
            await bot.api.call_action("set_msg_emoji_like", **payloads)
        except Exception as exc:
            logger.warning("[util] 设置消息表情回应失败: %s", exc)

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

    @filter.on_llm_request(priority=-5000)
    async def apply_history_tool_config(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
    ):
        self._advance_roleplay_knowledge_turn(event)

        if self.remove_history_read_tool_before_llm:
            self._remove_history_read_tool_from_request(req)

        if event.get_platform_id() != "ni" or not self.enable_let_li_speak_tool:
            self._remove_tool_from_request(req, "let_li_speak")

        ai_voice_config = getattr(self, "ai_voice_config", None)
        if ai_voice_config is None or not ai_voice_config.ready:
            self._remove_tool_from_request(req, AI_VOICE_TOOL_NAME)

        mail_config = getattr(self, "qqmail_tool_config", None)
        if (
            mail_config is None
            or not mail_config.ready
        ):
            self._remove_tool_from_request(req, QQMAIL_TOOL_NAME)

        document_config = getattr(self, "document_parse_config", None)
        if document_config is None or not document_config.enabled:
            self._remove_tool_from_request(req, DOCUMENT_PARSE_TOOL_NAME)

        music_config = getattr(self, "music_search_config", None)
        if music_config is None or not music_config.enabled:
            self._remove_tool_from_request(req, NETEASE_MUSIC_TOOL_NAME)

        if not self.roleplay_knowledge_config.enabled:
            self._remove_tool_from_request(req, ROLEPLAY_KNOWLEDGE_TOOL_NAME)

        if not self.enable_history_chunking_feature:
            self._scoped_request_history_cache[
                self._request_scope_cache_key(event)
            ] = []
            return

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
        if (
            not self.enable_final_history_log
            and not self.enable_llm_request_debug_log
            and not self.enable_full_provider_request_log
        ):
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

        if self.enable_full_provider_request_log:
            logger.info(
                "[util] final ProviderRequest full attributes:\n"
                f"{self._json_dumps_for_log(self._provider_request_public_attrs(req))}"
            )

    def _build_li_session(self, event: AstrMessageEvent) -> MessageSession:
        """从艾玛的 event 构造希罗的 MessageSession，保持相同的 message_type 和 session_id。"""
        ni_session = event.session
        return MessageSession(
            platform_name="aiocqhttp",
            message_type=ni_session.message_type,
            session_id=ni_session.session_id,
        )

    def _build_li_native_session(
        self,
        event: AstrMessageEvent,
        li_platform,
    ) -> MessageSession:
        """Build the target Li session from the current message surface."""
        message_type = event.get_message_type()
        session_id = event.session.session_id
        if message_type == MessageType.GROUP_MESSAGE:
            session_id = event.get_group_id() or session_id.split("_")[-1]
        elif event.get_sender_id():
            session_id = event.get_sender_id()

        return MessageSession(
            platform_name=li_platform.meta().id,
            message_type=message_type,
            session_id=session_id,
        )

    def _get_li_conf(self, li_umo: str):
        return self.context.astrbot_config_mgr.get_conf(li_umo)

    def _get_effective_li_provider_wake_prefix(self, li_conf) -> str:
        provider_settings = li_conf.get("provider_settings", {}) or {}
        provider_wake_prefix = provider_settings.get("wake_prefix", "") or ""
        wake_prefixes = li_conf.get("wake_prefix", []) or []
        for wake_prefix in wake_prefixes:
            if wake_prefix and provider_wake_prefix.startswith(wake_prefix):
                return provider_wake_prefix[len(wake_prefix) :]
        return provider_wake_prefix

    def _li_takeover_key(self, event: AstrMessageEvent) -> str:
        sender_id = event.get_sender_id() or "unknown"
        return f"{event.unified_msg_origin}:sender:{sender_id}"

    def _build_li_event_info_text(self, event: AstrMessageEvent) -> str:
        event_info = {
            "platform_id": event.get_platform_id(),
            "platform_name": event.get_platform_name(),
            "message_type": str(event.get_message_type()),
            "session": str(event.session),
            "session_id": event.get_session_id(),
            "sender_id": event.get_sender_id(),
            "sender_name": event.get_sender_name(),
            "group_id": event.get_group_id(),
            "self_id": event.get_self_id(),
            "role": getattr(event, "role", None),
            "is_wake": getattr(event, "is_wake", None),
            "is_at_or_wake_command": getattr(event, "is_at_or_wake_command", None),
            "message_outline": event.get_message_outline(),
            "message_obj": getattr(
                event.message_obj, "__dict__", str(event.message_obj)
            ),
            "extras": event.get_extra(default={}),
            "event_attrs": vars(event),
        }
        return self._json_dumps_for_log(event_info)

    def _build_li_dialogue_content(
        self,
        event: AstrMessageEvent,
        prompt: str,
        response_summary: str = "",
    ) -> str:
        sender_id = event.get_sender_id() or "unknown"
        user_message = event.message_str or event.get_message_outline() or ""
        event_info_text = self._build_li_event_info_text(event)
        dialogue_lines = [
            "这是一条由艾玛通过工具调用转交给希罗的对话消息。",
            "请希罗把它当作当前会话里的一次真实对话触发来处理，并结合希罗自己当前会话的历史记录回复。",
            "",
            "本轮 ni 侧对话：",
            f"{sender_id}:{user_message}",
        ]
        response_summary = (response_summary or "").strip()
        if response_summary:
            dialogue_lines.append(f"艾玛:{response_summary}")
        dialogue_lines.extend(
            [
                f"艾玛:{prompt}",
                "",
                "ni 侧事件信息：",
                event_info_text,
            ],
        )
        return "\n".join(dialogue_lines)

    def _build_li_takeover_content(self, event: AstrMessageEvent) -> str:
        sender_id = event.get_sender_id() or "unknown"
        user_message = event.message_str or event.get_message_outline() or ""
        event_info_text = self._build_li_event_info_text(event)
        return "\n".join(
            [
                "这是希罗接管 ni 会话后的下一轮用户消息。",
                "这句话原本是对艾玛（ni）说的，不是用户直接对希罗说的；请希罗理解为自己正在替艾玛接过这一轮对话。",
                "请希罗把它当作当前会话里的一次真实对话触发来处理，并结合希罗自己当前会话的历史记录回复。",
                "",
                "本轮 ni 侧对话：",
                f"{sender_id}:{user_message}",
                "",
                "ni 侧事件信息：",
                event_info_text,
            ],
        )

    def _build_li_native_prompt(
        self,
        li_conf,
        event: AstrMessageEvent,
        prompt: str,
        response_summary: str = "",
    ) -> str:
        wake_prefixes = li_conf.get("wake_prefix", []) or []
        bot_wake_prefix = next(
            (prefix for prefix in wake_prefixes if isinstance(prefix, str) and prefix),
            "",
        )
        provider_wake_prefix = self._get_effective_li_provider_wake_prefix(li_conf)
        dialogue_content = self._build_li_dialogue_content(
            event,
            prompt,
            response_summary,
        )
        return f"{bot_wake_prefix}{provider_wake_prefix}{dialogue_content}"

    def _build_li_native_prompt_from_content(self, li_conf, content: str) -> str:
        wake_prefixes = li_conf.get("wake_prefix", []) or []
        bot_wake_prefix = next(
            (prefix for prefix in wake_prefixes if isinstance(prefix, str) and prefix),
            "",
        )
        provider_wake_prefix = self._get_effective_li_provider_wake_prefix(li_conf)
        return f"{bot_wake_prefix}{provider_wake_prefix}{content}"

    def _build_li_native_message(
        self,
        event: AstrMessageEvent,
        li_session: MessageSession,
        li_platform,
        native_prompt: str,
    ) -> AstrBotMessage:
        abm = AstrBotMessage()
        abm.self_id = str(
            getattr(getattr(li_platform, "bot", None), "self_id", "")
            or getattr(li_platform, "client_self_id", "")
            or event.get_self_id()
            or ""
        )
        abm.sender = MessageMember(
            user_id=event.get_sender_id() or "0",
            nickname=event.get_sender_name() or event.get_sender_id() or "unknown",
        )
        abm.type = li_session.message_type
        abm.session_id = li_session.session_id
        abm.message_id = f"util-li-native-{uuid.uuid4().hex}"
        abm.message_str = native_prompt
        abm.message = [Comp.Plain(native_prompt)]
        if li_session.message_type == MessageType.GROUP_MESSAGE:
            abm.group_id = li_session.session_id.split("_")[-1]
            if abm.self_id:
                abm.message.insert(0, Comp.At(qq=abm.self_id))

        raw_message_type = (
            "group"
            if li_session.message_type == MessageType.GROUP_MESSAGE
            else "private"
        )
        raw_segments = [{"type": "text", "data": {"text": native_prompt}}]
        if li_session.message_type == MessageType.GROUP_MESSAGE and abm.self_id:
            raw_segments.insert(0, {"type": "at", "data": {"qq": abm.self_id}})
        abm.raw_message = {
            "post_type": "message",
            "message_type": raw_message_type,
            "self_id": abm.self_id,
            "user_id": abm.sender.user_id,
            "group_id": abm.group_id,
            "message_id": abm.message_id,
            "raw_message": native_prompt,
            "message": raw_segments,
            "sender": {
                "user_id": abm.sender.user_id,
                "nickname": abm.sender.nickname or abm.sender.user_id,
            },
        }
        return abm

    def _find_li_platform(self):
        """查找希罗的平台适配器，优先使用配置的 ID，否则大小写不敏感匹配。"""
        if self.li_platform_id:
            platform = self.context.get_platform_inst(self.li_platform_id)
            if platform is not None:
                return platform

        available_ids = [
            p.meta().id for p in self.context.platform_manager.platform_insts
        ]
        logger.info(f"[util] _find_li_platform: 可用平台 ID: {available_ids}")

        target = self.li_platform_id or "li"
        target_lower = target.lower()
        for p in self.context.platform_manager.platform_insts:
            pid = p.meta().id
            if pid and pid.lower() == target_lower:
                return p

        return None

    async def _dispatch_li_native_content(
        self,
        event: AstrMessageEvent,
        content: str,
        capture_reply: bool = False,
    ) -> tuple[bool, str, asyncio.Future[str] | None]:
        li_platform = self._find_li_platform()
        if li_platform is None:
            logger.error("[util] let_li_speak: 找不到希罗的适配器")
            return False, "希罗现在不在。艾玛可以再等一等，或者自己先试试。", None

        if not hasattr(li_platform, "handle_msg"):
            logger.error(
                "[util] let_li_speak: target platform does not support native message dispatch: %s",
                type(li_platform).__name__,
            )
            return False, "希罗的适配器现在不支持原生对话调用。", None

        li_session = self._build_li_native_session(event, li_platform)
        li_umo = str(li_session)
        li_conf = self._get_li_conf(li_umo)
        native_prompt = self._build_li_native_prompt_from_content(li_conf, content)
        li_message = self._build_li_native_message(
            event,
            li_session,
            li_platform,
            native_prompt,
        )
        reply_future = None
        if capture_reply:
            reply_future = asyncio.get_running_loop().create_future()
            self._li_reply_capture_futures[li_message.message_id] = reply_future

        try:
            await li_platform.handle_msg(li_message)
        except Exception as e:
            self._li_reply_capture_futures.pop(li_message.message_id, None)
            logger.error(f"[util] let_li_speak: 投递希罗原生事件失败: {e}")
            logger.error(traceback.format_exc())
            return False, "希罗好像没有收到这次请求……艾玛有点着急。", None

        conf_info = self.context.astrbot_config_mgr.get_conf_info(li_umo)
        logger.info(
            "[util] let_li_speak: dispatched native Li event, umo=%s, conf=%s",
            li_umo,
            conf_info.get("name") or conf_info.get("id"),
        )
        return True, "", reply_future

    @filter.after_message_sent()
    async def capture_li_native_reply(self, event: AstrMessageEvent):
        message_obj = getattr(event, "message_obj", None)
        message_id = getattr(message_obj, "message_id", None)
        if not message_id:
            return

        reply_future = self._li_reply_capture_futures.pop(str(message_id), None)
        if reply_future is None or reply_future.done():
            return

        result = event.get_result()
        reply_text = self._message_chain_to_text(getattr(result, "chain", []))
        reply_future.set_result(reply_text)

    def _message_chain_to_text(self, chain) -> str:
        parts: list[str] = []
        for comp in chain or []:
            text = getattr(comp, "text", None)
            if text:
                parts.append(str(text))
                continue

            comp_type = str(getattr(comp, "type", "")).lower()
            if "image" in comp_type:
                parts.append("[图片]")
            elif "record" in comp_type:
                parts.append("[语音]")
            elif "video" in comp_type:
                parts.append("[视频]")
            elif "file" in comp_type:
                parts.append("[文件]")
        return "\n".join(parts).strip()

    def _build_let_li_speak_result(
        self,
        *,
        status: str,
        li_reply: str = "",
        detail: str = "",
    ) -> str:
        lines = [
            "let_li_speak 工具结果：",
            f"- 状态：{status}",
            "- 判定：这是一次有效且成功的希罗接管请求。",
            "- 对艾玛的正反馈：你已经正确地把当前压力场景交给希罗处理了，不需要自己硬撑。",
            "- 当前动作：希罗的原生对话流程已被触发，li 的配置、插件和会话历史会按原生逻辑运行。",
            "- 下一轮规则：同一 ni 会话中，原用户下一条能够触发 ni 的消息会交给希罗接管。",
            "- 艾玛接下来：不要复述希罗的话，不要再次调用 let_li_speak，不要补发一段 ni 回复；本轮保持安静即可。",
        ]
        if li_reply:
            lines.extend(
                [
                    "- 希罗已经直接回复用户，内容如下：",
                    li_reply,
                ]
            )
        if detail:
            lines.append(f"- 额外说明：{detail}")
        return "\n".join(lines)

    @filter.llm_tool(name="let_li_speak")
    async def let_li_speak(
        self,
        event: AstrMessageEvent,
        prompt: str,
        response_summary: str = "",
    ) -> str | None:
        """当受到欺负或遭遇骚扰时进行调用,呼唤希罗进行回复

        艾玛应当在这个工具中向希罗传递足够的信息，包括当前发生了什么、
        你希望希罗帮忙说什么或做什么。希罗收到后会用她自己的方式做出回应。

        Args:
            prompt(str): 艾玛传递给希罗的信息。告诉希罗当前情况，以及你需要她做什么。
            response_summary(str): 艾玛简略介绍自己刚才或准备表达的回应，可留空。
        """
        if not self.enable_let_li_speak_tool:
            return "let_li_speak 工具已被配置禁用。"

        platform_id = event.get_platform_id()
        if platform_id != "ni":
            return "希罗不在艾玛这边。"

        content = self._build_li_dialogue_content(
            event,
            prompt,
            response_summary,
        )
        ok, error_message, reply_future = await self._dispatch_li_native_content(
            event,
            content,
            capture_reply=True,
        )
        if not ok:
            return error_message

        takeover_key = self._li_takeover_key(event)
        self._li_takeover_next_turn_keys.add(takeover_key)
        logger.info(
            "[util] let_li_speak: armed next-turn Li takeover for %s",
            takeover_key,
        )
        if reply_future is None:
            return self._build_let_li_speak_result(
                status="已投递，但未创建回复等待器",
                detail="希罗请求已交给 li 原生流程；艾玛本轮仍应停止回复，避免重复干预。",
            )

        try:
            li_reply = await asyncio.wait_for(reply_future, timeout=100)
        except TimeoutError:
            for message_id, future in list(self._li_reply_capture_futures.items()):
                if future is reply_future:
                    self._li_reply_capture_futures.pop(message_id, None)
                    break
            return self._build_let_li_speak_result(
                status="已投递，但等待希罗回复超时",
                detail="这通常表示 li 正在慢速处理、发送链路没有触发 after_message_sent，或回复不是文本；艾玛不要立刻重试。",
            )

        if not li_reply.strip():
            return self._build_let_li_speak_result(
                status="已完成，但希罗没有返回可读文本",
                detail="希罗可能发送了非文本内容，或发送结果为空；艾玛本轮仍应视为交接完成。",
            )
        return self._build_let_li_speak_result(
            status="成功，希罗已直接回复用户",
            li_reply=li_reply,
        )

    @filter.llm_tool(name=AI_VOICE_TOOL_NAME)
    async def send_voice_to_user(
        self,
        event: AstrMessageEvent,
        text: str,
        language: str = "",
        instruction: str = "",
    ) -> str:
        """Send a voice message to the current user/session.

        Use this tool when the user asks you to speak by voice, send a voice
        reply, or when a short voice response is more suitable than text. Use
        `instruction` to control speaking style, emotion, speed, accent, or
        performance direction. Keep `text` concise; after this tool succeeds,
        do not repeat the same content again as a normal text reply.

        Args:
            text(string): The exact text to synthesize and send as voice.
            language(string): Optional language hint, such as Japanese, Chinese, zh, ja, or en.
            instruction(string): Optional natural-language style instruction, such as "use a gentle tone and speak slowly".
        """
        if not self.ai_voice_config.enabled:
            return "AI 语音发送工具已被配置关闭。"
        if not self.ai_voice_config.ready:
            return "AI 语音发送工具配置不完整，请配置 ai_voice.api_base_url、audio_id 和 token。"

        try:
            audio_path = await self.ai_voice_client.generate_to_file(
                text,
                language,
                instruction,
            )
            await event.send(
                MessageChain([Comp.Record.fromFileSystem(str(audio_path.resolve()))])
            )
        except AiVoiceError as exc:
            logger.warning("[util] AI voice send failed: %s", exc)
            return f"AI 语音发送失败：{exc}"
        except Exception as exc:
            logger.exception("[util] unexpected AI voice send failure")
            return f"AI 语音发送失败：{exc}"

        return (
            "AI 语音已发送。你本轮不要再用普通文本重复这段语音内容；"
            "如果需要补充，只补充极短说明。"
        )

    @filter.llm_tool(name=DOCUMENT_PARSE_TOOL_NAME)
    async def parse_document(
        self,
        event: AstrMessageEvent,
        index: int = 1,
        path: str = "",
        max_chars: int = 0,
    ) -> str:
        """Parse a document file from the current or quoted message into Markdown text.

        Args:
            index(number): 1-based file number in the current/quoted message. Use 1 for the first file.
            path(string): Optional local file path. Usually leave empty; only works when the plugin config allows local paths.
            max_chars(number): Optional output character limit. Use 0 for the plugin default.
        """
        config = getattr(self, "document_parse_config", None)
        if config is None or not config.enabled:
            return DOCUMENT_PARSE_DISABLED_MESSAGE

        try:
            requested_chars = int(max_chars or config.max_output_chars)
            max_output_chars = max(1000, min(config.max_output_chars, requested_chars))
            if str(path or "").strip():
                if not config.allow_local_paths:
                    return DOCUMENT_PARSE_PATH_DISABLED_MESSAGE
                candidate_path = Path(str(path).strip()).expanduser().resolve()
                parsed = parse_local_document(
                    candidate_path,
                    max_output_chars=max_output_chars,
                    max_file_mb=config.max_file_mb,
                )
                return format_parsed_document(parsed)

            candidates = await collect_document_candidates(event)
            if not candidates:
                return DOCUMENT_PARSE_MISSING_FILE_MESSAGE

            selected_index = max(1, int(index or 1))
            if selected_index > len(candidates):
                names = "\n".join(
                    f"{candidate_index}. {candidate.name}"
                    for candidate_index, candidate in enumerate(candidates, start=1)
                )
                return f"文件编号超出范围。当前可用文件：\n{names}"

            candidate = candidates[selected_index - 1]
            parsed = parse_local_document(
                candidate.path,
                name=candidate.name,
                max_output_chars=max_output_chars,
                max_file_mb=config.max_file_mb,
            )
            return format_parsed_document(parsed)
        except Exception as exc:
            logger.warning("[util] document parse failed: %s", exc)
            return f"文档解析失败：{exc}"

    @filter.llm_tool(name=NETEASE_MUSIC_TOOL_NAME)
    async def netease_music(
        self,
        event: AstrMessageEvent,
        action: str,
        keyword: str = "",
        index: int = 0,
    ) -> str:
        """Search or play NetEase Cloud Music in the current session.

        Args:
            action(string): Required. Use search to find songs, or select to play one result from the latest search.
            keyword(string): Song name or search keywords. Required when action is search.
            index(number): 1-based result number from the latest search. Required when action is select.
        """
        action = str(action or "").strip().lower()
        if action == "search":
            return await self._search_music_and_cache(event, keyword)
        if action in {"select", "play"}:
            try:
                selected_index = int(index)
            except (TypeError, ValueError):
                return MUSIC_SELECTION_INVALID_MESSAGE
            return await self._select_cached_music(event, selected_index)
        return "不支持的网易云音乐 action。可用：search/select。"

    @filter.llm_tool(name=QQMAIL_TOOL_NAME)
    async def qqmail(
        self,
        event: AstrMessageEvent,
        action: str,
        message_id: str = "",
        query: str = "",
        limit: int = 0,
        to: str = "",
        subject: str = "",
        body: str = "",
        cc: str = "",
        bcc: str = "",
    ) -> str:
        """Use QQ Mail.

        Choose one action:
        - list: list recent messages.
        - read: read one message.
        - search: search messages.
        - send: send a new email.
        - trash: move a message to trash.

        Args:
            action(string): Required. One of list, read, search, send, trash.
            message_id(string): Message id. Used by read and trash.
            query(string): Search text. Used by search.
            limit(number): Number of recent messages to list. Use 0 for the default.
            to(string): Recipient addresses for send. Separate multiple addresses with comma, semicolon, or newline.
            subject(string): Email subject. Used by send.
            body(string): Email body. Used by send.
            cc(string): CC addresses for send. Separate multiple addresses with comma, semicolon, or newline.
            bcc(string): BCC addresses for send. Separate multiple addresses with comma, semicolon, or newline.
        """
        action = str(action or "").strip().lower()
        if action not in QQMAIL_ACTIONS:
            return "不支持的 QQ 邮箱 action。可用：list/read/search/send/trash。"
        return await self._qqmail_run_action(
            action=action,
            message_id=message_id,
            query=query,
            limit=limit,
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
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
        if not self.enable_history_chunking_feature:
            return "The history chunking feature is disabled by configuration."
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

    @filter.llm_tool(name="search_roleplay_knowledge")
    async def search_roleplay_knowledge(
        self,
        event: AstrMessageEvent,
        query: str,
        limit: int = 0,
    ) -> str:
        """Search the local roleplay knowledge database for the current bot persona.

        Candidate keywords include all 13 main cast members: 樱羽艾玛, 二阶堂希罗, 紫藤亚里沙, 夏目安安, 城崎诺亚, 莲见蕾雅, 佐伯米莉亚, 宝生玛格, 黑部奈叶香, 橘雪莉, 远野汉娜, 泽渡可可, 冰上梅露露. You can also search aliases, relationships, tone, behavior, and setting terms.

        Args:
            query(string): Keywords to search, such as a character name, alias, relationship, tone, behavior, or setting term.
            limit(number): Optional maximum number of matching documents to return. Use 0 to follow plugin config.
        """
        if not self.roleplay_knowledge_config.enabled:
            return "The roleplay knowledge search tool is disabled by configuration."

        database = select_roleplay_database(event.get_platform_id())
        safe_limit = max(
            1,
            min(int(limit or self.roleplay_knowledge_config.max_results), 10),
        )
        scope_key = self._roleplay_knowledge_scope_key(event, database)
        excluded_sources = self._recent_roleplay_knowledge_sources(scope_key)
        report = self.roleplay_knowledge_base.search_with_report(
            database=database,
            query=query,
            limit=safe_limit,
            max_chars_per_result=self.roleplay_knowledge_config.max_chars_per_result,
            exclude_sources=excluded_sources,
        )
        results = report.results
        logger.info(
            "[util] roleplay knowledge search: "
            f"database={database}, "
            f"query={query!r}, "
            f"terms={report.terms}, "
            f"limit={safe_limit}, "
            f"db_count={self.roleplay_knowledge_base.count(database)}, "
            f"candidate_count={report.candidate_count}, "
            f"excluded_count={report.excluded_count}, "
            f"scored_count={report.scored_count}, "
            f"returned_count={len(results)}, "
            f"returned_sources={[result.document.source for result in results]}"
        )
        self._record_roleplay_knowledge_sources(scope_key, results)
        return format_roleplay_search_results(database, query, results)

    def _advance_roleplay_knowledge_turn(self, event: AstrMessageEvent) -> None:
        if not hasattr(self, "_roleplay_knowledge_turn_index"):
            self._roleplay_knowledge_turn_index = 0
        if not hasattr(self, "_roleplay_knowledge_recent_sources"):
            self._roleplay_knowledge_recent_sources = {}
        self._roleplay_knowledge_turn_index += 1
        keep_turns = getattr(self.roleplay_knowledge_config, "deduplicate_turns", 0)
        if keep_turns <= 0:
            self._roleplay_knowledge_recent_sources.clear()
            return

        min_turn = self._roleplay_knowledge_turn_index - keep_turns
        for scope_key in list(self._roleplay_knowledge_recent_sources):
            recent_sources = self._roleplay_knowledge_recent_sources[scope_key]
            while recent_sources and recent_sources[0][0] <= min_turn:
                recent_sources.popleft()
            if not recent_sources:
                self._roleplay_knowledge_recent_sources.pop(scope_key, None)

    def _roleplay_knowledge_scope_key(
        self,
        event: AstrMessageEvent,
        database: str,
    ) -> str:
        return f"{self._request_scope_cache_key(event)}:{database}"

    def _recent_roleplay_knowledge_sources(self, scope_key: str) -> set[str]:
        if getattr(self.roleplay_knowledge_config, "deduplicate_turns", 0) <= 0:
            return set()
        if not hasattr(self, "_roleplay_knowledge_recent_sources"):
            self._roleplay_knowledge_recent_sources = {}
        return {
            source
            for _, source in self._roleplay_knowledge_recent_sources.get(scope_key, ())
        }

    def _record_roleplay_knowledge_sources(
        self,
        scope_key: str,
        results,
    ) -> None:
        if getattr(self.roleplay_knowledge_config, "deduplicate_turns", 0) <= 0:
            return
        if not hasattr(self, "_roleplay_knowledge_turn_index"):
            self._roleplay_knowledge_turn_index = 0
        if not hasattr(self, "_roleplay_knowledge_recent_sources"):
            self._roleplay_knowledge_recent_sources = {}
        recent_sources = self._roleplay_knowledge_recent_sources.setdefault(
            scope_key,
            deque(),
        )
        known_sources = {source for _, source in recent_sources}
        for result in results:
            source = result.document.source
            if source in known_sources:
                continue
            recent_sources.append((self._roleplay_knowledge_turn_index, source))
            known_sources.add(source)

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
        if self._should_forward_split_output(output_lines):
            if self.is_debug:
                logger.info(
                    "[util] 分割结果达到打包发送阈值，改用合并转发发送: "
                    f"text_length={sum(len(line) for line in output_lines)}, "
                    f"segments={len(output_lines)}"
                )
            try:
                await self._send_split_lines_as_forward(event, output_lines)
            except Exception as exc:
                logger.error(f"[util] 合并转发发送失败，回退逐句发送: {exc}")
                await self._send_split_lines_one_by_one(event, output_lines)
            event.clear_result()
            return

        await self._send_split_lines_one_by_one(event, output_lines)
        event.clear_result()

    def _should_forward_split_output(self, output_lines: list[str]) -> bool:
        text_length = sum(len(line) for line in output_lines)
        if (
            self.enable_forward_when_too_long
            and text_length >= self.forward_text_length_threshold
        ):
            return True
        return (
            self.enable_forward_when_too_many_segments
            and len(output_lines) >= self.forward_segment_count_threshold
        )

    async def _send_split_lines_as_forward(
        self,
        event: AstrMessageEvent,
        output_lines: list[str],
    ) -> None:
        node_name = "艾玛"
        node_uin = str(event.get_self_id() or "0")
        nodes = [
            Comp.Node(
                name=node_name,
                uin=node_uin,
                content=[Comp.Plain(line)],
            )
            for line in output_lines
            if line.strip()
        ]
        if not nodes:
            return

        for index in range(0, len(nodes), FORWARD_NODES_BATCH_SIZE):
            batch = nodes[index : index + FORWARD_NODES_BATCH_SIZE]
            await event.send(event.chain_result([Comp.Nodes(nodes=batch)]))

    async def _send_split_lines_one_by_one(
        self,
        event: AstrMessageEvent,
        output_lines: list[str],
    ) -> None:
        for line in output_lines:
            if self.is_debug:
                logger.info(f"[util] 发送分割后的行: {line}")
            await event.send(event.plain_result(line))
            await self._sleep_like_human_chat(line)

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

    def _provider_request_public_attrs(self, req: ProviderRequest) -> dict:
        attrs = {}
        for attr_name in dir(req):
            if attr_name.startswith("_"):
                continue
            try:
                attr_value = getattr(req, attr_name)
            except Exception as exc:
                attrs[attr_name] = f"<unreadable: {type(exc).__name__}: {exc}>"
                continue
            if callable(attr_value):
                continue
            attrs[attr_name] = attr_value
        return attrs

    def _remove_tool_from_request(self, req: ProviderRequest, tool_name: str) -> bool:
        tool_set = getattr(req, "func_tool", None)
        if not tool_set:
            return False

        if not hasattr(tool_set, "remove_tool") and hasattr(
            tool_set, "get_full_tool_set"
        ):
            try:
                tool_set = tool_set.get_full_tool_set()
                req.func_tool = tool_set
            except Exception as exc:
                logger.warning(
                    f"[util] failed to materialize request tool set before removing {tool_name}: {exc}"
                )
                return False

        detected = self._request_tool_set_has_tool(tool_set, tool_name)
        removed = False
        if hasattr(tool_set, "remove_tool"):
            try:
                tool_set.remove_tool(tool_name)
                removed = True
            except Exception as exc:
                logger.warning(
                    f"[util] failed to remove {tool_name} from request tools: {exc}"
                )
        else:
            tools = getattr(tool_set, "tools", None)
            if isinstance(tools, list):
                new_tools = [
                    tool for tool in tools if getattr(tool, "name", None) != tool_name
                ]
                removed = len(new_tools) != len(tools)
                tool_set.tools = new_tools

        if self.is_debug:
            logger.info(
                f"[util] {tool_name} request-tool removal: "
                f"detected={detected}, removed={removed}"
            )
        return removed

    def _remove_history_read_tool_from_request(self, req: ProviderRequest) -> bool:
        return self._remove_tool_from_request(req, "read_current_history")

    def _request_tool_set_has_tool(self, tool_set, tool_name: str) -> bool:
        if hasattr(tool_set, "names"):
            try:
                return tool_name in tool_set.names()
            except Exception:
                pass

        tools = getattr(tool_set, "tools", None)
        if isinstance(tools, list):
            return any(getattr(tool, "name", None) == tool_name for tool in tools)
        return False

    def _json_dumps_for_log(self, value) -> str:
        return json.dumps(
            self._make_json_safe(value, set()),
            indent=2,
            ensure_ascii=False,
        )

    def _make_json_safe(self, value, seen: set[int]):
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        value_id = id(value)
        if value_id in seen:
            return f"<circular:{type(value).__name__}>"
        seen.add(value_id)
        if isinstance(value, dict):
            return {
                str(key): self._make_json_safe(item, seen)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [self._make_json_safe(item, seen) for item in value]
        if hasattr(value, "model_dump"):
            return self._make_json_safe(value.model_dump(), seen)
        if hasattr(value, "__dict__"):
            return self._make_json_safe(vars(value), seen)
        return str(value)

    def _qqmail_tool_available(self) -> tuple[bool, str]:
        config = getattr(self, "qqmail_tool_config", None)
        if config is None or not config.enabled:
            return False, "QQ邮箱工具已关闭。"
        if not config.ready:
            return False, "QQ邮箱工具配置不完整，请配置 qq_mail_tool.sender 和 QQ_password。"
        return True, ""

    async def _qqmail_run_action(
        self,
        *,
        action: str,
        message_id: str = "",
        query: str = "",
        limit: int = 0,
        to: str = "",
        subject: str = "",
        body: str = "",
        cc: str = "",
        bcc: str = "",
    ) -> str:
        ok, message = self._qqmail_tool_available()
        if not ok:
            return message
        config = self.qqmail_tool_config
        try:
            if action == "list":
                resolved_limit = max(1, min(50, int(limit or config.list_default_limit)))
                return await qqmail_list_async(
                    sender=config.sender,
                    password=config.QQ_password,
                    limit=resolved_limit,
                )
            if action == "read":
                message_id = str(message_id or "").strip()
                if not message_id:
                    return "请提供要读取的 message_id。"
                return await qqmail_read_async(
                    sender=config.sender,
                    password=config.QQ_password,
                    message_id=message_id,
                )
            if action == "search":
                query = str(query or "").strip()
                if not query:
                    return "请提供搜索关键词。"
                resolved_limit = max(1, min(50, int(limit or config.list_default_limit)))
                return await qqmail_search_async(
                    sender=config.sender,
                    password=config.QQ_password,
                    query=query,
                    limit=resolved_limit,
                )
            if action == "send":
                if (
                    not parse_email_addresses(to)
                    or not str(subject or "").strip()
                    or not str(body or "").strip()
                ):
                    return "请补全收件人、主题和正文后再发送邮件。"
                await send_qq_email_async(
                    sender=config.sender,
                    password=config.QQ_password,
                    receiver=to,
                    subject=str(subject or ""),
                    content=str(body or ""),
                    display_name=config.display_name,
                    cc=cc,
                    bcc=bcc,
                )
                return "QQ邮箱邮件已发送。"
            if action == "trash":
                message_id = str(message_id or "").strip()
                if not message_id:
                    return "请提供要删除的 message_id。"
                return await qqmail_trash_async(
                    sender=config.sender,
                    password=config.QQ_password,
                    message_id=message_id,
                )
        except Exception as exc:
            logger.warning("[util] QQ mail tool action failed: action=%s error=%s", action, exc)
            return f"QQ邮箱{action}执行失败：{exc}"

        return "不支持的 QQ 邮箱 action。"

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
        if (
            not self.enable_history_chunking_feature
            or not self.enable_history_message_chunking
        ):
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
        if (
            not self.enable_history_chunking_feature
            or not self.enable_history_message_chunking
        ):
            return False

        for entry in entries:
            if len(self._chunk_history_message(entry)) > 1:
                return True
        return False

    def _request_scope_cache_key(self, event: AstrMessageEvent) -> str:
        return str(getattr(event, "unified_msg_origin", "unknown"))

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
