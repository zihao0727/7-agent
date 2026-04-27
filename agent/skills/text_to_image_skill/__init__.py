"""
TextToImageSkill —— 文生图（异步任务 + 轮询）
"""

from __future__ import annotations

from pathlib import Path

from agent.skills.base import BaseSkill
from agent.tools.builtin.text_to_image_tool import TextToImageTool


class TextToImageSkill(BaseSkill):
    name = "text_to_image"
    description = "文生图：根据提示词生成图片，自动轮询任务直至返回图片链接"
    skill_md_path = Path(__file__).parent / "SKILL.md"

    def get_tools(self):
        return [TextToImageTool()]
