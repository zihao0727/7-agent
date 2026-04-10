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
from .web_search import WebSearchTool
from .time_tool import CurrentTimeTool

__all__ = [
    "BashTool",
    "ReadFileTool",
    "WriteFileTool",
    "StrReplaceTool",
    "ListDirTool",
    "GlobSearchTool",
    "WebSearchTool",
    "CurrentTimeTool",
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
        WebSearchTool(),  # Tavily 网络搜索
        CurrentTimeTool(),
    ]
