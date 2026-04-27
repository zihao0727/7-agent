"""
代码执行 Skill —— 编写、运行代码并在右侧「代码执行」面板展示结果

激活后向 Agent 提供工具：
  run_code    在服务端执行 Python / JavaScript / TypeScript / Bash，
              输出与 matplotlib 图表写入当前会话，前端轮询展示。
"""

from pathlib import Path

from agent.skills.base import BaseSkill
from agent.tools.base import BaseTool
from agent.tools.builtin.run_code_tool import RunCodeTool


class CodeRunnerSkill(BaseSkill):
    name = "code_runner"
    description = (
        "代码执行：运行 Python/JS/TS/Bash，matplotlib 图表与终端输出展示在右侧代码面板"
    )
    skill_md_path = Path(__file__).parent / "SKILL.md"

    def get_tools(self) -> list[BaseTool]:
        return [RunCodeTool()]
