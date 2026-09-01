"""
自动生成技能管理 API
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.auth_dependencies import require_current_user
from backend.skill_extractor import (
    list_auto_skills,
    get_auto_skill,
    confirm_auto_skill,
)

router = APIRouter(prefix="/api/auto-skills", tags=["auto-skills"])


class ConfirmSkillRequest(BaseModel):
    """确认技能请求"""
    approved: bool = Field(..., description="是否批准该技能")


@router.get("/list")
async def list_skills(
    include_archived: bool = Query(False, description="是否包含已归档的技能"),
    user_info: dict = Depends(require_current_user),
):
    """列出用户的自动生成技能"""
    user_id = user_info["id"]
    skills = await list_auto_skills(user_id, include_archived=include_archived)

    return {
        "skills": skills,
        "total": len(skills),
    }


@router.get("/{skill_id}")
async def get_skill_detail(
    skill_id: str,
    user_info: dict = Depends(require_current_user),
):
    """获取技能详情"""
    user_id = user_info["id"]
    skill = await get_auto_skill(skill_id, user_id)

    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")

    return skill


@router.post("/{skill_id}/confirm")
async def confirm_skill(
    skill_id: str,
    request: ConfirmSkillRequest,
    user_info: dict = Depends(require_current_user),
):
    """确认或拒绝自动生成的技能"""
    user_id = user_info["id"]
    skill = await confirm_auto_skill(skill_id, user_id, request.approved)

    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")

    return {
        "message": "技能已激活" if request.approved else "技能已拒绝",
        "skill": skill,
    }
