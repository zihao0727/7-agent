"""
全局运行时状态 —— 单例 ToolRegistry + SkillRegistry + MCP 服务器配置

所有 router 通过 get_app_state() 共享同一份状态。
MCP 服务器在添加时立即加载工具；移除时注销对应工具。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from agent.tools.builtin import get_default_tools
from agent.tools.registry import ToolRegistry
from agent.skills.registry import SkillRegistry
from agent.skills.base import BaseSkill
from agent.skills.archive_download_skill import ArchiveDownloadSkill
from agent.skills.browser_skill import BrowserSkill
from agent.skills.wechat_send_skill import WechatSendSkill
from agent.skills.word_to_pdf_skill import WordToPdfSkill

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """MCP 服务器配置记录"""
    id: str
    name: str
    transport: str          # "stdio" | "sse"
    command: str = ""       # stdio 模式：命令
    args: list[str] = field(default_factory=list)   # stdio 参数
    url: str = ""           # sse 模式：URL
    env: dict[str, str] = field(default_factory=dict)
    tool_names: list[str] = field(default_factory=list)  # 该 server 注册的工具名
    status: str = "connected"  # connected | error | loading


class AppState:
    """应用全局状态"""

    def __init__(self) -> None:
        self.tool_registry = ToolRegistry()
        self.skill_registry = SkillRegistry()
        self.mcp_servers: dict[str, MCPServerConfig] = {}
        # 记录被前端 toggle 禁用的工具名（不发送给 LLM，但不从 registry 移除）
        self.disabled_tools: set[str] = set()
        self._initialized = False

    def initialize(self) -> None:
        """加载内置工具和 Skills（同步，在启动时调用一次）"""
        if self._initialized:
            return
        for t in get_default_tools():
            self.tool_registry.register(t)
        
        # 注册内置 Skills
        self.skill_registry.register(ArchiveDownloadSkill())
        self.skill_registry.register(WechatSendSkill())
        self.skill_registry.register(WordToPdfSkill())
        self.skill_registry.register(BrowserSkill())
        
        self._initialized = True
        logger.info("AppState 已初始化，内置工具: %s", self.tool_registry.names())
        logger.info("AppState 已初始化，注册 Skills: %s", self.skill_registry.names())

    # ── 工具管理 ──────────────────────────────────────────────────────────────

    def get_active_openai_schemas(self) -> list[dict]:
        """返回当前启用工具的 OpenAI 格式 schema 列表"""
        schemas = []
        for name, t in self.tool_registry._tools.items():
            if name not in self.disabled_tools:
                schemas.append(t.schema().to_openai_api())
        return schemas

    def get_tools_info(self) -> list[dict]:
        """返回前端工具列表（含启用状态）"""
        result = []
        for name, t in self.tool_registry._tools.items():
            s = t.schema()
            result.append({
                "name": name,
                "description": s.description,
                "enabled": name not in self.disabled_tools,
                "input_schema": s.input_schema,
            })
        return result

    def toggle_tool(self, name: str, enabled: bool) -> bool:
        if name not in self.tool_registry:
            return False
        if enabled:
            self.disabled_tools.discard(name)
        else:
            self.disabled_tools.add(name)
        return True

    # ── Skill 管理 ────────────────────────────────────────────────────────────

    def get_skills_info(self) -> list[dict]:
        result = []
        active = self.skill_registry.active_names()
        for name, skill in self.skill_registry._skills.items():
            result.append({
                "name": name,
                "description": skill.description,
                "active": name in active,
                "tools": [t.name for t in skill.get_tools()],
            })
        return result

    async def activate_skill(self, name: str) -> bool:
        if name not in self.skill_registry._skills:
            return False
        # ConversationContext 在 Agent 循环里动态创建，此处只注册工具
        skill = self.skill_registry._skills[name]
        tools = skill.get_tools()
        self.tool_registry.register_many(tools)
        self.skill_registry._active.add(name)
        logger.info("Skill '%s' 已激活，注册工具: %s", name, [t.name for t in tools])
        return True

    async def deactivate_skill(self, name: str) -> bool:
        if name not in self.skill_registry._active:
            return False
        skill = self.skill_registry._skills[name]
        for t in skill.get_tools():
            self.tool_registry.unregister(t.name)
        self.skill_registry._active.discard(name)
        logger.info("Skill '%s' 已停用", name)
        return True

    # ── MCP 管理 ──────────────────────────────────────────────────────────────

    async def add_mcp_server(
        self,
        name: str,
        transport: str,
        command: str = "",
        args: list[str] | None = None,
        url: str = "",
        env: dict | None = None,
    ) -> MCPServerConfig:
        server_id = uuid.uuid4().hex[:8]
        cfg = MCPServerConfig(
            id=server_id,
            name=name,
            transport=transport,
            command=command,
            args=args or [],
            url=url,
            env=env or {},
            status="loading",
        )
        self.mcp_servers[server_id] = cfg

        try:
            if transport == "stdio":
                from agent.mcp.client import MCPStdioClient
                client = MCPStdioClient(command=command, args=args or [], env=env)
                tools = await client.list_tools()
                client.register_to(self.tool_registry)
            elif transport == "sse":
                from agent.mcp.client import MCPSSEClient
                client = MCPSSEClient(url=url)
                tools = await client.list_tools()
                client.register_to(self.tool_registry)
            else:
                raise ValueError(f"不支持的 transport: {transport}")

            cfg.tool_names = [t.name for t in tools]
            cfg.status = "connected"
            logger.info("MCP server '%s' 已连接，工具: %s", name, cfg.tool_names)
        except Exception as exc:
            cfg.status = "error"
            logger.error("MCP server '%s' 连接失败: %s", name, exc)

        return cfg

    def remove_mcp_server(self, server_id: str) -> bool:
        cfg = self.mcp_servers.pop(server_id, None)
        if cfg is None:
            return False
        for tool_name in cfg.tool_names:
            self.tool_registry.unregister(tool_name)
        logger.info("MCP server '%s' 已移除", cfg.name)
        return True

    def get_mcp_servers_info(self) -> list[dict]:
        return [
            {
                "id": s.id,
                "name": s.name,
                "transport": s.transport,
                "command": s.command,
                "args": s.args,
                "url": s.url,
                "tool_names": s.tool_names,
                "status": s.status,
            }
            for s in self.mcp_servers.values()
        ]


# 单例
_app_state: AppState | None = None


def get_app_state() -> AppState:
    global _app_state
    if _app_state is None:
        _app_state = AppState()
        _app_state.initialize()
    return _app_state
