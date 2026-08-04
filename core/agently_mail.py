from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from typing import Any


QQMAIL_TOOL_NAME = "qqmail"
QQMAIL_READ_ACTIONS = {"list", "read", "search"}
QQMAIL_WRITE_ACTIONS = {"send", "reply", "forward", "trash"}

URL_PATTERN = re.compile(r"https?://[^\s<>\"]+")

@dataclass(frozen=True)
class AgentlyMailConfig:
    enabled: bool = False
    cli_path: str = "agently-cli"
    workspace: str = "astrbot_plugin_util"
    timeout_seconds: int = 60
    list_default_limit: int = 10
    enable_llm_tools: bool = False
    allow_write_operations: bool = False
    admin_qqs: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return bool(self.enabled and self.cli_path)


@dataclass(frozen=True)
class AgentlyMailResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def text(self) -> str:
        return "\n".join(part for part in (self.stdout, self.stderr) if part).strip()


class AgentlyMailError(RuntimeError):
    pass


def build_agently_mail_config(config: dict[str, Any] | None) -> AgentlyMailConfig:
    config = config or {}
    return AgentlyMailConfig(
        enabled=bool(config.get("enable_agently_mail_feature", False)),
        cli_path=str(config.get("cli_path", "agently-cli") or "agently-cli").strip(),
        workspace=str(config.get("workspace", "astrbot_plugin_util") or "astrbot_plugin_util").strip(),
        timeout_seconds=_int_between(config.get("timeout_seconds"), default=60, minimum=5, maximum=600),
        list_default_limit=_int_between(config.get("list_default_limit"), default=10, minimum=1, maximum=50),
        enable_llm_tools=bool(config.get("enable_agently_mail_tools", False)),
        allow_write_operations=bool(config.get("allow_write_operations", False)),
        admin_qqs=tuple(
            str(item).strip()
            for item in config.get("admin_qqs", []) or []
            if str(item).strip()
        ),
    )


def _int_between(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def agently_mail_env(config: AgentlyMailConfig) -> dict[str, str]:
    env = os.environ.copy()
    if config.workspace:
        env["AGENTLY_WORKSPACE"] = config.workspace
    return env


def mask_agently_mail_output(text: str) -> str:
    text = str(text or "")
    text = re.sub(r"(?i)(authorization:\s*bearer\s+)[^\s]+", r"\1<hidden>", text)
    text = re.sub(r"(?i)(access[_-]?token[\"'\s:=]+)[^\s,\"'}]+", r"\1<hidden>", text)
    return text


def extract_first_url(text: str) -> str:
    match = URL_PATTERN.search(str(text or ""))
    return match.group(0) if match else ""


def format_cli_result(result: AgentlyMailResult, *, max_chars: int = 6000) -> str:
    text = mask_agently_mail_output(result.text)
    if not text:
        text = f"命令已完成，退出码 {result.returncode}。"
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[已截断]"
    return text


def build_recipient_args(flag: str, values: list[str] | tuple[str, ...] | str | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        raw_values = [item.strip() for item in re.split(r"[,;\n]", values) if item.strip()]
    else:
        raw_values = [str(item).strip() for item in values if str(item).strip()]
    args: list[str] = []
    for value in raw_values:
        args.extend([flag, value])
    return args


class AgentlyMailClient:
    def __init__(self, config: AgentlyMailConfig):
        self.config = config

    async def run(self, args: list[str] | tuple[str, ...], *, timeout: int | None = None) -> AgentlyMailResult:
        if not self.config.ready:
            raise AgentlyMailError("QQ Agent 邮箱功能未启用或 agently-cli 路径未配置。")
        command = [self.config.cli_path, *[str(arg) for arg in args]]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=agently_mail_env(self.config),
            )
        except FileNotFoundError as exc:
            raise AgentlyMailError(f"找不到 agently-cli：{self.config.cli_path}") from exc
        except OSError as exc:
            raise AgentlyMailError(f"启动 agently-cli 失败：{exc}") from exc

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout or self.config.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise AgentlyMailError("agently-cli 执行超时。") from exc

        result = AgentlyMailResult(
            command=tuple(command),
            returncode=int(process.returncode or 0),
            stdout=stdout_bytes.decode("utf-8", errors="replace").strip(),
            stderr=stderr_bytes.decode("utf-8", errors="replace").strip(),
        )
        if result.returncode != 0:
            raise AgentlyMailError(format_cli_result(result))
        return result

    async def login_and_capture_url(self, on_url=None) -> tuple[str, AgentlyMailResult]:
        if not self.config.ready:
            raise AgentlyMailError("QQ Agent 邮箱功能未启用或 agently-cli 路径未配置。")
        command = [self.config.cli_path, "auth", "login"]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=agently_mail_env(self.config),
            )
        except FileNotFoundError as exc:
            raise AgentlyMailError(f"找不到 agently-cli：{self.config.cli_path}") from exc
        except OSError as exc:
            raise AgentlyMailError(f"启动 agently-cli 失败：{exc}") from exc

        output_parts: list[str] = []
        url = ""
        deadline = asyncio.get_running_loop().time() + self.config.timeout_seconds
        while asyncio.get_running_loop().time() < deadline and process.returncode is None:
            await asyncio.sleep(0.2)
            for stream in (process.stdout, process.stderr):
                if stream is None:
                    continue
                try:
                    chunk = await asyncio.wait_for(stream.read(4096), timeout=0.05)
                except asyncio.TimeoutError:
                    continue
                if not chunk:
                    continue
                text = chunk.decode("utf-8", errors="replace")
                output_parts.append(text)
                url = url or extract_first_url(text)
                if url:
                    if on_url is not None:
                        await on_url(url)
                    break
            if url:
                break

        if not url:
            process.kill()
            stdout_bytes, stderr_bytes = await process.communicate()
            text = "".join(output_parts)
            text += stdout_bytes.decode("utf-8", errors="replace")
            text += stderr_bytes.decode("utf-8", errors="replace")
            raise AgentlyMailError(f"未从 agently-cli auth login 输出中找到授权 URL：{mask_agently_mail_output(text)}")

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=self.config.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise AgentlyMailError("等待 QQ 邮箱授权完成超时。") from exc

        stdout = "".join(output_parts) + stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        result = AgentlyMailResult(
            command=tuple(command),
            returncode=int(process.returncode or 0),
            stdout=stdout.strip(),
            stderr=stderr.strip(),
        )
        if result.returncode != 0:
            raise AgentlyMailError(format_cli_result(result))
        return url, result

    async def me(self) -> AgentlyMailResult:
        return await self.run(["+me"])

    async def list_messages(self, limit: int) -> AgentlyMailResult:
        return await self.run(["message", "+list", "--limit", str(limit)])

    async def read_message(self, message_id: str) -> AgentlyMailResult:
        return await self.run(["message", "+read", "--id", message_id])

    async def search_messages(self, query: str) -> AgentlyMailResult:
        return await self.run(["message", "+search", "--q", query])
