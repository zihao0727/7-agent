"""
示例 02：自定义工具 —— 使用 @tool 装饰器和 BaseTool 子类两种方式
"""

import asyncio
import os
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from agent import Agent
from agent.tools.base import BaseTool, ToolSchema, tool


# ── 方式一：@tool 装饰器（快速定义）──────────────────────────────────────────

@tool(name="get_weather", description="查询城市天气（模拟数据）")
async def get_weather(city: str, unit: str = "celsius") -> str:
    """模拟天气 API"""
    mock_data = {
        "北京": ("晴天", 22),
        "上海": ("多云", 18),
        "广州": ("雷雨", 28),
    }
    weather, temp = mock_data.get(city, ("未知", 0))
    unit_str = "°C" if unit == "celsius" else "°F"
    temp_val = temp if unit == "celsius" else temp * 9 / 5 + 32
    return f"{city}: {weather}，温度 {temp_val:.0f}{unit_str}"


# ── 方式二：BaseTool 子类（完整控制）────────────────────────────────────────

class CalculatorTool(BaseTool):
    """四则运算计算器"""

    name = "calculator"
    description = "执行数学计算，支持加减乘除和乘方"

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，如 '3 + 4 * 2'",
                    }
                },
                "required": ["expression"],
            },
        )

    async def execute(self, expression: str) -> str:
        # 安全求值（仅允许数字和运算符）
        allowed = set("0123456789+-*/().**%^ ")
        if any(c not in allowed for c in expression):
            return f"不安全的表达式: {expression}"
        try:
            result = eval(expression, {"__builtins__": {}})
            return f"{expression} = {result}"
        except Exception as e:
            return f"计算错误: {e}"


async def main():
    agent = Agent.create(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        load_default_tools=False,  # 不加载内置工具，只用自定义工具
    )

    # 注册自定义工具
    agent.add_tool(get_weather)
    agent.add_tool(CalculatorTool())

    print(f"已注册工具：{agent.tool_registry.names()}\n")

    result = await agent.run(
        "帮我查一下北京和上海的天气，然后计算两城温度之差的平方。"
    )
    print(f"\n最终回答：{result.text}")


if __name__ == "__main__":
    asyncio.run(main())
