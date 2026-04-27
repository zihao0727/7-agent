from __future__ import annotations

from fastapi import HTTPException

from backend.db import get_db


def session_filter_for_user(session_id: str, user_id: int) -> dict:
    return {
        "$and": [
            {"$or": [{"_id": session_id}, {"id": session_id}]},
            {"user_id": user_id},
        ]
    }


async def assert_session_owned(session_id: str, user_id: int) -> dict:
    db = get_db()
    session = await db["sessions"].find_one(session_filter_for_user(session_id, user_id))
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或无权访问")
    return session
