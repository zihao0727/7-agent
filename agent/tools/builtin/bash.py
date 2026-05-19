"""Cross-platform shell command execution tool."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys

from backend.permission_service import create_permission_request, summarize_delete_command
from backend.workspace import resolve_workspace_path, session_workspace_root

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

DEFAULT_TIMEOUT = 30
MAX_OUTPUT_CHARS = 8_000


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
        return [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command]
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

    for match in _ABSOLUTE_PATH_RE.finditer(normalized):
        candidate = match.group(0)
        prefix = normalized[max(0, match.start() - 8):match.start()]
        if "://" in prefix:
            continue
        resolved = os.path.abspath(os.path.expanduser(candidate))
        if os.path.normcase(resolved).startswith(os.path.normcase(cwd)):
            continue
        raise ToolExecutionError(
            "bash",
            f"Absolute path escape is not allowed outside the workspace: {candidate}",
        )


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
