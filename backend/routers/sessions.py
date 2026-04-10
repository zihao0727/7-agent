"""
会话管理 API 路由 —— CRUD 操作
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel

from backend.config import get_settings
from backend.db import get_db
from backend.models import Message, Session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sessions"])

def _session_filter(session_id: str) -> dict:
    """
    兼容历史数据：既支持 _id，也支持早期误写入的 id 字段。
    """
    return {"$or": [{"_id": session_id}, {"id": session_id}]}


class CreateSessionRequest(BaseModel):
    title: str
    description: str | None = None


class AddMessageRequest(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    tool_invocations: list[dict[str, Any]] | None = None
    parts: list[dict[str, Any]] | None = None
    experimental_attachments: list[dict[str, Any]] | None = None


@router.post("/sessions")
async def create_session(req: CreateSessionRequest) -> dict:
    """创建新会话"""
    db = get_db()
    session = Session(title=req.title, description=req.description)

    # 统一使用 _id，避免后续按 _id 查询时 404。
    session_doc = session.model_dump()
    session_doc["_id"] = session_doc.pop("id")
    await db["sessions"].insert_one(session_doc)
    logger.info(f"创建会话: {session.id}")
    
    return {"id": session.id, "title": session.title}


@router.get("/sessions")
async def list_sessions() -> list[dict]:
    """获取所有会话列表（不含消息）"""
    db = get_db()
    sessions = await db["sessions"].find({}).sort("created_at", -1).to_list(None)
    
    return [
        {
            "id": str(s.get("_id") or s.get("id")),
            "title": s["title"],
            "description": s.get("description"),
            "created_at": s["created_at"].isoformat() if isinstance(s["created_at"], datetime) else s["created_at"],
            "updated_at": s["updated_at"].isoformat() if isinstance(s["updated_at"], datetime) else s["updated_at"],
            "message_count": len(s.get("messages", [])),
        }
        for s in sessions
    ]


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    """获取单个会话（含所有消息）"""
    db = get_db()
    session = await db["sessions"].find_one(_session_filter(session_id))
    
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    messages = session.get("messages", [])
    # 按 created_at 升序排列，保证问答顺序正确；时间相同时保留数组插入顺序（稳定排序）
    messages = sorted(
        messages,
        key=lambda m: m.get("created_at") or datetime.min,
    )
    # 将每条消息的 created_at 序列化为 ISO 字符串，便于前端解析
    serialized_messages = []
    for m in messages:
        msg = dict(m)
        if isinstance(msg.get("created_at"), datetime):
            msg["created_at"] = msg["created_at"].isoformat()
        serialized_messages.append(msg)

    return {
        "id": str(session.get("_id") or session.get("id")),
        "title": session["title"],
        "description": session.get("description"),
        "messages": serialized_messages,
        "created_at": session["created_at"].isoformat() if isinstance(session["created_at"], datetime) else session["created_at"],
        "updated_at": session["updated_at"].isoformat() if isinstance(session["updated_at"], datetime) else session["updated_at"],
    }


@router.post("/sessions/{session_id}/messages")
async def add_message(session_id: str, req: AddMessageRequest) -> dict:
    """向会话添加消息"""
    db = get_db()
    
    session = await db["sessions"].find_one(_session_filter(session_id))
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    message = Message(
        role=req.role,
        content=req.content,
        tool_invocations=req.tool_invocations,
        parts=req.parts,
        experimental_attachments=req.experimental_attachments,
    )
    
    # 将消息追加到会话
    await db["sessions"].update_one(
        _session_filter(session_id),
        {
            "$push": {"messages": message.model_dump()},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    
    logger.info(f"向会话 {session_id} 添加消息: {message.id}")
    return {"id": message.id, "created_at": message.created_at.isoformat()}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict:
    """删除会话"""
    db = get_db()
    
    result = await db["sessions"].delete_one(_session_filter(session_id))
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    logger.info(f"删除会话: {session_id}")
    return {"id": session_id}


@router.delete("/sessions/{session_id}/messages/{message_index}")
async def delete_messages_after(session_id: str, message_index: int) -> dict:
    """删除指定消息索引及之后的所有消息"""
    db = get_db()
    
    session = await db["sessions"].find_one(_session_filter(session_id))
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    messages = session.get("messages", [])
    
    if message_index < 0 or message_index >= len(messages):
        raise HTTPException(status_code=400, detail="消息索引无效")
    
    # 保留前 message_index 条消息（删除从 message_index 开始的所有消息）
    remaining_messages = messages[:message_index]
    
    await db["sessions"].update_one(
        _session_filter(session_id),
        {
            "$set": {
                "messages": remaining_messages,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    logger.info(f"删除会话 {session_id} 中索引 {message_index} 及之后的消息")
    return {"deleted_count": len(messages) - message_index}


@router.post("/sessions/{session_id}/summarize")
async def summarize_session(session_id: str) -> dict:
    """使用 DeepSeek 生成会话标题"""
    db = get_db()
    
    session = await db["sessions"].find_one(_session_filter(session_id))
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    messages = session.get("messages", [])
    
    if len(messages) == 0:
        # 如果没有消息，返回默认标题而不是错误
        default_title = "新建会话"
        await db["sessions"].update_one(
            _session_filter(session_id),
            {"$set": {"title": default_title}}
        )
        return {"title": default_title}
    
    # 构建聊天历史用于摘要生成
    chat_history = []
    for msg in messages[:10]:  # 仅使用前10条消息以节省 token
        chat_history.append({
            "role": msg.get("role", "user"),
            "content": msg.get("content", "")[:500]  # 限制单条消息长度
        })
    
    # 调用 DeepSeek（OpenAI 兼容）生成标题
    try:
        settings = get_settings()
        if not settings.deepseek_api_key:
            raise ValueError("DeepSeek API Key 未配置")

        client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )

        prompt = "请根据以下聊天记录，用5-10个字生成一个简洁标题，仅返回标题文本：\n\n"
        for msg in chat_history:
            role_label = "用户" if msg["role"] == "user" else "助手"
            prompt += f"{role_label}: {msg['content']}\n"

        response = await client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[
                {"role": "system", "content": "你是一个标题生成助手，只返回标题文本，不要解释。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=50,
            temperature=0.2,
        )

        title = (response.choices[0].message.content or "").strip().strip('"').strip("'")
        title = " ".join(title.split())
        if not title:
            title = "新建会话"
        
        # 更新会话标题（不更新 updated_at，保持创建顺序）
        await db["sessions"].update_one(
            _session_filter(session_id),
            {"$set": {"title": title}}
        )
        
        logger.info(f"为会话 {session_id} 生成标题: {title}")
        return {"title": title}
        
    except Exception as e:
        logger.error(f"生成标题失败: {e}")
        # 生成失败时使用默认标题
        default_title = "新建会话"
        try:
            await db["sessions"].update_one(
                _session_filter(session_id),
                {"$set": {"title": default_title}}
            )
        except:
            pass
        raise HTTPException(status_code=500, detail=f"生成标题失败: {str(e)}")
