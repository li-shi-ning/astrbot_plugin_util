from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import astrbot.api.message_components as Comp

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from core.music_search import (  # noqa: E402
    DEFAULT_MUSIC_API_BASE_URL,
    MUSIC_LOGIN_EXPIRED_MESSAGE,
    MUSIC_LOGIN_SUCCESS_MESSAGE,
    MUSIC_SEARCH_DISABLED_MESSAGE,
    MUSIC_SEARCH_USAGE,
    MUSIC_SELECTION_INVALID_MESSAGE,
    MusicConfig,
    NeteaseQrLogin,
    NeteaseQrLoginStatus,
    build_music_config,
    format_duration,
    format_search_results,
    load_persisted_music_cookie,
    normalize_api_base_url,
)

import main  # noqa: E402
from main import util  # noqa: E402


class FakeMusicApi:
    def __init__(
        self,
        songs=None,
        detail=None,
        audio_url="https://music.example/song.mp3",
        qr_login=None,
        login_statuses=None,
    ):
        self.songs = songs or []
        self.detail = detail
        self.audio_url = audio_url
        self.qr_login = qr_login
        self.login_statuses = list(login_statuses or [])
        self.search_calls = []
        self.detail_calls = []
        self.audio_calls = []
        self.create_qr_login_calls = 0
        self.check_qr_login_calls = []

    async def search_songs(self, keyword, limit):
        self.search_calls.append((keyword, limit))
        return self.songs

    async def get_song_detail(self, song_id):
        self.detail_calls.append(song_id)
        return self.detail

    async def get_audio_url(self, song_id, quality, cookie):
        self.audio_calls.append((song_id, quality, cookie))
        return self.audio_url

    async def create_qr_login(self):
        self.create_qr_login_calls += 1
        return self.qr_login or NeteaseQrLogin(
            key="test-key",
            qr_image=(
                "data:image/png;base64,"
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAA"
                "DUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            ),
        )

    async def check_qr_login(self, key):
        self.check_qr_login_calls.append(key)
        if self.login_statuses:
            return self.login_statuses.pop(0)
        return NeteaseQrLoginStatus(code=801, message="等待扫码")


class FakeConfig(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.saved = False

    def save_config(self):
        self.saved = True


def make_plugin(config: MusicConfig | None = None, api=None, raw_config=None) -> util:
    plugin = util.__new__(util)
    plugin.music_search_config = config or MusicConfig()
    plugin.music_pending_selections = {}
    plugin.music_song_cache = {}
    plugin.config = raw_config or FakeConfig({"music_search": {}})
    if api is not None:
        plugin._music_api = lambda: api
    return plugin


def make_event(message: str, session_id: str = "session-1"):
    stopped = {"value": False}
    sent = []

    def stop_event():
        stopped["value"] = True

    async def send(chain):
        sent.append(chain)

    event = SimpleNamespace(
        message_str=message,
        plain_result=lambda text: SimpleNamespace(message_str=text),
        chain_result=lambda chain: SimpleNamespace(chain=chain),
        get_session_id=lambda: session_id,
        stop_event=stop_event,
        stopped=stopped,
        send=send,
        sent=sent,
    )
    return event


async def collect(generator):
    return [item async for item in generator]


def test_build_music_config_normalizes_api_url_and_limits_values():
    config = build_music_config(
        {
            "api_base_url": "64.90.12.120:3051/",
            "search_limit": 99,
            "selection_timeout_seconds": 1,
            "quality": "higher",
        }
    )

    assert config.api_base_url == "http://64.90.12.120:3051"
    assert config.search_limit == 10
    assert config.selection_timeout_seconds == 10
    assert config.quality == "higher"


def test_normalize_api_base_url_uses_default_when_blank():
    assert normalize_api_base_url("") == DEFAULT_MUSIC_API_BASE_URL


def test_netease_login_uses_astrbot_plugin_data_dir():
    path_text = str(main.NETEASE_COOKIE_PATH).replace("\\", "/")

    assert "/data/plugin_data/astrbot_plugin_util/netease_login/cookie.json" in path_text
    assert "/data/plugins/astrbot_plugin_util/data/" not in path_text


def test_format_duration():
    assert format_duration(185000) == "3:05"


def test_format_search_results():
    text = format_search_results(
        "Lemon",
        [
            {
                "name": "Lemon",
                "artists": [{"name": "米津玄师"}],
                "album": {"name": "STRAY SHEEP"},
                "duration": 255000,
            }
        ],
    )

    assert "找到 1 首与「Lemon」相关的歌曲" in text
    assert "1. Lemon - 米津玄师《STRAY SHEEP》[4:15]" in text


@pytest.mark.asyncio
async def test_search_music_command_reports_disabled():
    plugin = make_plugin(MusicConfig(enabled=False))

    results = await collect(plugin.search_music_command(make_event(""), "Lemon"))

    assert results[0].message_str == MUSIC_SEARCH_DISABLED_MESSAGE


@pytest.mark.asyncio
async def test_search_music_command_requires_keyword():
    plugin = make_plugin()

    results = await collect(plugin.search_music_command(make_event(""), ""))

    assert results[0].message_str == MUSIC_SEARCH_USAGE


@pytest.mark.asyncio
async def test_search_music_command_returns_results_and_waits_for_selection():
    api = FakeMusicApi(
        songs=[
            {
                "id": 10001,
                "name": "Lemon",
                "artists": [{"name": "米津玄师"}],
                "album": {"name": "STRAY SHEEP"},
                "duration": 255000,
            }
        ]
    )
    plugin = make_plugin(api=api)

    results = await collect(plugin.search_music_command(make_event(""), "Lemon"))

    assert api.search_calls == [("Lemon", 5)]
    assert "1. Lemon - 米津玄师《STRAY SHEEP》[4:15]" in results[0].message_str
    assert "session-1" in plugin.music_pending_selections


@pytest.mark.asyncio
async def test_select_music_command_sends_detail_cover_and_record():
    api = FakeMusicApi(
        songs=[
            {
                "id": 10001,
                "name": "Lemon",
                "artists": [{"name": "米津玄师"}],
                "album": {"name": "STRAY SHEEP"},
                "duration": 255000,
            }
        ],
        detail={
            "id": 10001,
            "name": "Lemon",
            "ar": [{"name": "米津玄师"}],
            "al": {
                "name": "STRAY SHEEP",
                "picUrl": "https://music.example/cover.jpg",
            },
            "dt": 255000,
        },
        audio_url="https://music.example/song.mp3",
    )
    plugin = make_plugin(api=api)
    await collect(plugin.search_music_command(make_event(""), "Lemon"))

    event = make_event("1")
    results = await collect(plugin.select_music_command(event))

    assert event.stopped["value"] is True
    assert api.detail_calls == [10001]
    assert api.audio_calls == [(10001, "exhigh", "")]
    assert results == []
    assert isinstance(event.sent[0].chain[0], Comp.Plain)
    assert "歌名：Lemon" in event.sent[0].chain[0].text
    assert isinstance(event.sent[0].chain[1], Comp.Image)
    assert event.sent[0].chain[1].file == "https://music.example/cover.jpg"
    assert isinstance(event.sent[1].chain[0], Comp.Record)
    assert event.sent[1].chain[0].file == "https://music.example/song.mp3"
    assert plugin.music_pending_selections == {}
    assert plugin.music_song_cache == {}


@pytest.mark.asyncio
async def test_select_music_command_rejects_invalid_number():
    api = FakeMusicApi(
        songs=[
            {
                "id": 10001,
                "name": "Lemon",
                "artists": [{"name": "米津玄师"}],
                "album": {"name": "STRAY SHEEP"},
                "duration": 255000,
            }
        ]
    )
    plugin = make_plugin(api=api)
    await collect(plugin.search_music_command(make_event(""), "Lemon"))

    results = await collect(plugin.select_music_command(make_event("2")))

    assert results[0].message_str == MUSIC_SELECTION_INVALID_MESSAGE


@pytest.mark.asyncio
async def test_login_netease_music_command_persists_cookie(monkeypatch, tmp_path):
    async def fast_sleep(_seconds):
        return None

    cookie_path = tmp_path / "netease_login" / "cookie.json"
    monkeypatch.setattr("main.NETEASE_LOGIN_DATA_DIR", tmp_path / "netease_login")
    monkeypatch.setattr("main.NETEASE_COOKIE_PATH", cookie_path)
    monkeypatch.setattr("main.asyncio.sleep", fast_sleep)
    raw_config = FakeConfig({"music_search": {"api_base_url": "64.90.12.120:3051"}})
    api = FakeMusicApi(
        login_statuses=[
            NeteaseQrLoginStatus(
                code=803,
                message="授权登录成功",
                cookie="MUSIC_U=test-cookie;",
            )
        ]
    )
    plugin = make_plugin(api=api, raw_config=raw_config)
    event = make_event("/网易云登录")

    await plugin.login_netease_music_command(event)

    assert event.stopped["value"] is True
    assert api.create_qr_login_calls == 1
    assert api.check_qr_login_calls == ["test-key"]
    assert "cookie" not in raw_config["music_search"]
    assert raw_config.saved is False
    assert json.loads(cookie_path.read_text(encoding="utf-8"))["cookie"] == "MUSIC_U=test-cookie;"
    assert load_persisted_music_cookie(cookie_path) == "MUSIC_U=test-cookie;"
    assert plugin.music_search_config.cookie == "MUSIC_U=test-cookie;"
    assert isinstance(event.sent[0].chain[0], Comp.Image)
    assert len(event.sent[0].chain) == 1
    assert MUSIC_LOGIN_SUCCESS_MESSAGE in event.sent[-1].chain[0].text


@pytest.mark.asyncio
async def test_login_netease_music_command_reports_expired(monkeypatch, tmp_path):
    async def fast_sleep(_seconds):
        return None

    cookie_path = tmp_path / "netease_login" / "cookie.json"
    monkeypatch.setattr("main.NETEASE_LOGIN_DATA_DIR", tmp_path / "netease_login")
    monkeypatch.setattr("main.NETEASE_COOKIE_PATH", cookie_path)
    monkeypatch.setattr("main.asyncio.sleep", fast_sleep)
    raw_config = FakeConfig({"music_search": {}})
    api = FakeMusicApi(
        login_statuses=[NeteaseQrLoginStatus(code=800, message="二维码已过期")]
    )
    plugin = make_plugin(api=api, raw_config=raw_config)
    event = make_event("/网易云登录")

    await plugin.login_netease_music_command(event)

    assert "cookie" not in raw_config["music_search"]
    assert raw_config.saved is False
    assert not cookie_path.exists()
    assert isinstance(event.sent[0].chain[0], Comp.Image)
    assert MUSIC_LOGIN_EXPIRED_MESSAGE in event.sent[-1].chain[0].text
