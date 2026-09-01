from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

_SAFE_SEGMENT = re.compile(r"[^a-zA-Z0-9_.-]+")


def _additional_readable_roots() -> tuple[Path, ...]:
    """项目内、允许走"用户批准后读取"流程的目录白名单。

    这些目录里的文件 *不会* 被 read_file 直接读取（仍然返回 workspace 错误），
    而是触发 backend.permission_service 的批准弹窗；用户在前端点同意后，
    permission_service 会调用 file_ops.read_external_file_approved 重新校验并读取。
    """
    return (
        data_root() / "reports",
    )


def is_within_additional_readable_root(path: Path) -> Path | None:
    """若 path（已解析）位于额外可读根之下，返回命中的根；否则返回 None。"""
    try:
        resolved = path.resolve()
    except OSError:
        return None
    for root in _additional_readable_roots():
        try:
            root_resolved = root.resolve()
        except OSError:
            continue
        try:
            resolved.relative_to(root_resolved)
            return root_resolved
        except ValueError:
            continue
    return None


def resolve_external_readable_path(value: str) -> Path | None:
    """把字符串路径解析为外部可读路径；不在白名单则返回 None。

    只接受绝对路径——外部读取必须显式给绝对地址，相对路径一律走工作区流程。
    """
    if not value:
        return None
    raw = Path(os.path.expanduser(value))
    if not raw.is_absolute():
        return None
    try:
        resolved = raw.resolve()
    except OSError:
        return None
    if is_within_additional_readable_root(resolved) is None:
        return None
    return resolved


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
