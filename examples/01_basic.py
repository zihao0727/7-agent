"""
示例 01：最基础用法 —— 单轮对话 + 工具调用
演示 Agent 如何通过 BashTool 列出文件目录
"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

# 项目根目录加入 Python 路径
import sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from agent import Agent
from agent.core.agent import AgentEvent


async def on_event(event: AgentEvent) -> None:
    """实时打印 Agent 执行事件"""
    if event.type == "text_chunk":
        print(f"\n[Assistant] {event.data}")
    elif event.type == "tool_start":
        print(f"\n[Tool →] {event.data['name']}({event.data['input']})")
    elif event.type == "tool_end":
        status = "✗" if event.data["is_error"] else "✓"
        print(f"[Tool {status}] {event.data['name']}: {event.data['output'][:100]}…")
    elif event.type == "error":
        print(f"\n[Error] {event.data}")


async def main():
    agent = Agent.create(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        system_prompt="你是一个终端助手，善用工具完成任务。",
        on_event=on_event,
    )

    print(f"Agent 已就绪：{agent}")
    print(f"已注册工具：{agent.tool_registry.names()}\n")
    print("=" * 60)

    result = await agent.run("请列出当前目录的文件，并告诉我有多少个 Python 文件。")

    print("\n" + "=" * 60)
    print(f"[统计] 工具调用次数={result.tool_calls_made}, "
          f"迭代次数={result.total_iterations}, "
          f"耗时={result.elapsed_seconds:.2f}s, "
          f"Token={result.input_tokens}+{result.output_tokens}")


if __name__ == "__main__":
    asyncio.run(main())
