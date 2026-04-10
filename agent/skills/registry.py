"""
SkillRegistry —— Skill 生命周期管理中心

职责：
  1. 注册 / 注销 Skill
  2. 激活指定 Skill（向 ToolRegistry 和 ConversationContext 注入能力）
  3. 从 SKILL.md 文件路径动态加载 Skill（对应 Cursor Agent Skills 机制）
  4. 列出当前激活的 Skill
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .base import BaseSkill, FunctionSkill

if TYPE_CHECKING:
    from ..tools.registry import ToolRegistry
    from ..core.context import ConversationContext

logger = logging.getLogger(__name__)


class SkillRegistry:
    """
    Skill 注册表，管理 Skill 的完整生命周期。

    使用示例::

        registry = SkillRegistry()
        registry.register(GitSkill())
        await registry.activate("git", tool_registry, context)
    """

    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}
        self._active: set[str] = set()

    # ── 注册 ──────────────────────────────────────────────────────────────────

    def register(self, skill: BaseSkill) -> None:
        self._skills[skill.name] = skill
        logger.debug("Registered skill: %s", skill.name)

    def register_many(self, skills: list[BaseSkill]) -> None:
        for s in skills:
            self.register(s)

    def load_from_md(self, skill_md_path: str | Path, name: str | None = None) -> BaseSkill:
        """
        从 SKILL.md 文件路径动态创建并注册一个 FunctionSkill。
        对应 Cursor Agent Skills 的 skill 描述文件机制。
        """
        p = Path(skill_md_path)
        if not p.exists():
            raise FileNotFoundError(f"SKILL.md 不存在: {p}")

        content = p.read_text(encoding="utf-8")
        skill_name = name or p.parent.name  # 用父目录名作为 skill 名

        # 解析 YAML frontmatter（若有）
        description = ""
        if content.startswith("---"):
            try:
                end = content.index("---", 3)
                frontmatter = content[3:end].strip()
                for line in frontmatter.splitlines():
                    if line.startswith("description:"):
                        description = line.split(":", 1)[1].strip().strip('"\'')
                        break
            except ValueError:
                pass

        skill = FunctionSkill(
            name=skill_name,
            description=description or f"Skill loaded from {p}",
            skill_md=content,
        )
        self.register(skill)
        logger.info("Loaded skill '%s' from %s", skill_name, p)
        return skill

    def load_from_directory(self, directory: str | Path) -> list[BaseSkill]:
        """
        扫描目录，自动加载所有 SKILL.md 文件。
        目录结构示例：
          skills/
            git/SKILL.md
            docker/SKILL.md
        """
        base = Path(directory)
        loaded = []
        for md_file in base.glob("**/SKILL.md"):
            skill = self.load_from_md(md_file)
            loaded.append(skill)
        return loaded

    # ── 激活 / 停用 ───────────────────────────────────────────────────────────

    async def activate(
        self,
        name: str,
        tool_registry: "ToolRegistry",
        context: "ConversationContext",
    ) -> None:
        """激活 Skill，注入工具和上下文"""
        skill = self._skills.get(name)
        if skill is None:
            raise KeyError(f"Skill '{name}' 未注册。可用: {self.names()}")
        if name not in self._active:
            await skill.activate(tool_registry, context)
            self._active.add(name)
            logger.info("Activated skill: %s", name)

    async def deactivate(
        self,
        name: str,
        tool_registry: "ToolRegistry",
    ) -> None:
        """停用 Skill，注销相关工具"""
        skill = self._skills.get(name)
        if skill and name in self._active:
            await skill.deactivate(tool_registry)
            self._active.discard(name)
            logger.info("Deactivated skill: %s", name)

    async def activate_all(
        self,
        tool_registry: "ToolRegistry",
        context: "ConversationContext",
    ) -> None:
        for name in list(self._skills.keys()):
            await self.activate(name, tool_registry, context)

    # ── 查询 ──────────────────────────────────────────────────────────────────

    def names(self) -> list[str]:
        return list(self._skills.keys())

    def active_names(self) -> list[str]:
        return list(self._active)

    def get(self, name: str) -> BaseSkill | None:
        return self._skills.get(name)

    def __repr__(self) -> str:
        return f"SkillRegistry(registered={self.names()}, active={self.active_names()})"
