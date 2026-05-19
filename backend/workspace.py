from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

_SAFE_SEGMENT = re.compile(r"[^a-zA-Z0-9_.-]+")


def safe_segment(value: str | int | None, fallback: str = "default") -> str:
    text = str(value if value is not None else fallback)
    safe = _SAFE_SEGMENT.sub("_", text).strip("._-")
    return safe or fallback


def data_root() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def user_workspace_root(user_id: int) -> Path:
    root = data_root() / "user_workspaces" / f"user_{int(user_id)}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def session_workspace_root(user_id: int, session_id: str | None) -> Path:
    root = user_workspace_root(user_id) / "sessions" / safe_segment(session_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def session_subdir(user_id: int, session_id: str | None, name: str) -> Path:
    root = session_workspace_root(user_id, session_id) / safe_segment(name, "files")
    root.mkdir(parents=True, exist_ok=True)
    return root


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def resolve_workspace_path(
    value: str,
    *,
    user_id: int,
    session_id: str | None,
    base_dir: str | Path | None = None,
) -> Path:
    workspace = session_workspace_root(user_id, session_id)
    raw = Path(os.path.expanduser(value or "."))
    base = Path(base_dir) if base_dir is not None else workspace
    if not base.is_absolute():
        base = workspace / base
    base = base.resolve()
    if not is_relative_to(base, workspace):
        raise ValueError(f"Path is outside this user's session workspace: {base}")

    path = raw if raw.is_absolute() else base / raw
    path = path.resolve()
    if not is_relative_to(path, workspace):
        raise ValueError(f"Path is outside this user's session workspace: {path}")
    return path


def cleanup_session_workspace(user_id: int, session_id: str | None) -> None:
    root = session_workspace_root(user_id, session_id)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


def cleanup_user_workspace(user_id: int) -> None:
    root = user_workspace_root(user_id)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
