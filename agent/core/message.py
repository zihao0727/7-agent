"""
消息模型 —— 对应 Claude API 的 Message 结构
支持 user / assistant / tool_result 多种角色和内容块
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# ── 内容块类型 ─────────────────────────────────────────────────────────────────

@dataclass
class TextBlock:
    text: str
    type: Literal["text"] = field(default="text", init=False)

    def to_api(self) -> dict:
        return {"type": "text", "text": self.text}


@dataclass
class ToolCall:
    """对应 Claude API 的 tool_use 内容块"""
    name: str
    input: dict[str, Any]
    id: str = field(default_factory=lambda: f"toolu_{uuid.uuid4().hex[:16]}")
    type: Literal["tool_use"] = field(default="tool_use", init=False)

    def to_api(self) -> dict:
        return {
            "type": "tool_use",
            "id": self.id,
            "name": self.name,
            "input": self.input,
        }


@dataclass
class ToolResult:
    """对应 Claude API 的 tool_result 内容块（放在 user 消息里）"""
    tool_use_id: str
    content: str | list[dict]
    is_error: bool = False
    type: Literal["tool_result"] = field(default="tool_result", init=False)

    def to_api(self) -> dict:
        return {
            "type": "tool_result",
            "tool_use_id": self.tool_use_id,
            "content": self.content,
            "is_error": self.is_error,
        }


ContentBlock = TextBlock | ToolCall | ToolResult


# ── Message ───────────────────────────────────────────────────────────────────

@dataclass
class Message:
    """单条对话消息，持有若干内容块"""
    role: Role
    content: list[ContentBlock] = field(default_factory=list)

    # ── 工厂方法 ──────────────────────────────────────────────────────────────

    @classmethod
    def user(cls, text: str) -> "Message":
        return cls(role=Role.USER, content=[TextBlock(text=text)])

    @classmethod
    def assistant_text(cls, text: str) -> "Message":
        return cls(role=Role.ASSISTANT, content=[TextBlock(text=text)])

    @classmethod
    def tool_results(cls, results: list[ToolResult]) -> "Message":
        """将工具执行结果打包成 user 消息（Claude 要求格式）"""
        return cls(role=Role.USER, content=list(results))  # type: ignore[arg-type]

    # ── 转换 ──────────────────────────────────────────────────────────────────

    def to_api(self) -> dict:
        """序列化为 Anthropic Messages API 格式"""
        blocks = [block.to_api() for block in self.content]
        # 单纯文本消息可以用字符串简写
        if len(blocks) == 1 and blocks[0]["type"] == "text":
            return {"role": self.role.value, "content": blocks[0]["text"]}
        return {"role": self.role.value, "content": blocks}

    # ── 便捷属性 ──────────────────────────────────────────────────────────────

    @property
    def text_content(self) -> str:
        return " ".join(b.text for b in self.content if isinstance(b, TextBlock))

    @property
    def tool_calls(self) -> list[ToolCall]:
        return [b for b in self.content if isinstance(b, ToolCall)]

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)
