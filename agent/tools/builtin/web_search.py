from __future__ import annotations

import os
from typing import Any

import httpx

from ..base import BaseTool, ToolExecutionError, ToolSchema


class WebSearchTool(BaseTool):
    """
    使用 Tavily API 搜索互联网信息。
    从环境变量或后端配置读取 TAVILY_API_KEY。
    """

    name = "web_search"
    description = "在互联网上搜索信息，返回最相关的摘要和链接。"

    def __init__(self, api_key: str | None = None) -> None:
        # 显式传入 api_key 或从环境变量读取
        self._api_key = api_key

    def _get_api_key(self) -> str:
        """延迟加载 API Key，优先级：传入 > 环境变量 > 后端配置"""
        if self._api_key:
            return self._api_key
        
        # 尝试从环境变量读取
        key = os.getenv("TAVILY_API_KEY", "")
        if key:
            return key
        
        # 尝试从后端配置读取
        try:
            from backend.config import get_settings
            settings = get_settings()
            return settings.tavily_api_key or ""
        except Exception:
            return ""

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索查询关键词（如「比特币最新价格」）"},
                    "max_results": {
                        "type": "integer",
                        "description": "最多返回结果数（默认 5）",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        )

    async def execute(self, query: str, max_results: int = 5) -> str:
        api_key = self._get_api_key()
        if not api_key:
            raise ToolExecutionError(
                self.name, "未配置 Tavily API Key（TAVILY_API_KEY 环境变量）"
            )

        url = "https://api.tavily.com/search"
        payload = {
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
        }

        async with httpx.AsyncClient(timeout=20) as client:
            try:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as exc:
                raise ToolExecutionError(
                    self.name, f"HTTP {exc.response.status_code}: {exc.response.text}"
                ) from exc
            except Exception as exc:
                raise ToolExecutionError(self.name, str(exc), cause=exc) from exc

        results = data.get("results", [])
        if not results:
            return f"搜索 {query!r} 未找到结果"

        lines = [f"搜索结果：{query}\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.get('title', '')}")
            lines.append(f"   URL: {r.get('url', '')}")
            lines.append(f"   摘要: {r.get('content', '')[:200]}")
            lines.append("")

        return "\n".join(lines)
