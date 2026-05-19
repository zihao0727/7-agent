from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from backend.auth_dependencies import require_current_user
from backend.session_access import assert_session_owned

logger = logging.getLogger(__name__)

router = APIRouter(tags=["browser"])


def _safe_session_segment(session_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", session_id).strip("_") or "default"


def _browser_namespace(user_id: int, session_id: str) -> str:
    return f"user_{int(user_id)}/{_safe_session_segment(session_id)}"


def _empty_browser_state(user_id: int, session_id: str) -> dict:
    return {
        "session_id": session_id,
        "user_id": user_id,
        "namespace": _browser_namespace(user_id, session_id),
        "url": "",
        "title": "",
        "screenshot_url": "",
        "active": False,
    }


def _screenshots_dir(user_id: int, session_id: str) -> Path:
    return (
        Path(__file__).resolve().parent.parent.parent
        / "data"
        / "screenshots"
        / f"user_{int(user_id)}"
        / _safe_session_segment(session_id)
    )


def _resolve_screenshot_path(user_id: int, session_id: str, filename: str) -> Path:
    scoped = _screenshots_dir(user_id, session_id) / filename
    if scoped.exists():
        return scoped
    legacy = (
        Path(__file__).resolve().parent.parent.parent
        / "data"
        / "screenshots"
        / _safe_session_segment(session_id)
        / filename
    )
    return legacy


@router.get("/browser/state")
async def get_browser_state(
    session_id: str = Query(...),
    current_user: dict = Depends(require_current_user),
) -> dict:
    user_id = int(current_user["id"])
    await assert_session_owned(session_id, user_id)
    try:
        from agent.tools.builtin.browser_tools import get_browser_manager

        mgr = get_browser_manager()
        session = mgr.get_session(session_id, user_id=user_id)
        if session is None:
            return _empty_browser_state(user_id, session_id)
        return {
            "session_id": session_id,
            "user_id": user_id,
            "namespace": _browser_namespace(user_id, session_id),
            "url": session.current_url,
            "title": session.page_title,
            "screenshot_url": session.last_screenshot_url,
            "active": bool(session.current_url),
        }
    except Exception as exc:
        logger.warning("Failed to fetch browser state: %s", exc)
        return _empty_browser_state(user_id, session_id)


@router.get("/browser/screenshot/{session_id}/{filename}")
async def get_screenshot(
    session_id: str,
    filename: str,
    current_user: dict = Depends(require_current_user),
) -> FileResponse:
    user_id = int(current_user["id"])
    await assert_session_owned(session_id, user_id)
    for part in (session_id, filename):
        if ".." in part or "/" in part or "\\" in part:
            raise HTTPException(status_code=400, detail="Invalid path")
    if not filename.endswith(".png"):
        raise HTTPException(status_code=400, detail="Only PNG screenshots are supported")

    path = _resolve_screenshot_path(user_id, session_id, filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Screenshot not found")

    return FileResponse(
        path=str(path),
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.delete("/browser/session/{session_id}")
async def delete_browser_session(
    session_id: str, current_user: dict = Depends(require_current_user)
) -> dict:
    user_id = int(current_user["id"])
    await assert_session_owned(session_id, user_id)
    try:
        from agent.tools.builtin.browser_tools import get_browser_manager

        await get_browser_manager().close_session(session_id, user_id=user_id)
        return {
            "session_id": session_id,
            "user_id": user_id,
            "namespace": _browser_namespace(user_id, session_id),
            "closed": True,
        }
    except Exception as exc:
        logger.warning("Failed to close browser session: %s", exc)
        return {
            "session_id": session_id,
            "user_id": user_id,
            "namespace": _browser_namespace(user_id, session_id),
            "closed": False,
            "error": str(exc),
        }
