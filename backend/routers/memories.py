from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth_dependencies import require_current_user
from backend.memory_service import (
    MEMORY_KINDS,
    confirm_memory,
    create_memory,
    delete_memory,
    list_memories,
    update_memory,
)

router = APIRouter(tags=["memories"])


MemoryKind = Literal[
    "preference",
    "profile",
    "project",
    "contact",
    "format",
    "taboo",
    "instruction",
    "fact",
]


class CreateMemoryRequest(BaseModel):
    content: str = Field(min_length=1, max_length=1000)
    kind: MemoryKind = "fact"
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    needs_confirmation: bool = False


class UpdateMemoryRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=1000)
    kind: MemoryKind | None = None
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    status: Literal["active", "pending", "archived"] | None = None
    needs_confirmation: bool | None = None


class ConfirmMemoryRequest(BaseModel):
    approved: bool


@router.get("/memories")
async def get_memories(
    include_archived: bool = False,
    current_user: dict = Depends(require_current_user),
) -> dict:
    memories = await list_memories(current_user["id"], include_archived=include_archived)
    return {"memories": memories, "kinds": sorted(MEMORY_KINDS)}


@router.post("/memories")
async def add_memory(
    req: CreateMemoryRequest,
    current_user: dict = Depends(require_current_user),
) -> dict:
    memory = await create_memory(
        current_user["id"],
        req.content,
        kind=req.kind,
        importance=req.importance,
        confidence=req.confidence,
        status="pending" if req.needs_confirmation else "active",
        needs_confirmation=req.needs_confirmation,
    )
    return {"memory": memory}


@router.post("/memories/{memory_id}/confirm")
async def approve_memory(
    memory_id: str,
    req: ConfirmMemoryRequest,
    current_user: dict = Depends(require_current_user),
) -> dict:
    memory = await confirm_memory(current_user["id"], memory_id, req.approved)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"memory": memory}


@router.patch("/memories/{memory_id}")
async def patch_memory(
    memory_id: str,
    req: UpdateMemoryRequest,
    current_user: dict = Depends(require_current_user),
) -> dict:
    patch = req.model_dump(exclude_unset=True)
    memory = await update_memory(current_user["id"], memory_id, patch)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"memory": memory}


@router.delete("/memories/{memory_id}")
async def remove_memory(
    memory_id: str,
    current_user: dict = Depends(require_current_user),
) -> dict:
    deleted = await delete_memory(current_user["id"], memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"id": memory_id}
