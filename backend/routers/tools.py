from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth_dependencies import require_current_user
from backend.state import get_app_state

router = APIRouter(tags=["tools"])


class ToolToggleRequest(BaseModel):
    enabled: bool


@router.get("/tools")
async def list_tools(current_user: dict = Depends(require_current_user)) -> dict:
    state = get_app_state()
    return {"tools": state.get_tools_info()}


@router.patch("/tools/{name}/toggle")
async def toggle_tool(
    name: str,
    body: ToolToggleRequest,
    current_user: dict = Depends(require_current_user),
) -> dict:
    state = get_app_state()
    ok = state.toggle_tool(name, body.enabled)
    if not ok:
        raise HTTPException(status_code=404, detail=f"工具 '{name}' 不存在")
    return {"name": name, "enabled": body.enabled}
