from __future__ import annotations

import base64
import binascii
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp

DEFAULT_MUSIC_API_BASE_URL = ""
DEFAULT_MUSIC_QUALITY = "exhigh"
DEFAULT_MUSIC_SEARCH_LIMIT = 5
DEFAULT_MUSIC_SELECTION_TIMEOUT_SECONDS = 60
MUSIC_SEARCH_DISABLED_MESSAGE = "音乐搜索功能已关闭。"
MUSIC_SEARCH_USAGE = "请发送：/点歌 歌名，例如：/点歌 Lemon"
MUSIC_SEARCH_EMPTY_MESSAGE = "没有找到相关歌曲。"
MUSIC_SEARCH_API_ERROR_MESSAGE = "音乐服务暂时连接失败，请稍后再试。"
MUSIC_SELECTION_EXPIRED_MESSAGE = "点歌选择已过期，请重新搜索。"
MUSIC_SELECTION_INVALID_MESSAGE = "请选择列表中的歌曲编号。"
MUSIC_AUDIO_UNAVAILABLE_MESSAGE = "这首歌暂时没有可播放的音频链接。"
MUSIC_DETAIL_ERROR_MESSAGE = "获取歌曲详情失败，请稍后再试。"
MUSIC_LOGIN_QR_MESSAGE = "请使用网易云音乐 App 扫码登录，二维码 2 分钟内有效。"
MUSIC_LOGIN_SUCCESS_MESSAGE = "网易云音乐登录成功，Cookie 已保存到插件配置。"
MUSIC_LOGIN_EXPIRED_MESSAGE = "网易云音乐登录二维码已过期，请重新发送 /网易云登录。"
MUSIC_LOGIN_TIMEOUT_MESSAGE = "等待扫码登录超时，请重新发送 /网易云登录。"
MUSIC_LOGIN_API_ERROR_MESSAGE = "网易云音乐登录服务暂时连接失败，请稍后再试。"
MUSIC_LOGIN_NO_COOKIE_MESSAGE = "网易云音乐已确认登录，但接口没有返回 Cookie，请重新登录。"


@dataclass(frozen=True)
class MusicConfig:
    enabled: bool = True
    api_base_url: str = DEFAULT_MUSIC_API_BASE_URL
    quality: str = DEFAULT_MUSIC_QUALITY
    search_limit: int = DEFAULT_MUSIC_SEARCH_LIMIT
    selection_timeout_seconds: int = DEFAULT_MUSIC_SELECTION_TIMEOUT_SECONDS
    cookie: str = ""


@dataclass(frozen=True)
class PendingMusicSelection:
    cache_key: str
    expires_at: float


@dataclass(frozen=True)
class NeteaseQrLogin:
    key: str
    qr_image: str


@dataclass(frozen=True)
class NeteaseQrLoginStatus:
    code: int
    message: str
    cookie: str = ""


def normalize_api_base_url(value: str | None) -> str:
    api_base_url = (value or "").strip().rstrip("/")
    if not api_base_url:
        return ""
    if not api_base_url.startswith(("http://", "https://")):
        api_base_url = f"http://{api_base_url}"
    return api_base_url


def clamp_search_limit(value: Any) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MUSIC_SEARCH_LIMIT
    return max(1, min(limit, 10))


def clamp_selection_timeout(value: Any) -> int:
    try:
        timeout_seconds = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MUSIC_SELECTION_TIMEOUT_SECONDS
    return max(10, min(timeout_seconds, 600))


def format_duration(duration_ms: int | None) -> str:
    duration_ms = max(0, int(duration_ms or 0))
    total_seconds = duration_ms // 1000
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"


def _join_artist_names(artists: list[dict[str, Any]] | None) -> str:
    names = [
        str(artist.get("name", "")).strip()
        for artist in artists or []
        if str(artist.get("name", "")).strip()
    ]
    return " / ".join(names) or "未知歌手"


def song_search_title(song: dict[str, Any]) -> str:
    name = str(song.get("name", "")).strip() or "未知歌曲"
    artists = _join_artist_names(song.get("artists"))
    album = str(song.get("album", {}).get("name", "")).strip() or "未知专辑"
    duration = format_duration(song.get("duration"))
    return f"{name} - {artists}《{album}》[{duration}]"


def format_search_results(keyword: str, songs: list[dict[str, Any]]) -> str:
    lines = [f"找到 {len(songs)} 首与「{keyword}」相关的歌曲，请回复编号选择："]
    lines.extend(f"{index}. {song_search_title(song)}" for index, song in enumerate(songs, 1))
    return "\n".join(lines)


def format_song_detail(
    song_detail: dict[str, Any],
    audio_url: str,
    quality: str,
) -> tuple[str, str, str]:
    title = str(song_detail.get("name", "")).strip() or "未知歌曲"
    artists = _join_artist_names(song_detail.get("ar"))
    album_data = song_detail.get("al", {})
    album = str(album_data.get("name", "")).strip() or "未知专辑"
    cover_url = str(album_data.get("picUrl", "")).strip()
    duration = format_duration(song_detail.get("dt"))
    text = "\n".join(
        [
            "已为你找到歌曲：",
            f"歌名：{title}",
            f"歌手：{artists}",
            f"专辑：{album}",
            f"时长：{duration}",
            f"音质：{quality}",
            f"播放链接：{audio_url}",
        ]
    )
    return text, cover_url, audio_url


def pending_selection_is_expired(selection: PendingMusicSelection, now: float | None = None) -> bool:
    return (now if now is not None else time.time()) > selection.expires_at


def save_qr_image(qr_image: str, directory: Path, key: str) -> Path:
    """Persist an API qrimg data URL as a local PNG file."""
    if "," in qr_image:
        _, qr_image = qr_image.split(",", 1)
    try:
        image_bytes = base64.b64decode(qr_image, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Invalid QR image data.") from exc

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"netease-login-{key}.png"
    path.write_bytes(image_bytes)
    return path


def load_persisted_music_cookie(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("cookie") or "").strip()


def save_persisted_music_cookie(cookie: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "cookie": cookie,
                "saved_at": int(time.time()),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


class NeteaseMusicAPI:
    def __init__(self, api_base_url: str, timeout_seconds: int = 20):
        self.api_base_url = normalize_api_base_url(api_base_url)
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.api_base_url}{path}"
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                return await response.json(content_type=None)

    async def search_songs(self, keyword: str, limit: int) -> list[dict[str, Any]]:
        data = await self._get_json(
            "/search",
            {
                "keywords": keyword,
                "limit": clamp_search_limit(limit),
                "type": 1,
            },
        )
        songs = data.get("result", {}).get("songs", [])
        return songs if isinstance(songs, list) else []

    async def get_song_detail(self, song_id: int | str) -> dict[str, Any] | None:
        data = await self._get_json("/song/detail", {"ids": str(song_id)})
        songs = data.get("songs", [])
        if not isinstance(songs, list) or not songs:
            return None
        return songs[0]

    async def get_audio_url(
        self,
        song_id: int | str,
        quality: str,
        cookie: str = "",
    ) -> str | None:
        qualities = list(dict.fromkeys([quality, "exhigh", "higher", "standard"]))
        for current_quality in qualities:
            params = {
                "id": str(song_id),
                "level": current_quality,
            }
            if cookie:
                params["cookie"] = cookie
            data = await self._get_json("/song/url/v1", params)
            audio_items = data.get("data", [])
            if not isinstance(audio_items, list) or not audio_items:
                continue
            audio_url = str(audio_items[0].get("url") or "").strip()
            if audio_url:
                return audio_url
        return None

    async def create_qr_login(self) -> NeteaseQrLogin:
        key_data = await self._get_json("/login/qr/key", {})
        key = str(key_data.get("data", {}).get("unikey") or "").strip()
        if not key:
            raise ValueError("Netease QR login key is empty.")

        qr_data = await self._get_json(
            "/login/qr/create",
            {
                "key": key,
                "qrimg": "true",
            },
        )
        qr_image = str(qr_data.get("data", {}).get("qrimg") or "").strip()
        if not qr_image:
            raise ValueError("Netease QR image is empty.")
        return NeteaseQrLogin(key=key, qr_image=qr_image)

    async def check_qr_login(self, key: str) -> NeteaseQrLoginStatus:
        data = await self._get_json(
            "/login/qr/check",
            {
                "key": key,
                "timestamp": str(int(time.time() * 1000)),
            },
        )
        code = int(data.get("code") or 0)
        message = str(data.get("message") or data.get("msg") or "").strip()
        cookie = str(data.get("cookie") or "").strip()
        return NeteaseQrLoginStatus(code=code, message=message, cookie=cookie)


def build_music_config(section_config: dict[str, Any]) -> MusicConfig:
    return MusicConfig(
        enabled=bool(section_config.get("enable_music_search_feature", True)),
        api_base_url=normalize_api_base_url(section_config.get("api_base_url")),
        quality=str(section_config.get("quality", DEFAULT_MUSIC_QUALITY) or DEFAULT_MUSIC_QUALITY),
        search_limit=clamp_search_limit(section_config.get("search_limit")),
        selection_timeout_seconds=clamp_selection_timeout(
            section_config.get("selection_timeout_seconds")
        ),
        cookie=str(section_config.get("cookie", "") or ""),
    )
