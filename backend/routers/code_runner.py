from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from agent.tools.builtin.run_code_tool import clear_code_results, get_code_results
from backend.auth_dependencies import require_current_user
from backend.session_access import assert_session_owned

router = APIRouter(prefix="/code", tags=["code"])


class CodeResultsResponse(BaseModel):
    session_id: str
    results: list[dict]


@router.get("/results/{session_id}", response_model=CodeResultsResponse)
async def get_results(
    session_id: str, current_user: dict = Depends(require_current_user)
) -> CodeResultsResponse:
    await assert_session_owned(session_id, current_user["id"])
    return CodeResultsResponse(
        session_id=session_id,
        results=get_code_results(session_id),
    )


@router.delete("/results/{session_id}")
async def clear_results(
    session_id: str, current_user: dict = Depends(require_current_user)
) -> dict:
    await assert_session_owned(session_id, current_user["id"])
    clear_code_results(session_id)
    return {"ok": True}
