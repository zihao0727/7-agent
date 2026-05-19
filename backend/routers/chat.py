from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.agent_runner import run_agent_streaming
from backend.auth_dependencies import require_current_user
from backend.chat_upload_materialize import materialize_chat_uploads
from backend.intent_router import classify_intent
from backend.memory_service import build_memory_context
from backend.message_converter import ai_sdk_to_openai
from backend.session_access import assert_session_owned
from backend.state import get_app_state
from backend.workspace import safe_segment

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])
_SAFE_SESSION_TOKEN = re.compile(r"[^a-zA-Z0-9_.-]+")


class ChatRequest(BaseModel):
    messages: list[dict[str, Any]]
    id: str | None = None
    sessionId: str | None = None
    system: str | None = None
    model: str = "deepseek-v4-flash"


@router.post("/chat")
async def chat(
    req: ChatRequest,
    request: Request,
    current_user: dict = Depends(require_current_user),
) -> StreamingResponse:
    user_id = int(current_user["id"])
    state = get_app_state(user_id)
    model = request.headers.get("X-Model", req.model)

    if req.sessionId:
        session_id = req.sessionId
        await assert_session_owned(session_id, user_id)
    else:
        thread_id = _SAFE_SESSION_TOKEN.sub("_", req.id or "default").strip("_") or "default"
        session_id = f"user_{user_id}_thread_{safe_segment(thread_id)}"

    messages_with_paths = await materialize_chat_uploads(
        req.messages,
        model=model,
        user_id=user_id,
        session_id=session_id,
    )
    openai_messages = ai_sdk_to_openai(messages_with_paths, model=model)
    intent_route = classify_intent(openai_messages, state)
    memory_context = await build_memory_context(user_id, openai_messages)

    logger.info(
        "Chat request session=%s messages=%d tools=%d model=%s user=%s",
        session_id,
        len(req.messages),
        len(state.tool_registry),
        model,
        user_id,
    )

    async def generator():
        async for line in run_agent_streaming(
            messages=openai_messages,
            state=state,
            system_prompt=req.system,
            model=model,
            session_id=session_id,
            memory_context=memory_context,
            current_user_id=user_id,
            intent_route=intent_route,
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
