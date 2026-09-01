from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket

from backend.auth_dependencies import require_current_user
from backend.auth_service import get_user_by_token
from backend.client_runtime import client_runtime_broker


router = APIRouter(tags=["client-runtime"])


def _bearer_token(value: str | None) -> str:
    scheme, _, token = (value or "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


@router.websocket("/client-runtime/ws")
async def desktop_runtime(websocket: WebSocket) -> None:
    token = _bearer_token(websocket.headers.get("authorization"))
    user = await get_user_by_token(token) if token else None
    if not user:
        await websocket.close(code=4401, reason="Authentication required")
        return
    await client_runtime_broker.serve(int(user["id"]), websocket)


@router.get("/client-runtime/status")
async def desktop_runtime_status(
    current_user: dict = Depends(require_current_user),
) -> dict[str, bool]:
    connected = await client_runtime_broker.is_connected(int(current_user["id"]))
    return {"connected": connected}
