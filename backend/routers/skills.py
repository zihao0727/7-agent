"""
/api/skills —— Skill 列表查询、激活与停用
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.state import get_app_state

router = APIRouter(tags=["skills"])


class SkillLoadRequest(BaseModel):
    """从 SKILL.md 路径动态加载新 Skill"""
    skill_md_path: str
    name: str | None = None


@router.get("/skills")
async def list_skills() -> dict:
    """返回所有注册 Skill 及其激活状态"""
    state = get_app_state()
    return {"skills": state.get_skills_info()}


@router.post("/skills/{name}/activate")
async def activate_skill(name: str) -> dict:
    """激活指定 Skill，将其工具注册到 ToolRegistry"""
    state = get_app_state()
    ok = await state.activate_skill(name)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' 未注册")
    return {"name": name, "active": True}


@router.post("/skills/{name}/deactivate")
async def deactivate_skill(name: str) -> dict:
    """停用指定 Skill，注销其工具"""
    state = get_app_state()
    ok = await state.deactivate_skill(name)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' 未激活或不存在")
    return {"name": name, "active": False}


@router.post("/skills/load")
async def load_skill_from_md(body: SkillLoadRequest) -> dict:
    """从 SKILL.md 文件路径动态加载并注册新 Skill"""
    state = get_app_state()
    try:
        skill = state.skill_registry.load_from_md(body.skill_md_path, body.name)
        return {"name": skill.name, "description": skill.description, "loaded": True}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
