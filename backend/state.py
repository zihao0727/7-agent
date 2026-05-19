"""
Global application state shared across API routes.

This module owns the singleton ToolRegistry, SkillRegistry, and MCP server
configurations used by the backend.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.skills.archive_download_skill import ArchiveDownloadSkill
from agent.skills.browser_skill import BrowserSkill
from agent.skills.code_runner_skill import CodeRunnerSkill
from agent.skills.lark_skill import LarkSkill
from agent.skills.knowledge_base_skill import KnowledgeBaseSkill
from agent.skills.pdf2zh_translator import Pdf2zhTranslatorSkill
from agent.skills.stock_quote_skill import StockQuoteSkill
from agent.skills.text_to_image_skill import TextToImageSkill
from agent.skills.wechat_send_skill import WechatSendSkill
from agent.skills.word_to_pdf_skill import WordToPdfSkill
from agent.skills.registry import SkillRegistry
from agent.tools.builtin import get_default_tools
from agent.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

RISK_LEVELS = {"low", "medium", "high", "unknown"}
SKILL_PERMISSION_ALIASES = {
    "archive_download": "archive_download_skill",
    "browser": "browser_skill",
    "code_runner": "code_runner_skill",
    "lark": "lark",
    "pdf_layout_translator": "pdf2zh_translator",
    "stock_quote": "stock_quote_skill",
    "text_to_image": "text_to_image_skill",
    "wechat_send": "wechat_send_skill",
    "word_to_pdf": "word_to_pdf_skill",
    "knowledge_base": "knowledge_base_skill",
}

_STATE_LOCK = threading.Lock()
_STATE_CACHE: dict[str, "AppState"] = {}


def _state_cache_key(user_id: int | None) -> str:
    return f"user:{int(user_id)}" if user_id is not None else "system"


def _skill_permission_config_path(user_id: int | None) -> Path:
    base = Path(__file__).resolve().parent.parent / "data" / "skill_permissions"
    if user_id is None:
        return base / "system.json"
    return base / f"user_{int(user_id)}.json"


SKILL_PERMISSION_PROFILES: dict[str, dict[str, Any]] = {
    "archive_download_skill": {
        "capabilities": ["打包生成文件", "提供下载链接"],
        "access": ["本地生成目录"],
        "risk_level": "low",
        "requires_confirmation_for": ["覆盖已有归档"],
    },
    "browser_skill": {
        "capabilities": ["打开网页", "点击页面", "读取网页文本和截图"],
        "access": ["网络", "浏览器会话"],
        "risk_level": "medium",
        "requires_confirmation_for": ["提交表单", "登录后操作", "购买或发布内容"],
    },
    "code_runner_skill": {
        "capabilities": ["运行代码", "执行命令"],
        "access": ["工作区文件", "本机命令环境"],
        "risk_level": "high",
        "requires_confirmation_for": ["删除文件", "安装依赖", "访问外部网络"],
    },
    "lark": {
        "capabilities": ["操作飞书消息、云文档、日历和 OpenAPI"],
        "access": ["飞书账号授权数据"],
        "risk_level": "high",
        "requires_confirmation_for": ["发送消息", "修改云文档", "邀请成员"],
    },
    "office-file-analyst": {
        "capabilities": ["解析 Office/PDF/表格文件", "生成摘要和分析"],
        "access": ["用户上传文件"],
        "risk_level": "medium",
        "requires_confirmation_for": ["写回或导出文件"],
    },
    "pdf2zh_translator": {
        "capabilities": ["翻译 PDF", "生成译文文件"],
        "access": ["用户上传 PDF"],
        "risk_level": "medium",
        "requires_confirmation_for": ["覆盖译文文件"],
    },
    "stock_quote_skill": {
        "capabilities": ["查询股票行情", "生成市场摘要"],
        "access": ["网络行情源"],
        "risk_level": "medium",
        "requires_confirmation_for": ["无；但不得构成投资承诺"],
    },
    "text_to_image_skill": {
        "capabilities": ["生成图片"],
        "access": ["图像生成服务"],
        "risk_level": "low",
        "requires_confirmation_for": ["使用敏感人物或品牌素材"],
    },
    "wechat_send_skill": {
        "capabilities": ["按联系人发送微信消息"],
        "access": ["微信联系人/消息发送能力"],
        "risk_level": "high",
        "requires_confirmation_for": ["任何发送动作"],
    },
    "word_to_pdf_skill": {
        "capabilities": ["Word 转 PDF"],
        "access": ["用户上传 Word 文件"],
        "risk_level": "low",
        "requires_confirmation_for": ["覆盖输出文件"],
    },
    "knowledge_base_skill": {
        "capabilities": ["索引文件/网页/聊天记录", "检索个人知识库", "返回引用来源"],
        "access": ["MongoDB 文档库", "用户上传文件", "已保存会话"],
        "risk_level": "medium",
        "requires_confirmation_for": ["索引敏感文件", "删除知识库文档"],
    },
}


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

    def __init__(self, user_id: int | None = None) -> None:
        self.user_id = user_id
        self.tool_registry = ToolRegistry()
        self.skill_registry = SkillRegistry()
        self.mcp_servers: dict[str, MCPServerConfig] = {}
        self.disabled_tools: set[str] = set()
        self._skill_permission_config_path = _skill_permission_config_path(user_id)
        self.skill_permission_overrides: dict[str, dict[str, Any]] = self._load_skill_permission_overrides()
        self._initialized = False

    def _load_skill_permission_overrides(self) -> dict[str, dict[str, Any]]:
        try:
            if not self._skill_permission_config_path.exists():
                return {}
            data = json.loads(self._skill_permission_config_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning("Failed to load skill permission config: %s", exc)
            return {}

    def _save_skill_permission_overrides(self) -> None:
        self._skill_permission_config_path.parent.mkdir(parents=True, exist_ok=True)
        self._skill_permission_config_path.write_text(
            json.dumps(self.skill_permission_overrides, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _permission_profile_for_skill(self, name: str, description: str = "") -> dict[str, Any]:
        base = dict(
            SKILL_PERMISSION_PROFILES.get(
                name,
                SKILL_PERMISSION_PROFILES.get(
                    SKILL_PERMISSION_ALIASES.get(name, ""),
                    {
                        "capabilities": [description or "Custom skill"],
                        "access": ["未声明"],
                        "risk_level": "unknown",
                        "requires_confirmation_for": ["外部写入、发送、删除或高风险操作"],
                    },
                ),
            )
        )
        base.update(self.skill_permission_overrides.get(name) or {})
        risk = str(base.get("risk_level") or "unknown")
        if risk not in RISK_LEVELS:
            risk = "unknown"
        base["risk_level"] = risk
        base["requires_confirmation"] = bool(base.get("requires_confirmation", False))
        base.setdefault("access", [])
        base.setdefault("capabilities", [])
        base.setdefault("requires_confirmation_for", [])
        return base

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
            KnowledgeBaseSkill(),
            LarkSkill(),
            Pdf2zhTranslatorSkill(),
            StockQuoteSkill(),
            TextToImageSkill(),
        ]

        self.skill_registry.register_many(builtin_skills)
        office_file_skill = self.skill_registry.load_from_md(
            Path(__file__).resolve().parent.parent
            / "agent"
            / "skills"
            / "office-file-analyst"
            / "SKILL.md",
            name="office-file-analyst",
        )
        builtin_skills.append(office_file_skill)

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
            permissions = self._permission_profile_for_skill(name, skill.description)
            result.append(
                {
                    "name": name,
                    "description": skill.description,
                    "active": name in active,
                    "tools": [tool.name for tool in skill.get_tools()],
                    "permissions": permissions,
                }
            )
        return result

    def update_skill_permissions(
        self,
        name: str,
        *,
        risk_level: str | None = None,
        requires_confirmation: bool | None = None,
    ) -> dict[str, Any] | None:
        skill = self.skill_registry._skills.get(name)
        if not skill:
            return None
        patch: dict[str, Any] = {}
        if risk_level is not None:
            if risk_level not in RISK_LEVELS:
                raise ValueError(f"Unsupported risk level: {risk_level}")
            patch["risk_level"] = risk_level
        if requires_confirmation is not None:
            patch["requires_confirmation"] = bool(requires_confirmation)
        self.skill_permission_overrides[name] = {
            **self.skill_permission_overrides.get(name, {}),
            **patch,
        }
        self._save_skill_permission_overrides()
        return self._permission_profile_for_skill(name, skill.description)

    def get_skill_name_for_tool(self, tool_name: str) -> str | None:
        for name, skill in self.skill_registry._skills.items():
            if any(tool.name == tool_name for tool in skill.get_tools()):
                return name
        return None

    def requires_tool_confirmation(self, tool_name: str) -> tuple[bool, dict[str, Any] | None]:
        skill_name = self.get_skill_name_for_tool(tool_name)
        if not skill_name:
            return False, None
        skill = self.skill_registry._skills.get(skill_name)
        profile = self._permission_profile_for_skill(skill_name, skill.description if skill else "")
        return bool(profile.get("requires_confirmation")), {"skill_name": skill_name, **profile}

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


def get_app_state(user_id: int | None = None) -> AppState:
    key = _state_cache_key(user_id)
    with _STATE_LOCK:
        state = _STATE_CACHE.get(key)
        if state is None:
            state = AppState(user_id=user_id)
            state.initialize()
            _STATE_CACHE[key] = state
        return state
