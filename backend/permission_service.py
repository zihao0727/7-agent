from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal


PermissionStatus = Literal["pending", "approved", "denied", "expired", "executed", "failed"]

_requests: dict[str, dict[str, Any]] = {}
_requests_loaded = False
_requests_lock = threading.RLock()
REQUEST_TTL = timedelta(hours=24)


def _store_path() -> Path:
    root = Path(__file__).resolve().parent.parent / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root / "permission_requests.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _expire_old_pending_locked() -> None:
    now = datetime.now(timezone.utc)
    changed = False
    for item in _requests.values():
        if item.get("status") != "pending":
            continue
        created_at = _parse_iso(str(item.get("created_at") or ""))
        if created_at and now - created_at > REQUEST_TTL:
            item["status"] = "expired"
            item["updated_at"] = utc_now_iso()
            changed = True
    if changed:
        _save_requests_locked()


def _load_requests_once() -> None:
    global _requests_loaded
    with _requests_lock:
        if _requests_loaded:
            return
        path = _store_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    _requests.clear()
                    for key, value in data.items():
                        if isinstance(value, dict):
                            _requests[str(key)] = value
            except Exception:
                _requests.clear()
        _requests_loaded = True
        _expire_old_pending_locked()


def _save_requests_locked() -> None:
    path = _store_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(_requests, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def summarize_delete_command(command: str) -> dict[str, Any] | None:
    normalized = " ".join(command.strip().split())
    lower = normalized.lower()
    patterns = [
        r"\brm\s+[^;&|]*(-r|-rf|-fr|--recursive|--force)[^;&|]*",
        r"\brm\s+[^;&|]+",
        r"\bdel\s+[^;&|]+",
        r"\berase\s+[^;&|]+",
        r"\brmdir\s+[^;&|]+",
        r"\bremove-item\b[^;&|]+",
        r"\bremove\b[^;&|]+-item\b[^;&|]*",
        r"\bunlink\s+[^;&|]+",
    ]
    if not any(re.search(pattern, lower) for pattern in patterns):
        return None

    target = normalized
    for token in (
        "Remove-Item",
        "remove-item",
        "rm",
        "del",
        "erase",
        "rmdir",
        "unlink",
    ):
        idx = lower.find(token.lower())
        if idx >= 0:
            target = normalized[idx + len(token) :].strip()
            break

    if len(target) > 220:
        target = target[:217] + "..."
    return {
        "action": "delete_files",
        "summary": "请求删除文件或目录",
        "target": target or normalized,
    }


def create_permission_request(
    *,
    user_id: int,
    session_id: str,
    tool_name: str,
    action: str,
    summary: str,
    target: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    _load_requests_once()
    request_id = uuid.uuid4().hex
    item = {
        "id": request_id,
        "user_id": int(user_id),
        "session_id": session_id,
        "tool_name": tool_name,
        "action": action,
        "summary": summary,
        "target": target,
        "payload": payload,
        "status": "pending",
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }
    with _requests_lock:
        _requests[request_id] = item
        _save_requests_locked()
    return public_permission_request(item)


def public_permission_request(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "permission_required",
        "id": item["id"],
        "tool_name": item["tool_name"],
        "action": item["action"],
        "summary": item["summary"],
        "target": item["target"],
        "status": item["status"],
        "created_at": item["created_at"],
    }


def get_permission_request(request_id: str, user_id: int) -> dict[str, Any] | None:
    _load_requests_once()
    with _requests_lock:
        _expire_old_pending_locked()
        item = _requests.get(request_id)
        if not item or int(item.get("user_id") or 0) != int(user_id):
            return None
        return item


async def resolve_permission_request(
    *,
    request_id: str,
    user_id: int,
    approved: bool,
) -> dict[str, Any] | None:
    item = get_permission_request(request_id, user_id)
    if not item:
        return None
    if item["status"] != "pending":
        return public_permission_request(item)

    item["status"] = "approved" if approved else "denied"
    item["updated_at"] = utc_now_iso()
    with _requests_lock:
        _save_requests_locked()
    if not approved:
        return {
            **public_permission_request(item),
            "result": "用户已拒绝执行该删除操作。",
        }

    try:
        result = await execute_permission_payload(item)
        item["status"] = "executed"
        item["updated_at"] = utc_now_iso()
        with _requests_lock:
            _save_requests_locked()
        return {
            **public_permission_request(item),
            "result": result,
        }
    except Exception as exc:
        item["status"] = "failed"
        item["updated_at"] = utc_now_iso()
        with _requests_lock:
            _save_requests_locked()
        return {
            **public_permission_request(item),
            "error": str(exc),
        }


async def execute_permission_payload(item: dict[str, Any]) -> str:
    payload = item.get("payload") or {}
    if payload.get("kind") == "tool_call":
        from backend.state import get_app_state

        user_id = int(item.get("user_id") or 0)
        tool_name = str(payload.get("tool_name") or item.get("tool_name") or "")
        args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
        result = await get_app_state(user_id).tool_registry.execute(tool_name, args)
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)

    if item.get("tool_name") == "bash":
        from agent.tools.builtin.bash import run_shell_command

        return await run_shell_command(
            command=str(payload.get("command") or ""),
            timeout=int(payload.get("timeout") or 30),
            working_dir=payload.get("working_dir"),
            shell=str(payload.get("shell") or "auto"),
            current_user_id=int(item.get("user_id") or 0),
            session_id=str(payload.get("session_id") or item.get("session_id") or ""),
            require_delete_approval=False,
        )
    raise RuntimeError(f"Unsupported permission tool: {item.get('tool_name')}")
