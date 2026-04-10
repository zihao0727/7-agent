"""
文件操作工具集 —— ReadFileTool / WriteFileTool / ListDirTool / GlobTool
对标 Claude Code 的 Read / Write / LS / Glob 工具
"""

from __future__ import annotations

import glob as _glob
import os
from pathlib import Path
from typing import Any

from ..base import BaseTool, ToolExecutionError, ToolSchema

MAX_FILE_CHARS = 20_000  # 文件读取截断阈值


class ReadFileTool(BaseTool):
    """读取文件内容，支持行范围截取"""

    name = "read_file"
    description = "读取本地文件内容，可指定起始行和结束行。"

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "start_line": {
                        "type": "integer",
                        "description": "起始行（1-indexed，可选）",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "结束行（含，可选）",
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
    ) -> str:
        p = Path(path)
        if not p.exists():
            raise ToolExecutionError(self.name, f"文件不存在: {path}")
        if not p.is_file():
            raise ToolExecutionError(self.name, f"不是普通文件: {path}")

        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            raise ToolExecutionError(self.name, str(exc), cause=exc) from exc

        lines = text.splitlines(keepends=True)
        total = len(lines)

        if start_line is not None or end_line is not None:
            s = (start_line or 1) - 1
            e = end_line or total
            lines = lines[s:e]
            text = "".join(lines)
            header = f"# {path}  (lines {s+1}-{min(e, total)} / {total})\n"
        else:
            header = f"# {path}  ({total} lines)\n"

        if len(text) > MAX_FILE_CHARS:
            text = text[:MAX_FILE_CHARS] + f"\n…[已截断，文件共 {len(text)} 字符]…"

        return header + text


class WriteFileTool(BaseTool):
    """写入文件内容（覆盖模式），自动创建父目录"""

    name = "write_file"
    description = "将内容写入文件，若文件不存在则创建，若存在则覆盖。"

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目标文件路径"},
                    "content": {"type": "string", "description": "写入内容"},
                },
                "required": ["path", "content"],
            },
        )

    async def execute(self, path: str, content: str) -> str:
        p = Path(path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        except Exception as exc:
            raise ToolExecutionError(self.name, str(exc), cause=exc) from exc
        return f"已成功写入 {p} ({len(content)} 字符)"


class StrReplaceTool(BaseTool):
    """精确字符串替换工具 —— 对标 Claude Code 的 str_replace_based_edit_tool"""

    name = "str_replace"
    description = (
        "在文件中精确查找并替换字符串。"
        "old_str 必须在文件中唯一存在，否则拒绝执行。"
    )

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "old_str": {"type": "string", "description": "要替换的原始字符串（必须唯一）"},
                    "new_str": {"type": "string", "description": "替换后的新字符串"},
                },
                "required": ["path", "old_str", "new_str"],
            },
        )

    async def execute(self, path: str, old_str: str, new_str: str) -> str:
        p = Path(path)
        if not p.exists():
            raise ToolExecutionError(self.name, f"文件不存在: {path}")

        original = p.read_text(encoding="utf-8", errors="replace")
        count = original.count(old_str)

        if count == 0:
            raise ToolExecutionError(self.name, f"在 {path} 中找不到目标字符串")
        if count > 1:
            raise ToolExecutionError(
                self.name,
                f"在 {path} 中找到 {count} 处匹配，old_str 必须唯一。请提供更多上下文。",
            )

        updated = original.replace(old_str, new_str, 1)
        p.write_text(updated, encoding="utf-8")
        return f"替换成功: {path}"


class ListDirTool(BaseTool):
    """列出目录内容"""

    name = "list_dir"
    description = "列出目录下的文件和子目录（非递归）。"

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目录路径（默认为当前目录）",
                        "default": ".",
                    },
                },
                "required": [],
            },
        )

    async def execute(self, path: str = ".") -> str:
        p = Path(path)
        if not p.exists():
            raise ToolExecutionError(self.name, f"目录不存在: {path}")
        if not p.is_dir():
            raise ToolExecutionError(self.name, f"不是目录: {path}")

        entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name))
        lines = []
        for entry in entries:
            if entry.is_dir():
                lines.append(f"  [DIR]  {entry.name}/")
            else:
                size = entry.stat().st_size
                lines.append(f"  [FILE] {entry.name}  ({size} bytes)")

        return f"{path}/\n" + "\n".join(lines) if lines else f"{path}/ (空目录)"


class GlobSearchTool(BaseTool):
    """使用 Glob 模式搜索文件"""

    name = "glob_search"
    description = "用 Glob 模式在指定目录内搜索文件路径。"

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob 模式，例如 **/*.py",
                    },
                    "base_dir": {
                        "type": "string",
                        "description": "搜索根目录（默认当前目录）",
                        "default": ".",
                    },
                },
                "required": ["pattern"],
            },
        )

    async def execute(self, pattern: str, base_dir: str = ".") -> str:
        base = Path(base_dir)
        matches = sorted(base.glob(pattern))
        if not matches:
            return f"未找到匹配 {pattern!r} 的文件"
        lines = [str(m.relative_to(base)) for m in matches[:200]]
        result = "\n".join(lines)
        if len(matches) > 200:
            result += f"\n…（共 {len(matches)} 个，只显示前 200 个）"
        return result
