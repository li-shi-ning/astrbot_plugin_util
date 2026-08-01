from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import astrbot.api.message_components as Comp

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from core.ai_voice import (  # noqa: E402
    AI_VOICE_TOOL_NAME,
    AiVoiceClient,
    AiVoiceConfig,
    AiVoiceError,
    build_ai_voice_config,
    DEFAULT_AI_VOICE_API_BASE_URL,
    normalize_ai_voice_api_base_url,
    normalize_ai_voice_audio_format,
    validate_ai_voice_text,
    validate_ai_voice_instruction,
)
from main import util  # noqa: E402


class FakeAiVoiceClient:
    def __init__(self, audio_path: Path):
        self.audio_path = audio_path
        self.calls = []

    async def generate_to_file(
        self,
        text: str,
        language: str = "",
        instruction: str = "",
    ) -> Path:
        self.calls.append((text, language, instruction))
        self.audio_path.write_bytes(b"fake wav")
        return self.audio_path


class CapturingAiVoiceClient(AiVoiceClient):
    def __init__(self, config: AiVoiceConfig, output_dir: Path, audio_path: Path):
        super().__init__(config, output_dir)
        self.audio_path = audio_path
        self.payloads = []

    async def _post_generate(self, payload):
        self.payloads.append(payload)
        return {"output": {"audio": {"url": "https://dashscope.example/audio.wav"}}}

    async def _download_audio(self, audio_url: str) -> Path:
        self.downloaded_url = audio_url
        self.audio_path.write_bytes(b"fake wav")
        return self.audio_path


def make_event():
    sent = []

    async def send(chain):
        sent.append(chain)

    return SimpleNamespace(send=send, sent=sent)


def make_plugin(config: AiVoiceConfig, client) -> util:
    plugin = util.__new__(util)
    plugin.ai_voice_config = config
    plugin.ai_voice_client = client
    return plugin


def test_build_ai_voice_config_reads_audio_id_and_token_without_bearer_prefix():
    config = build_ai_voice_config(
        {
            "enable_ai_voice_tool": True,
            "api_base_url": "127.0.0.1:8000/",
            "audio_id": "reference-1",
            "token": "secret-token",
            "model": "cosyvoice-v3.5-plus",
            "audio_format": "mp3",
            "sample_rate": 44100,
            "language": "ja",
            "instruction": "使用温柔自然的语气，语速稍慢。",
            "timeout_seconds": 999,
            "max_text_chars": 0,
            "max_instruction_chars": 9999,
        }
    )

    assert config.enabled is True
    assert config.ready is True
    assert config.api_base_url == "http://127.0.0.1:8000"
    assert config.audio_id == "reference-1"
    assert config.token == "secret-token"
    assert config.model == "cosyvoice-v3.5-plus"
    assert config.audio_format == "mp3"
    assert config.sample_rate == 44100
    assert config.language == "ja"
    assert config.instruction == "使用温柔自然的语气，语速稍慢。"
    assert config.timeout_seconds == 600
    assert config.max_text_chars == 1
    assert config.max_instruction_chars == 1600


def test_normalize_ai_voice_api_base_url_defaults_and_adds_scheme():
    assert normalize_ai_voice_api_base_url("") == DEFAULT_AI_VOICE_API_BASE_URL
    assert normalize_ai_voice_api_base_url("tts.example.com/") == "http://tts.example.com"
    assert normalize_ai_voice_api_base_url("https://tts.example.com/") == "https://tts.example.com"


def test_normalize_ai_voice_audio_format_defaults_invalid_values():
    assert normalize_ai_voice_audio_format("mp3") == "mp3"
    assert normalize_ai_voice_audio_format("bad") == "wav"


def test_validate_ai_voice_text_rejects_empty_or_too_long_text():
    assert validate_ai_voice_text("  你好  ", 10) == "你好"

    with pytest.raises(AiVoiceError):
        validate_ai_voice_text("", 10)
    with pytest.raises(AiVoiceError):
        validate_ai_voice_text("太长了", 2)


def test_validate_ai_voice_instruction_allows_empty_and_rejects_too_long_text():
    assert validate_ai_voice_instruction("", 10) == ""
    assert validate_ai_voice_instruction("  温柔一点  ", 10) == "温柔一点"

    with pytest.raises(AiVoiceError):
        validate_ai_voice_instruction("太长了", 2)


@pytest.mark.asyncio
async def test_ai_voice_client_sends_instruction_aliases(tmp_path):
    audio_path = tmp_path / "generated.wav"
    client = CapturingAiVoiceClient(
        AiVoiceConfig(
            enabled=True,
            api_base_url="http://tts.example",
            audio_id="reference-1",
            token="secret-token",
            language="ja",
            instruction="使用默认温柔语气",
        ),
        tmp_path,
        audio_path,
    )

    result = await client.generate_to_file("你好")

    assert result == audio_path
    assert client.downloaded_url == "https://dashscope.example/audio.wav"
    assert client.payloads == [
        {
            "model": "cosyvoice-v3.5-plus",
            "input": {
                "text": "你好",
                "voice": "reference-1",
                "format": "wav",
                "sample_rate": 24000,
                "language_hints": ["ja"],
                "instruction": "使用默认温柔语气",
            },
        }
    ]


@pytest.mark.asyncio
async def test_send_voice_to_user_generates_and_sends_record(tmp_path):
    audio_path = tmp_path / "voice.wav"
    client = FakeAiVoiceClient(audio_path)
    plugin = make_plugin(
        AiVoiceConfig(
            enabled=True,
            api_base_url="http://tts.example",
            audio_id="reference-1",
            token="secret-token",
        ),
        client,
    )
    event = make_event()

    result = await plugin.send_voice_to_user(
        event,
        "请用语音说这句话",
        "Japanese",
        "使用温柔自然的语气",
    )

    assert client.calls == [("请用语音说这句话", "Japanese", "使用温柔自然的语气")]
    assert "AI 语音已发送" in result
    assert len(event.sent) == 1
    assert isinstance(event.sent[0].chain[0], Comp.Record)
    assert event.sent[0].chain[0].path == str(audio_path.resolve())


@pytest.mark.asyncio
async def test_send_voice_to_user_reports_incomplete_config(tmp_path):
    plugin = make_plugin(AiVoiceConfig(enabled=True), FakeAiVoiceClient(tmp_path / "x.wav"))
    event = make_event()

    result = await plugin.send_voice_to_user(event, "你好")

    assert "配置不完整" in result
    assert event.sent == []


def test_ai_voice_tool_name_is_stable():
    assert AI_VOICE_TOOL_NAME == "send_voice_to_user"
