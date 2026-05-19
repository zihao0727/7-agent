from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from backend.auth_dependencies import extract_bearer_token, require_current_user
from backend.auth_service import (
    login_user,
    logout_user,
    register_user,
    send_register_email_code,
    update_user_avatar,
)

router = APIRouter(tags=["auth"])


class SendCodeRequest(BaseModel):
    email: str


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    code: str = Field(min_length=6, max_length=6)
    display_name: str | None = Field(default=None, max_length=80)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)


class AvatarRequest(BaseModel):
    avatar_url: str | None = None


@router.post("/auth/send-register-code")
async def send_register_code_api(body: SendCodeRequest, request: Request) -> dict:
    client_ip = request.client.host if request.client else None
    return await send_register_email_code(body.email, client_ip=client_ip)


@router.post("/auth/register")
async def register_api(body: RegisterRequest, request: Request) -> dict:
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return await register_user(
        body.email,
        body.password,
        body.code,
        body.display_name,
        user_agent=user_agent,
        client_ip=client_ip,
    )


@router.post("/auth/login")
async def login_api(body: LoginRequest, request: Request) -> dict:
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return await login_user(
        body.email,
        body.password,
        user_agent=user_agent,
        client_ip=client_ip,
    )


@router.get("/auth/me")
async def me_api(current_user: dict = Depends(require_current_user)) -> dict:
    return {"user": current_user}


@router.patch("/auth/me/avatar")
async def update_avatar_api(
    body: AvatarRequest, current_user: dict = Depends(require_current_user)
) -> dict:
    user = await update_user_avatar(int(current_user["id"]), body.avatar_url)
    return {"user": user}


@router.post("/auth/logout")
async def logout_api(
    request: Request, current_user: dict = Depends(require_current_user)
) -> dict:
    authorization = request.headers.get("authorization")
    await logout_user(extract_bearer_token(authorization))
    return {"ok": True}
