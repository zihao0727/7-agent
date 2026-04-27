from __future__ import annotations

from pathlib import Path

from agent.skills.base import BaseSkill
from agent.tools.builtin.lark_cli_tool import LarkCliTool


class LarkCliSkill(BaseSkill):
    name = "lark_cli"
    description = "使用已绑定的飞书/Lark CLI 账户执行受控办公自动化操作"
    skill_md_path = Path(__file__).parent / "SKILL.md"

    def get_tools(self) -> list:
        return [LarkCliTool()]
