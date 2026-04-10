"""
/api/mcp —— MCP 服务器的增删查
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.state import get_app_state

router = APIRouter(tags=["mcp"])


class MCPAddRequest(BaseModel):
    name: str
    transport: str          # "stdio" | "sse"
    command: str = ""       # stdio 模式
    args: list[str] = []
    url: str = ""           # sse 模式
    env: dict[str, str] = {}


@router.get("/mcp")
async def list_mcp_servers() -> dict:
    """返回所有 MCP 服务器配置和状态"""
    state = get_app_state()
    return {"servers": state.get_mcp_servers_info()}


@router.post("/mcp")
async def add_mcp_server(body: MCPAddRequest) -> dict:
    """
    添加并连接一个 MCP 服务器。
    成功后将该 server 的工具自动注册到 ToolRegistry。
    """
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
async def remove_mcp_server(server_id: str) -> dict:
    """移除 MCP 服务器并注销其工具"""
    state = get_app_state()
    ok = state.remove_mcp_server(server_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"MCP server '{server_id}' 不存在")
    return {"id": server_id, "removed": True}
