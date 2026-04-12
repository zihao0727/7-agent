"""
浏览器自动化 API 路由

GET  /api/browser/state                              → 返回指定 session 的浏览器状态
GET  /api/browser/screenshot/{session_id}/{filename} → 提供截图文件下载
DELETE /api/browser/session/{session_id}             → 关闭并销毁指定 session 的浏览器 context
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["browser"])


def _screenshots_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "data" / "screenshots"


@router.get("/browser/state")
async def get_browser_state(session_id: str = Query(default="default")) -> dict:
    """返回指定 session 的浏览器状态，供前端面板实时轮询。"""
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
async def get_screenshot(session_id: str, filename: str) -> FileResponse:
    """
    提供截图文件静态访问。

    安全校验：session_id 和 filename 均不允许包含路径分隔符。
    """
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
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.delete("/browser/session/{session_id}")
async def delete_browser_session(session_id: str) -> dict:
    """关闭并销毁指定 session 的 BrowserContext，释放 Chromium 资源。"""
    try:
        from agent.tools.builtin.browser_tools import get_browser_manager
        mgr = get_browser_manager()
        await mgr.close_session(session_id)
        logger.info("手动关闭浏览器 session: %s", session_id)
        return {"session_id": session_id, "closed": True}
    except Exception as exc:
        logger.warning("关闭浏览器 session 失败: %s", exc)
        return {"session_id": session_id, "closed": False, "error": str(exc)}
