from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
from sqlalchemy import UniqueConstraint, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import Field, SQLModel, delete, select

from astrbot import logger

try:
    from .amap_adcode_data import AMAP_REGIONS
except ImportError:  # 兼容直接作为普通模块导入的情况
    from amap_adcode_data import AMAP_REGIONS

AMAP_WEATHER_URL = "https://restapi.amap.com/v3/weather/weatherInfo"

_SKIP_AREA_WORDS = {
    "none",
    "null",
    "无",
    "暂无",
    "无数据",
    "保密",
    "不显示",
    "未填写",
    "未知",
    "其他",
    "空",
    "nil",
    "undefined",
}

_AREA_PREFIX_RE = re.compile(
    r"^(?:现居地?|常驻地?|目前所在地?|所在地|所在地区|位于|位置|家乡|"
    r"国家/地区|国家|地区|来自|现居)\s*[:：]?\s*",
    re.IGNORECASE,
)

_AREA_SEPARATOR_RE = re.compile(r"[\s\-–—·,，、/\\|_]+")

# 允许进入索引的行政区划级别不再限制为市级；省/自治区/直辖市/自治州/地区/盟/县/区/旗等均可使用。
_MUNICIPALITIES = {"北京市", "天津市", "上海市", "重庆市"}

# 用于从“XX族XX自治州/自治县/自治旗”中提取常见简称。
_ETHNIC_MARKERS = (
    "柯尔克孜",
    "哈萨克",
    "维吾尔",
    "乌孜别克",
    "塔吉克",
    "塔塔尔",
    "俄罗斯",
    "蒙古",
    "达斡尔",
    "鄂温克",
    "鄂伦春",
    "朝鲜",
    "满",
    "锡伯",
    "藏",
    "彝",
    "苗",
    "侗",
    "布依",
    "哈尼",
    "傣",
    "白",
    "景颇",
    "傈僳",
    "回",
    "土家",
    "壮",
    "羌",
    "纳西",
    "独龙",
    "怒",
    "普米",
    "拉祜",
    "佤",
    "布朗",
    "德昂",
    "水",
    "仡佬",
    "畲",
    "高山",
    "黎",
    "门巴",
    "珞巴",
    "基诺",
)

# rank 只用于在多个候选地区里选择更具体/更合适的层级：
# 1 = 省级（省/自治区/直辖市/特别行政区）
# 2 = 地级（地级市/自治州/地区/盟）
# 3 = 县级（县/区/旗/县级市/特区/林区等）
_Entry = tuple[str, str, int]


def _cut_ethnic_suffix(text: str) -> str:
    """从“阿坝藏族羌族自治”这类文本中截取常见简称“阿坝”。"""
    positions = [(text.find(marker), marker) for marker in _ETHNIC_MARKERS]
    positions = [item for item in positions if item[0] >= 0]
    if not positions:
        return text
    index, marker = min(positions, key=lambda item: item[0])
    if index == 0:
        return marker
    if index < 2:
        return text
    return text[:index]


def _make_short_aliases(name: str) -> list[str]:
    """生成一个行政区划名的常见简称，可能为空。"""
    if name in _MUNICIPALITIES:
        aliases = [name[:-1]]
    elif name.endswith("特别行政区"):
        aliases = [name[:-5]]
    elif name.endswith("省"):
        aliases = [name[:-1]]
    elif name.endswith("自治区"):
        aliases = [_cut_ethnic_suffix(name[:-3])]
    elif name.endswith("自治州"):
        short = _cut_ethnic_suffix(name[:-3])
        aliases = [short, f"{short}州"] if len(short) >= 2 else [f"{short}州"]
    elif name.endswith("自治县"):
        aliases = [_cut_ethnic_suffix(name[:-3])]
    elif name.endswith("自治旗"):
        aliases = [_cut_ethnic_suffix(name[:-3])]
    elif name.endswith("地区"):
        aliases = [name[:-2]]
    elif name.endswith("盟"):
        aliases = [name[:-1]]
    elif name.endswith("区"):
        aliases = [name[:-1]]
    elif name.endswith("县"):
        aliases = [name[:-1]]
    elif name.endswith("旗"):
        aliases = [name[:-1]]
    elif name.endswith("特区"):
        aliases = [name[:-2]]
    elif name.endswith("林区"):
        aliases = [name[:-2]]
    elif name.endswith("市"):
        aliases = [name[:-1]]
    else:
        aliases = []
    return [alias for alias in dict.fromkeys(aliases) if len(alias) >= 2]


class CityCodeIndex:
    """高德行政区划索引，数据来自内置 Python 数据模块，不运行时解析 CSV。"""

    def __init__(self):
        self.full_index: dict[str, list[_Entry]] = {}
        self.short_index: dict[str, list[_Entry]] = {}
        self.entry_count = 0
        self._load()

    def _load(self) -> None:
        full_index: dict[str, list[_Entry]] = {}
        short_index: dict[str, list[_Entry]] = {}
        entry_count = 0

        for name, adcode, rank in AMAP_REGIONS:
            # 内置数据已排除表头与国家级条目；这里再做一次轻量防御。
            if not name or not adcode or rank not in (1, 2, 3):
                continue
            entry = (name, adcode, rank)
            entry_count += 1
            full_index.setdefault(name, []).append(entry)
            for alias in _make_short_aliases(name):
                if alias != name:
                    short_index.setdefault(alias, []).append(entry)

        self.full_index = {key: self._dedupe_entries(value) for key, value in full_index.items()}
        self.short_index = {key: self._dedupe_entries(value) for key, value in short_index.items()}
        self.entry_count = entry_count
        logger.info(
            "[util] city code index loaded: allowed_entries=%d full_names=%d short_aliases=%d",
            entry_count,
            len(self.full_index),
            len(self.short_index),
        )

    @staticmethod
    def _dedupe_entries(entries: list[_Entry]) -> list[_Entry]:
        return list(dict.fromkeys(entries))

    def extract_city(self, area: Any) -> tuple[str, str] | None:
        """从 QQ 资料中的地区字段解析行政区划，返回 (名称, adcode)。

        无法解析、字段为空或含义不清时返回 None。省级、地级、县级均可返回。
        """
        cleaned = self._clean_area(area)
        if not cleaned:
            return None

        # 1) 优先匹配完整行政区划名，例如“成都市”“阿坝藏族羌族自治州”。
        #    一个字符串里出现多个完整名称时，选择层级最具体的（如“四川省成都市武侯区” -> 武侯区）。
        full_named_matches: list[list[_Entry]] = []
        for full_name, entries in self.full_index.items():
            if full_name in cleaned:
                full_named_matches.append(entries)
        if full_named_matches:
            best = self._resolve_named_matches(full_named_matches)
            if best:
                return best

        # 2) 按常见分隔符拆分后做精确匹配，例如“四川-成都”。
        parts = [p for p in _AREA_SEPARATOR_RE.split(cleaned) if p]
        if parts:
            part_matches: list[list[_Entry]] = []
            for part in parts:
                part = part.strip(" ()（）[]【】:：")
                if not part:
                    continue
                if part in self.full_index:
                    part_matches.append(self.full_index[part])
                elif part in self.short_index:
                    part_matches.append(self.short_index[part])
            if part_matches:
                best = self._resolve_named_matches(part_matches)
                if best:
                    return best

        # 3) 没有分隔符时，允许简称作为子串出现，例如“四川成都武侯区” -> “成都”。
        substring_matches: list[tuple[str, list[_Entry]]] = []
        for alias, entries in self.short_index.items():
            if len(alias) < 2 or alias not in cleaned:
                continue
            substring_matches.append((alias, entries))
        if substring_matches:
            resolved: list[tuple[str, _Entry]] = []
            for alias, entries in substring_matches:
                entry = self._resolve_entries(entries)
                if entry:
                    resolved.append((alias, entry))
            if resolved:
                return self._pick_most_specific(resolved)

        return None

    def _resolve_named_matches(
        self,
        named_matches: list[list[_Entry]],
    ) -> tuple[str, str] | None:
        """从多个候选条目列表中选出一个最合适的条目。"""
        resolved: list[tuple[str, _Entry]] = []
        for entries in named_matches:
            entry = self._resolve_entries(entries)
            if entry:
                resolved.append((entry[0], entry))
        if not resolved:
            return None
        if len(resolved) == 1:
            return resolved[0][1][0], resolved[0][1][1]
        return self._pick_most_specific(resolved)

    @staticmethod
    def _resolve_entries(entries: list[_Entry]) -> _Entry | None:
        """处理同名条目：唯一则直接返回；多条时选择层级最高且唯一的那个。

        例如“吉林”同时命中“吉林省”和“吉林市”，单独出现时优先选“吉林省”；
        “阿坝”同时命中“阿坝藏族羌族自治州”和“阿坝县”，选“阿坝藏族羌族自治州”。
        如果同一层级仍有多个候选（如多个“长安区”），则认为含义不清，返回 None。
        """
        if len(entries) == 1:
            return entries[0]
        by_rank: dict[int, list[_Entry]] = {}
        for entry in entries:
            by_rank.setdefault(entry[2], []).append(entry)
        for rank in sorted(by_rank):
            rank_entries = CityCodeIndex._dedupe_entries(by_rank[rank])
            if len(rank_entries) == 1:
                return rank_entries[0]
        return None

    @staticmethod
    def _pick_most_specific(
        resolved: list[tuple[str, _Entry]],
    ) -> tuple[str, str] | None:
        """在已经解析出的候选条目里，选择层级最具体（县级 > 地级 > 省级）的一条。"""
        if not resolved:
            return None
        best_key: tuple[int, int] | None = None
        best_entry: _Entry | None = None
        for _alias, entry in resolved:
            key = (entry[2], len(entry[0]))
            if best_key is None or key > best_key:
                best_key = key
                best_entry = entry
        if best_entry is None:
            return None
        return best_entry[0], best_entry[1]

    @staticmethod
    def _clean_area(area: Any) -> str:
        if not isinstance(area, str):
            return ""
        cleaned = area.strip()
        if not cleaned:
            return ""
        # 全角空格、全角逗号等转半角，统一常见符号。
        cleaned = (
            cleaned.replace("\u3000", " ")
            .replace("，", ",")
            .replace("：", ":")
            .replace("／", "/")
            .replace("（", "(")
            .replace("）", ")")
            .replace("【", "[")
            .replace("】", "]")
        )
        cleaned = _AREA_PREFIX_RE.sub("", cleaned).strip()
        cleaned = cleaned.strip(" -–—·,，、/\\|_()（）[]【】:：")
        lowered = cleaned.lower()
        if lowered in _SKIP_AREA_WORDS:
            return ""
        return cleaned


@dataclass
class AmapWeatherConfig:
    api_key: str = ""
    extensions: str = "all"
    request_timeout_seconds: int = 10
    include_live_weather: bool = True
    forecast_days: int = 2

    @property
    def ready(self) -> bool:
        return bool(self.api_key.strip())


class AmapWeatherClient:
    """高德天气接口客户端，只用于把结果整理成给 LLM 的动态区文本。"""

    def __init__(self, config: AmapWeatherConfig):
        self.config = config

    async def get_weather_context(self, adcode: str, city_name: str) -> str | None:
        if not self.config.ready:
            logger.warning("[util] daily city weather amap key is empty, skip weather fetch")
            return None

        extensions = self.config.extensions.strip().lower() or "all"
        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout_seconds)
        logger.info(
            "[util] daily city weather fetch start: adcode=%s city=%s extensions=%s "
            "include_live=%s timeout=%ds",
            adcode,
            city_name,
            extensions,
            self.config.include_live_weather,
            self.config.request_timeout_seconds,
        )

        async with aiohttp.ClientSession(timeout=timeout) as session:
            live_task: asyncio.Task[dict[str, Any] | None] | None = None
            forecast_task: asyncio.Task[dict[str, Any] | None] | None = None

            if extensions == "base":
                live_task = asyncio.create_task(
                    self._fetch_weather(session, adcode, "base")
                )
            else:
                forecast_task = asyncio.create_task(
                    self._fetch_weather(session, adcode, "all")
                )
                if self.config.include_live_weather:
                    live_task = asyncio.create_task(
                        self._fetch_weather(session, adcode, "base")
                    )

            live_data = await live_task if live_task else None
            forecast_data = await forecast_task if forecast_task else None

        logger.info(
            "[util] daily city weather fetch finished: adcode=%s live_ok=%s forecast_ok=%s",
            adcode,
            live_data is not None,
            forecast_data is not None,
        )
        if not live_data and not forecast_data:
            logger.warning(
                "[util] daily city weather fetch empty: adcode=%s city=%s",
                adcode,
                city_name,
            )
            return None

        parts: list[str] = []
        days = max(1, min(4, int(self.config.forecast_days)))

        if live_data:
            live_text = self._format_live(live_data)
            if live_text:
                parts.append(live_text)
        if forecast_data:
            forecast_text = self._format_forecast(forecast_data, days)
            if forecast_text:
                parts.append(forecast_text)

        if not parts:
            logger.warning(
                "[util] daily city weather format empty: adcode=%s city=%s live=%s forecast=%s",
                adcode,
                city_name,
                live_data,
                forecast_data,
            )
            return None

        body = f"[城市天气] 用户所在地区：{city_name}。" + "；".join(parts) + (
            "。请结合用户所在地区的天气，在回复中自然地进行关怀或特殊提醒，不要生硬复述天气数据。"
        )
        logger.info("[util] daily city weather context built: %s", body)
        return body

    async def _fetch_weather(
        self,
        session: aiohttp.ClientSession,
        adcode: str,
        extensions: str,
    ) -> dict[str, Any] | None:
        params = {
            "city": adcode,
            "key": self.config.api_key.strip(),
            "extensions": extensions,
        }
        try:
            async with session.get(
                AMAP_WEATHER_URL,
                params=params,
            ) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
        except Exception as exc:
            logger.warning(
                "[util] amap weather request failed: adcode=%s extensions=%s error=%s",
                adcode,
                extensions,
                exc,
            )
            return None

        if not isinstance(data, dict):
            logger.warning(
                "[util] amap weather api returned non-dict data: adcode=%s extensions=%s type=%s",
                adcode,
                extensions,
                type(data).__name__,
            )
            return None
        status = str(data.get("status", ""))
        infocode = str(data.get("infocode", ""))
        if status != "1" or (infocode and infocode != "10000"):
            logger.warning(
                "[util] amap weather api returned error: adcode=%s extensions=%s "
                "status=%s infocode=%s info=%s",
                adcode,
                extensions,
                status,
                infocode,
                data.get("info", ""),
            )
            return None
        logger.info(
            "[util] amap weather api success: adcode=%s extensions=%s status=%s infocode=%s",
            adcode,
            extensions,
            status,
            infocode,
        )
        return data

    @staticmethod
    def _format_live(data: dict[str, Any]) -> str:
        lives = data.get("lives")
        if not isinstance(lives, list) or not lives:
            return ""
        live = lives[0]
        if not isinstance(live, dict):
            return ""
        weather = str(live.get("weather", "")).strip()
        temperature = _first_value(live.get("temperature"), live.get("temperature_float"))
        winddirection = str(live.get("winddirection", "")).strip()
        windpower = str(live.get("windpower", "")).strip()
        humidity = _first_value(live.get("humidity"), live.get("humidity_float"))
        if not weather and not temperature:
            return ""
        chunks: list[str] = ["实时天气"]
        if weather:
            chunks.append(str(weather))
        if temperature:
            chunks.append(f"气温{temperature}°C")
        if winddirection:
            wind_text = _wind_text(winddirection, windpower)
            chunks.append(wind_text)
        if humidity:
            chunks.append(f"湿度{humidity}%")
        return "，".join(chunks)

    @staticmethod
    def _format_forecast(data: dict[str, Any], days: int = 2) -> str:
        forecasts = data.get("forecasts")
        if not isinstance(forecasts, list) or not forecasts:
            return ""
        first = forecasts[0]
        if not isinstance(first, dict):
            return ""
        casts = first.get("casts")
        if not isinstance(casts, list) or not casts:
            return ""
        lines: list[str] = []
        for index, cast in enumerate(casts[:days]):
            if not isinstance(cast, dict):
                continue
            date_label = _cast_date_label(cast.get("date"), index)
            day_weather = str(cast.get("dayweather", "")).strip()
            night_weather = str(cast.get("nightweather", "")).strip()
            day_temp = _first_value(cast.get("daytemp"), cast.get("daytemp_float"))
            night_temp = _first_value(cast.get("nighttemp"), cast.get("nighttemp_float"))
            weather_text = day_weather or ""
            if night_weather and night_weather != day_weather:
                weather_text = f"{day_weather}/{night_weather}"
            temp_text = ""
            if day_temp and night_temp:
                temp_text = f"{day_temp}~{night_temp}°C"
            elif day_temp:
                temp_text = f"{day_temp}°C"
            wind = str(cast.get("daywind", "")).strip()
            power = str(cast.get("daypower", "")).strip()
            wind_text = ""
            if wind:
                wind_text = _wind_text(wind, power)
            chunks = [date_label]
            if weather_text:
                chunks.append(weather_text)
            if temp_text:
                chunks.append(temp_text)
            if wind_text:
                chunks.append(wind_text)
            lines.append(" ".join(chunks))
        if not lines:
            return ""
        return "预报：" + "；".join(lines)


def _wind_text(direction: str, power: str) -> str:
    if not direction:
        return ""
    if not power:
        return f"{direction}风"
    if power.endswith("级"):
        return f"{direction}风{power}"
    return f"{direction}风{power}级"


def _first_value(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() not in {"none", "null", "nan"}:
            return text
    return ""


def _cast_date_label(date_value: Any, index: int) -> str:
    if index == 0:
        return "今天"
    if index == 1:
        return "明天"
    if isinstance(date_value, str) and len(date_value) >= 10:
        return date_value[5:10]
    return f"D+{index}"


class DailyWeatherInjectionRecord(SQLModel, table=True):
    """每日每人一次地区天气注入记录。"""

    __tablename__ = "daily_city_weather_injection"
    __table_args__ = (
        UniqueConstraint(
            "user_key",
            "date",
            name="uq_daily_city_weather_user_date",
        ),
        {"extend_existing": True},
    )

    id: int | None = Field(default=None, primary_key=True)
    user_key: str = Field(index=True, description="用户 QQ 号")
    date: str = Field(index=True, description="YYYY-MM-DD")
    created_at: datetime = Field(default_factory=datetime.now, description="created at")


class DailyInjectionState:
    """记录每个用户每天是否已经尝试过首次聊天注入，使用 AstrBot 本地 SQLite 数据库保存。"""

    def __init__(
        self,
        db_path: str | Path,
        timezone: ZoneInfo,
        keep_days: int = 7,
    ):
        self.db_path = Path(db_path)
        self.timezone = timezone
        self.keep_days = keep_days
        self.db_url = f"sqlite+aiosqlite:///{self.db_path}"
        logger.info(
            "[util] daily city weather state init: db_path=%s timezone=%s keep_days=%s",
            self.db_path,
            getattr(self.timezone, "key", str(self.timezone)),
            self.keep_days,
        )
        self.engine = create_async_engine(
            self.db_url,
            echo=False,
            connect_args={"timeout": 30},
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._init_lock = asyncio.Lock()
        self._initialized = False

    def _today(self) -> str:
        return datetime.now(self.timezone).date().isoformat()

    async def init_db(self) -> None:
        """创建数据表并执行轻量 PRAGMA 设置。"""
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            logger.info(
                "[util] daily city weather db init start: path=%s table=%s",
                self.db_path,
                DailyWeatherInjectionRecord.__tablename__,
            )
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            async with self.engine.begin() as conn:
                await conn.run_sync(
                    lambda sync_conn: SQLModel.metadata.create_all(
                        sync_conn,
                        tables=[DailyWeatherInjectionRecord.__table__],
                    )
                )
            async with self.engine.connect() as conn:
                await conn.execute(text("PRAGMA journal_mode=WAL"))
                await conn.execute(text("PRAGMA synchronous=NORMAL"))
                await conn.execute(text("PRAGMA busy_timeout=30000"))
                await conn.commit()
            self._initialized = True
            logger.info(
                "[util] daily city weather db init finished: path=%s table=%s",
                self.db_path,
                DailyWeatherInjectionRecord.__tablename__,
            )

    async def try_mark_injected(self, key: str) -> bool:
        """检查并标记今日首次尝试。返回 True 表示本日首次尝试，可以继续执行注入。"""
        await self.init_db()
        today = self._today()
        cutoff = (
            datetime.now(self.timezone).date()
            - timedelta(days=max(0, int(self.keep_days)))
        ).isoformat()

        async with self.session_factory() as session:
            delete_result = await session.execute(
                delete(DailyWeatherInjectionRecord).where(
                    DailyWeatherInjectionRecord.date < cutoff
                )
            )
            if delete_result.rowcount:
                logger.info(
                    "[util] daily city weather pruned old records: deleted=%s cutoff=%s",
                    delete_result.rowcount,
                    cutoff,
                )
            result = await session.execute(
                select(DailyWeatherInjectionRecord).where(
                    DailyWeatherInjectionRecord.user_key == key,
                    DailyWeatherInjectionRecord.date == today,
                )
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                logger.debug(
                    "[util] daily city weather already injected today: user_qq=%s date=%s id=%s",
                    key,
                    today,
                    existing.id,
                )
                await session.commit()
                return False

            session.add(DailyWeatherInjectionRecord(user_key=key, date=today))
            try:
                await session.commit()
                logger.info(
                    "[util] daily city weather first-injection marked: user_qq=%s date=%s cutoff=%s",
                    key,
                    today,
                    cutoff,
                )
                return True
            except IntegrityError:
                await session.rollback()
                logger.warning(
                    "[util] daily city weather duplicate mark skipped: user_qq=%s date=%s",
                    key,
                    today,
                )
                return False

    async def close(self) -> None:
        logger.info("[util] daily city weather db closing: path=%s", self.db_path)
        await self.engine.dispose()
        logger.info("[util] daily city weather db closed: path=%s", self.db_path)
