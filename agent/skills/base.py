"""
Skill 抽象基类 ——
每个 Skill 是一个可动态加载的"能力包"，包含：
  1. SKILL.md  → 说明文档，注入到 system prompt
  2. 附带的 Tool 列表，注册到 ToolRegistry
  3. 生命周期钩子（activate / deactivate）

这与 Cursor Agent Skills 架构直接对应。
"""

from __future__ import annotations

import abc
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..tools.base import BaseTool
    from ..tools.registry import ToolRegistry
    from ..core.context import ConversationContext


class BaseSkill(abc.ABC):
    """
    Skill 基类。

    最简子类示例::

        class GitSkill(BaseSkill):
            name = "git"
            skill_md_path = Path(__file__).parent / "SKILL.md"

            def get_tools(self) -> list[BaseTool]:
                return [GitStatusTool(), GitCommitTool()]
    """

    name: str = ""
    description: str = ""
    skill_md_path: Path | None = None   # SKILL.md 文件路径

    # ── 工具 ──────────────────────────────────────────────────────────────────

    def get_tools(self) -> list["BaseTool"]:
        """返回该 Skill 附带的工具列表（子类按需覆盖）"""
        return []

    # ── 上下文注入 ─────────────────────────────────────────────────────────────

    def get_skill_md(self) -> str:
        """读取并返回 SKILL.md 内容；若未定义则返回空字符串"""
        if self.skill_md_path and self.skill_md_path.exists():
            return self.skill_md_path.read_text(encoding="utf-8")
        return self.description

    # ── 生命周期 ──────────────────────────────────────────────────────────────

    async def activate(
        self,
        registry: "ToolRegistry",
        context: "ConversationContext",
    ) -> None:
        """
        Skill 激活时：
          1. 注册附带工具到 ToolRegistry
          2. 将 SKILL.md 注入 system prompt
        """
        tools = self.get_tools()
        registry.register_many(tools)
        skill_doc = self.get_skill_md()
        if skill_doc:
            context.inject_skill_context(skill_doc)

    async def deactivate(self, registry: "ToolRegistry") -> None:
        """Skill 停用时：从 ToolRegistry 中注销本 Skill 的工具"""
        for tool in self.get_tools():
            registry.unregister(tool.name)

    def __repr__(self) -> str:
        return f"<Skill: {self.name}>"


class FunctionSkill(BaseSkill):
    """
    用函数快速创建 Skill（无需子类化）::

        skill = FunctionSkill(
            name="greet",
            description="打招呼 Skill",
            tools=[GreetTool()],
        )
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        tools: list["BaseTool"] | None = None,
        skill_md: str = "",
    ) -> None:
        self.name = name
        self.description = description
        self._tools = tools or []
        self._skill_md = skill_md

    def get_tools(self) -> list["BaseTool"]:
        return self._tools

    def get_skill_md(self) -> str:
        return self._skill_md or self.description
