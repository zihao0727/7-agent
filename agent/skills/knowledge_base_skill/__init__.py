from __future__ import annotations

from pathlib import Path

from agent.skills.base import BaseSkill
from agent.tools.base import BaseTool
from agent.tools.builtin.knowledge_base import KnowledgeListDocumentsTool, KnowledgeSearchTool


class KnowledgeBaseSkill(BaseSkill):
    name = "knowledge_base"
    description = (
        "Personal knowledge base backed by MongoDB. Searches indexed files, folders, web pages, "
        "and chat records, and returns citation-ready chunks."
    )
    skill_md_path = Path(__file__).parent / "SKILL.md"

    def get_tools(self) -> list[BaseTool]:
        return [KnowledgeSearchTool(), KnowledgeListDocumentsTool()]
