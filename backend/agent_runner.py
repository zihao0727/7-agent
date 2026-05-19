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

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from backend.config import get_settings
from backend.intent_router import IntentRoute, format_route_for_prompt
from backend.model_routing import is_kimi_route
from backend.state import AppState

logger = logging.getLogger(__name__)


# ── SSE 行格式化 ───────────────────────────────────────────────────────────────

def _text(chunk: str) -> str:
    return f"0:{json.dumps(chunk, ensure_ascii=False)}\n"

def _split_text_delta(text: str, max_chars: int = 12) -> list[str]:
    """
    Keep the UI streaming even when an upstream provider emits a large text delta.
    Prefer natural break points, but cap chunks so one provider frame cannot paint
    a whole paragraph at once.
    """
    if not text:
        return []

    chunks: list[str] = []
    current = ""
    soft_breaks = set(" \n\t，。！？；：,.!?;:")
    for char in text:
        current += char
        if len(current) >= max_chars or char in soft_breaks:
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return chunks

def _reasoning(chunk: str) -> str:
    return f"g:{json.dumps(chunk, ensure_ascii=False)}\n"

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


def _tool_preamble_from_args(args: dict[str, Any]) -> str:
    purpose = args.get("_purpose")
    if isinstance(purpose, str) and purpose.strip():
        return purpose.strip()
    return "我先执行必要的工具操作来推进这一步。"


def _extract_reasoning_delta(delta: Any) -> str:
    """
    兼容不同 SDK/网关的推理字段命名，提取本次 chunk 的 reasoning 文本增量。
    常见字段：reasoning_content / reasoning。
    """
    if delta is None:
        return ""

    val = getattr(delta, "reasoning_content", None)
    if isinstance(val, str) and val:
        return val

    val = getattr(delta, "reasoning", None)
    if isinstance(val, str) and val:
        return val

    return ""


# ── 客户端工厂 ────────────────────────────────────────────────────

def _make_client(model: str = "deepseek-v4-flash") -> AsyncOpenAI:
    s = get_settings()

    if is_kimi_route(model):
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

BROWSER_TOOL_NAMES = frozenset({
    "browser_navigate",
    "browser_screenshot",
    "browser_extract_text",
    "browser_extract_attrs",
    "browser_extract_table",
    "browser_scroll",
    "browser_click",
    "browser_extract_list",
})
FILE_TOOL_NAMES = frozenset({
    "read_file",
    "write_file",
    "str_replace",
    "edit_file",
    "list_dir",
    "glob_search",
})

# 需要自动注入 session_id 的工具集合（浏览器 + 代码执行）
SESSION_INJECTED_TOOL_NAMES = BROWSER_TOOL_NAMES | FILE_TOOL_NAMES | frozenset({"run_code", "bash"})
SESSION_AND_USER_INJECTED_TOOL_NAMES = BROWSER_TOOL_NAMES | FILE_TOOL_NAMES | frozenset({"run_code", "bash"})
USER_INJECTED_TOOL_NAMES = frozenset({
    "lark_auth",
    "lark_send_message",
    "lark_create_doc",
    "lark_calendar_query",
    "lark_calendar_create",
    "lark_api",
    "lark_command",
    "create_scheduled_task",
    "knowledge_search",
    "knowledge_list_documents",
})
AUTO_STOP_TOOLS = frozenset({"text_to_image"})


async def run_agent_streaming(
    messages: list[dict],
    state: AppState,
    system_prompt: str | None = None,
    model: str = "deepseek-v4-flash",
    session_id: str = "default",
    memory_context: str | None = None,
    current_user_id: int | None = None,
    intent_route: IntentRoute | None = None,
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
    if intent_route:
        prompt = f"{prompt}\n\n{format_route_for_prompt(intent_route)}"
    if memory_context:
        prompt = f"{prompt}\n\n{memory_context}"
    prompt = (
        f"{prompt}\n\n"
        "Verification rules:\n"
        "- For web/current/high-stakes answers, include source links and the date/time context when available.\n"
        "- For medical, legal, financial, tax, insurance, or safety topics, separate facts from suggestions and state uncertainty.\n"
        "- For file-based answers, cite the file or material you used instead of pretending to have seen missing data.\n"
        "- Before sending messages, deleting/overwriting files, or changing external systems, request or use explicit permission."
        "\n\n"
        "Completion rules:\n"
        "- Do not stop just because you have a plausible answer; stop only when the user's task is actually complete, verified, or clearly blocked.\n"
        "- If you created, updated, sent, or wrote something, verify the result with a follow-up tool call before concluding success.\n"
        "- If a tool call fails, or verification shows missing/empty output, continue using tools to fix it instead of ending the task early.\n"
        "- If the task is not complete, make the next tool call needed to finish it; do not hand-wave unfinished work.\n"
        "- Only end without more tool calls when there is nothing meaningful left to do, or when you must surface a real blocker to the user."
    )

    full_messages: list[dict] = [{"role": "system", "content": prompt}] + messages

    tools_schema = state.get_active_openai_schemas()
    logger.debug("工具数=%d", len(tools_schema))

    # ── 调用 LLM（流式）──────────────────────────────────────────────
    try:
        model_name = (
            settings.kimi_model if is_kimi_route(model) else settings.deepseek_model
        )
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
    accumulated_reasoning = ""
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
            for text_part in _split_text_delta(delta.content):
                yield _text(text_part)
                await asyncio.sleep(0.01)

        # 推理内容 delta（thinking/reasoning）—— 不直接展示给用户，但需用于下一轮回传
        r_delta = _extract_reasoning_delta(delta)
        if r_delta:
            accumulated_reasoning += r_delta
            yield _reasoning(r_delta)

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
            parsed_args = json.loads(tc["function"]["arguments"] or "{}")
        except json.JSONDecodeError:
            parsed_args = {}
        args = parsed_args if isinstance(parsed_args, dict) else {}
        args.setdefault("_purpose", _tool_preamble_from_args(args))
        ai_sdk_calls.append({
            "toolCallId": tc["id"],
            "toolName": tc["function"]["name"],
            "args": args,
            **({"reasoning_content": accumulated_reasoning} if accumulated_reasoning else {}),
        })

    # 先发出工具调用事件，让前端立即显示"正在调用"状态
    # ChatGPT / Claude style: show assistant text before the tool-use block.
    # The model is prompted to do this; this fallback enforces it when omitted.
    if not accumulated_text.strip() and ai_sdk_calls:
        yield _text(_tool_preamble_from_args(ai_sdk_calls[0]["args"]))

    for tc in ai_sdk_calls:
        yield _tool_call(tc)

    # 串行执行工具：每完成一个立即推送结果，前端逐个更新为"已完成"
    for ai_tc in ai_sdk_calls:
        tool_name = ai_tc["toolName"]
        # 剥离 _purpose 字段：该字段仅用于前端展示，不传入工具执行
        exec_args = {k: v for k, v in ai_tc["args"].items() if k != "_purpose"}
        # 浏览器工具和代码执行工具自动注入 session_id，实现多会话隔离
        if tool_name in SESSION_INJECTED_TOOL_NAMES:
            exec_args["session_id"] = session_id
        if tool_name in SESSION_AND_USER_INJECTED_TOOL_NAMES:
            exec_args["current_user_id"] = current_user_id
        if tool_name in USER_INJECTED_TOOL_NAMES:
            exec_args["current_user_id"] = current_user_id
        needs_confirmation, permission_profile = state.requires_tool_confirmation(tool_name)
        if needs_confirmation and current_user_id is not None:
            from backend.permission_service import create_permission_request

            skill_name = (permission_profile or {}).get("skill_name") or "unknown"
            risk_level = (permission_profile or {}).get("risk_level") or "unknown"
            permission = create_permission_request(
                user_id=int(current_user_id),
                session_id=session_id,
                tool_name=tool_name,
                action="tool_call",
                summary=f"需要确认后执行 {skill_name} / {tool_name}",
                target=f"风险等级: {risk_level}",
                payload={"kind": "tool_call", "tool_name": tool_name, "args": exec_args},
            )
            yield _tool_result({"toolCallId": ai_tc["toolCallId"], "result": permission})
            continue
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

    # 对仅文生图这类“结果已可直接展示”的工具，直接 stop，避免下一轮重复输出同一图片
    called_tool_names = {tc["toolName"] for tc in ai_sdk_calls}
    if called_tool_names and called_tool_names.issubset(AUTO_STOP_TOOLS):
        yield _done("stop", usage)
        return

    # 默认以 "tool-calls" 结束本轮，前端 useChat（maxSteps>1）将自动发起下一步请求
    yield _done("tool-calls", usage)
