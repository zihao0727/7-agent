from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from backend.auth_dependencies import require_current_user
from backend.session_access import assert_session_owned

logger = logging.getLogger(__name__)

router = APIRouter(tags=["browser"])


def _screenshots_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "data" / "screenshots"


@router.get("/browser/state")
async def get_browser_state(
    session_id: str = Query(...),
    current_user: dict = Depends(require_current_user),
) -> dict:
    await assert_session_owned(session_id, current_user["id"])
    try:
        from agent.tools.builtin.browser_tools import get_browser_manager

        mgr = get_browser_manager()
        session = mgr.get_session(session_id)
        if session is None:
            return {"url": "", "title": "", "screenshot_url": "", "active": False}
        return {
            "url": session.current_url,
            "title": session.page_title,
            "screenshot_url": session.last_screenshot_url,
            "active": bool(session.current_url),
        }
    except Exception as exc:
        logger.warning("获取浏览器状态失败: %s", exc)
        return {"url": "", "title": "", "screenshot_url": "", "active": False}


@router.get("/browser/screenshot/{session_id}/{filename}")
async def get_screenshot(
    session_id: str,
    filename: str,
    current_user: dict = Depends(require_current_user),
) -> FileResponse:
    await assert_session_owned(session_id, current_user["id"])
    for part in (session_id, filename):
        if ".." in part or "/" in part or "\\" in part:
            raise HTTPException(status_code=400, detail="非法路径")
    if not filename.endswith(".png"):
        raise HTTPException(status_code=400, detail="仅支持 PNG 格式")

    path = _screenshots_dir() / session_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="截图文件不存在")

    return FileResponse(
        path=str(path),
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.delete("/browser/session/{session_id}")
async def delete_browser_session(
    session_id: str, current_user: dict = Depends(require_current_user)
) -> dict:
    await assert_session_owned(session_id, current_user["id"])
    try:
        from agent.tools.builtin.browser_tools import get_browser_manager

        await get_browser_manager().close_session(session_id)
        return {"session_id": session_id, "closed": True}
    except Exception as exc:
        logger.warning("关闭浏览器 session 失败: %s", exc)
        return {"session_id": session_id, "closed": False, "error": str(exc)}
