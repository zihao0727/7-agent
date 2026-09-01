"""
服务端完整 Agent 循环 —— Hermes 风格的 server-side loop

与现有的 agent_runner.py（单步执行）不同：
- 在服务端运行完整的 agentic loop，无需前端 maxSteps 驱动
- 支持长时间运行的后台任务
- 通过 SSE (Server-Sent Events) 实时推送进度
- 用户断开连接后任务继续运行
- 支持任务取消和状态查询
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.core.agent import Agent, AgentEvent
from agent.core.context import ConversationContext
from agent.llm.anthropic import AnthropicLLM
from agent.tools.registry import ToolRegistry
from agent.skills.registry import SkillRegistry
from backend.agent_task_service import (
    AgentTask,
    TaskStatus,
    create_task,
    get_task,
    list_tasks,
    cancel_task,
    register_running_task,
    update_task_status,
)
from backend.auth_dependencies import require_current_user
from backend.config import get_settings
from backend.db import get_db
from backend.memory_service import build_memory_context
from backend.skill_extractor import (
    extract_skill_from_session,
    get_active_skills_for_prompt,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent-loop", tags=["agent-loop"])


# ── 请求/响应模型 ──────────────────────────────────────────────────────────


class AgentLoopRequest(BaseModel):
    """创建 Agent 循环任务的请求"""
    session_id: str = Field(..., description="会话 ID")
    message: str = Field(..., description="用户输入")
    model: str = Field(default="claude-opus-4-5", description="使用的模型")
    max_iterations: int | None = Field(default=20, description="最大迭代次数")


class AgentLoopResponse(BaseModel):
    """任务创建响应"""
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    status: str
    progress: float
    result: str | None = None
    error: str | None = None
    tool_calls_count: int
    iterations: int
    created_at: str
    updated_at: str
    completed_at: str | None = None


# ── 端点 ──────────────────────────────────────────────────────────────────


@router.post("/start", response_model=AgentLoopResponse)
async def start_agent_loop(
    request: AgentLoopRequest,
    user_info: dict = Depends(require_current_user),
):
    """
    启动一个服务端 Agent 循环任务（异步）

    任务会在后台运行，即使客户端断开连接也会继续。
    使用 /stream/{task_id} 订阅任务进度。
    """
    user_id = user_info["id"]

    # 创建任务记录
    task = await create_task(
        user_id=user_id,
        session_id=request.session_id,
        input_text=request.message,
    )

    # 在后台启动 Agent 循环
    asyncio.create_task(
        _run_agent_loop_background(
            task=task,
            model=request.model,
            max_iterations=request.max_iterations,
        )
    )

    return AgentLoopResponse(
        task_id=task.task_id,
        status=TaskStatus.PENDING.value,
        message="任务已创建，正在启动...",
    )


@router.get("/stream/{task_id}")
async def stream_agent_progress(
    task_id: str,
    user_info: dict = Depends(require_current_user),
):
    """
    订阅 Agent 任务的实时进度（SSE）

    返回 Server-Sent Events 流，格式：
    - event: status / text / tool_call / tool_result / done / error
    - data: JSON 格式的事件数据
    """
    user_id = user_info["id"]

    # 检查任务是否存在
    task = await get_task(task_id, user_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    async def event_stream() -> AsyncIterator[str]:
        """SSE 事件流生成器"""
        # 发送初始状态
        yield _sse_event("status", task.to_dict())

        # 如果任务已经结束，直接返回结果
        if task.is_terminal():
            if task.status == TaskStatus.COMPLETED:
                yield _sse_event("done", {"result": task.result})
            elif task.status == TaskStatus.FAILED:
                yield _sse_event("error", {"error": task.error})
            elif task.status == TaskStatus.CANCELLED:
                yield _sse_event("cancelled", {"message": "任务已取消"})
            return

        # 轮询任务状态（实际生产环境应该用 Redis pub/sub 或 WebSocket）
        while True:
            await asyncio.sleep(0.5)

            # 重新获取任务状态
            updated_task = await get_task(task_id, user_id)
            if not updated_task:
                yield _sse_event("error", {"error": "任务不存在"})
                break

            # 发送状态更新
            yield _sse_event("status", updated_task.to_dict())

            # 如果任务结束，发送最终事件并退出
            if updated_task.is_terminal():
                if updated_task.status == TaskStatus.COMPLETED:
                    yield _sse_event("done", {"result": updated_task.result})
                elif updated_task.status == TaskStatus.FAILED:
                    yield _sse_event("error", {"error": updated_task.error})
                elif updated_task.status == TaskStatus.CANCELLED:
                    yield _sse_event("cancelled", {"message": "任务已取消"})
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    user_info: dict = Depends(require_current_user),
):
    """获取任务状态（非流式）"""
    user_id = user_info["id"]

    task = await get_task(task_id, user_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    task_dict = task.to_dict()
    return TaskStatusResponse(**task_dict)


@router.post("/cancel/{task_id}")
async def cancel_agent_task(
    task_id: str,
    user_info: dict = Depends(require_current_user),
):
    """取消运行中的任务"""
    user_id = user_info["id"]

    success = await cancel_task(task_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="任务不存在或已结束")

    return {"message": "任务取消请求已发送"}


@router.get("/list")
async def list_agent_tasks(
    session_id: str | None = Query(None, description="按会话 ID 过滤"),
    limit: int = Query(50, ge=1, le=200, description="返回数量限制"),
    user_info: dict = Depends(require_current_user),
):
    """列出用户的任务历史"""
    user_id = user_info["id"]

    tasks = await list_tasks(user_id, session_id=session_id, limit=limit)

    return {
        "tasks": [task.to_dict() for task in tasks],
        "total": len(tasks),
    }


# ── 后台任务执行 ────────────────────────────────────────────────────────────


async def _run_agent_loop_background(
    task: AgentTask,
    model: str,
    max_iterations: int | None,
) -> None:
    """
    在后台运行完整的 Agent 循环

    这个函数会：
    1. 初始化 Agent（加载工具、技能等）
    2. 运行完整的 agentic loop
    3. 更新任务状态
    4. 在任务完成后触发技能提取
    """
    try:
        # 注册为运行中的任务
        cancel_event = asyncio.Event()
        task.set_cancel_event(cancel_event)
        await register_running_task(task)

        logger.info(f"开始执行 Agent 任务: {task.task_id}")

        # 1. 获取用户的会话上下文
        session = await get_db()["sessions"].find_one({
            "_id": task.session_id,
            "user_id": task.user_id,
        })

        if not session:
            raise ValueError(f"会话不存在: {task.session_id}")

        messages = session.get("messages", [])

        # 2. 构建系统 prompt（包含记忆和技能）
        memory_context = await build_memory_context(task.user_id, messages)
        skills_context = await get_active_skills_for_prompt(task.user_id)

        system_prompt = get_settings().AGENT_SYSTEM_PROMPT
        if memory_context:
            system_prompt += f"\n\n{memory_context}"
        if skills_context:
            system_prompt += f"\n\n{skills_context}"

        # 3. 初始化 Agent
        settings = get_settings()
        llm = AnthropicLLM(
            api_key=settings.ANTHROPIC_API_KEY,
            model=model,
            max_tokens=8192,
        )

        tool_registry = ToolRegistry()
        skill_registry = SkillRegistry()
        context = ConversationContext(system_prompt=system_prompt)

        # 加载内置工具
        from agent.tools.builtin import get_default_tools
        tool_registry.register_many(get_default_tools())

        # 创建 Agent
        agent = Agent(
            llm=llm,
            tool_registry=tool_registry,
            skill_registry=skill_registry,
            context=context,
            max_iterations=max_iterations,
            on_event=None,  # 暂时不使用事件回调
        )

        # 4. 运行 Agent 循环
        result = await agent.run(task.input_text)

        # 5. 检查是否被取消
        if task.is_cancelled():
            await update_task_status(
                task.task_id,
                TaskStatus.CANCELLED,
                error="用户取消了任务",
            )
            logger.info(f"任务已取消: {task.task_id}")
            return

        # 6. 更新任务状态为完成
        await update_task_status(
            task.task_id,
            TaskStatus.COMPLETED,
            result=result.text,
            tool_calls_count=result.tool_calls_made,
            iterations=result.total_iterations,
            progress=1.0,
        )

        logger.info(
            f"任务完成: {task.task_id} "
            f"(工具调用: {result.tool_calls_made}, 迭代: {result.total_iterations})"
        )

        # 7. 保存对话历史到会话
        await _save_agent_result_to_session(task, result, agent.context)

        # 8. 触发自动技能提取（P0 核心功能）
        if result.tool_calls_made >= 5:  # 复杂任务阈值
            logger.info(f"检测到复杂任务，触发技能提取: {task.task_id}")
            asyncio.create_task(
                extract_skill_from_session(
                    user_id=task.user_id,
                    session_id=task.session_id,
                    messages=agent.context.to_api_messages(),
                    model="deepseek-v4-flash",
                )
            )

    except Exception as exc:
        logger.exception(f"Agent 任务执行失败: {task.task_id}")
        await update_task_status(
            task.task_id,
            TaskStatus.FAILED,
            error=str(exc),
        )


async def _save_agent_result_to_session(
    task: AgentTask,
    result: Any,
    context: ConversationContext,
) -> None:
    """将 Agent 执行结果保存到会话"""
    try:
        # 将 Agent 的对话历史追加到会话
        new_messages = context.to_api_messages()

        await get_db()["sessions"].update_one(
            {"_id": task.session_id, "user_id": task.user_id},
            {
                "$push": {"messages": {"$each": new_messages}},
                "$set": {"updated_at": "now"},
            }
        )

        logger.debug(f"已保存 {len(new_messages)} 条消息到会话 {task.session_id}")

    except Exception as exc:
        logger.error(f"保存 Agent 结果失败: {exc}")


def _sse_event(event_type: str, data: Any) -> str:
    """格式化 SSE 事件"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
