"""
示例 05：多轮交互终端 —— 类 Claude Code 的 REPL
支持持久上下文、流式输出、命令前缀
"""

import asyncio
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.live import Live
    from rich.markdown import Markdown
    _RICH = True
except ImportError:
    _RICH = False

from agent import Agent
from agent.core.agent import AgentEvent

console = Console() if _RICH else None


def print_header():
    if _RICH:
        console.print(Panel(
            "[bold cyan]Claude-Code Style Agent[/bold cyan]\n"
            "[dim]输入 /quit 退出 | /reset 重置对话 | /tools 查看工具 | /help 帮助[/dim]",
            border_style="cyan",
        ))
    else:
        print("=== Claude-Code Style Agent ===")
        print("命令: /quit 退出 | /reset 重置 | /tools 工具列表 | /help 帮助\n")


current_tool_output = []


async def on_event(event: AgentEvent) -> None:
    global current_tool_output
    if event.type == "tool_start":
        name = event.data["name"]
        inp = str(event.data["input"])[:80]
        if _RICH:
            console.print(f"  [dim yellow]⚙ {name}({inp})[/dim yellow]")
        else:
            print(f"  [工具] {name}({inp})")
    elif event.type == "tool_end":
        status = "✓" if not event.data["is_error"] else "✗"
        out = event.data["output"][:80]
        if _RICH:
            color = "green" if not event.data["is_error"] else "red"
            console.print(f"  [dim {color}]{status} {event.data['name']}: {out}[/dim {color}]")
        else:
            print(f"  [{status}] {event.data['name']}: {out}")


async def main():
    agent = Agent.create(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        system_prompt=(
            "你是一个强大的编程助手，运行在终端环境中。"
            "使用工具完成用户的编程、文件操作和系统管理任务。"
            "回答简洁、专业，代码用 Markdown 格式展示。"
        ),
        on_event=on_event,
    )

    print_header()

    while True:
        try:
            if _RICH:
                user_input = console.input("\n[bold green]You>[/bold green] ").strip()
            else:
                user_input = input("\nYou> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n再见！")
            break

        if not user_input:
            continue

        # 特殊命令
        if user_input == "/quit":
            print("再见！")
            break
        elif user_input == "/reset":
            agent.reset_context()
            print("[对话已重置]")
            continue
        elif user_input == "/tools":
            tools = agent.tool_registry.names()
            print(f"已注册工具 ({len(tools)} 个): {', '.join(tools)}")
            continue
        elif user_input == "/help":
            print("/quit - 退出  /reset - 重置对话  /tools - 工具列表")
            print("直接输入问题开始对话，Agent 会自动使用工具。")
            continue
        elif user_input.startswith("/load_skill "):
            path = user_input[12:].strip()
            try:
                agent.skill_registry.load_from_md(path)
                name = Path(path).parent.name
                await agent.skill_registry.activate(name, agent.tool_registry, agent.context)
                print(f"[Skill '{name}' 已激活]")
            except Exception as e:
                print(f"[加载失败] {e}")
            continue

        # 正常对话
        if _RICH:
            console.print(f"\n[dim]Agent 思考中…[/dim]")
        
        result = await agent.run(user_input)

        if _RICH:
            if result.text:
                console.print(Panel(
                    Markdown(result.text),
                    title="[bold blue]Assistant[/bold blue]",
                    border_style="blue",
                ))
            console.print(
                f"[dim]工具调用={result.tool_calls_made} | "
                f"Token={result.input_tokens}+{result.output_tokens} | "
                f"耗时={result.elapsed_seconds:.1f}s[/dim]"
            )
        else:
            print(f"\nAssistant: {result.text}")
            print(f"[工具={result.tool_calls_made}, Token={result.input_tokens}+{result.output_tokens}]")


if __name__ == "__main__":
    asyncio.run(main())
