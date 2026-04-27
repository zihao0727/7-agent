"""
FastAPI 主应用 —— CORS + 路由挂载 + 启动初始化
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Windows：Playwright 依赖 asyncio 子进程；Selector 事件循环会触发
# NotImplementedError（无参），必须在创建事件循环之前设置策略。
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 确保项目根目录在 Python 路径中，以便 import agent/
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.auth_db import connect_auth_db, disconnect_auth_db
from backend.config import get_settings
from backend.db import connect_db, disconnect_db
from backend.routers import auth, browser, chat, code_runner, lark, memories, tools, skills, mcp, sessions
from backend.state import get_app_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

settings = get_settings()

app = FastAPI(
    title="Claude-Code Style Agent API",
    description="基于 DeepSeek + MCP 的 Agent 后端",
    version="0.1.0",
)

# CORS —— 允许前端开发服务器访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-vercel-ai-data-stream"],
)

# 路由挂载
app.include_router(chat.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(tools.router, prefix="/api")
app.include_router(skills.router, prefix="/api")
app.include_router(mcp.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(memories.router, prefix="/api")
app.include_router(browser.router, prefix="/api")
app.include_router(code_runner.router, prefix="/api")
app.include_router(lark.router, prefix="/api")


@app.on_event("startup")
async def startup():
    """应用启动时初始化"""
    # 连接 MongoDB
    await connect_db()
    await connect_auth_db()

    # 初始化工具注册表
    state = get_app_state()
    state.initialize()

    # 初始化浏览器会话管理器（惰性启动，此处仅创建单例）
    from agent.tools.builtin.browser_tools import init_browser_manager
    init_browser_manager()


@app.on_event("shutdown")
async def shutdown():
    """应用关闭时清理"""
    await disconnect_db()
    await disconnect_auth_db()
    # 关闭所有 Playwright 浏览器会话
    try:
        from agent.tools.builtin.browser_tools import get_browser_manager
        await get_browser_manager().cleanup()
    except Exception:
        pass


@app.get("/api/health")
async def health() -> dict:
    state = get_app_state()
    return {
        "status": "ok",
        "tools": len(state.tool_registry),
        "skills": len(state.skill_registry.names()),
        "mcp_servers": len(state.mcp_servers),
    }
