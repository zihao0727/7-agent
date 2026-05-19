from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth_dependencies import require_current_user
from backend.permission_service import get_permission_request, public_permission_request, resolve_permission_request

router = APIRouter(tags=["permissions"])


class ResolvePermissionRequest(BaseModel):
    approved: bool


@router.get("/permissions/{request_id}")
async def get_permission(
    request_id: str,
    current_user: dict = Depends(require_current_user),
) -> dict:
    item = get_permission_request(request_id, int(current_user["id"]))
    if not item:
        raise HTTPException(status_code=404, detail="Permission request not found")
    return {"permission": public_permission_request(item)}


@router.post("/permissions/{request_id}/resolve")
async def resolve_permission(
    request_id: str,
    req: ResolvePermissionRequest,
    current_user: dict = Depends(require_current_user),
) -> dict:
    result = await resolve_permission_request(
        request_id=request_id,
        user_id=int(current_user["id"]),
        approved=req.approved,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Permission request not found")
    return result
