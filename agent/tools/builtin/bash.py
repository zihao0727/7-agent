"""
BashTool —— 在受控沙箱中执行 Shell 命令
对标 Claude Code 的 Bash tool，包含超时、输出截断和安全拦截
"""

from __future__ import annotations

import asyncio
import os
import shlex
import sys
from typing import Any

from ..base import BaseTool, ToolExecutionError, ToolSchema

# 危险命令黑名单（生产环境应更完善）
_BLOCKED_PATTERNS = [
    "rm -rf /",
    "mkfs",
    ":(){:|:&};:",   # fork 炸弹
    "dd if=/dev/zero",
]

DEFAULT_TIMEOUT = 30  # 秒
MAX_OUTPUT_CHARS = 8_000  # 输出截断阈值


class BashTool(BaseTool):
    """
    执行 Shell 命令并返回 stdout + stderr。
    超时默认 30 秒，输出超长自动截断。
    """

    name = "bash"
    description = (
        "在系统 Shell 中执行命令，返回 stdout 和 stderr。"
        "适合文件操作、代码运行、包管理等场景。"
        "禁止执行破坏性命令。"
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
                        "description": "要执行的 Shell 命令",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": f"超时秒数（默认 {DEFAULT_TIMEOUT}）",
                        "default": DEFAULT_TIMEOUT,
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "工作目录（默认为当前目录）",
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
    ) -> str:
        # 安全拦截
        for pattern in _BLOCKED_PATTERNS:
            if pattern in command:
                raise ToolExecutionError(self.name, f"命令包含被拒绝的模式: {pattern!r}")

        cwd = working_dir or os.getcwd()

        # Windows 兼容：使用 cmd /c，Linux/macOS 使用 sh -c
        if sys.platform == "win32":
            shell_cmd = ["cmd", "/c", command]
        else:
            shell_cmd = ["sh", "-c", command]

        try:
            proc = await asyncio.create_subprocess_exec(
                *shell_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise ToolExecutionError(self.name, f"命令执行超时（{timeout}s）: {command}")
        except Exception as exc:
            raise ToolExecutionError(self.name, str(exc), cause=exc) from exc

        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        exit_code = proc.returncode

        # 拼接输出
        parts: list[str] = []
        if out:
            parts.append(f"<stdout>\n{out}</stdout>")
        if err:
            parts.append(f"<stderr>\n{err}</stderr>")
        parts.append(f"<exit_code>{exit_code}</exit_code>")

        result = "\n".join(parts)

        # 截断超长输出
        if len(result) > MAX_OUTPUT_CHARS:
            half = MAX_OUTPUT_CHARS // 2
            result = (
                result[:half]
                + f"\n\n…[输出已截断，共 {len(result)} 字符]…\n\n"
                + result[-half:]
            )

        return result
