"""
示例 03：Skill 系统 —— 动态加载 SKILL.md，注入上下文和工具
演示 Git Skill 的完整生命周期
"""

import asyncio
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from agent import Agent
from agent.skills.base import BaseSkill
from agent.tools.base import BaseTool, ToolSchema, ToolExecutionError


# ── 定义 Git 工具 ──────────────────────────────────────────────────────────────

class GitStatusTool(BaseTool):
    name = "git_status"
    description = "查看 Git 仓库状态"

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "repo_path": {
                        "type": "string",
                        "description": "Git 仓库路径（默认当前目录）",
                        "default": ".",
                    }
                },
                "required": [],
            },
        )

    async def execute(self, repo_path: str = ".") -> str:
        import subprocess
        try:
            result = subprocess.run(
                ["git", "status", "--short"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = result.stdout or "(工作区干净)"
            return f"Git Status ({repo_path}):\n{output}"
        except FileNotFoundError:
            raise ToolExecutionError(self.name, "未安装 git 命令")


class GitLogTool(BaseTool):
    name = "git_log"
    description = "查看最近提交历史"

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "description": "显示最近 N 条（默认 5）", "default": 5},
                    "repo_path": {"type": "string", "description": "仓库路径", "default": "."},
                },
                "required": [],
            },
        )

    async def execute(self, n: int = 5, repo_path: str = ".") -> str:
        import subprocess
        try:
            result = subprocess.run(
                ["git", "log", f"-{n}", "--oneline"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout or "(无提交记录)"
        except FileNotFoundError:
            raise ToolExecutionError(self.name, "未安装 git 命令")


# ── 定义 Git Skill ─────────────────────────────────────────────────────────────

class GitSkill(BaseSkill):
    name = "git"
    description = "Git 版本控制 Skill：提供 git_status / git_log 等操作"

    def get_tools(self) -> list[BaseTool]:
        return [GitStatusTool(), GitLogTool()]

    def get_skill_md(self) -> str:
        return """
# Git Skill

你现在具备了 Git 版本控制能力。可用工具：
- `git_status`: 查看工作区变更状态
- `git_log`: 查看提交历史

## 使用规则
1. 操作前先用 git_status 了解当前状态
2. 提交前先检查变更是否符合预期
3. 告诉用户每个操作的结果
"""


async def main():
    agent = Agent.create(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        load_default_tools=True,
    )

    # 注册并激活 Git Skill
    agent.skill_registry.register(GitSkill())
    await agent.skill_registry.activate("git", agent.tool_registry, agent.context)

    print(f"已激活 Skill: {agent.skill_registry.active_names()}")
    print(f"已注册工具: {agent.tool_registry.names()}\n")

    # 也可以从 SKILL.md 文件动态加载
    # agent.skill_registry.load_from_md("path/to/SKILL.md")

    result = await agent.run("查看当前目录的 Git 状态和最近 3 条提交记录，并给我一个简短总结。")
    print(f"\n最终回答：{result.text}")


if __name__ == "__main__":
    asyncio.run(main())
