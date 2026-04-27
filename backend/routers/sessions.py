from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel

from backend.auth_dependencies import require_current_user
from backend.config import get_settings
from backend.db import get_db
from backend.memory_service import extract_memory_from_session
from backend.models import Message, Session
from backend.session_access import assert_session_owned, session_filter_for_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sessions"])
SUMMARY_MODEL = "deepseek-v4-flash"


def _normalize_text(value: str) -> str:
    return " ".join((value or "").split()).strip("，。！？?!；;、")


def _message_text(message: dict[str, Any], max_chars: int = 500) -> str:
    parts: list[str] = []
    content = _normalize_text(str(message.get("content") or ""))
    if content:
        parts.append(content)

    reasoning = _normalize_text(str(message.get("reasoning_content") or ""))
    if reasoning:
        parts.append(reasoning)

    for part in message.get("parts") or []:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text":
            text = _normalize_text(str(part.get("text") or ""))
            if text:
                parts.append(text)
        elif part.get("type") == "reasoning":
            text = _normalize_text(str(part.get("text") or ""))
            if text:
                parts.append(text)

    merged = _normalize_text(" ".join(parts))
    return merged[:max_chars]


def _fallback_title(messages: list[dict[str, Any]]) -> str:
    for role in ("user", "assistant"):
        for message in messages:
            if message.get("role") != role:
                continue
            text = _message_text(message, max_chars=48)
            if text:
                head = re.split(r"[，。！？?!\n]", text, maxsplit=1)[0].strip()
                return head[:18] if len(head) > 18 else head
    return "新建会话"


async def _summarize_title(messages: list[dict[str, Any]]) -> str:
    settings = get_settings()
    if not settings.deepseek_api_key:
        return _fallback_title(messages)

    chat_history = []
    for message in messages[:12]:
        role = str(message.get("role") or "user")
        text = _message_text(message, max_chars=600)
        if text:
            chat_history.append((role, text))

    if not chat_history:
        return _fallback_title(messages)

    prompt = (
        "请阅读下面的多轮对话，生成一个简短中文标题。"
        "要求：只输出一行标题；不要引号；不要问号结尾；不要输出“新建会话”“聊天”等空泛词。"
    )
    for role, text in chat_history:
        role_label = "用户" if role == "user" else "助手"
        prompt += f"\n{role_label}: {text}"

    try:
        client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        response = await client.chat.completions.create(
            model=SUMMARY_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "你是会话标题生成器，只返回简洁标题本身。",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=60,
            temperature=0.2,
            extra_body={"thinking": {"type": "disabled"}},
        )
        content = (response.choices[0].message.content or "").strip()
        title = _normalize_text(content.splitlines()[0] if content else "")
        if title and title not in {"新建会话", "聊天", "对话", "会话"}:
            return title[:24]
    except Exception as exc:
        logger.warning("会话标题总结失败，回退本地规则: %s", exc)

    return _fallback_title(messages)


class CreateSessionRequest(BaseModel):
    title: str
    description: str | None = None


class AddMessageRequest(BaseModel):
    role: str
    content: str
    tool_invocations: list[dict[str, Any]] | None = None
    reasoning_content: str | None = None
    parts: list[dict[str, Any]] | None = None
    experimental_attachments: list[dict[str, Any]] | None = None


@router.post("/sessions")
async def create_session(
    req: CreateSessionRequest, current_user: dict = Depends(require_current_user)
) -> dict:
    db = get_db()
    session = Session(title=req.title, description=req.description)
    session_doc = session.model_dump()
    session_doc["_id"] = session_doc.pop("id")
    session_doc["user_id"] = current_user["id"]
    await db["sessions"].insert_one(session_doc)
    return {"id": session.id, "title": session.title}


@router.get("/sessions")
async def list_sessions(current_user: dict = Depends(require_current_user)) -> list[dict]:
    db = get_db()
    sessions = (
        await db["sessions"]
        .find({"user_id": current_user["id"]})
        .sort("updated_at", -1)
        .to_list(None)
    )
    return [
        {
            "id": str(session.get("_id") or session.get("id")),
            "title": session["title"],
            "description": session.get("description"),
            "created_at": session["created_at"].isoformat()
            if isinstance(session["created_at"], datetime)
            else session["created_at"],
            "updated_at": session["updated_at"].isoformat()
            if isinstance(session["updated_at"], datetime)
            else session["updated_at"],
            "message_count": len(session.get("messages", [])),
        }
        for session in sessions
    ]


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str, current_user: dict = Depends(require_current_user)
) -> dict:
    session = await assert_session_owned(session_id, current_user["id"])
    messages = sorted(
        session.get("messages", []),
        key=lambda item: item.get("created_at") or datetime.min,
    )
    serialized_messages = []
    for message in messages:
        row = dict(message)
        if isinstance(row.get("created_at"), datetime):
            row["created_at"] = row["created_at"].isoformat()
        serialized_messages.append(row)

    return {
        "id": str(session.get("_id") or session.get("id")),
        "title": session["title"],
        "description": session.get("description"),
        "messages": serialized_messages,
        "created_at": session["created_at"].isoformat()
        if isinstance(session["created_at"], datetime)
        else session["created_at"],
        "updated_at": session["updated_at"].isoformat()
        if isinstance(session["updated_at"], datetime)
        else session["updated_at"],
    }


@router.post("/sessions/{session_id}/messages")
async def add_message(
    session_id: str,
    req: AddMessageRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_current_user),
) -> dict:
    db = get_db()
    await assert_session_owned(session_id, current_user["id"])

    message = Message(
        role=req.role,
        content=req.content,
        tool_invocations=req.tool_invocations,
        reasoning_content=req.reasoning_content,
        parts=req.parts,
        experimental_attachments=req.experimental_attachments,
    )
    await db["sessions"].update_one(
        session_filter_for_user(session_id, current_user["id"]),
        {
            "$push": {"messages": message.model_dump()},
            "$set": {"updated_at": datetime.utcnow()},
        },
    )

    if req.role == "assistant":
        session = await db["sessions"].find_one(
            session_filter_for_user(session_id, current_user["id"])
        )
        if session:
            background_tasks.add_task(
                extract_memory_from_session,
                user_id=current_user["id"],
                session_id=session_id,
                messages=session.get("messages", []),
            )
    return {"id": message.id, "created_at": message.created_at.isoformat()}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str, current_user: dict = Depends(require_current_user)
) -> dict:
    db = get_db()
    result = await db["sessions"].delete_one(
        session_filter_for_user(session_id, current_user["id"])
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="会话不存在")

    try:
        from agent.tools.builtin.browser_tools import get_browser_manager

        await get_browser_manager().close_session(session_id)
    except Exception:
        pass

    return {"id": session_id}


@router.delete("/sessions/{session_id}/messages/{message_index}")
async def delete_messages_after(
    session_id: str,
    message_index: int,
    current_user: dict = Depends(require_current_user),
) -> dict:
    db = get_db()
    session = await assert_session_owned(session_id, current_user["id"])
    messages = session.get("messages", [])
    if message_index < 0 or message_index > len(messages):
        raise HTTPException(status_code=400, detail="消息索引无效")

    remaining_messages = messages[:message_index]
    await db["sessions"].update_one(
        session_filter_for_user(session_id, current_user["id"]),
        {
            "$set": {
                "messages": remaining_messages,
                "updated_at": datetime.utcnow(),
            }
        },
    )
    return {"deleted_count": len(messages) - message_index}


@router.post("/sessions/{session_id}/summarize")
async def summarize_session(
    session_id: str, current_user: dict = Depends(require_current_user)
) -> dict:
    db = get_db()
    session = await assert_session_owned(session_id, current_user["id"])
    messages = sorted(
        session.get("messages", []),
        key=lambda item: item.get("created_at") or datetime.min,
    )
    title = await _summarize_title(messages) if messages else "新建会话"
    await db["sessions"].update_one(
        session_filter_for_user(session_id, current_user["id"]),
        {"$set": {"title": title}},
    )
    return {"title": title}
