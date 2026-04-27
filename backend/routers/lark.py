from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.auth_dependencies import require_current_user
from backend.lark_service import (
    configure_lark_cli,
    delete_lark_account,
    get_lark_account,
    lark_auth_complete,
    lark_auth_login,
    lark_auth_status,
    list_lark_accounts,
    upsert_lark_account,
)

router = APIRouter(tags=["lark"])


class LarkAccountPayload(BaseModel):
    name: str = "default"
    app_id: str
    app_secret: str
    brand: str = Field(default="feishu", pattern="^(feishu|lark)$")
    make_default: bool = True
    configure_cli: bool = True


class LarkAuthLoginPayload(BaseModel):
    recommend: bool = True
    domains: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    no_wait: bool = True


class LarkAuthCompletePayload(BaseModel):
    device_code: str


@router.get("/lark/accounts")
async def accounts(current_user: dict = Depends(require_current_user)) -> dict[str, Any]:
    return {"accounts": await list_lark_accounts(int(current_user["id"]))}


@router.post("/lark/accounts")
async def save_account(
    payload: LarkAccountPayload,
    current_user: dict = Depends(require_current_user),
) -> dict[str, Any]:
    user_id = int(current_user["id"])
    account = await upsert_lark_account(
        user_id=user_id,
        name=payload.name,
        app_id=payload.app_id,
        app_secret=payload.app_secret,
        brand=payload.brand,
        make_default=payload.make_default,
    )
    result: dict[str, Any] = {"account": account}
    if payload.configure_cli:
        configured = await get_lark_account(user_id, int(account["id"]))
        result["configure"] = await configure_lark_cli(configured)
    return result


@router.delete("/lark/accounts/{account_id}")
async def remove_account(
    account_id: int,
    current_user: dict = Depends(require_current_user),
) -> dict[str, bool]:
    await delete_lark_account(int(current_user["id"]), account_id)
    return {"ok": True}


@router.post("/lark/accounts/{account_id}/auth-login")
async def auth_login(
    account_id: int,
    payload: LarkAuthLoginPayload,
    current_user: dict = Depends(require_current_user),
) -> dict[str, Any]:
    account = await get_lark_account(int(current_user["id"]), account_id)
    return await lark_auth_login(
        account,
        recommend=payload.recommend,
        domains=payload.domains or None,
        scopes=payload.scopes or None,
        no_wait=payload.no_wait,
    )


@router.get("/lark/accounts/{account_id}/status")
async def auth_status(
    account_id: int,
    current_user: dict = Depends(require_current_user),
) -> dict[str, Any]:
    account = await get_lark_account(int(current_user["id"]), account_id)
    result = await lark_auth_status(account)
    data = result.get("data")
    connected = bool(data.get("ok")) if isinstance(data, dict) else bool(result.get("ok"))
    return {"connected": connected, "status": "connected" if connected else "unauthorized"}


@router.post("/lark/accounts/{account_id}/auth-complete")
async def auth_complete(
    account_id: int,
    payload: LarkAuthCompletePayload,
    current_user: dict = Depends(require_current_user),
) -> dict[str, Any]:
    account = await get_lark_account(int(current_user["id"]), account_id)
    return await lark_auth_complete(account, payload.device_code)
