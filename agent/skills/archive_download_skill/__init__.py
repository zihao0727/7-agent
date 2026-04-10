"""
ArchiveDownloadSkill —— 依据卷号下载档案文件 Skill
"""

from __future__ import annotations

from pathlib import Path
from agent.skills.base import BaseSkill
from agent.tools.builtin.archive_download import ArchiveDownloadTool


class ArchiveDownloadSkill(BaseSkill):
    """根据卷号下载档案压缩包的 Skill"""

    name = "archive_download"
    description = "根据卷号（jh）下载对应的档案压缩包文件"
    skill_md_path = Path(__file__).parent / "SKILL.md"

    def get_tools(self) -> list:
        """返回本 Skill 附带的工具"""
        return [ArchiveDownloadTool()]
