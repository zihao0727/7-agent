"""
主入口 —— 启动交互式 Agent REPL
用法：python main.py [--model MODEL] [--skill SKILL_MD_PATH]
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# 确保 agent 包可导入
sys.path.insert(0, str(Path(__file__).parent))

from agent import Agent
from agent.core.agent import AgentEvent

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    console = Console()
    HAS_RICH = True
except ImportError:
    console = None
    HAS_RICH = False


async def on_event(event: AgentEvent) -> None:
    if event.type == "tool_start":
        name = event.data["name"]
        args_str = str(event.data["input"])[:100]
        if HAS_RICH:
            console.print(f"  [dim yellow]▶ {name}  {args_str}[/dim yellow]")
        else:
            print(f"  [TOOL] {name}({args_str})")
    elif event.type == "tool_end":
        ok = not event.data["is_error"]
        icon = "✓" if ok else "✗"
        out = event.data["output"][:100]
        if HAS_RICH:
            c = "green" if ok else "red"
            console.print(f"  [dim {c}]{icon} {out}[/dim {c}]")
        else:
            print(f"  [{icon}] {out}")
    elif event.type == "error":
        if HAS_RICH:
            console.print(f"[bold red]错误: {event.data}[/bold red]")
        else:
            print(f"[ERROR] {event.data}")


async def repl(args: argparse.Namespace) -> None:
    api_key = args.api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("错误：请设置 ANTHROPIC_API_KEY 环境变量或传入 --api-key 参数")
        sys.exit(1)

    agent = Agent.create(
        api_key=api_key,
        model=args.model,
        on_event=on_event,
    )

    # 加载额外 Skill
    for skill_path in (args.skill or []):
        try:
            skill = agent.skill_registry.load_from_md(skill_path)
            await agent.skill_registry.activate(skill.name, agent.tool_registry, agent.context)
            print(f"[Skill '{skill.name}' 已加载并激活]")
        except Exception as e:
            print(f"[Skill 加载失败: {e}]")

    # 加载 MCP Server
    for mcp_cmd in (args.mcp or []):
        parts = mcp_cmd.split()
        try:
            await agent.load_mcp_stdio(parts[0], parts[1:] if len(parts) > 1 else None)
            print(f"[MCP Server '{mcp_cmd}' 已连接]")
        except Exception as e:
            print(f"[MCP 连接失败: {e}]")

    if HAS_RICH:
        console.print(Panel(
            f"[bold cyan]Agent Ready[/bold cyan]  model=[yellow]{args.model}[/yellow]  "
            f"tools=[green]{len(agent.tool_registry)}[/green]\n"
            "[dim]/quit 退出  /reset 重置  /tools 工具列表[/dim]",
            border_style="cyan",
        ))
    else:
        print(f"=== Agent 就绪 | 模型: {args.model} | 工具: {len(agent.tool_registry)} ===")

    while True:
        try:
            prompt = "\nYou> " if not HAS_RICH else "\n"
            if HAS_RICH:
                user_input = console.input("[bold green]You>[/bold green] ").strip()
            else:
                user_input = input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input in ("/quit", "/exit", "exit", "quit"):
            print("再见！")
            break
        if user_input == "/reset":
            agent.reset_context()
            print("[对话已重置]")
            continue
        if user_input == "/tools":
            print(f"工具列表: {agent.tool_registry.names()}")
            continue

        result = await agent.run(user_input)

        if HAS_RICH and result.text:
            console.print(Panel(
                Markdown(result.text),
                title="[blue]Assistant[/blue]",
                border_style="blue",
            ))
            console.print(
                f"[dim]工具={result.tool_calls_made} | "
                f"Token in={result.input_tokens} out={result.output_tokens} | "
                f"{result.elapsed_seconds:.1f}s[/dim]"
            )
        elif result.text:
            print(f"\nAssistant: {result.text}")

        if result.error:
            print(f"[警告] {result.error}")


def main():
    parser = argparse.ArgumentParser(
        description="Claude-Code 风格 Python Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py
  python main.py --model claude-3-5-sonnet-20241022
  python main.py --skill skills/git/SKILL.md
  python main.py --mcp "python mcp_server.py"
        """,
    )
    parser.add_argument("--model", default="claude-opus-4-5", help="Claude 模型名称")
    parser.add_argument("--api-key", help="Anthropic API Key（优先级高于环境变量）")
    parser.add_argument("--skill", action="append", metavar="PATH", help="SKILL.md 路径（可多次指定）")
    parser.add_argument("--mcp", action="append", metavar="CMD", help="MCP Server 启动命令（可多次指定）")

    args = parser.parse_args()
    asyncio.run(repl(args))


if __name__ == "__main__":
    main()
