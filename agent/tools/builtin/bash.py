"""Cross-platform shell command execution tool."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

from backend.permission_service import create_permission_request, summarize_delete_command
from backend.workspace import (
    is_within_additional_readable_root,
    resolve_workspace_path,
    session_workspace_root,
)

from ..base import BaseTool, ToolExecutionError, ToolSchema

_BLOCKED_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    ":(){:|:&};:",
    "dd if=/dev/zero",
    "remove-item -recurse -force c:\\",
    "del /s /q c:\\",
]
_ABSOLUTE_PATH_RE = re.compile(
    r"(?<![\w.-])(?:[A-Za-z]:\\[^ \t;&|<>`'\"]*|/[^ \t;&|<>`'\"]*)"
)
_PARENT_TRAVERSAL_RE = re.compile(r"(?<![\w.-])\.\.(?:[\\/]|$)")

# 检测命令是否会向某个路径写入。保守命中：宁可让安全命令多过一道权限弹窗，
# 也不能让写入命令在白名单目录里无声执行。
_WRITE_REDIRECT_RE = re.compile(r"(?:^|[^&>])(?:>>|>)(?!&)")
_WRITE_CMD_RE = re.compile(
    r"(?ix)(?:^|[\s;&|`(])"
    r"(?:set-content|out-file|add-content|tee-object|new-item|"
    r"copy|copy-item|cp|move|move-item|mv|remove-item|"
    r"rm|del|erase|mkdir|md|rmdir|rd|touch)"
    r"\b"
)

DEFAULT_TIMEOUT = 30
MAX_OUTPUT_CHARS = 8_000
POWERSHELL_UTF8_PREAMBLE = (
    "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false; "
    "$OutputEncoding = [Console]::OutputEncoding; "
    "$PSDefaultParameterValues['Get-Content:Encoding'] = 'UTF8'; "
)


def _classify_absolute_paths(command: str, cwd: str) -> tuple[list[str], list[str], list[str]]:
    """扫描命令里的所有绝对路径，按归属分类。

    返回三段列表：(in_cwd, in_whitelist, outside)。
    - in_cwd: 在会话工作区下，本来就放行
    - in_whitelist: 在 ADDITIONAL_READABLE_ROOTS 下，需要看写入意图决定是放行还是要确认
    - outside: 不属于以上任何范围，直接拒绝
    """
    in_cwd: list[str] = []
    in_whitelist: list[str] = []
    outside: list[str] = []
    normalized = " ".join(command.split())
    cwd_nc = os.path.normcase(cwd)
    for match in _ABSOLUTE_PATH_RE.finditer(normalized):
        candidate = match.group(0)
        # URL scheme 分隔符 `://` 跨越 prefix 与 match 的边界——
        # `:` 在 match 之前一位，`//` 是 match 的开头。直接看前一位是不是 `:`。
        if match.start() > 0 and normalized[match.start() - 1] == ":":
            continue
        prefix = normalized[max(0, match.start() - 8):match.start()]
        if "://" in prefix:
            # 兜底：极少见的 `https : //example.com` 之类带空格的写法
            continue
        resolved = os.path.abspath(os.path.expanduser(candidate))
        if os.path.normcase(resolved).startswith(cwd_nc):
            in_cwd.append(resolved)
            continue
        if is_within_additional_readable_root(Path(resolved)) is not None:
            in_whitelist.append(resolved)
            continue
        outside.append(resolved)
    return in_cwd, in_whitelist, outside


def _is_write_command(command: str) -> bool:
    """命令是否会向文件系统写入。"""
    if _WRITE_REDIRECT_RE.search(command):
        return True
    if _WRITE_CMD_RE.search(command):
        return True
    return False


def _summarize_external_write_command(
    command: str, whitelist_paths: list[str]
) -> dict[str, str] | None:
    """若命令尝试向白名单目录写入，返回一条供权限请求展示的摘要。

    `whitelist_paths` 来自 _classify_absolute_paths，避免重复扫描。
    """
    if not whitelist_paths:
        return None
    if not _is_write_command(command):
        return None
    target = "\n".join(whitelist_paths[:3])
    if len(whitelist_paths) > 3:
        target += f"\n(+{len(whitelist_paths) - 3} more)"
    return {
        "action": "external_shell_write",
        "summary": "请求向工作区外受保护目录写入",
        "target": target,
    }


class BashTool(BaseTool):
    """Execute a command in the system shell and return stdout, stderr, and exit code."""

    name = "bash"
    description = (
        "Run a command in the system shell and return stdout/stderr. "
        "Windows defaults to PowerShell; Linux/macOS default to sh. "
        "Deletion commands require explicit user approval in the UI before execution."
    )

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": f"Timeout in seconds, default {DEFAULT_TIMEOUT}",
                        "default": DEFAULT_TIMEOUT,
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Working directory. Defaults to the current process directory.",
                    },
                    "shell": {
                        "type": "string",
                        "enum": ["auto", "powershell", "cmd", "bash", "sh"],
                        "description": "Shell to use. auto means PowerShell on Windows and sh on Linux/macOS.",
                        "default": "auto",
                    },
                },
                "required": ["command"],
            },
        )

    async def execute(
        self,
        command: str,
        timeout: int = DEFAULT_TIMEOUT,
        working_dir: str | None = None,
        shell: str = "auto",
        current_user_id: int | None = None,
        session_id: str = "",
    ) -> str:
        delete_summary = summarize_delete_command(command)
        if delete_summary:
            if current_user_id is None:
                raise ToolExecutionError(
                    self.name,
                    "Deletion commands require user approval, but no current_user_id was provided.",
                )
            request = create_permission_request(
                user_id=int(current_user_id),
                session_id=session_id,
                tool_name=self.name,
                action=delete_summary["action"],
                summary=delete_summary["summary"],
                target=delete_summary["target"],
                payload={
                    "command": command,
                    "timeout": timeout,
                    "working_dir": working_dir,
                    "shell": shell,
                    "current_user_id": current_user_id,
                    "session_id": session_id,
                },
            )
            return json.dumps(request, ensure_ascii=False)

        # 检测"向白名单目录写入"——读直接放行，写需要用户在 UI 批准
        if current_user_id is not None:
            try:
                if working_dir:
                    cwd_for_scan = str(resolve_workspace_path(
                        working_dir, user_id=int(current_user_id), session_id=session_id
                    ))
                else:
                    cwd_for_scan = str(session_workspace_root(int(current_user_id), session_id).resolve())
            except ValueError:
                cwd_for_scan = ""
            if cwd_for_scan:
                _, in_whitelist, _ = _classify_absolute_paths(command, cwd_for_scan)
                write_summary = _summarize_external_write_command(command, in_whitelist)
                if write_summary:
                    request = create_permission_request(
                        user_id=int(current_user_id),
                        session_id=session_id,
                        tool_name=self.name,
                        action=write_summary["action"],
                        summary=write_summary["summary"],
                        target=write_summary["target"],
                        payload={
                            "command": command,
                            "timeout": timeout,
                            "working_dir": working_dir,
                            "shell": shell,
                            "current_user_id": current_user_id,
                            "session_id": session_id,
                        },
                    )
                    return json.dumps(request, ensure_ascii=False)

        return await run_shell_command(
            command=command,
            timeout=timeout,
            working_dir=working_dir,
            shell=shell,
            current_user_id=current_user_id,
            session_id=session_id,
            require_delete_approval=False,
        )


async def run_shell_command(
    *,
    command: str,
    timeout: int = DEFAULT_TIMEOUT,
    working_dir: str | None = None,
    shell: str = "auto",
    current_user_id: int | None = None,
    session_id: str | None = None,
    require_delete_approval: bool = True,
) -> str:
    if require_delete_approval and summarize_delete_command(command):
        raise ToolExecutionError("bash", "Deletion commands require user approval.")

    normalized = command.lower()
    for pattern in _BLOCKED_PATTERNS:
        if pattern in normalized:
            raise ToolExecutionError("bash", f"Command contains a blocked pattern: {pattern!r}")

    if current_user_id is None:
        raise ToolExecutionError("bash", "Missing current_user_id for workspace-isolated shell access.")
    try:
        if working_dir:
            cwd = str(resolve_workspace_path(working_dir, user_id=int(current_user_id), session_id=session_id))
        else:
            cwd = str(session_workspace_root(int(current_user_id), session_id).resolve())
    except ValueError as exc:
        raise ToolExecutionError("bash", str(exc), cause=exc) from exc

    if not os.path.isdir(cwd):
        raise ToolExecutionError("bash", f"Working directory does not exist or is not a directory: {cwd}")
    _validate_command_scope(command, cwd)

    shell_cmd = _build_shell_command(command, shell)
    env = os.environ.copy()
    env["AGENT_USER_WORKSPACE"] = cwd
    env["AGENT_CURRENT_USER_ID"] = str(int(current_user_id))
    env["AGENT_SESSION_ID"] = session_id or ""

    try:
        proc = await asyncio.create_subprocess_exec(
            *shell_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        try:
            proc.kill()
        except Exception:
            pass
        raise ToolExecutionError("bash", f"Command timed out after {timeout}s: {command}") from exc
    except Exception as exc:
        raise ToolExecutionError("bash", str(exc), cause=exc) from exc

    out = _decode_output(stdout)
    err = _decode_output(stderr)
    exit_code = proc.returncode

    parts: list[str] = []
    if out:
        parts.append(f"<stdout>\n{out}</stdout>")
    if err:
        parts.append(f"<stderr>\n{err}</stderr>")
    parts.append(f"<exit_code>{exit_code}</exit_code>")

    result = "\n".join(parts)
    if len(result) > MAX_OUTPUT_CHARS:
        half = MAX_OUTPUT_CHARS // 2
        result = (
            result[:half]
            + f"\n\n...[output truncated, total {len(result)} chars]...\n\n"
            + result[-half:]
        )
    return result


def _build_shell_command(command: str, shell: str) -> list[str]:
    selected = (shell or "auto").lower()
    if selected == "auto":
        selected = "powershell" if sys.platform == "win32" else "sh"

    if selected == "powershell":
        executable = "powershell" if sys.platform == "win32" else "pwsh"
        return [
            executable,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"{POWERSHELL_UTF8_PREAMBLE}{command}",
        ]
    if selected == "cmd":
        return ["cmd", "/c", command]
    if selected == "bash":
        return ["bash", "-lc", command]
    if selected == "sh":
        return ["sh", "-c", command]
    raise ToolExecutionError("bash", f"Unsupported shell: {shell}")


def _validate_command_scope(command: str, cwd: str) -> None:
    normalized = " ".join(command.split())
    if _PARENT_TRAVERSAL_RE.search(normalized):
        raise ToolExecutionError("bash", "Parent-directory traversal is not allowed in workspace commands.")

    _in_cwd, _in_whitelist, outside = _classify_absolute_paths(command, cwd)
    if outside:
        raise ToolExecutionError(
            "bash",
            f"Absolute path escape is not allowed outside the workspace: {outside[0]}",
        )
    # 落在白名单内的绝对路径放行：读取直接执行，写入由调用方在 execute 里通过
    # _summarize_external_write_command 触发权限确认。


def _decode_output(data: bytes) -> str:
    if not data:
        return ""
    for encoding in ("utf-8", "gb18030", "gbk", "cp936"):
        try:
            text = data.decode(encoding)
            if "\ufffd" not in text:
                return text
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")
