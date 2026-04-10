"""
ToolRegistry —— 工具注册中心
职责：
  1. 统一管理所有 BaseTool 实例
  2. 向 LLM 导出完整的 tool schema 列表
  3. 按名称路由工具调用
  4. 支持运行时动态注册（MCP、Skill 注入的工具）
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseTool, ToolExecutionError, ToolSchema

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    工具注册表，支持：
    - register(tool)       手动注册
    - register_many(tools) 批量注册
    - unregister(name)     按名称注销（用于 Skill 生命周期管理）
    - execute(name, **kw)  路由执行
    - to_api_schemas()     导出 LLM 可用格式
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    # ── 注册 ──────────────────────────────────────────────────────────────────

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            logger.warning("Tool '%s' already registered, overwriting.", tool.name)
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool.name)

    def register_many(self, tools: list[BaseTool]) -> None:
        for t in tools:
            self.register(t)

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)
        logger.debug("Unregistered tool: %s", name)

    # ── 查询 ──────────────────────────────────────────────────────────────────

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    # ── 执行 ──────────────────────────────────────────────────────────────────

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """
        按工具名称路由执行。

        返回：工具输出字符串
        抛出：ToolExecutionError（工具不存在或执行失败）
        """
        tool = self._tools.get(name)
        if tool is None:
            raise ToolExecutionError(
                name,
                f"Tool '{name}' not found. Available: {self.names()}",
            )
        try:
            logger.debug("Executing tool '%s' with args: %s", name, arguments)
            result = await tool.execute(**arguments)
            logger.debug("Tool '%s' result: %s…", name, str(result)[:120])
            return result
        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError(name, str(exc), cause=exc) from exc

    # ── Schema 导出 ───────────────────────────────────────────────────────────

    def to_api_schemas(self) -> list[dict]:
        """返回 Anthropic API 格式的 tools 列表"""
        return [t.schema().to_api() for t in self._tools.values()]

    def to_openai_schemas(self) -> list[dict]:
        """返回 OpenAI / DeepSeek 兼容格式的 tools 列表"""
        return [t.schema().to_openai_api() for t in self._tools.values()]

    def __repr__(self) -> str:
        return f"ToolRegistry({self.names()})"
