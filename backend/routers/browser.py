"""
浏览器自动化 API 路由

GET /api/browser/state                  → 返回当前浏览器状态（URL、标题、最新截图）
GET /api/browser/screenshot/{filename}  → 提供截图文件下载
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["browser"])


def _screenshots_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "data" / "screenshots"


@router.get("/browser/state")
async def get_browser_state() -> dict:
    """返回当前浏览器实例的状态，供前端面板实时轮询。"""
    try:
        from agent.tools.builtin.browser_tools import get_browser_state
        bs = get_browser_state()
        return {
            "url": bs.current_url,
            "title": bs.page_title,
            "screenshot_url": bs.last_screenshot_url,
            "active": bool(bs.current_url),
        }
    except Exception as exc:
        logger.warning("获取浏览器状态失败: %s", exc)
        return {"url": "", "title": "", "screenshot_url": "", "active": False}


@router.get("/browser/screenshot/{filename}")
async def get_screenshot(filename: str) -> FileResponse:
    """
    提供截图文件静态访问。

    安全校验：只允许纯文件名（不含路径分隔符），且必须以 .png 结尾。
    """
    # 安全校验
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    if not filename.endswith(".png"):
        raise HTTPException(status_code=400, detail="仅支持 PNG 格式")

    path = _screenshots_dir() / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="截图文件不存在")

    return FileResponse(
        path=str(path),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )
