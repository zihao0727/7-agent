"""
数据模型 —— Session（会话）和 Message（消息）
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class Message(BaseModel):
    """聊天消息"""
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    role: str  # "user" | "assistant" | "system"
    content: str  # 消息内容（纯文本或 markdown）
    tool_invocations: Optional[list[dict[str, Any]]] = None  # 工具调用
    reasoning_content: Optional[str] = None  # thinking/reasoning 原文，供下一轮请求回传
    # AI SDK parts 数组，保留文本与工具调用的交错顺序，用于历史记录精确恢复
    parts: Optional[list[dict[str, Any]]] = None
    # 用户消息附件元数据（仅文件名/类型，不含 data URL，便于历史记录展示）
    experimental_attachments: Optional[list[dict[str, Any]]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class Session(BaseModel):
    """聊天会话"""
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    title: str  # 会话标题
    description: Optional[str] = None  # 会话描述
    messages: list[Message] = Field(default_factory=list)  # 消息列表
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
