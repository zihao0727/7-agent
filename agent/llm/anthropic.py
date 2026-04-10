"""
Anthropic Claude LLM 后端 ——
封装 Messages API，支持流式输出和工具调用解析

参考：https://docs.anthropic.com/en/api/messages
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import AsyncIterator, Any

import anthropic

from ..core.message import Message, Role, TextBlock, ToolCall

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-4-5"
DEFAULT_MAX_TOKENS = 8192


@dataclass
class LLMResponse:
    """
    LLM 单次响应的结构化表示。
    stop_reason 决定 Agent 循环的下一步行为：
      - "end_turn"      → 正常结束，输出最终答案
      - "tool_use"      → 需要执行工具，继续循环
      - "max_tokens"    → Token 耗尽，需截断或报错
    """
    message: Message                    # 解析后的 assistant 消息
    stop_reason: str                    # end_turn / tool_use / max_tokens
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = DEFAULT_MODEL

    @property
    def tool_calls(self) -> list[ToolCall]:
        return self.message.tool_calls

    @property
    def text(self) -> str:
        return self.message.text_content


class AnthropicLLM:
    """
    Claude Messages API 的轻量封装。

    支持：
    - 同步 complete()      → 一次性获取完整响应
    - 流式 stream()        → AsyncIterator[str] 实时返回文本
    - 工具调用自动解析      → 返回 LLMResponse（含 ToolCall 列表）
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        base_url: str | None = None,
        default_headers: dict | None = None,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens

        client_kwargs: dict[str, Any] = {
            "api_key": api_key or os.environ.get("ANTHROPIC_API_KEY", ""),
        }
        if base_url:
            client_kwargs["base_url"] = base_url
        if default_headers:
            client_kwargs["default_headers"] = default_headers

        self._client = anthropic.AsyncAnthropic(**client_kwargs)

    # ── 核心调用 ───────────────────────────────────────────────────────────────

    async def complete(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] | None = None,
        temperature: float = 1.0,
        **extra_kwargs: Any,
    ) -> LLMResponse:
        """
        一次性调用 Messages API，返回解析好的 LLMResponse。
        Agent 循环的核心驱动方法。
        """
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": messages,
            "temperature": temperature,
            **extra_kwargs,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        logger.debug(
            "LLM call: model=%s, messages=%d, tools=%d",
            self._model, len(messages), len(tools or []),
        )

        response = await self._client.messages.create(**kwargs)

        # 解析 content blocks → Message
        content_blocks = []
        for block in response.content:
            if block.type == "text":
                content_blocks.append(TextBlock(text=block.text))
            elif block.type == "tool_use":
                content_blocks.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        input=block.input,
                    )
                )

        assistant_msg = Message(role=Role.ASSISTANT, content=content_blocks)

        return LLMResponse(
            message=assistant_msg,
            stop_reason=response.stop_reason or "end_turn",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
        )

    async def stream(
        self,
        messages: list[dict],
        system: str = "",
        tools: list[dict] | None = None,
        temperature: float = 1.0,
    ) -> AsyncIterator[str]:
        """
        流式输出文本 token（不含工具调用解析，适合纯文本场景）。
        工具调用场景请使用 complete()。
        """
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": messages,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    # ── 属性 ──────────────────────────────────────────────────────────────────

    @property
    def model(self) -> str:
        return self._model

    def __repr__(self) -> str:
        return f"AnthropicLLM(model={self._model!r})"
