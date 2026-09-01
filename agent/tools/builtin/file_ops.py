"""Cross-platform file operation tools."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.permission_service import create_permission_request
from backend.workspace import resolve_external_readable_path, resolve_workspace_path

from ..base import BaseTool, ToolExecutionError, ToolSchema

MAX_FILE_CHARS = 20_000
MAX_DIRECT_READ_BYTES = 1_000_000
_BINARY_SAMPLE_BYTES = 8192


def _path(value: str) -> Path:
    return Path(os.path.expanduser(value))


def _workspace_path(tool_name: str, value: str, current_user_id: int | None, session_id: str | None) -> Path:
    if current_user_id is None:
        raise ToolExecutionError(tool_name, "Missing current_user_id for workspace-isolated file access.")
    try:
        return resolve_workspace_path(value, user_id=int(current_user_id), session_id=session_id)
    except ValueError as exc:
        raise ToolExecutionError(tool_name, str(exc), cause=exc) from exc


def _looks_binary(data: bytes) -> bool:
    if not data:
        return False
    if b"\x00" in data:
        return True
    text_controls = {7, 8, 9, 10, 12, 13, 27}
    suspicious = sum(1 for b in data if b < 32 and b not in text_controls)
    return suspicious / max(1, len(data)) > 0.05


def _ensure_text_file(tool_name: str, path: Path) -> None:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ToolExecutionError(tool_name, str(exc), cause=exc) from exc

    if size > MAX_DIRECT_READ_BYTES:
        raise ToolExecutionError(
            tool_name,
            (
                f"File is too large for direct text reading ({size} bytes). "
                "Please use a specialized tool or code-based streaming/analysis instead."
            ),
        )

    try:
        sample = path.read_bytes()[:_BINARY_SAMPLE_BYTES]
    except OSError as exc:
        raise ToolExecutionError(tool_name, str(exc), cause=exc) from exc

    if _looks_binary(sample):
        raise ToolExecutionError(
            tool_name,
            "This appears to be a binary file and cannot be read as plain text. "
            "Please use a specialized file tool instead.",
        )


class ReadFileTool(BaseTool):
    """Read a text file, optionally by line range."""

    name = "read_file"
    description = (
        "Read a local text file, optionally by 1-indexed line range. "
        "For binary files or large files, returns a clear error asking to use a specialized tool."
    )

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "start_line": {
                        "type": "integer",
                        "description": "Start line, 1-indexed",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "End line, inclusive",
                    },
                },
                "required": ["path"],
            },
        )

    async def execute(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        current_user_id: int | None = None,
        session_id: str | None = None,
    ) -> str:
        # 1) 先尝试解析为会话工作区内的路径——大多数读取走这条
        p: Path | None = None
        if current_user_id is not None:
            try:
                p = resolve_workspace_path(
                    path,
                    user_id=int(current_user_id),
                    session_id=session_id,
                )
            except ValueError:
                p = None  # 工作区外：交给后面的白名单 / 兜底处理

        if p is not None:
            if not p.exists():
                raise ToolExecutionError(self.name, f"File does not exist: {path}")
            if not p.is_file():
                raise ToolExecutionError(self.name, f"Not a regular file: {path}")
            _ensure_text_file(self.name, p)
            return _read_text_with_slice(self.name, p, start_line, end_line)

        # 2) 工作区外：检查白名单——命中则发起权限请求
        external = resolve_external_readable_path(path)
        if external is not None:
            if current_user_id is None:
                # 没有用户上下文就无法发权限请求；按统一错误提示返回
                raise ToolExecutionError(
                    self.name,
                    "Missing current_user_id for workspace-isolated file access.",
                )
            if not external.exists() or not external.is_file():
                raise ToolExecutionError(self.name, f"File does not exist or is not a regular file: {path}")
            request = create_permission_request(
                user_id=int(current_user_id),
                session_id=session_id or "",
                tool_name=self.name,
                action="read_external_file",
                summary=f"读取工作区外受限目录文件：{external.name}",
                target=str(external),
                payload={
                    "kind": "read_external",
                    "path": str(external),
                    "start_line": start_line,
                    "end_line": end_line,
                },
            )
            return json.dumps(request, ensure_ascii=False)

        # 3) 既不在工作区也不在白名单：复用 _workspace_path 抛出统一错误
        _workspace_path(self.name, path, current_user_id, session_id)
        # _workspace_path 在 current_user_id 缺失或路径越界时一定会抛错；保险起见兜底
        raise ToolExecutionError(self.name, f"Path is outside this user's session workspace: {path}")


def _read_text_with_slice(
    tool_name: str,
    p: Path,
    start_line: int | None,
    end_line: int | None,
) -> str:
    """读取文本文件并按 1-indexed 行区间切片，返回带 header 的字符串。

    供 ReadFileTool 与 read_external_file_approved 共用，避免行为漂移。
    调用前需自行确保 p 已通过 _ensure_text_file 校验。
    """
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise ToolExecutionError(tool_name, str(exc), cause=exc) from exc

    lines = text.splitlines(keepends=True)
    total = len(lines)

    if start_line is not None or end_line is not None:
        start = max(0, (start_line or 1) - 1)
        end = min(end_line or total, total)
        if end < start:
            raise ToolExecutionError(tool_name, "end_line must be greater than or equal to start_line")
        text = "".join(lines[start:end])
        header = f"# {p}  (lines {start + 1}-{end} / {total})\n"
    else:
        header = f"# {p}  ({total} lines)\n"

    original_len = len(text)
    if original_len > MAX_FILE_CHARS:
        text = (
            text[:MAX_FILE_CHARS]
            + f"\n...[truncated, selected content has {original_len} chars]..."
        )

    return header + text


async def read_external_file_approved(
    *,
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> str:
    """已经过用户在 UI 批准的工作区外文件读取入口。

    仅由 backend.permission_service.execute_permission_payload 在收到
    payload.kind == "read_external" 时调用：传入的 path 来自批准前持久化的
    payload，但本函数仍会用 resolve_external_readable_path 再做一次白名单校验，
    防止 payload 被篡改或白名单收紧后旧请求漏读。

    本函数 *不会* 在 ToolRegistry 中注册——LLM 没有任何途径直接调用它。
    """
    resolved = resolve_external_readable_path(path)
    if resolved is None:
        raise ToolExecutionError(
            "read_file",
            f"Path is not in any approved readable root: {path}",
        )
    if not resolved.exists() or not resolved.is_file():
        raise ToolExecutionError(
            "read_file",
            f"File does not exist or is not a regular file: {path}",
        )
    _ensure_text_file("read_file", resolved)
    return _read_text_with_slice("read_file", resolved, start_line, end_line)


class WriteFileTool(BaseTool):
    """Write a text file in overwrite mode, creating parent directories."""

    name = "write_file"
    description = "Write text content to a file. Creates parent directories. Overwrites existing files."

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Target file path"},
                    "content": {"type": "string", "description": "Text content to write"},
                },
                "required": ["path", "content"],
            },
        )

    async def execute(
        self,
        path: str,
        content: str,
        current_user_id: int | None = None,
        session_id: str | None = None,
    ) -> str:
        p = _workspace_path(self.name, path, current_user_id, session_id)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        except Exception as exc:
            raise ToolExecutionError(self.name, str(exc), cause=exc) from exc
        return f"Successfully wrote {p} ({len(content)} chars)"


class StrReplaceTool(BaseTool):
    """Precise single string replacement tool."""

    name = "str_replace"
    description = "Replace one unique string in a text file. old_str must be non-empty and appear exactly once."

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "old_str": {
                        "type": "string",
                        "description": "Original string. Must be unique and non-empty.",
                    },
                    "new_str": {"type": "string", "description": "Replacement string"},
                },
                "required": ["path", "old_str", "new_str"],
            },
        )

    async def execute(
        self,
        path: str,
        old_str: str,
        new_str: str,
        current_user_id: int | None = None,
        session_id: str | None = None,
    ) -> str:
        if old_str == "":
            raise ToolExecutionError(self.name, "old_str cannot be empty")

        p = _workspace_path(self.name, path, current_user_id, session_id)
        if not p.exists():
            raise ToolExecutionError(self.name, f"File does not exist: {path}")
        if not p.is_file():
            raise ToolExecutionError(self.name, f"Not a regular file: {path}")
        _ensure_text_file(self.name, p)

        original = p.read_text(encoding="utf-8", errors="replace")
        count = original.count(old_str)

        if count == 0:
            raise ToolExecutionError(self.name, f"Target string was not found in {path}")
        if count > 1:
            raise ToolExecutionError(
                self.name,
                f"Found {count} matches in {path}; old_str must be unique. Provide more context.",
            )

        updated = original.replace(old_str, new_str, 1)
        p.write_text(updated, encoding="utf-8")
        return f"Replacement succeeded: {path}"


class EditFileTool(BaseTool):
    """Apply multiple ordered string patches to a text file."""

    name = "edit_file"
    description = (
        "Apply multiple ordered text patches to a file. Each patch has old_str and new_str. "
        "Every old_str must be non-empty and unique in the current file content at the moment it is applied. "
        "Use this for multi-location edits instead of many separate str_replace calls."
    )

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                    "patches": {
                        "type": "array",
                        "description": "Ordered list of string replacement patches.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "old_str": {
                                    "type": "string",
                                    "description": "Existing text to replace. Must be unique.",
                                },
                                "new_str": {
                                    "type": "string",
                                    "description": "Replacement text.",
                                },
                            },
                            "required": ["old_str", "new_str"],
                        },
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, validate patches without writing the file.",
                        "default": False,
                    },
                },
                "required": ["path", "patches"],
            },
        )

    async def execute(
        self,
        path: str,
        patches: list[dict[str, Any]],
        dry_run: bool = False,
        current_user_id: int | None = None,
        session_id: str | None = None,
    ) -> str:
        p = _workspace_path(self.name, path, current_user_id, session_id)
        if not p.exists():
            raise ToolExecutionError(self.name, f"File does not exist: {path}")
        if not p.is_file():
            raise ToolExecutionError(self.name, f"Not a regular file: {path}")
        _ensure_text_file(self.name, p)

        if not patches:
            raise ToolExecutionError(self.name, "patches cannot be empty")

        original = p.read_text(encoding="utf-8", errors="replace")
        updated = original
        applied: list[str] = []

        for index, patch in enumerate(patches, start=1):
            old_str = str(patch.get("old_str", ""))
            new_str = str(patch.get("new_str", ""))
            if old_str == "":
                raise ToolExecutionError(self.name, f"Patch {index}: old_str cannot be empty")

            count = updated.count(old_str)
            if count == 0:
                raise ToolExecutionError(self.name, f"Patch {index}: target string was not found")
            if count > 1:
                raise ToolExecutionError(
                    self.name,
                    f"Patch {index}: found {count} matches; old_str must be unique",
                )

            updated = updated.replace(old_str, new_str, 1)
            applied.append(f"patch {index}: {len(old_str)} -> {len(new_str)} chars")

        if updated == original:
            return f"No changes needed for {path}"

        if not dry_run:
            p.write_text(updated, encoding="utf-8")

        action = "validated" if dry_run else "applied"
        delta = len(updated) - len(original)
        return f"Successfully {action} {len(patches)} patch(es) for {path}; char delta {delta}.\n" + "\n".join(applied)


class ListDirTool(BaseTool):
    """List a directory non-recursively."""

    name = "list_dir"
    description = "List files and child directories in a directory, non-recursively."

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path. Defaults to current directory.",
                        "default": ".",
                    },
                },
                "required": [],
            },
        )

    async def execute(
        self,
        path: str = ".",
        current_user_id: int | None = None,
        session_id: str | None = None,
    ) -> str:
        p = _workspace_path(self.name, path, current_user_id, session_id)
        if not p.exists():
            raise ToolExecutionError(self.name, f"Directory does not exist: {path}")
        if not p.is_dir():
            raise ToolExecutionError(self.name, f"Not a directory: {path}")

        entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        lines = []
        for entry in entries:
            if entry.is_dir():
                lines.append(f"  [DIR]  {entry.name}/")
            else:
                size = entry.stat().st_size
                lines.append(f"  [FILE] {entry.name}  ({size} bytes)")

        return f"{p}/\n" + "\n".join(lines) if lines else f"{p}/ (empty)"


class GlobSearchTool(BaseTool):
    """Search file paths with pathlib glob patterns."""

    name = "glob_search"
    description = "Search file paths under a base directory with glob patterns such as **/*.py."

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern, e.g. **/*.py",
                    },
                    "base_dir": {
                        "type": "string",
                        "description": "Search root directory. Defaults to current directory.",
                        "default": ".",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results. Defaults to 200, capped at 1000.",
                        "default": 200,
                    },
                },
                "required": ["pattern"],
            },
        )

    async def execute(
        self,
        pattern: str,
        base_dir: str = ".",
        max_results: int = 200,
        current_user_id: int | None = None,
        session_id: str | None = None,
    ) -> str:
        base = _workspace_path(self.name, base_dir, current_user_id, session_id)
        if not base.exists():
            raise ToolExecutionError(self.name, f"Search directory does not exist: {base_dir}")
        if not base.is_dir():
            raise ToolExecutionError(self.name, f"Not a directory: {base_dir}")

        matches = sorted(base.glob(pattern))
        if not matches:
            return f"No files matched {pattern!r}"

        limit = max(1, min(int(max_results or 200), 1000))
        lines = [str(m.relative_to(base)) for m in matches[:limit]]
        result = "\n".join(lines)
        if len(matches) > limit:
            result += f"\n...({len(matches)} total, showing first {limit})"
        return result
