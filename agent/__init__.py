"""
Claude-Code 风格的 Python Agent 框架
基于 MCP（Model Context Protocol）生态构建
"""

from .core.agent import Agent
from .core.context import ConversationContext
from .core.message import Message, Role, ToolCall, ToolResult
from .tools.base import BaseTool, ToolSchema
from .tools.registry import ToolRegistry
from .skills.base import BaseSkill
from .skills.registry import SkillRegistry

__version__ = "0.1.0"
__all__ = [
    "Agent",
    "ConversationContext",
    "Message",
    "Role",
    "ToolCall",
    "ToolResult",
    "BaseTool",
    "ToolSchema",
    "ToolRegistry",
    "BaseSkill",
    "SkillRegistry",
]
