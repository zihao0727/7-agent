"""
示例 04：MCP 集成 —— 连接本地 MCP Server，自动发现并注册工具

本示例会：
1. 启动一个内置的演示 MCP Server（使用 mcp 库）
2. 通过 stdio 连接该 Server
3. 自动将 Server 的所有工具注册到 Agent
"""

import asyncio
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from agent import Agent


# ── 演示 MCP Server（内嵌，不需要额外文件）──────────────────────────────────

DEMO_MCP_SERVER_CODE = '''
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

app = Server("demo-mcp-server")

@app.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="add_numbers",
            description="将两个数字相加",
            inputSchema={
                "type": "object",
                "properties": {
                    "a": {"type": "number"},
                    "b": {"type": "number"},
                },
                "required": ["a", "b"],
            }
        ),
        types.Tool(
            name="reverse_string",
            description="反转字符串",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                },
                "required": ["text"],
            }
        ),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "add_numbers":
        result = arguments["a"] + arguments["b"]
        return [types.TextContent(type="text", text=str(result))]
    elif name == "reverse_string":
        result = arguments["text"][::-1]
        return [types.TextContent(type="text", text=result)]
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())

asyncio.run(main())
'''


async def main():
    # 将演示 Server 写到临时文件
    server_file = Path("/tmp/demo_mcp_server.py")
    server_file.write_text(DEMO_MCP_SERVER_CODE)

    agent = Agent.create(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        load_default_tools=False,
    )

    print("正在连接 MCP Server...")
    try:
        await agent.load_mcp_stdio(
            command=sys.executable,
            args=[str(server_file)],
        )
        print(f"MCP 工具已加载：{agent.tool_registry.names()}\n")
    except Exception as e:
        print(f"MCP 连接失败（可能未安装 mcp 库）: {e}")
        print("使用内置工具代替演示...\n")
        from agent.tools.builtin import get_default_tools
        agent.tool_registry.register_many(get_default_tools())

    result = await agent.run(
        "用 add_numbers 工具计算 123 + 456，再用 reverse_string 反转结果的字符串形式。"
    )
    print(f"\n最终回答：{result.text}")


if __name__ == "__main__":
    asyncio.run(main())
