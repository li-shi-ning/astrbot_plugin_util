from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import aiohttp


AI_VOICE_TOOL_NAME = "send_voice_to_user"
DEFAULT_AI_VOICE_API_BASE_URL = "http://127.0.0.1:8000"


@dataclass(frozen=True)
class AiVoiceConfig:
    enabled: bool = False
    api_base_url: str = DEFAULT_AI_VOICE_API_BASE_URL
    audio_id: str = ""
    token: str = ""
    language: str = ""
    timeout_seconds: int = 180
    max_text_chars: int = 300

    @property
    def ready(self) -> bool:
        return bool(self.enabled and self.api_base_url and self.audio_id and self.token)


class AiVoiceError(RuntimeError):
    pass


def build_ai_voice_config(config: dict[str, Any] | None) -> AiVoiceConfig:
    config = config or {}
    return AiVoiceConfig(
        enabled=bool(config.get("enable_ai_voice_tool", False)),
        api_base_url=normalize_ai_voice_api_base_url(
            str(config.get("api_base_url", DEFAULT_AI_VOICE_API_BASE_URL) or "")
        ),
        audio_id=str(config.get("audio_id", "") or "").strip(),
        token=str(config.get("token", "") or "").strip(),
        language=str(config.get("language", "") or "").strip(),
        timeout_seconds=_int_between(config.get("timeout_seconds"), default=180, minimum=1, maximum=600),
        max_text_chars=_int_between(config.get("max_text_chars"), default=300, minimum=1, maximum=2000),
    )


def _int_between(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def normalize_ai_voice_api_base_url(value: str) -> str:
    value = str(value or "").strip().rstrip("/")
    if not value:
        return DEFAULT_AI_VOICE_API_BASE_URL
    if not value.startswith(("http://", "https://")):
        value = f"http://{value}"
    return value.rstrip("/")


def validate_ai_voice_text(text: str, max_chars: int) -> str:
    text = str(text or "").strip()
    if not text:
        raise AiVoiceError("语音文本不能为空。")
    if len(text) > max_chars:
        raise AiVoiceError(f"语音文本过长，当前 {len(text)} 字，配置上限 {max_chars} 字。")
    return text


class AiVoiceClient:
    def __init__(self, config: AiVoiceConfig, output_dir: Path):
        self.config = config
        self.output_dir = output_dir

    async def generate_to_file(self, text: str, language: str = "") -> Path:
        if not self.config.ready:
            raise AiVoiceError("AI 语音工具未启用，或 api_base_url/audio_id/token 未配置完整。")

        text = validate_ai_voice_text(text, self.config.max_text_chars)
        payload = {
            "text": text,
            "reference_id": self.config.audio_id,
        }
        selected_language = str(language or self.config.language or "").strip()
        if selected_language:
            payload["language"] = selected_language

        result = await self._post_generate(payload)
        file_path = self._local_file_path_from_result(result)
        if file_path is not None:
            return file_path

        audio_url = str(result.get("audio_url") or "").strip()
        if not audio_url:
            raise AiVoiceError("TTS 服务响应中没有 audio_url 或可访问的 file_path。")
        return await self._download_audio(audio_url)

    async def _post_generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        headers = {
            "Authorization": f"Bearer {self.config.token}",
            "Content-Type": "application/json",
        }
        url = f"{self.config.api_base_url}/generate"
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.post(url, headers=headers, json=payload) as response:
                    result = await response.json(content_type=None)
            except TimeoutError as exc:
                raise AiVoiceError("TTS 生成请求超时。") from exc
            except aiohttp.ClientError as exc:
                raise AiVoiceError(f"TTS 生成请求失败：{exc}") from exc
            except ValueError as exc:
                raise AiVoiceError("TTS 服务返回的不是合法 JSON。") from exc
            if response.status >= 400:
                detail = result.get("detail") if isinstance(result, dict) else result
                raise AiVoiceError(f"TTS 生成失败：HTTP {response.status}, detail={detail}")
        if not isinstance(result, dict):
            raise AiVoiceError("TTS 服务返回格式错误。")
        return result

    def _local_file_path_from_result(self, result: dict[str, Any]) -> Path | None:
        raw_path = str(result.get("file_path") or "").strip()
        if not raw_path:
            return None
        path = Path(raw_path)
        if path.is_file():
            return path
        return None

    async def _download_audio(self, audio_url: str) -> Path:
        output_path = self._new_output_path(audio_url)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = output_path.with_name(f"{output_path.name}.part")

        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        resolved_url = urljoin(f"{self.config.api_base_url}/", audio_url)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.get(resolved_url) as response:
                    if response.status >= 400:
                        raise AiVoiceError(f"音频下载失败：HTTP {response.status}")
                    with temporary_path.open("wb") as output_file:
                        async for chunk in response.content.iter_chunked(64 * 1024):
                            if chunk:
                                output_file.write(chunk)
                temporary_path.replace(output_path)
            except TimeoutError as exc:
                temporary_path.unlink(missing_ok=True)
                raise AiVoiceError("音频下载超时。") from exc
            except aiohttp.ClientError as exc:
                temporary_path.unlink(missing_ok=True)
                raise AiVoiceError(f"音频下载失败：{exc}") from exc
            except OSError as exc:
                temporary_path.unlink(missing_ok=True)
                raise AiVoiceError(f"音频保存失败：{exc}") from exc
        return output_path

    def _new_output_path(self, audio_url: str) -> Path:
        suffix = Path(audio_url.split("?", 1)[0]).suffix.lower()
        if suffix not in {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".amr", ".silk"}:
            suffix = ".wav"
        filename = f"ai-voice-{int(time.time())}-{uuid.uuid4().hex[:8]}{suffix}"
        return self.output_dir / filename
