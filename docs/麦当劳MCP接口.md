# 麦当劳 MCP 接口说明

本插件通过 `/麦` 管理员指令组调用麦当劳 MCP 服务。已明确排除并硬拦截下单接口，当前不提供 `create-order` 与 `mall-create-order` 指令。

## 指令

- `/麦 帮助`：查看指令说明。
- `/麦 工具`：列出允许调用的非下单工具。
- `/麦 说明 <工具名>`：实时读取 MCP 工具 schema，用于查看参数格式。
- `/麦 原始 <工具名> key=value ...`：兜底调用指定工具，不需要手写 JSON。
- `/麦 时间`：调用 `now-time-info {}`。
- `/麦 活动`：调用 `campaign-calendar {}`。
- `/麦 活动日期 2026-07-04`：调用 `campaign-calendar` 并指定日期。
- `/麦 营养`：调用 `list-nutrition-foods {}`。
- `/麦 附近门店 上海市 人民广场 到店`：查询附近门店。
- `/麦 外送门店 地址ID 麦乐送`：查询可配送门店。
- `/麦 餐品 门店编码 到店`：查询餐品列表。
- `/麦 餐品详情 门店编码 商品编码 到店`：查询餐品详情。
- `/麦 门店券 门店编码 到店`：查询门店可用券。
- `/麦 估价 门店编码 商品编码[:数量],... 到店`：计算价格。
- `/麦 地址`、`/麦 添加地址 城市 联系人 手机 地址 门牌 [先生/女士]`：查询或创建配送地址。
- `/麦 可领券`、`/麦 领券`、`/麦 我的券 页=1 每页=200`：优惠券相关。
- `/麦 积分`、`/麦 积分商品 商品券`、`/麦 积分商品详情 SPU_ID`：积分商城相关。
- `/麦 订单 订单号`、`/麦 商城订单 数量=10`、`/麦 商城订单详情 订单号`：订单查询。

复杂参数使用 `key=value`，例如：

```text
/麦 餐品 123456 麦乐送 beCode=abc
/麦 原始 delivery-query-stores addressId=123456 beType=2
```

## 允许调用的工具

```text
calculate-price
query-meal-assistance
campaign-calendar
available-coupons
list-nutrition-foods
query-store-coupons
auto-bind-coupons
query-my-coupons
query-meal-detail
delivery-query-stores
query-my-account
mall-points-products
mall-product-detail
mall-order-list
now-time-info
delivery-query-addresses
query-order
mall-order-detail
delivery-create-address
query-meals
query-nearby-stores
```

## 已验证的数据格式

MCP 返回体通常包含 `content` 与可选的 `structuredContent`。

`now-time-info` 示例结构：

```json
{
  "content": [
    {
      "type": "text",
      "text": "当前时间信息..."
    }
  ],
  "structuredContent": {
    "timestamp": 1783152000000,
    "date": "2026-07-04",
    "timezone": "Asia/Shanghai"
  }
}
```

`campaign-calendar` 示例结构：

```json
{
  "content": [
    {
      "type": "text",
      "text": "活动日历文本，可能包含图片链接和活动详情"
    }
  ]
}
```

`list-nutrition-foods` 示例结构：

```json
{
  "content": [
    {
      "type": "text",
      "text": "营养成分数据文本列表"
    }
  ]
}
```

插件输出时会优先展示 `structuredContent`；没有结构化内容时展示 `content[].text`。回复过长时按 `mcd_mcp.max_response_chars` 截断。
