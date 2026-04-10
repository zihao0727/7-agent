"""
DeepSeek Agent 单步执行 —— 流式输出 Vercel AI SDK 数据流格式

每次 HTTP 请求只执行一次 LLM 调用（单步），多轮循环由前端 useChat maxSteps 驱动：
  1. LLM 响应若包含工具调用 → 串行执行工具，逐个推送结果，以 finishReason="tool-calls" 结束
  2. LLM 响应若无工具调用 → 以 finishReason="stop" 结束
  3. 前端收到 "tool-calls" 后自动携带工具结果发起下一轮请求

这样每个工具调用的结果在完成时立即推送给前端（分步/流式展示，类 Manus 交互）。

数据流协议（每行 \\n 结尾，Content-Type: text/plain; charset=utf-8）：
  0:"文本 delta"      ← 文本增量
  9:{toolCallId,...}  ← 单个工具调用
  a:{toolCallId,...}  ← 单个工具结果
  3:"错误信息"        ← 错误
  d:{finishReason}    ← 结束标记（"stop" | "tool-calls" | "error"）
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from backend.config import get_settings
from backend.state import AppState

logger = logging.getLogger(__name__)


# ── SSE 行格式化 ───────────────────────────────────────────────────────────────

def _text(chunk: str) -> str:
    return f"0:{json.dumps(chunk, ensure_ascii=False)}\n"

def _tool_call(call: dict) -> str:
    return f"9:{json.dumps(call, ensure_ascii=False)}\n"

def _tool_result(result: dict) -> str:
    return f"a:{json.dumps(result, ensure_ascii=False)}\n"

def _error(msg: str) -> str:
    return f"3:{json.dumps(msg, ensure_ascii=False)}\n"

def _done(finish_reason: str = "stop", usage: dict | None = None) -> str:
    payload: dict[str, Any] = {"finishReason": finish_reason}
    if usage:
        payload["usage"] = usage
    return f"d:{json.dumps(payload, ensure_ascii=False)}\n"


# ── 客户端工厂 ────────────────────────────────────────────────────

def _make_client(model: str = "deepseek-chat") -> AsyncOpenAI:
    s = get_settings()

    if model == "kimi-k2.5":
        logger.info(f"使用 Kimi 模型: base_url={s.kimi_base_url}, model={s.kimi_model}")
        return AsyncOpenAI(
            api_key=s.kimi_api_key,
            base_url=s.kimi_base_url,
        )
    else:
        logger.info(f"使用 DeepSeek 模型: base_url={s.deepseek_base_url}, model={s.deepseek_model}")
        return AsyncOpenAI(
            api_key=s.deepseek_api_key,
            base_url=s.deepseek_base_url,
        )


# ── 单步 Agent 执行 ───────────────────────────────────────────────────────────

async def run_agent_streaming(
    messages: list[dict],
    state: AppState,
    system_prompt: str | None = None,
    model: str = "deepseek-chat",
) -> AsyncIterator[str]:
    """
    执行单步 Agent 操作，逐行 yield SSE 数据流字符串。

    - 每次请求只做一次 LLM 调用，不再内部循环。
    - 工具调用串行执行，每完成一个立即 yield 结果，前端可实时更新状态。
    - 若有工具调用，以 finishReason="tool-calls" 结束；前端 useChat（maxSteps>1）
      自动携带工具结果发起下一步请求，从而实现分步/类 Manus 的交互体验。
    """
    settings = get_settings()
    logger.info("开始单步 Agent，模型: %s，消息数: %d", model, len(messages))
    client = _make_client(model)
    prompt = system_prompt or settings.system_prompt

    full_messages: list[dict] = [{"role": "system", "content": prompt}] + messages

    tools_schema = state.get_active_openai_schemas()
    logger.debug("工具数=%d", len(tools_schema))

    # ── 调用 LLM（流式）──────────────────────────────────────────────
    try:
        model_name = settings.kimi_model if model == "kimi-k2.5" else settings.deepseek_model
        stream = await client.chat.completions.create(
            model=model_name,
            messages=full_messages,
            tools=tools_schema if tools_schema else None,
            tool_choice="auto" if tools_schema else None,
            max_tokens=settings.max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
    except Exception as exc:
        yield _error(f"LLM 调用失败: {exc}")
        yield _done("error")
        return

    # ── 逐 chunk 流式收集响应 ─────────────────────────────────────────
    accumulated_text = ""
    accumulated_tool_calls: dict[int, dict] = {}
    finish_reason = "stop"
    total_prompt_tokens = 0
    total_completion_tokens = 0

    async for chunk in stream:
        if chunk.usage:
            total_prompt_tokens += chunk.usage.prompt_tokens or 0
            total_completion_tokens += chunk.usage.completion_tokens or 0

        if not chunk.choices:
            continue

        choice = chunk.choices[0]
        delta = choice.delta
        finish_reason = choice.finish_reason or finish_reason

        # 文本 delta —— 实时推送给前端
        if delta.content:
            accumulated_text += delta.content
            yield _text(delta.content)

        # 工具调用 delta —— 流式累积，等完整后再处理
        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
                if idx not in accumulated_tool_calls:
                    accumulated_tool_calls[idx] = {
                        "id": "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    }
                tc = accumulated_tool_calls[idx]
                if tc_delta.id:
                    tc["id"] = tc_delta.id
                if tc_delta.function:
                    if tc_delta.function.name:
                        tc["function"]["name"] += tc_delta.function.name
                    if tc_delta.function.arguments:
                        tc["function"]["arguments"] += tc_delta.function.arguments

    usage = {
        "promptTokens": total_prompt_tokens,
        "completionTokens": total_completion_tokens,
    }

    # ── 处理工具调用 ──────────────────────────────────────────────────
    if not accumulated_tool_calls:
        # 无工具调用，正常结束
        yield _done("stop", usage)
        return

    tool_calls_list = [accumulated_tool_calls[i] for i in sorted(accumulated_tool_calls)]

    # 构建 AI SDK 格式的工具调用列表
    ai_sdk_calls: list[dict] = []
    for tc in tool_calls_list:
        try:
            args = json.loads(tc["function"]["arguments"] or "{}")
        except json.JSONDecodeError:
            args = {}
        ai_sdk_calls.append({
            "toolCallId": tc["id"],
            "toolName": tc["function"]["name"],
            "args": args,
        })

    # 先发出所有工具调用事件，让前端立即显示"正在调用"状态
    for tc in ai_sdk_calls:
        yield _tool_call(tc)

    # 串行执行工具：每完成一个立即推送结果，前端逐个更新为"已完成"
    for ai_tc in ai_sdk_calls:
        tool_name = ai_tc["toolName"]
        # 剥离 _purpose 字段：该字段仅用于前端展示，不传入工具执行
        exec_args = {k: v for k, v in ai_tc["args"].items() if k != "_purpose"}
        try:
            result = await state.tool_registry.execute(tool_name, exec_args)
            logger.info("工具 '%s' 执行完成", tool_name)
            yield _tool_result({"toolCallId": ai_tc["toolCallId"], "result": result})
        except Exception as exc:
            logger.warning("工具 '%s' 执行失败: %s", tool_name, exc)
            yield _tool_result({
                "toolCallId": ai_tc["toolCallId"],
                "result": f"错误: {exc}",
                "isError": True,
            })

    # 以 "tool-calls" 结束本轮，前端 useChat（maxSteps>1）将自动发起下一步请求
    yield _done("tool-calls", usage)
