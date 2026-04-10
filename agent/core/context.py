"""
对话上下文管理 —— 维护多轮历史，控制 Token 窗口，注入系统提示
类比 Claude Code 的 conversation history 压缩机制
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .message import Message, Role, TextBlock


@dataclass
class ConversationContext:
    """
    管理一次完整对话的所有消息历史。

    功能亮点：
    - 自动维护 system prompt（含动态 Skill 说明）
    - 简单的滑动窗口截断（保留最近 N 轮）
    - 导出/恢复 JSON 快照
    """

    system_prompt: str = "You are a helpful coding assistant."
    max_turns: int = 40          # 超出后保留最新 N 轮（头尾各保留一条）
    _messages: list[Message] = field(default_factory=list, repr=False)
    _metadata: dict[str, Any] = field(default_factory=dict, repr=False)

    # ── 消息管理 ───────────────────────────────────────────────────────────────

    def add(self, message: Message) -> None:
        self._messages.append(message)
        self._maybe_truncate()

    def add_user(self, text: str) -> Message:
        msg = Message.user(text)
        self.add(msg)
        return msg

    def add_assistant(self, text: str) -> Message:
        msg = Message.assistant_text(text)
        self.add(msg)
        return msg

    def _maybe_truncate(self) -> None:
        """超出 max_turns 时，保留首条（通常是初始 user 请求）+ 最新的消息"""
        if len(self._messages) > self.max_turns:
            keep_head = 2          # 保留最初 2 条（user + assistant）
            keep_tail = self.max_turns - keep_head
            self._messages = self._messages[:keep_head] + self._messages[-keep_tail:]

    # ── 上下文注入 ─────────────────────────────────────────────────────────────

    def inject_skill_context(self, skill_text: str) -> None:
        """
        将 Skill 说明追加到 system prompt，
        使 Agent 获得调用当前 Skill 所需的背景知识。
        """
        if skill_text not in self.system_prompt:
            self.system_prompt = f"{self.system_prompt}\n\n---\n{skill_text}"

    def set_metadata(self, key: str, value: Any) -> None:
        self._metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        return self._metadata.get(key, default)

    # ── 序列化 ────────────────────────────────────────────────────────────────

    def to_api_messages(self) -> list[dict]:
        """导出供 Anthropic API 使用的 messages 列表"""
        return [m.to_api() for m in self._messages]

    def snapshot(self) -> dict:
        """导出 JSON 快照，用于持久化或调试"""
        return {
            "system_prompt": self.system_prompt,
            "max_turns": self.max_turns,
            "messages": [m.to_api() for m in self._messages],
            "metadata": self._metadata,
        }

    @classmethod
    def from_snapshot(cls, data: dict) -> "ConversationContext":
        ctx = cls(
            system_prompt=data.get("system_prompt", ""),
            max_turns=data.get("max_turns", 40),
        )
        ctx._metadata = data.get("metadata", {})
        # 消息历史简单重建（仅文本，工具调用历史不还原，避免状态不一致）
        for m in data.get("messages", []):
            role = Role(m["role"])
            content = m["content"]
            text = content if isinstance(content, str) else ""
            ctx._messages.append(Message(role=role, content=[TextBlock(text=text)]))
        return ctx

    # ── 属性 ──────────────────────────────────────────────────────────────────

    @property
    def messages(self) -> list[Message]:
        return list(self._messages)

    @property
    def turn_count(self) -> int:
        return len(self._messages)

    def __repr__(self) -> str:
        return f"ConversationContext(turns={self.turn_count}, system_prompt={self.system_prompt[:40]!r}…)"
