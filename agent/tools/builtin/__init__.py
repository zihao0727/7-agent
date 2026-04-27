"""
内置工具集 —— 开箱即用的原子能力
"""

from .bash import BashTool
from .file_ops import (
    GlobSearchTool,
    ListDirTool,
    ReadFileTool,
    StrReplaceTool,
    WriteFileTool,
)
from .run_code_tool import RunCodeTool  # 由 code_runner Skill 注册，非默认内置
from .web_search import WebSearchTool
from .time_tool import CurrentTimeTool
from .lark_cli_tool import LarkCliTool

__all__ = [
    "BashTool",
    "ReadFileTool",
    "WriteFileTool",
    "StrReplaceTool",
    "ListDirTool",
    "GlobSearchTool",
    "RunCodeTool",
    "WebSearchTool",
    "CurrentTimeTool",
    "LarkCliTool",
]


def get_default_tools() -> list:
    """返回默认内置工具实例列表"""
    return [
        BashTool(),
        ReadFileTool(),
        WriteFileTool(),
        StrReplaceTool(),
        ListDirTool(),
        GlobSearchTool(),
        WebSearchTool(),
        CurrentTimeTool(),
    ]
