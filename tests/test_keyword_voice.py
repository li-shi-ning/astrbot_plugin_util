from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from core.keyword_voice import (  # noqa: E402
    GroupKeywordVoice,
    load_group_keyword_voices,
)

from main import util  # noqa: E402


def make_event(
    *,
    group_id: str | None = "20002",
    message: str = "播放 AIZO",
):
    return SimpleNamespace(
        message_str=message,
        get_group_id=lambda: group_id,
        get_message_outline=lambda: message,
        chain_result=lambda chain: SimpleNamespace(chain=chain),
    )


async def collect_async_results(generator):
    return [item async for item in generator]


def make_plugin(rules: dict[str, tuple[GroupKeywordVoice, ...]]) -> util:
    plugin = util.__new__(util)
    plugin.group_keyword_voices = rules
    return plugin


def test_loads_only_explicit_group_rules_without_global_fallback():
    rules = load_group_keyword_voices(
        {
            "global_keyword_voice": {
                "enabled": True,
                "keywords": ["全局"],
                "audio_directory": "E:/global",
            },
            "group_keyword_voices": [
                {
                    "group_id": "20002",
                    "enabled": True,
                    "keywords": ["Aizo", ""],
                    "audio_directory": " E:/voice/aizo ",
                }
            ],
        }
    )

    assert set(rules) == {"20002"}
    assert rules["20002"][0].keywords == ("Aizo",)
    assert rules["20002"][0].audio_directory == "E:/voice/aizo"


def test_duplicate_group_keeps_all_configurations_in_order():
    rules = load_group_keyword_voices(
        {
            "group_keyword_voices": [
                {
                    "group_id": "20002",
                    "keywords": ["旧"],
                    "audio_directory": "old",
                },
                {
                    "group_id": "20002",
                    "enabled": False,
                    "keywords": ["新"],
                    "audio_directory": "new",
                },
            ]
        }
    )

    assert len(rules["20002"]) == 2
    assert rules["20002"][0].keywords == ("旧",)
    assert rules["20002"][0].audio_directory == "old"
    assert rules["20002"][1].enabled is False
    assert rules["20002"][1].keywords == ("新",)
    assert rules["20002"][1].audio_directory == "new"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("请播放 AIZO", "E:/voice/aizo"),
        ("没有命中", None),
        ("", None),
    ],
)
def test_directory_for_matches_case_insensitively(message, expected):
    settings = GroupKeywordVoice(
        enabled=True,
        keywords=("aizo",),
        audio_directory="E:/voice/aizo",
    )

    assert settings.directory_for(message) == expected


def test_disabled_or_incomplete_rule_never_replies():
    disabled = GroupKeywordVoice(False, ("aizo",), "E:/voice/aizo")
    no_keywords = GroupKeywordVoice(True, (), "E:/voice/aizo")
    no_directory = GroupKeywordVoice(True, ("aizo",), "")

    assert disabled.directory_for("aizo") is None
    assert no_keywords.directory_for("aizo") is None
    assert no_directory.directory_for("aizo") is None


@pytest.mark.asyncio
async def test_handler_sends_audio_only_in_configured_enabled_group(tmp_path):
    audio_directory = tmp_path / "voice"
    audio_directory.mkdir()
    audio_path = audio_directory / "aizo.mp3"
    audio_path.write_bytes(b"test audio")
    plugin = make_plugin(
        {
            "20002": (
                GroupKeywordVoice(
                    enabled=True,
                    keywords=("aizo",),
                    audio_directory=str(audio_directory),
                ),
            ),
            "30003": (
                GroupKeywordVoice(
                    enabled=False,
                    keywords=("aizo",),
                    audio_directory=str(audio_directory),
                ),
            ),
        }
    )

    matched = await collect_async_results(
        plugin.reply_group_keyword_voice(make_event(group_id="20002"))
    )
    unconfigured = await collect_async_results(
        plugin.reply_group_keyword_voice(make_event(group_id="99999"))
    )
    disabled = await collect_async_results(
        plugin.reply_group_keyword_voice(make_event(group_id="30003"))
    )
    private = await collect_async_results(
        plugin.reply_group_keyword_voice(make_event(group_id=None))
    )

    assert len(matched) == 1
    assert len(matched[0].chain) == 1
    assert matched[0].chain[0].path == str(audio_path.resolve())
    assert unconfigured == []
    assert disabled == []
    assert private == []


@pytest.mark.asyncio
async def test_handler_skips_missing_audio_directory():
    plugin = make_plugin(
        {
            "20002": (
                GroupKeywordVoice(
                    enabled=True,
                    keywords=("aizo",),
                    audio_directory="missing-aizo-directory",
                ),
            )
        }
    )

    results = await collect_async_results(
        plugin.reply_group_keyword_voice(make_event(group_id="20002"))
    )

    assert results == []


@pytest.mark.asyncio
async def test_same_group_can_use_different_keywords_and_directories(tmp_path):
    first_directory = tmp_path / "first"
    second_directory = tmp_path / "second"
    first_directory.mkdir()
    second_directory.mkdir()
    first_audio = first_directory / "first.mp3"
    second_audio = second_directory / "second.mp3"
    first_audio.write_bytes(b"first")
    second_audio.write_bytes(b"second")
    plugin = make_plugin(
        {
            "20002": (
                GroupKeywordVoice(True, ("第一个",), str(first_directory)),
                GroupKeywordVoice(True, ("第二个",), str(second_directory)),
            )
        }
    )

    results = await collect_async_results(
        plugin.reply_group_keyword_voice(
            make_event(group_id="20002", message="播放第二个")
        )
    )

    assert len(results) == 1
    assert results[0].chain[0].path == str(second_audio.resolve())


@pytest.mark.asyncio
async def test_same_group_sends_only_first_valid_matching_rule(tmp_path):
    first_directory = tmp_path / "first"
    second_directory = tmp_path / "second"
    first_directory.mkdir()
    second_directory.mkdir()
    first_audio = first_directory / "first.mp3"
    second_audio = second_directory / "second.mp3"
    first_audio.write_bytes(b"first")
    second_audio.write_bytes(b"second")
    plugin = make_plugin(
        {
            "20002": (
                GroupKeywordVoice(True, ("共同",), str(first_directory)),
                GroupKeywordVoice(True, ("共同",), str(second_directory)),
            )
        }
    )

    results = await collect_async_results(
        plugin.reply_group_keyword_voice(
            make_event(group_id="20002", message="共同关键词")
        )
    )

    assert len(results) == 1
    assert results[0].chain[0].path == str(first_audio.resolve())


def test_first_audio_in_directory_uses_sorted_supported_file(tmp_path):
    (tmp_path / "z-last.wav").write_bytes(b"wav")
    expected = tmp_path / "A-first.MP3"
    expected.write_bytes(b"mp3")
    (tmp_path / "notes.txt").write_text("ignored", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "nested.mp3").write_bytes(b"ignored")

    assert util._first_audio_in_directory(tmp_path) == expected


def test_first_audio_in_directory_rejects_empty_or_missing_directory(tmp_path):
    assert util._first_audio_in_directory(tmp_path) is None
    assert util._first_audio_in_directory(tmp_path / "missing") is None
