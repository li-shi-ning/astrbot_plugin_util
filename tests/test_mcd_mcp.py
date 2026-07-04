from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from astrbot.api.event import filter  # noqa: E402
from astrbot.core.star.filter.command import GreedyStr  # noqa: E402
from astrbot.core.star.star_handler import star_handlers_registry  # noqa: E402

from core.mcd_mcp import (  # noqa: E402
    MCD_MCP_ALLOWED_TOOLS,
    McdMcpError,
    ensure_mcd_mcp_tool_allowed,
    format_mcd_mcp_result,
    format_mcd_mcp_tools,
    load_mcd_mcp_config,
    parse_mcd_human_arguments,
    parse_mcd_mcp_arguments,
    parse_mcd_points_category,
    parse_mcd_price_arguments,
)

import main  # noqa: E402,F401


def test_mcd_mcp_config_defaults_to_blank_direct_token():
    config = load_mcd_mcp_config({})

    assert config.enabled is True
    assert config.token == ""
    assert config.max_response_chars == 3500


def test_mcd_mcp_config_clamps_limits_and_reads_direct_token():
    config = load_mcd_mcp_config(
        {
            "enable_mcd_mcp_commands": False,
            "token": " secret-value ",
            "timeout_seconds": 999,
            "max_response_chars": 1,
        }
    )

    assert config.enabled is False
    assert config.token == "secret-value"
    assert config.timeout_seconds == 120
    assert config.max_response_chars == 500


def test_mcd_mcp_blocks_order_tools_and_unknown_tools():
    with pytest.raises(McdMcpError):
        ensure_mcd_mcp_tool_allowed("create-order")
    with pytest.raises(McdMcpError):
        ensure_mcd_mcp_tool_allowed("mall-create-order")
    with pytest.raises(McdMcpError):
        ensure_mcd_mcp_tool_allowed("unknown-tool")

    assert ensure_mcd_mcp_tool_allowed("now-time-info") == "now-time-info"


def test_mcd_mcp_argument_parser_requires_json_object():
    assert parse_mcd_mcp_arguments("") == {}
    assert parse_mcd_mcp_arguments("{}") == {}
    assert parse_mcd_mcp_arguments('{"storeId": "123", "count": 2}') == {
        "storeId": "123",
        "count": 2,
    }

    with pytest.raises(McdMcpError):
        parse_mcd_mcp_arguments("[]")
    with pytest.raises(McdMcpError):
        parse_mcd_mcp_arguments("{bad json")


def test_mcd_human_argument_parser_supports_positional_key_value_and_scene():
    args = parse_mcd_human_arguments(
        "上海市 人民广场 得来速 预约='2026-07-04 12:00'",
        ("city", "keyword"),
        defaults={"searchType": 2, "beType": 1},
    )

    assert args == {
        "city": "上海市",
        "keyword": "人民广场",
        "searchType": 2,
        "orderType": 1,
        "beType": 5,
        "reservationDate": "2026-07-04 12:00",
    }


def test_mcd_price_argument_parser_builds_items_and_defaults_scene():
    args = parse_mcd_price_arguments("123456 10001:2,10002 麦乐送 beCode=abc")

    assert args["storeCode"] == "123456"
    assert args["items"] == [
        {"productCode": "10001", "quantity": 2},
        {"productCode": "10002", "quantity": 1},
    ]
    assert args["orderType"] == 2
    assert args["beType"] == 2
    assert args["beCode"] == "abc"


def test_mcd_points_category_aliases():
    assert parse_mcd_points_category("商品券") == "1>4"
    assert parse_mcd_points_category("全部") == ""


def test_mcd_mcp_result_prefers_structured_content_and_truncates():
    text = format_mcd_mcp_result(
        "now-time-info",
        {"structuredContent": {"timestamp": 1, "date": "2026-07-04"}},
        500,
    )

    assert "now-time-info 返回" in text
    assert '"timestamp": 1' in text

    long_text = format_mcd_mcp_result(
        "campaign-calendar",
        {"content": [{"type": "text", "text": "x" * 100}]},
        40,
    )
    assert "已截断" in long_text
    assert len(long_text) <= 43


def test_mcd_mcp_tools_listing_excludes_order_tools():
    text = format_mcd_mcp_tools()

    assert "create-order" not in text
    assert "mall-create-order" not in text
    assert "/麦 时间" in text
    assert len(MCD_MCP_ALLOWED_TOOLS) == 21


def test_mcd_command_group_requires_admin_permission():
    handler = next(item for item in star_handlers_registry if item.handler_name == "mcd")
    permission_filters = [
        item
        for item in handler.event_filters
        if item.__class__.__name__ == "PermissionTypeFilter"
    ]

    assert permission_filters
    assert permission_filters[0].permission_type == filter.PermissionType.ADMIN


def test_mcd_command_payload_uses_greedy_str():
    handler = next(
        item for item in star_handlers_registry if item.handler_name == "mcd_raw_command"
    )
    command_filters = [
        item
        for item in handler.event_filters
        if item.__class__.__name__ == "CommandFilter"
    ]

    assert command_filters
    assert command_filters[0].handler_params["payload"] is GreedyStr
