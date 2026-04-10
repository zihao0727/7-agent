"""
Agent 核心循环 —— 对标 Claude Code 的 agentic loop

架构：
  ┌─────────────────────────────────────────────┐
  │               Agent Loop                    │
  │                                             │
  │  user_input                                 │
  │      │                                      │
  │      ▼                                      │
  │  ConversationContext.add()                  │
  │      │                                      │
  │      ▼                         ┌──────────┐ │
  │  AnthropicLLM.complete() ◄─────┤ 工具结果  │ │
  │      │                         └──────────┘ │
  │      ▼                              ▲        │
  │  stop_reason == "tool_use"?         │        │
  │      │ YES                          │        │
  │      ▼                              │        │
  │  ToolRegistry.execute()  ───────────┘        │
  │      │ NO (end_turn)                         │
  │      ▼                                      │
  │  返回最终文本响应                             │
  └─────────────────────────────────────────────┘

关键设计：
1. 并行工具调用：同一轮 LLM 响应中的多个 tool_use 并发执行
2. 错误容错：单个工具失败不中断循环，错误作为 tool_result 反馈给 LLM
3. 最大迭代防护：防止无限循环
4. 流式回调：每步执行都触发钩子，方便接入 UI
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Awaitable

from .context import ConversationContext
from .message import Message, Role, ToolCall, ToolResult
from ..llm.anthropic import AnthropicLLM, LLMResponse
from ..tools.registry import ToolRegistry
from ..tools.base import ToolExecutionError
from ..skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

# Agent 循环最大迭代次数（防止无限工具调用链）
DEFAULT_MAX_ITERATIONS = 50


# ── 事件钩子类型 ────────────────────────────────────────────────────────────────

@dataclass
class AgentEvent:
    """Agent 执行过程中产生的事件，传递给回调钩子"""
    type: str          # text_chunk / tool_start / tool_end / error / done
    data: Any = None


OnEventCallback = Callable[[AgentEvent], Awaitable[None]]


# ── 执行结果 ──────────────────────────────────────────────────────────────────

@dataclass
class AgentResult:
    """Agent 一次完整 run() 的执行结果"""
    text: str
    tool_calls_made: int = 0
    total_iterations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_seconds: float = 0.0
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None


# ── Agent ─────────────────────────────────────────────────────────────────────

class Agent:
    """
    Claude-Code 风格的 Agent。

    最小用法::

        agent = Agent.create(api_key="sk-...")
        result = await agent.run("帮我列出当前目录的文件")
        print(result.text)

    完整用法（含 MCP + Skill）::

        agent = Agent.create(api_key="sk-...")
        # 加载 MCP 工具
        mcp_client = MCPStdioClient("python", ["mcp_server.py"])
        tools = await mcp_client.list_tools()
        mcp_client.register_to(agent.tool_registry)
        # 激活 Skill
        agent.skill_registry.load_from_md("skills/git/SKILL.md")
        await agent.skill_registry.activate("git", agent.tool_registry, agent.context)
        # 运行
        result = await agent.run("提交所有更改")
    """

    def __init__(
        self,
        llm: AnthropicLLM,
        tool_registry: ToolRegistry,
        skill_registry: SkillRegistry,
        context: ConversationContext,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        on_event: OnEventCallback | None = None,
    ) -> None:
        self.llm = llm
        self.tool_registry = tool_registry
        self.skill_registry = skill_registry
        self.context = context
        self.max_iterations = max_iterations
        self._on_event = on_event

    # ── 工厂方法 ──────────────────────────────────────────────────────────────

    @classmethod
    def create(
        cls,
        api_key: str | None = None,
        model: str = "claude-opus-4-5",
        system_prompt: str = (
            "你是一个强大的编程助手，能够使用工具完成复杂任务。"
            "优先使用工具而非仅靠记忆回答。每次工具调用后仔细阅读结果再决定下一步。"
            "若工具调用的是 HTTP/API 类接口且返回了 JSON 等结构化数据，面向用户的回复中不要原样粘贴完整响应体；"
            "用一两句话概括是否成功，必要时简述关键业务含义或错误原因（如状态码、错误信息），避免冗长原始 JSON。"
        ),
        max_tokens: int = 8192,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        load_default_tools: bool = True,
        on_event: OnEventCallback | None = None,
    ) -> "Agent":
        """便捷工厂：一行代码创建完整 Agent"""
        from ..tools.builtin import get_default_tools

        llm = AnthropicLLM(api_key=api_key, model=model, max_tokens=max_tokens)
        tool_registry = ToolRegistry()
        skill_registry = SkillRegistry()
        context = ConversationContext(system_prompt=system_prompt)

        if load_default_tools:
            tool_registry.register_many(get_default_tools())

        return cls(
            llm=llm,
            tool_registry=tool_registry,
            skill_registry=skill_registry,
            context=context,
            max_iterations=max_iterations,
            on_event=on_event,
        )

    # ── 主入口 ────────────────────────────────────────────────────────────────

    async def run(self, user_input: str) -> AgentResult:
        """
        执行一次完整的 Agent 任务：
          1. 将用户输入加入上下文
          2. 调用 LLM
          3. 若 LLM 请求工具调用 → 执行工具 → 将结果反馈给 LLM → 重复
          4. 直到 stop_reason == "end_turn" 或达到最大迭代次数
          5. 返回 AgentResult
        """
        start_time = time.monotonic()
        self.context.add_user(user_input)

        total_tool_calls = 0
        total_input_tokens = 0
        total_output_tokens = 0
        final_text = ""
        error_msg: str | None = None

        for iteration in range(self.max_iterations):
            logger.debug("Agent iteration %d/%d", iteration + 1, self.max_iterations)

            # ── 调用 LLM ───────────────────────────────────────────────────────
            try:
                llm_response = await self.llm.complete(
                    messages=self.context.to_api_messages(),
                    system=self.context.system_prompt,
                    tools=self.tool_registry.to_api_schemas() or None,
                )
            except Exception as exc:
                error_msg = f"LLM 调用失败: {exc}"
                logger.error(error_msg)
                await self._emit(AgentEvent(type="error", data=error_msg))
                break

            total_input_tokens += llm_response.input_tokens
            total_output_tokens += llm_response.output_tokens

            # 将 assistant 消息加入上下文
            self.context.add(llm_response.message)

            # 流出文本内容
            if llm_response.text:
                final_text = llm_response.text
                await self._emit(AgentEvent(type="text_chunk", data=llm_response.text))

            # ── 判断是否需要工具调用 ─────────────────────────────────────────────
            if llm_response.stop_reason != "tool_use":
                logger.debug("Agent loop ended: stop_reason=%s", llm_response.stop_reason)
                break

            if not llm_response.tool_calls:
                logger.warning("stop_reason=tool_use 但没有 tool_calls，强制退出")
                break

            # ── 并行执行所有工具调用 ─────────────────────────────────────────────
            tool_results = await self._execute_tool_calls_parallel(
                llm_response.tool_calls
            )
            total_tool_calls += len(llm_response.tool_calls)

            # 将工具结果作为 user 消息反馈给 LLM
            result_msg = Message.tool_results(tool_results)
            self.context.add(result_msg)

        else:
            # 达到最大迭代次数
            error_msg = f"Agent 达到最大迭代次数 ({self.max_iterations})"
            logger.warning(error_msg)

        elapsed = time.monotonic() - start_time
        await self._emit(AgentEvent(type="done", data=final_text))

        return AgentResult(
            text=final_text,
            tool_calls_made=total_tool_calls,
            total_iterations=iteration + 1,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            elapsed_seconds=elapsed,
            error=error_msg,
        )

    async def stream_run(self, user_input: str) -> AsyncIterator[str]:
        """
        流式执行变体：逐 token 产出文本。
        工具调用步骤不流式（等待执行完毕后继续）。
        """
        self.context.add_user(user_input)

        for iteration in range(self.max_iterations):
            # 流式模式：先用 complete 获取结构化响应（含工具调用解析）
            # 若为纯文本轮次，可改用 stream()
            llm_response = await self.llm.complete(
                messages=self.context.to_api_messages(),
                system=self.context.system_prompt,
                tools=self.tool_registry.to_api_schemas() or None,
            )

            self.context.add(llm_response.message)

            if llm_response.text:
                yield llm_response.text

            if llm_response.stop_reason != "tool_use":
                break

            if not llm_response.tool_calls:
                break

            tool_results = await self._execute_tool_calls_parallel(
                llm_response.tool_calls
            )
            result_msg = Message.tool_results(tool_results)
            self.context.add(result_msg)

    # ── 工具执行 ──────────────────────────────────────────────────────────────

    async def _execute_tool_calls_parallel(
        self, tool_calls: list[ToolCall]
    ) -> list[ToolResult]:
        """
        并发执行所有工具调用（asyncio.gather）。
        单个工具失败不影响其他工具，错误作为 is_error=True 的结果返回。
        """
        tasks = [self._execute_single_tool(tc) for tc in tool_calls]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return list(results)

    async def _execute_single_tool(self, tool_call: ToolCall) -> ToolResult:
        """执行单个工具调用，捕获异常并转为错误结果"""
        await self._emit(
            AgentEvent(
                type="tool_start",
                data={"name": tool_call.name, "input": tool_call.input},
            )
        )

        try:
            output = await self.tool_registry.execute(
                tool_call.name, tool_call.input
            )
            is_error = False
        except ToolExecutionError as exc:
            output = f"工具执行错误: {exc}"
            is_error = True
            logger.warning("Tool '%s' failed: %s", tool_call.name, exc)
        except Exception as exc:
            output = f"意外错误: {exc}"
            is_error = True
            logger.exception("Unexpected error in tool '%s'", tool_call.name)

        await self._emit(
            AgentEvent(
                type="tool_end",
                data={
                    "name": tool_call.name,
                    "output": output[:200],
                    "is_error": is_error,
                },
            )
        )

        return ToolResult(
            tool_use_id=tool_call.id,
            content=output,
            is_error=is_error,
        )

    # ── 事件系统 ──────────────────────────────────────────────────────────────

    async def _emit(self, event: AgentEvent) -> None:
        if self._on_event:
            try:
                await self._on_event(event)
            except Exception:
                logger.exception("on_event callback raised an error")

    # ── 便捷方法 ──────────────────────────────────────────────────────────────

    def reset_context(self, keep_system: bool = True) -> None:
        """重置对话历史，开启新任务"""
        system = self.context.system_prompt if keep_system else ""
        self.context = ConversationContext(system_prompt=system)

    def add_tool(self, tool) -> None:
        self.tool_registry.register(tool)

    async def load_mcp_stdio(self, command: str, args: list[str] | None = None) -> None:
        """快捷方法：加载 stdio MCP server 的工具"""
        from ..mcp.client import MCPStdioClient
        client = MCPStdioClient(command=command, args=args)
        await client.list_tools()
        client.register_to(self.tool_registry)

    async def load_mcp_sse(self, url: str) -> None:
        """快捷方法：加载 SSE MCP server 的工具"""
        from ..mcp.client import MCPSSEClient
        client = MCPSSEClient(url=url)
        await client.list_tools()
        client.register_to(self.tool_registry)

    def __repr__(self) -> str:
        return (
            f"Agent(model={self.llm.model!r}, "
            f"tools={len(self.tool_registry)}, "
            f"turns={self.context.turn_count})"
        )
