"""
/api/tools —— 工具列表查询与启用状态切换
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.state import get_app_state

router = APIRouter(tags=["tools"])


class ToolToggleRequest(BaseModel):
    enabled: bool


@router.get("/tools")
async def list_tools() -> dict:
    """返回所有注册工具及其启用状态"""
    state = get_app_state()
    return {"tools": state.get_tools_info()}


@router.patch("/tools/{name}/toggle")
async def toggle_tool(name: str, body: ToolToggleRequest) -> dict:
    """启用或禁用指定工具（不从 registry 移除，仅在调用 LLM 时过滤）"""
    state = get_app_state()
    ok = state.toggle_tool(name, body.enabled)
    if not ok:
        raise HTTPException(status_code=404, detail=f"工具 '{name}' 不存在")
    return {"name": name, "enabled": body.enabled}
