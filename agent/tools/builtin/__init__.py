"""
内置工具集 —— 开箱即用的原子能力
"""

from .bash import BashTool
from .file_ops import (
    EditFileTool,
    GlobSearchTool,
    ListDirTool,
    ReadFileTool,
    StrReplaceTool,
    WriteFileTool,
)
from .run_code_tool import RunCodeTool  # 由 code_runner Skill 注册，非默认内置
from .web_search import WebSearchTool
from .time_tool import CurrentTimeTool
from .lark import (
    LarkApiTool,
    LarkAuthTool,
    LarkCalendarCreateTool,
    LarkCalendarQueryTool,
    LarkCommandTool,
    LarkCreateDocTool,
    LarkMyTasksTool,
    LarkRelatedTasksTool,
    LarkSendMessageTool,
)
from .scheduled_task_tool import CreateScheduledTaskTool
from .knowledge_base import KnowledgeListDocumentsTool, KnowledgeSearchTool

__all__ = [
    "BashTool",
    "ReadFileTool",
    "WriteFileTool",
    "StrReplaceTool",
    "EditFileTool",
    "ListDirTool",
    "GlobSearchTool",
    "RunCodeTool",
    "WebSearchTool",
    "CurrentTimeTool",
    "LarkApiTool",
    "LarkAuthTool",
    "LarkCalendarCreateTool",
    "LarkCalendarQueryTool",
    "LarkCommandTool",
    "LarkCreateDocTool",
    "LarkMyTasksTool",
    "LarkRelatedTasksTool",
    "LarkSendMessageTool",
    "CreateScheduledTaskTool",
    "KnowledgeSearchTool",
    "KnowledgeListDocumentsTool",
]


def get_default_tools() -> list:
    """返回默认内置工具实例列表"""
    return [
        BashTool(),
        ReadFileTool(),
        WriteFileTool(),
        StrReplaceTool(),
        EditFileTool(),
        ListDirTool(),
        GlobSearchTool(),
        WebSearchTool(),
        CurrentTimeTool(),
        CreateScheduledTaskTool(),
    ]
