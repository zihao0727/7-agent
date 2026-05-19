from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth_dependencies import require_current_user
from backend.state import get_app_state

router = APIRouter(tags=["skills"])


class SkillLoadRequest(BaseModel):
    skill_md_path: str
    name: str | None = None


class SkillPermissionUpdateRequest(BaseModel):
    risk_level: str | None = None
    requires_confirmation: bool | None = None


@router.get("/skills")
async def list_skills(current_user: dict = Depends(require_current_user)) -> dict:
    state = get_app_state(int(current_user["id"]))
    return {"skills": state.get_skills_info()}


@router.post("/skills/{name}/activate")
async def activate_skill(name: str, current_user: dict = Depends(require_current_user)) -> dict:
    state = get_app_state(int(current_user["id"]))
    ok = await state.activate_skill(name)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return {"name": name, "active": True}


@router.post("/skills/{name}/deactivate")
async def deactivate_skill(
    name: str, current_user: dict = Depends(require_current_user)
) -> dict:
    state = get_app_state(int(current_user["id"]))
    ok = await state.deactivate_skill(name)
    if not ok:
        raise HTTPException(
            status_code=404, detail=f"Skill '{name}' is not active or does not exist"
        )
    return {"name": name, "active": False}


@router.patch("/skills/{name}/permissions")
async def update_skill_permissions(
    name: str,
    body: SkillPermissionUpdateRequest,
    current_user: dict = Depends(require_current_user),
) -> dict:
    state = get_app_state(int(current_user["id"]))
    try:
        permissions = state.update_skill_permissions(
            name,
            risk_level=body.risk_level,
            requires_confirmation=body.requires_confirmation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not permissions:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return {"name": name, "permissions": permissions}


@router.post("/skills/load")
async def load_skill_from_md(
    body: SkillLoadRequest, current_user: dict = Depends(require_current_user)
) -> dict:
    state = get_app_state(int(current_user["id"]))
    try:
        skill = state.skill_registry.load_from_md(body.skill_md_path, body.name)
        await state.activate_skill(skill.name)
        return {
            "name": skill.name,
            "description": skill.description,
            "loaded": True,
            "active": True,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
