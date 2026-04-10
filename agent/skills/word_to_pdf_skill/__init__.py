"""
WordToPdfSkill —— Word 转 PDF（远程转换 + 预签名 URL）
"""

from __future__ import annotations

from pathlib import Path

from agent.skills.base import BaseSkill
from agent.tools.builtin.word_to_pdf import ConvertWordToPdfTool


class WordToPdfSkill(BaseSkill):
    """将本地 Word 转为 PDF，返回 presigned_url 供前端预览与下载"""

    name = "word_to_pdf"
    description = "将 .doc/.docx 转为 PDF，返回 presigned_url；需先激活本 Skill"
    skill_md_path = Path(__file__).parent / "SKILL.md"

    def get_tools(self) -> list:
        return [ConvertWordToPdfTool()]
