# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个 AstrBot 插件项目，提供多种实用工具功能：
- **麻将 Copilot 控制**：通过聊天命令远程控制 Mahjong Copilot 应用
- **中文实体抽取**：基于 jieba 的中文实体识别，用于动态注入角色文档到 LLM 提示词
- **QQ 机器人交互**：戳一戳响应、消息表情回复等 AIOCQHTTP 平台特定功能

## 架构设计

```
main.py              # 插件入口，注册 Star 类，定义所有命令处理器
core/
├── api_client.py           # 麻将 Copilot API 异步客户端 (aiohttp)
├── ChineseEntityExtractor.py  # jieba 中文实体抽取器
└── Filter.py               # 自定义事件过滤器 (戳一戳检测)
```

**核心依赖**：
- `astrbot` 框架 API (`astrbot.api`, `astrbot.core`)
- `jieba` 中文分词
- `aiohttp` 异步 HTTP
- `numpy` 加权随机

## 命令组

### `/mj` - 麻将控制
| 命令 | 功能 |
|------|------|
| `seturl <url>` | 设置麻将接口地址 |
| `gs` | 获取系统状态 |
| `ggi` | 获取游戏信息 |
| `gag` | 获取 AI 指导 |
| `sb` | 启动浏览器 |
| `ea/da/ta` | 启用/禁用/切换自动打牌 |
| `ej/dj/tj` | 启用/禁用/切换自动加入 |
| `eo/do/to` | 启用/禁用/切换覆盖显示 |
| `gjs/sjs` | 获取/设置自动加入参数 |
| `gset/sset` | 获取/保存设置 |
| `rm` | 重载模型 |
| `sd` | 关闭应用 |
| `hc` | 健康检查 |

### `/lishi` - 调试工具
| 命令 | 功能 |
|------|------|
| `ah` | 获取所有处理器信息 |
| `hibmp <path>` | 按模块路径查插件 |
| `hibfn <name>` | 按完整名称查插件 |
| `kh <qq>` | 获取陌生人信息 |
| `ch` | 获取会话历史 |
| `chb/chbf/chbg` | 通过 OneBot 获取聊天记录 |
| `setd <0\|1>` | 设置调试模式 |

## 关键实现模式

### 事件过滤器
`Filter.py` 定义了自定义 `HandlerFilter` 用于检测戳一戳事件：
```python
@filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
@register_pack_type()  # 自定义过滤器装饰器
async def poke(self, event):
    ...
```

### LLM 请求拦截
通过 `@filter.on_llm_request(priority=49)` 拦截 LLM 请求，根据实体识别结果动态注入角色文档到系统提示词。

### 配置项
- `data_dir`: 数据目录路径
- `max_role_doct`: 最大角色文档注入数量
- `mahjong_interface_url`: 麻将接口地址

## 开发注意事项

- 所有 AIOCQHTTP 特定功能需添加 `@filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)` 装饰器
- QQ 号验证使用 `_validate_qq()` 方法防止注入攻击
- 实体词典格式：`词语 词频 类型`（空格分隔，支持 `#` 注释）
