from __future__ import annotations

from fastapi import Header, HTTPException

from backend.auth_service import get_user_by_token


def extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        return ""
    prefix = "Bearer "
    if authorization.startswith(prefix):
        return authorization[len(prefix) :].strip()
    return ""


async def require_current_user(
    authorization: str | None = Header(default=None),
) -> dict:
    token = extract_bearer_token(authorization)
    user = await get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user
