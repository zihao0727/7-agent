"""
MCP 客户端适配器 ——
将 MCP Server 暴露的工具自动桥接为 BaseTool，
无缝接入 ToolRegistry，实现即插即用。

支持两种传输：
  - stdio  → 本地子进程（最常见）
  - sse    → 远程 HTTP Server-Sent Events

参考：https://modelcontextprotocol.io/docs
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..tools.base import BaseTool, ToolExecutionError, ToolSchema
from ..tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# 懒导入 mcp 库，避免未安装时崩溃
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.sse import sse_client
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False
    logger.warning("mcp 库未安装，MCP 功能不可用。运行 pip install mcp 启用。")


class MCPToolAdapter(BaseTool):
    """
    将 MCP Server 的单个工具包装成 BaseTool。
    由 MCPClient 自动创建，无需手动实例化。
    """

    def __init__(
        self,
        tool_name: str,
        tool_description: str,
        input_schema: dict,
        session_factory,  # 返回 ClientSession 的异步上下文管理器工厂
    ) -> None:
        self.name = tool_name
        self.description = tool_description
        self._input_schema = input_schema
        self._session_factory = session_factory

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema=self._input_schema,
        )

    async def execute(self, **kwargs: Any) -> str:
        async with self._session_factory() as session:
            try:
                result = await session.call_tool(self.name, arguments=kwargs)
                # MCP 返回 content 列表，提取文本
                parts = []
                for block in result.content:
                    if hasattr(block, "text"):
                        parts.append(block.text)
                    else:
                        parts.append(str(block))
                return "\n".join(parts) or "(empty result)"
            except Exception as exc:
                raise ToolExecutionError(self.name, str(exc), cause=exc) from exc


class MCPStdioClient:
    """
    通过 stdio 连接 MCP Server（本地子进程）。

    使用示例::

        client = MCPStdioClient(command="python", args=["my_server.py"])
        tools = await client.list_tools()
        client.register_to(tool_registry)
    """

    def __init__(self, command: str, args: list[str] | None = None, env: dict | None = None) -> None:
        if not _MCP_AVAILABLE:
            raise RuntimeError("mcp 库未安装，请运行 pip install mcp")
        self._command = command
        self._args = args or []
        self._env = env
        self._tools: list[BaseTool] = []

    def _make_params(self) -> "StdioServerParameters":
        return StdioServerParameters(
            command=self._command,
            args=self._args,
            env=self._env,
        )

    async def list_tools(self) -> list[BaseTool]:
        """连接 Server，获取工具列表，返回 BaseTool 列表"""
        params = self._make_params()
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()

        def make_factory(p=params):
            import contextlib

            @contextlib.asynccontextmanager
            async def _factory():
                async with stdio_client(p) as (r, w):
                    async with ClientSession(r, w) as sess:
                        await sess.initialize()
                        yield sess

            return _factory

        self._tools = [
            MCPToolAdapter(
                tool_name=t.name,
                tool_description=t.description or "",
                input_schema=t.inputSchema if hasattr(t, "inputSchema") else {},
                session_factory=make_factory(),
            )
            for t in result.tools
        ]
        logger.info("MCP stdio: 发现 %d 个工具", len(self._tools))
        return self._tools

    def register_to(self, registry: ToolRegistry) -> None:
        """将已加载的 MCP 工具注册到 ToolRegistry"""
        registry.register_many(self._tools)


class MCPSSEClient:
    """
    通过 HTTP SSE 连接远程 MCP Server。

    使用示例::

        client = MCPSSEClient(url="http://localhost:8000/sse")
        tools = await client.list_tools()
        client.register_to(tool_registry)
    """

    def __init__(self, url: str, headers: dict | None = None) -> None:
        if not _MCP_AVAILABLE:
            raise RuntimeError("mcp 库未安装，请运行 pip install mcp")
        self._url = url
        self._headers = headers or {}
        self._tools: list[BaseTool] = []

    async def list_tools(self) -> list[BaseTool]:
        async with sse_client(self._url, headers=self._headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()

        url = self._url
        headers = self._headers

        def make_factory():
            import contextlib

            @contextlib.asynccontextmanager
            async def _factory():
                async with sse_client(url, headers=headers) as (r, w):
                    async with ClientSession(r, w) as sess:
                        await sess.initialize()
                        yield sess

            return _factory

        self._tools = [
            MCPToolAdapter(
                tool_name=t.name,
                tool_description=t.description or "",
                input_schema=t.inputSchema if hasattr(t, "inputSchema") else {},
                session_factory=make_factory(),
            )
            for t in result.tools
        ]
        logger.info("MCP SSE: 发现 %d 个工具（%s）", len(self._tools), self._url)
        return self._tools

    def register_to(self, registry: ToolRegistry) -> None:
        registry.register_many(self._tools)
