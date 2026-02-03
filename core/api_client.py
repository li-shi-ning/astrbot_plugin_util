""" Mahjong Copilot API 客户端

使用 aiohttp 异步访问所有 API 端点
"""

import asyncio
import aiohttp
import json


class ApiClient:
    """API 客户端类，用于异步访问所有 API 端点"""

    def __init__(self, base_url="http://localhost:5001"):
        """初始化 API 客户端

        Args:
            base_url: API 基础 URL，默认为 http://localhost:5001
        """
        self.base_url = base_url

    def set_url(self, url):
        self.base_url = url

    async def _request(self, method, endpoint, data=None):
        """发送异步 HTTP 请求

        Args:
            method: HTTP 方法 (GET, POST)
            endpoint: API 端点路径
            data: POST 请求的数据

        Returns:
            dict: 响应 JSON 数据
        """
        url = f"{self.base_url}{endpoint}"
        async with aiohttp.ClientSession() as session:
            try:
                if method == "GET":
                    async with session.get(url) as response:
                        return await response.json()
                elif method == "POST":
                    async with session.post(url, json=data) as response:
                        return await response.json()
            except Exception as e:
                return {"error": str(e)}

    async def get_status(self):
        """获取系统整体状态

        Returns:
            dict: 包含主线程、浏览器、游戏、模型等状态信息
        """
        return await self._request("GET", "/api/status")

    async def get_game_info(self):
        """获取当前游戏信息

        Returns:
            dict: 手牌、摸牌等游戏信息
        """
        return await self._request("GET", "/api/game_info")

    async def get_ai_guide(self):
        """获取 AI 指导信息

        Returns:
            dict: AI 推荐的动作和选项
        """
        return await self._request("GET", "/api/ai_guide")

    async def start_browser(self):
        """启动浏览器

        Returns:
            dict: 操作结果
        """
        return await self._request("POST", "/api/browser/start")

    async def enable_overlay(self):
        """启用网页覆盖显示

        Returns:
            dict: 操作结果
        """
        return await self._request("POST", "/api/overlay/enable")

    async def disable_overlay(self):
        """禁用网页覆盖显示

        Returns:
            dict: 操作结果
        """
        return await self._request("POST", "/api/overlay/disable")

    async def toggle_overlay(self):
        """切换网页覆盖显示状态

        Returns:
            dict: 操作结果
        """
        return await self._request("POST", "/api/overlay/toggle")

    async def enable_automation(self):
        """启用自动打牌

        Returns:
            dict: 操作结果
        """
        return await self._request("POST", "/api/automation/enable")

    async def disable_automation(self):
        """禁用自动打牌

        Returns:
            dict: 操作结果
        """
        return await self._request("POST", "/api/automation/disable")

    async def toggle_automation(self):
        """切换自动打牌状态

        Returns:
            dict: 操作结果
        """
        return await self._request("POST", "/api/automation/toggle")

    async def enable_autojoin(self):
        """启用自动加入游戏

        Returns:
            dict: 操作结果
        """
        return await self._request("POST", "/api/autojoin/enable")

    async def disable_autojoin(self):
        """禁用自动加入游戏

        Returns:
            dict: 操作结果
        """
        return await self._request("POST", "/api/autojoin/disable")

    async def toggle_autojoin(self):
        """切换自动加入游戏状态

        Returns:
            dict: 操作结果
        """
        return await self._request("POST", "/api/autojoin/toggle")

    async def get_autojoin_settings(self):
        """获取自动加入游戏设置

        Returns:
            dict: 自动加入游戏设置
        """
        return await self._request("GET", "/api/autojoin/settings")

    async def set_autojoin_settings(self, level, mode):
        """设置自动加入游戏参数

        Args:
            level: 等级索引
            mode: 游戏模式

        Returns:
            dict: 操作结果
        """
        data = {"level": level, "mode": mode}
        return await self._request("POST", "/api/autojoin/settings", data)

    async def get_settings(self):
        """获取当前设置

        Returns:
            dict: 当前设置
        """
        return await self._request("GET", "/api/settings")

    async def save_settings(self):
        """保存设置到文件

        Returns:
            dict: 操作结果
        """
        return await self._request("POST", "/api/settings/save")

    async def reload_model(self):
        """重新加载模型

        Returns:
            dict: 操作结果
        """
        return await self._request("POST", "/api/model/reload")

    async def shutdown(self):
        """关闭应用程序

        Returns:
            dict: 操作结果
        """
        return await self._request("POST", "/api/shutdown")

    async def health_check(self):
        """健康检查接口

        Returns:
            dict: 健康检查结果
        """
        return await self._request("GET", "/api/health")


async def main():
    """示例：测试所有 API 方法"""
    client = ApiClient()

    # 测试获取系统状态
    print("=== 测试获取系统状态 ===")
    status = await client.get_status()
    print(json.dumps(status, ensure_ascii=False, indent=2))
    print()

    # 测试获取游戏信息
    print("=== 测试获取游戏信息 ===")
    game_info = await client.get_game_info()
    print(json.dumps(game_info, ensure_ascii=False, indent=2))
    print()

    # 测试获取 AI 指导
    print("=== 测试获取 AI 指导 ===")
    ai_guide = await client.get_ai_guide()
    print(json.dumps(ai_guide, ensure_ascii=False, indent=2))
    print()

    # 测试健康检查
    print("=== 测试健康检查 ===")
    health = await client.health_check()
    print(json.dumps(health, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())