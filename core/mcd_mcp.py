from __future__ import annotations

import json
import re
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import aiohttp


MCD_MCP_DEFAULT_URL = "https://mcp.mcd.cn/mcp-servers/mcd-mcp"
MCD_MCP_BLOCKED_TOOLS = frozenset({"create-order", "mall-create-order"})
MCD_MCP_ALLOWED_TOOLS = (
    "calculate-price",
    "query-meal-assistance",
    "campaign-calendar",
    "available-coupons",
    "list-nutrition-foods",
    "query-store-coupons",
    "auto-bind-coupons",
    "query-my-coupons",
    "query-meal-detail",
    "delivery-query-stores",
    "query-my-account",
    "mall-points-products",
    "mall-product-detail",
    "mall-order-list",
    "now-time-info",
    "delivery-query-addresses",
    "query-order",
    "mall-order-detail",
    "delivery-create-address",
    "query-meals",
    "query-nearby-stores",
)

MCD_MCP_TOOL_DESCRIPTIONS = {
    "calculate-price": "计算商品价格和优惠，不创建订单。",
    "query-meal-assistance": "查询企业团餐助餐服务。",
    "campaign-calendar": "查询麦当劳中国营销活动日历。",
    "available-coupons": "查询当前可领取的麦麦省优惠券。",
    "list-nutrition-foods": "查询常见餐品营养成分。",
    "query-store-coupons": "查询指定门店和订单类型可用优惠券。",
    "auto-bind-coupons": "自动领取当前可领取优惠券。",
    "query-my-coupons": "查询用户卡包优惠券。",
    "query-meal-detail": "查询餐品详情、套餐组成和特制选项。",
    "delivery-query-stores": "根据配送地址查询可配送门店。",
    "query-my-account": "查询积分账户详情。",
    "mall-points-products": "查询可积分兑换商品列表。",
    "mall-product-detail": "查询积分兑换商品详情。",
    "mall-order-list": "查询麦麦商城订单列表。",
    "now-time-info": "获取当前服务器时间。",
    "delivery-query-addresses": "查询用户配送地址列表。",
    "query-order": "查询麦当劳订单详情。",
    "mall-order-detail": "查询麦麦商城订单详情。",
    "delivery-create-address": "创建用户配送地址。",
    "query-meals": "查询餐品列表。",
    "query-nearby-stores": "查询附近可点餐门店。",
}

MCD_MCP_FIELD_ALIASES = {
    "门店": "storeCode",
    "门店编码": "storeCode",
    "店": "storeCode",
    "商品": "code",
    "商品编码": "code",
    "餐品": "code",
    "订单": "orderId",
    "订单号": "orderId",
    "地址": "address",
    "地址id": "addressId",
    "地址ID": "addressId",
    "地址编号": "addressId",
    "城市": "city",
    "关键词": "keyword",
    "联系人": "contactName",
    "姓名": "contactName",
    "手机": "phone",
    "手机号": "phone",
    "电话": "phone",
    "性别": "gender",
    "门牌": "addressDetail",
    "门牌号": "addressDetail",
    "页": "page",
    "页码": "page",
    "每页": "pageSize",
    "数量": "size",
    "最后": "lastId",
    "spu": "spuId",
    "分类": "catRuleIds",
    "日期": "specifiedDate",
    "预约": "reservationDate",
    "业务": "beCode",
    "业务编码": "beCode",
    "场景": "scene",
    "类型": "scene",
    "助餐": "gmServiceCode",
}

MCD_MCP_SCENARIOS = {
    "到店": {"orderType": 1, "beType": 1},
    "自取": {"orderType": 1, "beType": 1},
    "到店自取": {"orderType": 1, "beType": 1},
    "得来速": {"orderType": 1, "beType": 5},
    "DT": {"orderType": 1, "beType": 5},
    "dt": {"orderType": 1, "beType": 5},
    "麦乐送": {"orderType": 2, "beType": 2},
    "外送": {"orderType": 2, "beType": 2},
    "配送": {"orderType": 2, "beType": 2},
    "团餐": {"orderType": 2, "beType": 6},
    "企业团餐": {"orderType": 2, "beType": 6},
}

MCD_MCP_POINT_CATEGORIES = {
    "全部": "",
    "商品券": "1>4",
    "餐品券": "1>4",
    "实物": "2",
    "实物商品": "2",
    "周边": "2>8",
    "周边产品": "2>8",
    "礼品卡": "2>9",
    "实物礼品卡": "2>9",
}


@dataclass(frozen=True)
class McdMcpConfig:
    enabled: bool = True
    url: str = MCD_MCP_DEFAULT_URL
    token: str = ""
    timeout_seconds: int = 30
    max_response_chars: int = 3500


class McdMcpError(RuntimeError):
    pass


def load_mcd_mcp_config(config: Mapping[str, Any]) -> McdMcpConfig:
    section = config.get("mcd_mcp", config)
    if not isinstance(section, Mapping):
        section = {}

    url = str(section.get("url", MCD_MCP_DEFAULT_URL) or MCD_MCP_DEFAULT_URL).strip()
    return McdMcpConfig(
        enabled=bool(section.get("enable_mcd_mcp_commands", True)),
        url=url or MCD_MCP_DEFAULT_URL,
        token=str(section.get("token", "") or "").strip(),
        timeout_seconds=max(1, min(120, int(section.get("timeout_seconds", 30) or 30))),
        max_response_chars=max(
            500,
            min(12000, int(section.get("max_response_chars", 3500) or 3500)),
        ),
    )


def parse_mcd_mcp_arguments(payload: str) -> dict[str, Any]:
    payload = str(payload or "").strip()
    if not payload:
        return {}
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise McdMcpError(f"JSON 参数格式错误：{exc}") from exc
    if not isinstance(value, dict):
        raise McdMcpError("JSON 参数必须是对象，例如 {\"beType\": 1}")
    return value


def parse_mcd_human_arguments(
    payload: str,
    positional_fields: tuple[str, ...] = (),
    *,
    defaults: Mapping[str, Any] | None = None,
    aliases: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    args: dict[str, Any] = dict(defaults or {})
    positional, kv = _split_mcd_human_payload(payload)
    field_aliases = dict(MCD_MCP_FIELD_ALIASES)
    field_aliases.update(aliases or {})

    remaining_positional = []
    for item in positional:
        scenario = parse_mcd_scenario(item)
        if scenario:
            args.update(scenario)
        else:
            remaining_positional.append(item)

    for field, value in zip(positional_fields, remaining_positional, strict=False):
        args[field] = _coerce_mcd_value(field, value)

    for raw_key, raw_value in kv.items():
        field = field_aliases.get(raw_key, raw_key)
        if field == "scene":
            scenario = parse_mcd_scenario(raw_value)
            if scenario:
                args.update(scenario)
            continue
        args[field] = _coerce_mcd_value(field, raw_value)

    return {key: value for key, value in args.items() if value not in ("", None)}


def parse_mcd_scenario(value: str) -> dict[str, int] | None:
    return MCD_MCP_SCENARIOS.get(str(value or "").strip())


def parse_mcd_points_category(value: str) -> str:
    value = str(value or "").strip()
    return MCD_MCP_POINT_CATEGORIES.get(value, value)


def parse_mcd_price_arguments(payload: str) -> dict[str, Any]:
    positional, kv = _split_mcd_human_payload(payload)
    if len(positional) < 2:
        raise McdMcpError(
            "估价格式：/麦 估价 门店编码 商品编码[:数量],... [到店|麦乐送|得来速|团餐] [beCode=xxx]"
        )
    args = parse_mcd_human_arguments(" ".join(positional[2:]))
    args["storeCode"] = positional[0]
    args["items"] = _parse_mcd_price_items(positional[1])
    for raw_key, raw_value in kv.items():
        key = MCD_MCP_FIELD_ALIASES.get(raw_key, raw_key)
        args[key] = _coerce_mcd_value(key, raw_value)
    args.setdefault("orderType", 1)
    args.setdefault("beType", 1)
    return args


def format_mcd_usage(title: str, examples: tuple[str, ...]) -> str:
    return title + "\n" + "\n".join(f"- {example}" for example in examples)


def ensure_mcd_mcp_tool_allowed(tool_name: str) -> str:
    tool_name = str(tool_name or "").strip()
    if not tool_name:
        raise McdMcpError("请提供工具名。")
    if tool_name in MCD_MCP_BLOCKED_TOOLS:
        raise McdMcpError(f"{tool_name} 是下单接口，已禁止通过指令调用。")
    if tool_name not in MCD_MCP_ALLOWED_TOOLS:
        allowed = "、".join(MCD_MCP_ALLOWED_TOOLS)
        raise McdMcpError(f"未知或未允许的麦当劳 MCP 工具：{tool_name}\n可用工具：{allowed}")
    return tool_name


def format_mcd_mcp_tools() -> str:
    lines = [
        "麦当劳 MCP 管理员指令（不含下单接口）：",
        "/麦 时间",
        "/麦 活动 或 /麦 活动日期 2026-07-04",
        "/麦 营养",
        "/麦 可领券 / /麦 领券 / /麦 我的券 [页=1 每页=200]",
        "/麦 地址 / /麦 添加地址 城市 联系人 手机 地址 门牌 [先生/女士]",
        "/麦 附近门店 城市 关键词 [到店|得来速]",
        "/麦 外送门店 地址ID [麦乐送|团餐]",
        "/麦 餐品 门店编码 [到店|麦乐送|得来速|团餐] [beCode=xxx]",
        "/麦 餐品详情 门店编码 商品编码 [到店|麦乐送|得来速|团餐] [beCode=xxx]",
        "/麦 门店券 门店编码 [到店|麦乐送|得来速|团餐] [beCode=xxx]",
        "/麦 估价 门店编码 商品编码[:数量],... [到店|麦乐送|得来速|团餐] [beCode=xxx]",
        "/麦 团餐服务 门店编码 beCode=xxx",
        "/麦 积分 / /麦 积分商品 [全部|商品券|实物|周边|礼品卡] / /麦 积分商品详情 SPU_ID",
        "/麦 订单 订单号 / /麦 商城订单 [数量=10] / /麦 商城订单详情 订单号",
        "/麦 原始 工具名 key=value ...（兜底调试，不需要 JSON）",
        "",
        "下单接口已硬拦截，不提供指令调用。",
    ]
    return "\n".join(lines)


def format_mcd_mcp_result(tool_name: str, result: Mapping[str, Any], max_chars: int) -> str:
    if "error" in result:
        return _truncate(
            f"{tool_name} 调用失败：\n"
            + json.dumps(result["error"], ensure_ascii=False, indent=2),
            max_chars,
        )

    payload = result.get("result", result)
    is_error = bool(payload.get("isError")) if isinstance(payload, Mapping) else False
    title = f"{tool_name} 返回结果"
    if is_error:
        title += "（工具标记为错误）"

    structured = payload.get("structuredContent") if isinstance(payload, Mapping) else None
    if structured is not None:
        body = json.dumps(structured, ensure_ascii=False, indent=2)
        return _truncate(f"{title}：\n{body}", max_chars)

    content = payload.get("content") if isinstance(payload, Mapping) else None
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, Mapping):
                text = item.get("text")
                if text:
                    text_parts.append(str(text))
            elif item:
                text_parts.append(str(item))
        if text_parts:
            return _truncate(f"{title}：\n" + "\n\n".join(text_parts), max_chars)

    return _truncate(
        f"{title}：\n" + json.dumps(payload, ensure_ascii=False, indent=2),
        max_chars,
    )


class McdMcpClient:
    def __init__(self, config: McdMcpConfig, token: str):
        self.config = config
        self.token = token
        self._initialized = False

    @property
    def ready(self) -> bool:
        return bool(self.config.enabled and self.config.url and self.token)

    async def list_tools(self) -> dict[str, Any]:
        await self._ensure_initialized()
        return await self._post({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

    async def call_tool(self, tool_name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        tool_name = ensure_mcd_mcp_tool_allowed(tool_name)
        await self._ensure_initialized()
        return await self._post(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": dict(arguments)},
            }
        )

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        if not self.ready:
            raise McdMcpError("麦当劳 MCP 未启用或 token 未配置。")
        await self._post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "astrbot-plugin-util", "version": "1.0.0"},
                },
            }
        )
        await self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            allow_empty=True,
        )
        self._initialized = True

    async def _post(
        self, payload: Mapping[str, Any], allow_empty: bool = False
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        }
        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.config.url,
                    headers=headers,
                    json=dict(payload),
                ) as response:
                    text = await response.text()
                    if response.status >= 400:
                        raise McdMcpError(
                            f"MCP HTTP {response.status}: {_truncate(text, 800)}"
                        )
                    if not text.strip():
                        return {} if allow_empty else {"result": {}}
                    return json.loads(text)
        except TimeoutError as exc:
            raise McdMcpError("MCP 请求超时。") from exc
        except aiohttp.ClientError as exc:
            raise McdMcpError(f"MCP 网络请求失败：{exc}") from exc
        except json.JSONDecodeError as exc:
            raise McdMcpError(f"MCP 返回不是合法 JSON：{exc}") from exc


def _truncate(text: str, max_chars: int) -> str:
    text = str(text)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 40)] + f"\n...（已截断，原长度 {len(text)} 字符）"


def _split_mcd_human_payload(payload: str) -> tuple[list[str], dict[str, str]]:
    payload = str(payload or "").strip()
    if not payload:
        return [], {}
    try:
        parts = shlex.split(payload)
    except ValueError:
        parts = payload.split()
    positional: list[str] = []
    kv: dict[str, str] = {}
    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            key = key.strip()
            if key:
                kv[key] = value.strip()
            continue
        positional.append(part)
    return positional, kv


def _coerce_mcd_value(field: str, value: str) -> Any:
    value = str(value).strip()
    if field in {"beType", "orderType", "size", "spuId"}:
        try:
            return int(value)
        except ValueError as exc:
            raise McdMcpError(f"{field} 必须是整数：{value}") from exc
    if field == "lastId":
        try:
            return float(value)
        except ValueError as exc:
            raise McdMcpError(f"{field} 必须是数字：{value}") from exc
    return value


def _parse_mcd_price_items(value: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw_item in re.split(r"[,，]", value):
        raw_item = raw_item.strip()
        if not raw_item:
            continue
        if ":" in raw_item:
            product_code, quantity_text = raw_item.split(":", 1)
        elif "x" in raw_item:
            product_code, quantity_text = raw_item.split("x", 1)
        elif "*" in raw_item:
            product_code, quantity_text = raw_item.split("*", 1)
        else:
            product_code, quantity_text = raw_item, "1"
        product_code = product_code.strip()
        if not product_code:
            continue
        try:
            quantity = int(quantity_text.strip() or "1")
        except ValueError as exc:
            raise McdMcpError(f"商品数量必须是整数：{raw_item}") from exc
        items.append({"productCode": product_code, "quantity": quantity})
    if not items:
        raise McdMcpError("请至少提供一个商品编码，例如：12345:2")
    return items
