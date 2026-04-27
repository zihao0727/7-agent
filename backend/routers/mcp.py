from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth_dependencies import require_current_user
from backend.state import get_app_state

router = APIRouter(tags=["mcp"])


class MCPAddRequest(BaseModel):
    name: str
    transport: str
    command: str = ""
    args: list[str] = Field(default_factory=list)
    url: str = ""
    env: dict[str, str] = Field(default_factory=dict)


@router.get("/mcp")
async def list_mcp_servers(current_user: dict = Depends(require_current_user)) -> dict:
    state = get_app_state()
    return {"servers": state.get_mcp_servers_info()}


@router.post("/mcp")
async def add_mcp_server(
    body: MCPAddRequest,
    current_user: dict = Depends(require_current_user),
) -> dict:
    if body.transport == "stdio" and not body.command:
        raise HTTPException(status_code=422, detail="stdio 模式必须提供 command")
    if body.transport == "sse" and not body.url:
        raise HTTPException(status_code=422, detail="sse 模式必须提供 url")

    state = get_app_state()
    cfg = await state.add_mcp_server(
        name=body.name,
        transport=body.transport,
        command=body.command,
        args=body.args,
        url=body.url,
        env=body.env,
    )
    return {
        "id": cfg.id,
        "name": cfg.name,
        "status": cfg.status,
        "tool_names": cfg.tool_names,
    }


@router.delete("/mcp/{server_id}")
async def remove_mcp_server(
    server_id: str, current_user: dict = Depends(require_current_user)
) -> dict:
    state = get_app_state()
    ok = state.remove_mcp_server(server_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' 不存在")
    return {"id": server_id, "removed": True}
