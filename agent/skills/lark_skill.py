from __future__ import annotations

from pathlib import Path

from agent.skills.base import BaseSkill
from agent.tools.builtin.lark import (
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


class LarkSkill(BaseSkill):
    name = "lark"
    description = "Feishu/Lark office automation skill pack for messages, docs, calendar, and OpenAPI."
    skill_md_path = Path(__file__).parent / "lark" / "SKILL.md"

    def get_tools(self) -> list:
        return [
            LarkAuthTool(),
            LarkSendMessageTool(),
            LarkCreateDocTool(),
            LarkCalendarQueryTool(),
            LarkCalendarCreateTool(),
            LarkMyTasksTool(),
            LarkRelatedTasksTool(),
            LarkApiTool(),
            LarkCommandTool(),
        ]
