from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.agent_runner import run_agent_streaming
from backend.auth_dependencies import require_current_user
from backend.chat_upload_materialize import materialize_chat_uploads
from backend.memory_service import build_memory_context
from backend.message_converter import ai_sdk_to_openai
from backend.session_access import assert_session_owned
from backend.state import get_app_state

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    messages: list[dict[str, Any]]
    id: str | None = None               # useChat 内部 thread id（SDK 自动发送）
    sessionId: str | None = None        # 显式会话 ID（由前端 body 注入，用于浏览器 session 隔离）
    system: str | None = None           # 可选：前端自定义 system prompt
    model: str = "deepseek-v4-flash"    # 可选：模型选择（与 X-Model / 前端 id 对齐）


@router.post("/chat")
async def chat(
    req: ChatRequest,
    request: Request,
    current_user: dict = Depends(require_current_user),
) -> StreamingResponse:
    """
    接收 Vercel AI SDK useChat 发来的 messages，
    运行 Agent 循环，流式返回数据流。

    响应头：
      Content-Type: text/plain; charset=utf-8
      x-vercel-ai-data-stream: v1       ← AI SDK 必须识别的标记

    支持从请求头中读取模型选择 (X-Model header)
    文件上传处理：
      - Word: 落盘，注入服务器路径
      - PDF: 提取文本注入（Kimi 用 Files API，DeepSeek 用 pypdf）
      - TXT: 读取文本注入
      - 图片: 保留 vision 格式，发给支持多模态的模型
    """
    state = get_app_state()

    # 从请求头中获取模型选择，优先级：请求头 > 请求体 > 默认值
    model = request.headers.get("X-Model", req.model)

    # materialize_chat_uploads 现在是 async（可能调用 Kimi Files API）
    messages_with_paths = await materialize_chat_uploads(req.messages, model=model)
    openai_messages = ai_sdk_to_openai(messages_with_paths, model=model)
    memory_context = await build_memory_context(current_user["id"], openai_messages)

    # sessionId 优先（前端 body 显式注入），其次 id（SDK thread id），最后 default
    session_id = req.sessionId or req.id or "default"
    if session_id != "default":
        await assert_session_owned(session_id, current_user["id"])

    logger.info(
        "Chat 请求 session=%s，消息数=%d，工具数=%d，模型=%s",
        session_id, len(req.messages), len(state.tool_registry), model,
    )

    async def generator():
        async for line in run_agent_streaming(
            messages=openai_messages,
            state=state,
            system_prompt=req.system,
            model=model,
            session_id=session_id,
            memory_context=memory_context,
            current_user_id=int(current_user["id"]),
        ):
            yield line

    return StreamingResponse(
        generator(),
        media_type="text/plain; charset=utf-8",
        headers={
            "x-vercel-ai-data-stream": "v1",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
