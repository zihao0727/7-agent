"""
Global application state shared across API routes.

This module owns the singleton ToolRegistry, SkillRegistry, and MCP server
configurations used by the backend.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from agent.skills.archive_download_skill import ArchiveDownloadSkill
from agent.skills.browser_skill import BrowserSkill
from agent.skills.code_runner_skill import CodeRunnerSkill
from agent.skills.lark_cli_skill import LarkCliSkill
from agent.skills.stock_quote_skill import StockQuoteSkill
from agent.skills.text_to_image_skill import TextToImageSkill
from agent.skills.wechat_send_skill import WechatSendSkill
from agent.skills.word_to_pdf_skill import WordToPdfSkill
from agent.skills.registry import SkillRegistry
from agent.tools.builtin import get_default_tools
from agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration and runtime status for one MCP server."""

    id: str
    name: str
    transport: str
    command: str = ""
    args: list[str] = field(default_factory=list)
    url: str = ""
    env: dict[str, str] = field(default_factory=dict)
    tool_names: list[str] = field(default_factory=list)
    status: str = "connected"


class AppState:
    """Holds shared registries and MCP connection metadata."""

    def __init__(self) -> None:
        self.tool_registry = ToolRegistry()
        self.skill_registry = SkillRegistry()
        self.mcp_servers: dict[str, MCPServerConfig] = {}
        self.disabled_tools: set[str] = set()
        self._initialized = False

    def initialize(self) -> None:
        """Load built-in tools and register all built-in skills as active."""
        if self._initialized:
            return

        for tool in get_default_tools():
            self.tool_registry.register(tool)

        builtin_skills = [
            ArchiveDownloadSkill(),
            WechatSendSkill(),
            WordToPdfSkill(),
            BrowserSkill(),
            CodeRunnerSkill(),
            LarkCliSkill(),
            StockQuoteSkill(),
            TextToImageSkill(),
        ]

        self.skill_registry.register_many(builtin_skills)

        # All skills are auto-enabled by default.
        for skill in builtin_skills:
            self.tool_registry.register_many(skill.get_tools())
            self.skill_registry._active.add(skill.name)

        self._initialized = True
        logger.info("AppState initialized with tools: %s", self.tool_registry.names())
        logger.info("AppState initialized with skills: %s", self.skill_registry.names())

    def get_active_openai_schemas(self) -> list[dict]:
        """Return OpenAI-compatible schemas for all enabled tools."""
        schemas = []
        for name, tool in self.tool_registry._tools.items():
            if name not in self.disabled_tools:
                schemas.append(tool.schema().to_openai_api())
        return schemas

    def get_tools_info(self) -> list[dict]:
        """Return tool metadata for the frontend."""
        result = []
        for name, tool in self.tool_registry._tools.items():
            schema = tool.schema()
            result.append(
                {
                    "name": name,
                    "description": schema.description,
                    "enabled": name not in self.disabled_tools,
                    "input_schema": schema.input_schema,
                }
            )
        return result

    def toggle_tool(self, name: str, enabled: bool) -> bool:
        if name not in self.tool_registry:
            return False
        if enabled:
            self.disabled_tools.discard(name)
        else:
            self.disabled_tools.add(name)
        return True

    def get_skills_info(self) -> list[dict]:
        """Return skill metadata for the frontend."""
        result = []
        active = set(self.skill_registry.active_names())
        for name, skill in self.skill_registry._skills.items():
            result.append(
                {
                    "name": name,
                    "description": skill.description,
                    "active": name in active,
                    "tools": [tool.name for tool in skill.get_tools()],
                }
            )
        return result

    async def activate_skill(self, name: str) -> bool:
        if name not in self.skill_registry._skills:
            return False
        skill = self.skill_registry._skills[name]
        self.tool_registry.register_many(skill.get_tools())
        self.skill_registry._active.add(name)
        logger.info(
            "Skill '%s' activated with tools: %s",
            name,
            [tool.name for tool in skill.get_tools()],
        )
        return True

    async def deactivate_skill(self, name: str) -> bool:
        if name not in self.skill_registry._active:
            return False
        skill = self.skill_registry._skills[name]
        for tool in skill.get_tools():
            self.tool_registry.unregister(tool.name)
        self.skill_registry._active.discard(name)
        logger.info("Skill '%s' deactivated", name)
        return True

    async def add_mcp_server(
        self,
        name: str,
        transport: str,
        command: str = "",
        args: list[str] | None = None,
        url: str = "",
        env: dict[str, str] | None = None,
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
                raise ValueError(f"Unsupported transport: {transport}")

            cfg.tool_names = [tool.name for tool in tools]
            cfg.status = "connected"
            logger.info("MCP server '%s' connected with tools: %s", name, cfg.tool_names)
        except Exception as exc:
            cfg.status = "error"
            logger.error("MCP server '%s' failed to connect: %s", name, exc)

        return cfg

    def remove_mcp_server(self, server_id: str) -> bool:
        cfg = self.mcp_servers.pop(server_id, None)
        if cfg is None:
            return False
        for tool_name in cfg.tool_names:
            self.tool_registry.unregister(tool_name)
        logger.info("MCP server '%s' removed", cfg.name)
        return True

    def get_mcp_servers_info(self) -> list[dict]:
        return [
            {
                "id": server.id,
                "name": server.name,
                "transport": server.transport,
                "command": server.command,
                "args": server.args,
                "url": server.url,
                "tool_names": server.tool_names,
                "status": server.status,
            }
            for server in self.mcp_servers.values()
        ]


_app_state: AppState | None = None


def get_app_state() -> AppState:
    global _app_state
    if _app_state is None:
        _app_state = AppState()
        _app_state.initialize()
    return _app_state
